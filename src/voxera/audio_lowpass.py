"""``voxera audio lowpass`` — efecto "Pase Bajo" de Premiere (sin Premiere).

Replicación programática del truco del tutorial de @serri.mp4 (Premiere):
un filtro paso bajo (low-pass) sobre la música, con transición suave en los
cortes para que el cambio no sea brusco.

Medición del tutorial (2026-08-13, espectro del TikTok de @serri.mp4,
extraído vía CDP): el creador corta la música en los dos lados del momento
(ponerse/quitarse los auriculares), arrastra el efecto "Pase Bajo" al clip y
"ajusta el valor a 800 hercios" (cutoff = 800 Hz). Después pone una
"transición predeterminada" (la de Premiere: Constant Power, 1 s por
defecto) en cada corte — el audio filtrado en el tutorial muestra rampas de
~0.5-1.5 s (medidas por envolvente de la banda 4-10 kHz con mediana 1 s para
quitar los sibilantes de la voz). Pendiente medida del filtro ~12 dB/oct
(2º orden).

Implementación: 100 % numpy/scipy (sin Premiere, sin keyframes a mano).
  wet = butter(order, cutoff) aplicado con sosfilt a todo el clip
  out = dry + (wet - dry) * env   (crossfade seco/húmedo)

env es la envolvente 0..1 de la región con rampas S SOLO en los bordes de
región explícitos (los cortes del tutorial):
  - sin --start/--end : todo el clip filtrado, rampa en ambos bordes
    (la "transición predeterminada" del tutorial, aplicada a los cortes)
  - --start y --end   : "blip" — rampa de entrada, mantener, rampa de salida
    (el caso del tutorial: el segmento entre los dos cortes)
  - solo --start      : "on" — entra el filtro y se queda hasta el final
  - solo --end        : "off" — el clip empieza filtrado y se suelta al final

Curva de las rampas (misma convención que ``voxera video zoom``, el rango
60-65 del creador):
  - smooth (default): S-curva simétrica p^a/(p^a+(1-p)^a), a = 1+curve/25
  - out: arranca rápido y decelera: 1-(1-p)^(1+curve/50)
  - in : arranca lento y acelera: p^(1+curve/50)
  - linear: sin curva
curve=0 => siempre lineal, en cualquier easing.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt

from voxera import audioio
from voxera.errors import EnhancementError

DEFAULT_CUTOFF = 800.0    # "ajustaremos el valor a 800 hercios" (el tutorial)
DEFAULT_TRANSITION = 1.0  # "transición predeterminada" de Premiere (Constant Power, 1 s)
DEFAULT_CURVE = 62.0      # curva S del creador (60-65), misma que voxera video zoom
DEFAULT_ORDER = 2         # pendiente ~12 dB/oct (medida en el tutorial)
LP_EASINGS = ("smooth", "out", "in", "linear")
LP_ORDERS = (1, 2, 4)


@dataclass(frozen=True)
class LowPassOptions:
    """Parámetros del efecto Pase Bajo. Un solo default sensato; el resto escapes.

    Medición del tutorial de @serri.mp4 (2026-08-13): cutoff 800 Hz declarado
    ("ajustaremos el valor a 800 hercios"); transición predeterminada de
    Premiere (Constant Power, 1 s) en los cortes; pendiente medida ~12 dB/oct
    (2º orden). La rampa medida en el audio real es de ~0.5-1.5 s.
    """

    cutoff: float = DEFAULT_CUTOFF
    transition: float = DEFAULT_TRANSITION
    curve: float = DEFAULT_CURVE
    easing: str = "smooth"
    order: int = DEFAULT_ORDER
    start: float | None = None
    end: float | None = None

    def validate(self) -> None:
        if not 20 <= self.cutoff <= 20000:
            raise EnhancementError(f"cutoff debe estar en [20, 20000] Hz, got {self.cutoff}")
        if not 0 <= self.transition <= 60:
            raise EnhancementError(f"transition debe estar en [0, 60] s, got {self.transition}")
        if not 0 <= self.curve <= 100:
            raise EnhancementError(f"curve debe estar en [0, 100], got {self.curve}")
        if self.easing not in LP_EASINGS:
            raise EnhancementError(f"easing debe ser uno de {LP_EASINGS}, got {self.easing!r}")
        if self.order not in LP_ORDERS:
            raise EnhancementError(f"order debe ser uno de {LP_ORDERS}, got {self.order}")
        if self.start is not None and self.start < 0:
            raise EnhancementError(f"start debe ser >= 0, got {self.start}")
        if self.end is not None and self.end <= 0:
            raise EnhancementError(f"end debe ser > 0, got {self.end}")
        if self.start is not None and self.end is not None and self.end <= self.start:
            raise EnhancementError(f"end ({self.end}) debe ser > start ({self.start})")


def ease(p, curve: float = DEFAULT_CURVE, easing: str = "smooth"):
    """Progreso con curva de easing: 0 -> 1. curve=0 => siempre lineal.

    Misma parametrización que ``voxera video zoom`` (convención del repo):
    a = 1 + curve/25 en la S-curva simétrica; 60-65 = el rango del creador.
    Vectorizada: acepta escalar o array (float32 in -> float32 out);
    devuelve float para entrada escalar.
    """
    pv = np.asarray(p)
    scalar = pv.ndim == 0
    pv = np.clip(pv, 0.0, 1.0)
    if easing == "linear":
        out = pv
    else:
        c = min(max(curve, 0.0), 100.0)
        if easing == "out":
            out = 1 - (1 - pv) ** (1 + c / 50)
        elif easing == "in":
            out = pv ** (1 + c / 50)
        else:
            a = 1 + c / 25
            denom = pv**a + (1 - pv) ** a
            out = pv**a / denom
    return out.item() if scalar else out


def _mode(opts: LowPassOptions) -> str:
    """Modo derivado de qué bordes de región se han dado."""
    if opts.start is not None and opts.end is not None:
        return "blip"   # el caso del tutorial: segmento entre los dos cortes
    if opts.start is not None:
        return "on"
    if opts.end is not None:
        return "off"
    return "full"


def build_envelope(n: int, sample_rate: int, opts: LowPassOptions) -> np.ndarray:
    """Envolvente wet 0..1 (float32, longitud ``n``).

    Región [a, b] con rampas S de ``transition`` s SOLO en los bordes de
    región explícitos (--start/--end): en modo "on" (solo --start) el filtro
    se queda hasta el final; en "off" (solo --end) empieza ya filtrado desde
    el inicio; sin bordes (full) rampa en ambos bordes del archivo. Fuera de
    la región la salida es el audio seco (bit-exacto). Si la región es más
    corta que 2*transition las rampas se cruzan (pico < 1, sin sobresaltos).

    Vectorizada (sin loops por muestra): ~n float32 arrays, instantánea.
    """
    opts.validate()
    dur = n / sample_rate
    a = opts.start if opts.start is not None else 0.0
    b = opts.end if opts.end is not None else dur
    # rampa de entrada solo si el borde de región es explícito o el modo es
    # "full" (el clip ya cortado del tutorial: transición en ambos cortes);
    # en modo "off" (solo --end) el clip empieza filtrado, sin rampa en 0.
    ramp_in_active = opts.start is not None or opts.end is None
    ramp_out_active = opts.end is not None or opts.start is None

    t = np.arange(n, dtype=np.float32) / sample_rate
    env = np.ones(n, dtype=np.float32)
    if opts.transition > 0.0:
        tau = float(opts.transition)
        if ramp_in_active:
            p_in = np.clip((t - a) / tau, 0.0, 1.0)
            env = np.minimum(env, ease(p_in, opts.curve, opts.easing))
        if ramp_out_active:
            p_out = np.clip((b - t) / tau, 0.0, 1.0)
            env = np.minimum(env, ease(p_out, opts.curve, opts.easing))
    env[t < a] = 0.0
    env[t > b] = 0.0
    return env


def apply_lowpass(samples: np.ndarray, sample_rate: int, opts: LowPassOptions) -> np.ndarray:
    """Aplica el Pase Bajo: crossfade seco/húmedo con la envolvente.

    out = dry + (wet - dry) * env — fuera de la región la salida es
    bit-exacta al original; dentro, el filtro Butterworth ``order`` con el
    cutoff del tutorial.
    """
    opts.validate()
    if opts.cutoff >= sample_rate / 2:
        raise EnhancementError(
            f"cutoff ({opts.cutoff} Hz) debe ser < nyquist ({sample_rate / 2} Hz)"
        )
    dry = np.asarray(samples, dtype=np.float32).reshape(-1)
    sos = butter(opts.order, opts.cutoff, btype="lowpass", fs=sample_rate, output="sos")
    wet = np.asarray(sosfilt(sos, dry), dtype=np.float32)
    env = build_envelope(len(dry), sample_rate, opts)
    return dry + (wet - dry) * env


def _check_region(duration: float, opts: LowPassOptions) -> None:
    """Rechaza regiones fuera del archivo (un no-op silencioso confunde)."""
    if opts.start is not None and opts.start >= duration:
        raise EnhancementError(
            f"start ({opts.start}) fuera del archivo ({duration:.2f} s)"
        )
    if opts.end is not None and opts.end > duration:
        raise EnhancementError(
            f"end ({opts.end}) fuera del archivo ({duration:.2f} s)"
        )


def build_plan(input: str | Path, opts: LowPassOptions) -> str:
    """Plan legible para --dry-run (misma convención que enhance/video zoom)."""
    opts.validate()
    inp = Path(input)
    data = audioio.load_audio(inp)
    dur = data.duration_s
    _check_region(dur, opts)
    sr = data.source_sample_rate
    a = opts.start if opts.start is not None else 0.0
    b = opts.end if opts.end is not None else dur
    mode = _mode(opts)
    mode_label = {
        "blip": "entra al inicio, se mantiene, sale al final",
        "on": "entra al inicio y se queda",
        "off": "empieza filtrado y sale al final",
        "full": "todo el clip, rampa en ambos bordes",
    }[mode]
    slope = {1: "6 dB/oct", 2: "12 dB/oct", 4: "24 dB/oct"}[opts.order]
    lines = [
        "VOXERA PLAN (audio lowpass)",
        f"  entrada : {inp} ({sr} Hz, {dur:.2f} s)",
        f"  filtro  : butter {opts.order}º ({slope}) lowpass @ {opts.cutoff:g} Hz",
        f"  región  : {a:.2f}s .. {b:.2f}s ({mode}: {mode_label})",
        f"  rampa   : {opts.transition:g} s por borde (curva {opts.curve:.0f}, "
        f"easing {opts.easing})",
        f"  salida  : wav 48 kHz 24-bit (misma duración)",
    ]
    return "\n".join(lines)


def lowpass_file(input: str | Path, output: str | Path, opts: LowPassOptions) -> Path:
    """Aplica el efecto Pase Bajo a un archivo de audio y escribe la salida."""
    opts.validate()
    data = audioio.load_audio(input)
    _check_region(data.duration_s, opts)
    out = apply_lowpass(data.samples, audioio.INTERNAL_SAMPLE_RATE, opts)
    return audioio.write_wav(output, out, sample_rate=audioio.INTERNAL_SAMPLE_RATE)
