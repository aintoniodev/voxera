"""``voxera video cutsilence`` — eliminación automática de silencios en vídeo.

Edición automática estilo TikTok/CapCut "remove silence": detecta los
silencios entre frases y los recorta del vídeo Y del audio a la vez,
generando jump-cuts con sync A/V exacto. Un solo paso de ffmpeg, sin GPU,
sin Premiere, sin edición manual.

Diseño:

- Reutiliza el VAD de envolvente de ``voxera silence`` (mismo margen de
  respiración de 200 ms alrededor de la voz: las respiraciones nunca se
  cortan).
- Los gaps > trigger (--level: light 1.5 s / medium 0.8 s / aggressive 0.4 s)
  se recortan a ``--keep`` segundos (default 0.15 s — el padding que evita
  el sonido robótico del corte a cero; ``--keep 0`` = corte total).
- Los cortes se cuantizan a la rejilla de frames del vídeo (n/fps): el audio
  se corta en los MISMOS instantes que el vídeo, así el sync es perfecto
  frame a frame (sin drift acumulado).
- ffmpeg: ``select``/``aselect`` con la misma expresión de rangos [a, b)
  (gte*lt — extremo superior EXCLUSIVO, para que el primer frame de cada
  silencio se caiga) + ``setpts``/``asetpts`` que re-empaquetan los
  timestamps contiguos desde 0.

Verificación (misma disciplina que los demás efectos): duración de salida =
suma de tramos conservados (±0.25 s), fps preservado, y en tests sync
A/V < 0.1 s + conteo de frames exacto.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from voxera import audioio
from voxera import video as video_mod
from voxera import video_enhance as ve
from voxera.errors import EnhancementError
from voxera.silence import _envelope_segments_samples, LEVELS

SR = audioio.INTERNAL_SAMPLE_RATE  # 48000 — formato interno (todos los cortes en esta rejilla)
DEFAULT_KEEP = 0.15                # padding de silencio conservado en cada corte
MAX_KEEP = 2.0
TRIGGERS = {k: v[0] for k, v in LEVELS.items()}  # light 1.5 / medium 0.8 / aggressive 0.4


@dataclass(frozen=True)
class CutSilenceOptions:
    """Parámetros de la edición automática de silencios.

    Un solo default sensato (medium + keep 0.15 s — ritmo natural de
    jump-cut); el resto son escapes. ``level`` fija el trigger (gap mínimo
    que se considera silencio a cortar); ``keep`` cuánto silencio queda en
    cada corte (0 = cortes a cero, sonido encadenado).
    """

    level: str = "medium"
    keep: float = DEFAULT_KEEP
    crf: int = 18
    audio_bitrate: str = "192k"

    def validate(self) -> None:
        if self.level not in TRIGGERS:
            raise EnhancementError(
                f"level debe ser uno de {sorted(TRIGGERS)}, got {self.level!r}"
            )
        if not 0.0 <= self.keep <= MAX_KEEP:
            raise EnhancementError(f"keep debe estar en [0, {MAX_KEEP}]s, got {self.keep}")
        if not 0 < self.crf <= 51:
            raise EnhancementError(f"crf debe estar en (0, 51], got {self.crf}")


def detect_keep_parts(samples: np.ndarray, level: str, keep: float) -> list[tuple[float, float]]:
    """Tramos [inicio, fin) en segundos que se CONSERVAN.

    La voz (segmentos del VAD, ya con el margen de respiración de 200 ms)
    se conserva siempre entera. Cada gap > trigger se recorta a ``keep``
    segundos desde su inicio; los gaps cortos quedan intactos. El gap
    inicial/final del vídeo siguen la misma regla.
    """
    trigger = TRIGGERS[level]
    x = np.asarray(samples, dtype=np.float32)
    total = len(x) / SR
    segments = _envelope_segments_samples(x)
    segs_s = [(a / SR, min(b / SR, total)) for a, b in segments]
    if not segs_s:
        return []  # sin voz detectable: no hay nada que conservar

    parts: list[tuple[float, float]] = []
    prev = 0.0
    for a, b in segs_s:
        if a - prev > trigger:
            parts.append((prev, min(prev + keep, a)))  # gap largo: solo keep s
        else:
            parts.append((prev, a))  # gap corto: entero
        parts.append((a, b))  # voz: siempre entera
        prev = b
    if total - prev > trigger:
        parts.append((prev, min(prev + keep, total)))
    else:
        parts.append((prev, total))
    # fusión de tramos contiguos (p. ej. gap corto + voz + gap corto)
    merged: list[tuple[float, float]] = []
    for a, b in parts:
        if b - a <= 1e-6:
            continue
        if merged and a <= merged[-1][1] + 1e-6:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


def quantize_frames(parts: list[tuple[float, float]], fps: float) -> list[tuple[float, float]]:
    """Snap de los cortes a la rejilla de frames (n/fps).

    Es lo que garantiza el sync: el audio se corta en los mismos instantes
    que el vídeo. Tramos sub-frame se descartan; tramos que quedan pegados
    tras el snap se fusionan.
    """
    if fps <= 0:
        raise EnhancementError(f"fps inválido: {fps}")
    out: list[tuple[float, float]] = []
    frame = 1.0 / fps
    for a, b in parts:
        qa = round(a * fps) / fps
        qb = round(b * fps) / fps
        if qb - qa < 0.5 * frame:
            continue
        if out and qa <= out[-1][1] + 1e-9:
            out[-1] = (out[-1][0], max(out[-1][1], qb))
        else:
            out.append((qa, qb))
    return out


def build_cut_filters(parts: list[tuple[float, float]], fps: float) -> tuple[str, str]:
    """(vf, af): select/aselect con la MISMA expresión de rangos [a, b).

    ``gte(t,a)*lt(t,b)`` en vez de ``between(t,a,b)``: el extremo superior
    es exclusivo, así el primer frame de cada silencio se cae (sin frame
    extra por corte). asetpts usa 48000 porque aresample normaliza antes.
    """
    if not parts:
        raise EnhancementError("no hay tramos que conservar (sin voz detectable)")
    terms = "+".join(f"gte(t,{a:.6f})*lt(t,{b:.6f})" for a, b in parts)
    vf = f"select='{terms}',setpts=N/{fps:.6f}/TB"
    af = f"aresample={SR},aselect='{terms}',asetpts=N/{SR}/TB"
    return vf, af


def _load_audio(video: str | Path) -> np.ndarray:
    """Extrae y carga el audio del vídeo a 48 kHz mono float32 (formato interno)."""
    tmp = video_mod.temp_wav()
    try:
        video_mod.extract_audio(video, tmp)
        return np.asarray(audioio.load_audio(tmp).samples, dtype=np.float32)
    finally:
        tmp.unlink(missing_ok=True)


def _cut_count(parts: list[tuple[float, float]], total: float) -> int:
    """Número de cortes = huecos entre tramos conservados + leading/trailing."""
    cuts = 0
    prev = 0.0
    for a, b in parts:
        if a - prev > 1e-9:
            cuts += 1
        prev = b
    if total - prev > 1e-9:
        cuts += 1
    return cuts


def build_plan(input: str | Path, opts: CutSilenceOptions) -> str:
    """Plan legible para --dry-run (misma convención que enhance/zoom)."""
    opts.validate()
    inp = Path(input)
    probe = ve.probe_video(inp)
    if not probe["has_audio"]:
        raise EnhancementError(f"sin pista de audio: {inp}")
    x = _load_audio(inp)
    in_dur = len(x) / SR
    parts = detect_keep_parts(x, opts.level, opts.keep)
    fps = probe["fps"] if probe["fps"] > 0 else 30.0
    quant = quantize_frames(parts, fps)
    out_dur = sum(b - a for a, b in quant)
    vf, af = build_cut_filters(quant, fps)
    removed = in_dur - out_dur
    return "\n".join(
        [
            "VOXERA PLAN (video cutsilence)",
            f"  entrada : {inp} ({probe['width']}x{probe['height']} @{fps:.2f}fps, "
            f"{in_dur:.2f}s, con audio)",
            f"  nivel   : {opts.level} (trigger {TRIGGERS[opts.level]:.2f}s) · "
            f"keep {opts.keep:.2f}s · margen respiración 0.20s",
            f"  corte   : {_cut_count(quant, in_dur)} cortes — conserva "
            f"{len(quant)} tramos: {in_dur:.2f}s → {out_dur:.2f}s "
            f"(elimina {removed:.2f}s, {100 * removed / max(in_dur, 1e-9):.1f}%)",
            f"  filtro  : vf={vf}",
            f"            af={af}",
            f"  encoder : libx264 crf {opts.crf} + aac {opts.audio_bitrate} "
            f"(re-encode de ambos streams, sync frame-accurate)",
        ]
    )


def cutsilence_video(input: str | Path, output: str | Path, opts: CutSilenceOptions) -> Path:
    """Elimina los silencios del vídeo (audio + vídeo, sync exacto) y
    devuelve la ruta de salida (verificada)."""
    opts.validate()
    inp = Path(input)
    out = Path(output)
    if not inp.exists():
        raise EnhancementError(f"input no existe: {inp}")
    out.parent.mkdir(parents=True, exist_ok=True)

    probe = ve.probe_video(inp)
    if not probe["has_audio"]:
        raise EnhancementError(f"sin pista de audio: {inp} (no se puede detectar silencio)")

    x = _load_audio(inp)
    in_dur = len(x) / SR
    parts = detect_keep_parts(x, opts.level, opts.keep)
    if not parts:
        raise EnhancementError(f"sin voz detectable en {inp}: no hay nada que conservar")
    fps = probe["fps"] if probe["fps"] > 0 else 30.0
    quant = quantize_frames(parts, fps)
    out_dur = sum(b - a for a, b in quant)

    # Sin silencios que cortar: copia directa (el vídeo ya está editado).
    if len(quant) == 1 and quant[0][0] <= 0.01 and in_dur - quant[0][1] <= 0.01:
        print(
            f"[cutsilence] sin silencios > {TRIGGERS[opts.level]:.2f}s: copia directa"
        )
        shutil.copyfile(inp, out)
        return out

    vf, af = build_cut_filters(quant, fps)
    print(
        f"[cutsilence] {len(quant)} tramos conservados, {_cut_count(quant, in_dur)} cortes: "
        f"{in_dur:.2f}s → {out_dur:.2f}s ({in_dur - out_dur:.2f}s de silencio eliminados)"
    )

    cmd = [video_mod._tool("ffmpeg"), "-y", "-v", "error", "-i", str(inp),
           "-vf", vf, "-af", af,
           "-c:v", "libx264", "-crf", str(opts.crf), "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", opts.audio_bitrate,
           "-shortest", str(out)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=7200)
    except subprocess.CalledProcessError as exc:
        raise EnhancementError(
            f"ffmpeg falló: {exc.stderr.decode(errors='replace')[-800:]}"
        ) from exc

    oprobe = ve.probe_video(out)
    if abs(oprobe["duration_s"] - out_dur) > 0.3:
        raise EnhancementError(
            f"duración inesperada: {oprobe['duration_s']:.2f}s (esperada ~{out_dur:.2f}s)"
        )
    if oprobe["fps"] and abs(oprobe["fps"] - fps) > 0.5:
        raise EnhancementError(
            f"fps inesperado en salida: {oprobe['fps']} (esperado {fps})"
        )
    return out
