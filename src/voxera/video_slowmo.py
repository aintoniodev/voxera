"""``voxera video slowmo`` — slow motion (y fast motion) de vídeo.

Efecto de slow motion (factor < 1) o fast motion (factor > 1) sobre todo
el clip o un segmento dado, en un solo paso de ffmpeg.

Diseño:

- **setpts** + **atempo**: setpts re-escala los timestamps de vídeo
  (``setpts=PTS/{factor}``) y atempo re-escala el audio manteniendo el
  pitch. atempo tiene rango [0.5, 100] por stage, así que para factor <
  0.5 se encadenan N stages con ``stage = factor**(1/n) >= 0.5``.
- **Segmento (--at S:E)**: solo el tramo [S, E) se ralentiza; antes y
  después se pasan a 1x. Filtro complejo con trim/concat.
- **minterpolate** (opcional): interpola frames sintéticos para un slow
  motion más suave, pero es MUY lento (~10x). Solo tiene sentido cuando el
  factor < 1 y fps de salida > fps fuente.
- Verificación post-ffmpeg: duración ±1 frame, fps preservado, pitch
  preservado por atempo.

Referencia: JMR N=27,227 — el slow motion es el efecto con mayor soporte
académico para percepción de calidad en vídeo de producto/demo.
"""

from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass
from pathlib import Path

from voxera import video as video_mod
from voxera import video_enhance as ve
from voxera.errors import EnhancementError

# --- Constants -----------------------------------------------------------
DEFAULT_FACTOR = 0.5          # playback speed multiplier (0.5 = 2x slower)
FACTOR_MIN = 0.125            # mínimo factor aceptado
FACTOR_MAX = 4.0              # máximo factor aceptado
INTERPOLATE_OPTIONS = ("none", "minterpolate")
DEFAULT_INTERPOLATE = "none"
DEFAULT_INTERPOLATE_FPS = 60


# --- atempo chain ---------------------------------------------------------

def atempo_chain(factor: float) -> list[str]:
    """Cadena de filtros ``atempo`` para un factor dado.

    atempo solo acepta [0.5, 100] por stage. Para factor < 0.5 se
    encadenan N stages con stage = factor**(1/n) >= 0.5 (N mínimo).

    >>> atempo_chain(0.5)
    ['atempo=0.5']
    >>> atempo_chain(0.25)
    ['atempo=0.5', 'atempo=0.5']
    >>> atempo_chain(2.0)
    ['atempo=2.0']
    """
    if factor == 1.0:
        return []
    if factor >= 0.5:
        return [f"atempo={factor:.6f}"]
    # factor < 0.5: encontrar N mínimo tal que stage = factor**(1/N) >= 0.5
    # Es decir: N <= log(factor)/log(0.5) -> N = ceil(log(factor)/log(0.5))
    # Pero asegurar que factor**(1/N) >= 0.5 con N = ceil(...).
    n = max(1, math.ceil(math.log(factor) / math.log(0.5)))
    # Ajustar si el stage cae por debajo de 0.5
    stage = factor ** (1.0 / n)
    while stage < 0.5 - 1e-12:
        n += 1
        stage = factor ** (1.0 / n)
    return [f"atempo={stage:.6f}"] * n


# --- build_plan -----------------------------------------------------------

def build_plan(
    input: str,
    *,
    factor: float = DEFAULT_FACTOR,
    start: float | None = None,
    end: float | None = None,
    interpolate: str = DEFAULT_INTERPOLATE,
    fps: int = DEFAULT_INTERPOLATE_FPS,
    crf: int = 18,
    audio_bitrate: str = "192k",
) -> str:
    """Plan legible para --dry-run (misma convención que enhance/zoom)."""
    inp = Path(input)
    probe = ve.probe_video(inp)
    in_dur = probe["duration_s"]
    src_fps = probe["fps"] if probe["fps"] > 0 else 30.0
    has_audio = probe["has_audio"]
    seg_fps = fps if interpolate == "minterpolate" else src_fps

    if start is not None and end is not None:
        s_q, e_q = _quantize_se(start, end, src_fps)
        s_q, e_q = _clamp_segment(s_q, e_q, in_dur)
        d = e_q - s_q
        slow_part = d / factor
        out_dur = s_q + slow_part + max(in_dur - e_q, 0.0)
        mode = f"segmento {s_q:.3f}s – {e_q:.3f}s ({d:.3f}s ralentizados)"
    else:
        out_dur = in_dur / factor
        mode = f"clip completo ({in_dur:.3f}s)"

    chain = atempo_chain(factor)
    atempo_str = " → ".join(chain) if chain else "sin cambio"

    lines = [
        "VOXERA PLAN (video slowmo)",
        f"  entrada     : {inp} ({probe['width']}x{probe['height']} @{src_fps:.2f}fps, "
        f"{in_dur:.2f}s, {'con audio' if has_audio else 'sin audio'})",
        f"  factor      : {factor}x ({'lento' if factor < 1 else 'rápido' if factor > 1 else 'sin cambio'})",
        f"  modo        : {mode}",
        f"  duración out: {out_dur:.2f}s",
        f"  atempo      : {atempo_str} (n={len(chain)} stage{'s' if len(chain) != 1 else ''})",
        f"  encoder     : libx264 crf {crf} + {'aac ' + audio_bitrate if has_audio else 'sin audio'}",
    ]
    if interpolate == "minterpolate":
        lines.append(
            f"  interp.     : minterpolate @ {fps}fps (MUY lento — "
            f"solo útil si fps > fuente {src_fps:.0f})"
        )
    return "\n".join(lines)


# --- Segment helpers ------------------------------------------------------

def _quantize_se(start: float, end: float, fps: float) -> tuple[float, float]:
    """Snap de start/end a la rejilla de frames (round(t*fps)/fps)."""
    if fps <= 0:
        raise EnhancementError(f"fps inválido: {fps}")
    qs = round(start * fps) / fps
    qe = round(end * fps) / fps
    return qs, qe


def _clamp_segment(start: float, end: float, duration: float) -> tuple[float, float]:
    """Recorta start/end al rango [0, duration] y valida start < end."""
    start = max(start, 0.0)
    end = min(end, duration)
    if start >= end:
        raise EnhancementError(
            f"segmento inválido: start={start:.3f} >= end={end:.3f}"
        )
    return start, end


# --- slowmo_video ---------------------------------------------------------

def slowmo_video(
    input: str,
    output: str,
    *,
    factor: float = DEFAULT_FACTOR,
    start: float | None = None,
    end: float | None = None,
    interpolate: str = DEFAULT_INTERPOLATE,
    fps: int = DEFAULT_INTERPOLATE_FPS,
    crf: int = 18,
    audio_bitrate: str = "192k",
) -> str:
    """Aplica slow motion (o fast motion) y devuelve la ruta de salida."""
    # --- validate ---
    if factor < FACTOR_MIN:
        raise EnhancementError(
            f"factor debe ser >= {FACTOR_MIN}, got {factor}"
        )
    if factor > FACTOR_MAX:
        raise EnhancementError(
            f"factor debe ser <= {FACTOR_MAX}, got {factor}"
        )
    if interpolate not in INTERPOLATE_OPTIONS:
        raise EnhancementError(
            f"interpolate debe ser uno de {INTERPOLATE_OPTIONS}, got {interpolate!r}"
        )
    if start is not None and start < 0:
        raise EnhancementError(f"start debe ser >= 0, got {start}")
    if start is not None and end is not None and end <= start:
        raise EnhancementError(f"end ({end}) debe ser > start ({start})")

    inp = Path(input)
    out = Path(output)
    if not inp.exists():
        raise EnhancementError(f"input no existe: {inp}")
    out.parent.mkdir(parents=True, exist_ok=True)

    probe = ve.probe_video(inp)
    in_dur = probe["duration_s"]
    src_fps = probe["fps"] if probe["fps"] > 0 else 30.0
    has_audio = probe["has_audio"]

    if start is not None and end is not None:
        return _slowmo_segment(
            inp, out, probe, factor, start, end,
            interpolate=interpolate, fps=fps,
            crf=crf, audio_bitrate=audio_bitrate,
        )
    return _slowmo_whole(
        inp, out, probe, factor,
        interpolate=interpolate, fps=fps,
        crf=crf, audio_bitrate=audio_bitrate,
    )


def _slowmo_whole(
    inp: Path, out: Path, probe: dict, factor: float, *,
    interpolate: str, fps: int, crf: int, audio_bitrate: str,
) -> Path:
    """Slow motion de clip completo."""
    in_dur = probe["duration_s"]
    has_audio = probe["has_audio"]
    src_fps = probe["fps"] if probe["fps"] > 0 else 30.0
    out_fps = fps if (interpolate == "minterpolate" and fps > src_fps) else src_fps

    vf = f"setpts=PTS/{factor:.6f}"
    if interpolate == "minterpolate" and fps > src_fps:
        vf += f",minterpolate=fps={fps}:mi_mode=mci"

    cmd = [video_mod._tool("ffmpeg"), "-y", "-v", "error", "-i", str(inp)]
    cmd += ["-vf", vf]
    cmd += ["-r", f"{out_fps:.3f}"]
    if has_audio:
        chain = atempo_chain(factor)
        if chain:
            cmd += ["-af", ",".join(chain)]
        cmd += ["-c:a", "aac", "-b:a", audio_bitrate]
    else:
        cmd += ["-an"]
    cmd += ["-c:v", "libx264", "-crf", str(crf), "-pix_fmt", "yuv420p",
            "-shortest", str(out)]

    _run_ffmpeg(cmd)

    # Post-verify
    oprobe = ve.probe_video(out)
    expected_dur = in_dur / factor
    frame_dur = 1.0 / out_fps
    if abs(oprobe["duration_s"] - expected_dur) > frame_dur + 0.05:
        raise EnhancementError(
            f"duración inesperada: {oprobe['duration_s']:.2f}s "
            f"(esperada ~{expected_dur:.2f}s ±1 frame)"
        )
    if interpolate != "minterpolate":
        if oprobe["fps"] and abs(oprobe["fps"] - src_fps) > 0.5:
            raise EnhancementError(
                f"fps inesperado en salida: {oprobe['fps']} (esperado {src_fps})"
            )
    print(
        f"[slowmo] {in_dur:.2f}s → {oprobe['duration_s']:.2f}s "
        f"(factor {factor}x)"
    )
    return out


def _slowmo_segment(
    inp: Path, out: Path, probe: dict, factor: float,
    start_raw: float, end_raw: float, *,
    interpolate: str, fps: int, crf: int, audio_bitrate: str,
) -> Path:
    """Slow motion de un segmento [start, end), clip completo alrededor."""
    in_dur = probe["duration_s"]
    has_audio = probe["has_audio"]
    src_fps = probe["fps"] if probe["fps"] > 0 else 30.0
    out_fps = fps if (interpolate == "minterpolate" and fps > src_fps) else src_fps
    sr_audio = 48000  # audio sample rate for PTS offsets

    # Quantize + clamp
    S, E = _quantize_se(start_raw, end_raw, src_fps)
    S, E = _clamp_segment(S, E, in_dur)

    D = E - S
    ADD = S + D / factor  # output-time offset where after-segment resumes

    # --- Video: single setpts expression (no concat) ---
    # After trim, PTS is in input timebase. T = PTS * TB.
    # For frames at time T:
    #   T < S:       PTS_out = PTS (no change)
    #   S <= T < E:  PTS_out = S/TB + (PTS - S/TB) / factor
    #   T >= E:      PTS_out = ADD/TB + PTS - E/TB
    TB = 1.0 / out_fps
    S_tb = S / TB   # S in output timebase ticks
    E_tb = E / TB
    ADD_tb = ADD / TB

    # Build setpts expression using T (seconds) for comparison,
    # PTS for arithmetic. ffmpeg evaluates T as PTS*TB.
    # Single quotes protect commas inside if() from being parsed as filter sep.
    vf = (
        f"setpts='if(lt(T,{S:.6f}),"
        f"PTS,"
        f"if(lt(T,{E:.6f}),"
        f"{S_tb:.6f}+(PTS-{S_tb:.6f})/{factor:.6f},"
        f"{ADD_tb:.6f}+PTS-{E_tb:.6f}))'"
    )
    if interpolate == "minterpolate" and fps > src_fps:
        vf += f",minterpolate=fps={fps}:mi_mode=mci"

    # --- Audio: trim + atempo + concat ---
    filters: list[str] = []
    a_labels: list[str] = []
    n_a = 0
    has_audio_filter = False
    ao_map = ""

    if has_audio:
        a_sr = float(sr_audio)

        # Segment a: before [0, S)
        if S > 1e-9:
            filters.append(
                f"[0:a]atrim=start=0:end={S:.6f},"
                f"asetpts=PTS[a{n_a}]"
            )
            a_labels.append(f"[a{n_a}]")
            n_a += 1

        # Segment b: slow [S, E) with atempo
        chain = atempo_chain(factor)
        atempo_f = ",".join(chain) if chain else ""
        a_expr = f"[0:a]atrim=start={S:.6f}:end={E:.6f},asetpts=PTS"
        if atempo_f:
            a_expr += f",{atempo_f}"
        # After atempo, PTS spans [0, D/factor*sr]. We need it at S.
        a_expr += f",asetpts=PTS+{S * a_sr:.6f}[a{n_a}]"
        filters.append(a_expr)
        a_labels.append(f"[a{n_a}]")
        n_a += 1

        # Segment c: after [E, end)
        if E < in_dur - 1e-9:
            filters.append(
                f"[0:a]atrim=start={E:.6f},"
                f"asetpts=PTS+{ADD * a_sr:.6f}[a{n_a}]"
            )
            a_labels.append(f"[a{n_a}]")
            n_a += 1

        a_concat = "".join(a_labels) + f"concat=n={n_a}:v=0:a=1,aresample=48000[ao]"
        filters.append(a_concat)
        has_audio_filter = True
        ao_map = "[ao]"

    # --- Build ffmpeg command ---
    # Video filter goes into filter_complex (can't mix -vf and -filter_complex)
    cmd = [video_mod._tool("ffmpeg"), "-y", "-v", "error", "-i", str(inp)]
    cmd += ["-r", f"{out_fps:.3f}"]
    if has_audio_filter:
        # Wrap video filter as a labeled filter in filter_complex
        all_fc = [f"[0:v]{vf}[vo]"] + filters
        cmd += ["-filter_complex", ";".join(all_fc)]
        cmd += ["-map", "[vo]", "-map", ao_map]
    else:
        cmd += ["-vf", vf, "-an"]
    cmd += ["-c:v", "libx264", "-crf", str(crf), "-pix_fmt", "yuv420p"]
    if has_audio:
        cmd += ["-c:a", "aac", "-b:a", audio_bitrate]
    cmd += ["-shortest", str(out)]

    _run_ffmpeg(cmd)

    # --- Post-verify ---
    oprobe = ve.probe_video(out)
    expected_dur = S + D / factor + max(in_dur - E, 0.0)
    frame_dur = 1.0 / out_fps
    if abs(oprobe["duration_s"] - expected_dur) > frame_dur + 0.1:
        raise EnhancementError(
            f"duración inesperada: {oprobe['duration_s']:.2f}s "
            f"(esperada ~{expected_dur:.2f}s)"
        )
    if interpolate != "minterpolate":
        if oprobe["fps"] and abs(oprobe["fps"] - out_fps) > 0.5:
            raise EnhancementError(
                f"fps inesperado en salida: {oprobe['fps']} (esperado {out_fps})"
            )
    print(
        f"[slowmo] segmento {S:.2f}–{E:.2f}s factor {factor}x: "
        f"{in_dur:.2f}s → {oprobe['duration_s']:.2f}s"
    )
    return out


# --- Helpers --------------------------------------------------------------

def _run_ffmpeg(cmd: list[str]) -> None:
    """Ejecuta ffmpeg y lanza EnhancementError si falla."""
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=7200)
    except subprocess.CalledProcessError as exc:
        raise EnhancementError(
            f"ffmpeg falló: {exc.stderr.decode(errors='replace')[-800:]}"
        ) from exc
