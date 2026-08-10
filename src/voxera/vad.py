"""Voice activity detection (Track 1A/1).

webrtcvad operates on 30 ms frames (spec: ``VAD webrtcvad-wheels (30 ms
frames)``) at the internal 48 kHz rate, which the wrapper accepts natively.
All masks are deterministic for a fixed input.
"""

from __future__ import annotations

import numpy as np

from voxera.errors import NoSpeechError

VAD_FRAME_MS = 30
NO_SPEECH_RATIO = 0.05  # spec: speech ratio < 5% -> VOXERA_NO_SPEECH


def _frame_pcm(samples: np.ndarray, sample_rate: int) -> list[bytes]:
    frame_len = sample_rate * VAD_FRAME_MS // 1000
    n_frames = len(samples) // frame_len
    pcm = (samples[: n_frames * frame_len].reshape(n_frames, frame_len) * 32767.0)
    pcm = pcm.astype(np.int16)
    return [pcm[i].tobytes() for i in range(n_frames)]


def speech_mask(samples: np.ndarray, sample_rate: int, aggressiveness: int = 2) -> np.ndarray:
    """Per-30ms-frame boolean speech mask (same length as the frame count)."""
    from webrtcvad import Vad  # declared dependency

    vad = Vad(aggressiveness)
    frames = _frame_pcm(samples, sample_rate)
    mask = np.zeros(len(frames), dtype=bool)
    for i, frame in enumerate(frames):
        mask[i] = vad.is_speech(frame, sample_rate)
    return mask


def speech_ratio(samples: np.ndarray, sample_rate: int, aggressiveness: int = 2) -> float:
    """Fraction of 30 ms frames classified as speech (0.0-1.0)."""
    mask = speech_mask(samples, sample_rate, aggressiveness)
    return float(mask.mean()) if len(mask) else 0.0


def require_speech(samples: np.ndarray, sample_rate: int, aggressiveness: int = 2) -> float:
    """Raise :class:`NoSpeechError` (exit 20) when speech ratio < 5%."""
    ratio = speech_ratio(samples, sample_rate, aggressiveness)
    if ratio < NO_SPEECH_RATIO:
        raise NoSpeechError(
            f"no speech detected (speech ratio {ratio * 100:.1f}% < "
            f"{NO_SPEECH_RATIO * 100:.0f}%)"
        )
    return ratio
