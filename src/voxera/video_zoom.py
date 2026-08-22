"""``voxera video zoom`` — zoom "Grow": push-in con curva de easing (sin Premiere).

Replicación programática del truco del tutorial de @serri.mp4 (Premiere):
en vez de un zoom lineal "aburrido", un zoom con **curva de easing** anclado
a un **punto de anclaje** (p. ej. la cara), con la curva entre 60 y 65.

Implementación: 100 % ffmpeg (sin GPU, sin Premiere, sin keyframes a mano).
Pipeline por frame: upscale supersampled (SS=2) -> crop animado por expresión
(anchored en el punto elegido) -> downscale lanczos. El supersampling evita
el jitter subpíxel típico de zoompan con zooms lentos.

Curva de easing (0-100, default 62 — el rango 60-65 del tutorial):
  - smooth (default): S-curva simétrica p^a/(p^a+(1-p)^a), a = 1+curve/25
  - out: arranca rápido y decelera: 1-(1-p)^(1+curve/50)   ("punch-in")
  - in : arranca lento y acelera: p^(1+curve/50)
  - linear: sin curva (el zoom "aburrido" que el tutorial quiere evitar)
curve=0  => siempre lineal, en cualquier easing.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from voxera import video as video_mod
from voxera import audioio
from voxera.errors import EnhancementError
from voxera import video_enhance as ve

ZOOM_EASINGS = ("smooth", "out", "in", "linear")
ZOOM_DIRECTIONS = ("grow", "shrink", "pulse")
DEFAULT_PCT = 40.0          # % de zoom final — medido en el tutorial: la demo real es +40% en 4s
DEFAULT_CURVE = 62.0        # curva 60-65 del tutorial
DEFAULT_ANCHOR = (0.5, 0.5)  # centro; para talking-head usar ~(0.5, 0.33)
DEFAULT_DIRECTION = "grow"
DEFAULT_HOLD = 0.0          # fracción de la duración en el pico (pulse)
SUPERSAMPLE = 2             # x2 = precisión subpíxel 0.5px (sin jitter en zooms lentos)


@dataclass(frozen=True)
class ZoomOptions:
    """Parámetros de un zoom Grow. Un solo default sensato; el resto escapes.

    Medición del tutorial de @serri.mp4 (frame a frame, ECC): la demo real es
    un zoom-in 1.0 -> 1.40 en ~4 s con curva S (pico de velocidad ~60% de la
    duración — la "curva 60-65"), anclado en el sujeto; también demuestra un
    shrink 1.0 -> 0.77. Direcciones: grow (ampliar), shrink (reducir,
    ventana negra), pulse (ampliar y reducir).
    """

    pct: float = DEFAULT_PCT
    anchor: tuple[float, float] = DEFAULT_ANCHOR
    curve: float = DEFAULT_CURVE
    easing: str = "smooth"
    direction: str = DEFAULT_DIRECTION
    hold: float = DEFAULT_HOLD
    auto_emphasis: bool = False
    pulse_dur: float = 3.0
    max_pulses: int = 4
    start: float | None = None
    end: float | None = None
    ss: int = SUPERSAMPLE
    crf: int = 18
    audio_bitrate: str = "192k"

    def validate(self) -> None:
        if not 0 < self.pct <= 200:
            raise EnhancementError(f"pct debe estar en (0, 200], got {self.pct}")
        if self.direction == "shrink" and self.pct >= 100:
            raise EnhancementError(
                f"shrink necesita pct < 100 (imagen no puede reducirse a 0), got {self.pct}"
            )
        ax, ay = self.anchor
        if not (0 <= ax <= 1 and 0 <= ay <= 1):
            raise EnhancementError(f"anchor debe estar en [0,1]x[0,1], got {self.anchor}")
        if not 0 <= self.curve <= 100:
            raise EnhancementError(f"curve debe estar en [0, 100], got {self.curve}")
        if self.easing not in ZOOM_EASINGS:
            raise EnhancementError(f"easing debe ser uno de {ZOOM_EASINGS}, got {self.easing!r}")
        if self.direction not in ZOOM_DIRECTIONS:
            raise EnhancementError(
                f"direction debe ser uno de {ZOOM_DIRECTIONS}, got {self.direction!r}"
            )
        if not 0 <= self.hold <= 0.9:
            raise EnhancementError(f"hold debe estar en [0, 0.9], got {self.hold}")
        if not 1.0 <= self.pulse_dur <= 30.0:
            raise EnhancementError(f"pulse_dur debe estar en [1, 30]s, got {self.pulse_dur}")
        if not 1 <= self.max_pulses <= 12:
            raise EnhancementError(f"max_pulses debe estar en [1, 12], got {self.max_pulses}")
        if self.ss not in (1, 2, 4):
            raise EnhancementError(f"ss debe ser 1, 2 o 4, got {self.ss}")
        if not 0 < self.crf <= 51:
            raise EnhancementError(f"crf debe estar en (0, 51], got {self.crf}")
        if self.start is not None and self.end is not None and self.end <= self.start:
            raise EnhancementError(f"end ({self.end}) debe ser > start ({self.start})")


def _phases(duration: float, opts: ZoomOptions) -> tuple[float, float, float]:
    """(in, hold, out) en segundos según direction y hold."""
    if opts.direction == "pulse":
        in_f = max((1 - opts.hold) / 2, 0.05)
        hold_f = opts.hold
        out_f = max(1 - in_f - hold_f, 0.001)
        return duration * in_f, duration * hold_f, duration * out_f
    return duration, 0.0, 0.001


def z_at(t: float, duration: float, opts: ZoomOptions) -> float:
    """Factor de escala en el instante t (espejo Python de la expr ffmpeg).

    z(t) = 1 + amp*pct/100 * E(clamp01(t/IN)) * E(clamp01((IN+HOLD+OUT-t)/OUT))
    amp = -1 para shrink, +1 para grow/pulse. E = ease().
    """
    opts.validate()
    dur = max(duration, 0.001)
    in_, hold, out = _phases(dur, opts)
    amp = -1.0 if opts.direction == "shrink" else 1.0
    t1 = in_ + hold
    p_in = min(max(t / in_, 0.0), 1.0)
    p_rev = min(max((t1 + out - t) / out, 0.0), 1.0)
    pulse = ease(p_in, opts.curve, opts.easing) * ease(p_rev, opts.curve, opts.easing)
    return 1.0 + amp * (opts.pct / 100.0) * pulse


def _clamp01(x: str) -> str:
    """clamp(x, 0, 1) en expr ffmpeg SIN operador resta entre bloques.

    Nota de contexto (medido en ffmpeg 7.1, build gyan.dev): el filtro crop
    moderno evalúa w/h UNA sola vez al configurar (con t=NaN -> este clamp
    devuelve 1 -> el zoom se congelaba en el pico) y solo x/y por frame;
    por eso el zoom real NO anima con crop y usamos zoompan, que evalúa
    z/x/y por frame de verdad. La construcción E_in*E_rev y el clamp
    (x+|x|)/2 siguen siendo necesarios por robustez de expresiones.
    """
    return f"((min({x},1)+abs(min({x},1)))/2)"


def _pulse_expr(opts: ZoomOptions, duration: float | None = None,
                moments: list[float] | None = None) -> str:
    """Expresión del pulso (0..1): E_in*E_rev por pulso, sumados si hay
    varios momentos. Es la pieza reutilizable por grow, pulse y shrink."""
    if moments:
        d = opts.pulse_dur
        in_ = max((1 - opts.hold) / 2 * d, 0.05)
        hold = opts.hold * d
        out = max(d - in_ - hold, 0.001)
        pulses = [_single_pulse_expr(m - in_, in_, hold, out, opts) for m in moments]
        return "+".join(f"({p})" for p in pulses)
    dur = max(duration or 0.001, 0.001)
    in_, hold, out = _phases(dur, opts)
    return _single_pulse_expr(0.0, in_, hold, out, opts)


def _z_expr(in_: float, hold: float, out: float, opts: ZoomOptions) -> str:
    """Expresión ffmpeg de z(t)."""
    amp = -1.0 if opts.direction == "shrink" else 1.0
    pulse = _single_pulse_expr(0.0, in_, hold, out, opts)
    # menús binario con átomo (1-x): el menos unario (1+-x) congela la eval
    # por-frame de zoompan (medido); 1-x y 1.25-0.25*x animan bien.
    op = "-" if amp < 0 else "+"
    return f"(1{op}{_fmt(opts.pct / 100)}*({pulse}))"


def _single_pulse_expr(t0: float, in_: float, hold: float, out: float, opts) -> str:
    """Pulso unitario: E(p_in) * E(p_rev) — sube con la curva y baja con la
    misma curva (ampliar y reducir). p_rev invierte el tiempo con
    time*(-1) (zoompan no expone 't'; usa 'time' = out_time)."""
    t1 = t0 + in_ + hold
    p_in = _clamp01(f"(time-{_fmt(t0)})/{_fmt(in_)}")
    p_rev = _clamp01(f"({_fmt(t1)}+{_fmt(out)}+time*(-1.000000))/{_fmt(out)}")
    e_in = _ease_expr(opts.curve, opts.easing).replace("P", f"({p_in})")
    e_rev = _ease_expr(opts.curve, opts.easing).replace("P", f"({p_rev})")
    return f"(({e_in})*({e_rev}))"


def _multi_z_expr(moments: list[float], opts: ZoomOptions) -> str:
    """z(t) para N pulsos: 1 + pct * (pulso_1 + ... + pulso_N).

    Los pulsos nunca se solapan (separación mínima garantizada por el
    criterio), así que la unión es una suma simple — sin max() ni restas
    (ver _clamp01).
    """
    return f"(1+{_fmt(opts.pct / 100)}*({_pulse_expr(opts, moments=moments)}))"


def detect_emphasis_moments(
    input: str | Path, max_pulses: int, min_gap: float = 6.0
) -> list[float]:
    """Momentos de énfasis: picos de la envolvente RMS de la voz.

    Criterio (elegido por el usuario, 2026-08-13): aplicar el efecto donde la
    voz enfatiza. Envolvente RMS 50ms/25ms suavizada (~150ms), picos locales
    > 1.2x la media, selección voraz con separación mínima, top max_pulses.
    Sin dependencia de opciones de zoom (compartido con video magnify).
    """
    tmp = video_mod.temp_wav()
    try:
        video_mod.extract_audio(input, tmp)
        data = audioio.load_audio(tmp)
    finally:
        tmp.unlink(missing_ok=True)
    x = data.samples.astype("float32")
    sr = audioio.INTERNAL_SAMPLE_RATE  # AudioData ya es 48 kHz mono
    win, hop = int(0.05 * sr), int(0.025 * sr)
    n = max((len(x) - win) // hop, 1)
    env = np.sqrt(
        np.array([np.mean(x[i * hop : i * hop + win] ** 2) for i in range(n)])
    )
    k = max(int(round(0.15 / 0.025)), 1)
    env = np.convolve(env, np.ones(k) / k, mode="same")
    # Regiones enfatizadas: envolvente > max(1.2x media, 0.35x pico).
    thr = max(float(np.mean(env) * 1.2), float(env.max()) * 0.35)
    mask = env > thr
    cands = []  # (energía, centroide de la región)
    i = 0
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j = i
        while j < n and mask[j]:
            j += 1
        seg = env[i:j]
        w = seg - thr
        t_c = (i + float(np.sum(w * np.arange(len(seg))) / max(np.sum(w), 1e-9))) * hop / sr
        cands.append((float(seg.max()), t_c))
        i = j
    cands.sort(reverse=True)
    chosen = []
    for _, t in cands:
        if all(abs(t - c) >= min_gap for c in chosen):
            chosen.append(t)
        if len(chosen) >= max_pulses:
            break
    chosen.sort()
    if not chosen:
        raise EnhancementError(
            "auto-emphasis: no se detectaron momentos de énfasis "
            "(¿el audio tiene voz? pruebe sin --auto-emphasis)"
        )
    return chosen


def find_emphasis_moments(
    input: str | Path, opts: ZoomOptions, min_gap: float = 6.0
) -> list[float]:
    """Momentos de énfasis para zoom (envoltura de detect_emphasis_moments)."""
    opts.validate()
    return detect_emphasis_moments(input, opts.max_pulses, min_gap)


def ease(p: float, curve: float = DEFAULT_CURVE, easing: str = "smooth") -> float:
    """Progreso con curva de easing: 0 -> 1. curve=0 => siempre lineal."""
    p = min(max(p, 0.0), 1.0)
    if easing == "linear":
        return p
    c = min(max(curve, 0.0), 100.0)
    if easing == "out":
        return 1 - (1 - p) ** (1 + c / 50)
    if easing == "in":
        return p ** (1 + c / 50)
    a = 1 + c / 25
    denom = p**a + (1 - p) ** a
    return 0.0 if denom == 0 else p**a / denom


def _fmt(x: float) -> str:
    return f"{x:.6f}"


def _ease_expr(curve: float, easing: str) -> str:
    """Expresión ffmpeg de la curva; usa la variable P (el progreso 0-1)."""
    if curve <= 0:
        return "P"
    if easing == "linear":
        return "P"
    if easing == "out":
        return f"1-pow(1-P,{_fmt(1 + curve / 50)})"
    if easing == "in":
        return f"pow(P,{_fmt(1 + curve / 50)})"
    a = _fmt(1 + curve / 25)
    return f"pow(P,{a})/(pow(P,{a})+pow(1-P,{a}))"


def _even(x: float) -> int:
    return int(x) // 2 * 2


def build_zoom_filter(
    width: int, height: int, duration: float, opts: ZoomOptions,
    moments: list[float] | None = None, fps: float = 30.0,
) -> str:
    """Cadena de filtros ffmpeg para el zoom Grow (ampliar y/o reducir).

    Motor: zoompan (d=1, canvas supersampled), porque el crop moderno de
    ffmpeg 7.1 congela w/h en la config (medido; ver _clamp01) y no puede
    animar el tamaño del window. zoompan evalúa z/x/y por frame con 'time'.

    Semántica del ancla (igual que Premiere): el punto (ax, ay) queda FIJO
    en pantalla mientras la imagen crece/encoge alrededor.

    - grow/pulse (z >= 1): zoompan directo sobre el canvas supersampled.
    - shrink (z <= 1): la imagen se pre-escala a su tamaño mínimo y se
      centra en un canvas negro (pad); zoompan con z' = z/zmin >= 1
      magnífica el canvas -> la imagen encoge de 1 a zmin sobre negro.
    """
    opts.validate()
    ax, ay = opts.anchor
    ss = opts.ss
    dur = max(duration, 0.001)
    pulse = _pulse_expr(opts, duration=dur, moments=moments)
    cw, ch = width * ss, height * ss
    out_fps = max(int(round(fps)), 1)

    if opts.direction == "shrink":
        zmin = 1.0 - opts.pct / 100.0
        iw_, ih_ = _even(cw * zmin), _even(ch * zmin)
        px, py = (cw - iw_) // 2, (ch - ih_) // 2
        # ancla efectiva del canvas: posición del punto (ax, ay) de la imagen
        ax_e = (px + ax * iw_) / cw
        ay_e = (py + ay * ih_) / ch
        # zpan = 1/zmin - (pct/zmin)*pulse (en [1, 1/zmin]). Forma VERIFICADA:
        # empezar con '1-' (p.ej. 1-0.2*x) congela la eval por-frame de
        # zoompan (medido); '1.25-0.25*x' anima bien.
        zpan = f"{_fmt(1 / zmin)}-{_fmt(opts.pct / 100 / zmin)}*({pulse})"
        return (
            f"fps={out_fps},"  # normaliza VFR -> CFR (timestamps del zoompan)
            f"scale={iw_}:{ih_}:flags=lanczos,"
            f"pad={cw}:{ch}:x={px}:y={py}:color=black,"
            f"zoompan=z='{zpan}':x='(iw-iw/zoom)*{_fmt(ax_e)}':"
            f"y='(ih-ih/zoom)*{_fmt(ay_e)}':d=1:fps={out_fps}:s={cw}x{ch},"
            f"scale={width}:{height}:flags=lanczos,"
            f"setsar=1,format=yuv420p"
        )

    # grow / pulse: z >= 1 siempre
    z = f"(1+{_fmt(opts.pct / 100)}*({pulse}))"
    return (
        f"fps={out_fps},"  # normaliza VFR -> CFR (timestamps del zoompan)
        f"scale={cw}:{ch}:flags=lanczos,"
        f"zoompan=z='{z}':x='(iw-iw/zoom)*{_fmt(ax)}':"
        f"y='(ih-ih/zoom)*{_fmt(ay)}':d=1:fps={out_fps}:s={cw}x{ch},"
        f"scale={width}:{height}:flags=lanczos,"
        f"setsar=1,format=yuv420p"
    )


def build_plan(input: str | Path, opts: ZoomOptions) -> str:
    """Plan legible para --dry-run (misma convención que enhance)."""
    opts.validate()
    inp = Path(input)
    probe = ve.probe_video(inp)
    seg_dur = _segment_duration(probe, opts)
    moments = None
    if opts.auto_emphasis:
        moments = find_emphasis_moments(inp, opts)
    vf = build_zoom_filter(probe["width"], probe["height"], seg_dur, opts, moments=moments, fps=probe["fps"])
    ax, ay = opts.anchor
    dir_label = {
        "grow": f"ampliar +{opts.pct:.1f}%",
        "shrink": f"reducir -{opts.pct:.1f}%",
        "pulse": f"pulso +{opts.pct:.1f}% (hold {opts.hold:.0%})",
    }[opts.direction]
    lines = [
        "VOXERA PLAN (video zoom)",
        f"  entrada : {inp} ({probe['width']}x{probe['height']} @{probe['fps']:.2f}fps, "
        f"{probe['duration_s']:.2f}s)",
        f"  salida  : 1080x1920-equivalente (misma resolución que entrada)",
        f"  zoom    : {dir_label}  anchor=({ax:.2f},{ay:.2f})  "
        f"curva={opts.curve:.0f}  easing={opts.easing}",
        f"  rango   : {opts.start if opts.start is not None else 0:.2f}s .. "
        f"{opts.end if opts.end is not None else probe['duration_s']:.2f}s "
        f"({seg_dur:.2f}s)",
        f"  encoder : libx264 crf {opts.crf} + aac {opts.audio_bitrate} "
        f"(audio original, sin masterizar)",
        f"  filtro  : {vf}",
    ]
    if moments:
        lines.insert(4, "  criterio: auto-emphasis (picos de energía de voz) en "
                        f"t = {', '.join(f'{m:.2f}s' for m in moments)}")
    return "\n".join(lines)


def _segment_duration(probe: dict, opts: ZoomOptions) -> float:
    start = opts.start if opts.start is not None else 0.0
    end = opts.end if opts.end is not None else probe["duration_s"]
    return max(end - start, 0.001)


def zoom_video(input: str | Path, output: str | Path, opts: ZoomOptions) -> Path:
    """Aplica el zoom Grow y devuelve la ruta de salida (verificada)."""
    opts.validate()
    inp = Path(input)
    out = Path(output)
    if not inp.exists():
        raise EnhancementError(f"input no existe: {inp}")
    out.parent.mkdir(parents=True, exist_ok=True)

    probe = ve.probe_video(inp)
    seg_dur = _segment_duration(probe, opts)
    moments = None
    if opts.auto_emphasis:
        moments = find_emphasis_moments(inp, opts)
    vf = build_zoom_filter(probe["width"], probe["height"], seg_dur, opts, moments=moments, fps=probe["fps"])
    if moments:
        print(
            "[zoom] momentos de énfasis (auto-emphasis): "
            + ", ".join(f"{m:.2f}s" for m in moments)
        )

    cmd = [video_mod._tool("ffmpeg"), "-y", "-v", "error"]
    cmd += ["-i", str(inp), "-vf", vf, "-c:v", "libx264", "-crf", str(opts.crf),
            "-pix_fmt", "yuv420p"]
    if opts.start is not None:
        cmd += ["-ss", f"{opts.start:.6f}"]  # después de -i: decode-seek exacto
    if opts.end is not None:
        cmd += ["-to", f"{opts.end:.6f}"]
    if probe["has_audio"]:
        cmd += ["-c:a", "aac", "-b:a", opts.audio_bitrate, "-shortest"]
    else:
        cmd += ["-an"]
    cmd += [str(out)]

    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=7200)
    except subprocess.CalledProcessError as exc:
        raise EnhancementError(
            f"ffmpeg falló: {exc.stderr.decode(errors='replace')[-800:]}"
        ) from exc

    # Verificación determinista (misma disciplina que enhance): streams, tamaño,
    # duración esperada del segmento.
    oprobe = ve.probe_video(out)
    if oprobe["width"] != probe["width"] or oprobe["height"] != probe["height"]:
        raise EnhancementError(
            f"salida con resolución inesperada: {oprobe['width']}x{oprobe['height']}"
        )
    expected = seg_dur
    if abs(oprobe["duration_s"] - expected) > 0.25:
        raise EnhancementError(
            f"duración inesperada: {oprobe['duration_s']:.2f}s (esperada ~{expected:.2f}s)"
        )
    return out
