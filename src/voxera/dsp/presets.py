"""Frozen voice presets (Track 1, spec table).

Parameters are frozen per preset and only change by spec revision. Presets
differ in LUFS target, vocal EQ, compressor and de-esser; ``bad-room`` also
moves the high-pass from 70 to 90 Hz.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from voxera.errors import EnhancementError


@dataclass(frozen=True)
class Preset:
    name: str
    lufs: float
    description: str
    highpass_hz: float = 70.0
    eq_mud_db: float = 0.0
    eq_boxiness_db: float = 0.0
    eq_presence_db: float = 0.0
    eq_air_db: float = 0.0
    comp_threshold_db: float = -24.0
    comp_ratio: float = 2.0
    deesser: bool = False
    deesser_threshold_db: float = -8.0

    def eq_params(self) -> dict[str, float]:
        return {
            "mud_db": self.eq_mud_db,
            "boxiness_db": self.eq_boxiness_db,
            "presence_db": self.eq_presence_db,
            "air_db": self.eq_air_db,
        }


PRESETS: dict[str, Preset] = {
    "creator": Preset(
        name="creator",
        lufs=-16.0,
        description="Natural + clear (default)",
        eq_mud_db=-2.0,
        comp_threshold_db=-24.0,
        comp_ratio=2.0,
        deesser=False,
    ),
    "youtube": Preset(
        name="youtube",
        lufs=-14.0,
        description="Warm + present",
        eq_presence_db=2.0,
        eq_air_db=1.0,
        comp_threshold_db=-24.0,
        comp_ratio=2.5,
        deesser=True,
    ),
    "podcast": Preset(
        name="podcast",
        lufs=-16.0,
        description="Rich + consistent",
        eq_mud_db=-3.0,
        eq_presence_db=1.0,
        comp_threshold_db=-24.0,
        comp_ratio=3.0,
        deesser=True,
    ),
    "social": Preset(
        name="social",
        lufs=-14.0,
        description="Loud + punchy (TT/IG)",
        eq_air_db=2.0,
        comp_threshold_db=-22.0,
        comp_ratio=3.5,
        deesser=True,
    ),
    "bad-room": Preset(
        name="bad-room",
        lufs=-16.0,
        description="Noise + echo: DF2 + high-pass 90 Hz",
        highpass_hz=90.0,
        eq_mud_db=-4.0,
        eq_boxiness_db=-2.0,
        comp_threshold_db=-24.0,
        comp_ratio=2.0,
        deesser=False,
    ),
}

DEFAULT_PRESET = "creator"


def preset_names() -> list[str]:
    return list(PRESETS)


def resolve_preset(name: str | None) -> Preset:
    """Resolve a preset name (default ``creator``); unknown names raise."""
    if name is None:
        name = DEFAULT_PRESET
    try:
        return PRESETS[name]
    except KeyError:
        available = ", ".join(preset_names())
        raise EnhancementError(f"unknown preset: {name} (available: {available})") from None
