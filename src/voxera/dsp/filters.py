"""Vocal DSP building blocks (Track 1B).

Every stage is deterministic on the frozen internal format (48 kHz mono
float32). Filters are RBJ-cookbook biquads / scipy IIRs applied with
``scipy.signal.lfilter``; dynamics (compressor/limiter) come from pedalboard;
loudness from pyloudnorm. The de-esser is a numpy spectral sidechain (spec:
detection 4-10 kHz, max 6 dB, attack ~1 ms, release 50-100 ms).
"""

from __future__ import annotations

import numpy as np
import scipy.signal

# ---------------------------------------------------------------------------
# Biquad building blocks (RBJ audio EQ cookbook)
# ---------------------------------------------------------------------------


def _rbj_peaking(f0: float, q: float, gain_db: float, sr: int) -> tuple[np.ndarray, np.ndarray]:
    """Peaking EQ biquad coefficients (``b``, ``a``) at ``f0``."""
    a = 10 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * f0 / sr
    alpha = np.sin(w0) / (2.0 * q)
    b = np.array([1.0 + alpha * a, -2.0 * np.cos(w0), 1.0 - alpha * a])
    a_coeff = np.array([1.0 + alpha / a, -2.0 * np.cos(w0), 1.0 - alpha / a])
    return b / a_coeff[0], a_coeff / a_coeff[0]


def _rbj_highshelf(f0: float, gain_db: float, sr: int, s: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """High-shelf biquad coefficients at ``f0``."""
    a = 10 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * f0 / sr
    alpha = np.sin(w0) / 2.0 * np.sqrt((a + 1.0 / a) * (1.0 / s - 1.0) + 2.0)
    two_sqrt_a = 2.0 * np.sqrt(a)
    b = np.array(
        [
            a * ((a + 1.0) + (a - 1.0) * np.cos(w0) + two_sqrt_a * alpha),
            -2.0 * a * ((a - 1.0) + (a + 1.0) * np.cos(w0)),
            a * ((a + 1.0) + (a - 1.0) * np.cos(w0) - two_sqrt_a * alpha),
        ]
    )
    a_coeff = np.array(
        [
            (a + 1.0) - (a - 1.0) * np.cos(w0) + two_sqrt_a * alpha,
            2.0 * ((a - 1.0) - (a + 1.0) * np.cos(w0)),
            (a + 1.0) - (a - 1.0) * np.cos(w0) - two_sqrt_a * alpha,
        ]
    )
    return b / a_coeff[0], a_coeff / a_coeff[0]


def _apply(b: np.ndarray, a: np.ndarray, x: np.ndarray) -> np.ndarray:
    return scipy.signal.lfilter(b, a, x).astype(np.float32)


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------


def dc_block(samples: np.ndarray, sr: int) -> np.ndarray:
    """DC removal: one-pole high-pass at 20 Hz (spec alternative to a DC blocker)."""
    b, a = scipy.signal.butter(1, 20.0 / (sr / 2.0), btype="high")
    return _apply(b, a, samples)


def highpass_lr24(samples: np.ndarray, sr: int, cutoff_hz: float) -> np.ndarray:
    """Linkwitz-Riley 24 dB/oct high-pass = two cascaded 2nd-order Butterworth."""
    b, a = scipy.signal.butter(2, cutoff_hz / (sr / 2.0), btype="high")
    return _apply(b, a, _apply(b, a, samples))


def notch(samples: np.ndarray, sr: int, freq_hz: float, q: float = 20.0) -> np.ndarray:
    """Narrow notch filter (de-hum)."""
    b, a = scipy.signal.iirnotch(freq_hz, q, fs=sr)
    return _apply(b, a, samples)


def vocal_eq(
    samples: np.ndarray,
    sr: int,
    *,
    mud_db: float = 0.0,
    boxiness_db: float = 0.0,
    presence_db: float = 0.0,
    air_db: float = 0.0,
) -> np.ndarray:
    """Vocal EQ: mud 100-300 Hz, boxiness 300-600 Hz, presence 2-5 kHz, air 8-14 kHz.

    Bounded to ±4 dB per spec ("EQ ≤±4 dB"). Zero-gain stages are skipped.
    """
    x = samples
    if mud_db:
        b, a = _rbj_peaking(180.0, 0.9, float(np.clip(mud_db, -4, 4)), sr)
        x = _apply(b, a, x)
    if boxiness_db:
        b, a = _rbj_peaking(450.0, 1.0, float(np.clip(boxiness_db, -4, 4)), sr)
        x = _apply(b, a, x)
    if presence_db:
        b, a = _rbj_peaking(3200.0, 0.8, float(np.clip(presence_db, -4, 4)), sr)
        x = _apply(b, a, x)
    if air_db:
        b, a = _rbj_highshelf(9000.0, float(np.clip(air_db, -4, 4)), sr)
        x = _apply(b, a, x)
    return x


def deesser(
    samples: np.ndarray,
    sr: int,
    *,
    threshold_db: float = -8.0,
    max_att_db: float = 6.0,
    attack_s: float = 0.001,
    release_s: float = 0.075,
) -> np.ndarray:
    """Spectral de-esser (spec Track 1B).

    Detection band 4-10 kHz vs reference 100 Hz-10 kHz per 10 ms frame; gain
    reduction only on sibilant frames, smoothed with attack/release, applied
    at sample resolution. Non-sibilant frames (and their high-frequency air)
    are untouched, satisfying the no-harm criterion on 2-5 kHz energy.
    """
    x = np.asarray(samples, dtype=np.float32)
    if len(x) < 256:
        return x
    frame_ms = 10.0
    frame_len = int(sr * frame_ms / 1000.0)
    n_frames = len(x) // frame_len
    if n_frames == 0:
        return x

    frames = x[: n_frames * frame_len].reshape(n_frames, frame_len)
    spec = np.fft.rfft(frames, axis=1)
    power = np.abs(spec) ** 2
    freqs = np.fft.rfftfreq(frame_len, 1.0 / sr)

    band = (freqs >= 4000.0) & (freqs < 10000.0)
    ref = (freqs >= 100.0) & (freqs < 10000.0)
    band_energy = power[:, band].sum(axis=1)
    ref_energy = power[:, ref].sum(axis=1)
    frame_rms_db = 20.0 * np.log10(np.sqrt((frames**2).mean(axis=1)) + 1e-12)

    with np.errstate(divide="ignore"):
        ratio_db = 10.0 * np.log10((band_energy + 1e-12) / (ref_energy + 1e-12))
    excess = np.where(frame_rms_db > -50.0, ratio_db - threshold_db, -np.inf)
    reduction = np.clip(excess, 0.0, max_att_db)
    gains = 10.0 ** (-reduction / 20.0)

    # Attack/release smoothing (one-pole), then sample-domain interpolation.
    attack_coef = 1.0 - np.exp(-1.0 / (attack_s * sr / frame_len)) if attack_s > 0 else 1.0
    release_coef = 1.0 - np.exp(-1.0 / (release_s * sr / frame_len))
    smoothed = np.empty_like(gains)
    current = 1.0
    for i, g in enumerate(gains):
        coef = attack_coef if g < current else release_coef
        current = current + coef * (g - current)
        smoothed[i] = current

    centers = (np.arange(n_frames) + 0.5) * frame_len
    gain_env = np.interp(np.arange(len(x)), centers, smoothed).astype(np.float32)
    return x * gain_env


def compressor(
    samples: np.ndarray,
    sr: int,
    *,
    threshold_db: float = -24.0,
    ratio: float = 2.0,
) -> np.ndarray:
    """Soft compressor (pedalboard)."""
    import pedalboard

    comp = pedalboard.Compressor(
        threshold_db=threshold_db,
        ratio=ratio,
        attack_ms=10.0,
        release_ms=150.0,
    )
    return comp(samples, sr)


def limiter(samples: np.ndarray, sr: int, threshold_db: float = -1.0) -> np.ndarray:
    """Look-ahead peak limiter (pedalboard)."""
    import pedalboard

    return pedalboard.Limiter(threshold_db=threshold_db, release_ms=50.0)(samples, sr)


def true_peak_db(samples: np.ndarray) -> float:
    """True peak via 4x polyphase oversampling (spec: true peak, not sample peak)."""
    if len(samples) == 0:
        return -np.inf
    up = scipy.signal.resample_poly(samples, 4, 1)
    peak = float(np.max(np.abs(up)))
    return 20.0 * np.log10(peak + 1e-12)


def loudness_normalize(samples: np.ndarray, sr: int, target_lufs: float) -> np.ndarray:
    """Normalize integrated loudness to ``target_lufs``; true peak capped at -1 dBTP.

    The frozen stage order is limiter -> loudnorm (spec). A final true-peak
    guard guarantees ``true_peak <= -1 dBTP`` even when normalization adds gain
    after the limiter stage.
    """
    import pyloudnorm as pyln

    x = np.asarray(samples, dtype=np.float32)
    meter = pyln.Meter(sr)
    measured = meter.integrated_loudness(x)
    if not np.isfinite(measured) or measured < -70.0:
        return x  # effectively silent; nothing to normalize
    gain_db = float(target_lufs - measured)
    y = x * float(10.0 ** (gain_db / 20.0))
    if true_peak_db(y) > -1.0:
        # pedalboard's limiter works on sample peaks; oversampled true peak can
        # still exceed -1 dBTP, so re-measure and apply an exact safety trim.
        y = limiter(y, sr, threshold_db=-3.0)
        tp = true_peak_db(y)
        if tp > -1.0:
            y = y * float(10.0 ** ((-1.0 - tp) / 20.0))
    return y.astype(np.float32)
