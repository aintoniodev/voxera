"""``voxera analyze`` — analysis-only metrics (Track 1).

Never modifies audio. Every estimate carries a ``confidence`` (an RT60
without one is misleading). Heuristics are measurable and replaceable: the
schema is prepared for future ML, but today everything is deterministic
numpy/pyloudnorm/VAD.

Report contract (docs/SPECS-fase2.md, Track 1): blocks ``input``, ``loudness``,
``voice``, ``spectral``, ``room``, ``artifacts``, ``system``.
"""

from __future__ import annotations

import time

import numpy as np

from voxera import audioio
from voxera.device import resolve_device
from voxera.determinism import system_block
from voxera.vad import speech_mask

NOISE_TYPES = (
    "fan ac hiss hum keyboard traffic people music "
    "stationary non-stationary unknown"
).split()


# ---------------------------------------------------------------------------
# Small signal helpers (all deterministic)
# ---------------------------------------------------------------------------


def _mask_to_10ms(mask: np.ndarray, env_len: int) -> np.ndarray:
    """Upscale the 30 ms VAD mask to the 10 ms envelope grid, padded with False."""
    up = np.repeat(mask, 3)
    if len(up) < env_len:
        return np.pad(up, (0, env_len - len(up)))
    return up[:env_len]

def _frame_rms_db(samples: np.ndarray, sr: int, frame_ms: int = 10) -> np.ndarray:
    frame_len = int(sr * frame_ms / 1000.0)
    n = len(samples) // frame_len
    if n == 0:
        return np.array([], dtype=np.float64)
    frames = samples[: n * frame_len].reshape(n, frame_len).astype(np.float64)
    return 20.0 * np.log10(np.sqrt((frames**2).mean(axis=1)) + 1e-12)


def _band_energy_db(samples: np.ndarray, sr: int, lo: float, hi: float) -> float:
    if len(samples) < 64:
        return -np.inf
    spec = np.fft.rfft(samples.astype(np.float64))
    power = np.abs(spec) ** 2 / len(samples) ** 2
    freqs = np.fft.rfftfreq(len(samples), 1.0 / sr)
    band = (freqs >= lo) & (freqs < hi)
    energy = float(power[band].sum())
    return 10.0 * np.log10(energy + 1e-30)


def _spectral_flatness_db(samples: np.ndarray, sr: int, lo: float, hi: float) -> float:
    """Flatness in dB (0 = pure tone, lower = flatter/noisier spectrum)."""
    if len(samples) < 64:
        return -np.inf
    spec = np.abs(np.fft.rfft(samples.astype(np.float64))) ** 2
    freqs = np.fft.rfftfreq(len(samples), 1.0 / sr)
    band = (freqs >= lo) & (freqs < hi)
    p = spec[band] + 1e-30
    geom = np.exp(np.log(p).mean())
    arith = p.mean()
    return float(10.0 * np.log10(geom / arith))


def _loudness_metrics(samples: np.ndarray, sr: int) -> dict:
    import pyloudnorm as pyln

    meter = pyln.Meter(sr, block_size=0.4)
    try:
        integrated = meter.integrated_loudness(samples)
        lra = meter.loudness_range(samples)
        # pyloudnorm 0.2 stores the blockwise ST loudness as a side effect.
        st = np.asarray(meter.blockwise_loudness, dtype=float)
    except Exception:  # noqa: BLE001 - too-short input for the 400 ms blocks
        integrated = st = lra = None
    rms_db = 20.0 * np.log10(np.sqrt((samples**2).mean()) + 1e-12)
    from voxera.dsp.filters import true_peak_db

    def _finite(value):
        return value if value is not None and np.isfinite(value) else None

    metrics = {
        "integrated_lufs": _finite(integrated),
        "short_term_lufs": float(np.max(st)) if st is not None and len(st) else None,
        "lra": _finite(lra),
        "true_peak_db": true_peak_db(samples),
        "rms_db": rms_db,
        "clipping_ratio": float(np.mean(np.abs(samples) >= 0.999)),
    }
    return {k: (None if v is None else v) for k, v in metrics.items()}


def _hum_analysis(samples: np.ndarray, sr: int) -> dict:
    """Tonal peaks near 50/100/150 Hz (mains harmonics), in dBFS."""
    if len(samples) < 512:
        return {"h50": None, "h100": None, "h150": None, "dominant": None}
    spec = np.abs(np.fft.rfft(samples.astype(np.float64))) ** 2 / len(samples) ** 2
    freqs = np.fft.rfftfreq(len(samples), 1.0 / sr)
    out: dict = {}
    for f0, key in ((50.0, "h50"), (100.0, "h100"), (150.0, "h150")):
        band = (freqs >= f0 - 2.0) & (freqs <= f0 + 2.0)
        if not band.any():
            out[key] = None
            continue
        peak_energy = float(spec[band].max())
        out[key] = 10.0 * np.log10(peak_energy + 1e-30)
    levels = {key: out[key] for key in ("h50", "h100", "h150") if out[key] is not None}
    if levels:
        dominant = max(levels, key=levels.get)
        out["dominant"] = {"h50": "50 Hz", "h100": "100 Hz", "h150": "150 Hz"}[dominant]
    else:
        out["dominant"] = None
    return out


# ---------------------------------------------------------------------------
# Segmentation helpers (speech / silence runs)
# ---------------------------------------------------------------------------


def _speech_runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Contiguous speech frame runs as (start, end) frame indices."""
    runs: list[tuple[int, int]] = []
    start = None
    for i, is_speech in enumerate(np.concatenate([[False], mask, [False]])):
        if is_speech and start is None:
            start = i - 1
        elif not is_speech and start is not None:
            runs.append((start, i - 2))
            start = None
    return runs


def _rt60_estimate(
    samples: np.ndarray, sr: int, mask: np.ndarray, frame_ms: int = 10
) -> dict:
    """Schroeder-style decay fit on post-speech tails.

    Heuristic: for each speech segment with a following silence of >= 200 ms,
    fit the dB envelope decay; RT60 = -60 / slope. Confidence from R^2 and
    tail coverage. Returns ``{rt60_s, confidence, reverb}`` (nulls when no
    usable tail exists).
    """
    frame_len = sr * frame_ms // 1000
    env = _frame_rms_db(samples, sr, frame_ms)
    mask10 = _mask_to_10ms(mask, len(env))

    best = None
    for start, end in _speech_runs(mask10):
        if end - start < 30:  # segment shorter than 300 ms: no reliable decay
            continue
        tail_start = end + 1
        tail_end = tail_start
        while tail_end < len(env) and not mask10[tail_end]:
            tail_end += 1
        tail_len = tail_end - tail_start
        if tail_len * frame_ms < 200:  # at least 200 ms of tail
            continue
        tail = env[tail_start:tail_end]
        head_db = float(np.max(tail[: max(1, min(10, len(tail)))]))
        if not np.isfinite(head_db):
            continue
        region = tail[(tail >= head_db - 35.0) & (tail <= head_db - 3.0)]
        if len(region) < 5:
            continue
        x = np.arange(len(region)) * frame_ms / 1000.0
        y = region.astype(np.float64)
        slope, intercept = np.polyfit(x, y, 1)
        r = np.corrcoef(x, y)[0, 1] ** 2
        if slope >= -0.5:  # not decaying: nothing to measure
            continue
        rt60 = -60.0 / slope
        if rt60 <= 0 or rt60 > 10:
            continue
        coverage = len(region) / tail_len
        confidence = float(np.clip(r * coverage, 0.0, 0.95))
        if best is None or confidence > best[0]:
            best = (confidence, rt60, _reverb_label(rt60))

    if best is None:
        return {"rt60_s": None, "confidence": 0.0, "reverb": "unknown"}
    _, rt60, label = best
    return {"rt60_s": rt60, "confidence": best[0], "reverb": label}


def _reverb_label(rt60: float) -> str:
    if rt60 < 0.25:
        return "none"
    if rt60 < 0.4:
        return "low"
    if rt60 < 0.7:
        return "medium"
    return "high"


def _snr_estimate(samples: np.ndarray, mask: np.ndarray, frame_ms: int = 10) -> dict:
    """Speech-vs-silence energy ratio (VAD-segmented), in dB + confidence."""
    sr = audioio.INTERNAL_SAMPLE_RATE
    env = _frame_rms_db(samples, sr, frame_ms)
    mask10 = _mask_to_10ms(mask, len(env))
    if not mask10.any() or not (~mask10).any():
        return {"value": None, "confidence": 0.0}
    speech_power = 10.0 ** (env[mask10] / 10.0)
    noise_power = 10.0 ** (env[~mask10] / 10.0)
    snr = 10.0 * np.log10((speech_power.mean() + 1e-12) / (noise_power.mean() + 1e-12))
    ratio = float(mask.mean()) if len(mask) else 0.0
    confidence = float(np.clip(0.3 + ratio, 0.3, 0.95))
    return {"value": float(np.clip(snr, -10.0, 40.0)), "confidence": confidence}


def breath_regions(samples: np.ndarray, sr: int) -> list[tuple[float, float]]:
    """Breath regions in seconds: low-energy, broadband 1-8 kHz, 100-800 ms,
    adjacent to speech (envelope-based — see ``_breath_detection``)."""
    frame_len = sr * 10 // 1000
    env = _frame_rms_db(samples, sr, 10)
    quiet = env < -30.0
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for i, q in enumerate(np.concatenate([[False], quiet, [False]])):
        if q and start is None:
            start = i - 1
        elif not q and start is not None:
            runs.append((start, i - 2))
            start = None
    regions: list[tuple[float, float]] = []
    for a, b in runs:
        if not 10 <= (b - a) <= 80:  # 100-800 ms
            continue
        level = float(np.max(env[a:b]))
        if not -55.0 <= level <= -30.0:
            continue
        near_speech = (a > 0 and not quiet[max(0, a - 30) : a].all()) or (
            b < len(env) - 1 and not quiet[b + 1 : min(len(env), b + 31)].all()
        )
        if not near_speech:
            continue
        seg = samples[a * frame_len : (b + 1) * frame_len]
        broadband = (
            _band_energy_db(seg, sr, 1000.0, 8000.0)
            - _band_energy_db(seg, sr, 100.0, 1000.0)
        ) > 0.0
        if broadband:
            regions.append((a * frame_len / sr, (b + 1) * frame_len / sr))
    return regions


def click_regions(samples: np.ndarray, sr: int) -> list[tuple[float, float]]:
    """Click transient regions in seconds (5-40 ms, 2-6 kHz spike vs local median)."""
    from scipy.ndimage import median_filter

    short_len = sr * 2 // 1000
    n_short = len(samples) // short_len
    if n_short < 32:
        return []
    short = samples[: n_short * short_len].reshape(n_short, short_len).astype(np.float64)
    spec = np.abs(np.fft.rfft(short, axis=1)) ** 2
    freqs = np.fft.rfftfreq(short_len, 1.0 / sr)
    band = (freqs >= 2000.0) & (freqs < 6000.0)
    band_energy = 10.0 * np.log10(spec[:, band].sum(axis=1) + 1e-30)
    baseline = median_filter(band_energy, size=251, mode="nearest")
    spikes = (band_energy - baseline > 12.0) & (band_energy > -50.0)
    regions: list[tuple[float, float]] = []
    run_start: int | None = None
    for i, flag in enumerate(np.concatenate([spikes, [False]])):
        if flag and run_start is None:
            run_start = i
        elif not flag and run_start is not None:
            ms = (i - run_start) * 2
            if 5 <= ms <= 40:
                regions.append(
                    (run_start * short_len / sr, i * short_len / sr)
                )
            run_start = None
    return regions


def plosive_regions(samples: np.ndarray, sr: int, mask: np.ndarray) -> list[tuple[float, float]]:
    """Plosive onset regions in seconds (burst <150 Hz at speech onsets)."""
    frame_len = sr * 10 // 1000
    mask10 = _mask_to_10ms(mask, len(samples) // frame_len)
    regions: list[tuple[float, float]] = []
    for start, end in _speech_runs(mask10):
        onset = samples[start * frame_len : min((start + 5) * frame_len, len(samples))]
        if len(onset) < frame_len:
            continue
        lf = _band_energy_db(onset, sr, 20.0, 150.0)
        mid = _band_energy_db(onset, sr, 150.0, 1000.0)
        if lf - mid > 6.0:
            regions.append((start * frame_len / sr, min((start + 5) * frame_len, len(samples)) / sr))
    return regions


def _breath_detection(samples: np.ndarray, sr: int, mask: np.ndarray) -> int:
    """Number of breath candidates (see :func:`breath_regions`)."""
    return len(breath_regions(samples, sr))


def _click_candidates(samples: np.ndarray, sr: int, mask: np.ndarray) -> dict:
    """Mouth-click candidates (see :func:`click_regions`)."""
    events = click_regions(samples, sr)
    confidence = float(np.clip(0.3 + 0.05 * len(events), 0.3, 0.9))
    return {"count": len(events), "confidence": confidence}


def _plosive_candidates(samples: np.ndarray, sr: int, mask: np.ndarray) -> dict:
    """Plosive candidates (see :func:`plosive_regions`)."""
    regions = plosive_regions(samples, sr, mask)
    confidence = 0.0 if not regions else float(np.clip(0.4 + 0.1 * len(regions), 0.4, 0.9))
    return {"candidates": len(regions), "confidence": confidence}


def _noise_type(samples: np.ndarray, sr: int, mask: np.ndarray, hum: dict) -> dict:
    """Heuristic noise-type classification (Track 1B, 11 types, no ML yet)."""
    env = _frame_rms_db(samples, sr, 30)
    speech_ratio = float(mask.mean()) if len(mask) else 0.0
    active = env[np.isfinite(env)]
    stationary = bool(len(active) > 4 and float(np.std(active) / (np.abs(np.mean(active)) + 1e-9)) < 0.35)

    flat = _spectral_flatness_db(samples, sr, 100.0, 10000.0)
    broadband = bool(flat > -14.0)
    rumble = _band_energy_db(samples, sr, 20.0, 70.0)

    # Tonal dominance: strongest spectral peak vs median spectrum.
    spec = np.abs(np.fft.rfft(samples.astype(np.float64))) ** 2
    freqs = np.fft.rfftfreq(len(samples), 1.0 / sr)
    mid = (freqs >= 100.0) & (freqs < 10000.0)
    p = spec[mid] + 1e-30
    tonal = bool(float(np.max(p) / np.median(p)) > 10.0)  # > 10 dB peak dominance

    hum_strong = any(
        hum.get(k) is not None and hum.get(k) > -45.0 and hum.get(k) > hum.get("h50", -np.inf) - 6.0
        for k in ("h50", "h100", "h150")
    )

    confidence = 0.55
    if hum_strong:
        kind, confidence = "hum", 0.8
    elif tonal and stationary:
        kind, confidence = "fan", 0.7
    elif broadband and stationary:
        kind, confidence = ("ac" if rumble > -40.0 else "hiss"), 0.65
    elif speech_ratio < 0.1 and _click_candidates(samples, sr, mask)["count"] >= 8:
        kind, confidence = "keyboard", 0.7
    elif not stationary:
        if broadband and rumble > -40.0:
            kind, confidence = "traffic", 0.6
        elif speech_ratio > 0.5:
            kind, confidence = "people", 0.6
        elif tonal:
            kind, confidence = "music", 0.55
        else:
            kind, confidence = "non-stationary", 0.5
    elif stationary:
        kind, confidence = "stationary", 0.5
    else:
        kind, confidence = "unknown", 0.3

    return {
        "type": kind,
        "confidence": confidence,
        "stationary": stationary,
        "broadband": broadband,
        "tonal": tonal,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze(input_path: str, device: str = "auto", verbose: bool = False) -> dict:
    """Analyze ``input_path`` and return the full report dict (never modifies audio)."""
    t0 = time.perf_counter()
    resolved_device = resolve_device(device, probe=False)

    data = audioio.load_audio(input_path)
    x, sr = data.samples, audioio.INTERNAL_SAMPLE_RATE
    mask = speech_mask(x, sr)

    hum = _hum_analysis(x, sr)
    report: dict = {
        "input": {
            "format": data.source_format,
            "sample_rate": data.source_sample_rate,
            "channels": data.source_channels,
            "bit_depth": data.source_bit_depth,
            "duration_s": data.duration_s,
        },
        "loudness": _loudness_metrics(x, sr),
        "voice": {
            "speech_ratio": float(mask.mean()) if len(mask) else 0.0,
            "snr_db": _snr_estimate(x, mask),
            "intelligibility_proxy": _intelligibility_proxy(x, sr),
        },
        "spectral": {
            "rumble_db": _band_energy_db(x, sr, 20.0, 70.0),
            "hum_db": hum,
            "mud_db": _band_energy_db(x, sr, 100.0, 300.0),
            "boxiness_db": _band_energy_db(x, sr, 300.0, 600.0),
            "presence_db": _band_energy_db(x, sr, 2000.0, 5000.0),
            "air_db": _band_energy_db(x, sr, 8000.0, 14000.0),
        },
        "room": _rt60_estimate(x, sr, mask),
        "artifacts": {
            "dc_offset_db": 20.0 * np.log10(abs(float(np.mean(x))) + 1e-12),
            "plosives": _plosive_candidates(x, sr, mask),
            "breaths": {"count": _breath_detection(x, sr, mask),
                        "note": "se preservan por defecto"},
            "mouth_click_candidates": _click_candidates(x, sr, mask),
            "noise_type": _noise_type(x, sr, mask, hum),
        },
        "system": system_block(
            device=resolved_device,
            sample_rate=sr,
            processing_time_s=time.perf_counter() - t0,
        ),
    }
    return report


def _intelligibility_proxy(samples: np.ndarray, sr: int) -> dict:
    """Presence/mud band-ratio mapped to 0-1 (proxy, not STOI)."""
    presence = _band_energy_db(samples, sr, 2000.0, 5000.0)
    mud = _band_energy_db(samples, sr, 100.0, 300.0)
    ratio_db = presence - mud
    value = float(1.0 / (1.0 + np.exp(-ratio_db / 6.0)))
    return {
        "value": round(value, 4),
        "note": "presence/mud band-ratio — proxy, no STOI",
    }


def quick_metrics(samples: np.ndarray, sr: int = audioio.INTERNAL_SAMPLE_RATE) -> dict:
    """Light metric set for dry-run plans (SNR, LUFS, reverb, clipping)."""
    mask = speech_mask(samples, sr)
    env = _frame_rms_db(samples, sr)
    mask10 = _mask_to_10ms(mask, len(env))
    if mask10.any() and (~mask10).any():
        sp = 10.0 ** (env[mask10] / 10.0)
        np_ = 10.0 ** (env[~mask10] / 10.0)
        snr = 10.0 * np.log10((sp.mean() + 1e-12) / (np_.mean() + 1e-12))
    else:
        snr = None
    import pyloudnorm as pyln

    measured = pyln.Meter(sr).integrated_loudness(samples)
    room = _rt60_estimate(samples, sr, mask)
    return {
        "snr_db": None if snr is None else float(np.clip(snr, -10.0, 40.0)),
        "lufs": measured if np.isfinite(measured) else None,
        "reverb": room["reverb"],
        "clipping_ratio": float(np.mean(np.abs(samples) >= 0.999)),
    }
