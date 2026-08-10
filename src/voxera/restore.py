"""``voxera restore`` — restoration heuristics (Track 5).

Spec (docs/SPECS-fase2.md, Track 5): restoration arrives after Tracks 1-3;
``analyze`` already detects clipping/RT60/plosives/hum so ``restore`` targets
what was measured. ML candidates (VoiceFixer/ClearerVoice) are evaluated in
the benchmark (Track 6); today everything here is deterministic DSP:

    declip (flat-top reconstruction via cubic interpolation)
    -> deplosive (LF burst reduction at speech onsets)
    -> dehum (narrow notch on the dominant mains harmonic)

An optional master preset can follow. Decision #11 (de-plosive + dehum in
Track 5) is implemented here.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from voxera import audioio
from voxera.analyze import plosive_regions
from voxera.device import resolve_device
from voxera.dsp import DEFAULT_PRESET, master
from voxera.dsp import filters as dsp_filters
from voxera.errors import EnhancementError
from voxera.vad import require_speech, speech_mask

SR = audioio.INTERNAL_SAMPLE_RATE
CLIP_THRESHOLD = 0.999


def declip(samples: np.ndarray, sr: int) -> np.ndarray:
    """Reconstruct hard-clipped flat-tops with cubic interpolation.

    Clipping is detected adaptively: runs of >= 2 samples at the file's
    peak ceiling whose values are an exact plateau (max-min < 1e-6). Natural
    signal peaks never form exact plateaus, so clean audio is untouched
    (bit-identical). Clipped runs are replaced by a cubic spline through the
    two surrounding anchor samples per side.
    """
    x = samples.astype(np.float64)
    ceiling = float(np.max(np.abs(x)))
    if ceiling < 0.05:
        return samples  # near-silence: nothing to reconstruct
    clip_level = 0.999 if ceiling > 0.999 else ceiling * (1.0 - 1e-4)
    at_ceiling = np.abs(x) >= clip_level
    if not at_ceiling.any():
        return samples

    from scipy.interpolate import CubicSpline

    y = x.copy()
    n = len(x)
    modified = False
    run_start: int | None = None
    for i, flag in enumerate(np.concatenate([at_ceiling, [False]])):
        if flag and run_start is None:
            run_start = i
        elif not flag and run_start is not None:
            a, b = run_start, i - 1  # inclusive run
            plateau = float(np.max(x[a : b + 1]) - np.min(x[a : b + 1])) < 1e-6
            if plateau and b - a >= 1 and a >= 2 and b <= n - 3:
                anchors_x = [a - 2, a - 1, b + 1, b + 2]
                anchors_y = [x[a - 2], x[a - 1], x[b + 1], x[b + 2]]
                spline = CubicSpline(anchors_x, anchors_y)
                region = np.arange(a, b + 1)
                y[a : b + 1] = np.clip(spline(region), -1.0, 1.0)
                modified = True
            run_start = None
    if not modified:
        return samples  # clean audio: bit-identical
    return y.astype(np.float32)


def deplosive(samples: np.ndarray, sr: int, mask: np.ndarray, amount: float = 0.6) -> np.ndarray:
    """Reduce low-frequency plosive bursts at speech onsets.

    For each plosive onset region, subtract ``amount`` of its < 150 Hz
    content with 5 ms fades. Deterministic; non-onset regions untouched.
    """
    from scipy.signal import butter, lfilter

    b, a = butter(2, 150.0 / (sr / 2.0), btype="low")
    regions = plosive_regions(samples, sr, mask)
    if not regions:
        return samples
    x = samples.astype(np.float64)
    for start_s, end_s in regions:
        start, end = int(start_s * sr), int(end_s * sr)
        lf = lfilter(b, a, x[start:end])
        fade = min(int(sr * 5 / 1000), (end - start) // 4)
        env = np.ones(end - start)
        if fade:
            env[:fade] = np.linspace(0.0, 1.0, fade)
            env[-fade:] = np.linspace(1.0, 0.0, fade)
        x[start:end] -= amount * lf * env
    return x.astype(np.float32)


def _clip_ratio(samples: np.ndarray, clip_level: float) -> float:
    return float(np.mean(np.abs(samples) >= clip_level))


def restore_file(
    input_path: str | Path,
    output_path: str | Path,
    *,
    do_declip: bool = False,
    do_deplosive: bool = False,
    dehum_hz: int | None = None,
    preset: str | None = None,
    lufs: float | None = None,
    device: str = "auto",
) -> dict:
    """Restore ``input_path`` -> ``output_path`` (Track 5).

    Returns ``{output, stages, clipping_ratio_in, clipping_ratio_out, ...}``.
    """
    if not (do_declip or do_deplosive or dehum_hz or preset):
        raise EnhancementError(
            "restore needs at least one of --declip, --deplosive, --dehum, --preset"
        )
    resolved_device = resolve_device(device, probe=False)
    t0 = time.perf_counter()

    data = audioio.load_audio(input_path)
    x = data.samples
    ratio = require_speech(x, SR)
    mask = speech_mask(x, SR)
    ceiling = float(np.max(np.abs(x)))
    clip_level = 0.999 if ceiling > 0.999 else ceiling * (1.0 - 1e-4)
    clip_in = _clip_ratio(x, clip_level)

    stages: list[str] = []
    if do_declip:
        x = declip(x, SR)
        stages.append("declip")
    if do_deplosive:
        x = deplosive(x, SR, mask)
        stages.append("deplosive")
    if dehum_hz:
        x = dsp_filters.notch(x, SR, float(dehum_hz))
        stages.append(f"dehum {dehum_hz} Hz")
    if preset:
        x, dsp_stages = master(x, SR, preset, lufs=lufs)
        stages.extend(dsp_stages)

    clip_out = _clip_ratio(x, clip_level)
    audioio.write_wav(output_path, x, SR)
    return {
        "output": Path(output_path),
        "stages": stages,
        "speech_ratio": ratio,
        "clipping_ratio_in": clip_in,
        "clipping_ratio_out": clip_out,
        "duration_s": len(x) / SR,
        "device": resolved_device,
        "processing_time_s": time.perf_counter() - t0,
    }
