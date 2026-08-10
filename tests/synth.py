"""Deterministic synthetic-audio fixtures for fase-2 tests.

Everything is generated in-memory at 48 kHz mono float32 (the frozen internal
format) unless noted. Seed-fixed so fixtures are reproducible.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, lfilter

SR = 48000


def speech_like(seconds: float = 4.0, gap_frac: float = 0.3, seed: int = 42) -> np.ndarray:
    """Harmonic-stack 'speech' with syllabic AM + band-limited noise + gaps.

    Verified against webrtcvad (aggressiveness 2): speech ratio ~0.86.
    """
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    t = np.arange(n) / SR
    f0 = 140.0
    x = sum(np.sin(2 * np.pi * f0 * k * t + 0.5 * k) / k for k in range(1, 12))
    x *= 0.5 * (1 + 0.6 * np.sin(2 * np.pi * 3.7 * t))
    b, a = butter(4, [200 / (SR / 2), 3400 / (SR / 2)], btype="band")
    noise = lfilter(b, a, rng.standard_normal(n))
    x = x + 0.35 * noise
    gap = int(gap_frac * SR)
    for start in range(int(0.6 * SR), n - gap, int(1.1 * SR)):
        x[start : start + gap] *= 0.02
    return 0.4 * x / np.max(np.abs(x))


def silence(seconds: float = 2.0) -> np.ndarray:
    return np.zeros(int(seconds * SR), dtype=np.float32)


def tone(freq_hz: float, seconds: float = 2.0, amplitude: float = 0.3) -> np.ndarray:
    t = np.arange(int(seconds * SR)) / SR
    return (amplitude * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)


def mud_heavy(seconds: float = 3.0) -> np.ndarray:
    """Voice with strong 100-300 Hz content (mud-band heavy fixture)."""
    t = np.arange(int(seconds * SR)) / SR
    x = 0.6 * np.sin(2 * np.pi * 220 * t) + 0.3 * np.sin(2 * np.pi * 300 * t)
    x += 0.15 * np.sin(2 * np.pi * 3000 * t)
    return (0.5 * x / np.max(np.abs(x))).astype(np.float32)


def sibilant(seconds: float = 2.0, seed: int = 7) -> np.ndarray:
    """Long /s/-like noise bursts: 4-8 kHz band-passed noise with gaps."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    b, a = butter(4, [4000 / (SR / 2), 8000 / (SR / 2)], btype="band")
    noise = lfilter(b, a, rng.standard_normal(n))
    noise *= 0.5
    # alternate sibilance / quiet
    for start in range(0, n, int(0.5 * SR)):
        noise[start + int(0.3 * SR) : start + int(0.5 * SR)] *= 0.05
    return noise.astype(np.float32)


def hum_buzz(seconds: float = 2.0) -> np.ndarray:
    """50 Hz mains hum + harmonics at low level."""
    t = np.arange(int(seconds * SR)) / SR
    x = 0.2 * np.sin(2 * np.pi * 50 * t) + 0.06 * np.sin(2 * np.pi * 100 * t)
    return x.astype(np.float32)


def with_breaths(seed: int = 3) -> np.ndarray:
    """Speech segments separated by a broadband low-level 'breath' gap."""
    speech = speech_like(seconds=2.4, gap_frac=0.15, seed=seed)
    rng = np.random.default_rng(seed + 1)
    breath = 0.015 * lfilter(
        *butter(4, [1000 / (SR / 2), 8000 / (SR / 2)], btype="band"),
        rng.standard_normal(int(0.35 * SR)),
    )
    out = np.concatenate([speech[: int(1.2 * SR)], breath, speech[int(1.2 * SR) :]])
    return out.astype(np.float32)


def with_clicks(seed: int = 9) -> np.ndarray:
    """Speech with 3 short 2-6 kHz transients in the silent gaps."""
    speech = speech_like(seconds=3.0, gap_frac=0.4, seed=seed)
    rng = np.random.default_rng(seed)
    b, a = butter(4, [2000 / (SR / 2), 6000 / (SR / 2)], btype="band")
    out = speech.copy()
    for offset in (0.7, 1.3, 1.9):
        start = int(offset * SR)
        click = 0.6 * lfilter(b, a, rng.standard_normal(int(0.012 * SR)))
        out[start : start + len(click)] += click
    return out.astype(np.float32)


def long_gaps(seed: int = 11) -> np.ndarray:
    """Speech 1s + gap 2s + speech 1s + gap 1.2s + speech 1s (total ~5.2 s)."""
    rng = np.random.default_rng(seed)
    parts: list[np.ndarray] = []
    for gap_s in (2.0, 1.2):
        seg = speech_like(seconds=1.0, gap_frac=0.0, seed=seed + len(parts))
        parts.append(seg)
        parts.append(np.zeros(int(gap_s * SR), dtype=np.float32))
    parts.append(speech_like(seconds=1.0, gap_frac=0.0, seed=seed + 9))
    return np.concatenate(parts).astype(np.float32)


def with_plosive(seed: int = 5) -> np.ndarray:
    """Speech whose first onset contains a strong <150 Hz burst (P/B/T-like)."""
    speech = speech_like(seconds=2.0, gap_frac=0.0, seed=seed)
    t = np.arange(int(0.03 * SR)) / SR
    burst = 0.9 * np.sin(2 * np.pi * 60 * t) * np.exp(-t * 80)
    out = speech.copy()
    out[: len(burst)] += burst
    return out.astype(np.float32)
