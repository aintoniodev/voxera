"""The backend-agnostic enhance() contract (Track 1).

Two paths, frozen by spec:

- **Legacy** (``preset=None`` and not ``dsp_only``): backend-only enhancement,
  back-compat with phase 1 — the backend reads/writes the file and the CLI
  stays a thin adapter.
- **Pipeline** (``--preset X`` or ``--dsp-only``): format policy (48 kHz mono,
  PCM 24-bit out), VOXERA_NO_SPEECH gate, and **always** the full master
  pipeline after the backend. ``--dry-run`` prints the plan and writes
  nothing / loads no NN.
"""

from __future__ import annotations

import os
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

from voxera import audioio
from voxera.backends import get_backend, list_backends
from voxera.device import resolve_device
from voxera.dsp import DEFAULT_PRESET, master, plan_stages, resolve_preset
from voxera.errors import EnhancementError, UnknownBackendError
from voxera.master import build_plan
from voxera.vad import require_speech

SUPPORTED_EXTENSIONS = frozenset({".wav"})

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TMP_DIR = PROJECT_ROOT / "tmp"


def _require_readable_wav(input_path: Path) -> None:
    """Validate that ``input_path`` is a non-empty, readable WAV file."""
    try:
        with wave.open(str(input_path), "rb") as wav:
            if wav.getnframes() == 0:
                raise EnhancementError(f"empty audio: {input_path} contains no frames")
    except EnhancementError:
        raise
    except (wave.Error, EOFError, OSError) as exc:
        raise EnhancementError(f"invalid wav file: {input_path}") from exc


def _validate_input(inp: Path) -> None:
    """Raise :class:`EnhancementError` for unusable ``inp`` paths."""
    if not inp.exists():
        raise EnhancementError(f"no such file: {inp}")
    if inp.is_dir():
        raise EnhancementError(f"input is a directory: {inp}")
    if inp.suffix.lower() not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise EnhancementError(f"unsupported format: {inp.suffix} (supported: {supported})")
    _require_readable_wav(inp)


def _resolve_backend(
    backend: str,
    model: str | None,
    attn_limit_db: float | None,
    pf: bool | None,
    seed: int | None,
):
    kwargs: dict[str, object] = {}
    if model is not None:
        kwargs["model"] = model
    if attn_limit_db is not None:
        kwargs["attn_limit_db"] = attn_limit_db
    if pf is not None:
        kwargs["pf"] = pf
    if seed is not None:
        kwargs["seed"] = seed
    impl = get_backend(backend, **kwargs)
    if impl is None:
        available = ", ".join(list_backends())
        raise UnknownBackendError(f"unknown backend: {backend} (available: {available})")
    return impl


def _enhance_pipeline(
    inp: Path,
    out: Path,
    *,
    backend: str,
    model: str | None,
    attn_limit_db: float | None,
    pf: bool | None,
    preset_name: str,
    dsp_only: bool,
    dry_run: bool,
    device: str,
    seed: int | None,
) -> dict:
    """Pipeline path: format policy + no-speech gate + NN + master + 24-bit out."""
    resolved_device = resolve_device(device, probe=not dsp_only)
    t0 = time.perf_counter()

    data = audioio.load_audio(inp)
    sr = audioio.INTERNAL_SAMPLE_RATE
    speech_ratio = require_speech(data.samples, sr)

    stages = plan_stages(preset_name)
    if dry_run:
        return {
            "output": None,
            "plan": build_plan(
                data.samples, sr, preset_name, include_nn=not dsp_only
            ),
            "stages": stages,
            "speech_ratio": speech_ratio,
            "rtf_e2e": time.perf_counter() - t0,
            "preset": preset_name,
            "device": resolved_device,
        }

    if dsp_only:
        y, ran_stages = master(data.samples, sr, preset_name)
        resolved_model = None
    else:
        impl = _resolve_backend(backend, model, attn_limit_db, pf, seed)
        resolved_model = model or getattr(impl, "model", None)
        t_model = time.perf_counter()
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(suffix=".wav", dir=str(TMP_DIR))
        os.close(fd)
        tmp_path = Path(tmp_name)
        try:
            impl.enhance(inp, tmp_path)
            nn_data = audioio.load_audio(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)
        rtf_model = time.perf_counter() - t_model
        y, ran_stages = master(nn_data.samples, sr, preset_name)

    audioio.write_wav(out, y, sr)
    rtf_pipeline = time.perf_counter() - t0

    from voxera.dsp.filters import true_peak_db
    import pyloudnorm as pyln

    measured = pyln.Meter(sr).integrated_loudness(y)
    result: dict = {
        "output": out,
        "stages": ran_stages,
        "speech_ratio": speech_ratio,
        "lufs_out": measured if np.isfinite(measured) else None,
        "true_peak_out": true_peak_db(y),
        "duration_s": len(y) / sr,
        "rtf_pipeline": rtf_pipeline,
        "rtf_e2e": time.perf_counter() - t0,
        "preset": preset_name,
        "device": resolved_device,
        "backend": None if dsp_only else backend,
        "model": None if dsp_only else resolved_model,
    }
    if not dsp_only:
        result["rtf_model"] = rtf_model
    return result


def enhance(
    input_path: str | Path,
    output_path: str | Path,
    backend: str = "deepfilternet",
    model: str | None = None,
    attn_limit_db: float | None = None,
    pf: bool | None = None,
    *,
    preset: str | None = None,
    dsp_only: bool = False,
    dry_run: bool = False,
    device: str = "auto",
    seed: int | None = None,
) -> Path | dict:
    """Enhance ``input_path`` and write the improved audio to ``output_path``.

    Parameters
    ----------
    input_path:
        Path to the source audio file (WAV, non-empty).
    output_path:
        Where the enhanced audio is written.
    backend:
        Name of the pluggable backend engine (default ``deepfilternet``); the
        core validates the name.
    model / attn_limit_db / pf:
        Optional per-run backend tuning; ``None`` keeps backend defaults.
    preset:
        Preset name. When set, **always** runs the full master pipeline after
        the backend (never NN-only silently); default preset: ``creator``.
    dsp_only:
        Pipeline without any neural network (``master`` puro).
    dry_run:
        Print the plan and exit 0 without writing OUT or loading the NN.
    device:
        ``auto`` (default), ``cpu`` or ``cuda``.
    seed:
        Optional inference seed (determinism on CPU).
    """
    inp = Path(input_path)
    out = Path(output_path)

    if preset is not None or dsp_only:
        return _enhance_pipeline(
            inp,
            out,
            backend=backend,
            model=model,
            attn_limit_db=attn_limit_db,
            pf=pf,
            preset_name=preset or DEFAULT_PRESET,
            dsp_only=dsp_only,
            dry_run=dry_run,
            device=device,
            seed=seed,
        )

    # --- legacy path (back-compat: backend-only, no format policy) ---
    _validate_input(inp)
    impl = _resolve_backend(backend, model, attn_limit_db, pf, seed)
    impl.enhance(inp, out)
    if not out.exists():
        raise EnhancementError(f"backend '{backend}' did not produce output: {out}")
    return out
