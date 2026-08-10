"""Vocal DSP: filters, presets and the frozen mastering pipeline (Tracks 1/1B)."""

from voxera.dsp.pipeline import (
    STAGE_COMP,
    STAGE_DC,
    STAGE_DEESSER,
    STAGE_DEHUM,
    STAGE_EQ,
    STAGE_HIGHPASS,
    STAGE_LIMIT,
    STAGE_LOUDNORM,
    master,
    plan_stages,
)
from voxera.dsp.presets import DEFAULT_PRESET, PRESETS, preset_names, resolve_preset

__all__ = [
    "STAGE_COMP",
    "STAGE_DC",
    "STAGE_DEESSER",
    "STAGE_DEHUM",
    "STAGE_EQ",
    "STAGE_HIGHPASS",
    "STAGE_LIMIT",
    "STAGE_LOUDNORM",
    "DEFAULT_PRESET",
    "PRESETS",
    "master",
    "plan_stages",
    "preset_names",
    "resolve_preset",
]
