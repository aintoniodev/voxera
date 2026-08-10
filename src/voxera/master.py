"""``voxera master`` — voice mastering ONLY (Track 1).

Runs the frozen DSP pipeline with a preset, no neural network. Pure DSP must
be byte-equivalent for the same input+parameters (Track 1A determinism).
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from voxera import audioio
from voxera.analyze import quick_metrics
from voxera.device import resolve_device
from voxera.dsp import DEFAULT_PRESET, master, plan_stages, resolve_preset
from voxera.errors import EnhancementError
from voxera.vad import require_speech


def build_plan(
    samples: np.ndarray,
    sample_rate: int,
    preset_name: str,
    *,
    include_nn: bool,
    lufs: float | None = None,
    dehum_hz: int | None = None,
    no_eq: bool = False,
    no_comp: bool = False,
    no_limit: bool = False,
    no_loudnorm: bool = False,
) -> str:
    """The ``VOXERA PLAN`` dry-run text (spec Track 1). Never writes or loads NN."""
    preset = resolve_preset(preset_name)
    m = quick_metrics(samples, sample_rate)
    target = preset.lufs if lufs is None else lufs

    snr = m["snr_db"]
    lufs = m["lufs"]
    lines = ["VOXERA PLAN", ""]
    lines.append("Input:")
    lines.append(f"  SNR:       {snr:5.1f} dB" if snr is not None else "  SNR:        n/a")
    lines.append(f"  LUFS:     {lufs:6.1f}" if lufs is not None else "  LUFS:        n/a")
    lines.append(f"  Reverb:    {m['reverb']}")
    lines.append(f"  Clipping: {m['clipping_ratio'] * 100:.1f}%")
    lines.append("")
    lines.append("Pipeline:")
    if include_nn:
        lines.append("  ✓ DeepFilterNet2")
    for stage in plan_stages(
        preset_name,
        dehum_hz=dehum_hz,
        no_eq=no_eq,
        no_comp=no_comp,
        no_limit=no_limit,
        no_loudnorm=no_loudnorm,
    ):
        lines.append(f"  ✓ {stage}")
    lines.append("")
    lines.append("Expected:")
    noise_arrows = "↓↓↓" if (snr is not None and snr < 8) else ("↓↓" if snr is not None and snr < 15 else "↓")
    clarity_arrows = "↑↑" if (snr is not None and snr >= 8) else "↑"
    loud_arrows = "↑↑" if (lufs is not None and lufs < target - 3) else "↑"
    lines.append(f"  Noise       {noise_arrows}")
    lines.append(f"  Clarity     {clarity_arrows}")
    lines.append(f"  Loudness    {loud_arrows}")
    return "\n".join(lines)


def master_file(
    input_path: str | Path,
    output_path: str | Path,
    preset_name: str = DEFAULT_PRESET,
    *,
    lufs: float | None = None,
    dehum_hz: int | None = None,
    no_eq: bool = False,
    no_comp: bool = False,
    no_limit: bool = False,
    no_loudnorm: bool = False,
    device: str = "auto",
    dry_run: bool = False,
) -> dict:
    """Master ``input_path`` -> ``output_path``; returns a result dict.

    Result keys: ``output``, ``stages``, ``speech_ratio``, ``lufs_out``,
    ``true_peak_out``, ``duration_s``, ``rtf_master`` (DSP only),
    ``rtf_pipeline`` (DSP + I/O + resample). With ``dry_run=True`` the result
    carries ``plan`` and writes nothing.
    """
    inp = Path(input_path)
    out = Path(output_path)
    resolved_device = resolve_device(device, probe=False)
    t0 = time.perf_counter()

    data = audioio.load_audio(inp)
    sr = audioio.INTERNAL_SAMPLE_RATE
    speech_ratio = require_speech(data.samples, sr)

    stages = plan_stages(
        preset_name,
        dehum_hz=dehum_hz,
        no_eq=no_eq,
        no_comp=no_comp,
        no_limit=no_limit,
        no_loudnorm=no_loudnorm,
    )

    if dry_run:
        return {
            "output": None,
            "plan": build_plan(
                data.samples, sr, preset_name,
                include_nn=False,
                lufs=lufs,
                dehum_hz=dehum_hz,
                no_eq=no_eq,
                no_comp=no_comp,
                no_limit=no_limit,
                no_loudnorm=no_loudnorm,
            ),
            "stages": stages,
            "speech_ratio": speech_ratio,
            "rtf_master": time.perf_counter() - t0,
        }

    t_dsp = time.perf_counter()
    y, ran_stages = master(
        data.samples, sr, preset_name,
        lufs=lufs,
        dehum_hz=dehum_hz,
        no_eq=no_eq,
        no_comp=no_comp,
        no_limit=no_limit,
        no_loudnorm=no_loudnorm,
    )
    rtf_master = time.perf_counter() - t_dsp

    audioio.write_wav(out, y, sr)
    rtf_pipeline = time.perf_counter() - t0

    from voxera.dsp.filters import true_peak_db
    import pyloudnorm as pyln

    measured = pyln.Meter(sr).integrated_loudness(y)
    return {
        "output": out,
        "stages": ran_stages,
        "speech_ratio": speech_ratio,
        "lufs_out": measured if np.isfinite(measured) else None,
        "true_peak_out": true_peak_db(y),
        "duration_s": len(y) / sr,
        "rtf_master": rtf_master,
        "rtf_pipeline": rtf_pipeline,
        "device": resolved_device,
    }
