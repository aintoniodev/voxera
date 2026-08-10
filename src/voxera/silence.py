"""``voxera silence`` — VAD + silence trimming + breath/click handling (Track 2).

Rules (docs/SPECS-fase2.md, Track 2):

- light: gaps > 1.5 s -> 0.8 s · medium: > 0.8 s -> 0.5 s · aggressive: > 0.4 s -> 0.25 s.
- A 200 ms margin around every speech segment guarantees breaths are never cut;
  short gaps (<= 300 ms) are never touched.
- ``--breaths preserve`` (default) / ``attenuate`` (-6 dB) / ``remove`` — per Track 1B.
- ``--declick`` attenuates 5-40 ms 2-6 kHz transients by -6 dB.
- 2 ms fades at every cut to avoid clicks.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from voxera import audioio
from voxera.analyze import breath_regions, click_regions
from voxera.device import resolve_device
from voxera.errors import EnhancementError
from voxera.vad import require_speech, speech_mask

LEVELS = {
    "light": (1.5, 0.8),
    "medium": (0.8, 0.5),
    "aggressive": (0.4, 0.25),
}
MARGIN_S = 0.2
BREATH_HANDLING = ("preserve", "attenuate", "remove")
BREATH_ATTENUATE_DB = -6.0
CLICK_ATTENUATE_DB = -6.0
FADE_MS = 2.0
SR = audioio.INTERNAL_SAMPLE_RATE


def _apply_gain_region(x: np.ndarray, start: int, end: int, gain_db: float, fade_ms: float) -> np.ndarray:
    """Apply ``gain_db`` over [start, end) with linear fades at both edges."""
    gain = 10.0 ** (gain_db / 20.0)
    if gain == 1.0:
        return x
    fade = int(SR * fade_ms / 1000.0)
    n = end - start
    if n <= 0:
        return x
    fade = min(fade, n // 2)
    env = np.full(n, gain, dtype=np.float64)
    if fade > 0:
        ramp = np.linspace(1.0, gain, fade)
        env[:fade] = ramp
        env[-fade:] = ramp[::-1]
    y = x.copy()
    y[start:end] = y[start:end] * env
    return y


def _remove_region(x: np.ndarray, start: int, end: int, fade_ms: float) -> np.ndarray:
    """Cut [start, end) with short fades at the boundaries."""
    fade = int(SR * fade_ms / 1000.0)
    fade = min(fade, (end - start) // 2)
    y = np.concatenate([x[:start], x[end:]])
    if fade > 0:
        # fade out the tail of the kept-left part and in the kept-right part
        left = y[max(0, start - fade) : start]
        right = y[start : start + fade]
        y[max(0, start - fade) : start] = left * np.linspace(1.0, 0.0, len(left))
        y[start : start + fade] = right * np.linspace(0.0, 1.0, len(right))
    return y


def _envelope_segments_samples(samples: np.ndarray) -> list[tuple[int, int]]:
    """Speech segments in samples via relative envelope threshold.

    webrtcvad is unreliable at gap level (it flags noise floors as speech), so
    Track 2 segments on the 30 ms RMS envelope: active = env above
    ``max(-50, p75(env) - 12)`` dBFS. Segments are expanded by the 200 ms
    breath-protection margin and merged.
    """
    frame_ms = 30
    frame_len = int(SR * frame_ms / 1000)
    n = len(samples) // frame_len
    if n == 0:
        return []
    frames = samples[: n * frame_len].reshape(n, frame_len).astype(np.float64)
    env = 20.0 * np.log10(np.sqrt((frames**2).mean(axis=1)) + 1e-12)
    speech_level = float(np.percentile(env, 75))
    threshold = max(-50.0, speech_level - 12.0)
    active = env > threshold

    margin = int(MARGIN_S * SR / frame_len)
    runs: list[tuple[int, int]] = []
    start = None
    for i, flag in enumerate(np.concatenate([[False], active, [False]])):
        if flag and start is None:
            start = i - 1
        elif not flag and start is not None:
            runs.append((start - 1, i - 2))
            start = None
    expanded: list[tuple[int, int]] = []
    for a, b in runs:
        ea, eb = max(0, a - margin), min(b + margin, n - 1)
        if expanded and ea <= expanded[-1][1]:
            expanded[-1] = (expanded[-1][0], max(expanded[-1][1], eb))
        else:
            expanded.append((ea, eb))
    return [(a * frame_len, min((b + 1) * frame_len, len(samples))) for a, b in expanded]


def trim_gaps(
    samples: np.ndarray,
    mask: np.ndarray,
    level: str = "medium",
) -> np.ndarray:
    """Trim over-long gaps between speech segments (never cutting breaths)."""
    if level not in LEVELS:
        raise EnhancementError(f"invalid silence level: {level} (light|medium|aggressive)")
    trigger_s, target_s = LEVELS[level]
    segments = _envelope_segments_samples(samples)

    # gap regions: leading, between, trailing
    gaps: list[tuple[int, int]] = []
    prev = 0
    for a, b in segments:
        gaps.append((prev, a))
        prev = b
    gaps.append((prev, len(samples)))

    trigger = int(trigger_s * SR)
    target = int(target_s * SR)

    def _trim_gap(a: int, b: int) -> tuple[int, int]:
        if b - a <= trigger:
            return (a, b)
        return (a, a + target)

    parts: list[tuple[int, int]] = []
    prev = 0
    for a, b in segments:
        parts.append(_trim_gap(prev, a))  # gap before this segment
        parts.append((a, b))  # speech segment: always kept whole
        prev = b
    parts.append(_trim_gap(prev, len(samples)))  # trailing gap

    # 2 ms fades at every cut boundary (non-adjacent parts)
    out_parts: list[np.ndarray] = []
    for i, (a, b) in enumerate(parts):
        if b <= a:
            continue
        seg = samples[a:b].copy()
        fade = min(int(SR * FADE_MS / 1000.0), (b - a) // 2)
        if i > 0 and parts[i - 1][1] != a and fade:
            seg[:fade] *= np.linspace(0.0, 1.0, fade)
        if i < len(parts) - 1 and parts[i + 1][0] != b and fade:
            seg[-fade:] *= np.linspace(1.0, 0.0, fade)
        out_parts.append(seg)
    return np.concatenate(out_parts).astype(np.float32) if out_parts else samples.astype(np.float32)


def silence_file(
    input_path: str | Path,
    output_path: str | Path,
    level: str = "medium",
    breaths: str = "preserve",
    declick: bool = False,
    device: str = "auto",
) -> dict:
    """Trim silence from ``input_path`` -> ``output_path`` (Track 2).

    Returns ``{output, duration_in_s, duration_out_s, speech_ratio_in,
    speech_ratio_out, breaths_handled, level, system}``.
    """
    if breaths not in BREATH_HANDLING:
        raise EnhancementError(
            f"invalid --breaths value: {breaths} (preserve|attenuate|remove)"
        )
    resolved_device = resolve_device(device, probe=False)
    t0 = time.perf_counter()

    data = audioio.load_audio(input_path)
    x = data.samples
    ratio_in = require_speech(x, SR)
    mask = speech_mask(x, SR)

    # breath / click processing happens BEFORE trimming so regions stay valid.
    if breaths in ("attenuate", "remove") or declick:
        for start_s, end_s in breath_regions(x, SR) if breaths != "preserve" else []:
            a, b = int(start_s * SR), int(end_s * SR)
            if breaths == "attenuate":
                x = _apply_gain_region(x, a, b, BREATH_ATTENUATE_DB, 20.0)
            else:  # remove
                x = _remove_region(x, a, b, 5.0)
        for start_s, end_s in click_regions(x, SR) if declick else []:
            a, b = int(start_s * SR), int(end_s * SR)
            x = _apply_gain_region(x, a, b, CLICK_ATTENUATE_DB, 3.0)

    # re-run VAD on the processed signal so trimming reflects it
    mask = speech_mask(x, SR)
    out = trim_gaps(x, mask, level)
    ratio_out = float(speech_mask(out, SR).mean()) if len(out) else 0.0

    audioio.write_wav(output_path, out, SR)
    return {
        "output": Path(output_path),
        "duration_in_s": len(x) / SR,
        "duration_out_s": len(out) / SR,
        "speech_ratio_in": ratio_in,
        "speech_ratio_out": ratio_out,
        "breaths_handled": breaths,
        "level": level,
        "device": resolved_device,
        "processing_time_s": time.perf_counter() - t0,
    }
