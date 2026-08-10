"""The frozen voice-mastering pipeline (Track 1).

Order is frozen by spec (docs/SPECS-fase2.md, Track 1):

    DC removal -> high-pass (LR24, 70 Hz; 90 Hz for bad-room) -> [dehum]
    -> vocal EQ -> de-esser -> compressor -> limiter (-1 dBTP)
    -> loudnorm (target LUFS) + true-peak guard

Byte-equivalent deterministic on the frozen internal format (48 kHz mono
float32). ``master()`` returns the processed samples and the list of stages
that actually ran (for ``--dry-run`` plans and verbose reports).
"""

from __future__ import annotations

import time

import numpy as np

from voxera.dsp import filters
from voxera.dsp.presets import DEFAULT_PRESET, PRESETS, resolve_preset

# Stage labels used by dry-run plans and reports.
STAGE_DC = "DC removal"
STAGE_HIGHPASS = "High-pass"
STAGE_DEHUM = "De-hum"
STAGE_EQ = "Vocal EQ"
STAGE_DEESSER = "De-esser"
STAGE_COMP = "Compressor"
STAGE_LIMIT = "Limiter"
STAGE_LOUDNORM = "Loudness"


def plan_stages(
    preset_name: str = DEFAULT_PRESET,
    *,
    dehum_hz: int | None = None,
    no_eq: bool = False,
    no_comp: bool = False,
    no_limit: bool = False,
    no_loudnorm: bool = False,
) -> list[str]:
    """Stage list for a run, in frozen order (used by --dry-run)."""
    preset = resolve_preset(preset_name)
    stages = [STAGE_DC, f"{STAGE_HIGHPASS} {int(preset.highpass_hz)} Hz"]
    if dehum_hz:
        stages.append(f"{STAGE_DEHUM} {dehum_hz} Hz")
    if not no_eq:
        stages.append(STAGE_EQ)
        if preset.deesser:
            stages.append(STAGE_DEESSER)
    if not no_comp:
        stages.append(f"{STAGE_COMP} {preset.comp_ratio:g}:1")
    if not no_limit:
        stages.append(f"{STAGE_LIMIT} -1 dBTP")
    if not no_loudnorm:
        stages.append(f"{STAGE_LOUDNORM} -> {preset.lufs:g} LUFS")
    return stages


def master(
    samples: np.ndarray,
    sample_rate: int,
    preset_name: str = DEFAULT_PRESET,
    *,
    lufs: float | None = None,
    dehum_hz: int | None = None,
    no_eq: bool = False,
    no_comp: bool = False,
    no_limit: bool = False,
    no_loudnorm: bool = False,
    track_time: bool = False,
) -> tuple[np.ndarray, list[str]]:
    """Run the frozen DSP pipeline; returns ``(samples, stages)``."""
    preset = resolve_preset(preset_name)
    stages: list[str] = []
    t0 = time.perf_counter()

    x = filters.dc_block(samples, sample_rate)
    stages.append(STAGE_DC)
    x = filters.highpass_lr24(x, sample_rate, preset.highpass_hz)
    stages.append(f"{STAGE_HIGHPASS} {int(preset.highpass_hz)} Hz")

    if dehum_hz:
        x = filters.notch(x, sample_rate, float(dehum_hz))
        stages.append(f"{STAGE_DEHUM} {dehum_hz} Hz")

    if not no_eq:
        x = filters.vocal_eq(x, sample_rate, **preset.eq_params())
        stages.append(STAGE_EQ)
        if preset.deesser:
            x = filters.deesser(
                x, sample_rate, threshold_db=preset.deesser_threshold_db
            )
            stages.append(STAGE_DEESSER)

    if not no_comp:
        x = filters.compressor(
            x, sample_rate,
            threshold_db=preset.comp_threshold_db,
            ratio=preset.comp_ratio,
        )
        stages.append(f"{STAGE_COMP} {preset.comp_ratio:g}:1")

    if not no_limit:
        x = filters.limiter(x, sample_rate, threshold_db=-1.0)
        stages.append(f"{STAGE_LIMIT} -1 dBTP")

    if not no_loudnorm:
        target = preset.lufs if lufs is None else lufs
        x = filters.loudness_normalize(x, sample_rate, target)
        stages.append(f"{STAGE_LOUDNORM} -> {target:g} LUFS")

    _ = track_time, time.perf_counter() - t0  # timing handled by callers
    return x.astype(np.float32), stages
