"""``voxera audio tonal`` — la música que le dice a la gente cómo sentirse.

Un corte suena mejor cuando la armonía empuja la emoción. Este módulo
sintetiza elementos tonales EMOTIVALES y los mezcla sobre audio existente:
  - ``transition`` : cambio de emoción armónica (acorde A → acorde B con
    movimiento mínimo de voces y glide logarítmico, no un crossfade crudo)
  - ``riser``      : tensión ascendente que termina exactamente en el hit
    (corte/impacto del vídeo), con cola de release que resuelve después
  - ``melody``     : melodía generada bajo la voz, pregunta + respuesta,
    en la escala y el contorno del mood

La tabla ``MOODS`` es el corazón: 8 emociones (hope, tension, melancholy,
triumph, wonder, calm, mystery, urgency) cada una con su modo, raíz, registro,
timbre, detune, vibrato y contorno melódico — "tell the people how to feel".
Cada mood lleva una frase que explica QUÉ le dice al oyente (la razón musical,
no la etiqueta).

Implementación: 100 % numpy/scipy (butter/sosfilt), determinista — RNG
sembrado (``np.random.default_rng(seed)``), sin tiempo, sin global. Misma
convención de región que ``voxera audio lowpass``: fuera de la región
mezclada la salida es BIT-EXACTA al input (``mix_element`` copia el seco y
solo toca [i0, i0+n_elem); clip a [-1, 1] solo dentro de la región).

Síntesis: osciladores de fase acumulada (float64 interno, salida float32);
triangle exacto band-limited via arcsin(sin); saw/square naïvos con
anti-alias lowpass 7 kHz; campana con parciales inarmónicos (2.76x, 5.4x).
Curvas S reutilizadas de ``audio_lowpass.ease`` (convención curve 0-100,
easing smooth/out/in/linear).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt

from voxera import audioio
from voxera.audio_lowpass import ease
from voxera.errors import EnhancementError

DEFAULT_CURVE = 62.0     # curva S del repo (misma que lowpass / video zoom)
DEFAULT_MIX_FADE = 0.3   # s, rampas de duck en mix_element
TONAL_EASINGS = ("smooth", "out", "in", "linear")
TONAL_WAVES = ("sine", "triangle", "saw", "square", "bell")
_NAIVE_AA_HZ = 7000.0    # anti-alias barato para saw/square naïvos

# ---------------------------------------------------------------------------
# Teoría musical
# ---------------------------------------------------------------------------

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
SCALES = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "minor": (0, 2, 3, 5, 7, 8, 10),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "lydian": (0, 2, 4, 6, 7, 9, 11),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10),
    "harmonic_minor": (0, 2, 3, 5, 7, 8, 11),
    "pentatonic_major": (0, 2, 4, 7, 9),
    "pentatonic_minor": (0, 3, 5, 7, 10),
}


def note_to_midi(name: str, octave: int = 4) -> int:
    """Nombre de nota ("C", "C#", ...) + octava → número MIDI (C4=60, A4=69).

    Solo sostenidos ("C#", no "Db"); ``name`` debe estar en NOTE_NAMES y
    0 <= octave <= 8, si no EnhancementError.
    """
    if name not in NOTE_NAMES:
        raise EnhancementError(f"nota {name!r} no válida (usa sostenidos: {NOTE_NAMES})")
    if not 0 <= octave <= 8:
        raise EnhancementError(f"octave debe estar en [0, 8], got {octave}")
    return NOTE_NAMES.index(name) + 12 * (octave + 1)


def midi_to_freq(midi: float) -> float:
    """MIDI → Hz (A4 = 440 Hz, temperamento igual)."""
    return 440.0 * 2.0 ** ((midi - 69) / 12.0)


def midi_to_name(m: int) -> str:
    """MIDI → "C#4" (nota + octava; la octava MIDI empieza en C)."""
    return f"{NOTE_NAMES[int(m) % 12]}{int(m) // 12 - 1}"


def scale_midi(root_midi: int, mode: str, n_octaves: int = 2) -> np.ndarray:
    """Grados del modo ascendentes desde root, tónica en cada octava (dtype int).

    Longitud = n_octaves·len(intervalos) + 1 (la última es la tónica superior).
    """
    if mode not in SCALES:
        raise EnhancementError(f"mode debe ser uno de {tuple(SCALES)}, got {mode!r}")
    intervals = SCALES[mode]
    out = [
        root_midi + 12 * oct_i + iv
        for oct_i in range(n_octaves)
        for iv in intervals
    ]
    out.append(root_midi + 12 * n_octaves)
    return np.asarray(out, dtype=int)


def triad_midi(root_midi: int, mode: str) -> tuple[int, int, int]:
    """Triada (grados 1-3-5) de la escala: índices 0, 2, 4 de scale_midi.

    Para las pentatónicas son 0, 2, 4 también — su "triada equivalente"
    (p.ej. pentatónica menor: 0-5-10, cuartal pero perfectamente usable).
    """
    notes = scale_midi(root_midi, mode, 1)
    if len(notes) < 5:
        raise EnhancementError(f"la escala {mode!r} es demasiado corta para una triada")
    return int(notes[0]), int(notes[2]), int(notes[4])


def best_voice_leading(a: tuple[int, ...], b: tuple[int, ...]) -> tuple[int, ...]:
    """Revozado de ``b`` que suena lo más cerca posible de ``a``.

    movimiento mínimo — la diferencia entre un crossfade crudo y una
    transición musical: busca entre las rotaciones de ``b`` y los
    desplazamientos de octava de cada nota (b_i ± 12) la asignación que
    minimiza la suma de |a_i - b_i| en semitonos; empate → menor salto máximo.
    """
    best_key: tuple[int, int] | None = None
    best: tuple[int, ...] = tuple(b)
    for rot in range(len(b)):
        rotated = b[rot:] + b[:rot]
        voiced: list[int] = []
        total = 0
        for b_i, a_i in zip(rotated, a):
            # octava (−12/0/+12) que minimiza la distancia a la nota emparejada
            oct_shift = min((-12, 0, 12), key=lambda o: abs(b_i + o - a_i))
            voiced.append(b_i + oct_shift)
            total += abs(b_i + oct_shift - a_i)
        max_jump = max(abs(v - a_i) for v, a_i in zip(voiced, a))
        key = (total, max_jump)
        if best_key is None or key < best_key:
            best_key = key
            best = tuple(voiced)
    return best


# ---------------------------------------------------------------------------
# Tabla de emociones — "tell the people how to feel"
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MoodSpec:
    """Una emoción traducida a decisiones musicales concretas.

    ``doc`` es la frase que le dice al oyente QUÉ siente (la razón musical,
    no la etiqueta). ``contour`` es la forma melódica; ``density`` (0-1) la
    densidad rítmica de la melodía generada.
    """

    mode: str          # escala
    root: str          # nota raíz por defecto (sostenidos)
    octave: int        # octava de registro
    bpm: float
    contour: str       # "arch" | "rise" | "fall" | "wave"
    wave: str          # "sine" | "triangle" | "saw" | "square" | "bell"
    detune_cents: float
    vibrato_hz: float
    vibrato_depth: float  # relativa a f0 (0.006 ≈ ±10 cents)
    attack: float      # s
    release: float     # s
    density: float     # 0-1: densidad rítmica de la melodía
    doc: str           # una frase es-ES: qué le dice al oyente


MOODS: dict[str, MoodSpec] = {
    "hope": MoodSpec(
        mode="lydian", root="C", octave=5, bpm=90.0, contour="rise", wave="triangle",
        detune_cents=6.0, vibrato_hz=5.5, vibrato_depth=0.006,
        attack=0.02, release=0.35, density=0.45,
        doc="asciende y abre: el #4 del lidio es el color de las promesas",
    ),
    "tension": MoodSpec(
        mode="phrygian", root="E", octave=3, bpm=120.0, contour="wave", wave="saw",
        detune_cents=12.0, vibrato_hz=6.5, vibrato_depth=0.010,
        attack=0.005, release=0.12, density=0.8,
        doc="semitonos bajos y ritmo apretado: algo va a pasar",
    ),
    "melancholy": MoodSpec(
        mode="minor", root="A", octave=4, bpm=60.0, contour="fall", wave="sine",
        detune_cents=4.0, vibrato_hz=4.5, vibrato_depth=0.008,
        attack=0.08, release=0.8, density=0.25,
        doc="desciende lento, sin prisa: lo que ya no vuelve",
    ),
    "triumph": MoodSpec(
        mode="major", root="C", octave=4, bpm=110.0, contour="rise", wave="square",
        detune_cents=8.0, vibrato_hz=5.0, vibrato_depth=0.006,
        attack=0.004, release=0.2, density=0.7,
        doc="arpegio ascendente de tónica a octava: meta alcanzada",
    ),
    "wonder": MoodSpec(
        mode="pentatonic_major", root="G", octave=5, bpm=75.0, contour="arch", wave="bell",
        detune_cents=3.0, vibrato_hz=5.0, vibrato_depth=0.003,
        attack=0.002, release=1.2, density=0.2,
        doc="campanas pentatónicas escasas: no hay notas malas, solo asombro",
    ),
    "calm": MoodSpec(
        mode="dorian", root="D", octave=4, bpm=70.0, contour="arch", wave="sine",
        detune_cents=5.0, vibrato_hz=4.0, vibrato_depth=0.004,
        attack=0.15, release=1.0, density=0.2,
        doc="dorio (menor con 6ª mayor): serenidad con movimiento suave",
    ),
    "mystery": MoodSpec(
        mode="harmonic_minor", root="A", octave=4, bpm=80.0, contour="wave", wave="sine",
        detune_cents=14.0, vibrato_hz=5.5, vibrato_depth=0.009,
        attack=0.05, release=0.5, density=0.35,
        doc="la 7ª mayor sobre acorde menor y el detune ancho: la puerta entreabierta",
    ),
    "urgency": MoodSpec(
        mode="pentatonic_minor", root="E", octave=4, bpm=140.0, contour="rise", wave="saw",
        detune_cents=10.0, vibrato_hz=6.0, vibrato_depth=0.007,
        attack=0.003, release=0.08, density=0.9,
        doc="pentatónica menor densa y staccato: corre",
    ),
}

MOOD_NAMES = tuple(MOODS)  # para choices del CLI


# ---------------------------------------------------------------------------
# Síntesis (privada)
# ---------------------------------------------------------------------------


def _lowpass(x: np.ndarray, sr: int, hz: float) -> np.ndarray:
    """Butterworth 2º orden (sos) — anti-alias barato para saw/square naïvos."""
    if hz >= sr / 2:
        raise EnhancementError(f"_lowpass: hz ({hz} Hz) debe ser < nyquist ({sr / 2} Hz)")
    sos = butter(2, hz, btype="lowpass", fs=sr, output="sos")
    return np.asarray(sosfilt(sos, x), dtype=np.float32)


def _bell(freq_t: np.ndarray, sr: int, t: np.ndarray) -> np.ndarray:
    """Campana: parciales inarmónicos (2.76x, 5.4x) con decaimientos propios.

    ``t`` es el tiempo desde el inicio de la nota (el decay ES la envolvente).
    """
    f = np.asarray(freq_t, dtype=np.float64).reshape(-1)
    phase = 2.0 * np.pi * np.cumsum(f) / float(sr)
    t64 = np.asarray(t, dtype=np.float64)
    x = (
        np.sin(phase) * np.exp(-2.5 * t64)
        + 0.5 * np.sin(2.76 * phase) * np.exp(-5.0 * t64)
        + 0.25 * np.sin(5.4 * phase) * np.exp(-9.0 * t64)
    )
    return np.asarray(x, dtype=np.float32)


def _osc(wave: str, freq_t: np.ndarray, sr: int, t: np.ndarray | None = None) -> np.ndarray:
    """Oscilador de fase acumulada (float64 interno, salida float32).

    - sine    : sin(φ)
    - triangle: (2/π)·arcsin(sin(φ)) — band-limited exacto
    - saw     : 2·frac(φ/2π)−1 + lowpass 7 kHz (naive anti-alias)
    - square  : sign(sin(φ)) + lowpass 7 kHz
    - bell    : delega en ``_bell`` (requiere ``t``)

    Si ``freq_t`` es escalar-constante se acepta y se rellena a len(t).
    """
    if wave not in TONAL_WAVES:
        raise EnhancementError(f"wave debe ser uno de {TONAL_WAVES}, got {wave!r}")
    f = np.asarray(freq_t, dtype=np.float64).reshape(-1)
    if f.size == 1 and t is not None and len(t) > 1:
        f = np.full(len(t), float(f[0]), dtype=np.float64)
    if wave == "bell":
        if t is None:
            raise EnhancementError("la onda 'bell' requiere t (tiempo desde el inicio de la nota)")
        return _bell(f, sr, t)
    phase = 2.0 * np.pi * np.cumsum(f) / float(sr)
    if wave == "sine":
        x = np.sin(phase)
    elif wave == "triangle":
        x = (2.0 / np.pi) * np.arcsin(np.sin(phase))
    elif wave == "saw":
        x = 2.0 * np.mod(phase / (2.0 * np.pi), 1.0) - 1.0
        x = _lowpass(x, sr, _NAIVE_AA_HZ)
    else:  # square
        x = np.sign(np.sin(phase))
        x = _lowpass(x, sr, _NAIVE_AA_HZ)
    return np.asarray(x, dtype=np.float32)


def _adsr(n: int, sr: int, attack: float, release: float) -> np.ndarray:
    """Envolvente 0→1 (ease smooth 62) — sustain — 1→0; clamp attack+release ≤ n."""
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    a_n = min(int(round(attack * sr)), n)
    r_n = min(int(round(release * sr)), n - a_n)
    env = np.ones(n, dtype=np.float64)
    if a_n > 0:
        env[:a_n] = ease(np.arange(a_n, dtype=np.float64) / a_n, 62.0, "smooth")
    if r_n > 0:
        p = np.arange(r_n, dtype=np.float64) / r_n
        env[n - r_n:] = ease(1.0 - p, 62.0, "smooth")
    return np.clip(env, 0.0, 1.0).astype(np.float32)


def _voice(
    wave: str,
    f0: float | np.ndarray,
    dur_s: float,
    sr: int,
    mood: MoodSpec,
    vib_progress: bool = False,
) -> np.ndarray:
    """Una voz con vibrato, detune chorus y adsr del mood (float32).

    ``f0`` puede ser un array (glide). Con ``vib_progress`` la profundidad
    del vibrato CRECE con el progreso de la nota (0 → 0.02) — la convención
    del riser glide (empieza limpia, acaba nerviosa).
    """
    n = int(round(dur_s * sr))
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    t = np.arange(n, dtype=np.float64) / sr
    f0a = np.asarray(f0, dtype=np.float64).reshape(-1)
    if f0a.size == 1:
        f0a = np.full(n, float(f0a[0]), dtype=np.float64)
    if vib_progress:
        depth_t = (t / dur_s) * 0.02
    else:
        depth_t = mood.vibrato_depth
    freq_t = f0a * (1.0 + depth_t * np.sin(2.0 * np.pi * mood.vibrato_hz * t))
    if mood.detune_cents > 0.0:
        ratio = 2.0 ** (mood.detune_cents / 1200.0)
        x = 0.5 * (
            _osc(wave, freq_t / ratio, sr, t).astype(np.float64)
            + _osc(wave, freq_t * ratio, sr, t).astype(np.float64)
        )
    else:
        x = _osc(wave, freq_t, sr, t).astype(np.float64)
    clamp45 = 0.45 * dur_s
    if wave == "bell":
        # la campana trae su propio decay: sin attack, release corto
        env = _adsr(n, sr, 0.0, min(mood.release, clamp45))
    else:
        env = _adsr(n, sr, min(mood.attack, clamp45), min(mood.release, clamp45))
    return np.asarray(x * env, dtype=np.float32)


def _normalize(x: np.ndarray, peak: float = 0.5) -> np.ndarray:
    """Escala el elemento a un pico fijo (guard max==0 → zeros)."""
    arr = np.asarray(x, dtype=np.float64)
    m = float(np.max(np.abs(arr))) if arr.size else 0.0
    if m == 0.0:
        return np.zeros(arr.size, dtype=np.float32)
    return np.asarray(arr / m * peak, dtype=np.float32)


# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TransitionOptions:
    """Transición de emoción armónica: acorde A → acorde B con movimiento mínimo.

    ``from_key``/``to_key`` sobreescriben la raíz de cada mood (default: mood.root).
    """

    from_mood: str = "calm"
    to_mood: str = "hope"
    from_key: str | None = None
    to_key: str | None = None
    at: float = 0.0
    dur: float = 3.0
    gain_db: float = -18.0
    curve: float = DEFAULT_CURVE
    easing: str = "smooth"

    def validate(self) -> None:
        if self.from_mood not in MOODS:
            raise EnhancementError(f"from_mood debe ser uno de {MOOD_NAMES}, got {self.from_mood!r}")
        if self.to_mood not in MOODS:
            raise EnhancementError(f"to_mood debe ser uno de {MOOD_NAMES}, got {self.to_mood!r}")
        if self.from_key is not None:
            note_to_midi(self.from_key, 4)  # valida el nombre de nota
        if self.to_key is not None:
            note_to_midi(self.to_key, 4)
        if not 0 <= self.at:
            raise EnhancementError(f"at debe ser >= 0, got {self.at}")
        if not 0.5 <= self.dur <= 30:
            raise EnhancementError(f"dur debe estar en [0.5, 30] s, got {self.dur}")
        if not -60 <= self.gain_db <= 0:
            raise EnhancementError(f"gain_db debe estar en [-60, 0], got {self.gain_db}")
        if not 0 <= self.curve <= 100:
            raise EnhancementError(f"curve debe estar en [0, 100], got {self.curve}")
        if self.easing not in TONAL_EASINGS:
            raise EnhancementError(f"easing debe ser uno de {TONAL_EASINGS}, got {self.easing!r}")


@dataclass(frozen=True)
class RiserOptions:
    """Riser tonal: acelera y crece hasta terminar EXACTO en el hit.

    ``hit=None`` lo resuelve ``_resolve_riser_opts`` al final del archivo
    (el elemento, incluida la cola, termina en EOF). ``tail`` es el release
    que resuelve DESPUÉS del hit.
    """

    mood: str = "tension"
    key: str | None = None
    hit: float | None = None
    dur: float = 2.0
    style: str = "notes"  # "notes" | "glide"
    gain_db: float = -16.0
    tail: float = 0.3

    def validate(self) -> None:
        if self.mood not in MOODS:
            raise EnhancementError(f"mood debe ser uno de {MOOD_NAMES}, got {self.mood!r}")
        if self.key is not None:
            note_to_midi(self.key, 4)
        if self.hit is not None and self.hit < self.dur:
            raise EnhancementError(f"hit debe ser >= dur ({self.dur}), got {self.hit}")
        if not 0.5 <= self.dur <= 15:
            raise EnhancementError(f"dur debe estar en [0.5, 15] s, got {self.dur}")
        if self.style not in ("notes", "glide"):
            raise EnhancementError(f"style debe ser 'notes' o 'glide', got {self.style!r}")
        if not -60 <= self.gain_db <= 0:
            raise EnhancementError(f"gain_db debe estar en [-60, 0], got {self.gain_db}")
        if not 0 <= self.tail <= 5:
            raise EnhancementError(f"tail debe estar en [0, 5] s, got {self.tail}")


@dataclass(frozen=True)
class MelodyOptions:
    """Melodía generada bajo la voz: pregunta + respuesta, rng sembrado.

    ``bpm=None`` usa el bpm del mood; ``duck_db > 0`` baja la voz bajo la melodía.
    """

    mood: str = "wonder"
    key: str | None = None
    start: float = 0.0
    bars: int = 4
    bpm: float | None = None
    seed: int = 0
    gain_db: float = -20.0
    duck_db: float = 0.0

    def validate(self) -> None:
        if self.mood not in MOODS:
            raise EnhancementError(f"mood debe ser uno de {MOOD_NAMES}, got {self.mood!r}")
        if self.key is not None:
            note_to_midi(self.key, 4)
        if not 0 <= self.start:
            raise EnhancementError(f"start debe ser >= 0, got {self.start}")
        if not 1 <= self.bars <= 64:
            raise EnhancementError(f"bars debe estar en [1, 64], got {self.bars}")
        if self.bpm is not None and not 30 <= self.bpm <= 300:
            raise EnhancementError(f"bpm debe estar en [30, 300] o ser None, got {self.bpm}")
        if not -60 <= self.gain_db <= 0:
            raise EnhancementError(f"gain_db debe estar en [-60, 0], got {self.gain_db}")
        if not 0 <= self.duck_db <= 24:
            raise EnhancementError(f"duck_db debe estar en [0, 24], got {self.duck_db}")


# ---------------------------------------------------------------------------
# Render (devuelven SOLO el elemento, sin mezclar)
# ---------------------------------------------------------------------------


def _transition_chords(
    opts: TransitionOptions,
) -> tuple[MoodSpec, MoodSpec, int, int, tuple[int, int, int], tuple[int, ...]]:
    """Acordes efectivos de la transición (keys override aplicadas) + voz líder."""
    mood_a = MOODS[opts.from_mood]
    mood_b = MOODS[opts.to_mood]
    key_a = opts.from_key if opts.from_key is not None else mood_a.root
    key_b = opts.to_key if opts.to_key is not None else mood_b.root
    root_a = note_to_midi(key_a, mood_a.octave)
    root_b = note_to_midi(key_b, mood_b.octave)
    chord_a = triad_midi(root_a, mood_a.mode)
    chord_b = triad_midi(root_b, mood_b.mode)
    b_voiced = best_voice_leading(chord_a, chord_b)
    return mood_a, mood_b, root_a, root_b, chord_a, b_voiced


def render_transition(sr: int, opts: TransitionOptions) -> np.ndarray:
    """Sintetiza el pad de transición A→B (solo el elemento, float32).

    Cada voz hace un glide LOGarítmico de a_i a b_i (movimiento melódico,
    no crossfade de acordes); timbre blend 0.5·triangle + 0.5·sine con
    detune y vibrato del mood destino; bajo pivote (tónica de B una octava
    abajo) que entra en la segunda mitad. Normalizado a pico 0.5.
    """
    opts.validate()
    mood_a, mood_b, _root_a, root_b, chord_a, b_voiced = _transition_chords(opts)
    n = int(round(opts.dur * sr))
    t = np.arange(n, dtype=np.float64) / sr
    p = np.asarray(ease(t / opts.dur, opts.curve, opts.easing), dtype=np.float64)
    out = np.zeros(n, dtype=np.float64)
    for a_i, b_i, amp in zip(chord_a, b_voiced, (1.0, 0.8, 0.6)):  # la raíz manda
        fa = midi_to_freq(float(a_i))
        fb = midi_to_freq(float(b_i))
        f = fa * (fb / fa) ** p  # glide logarítmico
        if mood_b.vibrato_depth > 0.0:
            f = f * (1.0 + mood_b.vibrato_depth * np.sin(2.0 * np.pi * mood_b.vibrato_hz * t))
        ratio = 2.0 ** (mood_b.detune_cents / 1200.0)
        if mood_b.detune_cents > 0.0:
            x = 0.25 * (
                _osc("triangle", f * ratio, sr, t).astype(np.float64)
                + _osc("triangle", f / ratio, sr, t).astype(np.float64)
                + _osc("sine", f * ratio, sr, t).astype(np.float64)
                + _osc("sine", f / ratio, sr, t).astype(np.float64)
            )
        else:
            x = 0.5 * (
                _osc("triangle", f, sr, t).astype(np.float64)
                + _osc("sine", f, sr, t).astype(np.float64)
            )
        out += amp * x
    # bajo pivote: tónica de B una octava abajo, entra en la segunda mitad
    bass = _osc("sine", midi_to_freq(root_b - 12), sr, t).astype(np.float64)
    mask = np.asarray(ease(np.clip((p - 0.5) * 2.0, 0.0, 1.0), 62.0, "smooth"), dtype=np.float64)
    out += 0.5 * bass * mask
    env = _adsr(n, sr, max(mood_a.attack, mood_b.attack, 0.05), max(mood_a.release, mood_b.release, 0.15))
    out = out * env
    return _normalize(out)


def render_riser(sr: int, opts: RiserOptions) -> np.ndarray:
    """Sintetiza el riser (solo el elemento, float32).

    El elemento mide dur + tail; el hit está exactamente en la muestra
    ``int(dur·sr)``: hasta ahí el crescendo (ease)², después la cola decae
    exponencialmente (τ = tail/3; zeros si tail=0). Estilo "notes": grados
    de la escala con duraciones geométricas r=0.72 (acelerando), cada uno
    apilado con quinta y octava — siempre un acorde, nunca melodía suelta.
    Estilo "glide": 2 octavas exponenciales con vibrato creciente.
    """
    opts.validate()
    mood = MOODS[opts.mood]
    key = opts.key if opts.key is not None else mood.root
    root_midi = note_to_midi(key, mood.octave)
    n_hit = int(round(opts.dur * sr))
    n_total = max(int(round((opts.dur + opts.tail) * sr)), n_hit)
    out = np.zeros(n_total, dtype=np.float64)
    if opts.style == "notes":
        grados = scale_midi(root_midi - 12, mood.mode, 2)  # sube ~2 octavas desde una octava abajo
        k = len(grados)
        weights = np.asarray([0.72**i for i in range(k)], dtype=np.float64)
        d = weights / weights.sum() * opts.dur  # d_i ∝ r^i, Σd_i = dur
        starts = np.concatenate(([0.0], np.cumsum(d)[:-1]))
        for i in range(k):
            note_dur = 0.9 * float(d[i]) + (opts.tail if i == k - 1 else 0.0)
            g = int(grados[i])
            seg = (
                _voice(mood.wave, midi_to_freq(g), note_dur, sr, mood).astype(np.float64)
                + 0.4 * _voice(mood.wave, midi_to_freq(g + 7), note_dur, sr, mood).astype(np.float64)
                + 0.3 * _voice(mood.wave, midi_to_freq(g + 12), note_dur, sr, mood).astype(np.float64)
            )
            i0 = int(round(float(starts[i]) * sr))
            i1 = min(i0 + len(seg), n_total)
            if i1 > i0:
                out[i0:i1] += seg[: i1 - i0]
    else:  # glide
        t = np.arange(n_total, dtype=np.float64) / sr
        p = np.asarray(ease(np.clip(t / opts.dur, 0.0, 1.0)), dtype=np.float64)
        f0 = midi_to_freq(root_midi - 12)
        freq_t = f0 * 2.0 ** (2.0 * p)  # 2 octavas, exponencial
        out += _voice(mood.wave, freq_t, opts.dur + opts.tail, sr, mood, vib_progress=True).astype(np.float64)
        out += 0.4 * _voice(
            mood.wave, freq_t * 2.0 ** (7.0 / 12.0), opts.dur + opts.tail, sr, mood, vib_progress=True
        ).astype(np.float64)
    # crescendo global (ease)² hasta el hit + cola exponencial después
    t_all = np.arange(n_total, dtype=np.float64) / sr
    amp = np.empty(n_total, dtype=np.float64)
    amp[:n_hit] = np.asarray(ease(np.clip(t_all[:n_hit] / opts.dur, 0.0, 1.0)), dtype=np.float64) ** 2
    if n_total > n_hit:
        amp[n_hit:] = np.exp(-(t_all[n_hit:] - opts.dur) / (opts.tail / 3.0))
    out *= amp
    return _normalize(out)


def render_melody(sr: int, opts: MelodyOptions) -> tuple[np.ndarray, list[dict]]:
    """Genera la melodía (solo el elemento, float32) y su lista de notas.

    Rejilla en corcheas; duraciones {1,2,4,8} ponderadas por la density del
    mood. Dos frases si bars >= 2: la "pregunta" termina en 4º o 2º grado,
    la "respuesta" termina en la TÓNICA (forzado) — la melodía cuenta algo.
    Cada nota se elige por grado (tónica/3ª/5ª pesan), tamaño de salto
    (density alta → pasos) y contorno del mood (arch/rise/fall/wave).
    Devuelve (elemento normalizado a 0.5, notas) con notas = [{"t_on": s,
    "dur": s, "midi": int, "freq": Hz, "degree": índice en la escala}].
    """
    opts.validate()
    mood = MOODS[opts.mood]
    bpm = opts.bpm if opts.bpm is not None else mood.bpm
    key = opts.key if opts.key is not None else mood.root
    root_midi = note_to_midi(key, mood.octave)
    n_int = len(SCALES[mood.mode])
    scale = scale_midi(root_midi, mood.mode, 2)
    max_idx = len(scale) - 1
    beat = 60.0 / bpm
    eighth = 0.5 * beat
    total_e = opts.bars * 8
    total_s = opts.bars * 4.0 * beat
    rng = np.random.default_rng(opts.seed)

    # plan rítmico: duraciones en corcheas ponderadas por density (alta → cortas)
    choices = np.asarray((1, 2, 4, 8))
    w = np.asarray(
        (
            0.2 + 0.8 * mood.density,
            0.6,
            0.6 * (1.0 - 0.5 * mood.density),
            0.4 * (1.0 - mood.density),
        )
    )
    w = w / w.sum()
    durs: list[int] = []
    filled = 0
    while filled < total_e:
        d = int(rng.choice(choices, p=w))
        d = min(d, total_e - filled)
        durs.append(d)
        filled += d
    starts_e: list[int] = []
    acc = 0
    for d in durs:
        starts_e.append(acc)
        acc += d
    n_notes = len(durs)

    # frontera de frases: la primera nota que cae en la 2ª mitad abre la respuesta
    question_last: int | None = None
    if opts.bars >= 2:
        half = total_e / 2.0
        for j in range(n_notes):
            if starts_e[j] >= half:
                question_last = j - 1
                break

    def grado_weight(idx_c: int) -> float:
        deg = idx_c % n_int
        if deg == 0:
            return 1.0  # tónica
        iv = int(scale[idx_c] - root_midi) % 12
        if iv in (3, 4, 7):
            return 0.7  # 3ª / 5ª
        if deg == n_int - 1:
            return 0.3  # sensible: el último grado antes de la tónica
        return 0.45

    def target_index(prog: float) -> float:
        m = float(max_idx)
        if mood.contour == "arch":
            return m * np.sin(np.pi * prog)
        if mood.contour == "rise":
            return m * prog
        if mood.contour == "fall":
            return m * (1.0 - prog)
        return m * abs(np.sin(2.0 * np.pi * prog))  # wave

    step_base = {1: 1.0, 2: 0.6, 3: 0.3}
    bell_extra = mood.release if mood.wave == "bell" else 0.0
    buf = np.zeros(int(round(total_s * sr)), dtype=np.float64)
    idx = 0
    notas: list[dict] = []
    for j in range(n_notes):
        if j == 0:
            idx = 0  # primera nota: tónica
        elif j == question_last:
            idx = min((3, 1), key=lambda c: abs(c - idx))  # pregunta: 4º o 2º grado
        elif j == n_notes - 1:
            idx = min((0, n_int), key=lambda c: abs(c - idx))  # respuesta: tónica
        else:
            cands = [idx + s for s in (-3, -2, -1, 1, 2, 3) if 0 <= idx + s <= max_idx]
            tgt = target_index(starts_e[j] / total_e)
            ws = np.asarray(
                [
                    grado_weight(c)
                    * step_base[abs(c - idx)] ** (1.0 + mood.density)
                    * np.exp(-abs(c - tgt) / 3.0)
                    for c in cands
                ]
            )
            ws = ws / ws.sum()
            idx = int(rng.choice(np.asarray(cands), p=ws))
        dur_s = durs[j] * eighth
        t_on = starts_e[j] * eighth
        midi = int(scale[idx])
        # bell: la nota suena dur + release → resonancias solapadas (deseado)
        v = _voice(mood.wave, midi_to_freq(midi), dur_s + bell_extra, sr, mood).astype(np.float64)
        i0 = int(round(t_on * sr))
        i1 = min(i0 + len(v), len(buf))
        if i1 > i0:
            buf[i0:i1] += v[: i1 - i0]
        notas.append(
            {"t_on": t_on, "dur": dur_s, "midi": midi, "freq": midi_to_freq(midi), "degree": idx}
        )
    return _normalize(buf), notas


# ---------------------------------------------------------------------------
# Mezcla
# ---------------------------------------------------------------------------


def mix_element(
    samples: np.ndarray,
    sr: int,
    element: np.ndarray,
    at: float,
    gain_db: float,
    duck_db: float = 0.0,
    fade: float = DEFAULT_MIX_FADE,
) -> np.ndarray:
    """Mezcla un elemento sobre el audio seco en ``at`` s (misma duración).

    Fuera de la región [i0, i0+n_elem) la salida es BIT-EXACTA al input
    (misma convención de región que el lowpass). ``duck_db > 0`` baja la
    parte seca bajo el elemento (rampas S ease 62 de ``fade`` s en ambos
    bordes). Clip a [-1, 1] SOLO dentro de la región.
    """
    if at < 0:
        raise EnhancementError(f"at debe ser >= 0, got {at}")
    dry = np.asarray(samples, dtype=np.float32).reshape(-1)
    elem = np.asarray(element, dtype=np.float32).reshape(-1)
    out = dry.copy()  # fuera de la región: bit-exacto
    i0 = int(round(at * sr))
    if i0 >= len(dry) or elem.size == 0:
        return out
    i1 = min(i0 + elem.size, len(dry))
    region = dry[i0:i1].astype(np.float64)
    if duck_db > 0.0:
        n_r = i1 - i0
        t_r = np.arange(n_r, dtype=np.float64) / sr
        depth = 10.0 ** (-duck_db / 20.0)
        if fade > 0.0:
            shape = np.asarray(ease(np.clip(t_r / fade, 0.0, 1.0), 62.0, "smooth")) * np.asarray(
                ease(np.clip(((n_r / sr) - t_r) / fade, 0.0, 1.0), 62.0, "smooth")
            )
        else:
            shape = np.ones(n_r, dtype=np.float64)
        region = region * (1.0 - (1.0 - depth) * shape)
    g = 10.0 ** (gain_db / 20.0)
    out[i0:i1] = np.clip(region + elem[: i1 - i0].astype(np.float64) * g, -1.0, 1.0).astype(np.float32)
    return out


# ---------------------------------------------------------------------------
# File-level (espejo de lowpass_file)
# ---------------------------------------------------------------------------


def _resolve_riser_opts(opts: RiserOptions, duration: float) -> RiserOptions:
    """hit=None → el elemento termina justo al final del archivo.

    hit = duration − tail: la subida acaba en el hit y la cola del release
    resuelve DENTRO del archivo (validate exige hit >= dur).
    """
    if opts.hit is None:
        opts = replace(opts, hit=duration - opts.tail)
        opts.validate()
    return opts


def _resolve_melody_opts(opts: MelodyOptions) -> MelodyOptions:
    """bpm=None → el bpm del mood."""
    if opts.bpm is None:
        return replace(opts, bpm=MOODS[opts.mood].bpm)
    return opts


def _check_placement(duration: float, start: float, end: float, nombre: str) -> None:
    """Rechaza elementos que no caben en el archivo (un no-op silencioso confunde)."""
    if start >= duration:
        raise EnhancementError(f"{nombre} ({start:g}) fuera del archivo ({duration:.2f} s)")
    if end > duration + 1e-6:
        raise EnhancementError(
            f"{nombre} ({end:.2f} s) fuera del archivo ({duration:.2f} s): "
            "el elemento debe caber (reduce --dur/--bars/--tail)"
        )


def build_transition_plan(input: str | Path, opts: TransitionOptions) -> str:
    """Plan legible para --dry-run (misma convención que lowpass/build_plan)."""
    opts.validate()
    inp = Path(input)
    data = audioio.load_audio(inp)
    _check_placement(data.duration_s, opts.at, opts.at + opts.dur, "at")
    mood_a, mood_b, _ra, _rb, chord_a, b_voiced = _transition_chords(opts)
    key_a = opts.from_key if opts.from_key is not None else mood_a.root
    key_b = opts.to_key if opts.to_key is not None else mood_b.root
    names_a = "-".join(midi_to_name(m) for m in chord_a)
    names_b = "-".join(midi_to_name(m) for m in b_voiced)
    motion = sum(abs(a - b) for a, b in zip(chord_a, b_voiced))
    lines = [
        "VOXERA PLAN (audio transition)",
        f"  entrada  : {inp} ({data.source_sample_rate} Hz, {data.duration_s:.2f} s)",
        f"  emoción  : {opts.from_mood} ({key_a} {mood_a.mode}) → {opts.to_mood} ({key_b} {mood_b.mode})",
        f"  acordes  : {names_a} → {names_b} (movimiento mínimo: {motion} semitonos)",
        f"  región   : {opts.at:.2f} s .. {opts.at + opts.dur:.2f} s",
        f"  ganancia : {opts.gain_db:g} dB (curva {opts.curve:.0f}, easing {opts.easing})",
        f"  salida   : wav 48 kHz 24-bit (misma duración)",
    ]
    return "\n".join(lines)


def build_riser_plan(input: str | Path, opts: RiserOptions) -> str:
    """Plan legible para --dry-run (misma convención que lowpass/build_plan)."""
    opts.validate()
    inp = Path(input)
    data = audioio.load_audio(inp)
    opts = _resolve_riser_opts(opts, data.duration_s)
    t0 = opts.hit - opts.dur  # la subida acaba exactamente en el hit
    _check_placement(data.duration_s, t0, t0 + opts.dur + opts.tail, "hit")
    mood = MOODS[opts.mood]
    key = opts.key if opts.key is not None else mood.root
    root_midi = note_to_midi(key, mood.octave)
    if opts.style == "notes":
        grados = scale_midi(root_midi - 12, mood.mode, 2)
        detalle = f"{len(grados)} grados ({midi_to_name(int(grados[0]))} → {midi_to_name(int(grados[-1]))})"
    else:
        f0 = midi_to_freq(root_midi - 12)
        detalle = f"glide {f0:.1f} Hz → {f0 * 4.0:.1f} Hz (2 octavas, exponencial)"
    lines = [
        "VOXERA PLAN (audio riser)",
        f"  entrada   : {inp} ({data.source_sample_rate} Hz, {data.duration_s:.2f} s)",
        f"  emoción   : {opts.mood} ({key} {mood.mode}), estilo {opts.style}",
        f"  subida    : {detalle}",
        f"  hit       : termina en el hit t={opts.hit:.2f} s (crescendo (ease)² hasta el hit)",
        f"  tail      : {opts.tail:g} s de release tras el hit",
        f"  ganancia  : {opts.gain_db:g} dB",
        f"  salida    : wav 48 kHz 24-bit (misma duración)",
    ]
    return "\n".join(lines)


def build_melody_plan(input: str | Path, opts: MelodyOptions) -> str:
    """Plan legible para --dry-run (renderiza para contar notas: rápido y determinista)."""
    opts.validate()
    inp = Path(input)
    data = audioio.load_audio(inp)
    opts = _resolve_melody_opts(opts)
    mood = MOODS[opts.mood]
    key = opts.key if opts.key is not None else mood.root
    element, notas = render_melody(audioio.INTERNAL_SAMPLE_RATE, opts)
    total = len(element) / audioio.INTERNAL_SAMPLE_RATE
    _check_placement(data.duration_s, opts.start, opts.start + total, "start")
    midis = [nn["midi"] for nn in notas]
    duck = f"{opts.duck_db:g} dB" if opts.duck_db > 0.0 else "off (sin ducking)"
    lines = [
        "VOXERA PLAN (audio melody)",
        f"  entrada  : {inp} ({data.source_sample_rate} Hz, {data.duration_s:.2f} s)",
        f"  emoción  : {opts.mood} ({key} {mood.mode}), bpm {opts.bpm:g}, seed {opts.seed}",
        f"  melodía  : {len(notas)} notas, rango MIDI {min(midis)}-{max(midis)} "
        f"({midi_to_name(min(midis))}-{midi_to_name(max(midis))})",
        f"  región   : {opts.start:.2f} s .. {opts.start + total:.2f} s",
        f"  ganancia : {opts.gain_db:g} dB",
        f"  duck     : {duck}",
        f"  salida   : wav 48 kHz 24-bit (misma duración)",
    ]
    return "\n".join(lines)


def transition_file(input: str | Path, output: str | Path, opts: TransitionOptions) -> Path:
    """Aplica una transición tonal a un archivo de audio y escribe la salida."""
    opts.validate()
    data = audioio.load_audio(input)
    _check_placement(data.duration_s, opts.at, opts.at + opts.dur, "at")
    element = render_transition(audioio.INTERNAL_SAMPLE_RATE, opts)
    out = mix_element(data.samples, audioio.INTERNAL_SAMPLE_RATE, element, opts.at, opts.gain_db)
    return audioio.write_wav(output, out, sample_rate=audioio.INTERNAL_SAMPLE_RATE)


def riser_file(input: str | Path, output: str | Path, opts: RiserOptions) -> Path:
    """Aplica un riser tonal (termina en el hit) y escribe la salida."""
    opts.validate()
    data = audioio.load_audio(input)
    opts = _resolve_riser_opts(opts, data.duration_s)
    t0 = opts.hit - opts.dur  # la subida acaba exactamente en el hit
    _check_placement(data.duration_s, t0, t0 + opts.dur + opts.tail, "hit")
    element = render_riser(audioio.INTERNAL_SAMPLE_RATE, opts)
    out = mix_element(data.samples, audioio.INTERNAL_SAMPLE_RATE, element, t0, opts.gain_db)
    return audioio.write_wav(output, out, sample_rate=audioio.INTERNAL_SAMPLE_RATE)


def melody_file(input: str | Path, output: str | Path, opts: MelodyOptions) -> Path:
    """Añade una melodía tonal bajo la voz (con duck opcional) y escribe la salida."""
    opts.validate()
    data = audioio.load_audio(input)
    opts = _resolve_melody_opts(opts)
    element, _notas = render_melody(audioio.INTERNAL_SAMPLE_RATE, opts)
    total = len(element) / audioio.INTERNAL_SAMPLE_RATE
    _check_placement(data.duration_s, opts.start, opts.start + total, "start")
    out = mix_element(
        data.samples, audioio.INTERNAL_SAMPLE_RATE, element, opts.start, opts.gain_db, duck_db=opts.duck_db
    )
    return audioio.write_wav(output, out, sample_rate=audioio.INTERNAL_SAMPLE_RATE)
