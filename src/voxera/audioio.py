"""Audio I/O and the frozen format policy (Track 1A).

Frozen policies (docs/SPECS-fase2.md, Track 1A):

- **Input WAV**: 16 / 22.05 / 44.1 / 48 kHz, mono or stereo. Anything else
  fails with a clear error that names the read value. (Video input arrives in
  Track 4 and is resampled to 48 kHz by the same path.)
- **Stereo downmix**: energy-preserving ``mono = 0.5 * (L + R)`` — never a raw
  sum, which can double amplitude and clip.
- **Internal**: 48 kHz mono float32, resampled with soxr quality.
- **Output WAV**: 48 kHz, PCM 24-bit.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from voxera.errors import EnhancementError

INTERNAL_SAMPLE_RATE = 48000
SUPPORTED_SAMPLE_RATES = frozenset({16000, 22050, 44100, 48000})
RATE_TOLERANCE_HZ = 1  # tolerate tiny header jitter, e.g. 44100.0 vs 44100.5
SUPPORTED_EXTENSIONS = frozenset({".wav"})
MAX_CHANNELS = 2

OUTPUT_SUBTYPE = "PCM_24"

_SUBTYPE_LABELS = {
    "PCM_16": "16-bit",
    "PCM_24": "24-bit",
    "PCM_32": "32-bit",
    "FLOAT": "float32",
    "DOUBLE": "float64",
}


@dataclass(frozen=True)
class AudioData:
    """Loaded audio at the frozen internal format: 48 kHz mono float32."""

    samples: np.ndarray  # float32, shape (n,)
    source_sample_rate: int
    source_channels: int
    source_bit_depth: int | None
    source_format: str  # e.g. "WAV PCM 24-bit"

    @property
    def duration_s(self) -> float:
        return len(self.samples) / INTERNAL_SAMPLE_RATE


def format_label(subtype: str) -> str:
    bits = _SUBTYPE_LABELS.get(subtype)
    if bits is None:
        return f"WAV {subtype}"
    return f"WAV PCM {bits}"


def validate_input_path(path: str | Path) -> Path:
    """Validate that ``path`` is a usable WAV input (Track 1A policy)."""
    inp = Path(path)
    if not inp.exists():
        raise EnhancementError(f"no such file: {inp}")
    if inp.is_dir():
        raise EnhancementError(f"input is a directory: {inp}")
    if inp.suffix.lower() not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise EnhancementError(
            f"unsupported format: {inp.suffix} (supported: {supported})"
        )
    return inp


def load_audio(path: str | Path) -> AudioData:
    """Load ``path`` under the frozen policy, returning 48 kHz mono float32.

    Raises :class:`EnhancementError` for missing files, unsupported formats,
    out-of-policy sample rates, channel counts or empty audio.
    """
    inp = validate_input_path(path)
    try:
        info = sf.info(str(inp))
    except Exception as exc:  # noqa: BLE001 - user-facing boundary
        raise EnhancementError(f"invalid wav file: {inp}") from exc

    rate = info.samplerate
    if not any(abs(rate - supported) <= RATE_TOLERANCE_HZ for supported in SUPPORTED_SAMPLE_RATES):
        allowed = ", ".join(f"{r / 1000:g} kHz" for r in sorted(SUPPORTED_SAMPLE_RATES))
        raise EnhancementError(
            f"unsupported sample rate: {rate} Hz (supported: {allowed})"
        )
    if info.channels > MAX_CHANNELS:
        raise EnhancementError(
            f"unsupported channel count: {info.channels} (supported: 1-2)"
        )
    if info.frames == 0:
        raise EnhancementError(f"empty audio: {inp} contains no frames")

    try:
        audio, sr = sf.read(str(inp), dtype="float32", always_2d=False)
    except Exception as exc:  # noqa: BLE001
        raise EnhancementError(f"failed to read audio: {inp}") from exc

    if audio.ndim > 1:
        # Energy-preserving downmix — never a raw sum (would double amplitude).
        audio = 0.5 * audio.sum(axis=1)
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)

    if abs(sr - INTERNAL_SAMPLE_RATE) > RATE_TOLERANCE_HZ:
        audio = _resample(audio, sr, INTERNAL_SAMPLE_RATE)

    return AudioData(
        samples=audio,
        source_sample_rate=rate,
        source_channels=info.channels,
        source_bit_depth=_SUBTYPE_LABELS.get(info.subtype),
        source_format=format_label(info.subtype),
    )


def _resample(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Resample with soxr (spec: 'resample con calidad soxr')."""
    try:
        import soxr
    except ImportError as exc:  # pragma: no cover - dependency declared
        raise EnhancementError("resampling requires the 'soxr' package") from exc
    out = soxr.resample(samples, src_rate, dst_rate, quality="HQ")
    return np.asarray(out, dtype=np.float32)


def write_wav(
    path: str | Path,
    samples: np.ndarray,
    sample_rate: int = INTERNAL_SAMPLE_RATE,
    subtype: str = OUTPUT_SUBTYPE,
) -> Path:
    """Write ``samples`` as a WAV at the frozen output policy (48 kHz, 24-bit)."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    audio = np.asarray(samples, dtype=np.float32).reshape(-1)
    try:
        sf.write(str(out), audio, sample_rate, subtype=subtype)
    except Exception as exc:  # noqa: BLE001
        raise EnhancementError(f"failed to write audio: {out}") from exc
    return out
