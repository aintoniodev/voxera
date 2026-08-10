"""Determinism + provenance helpers (Track 1A).

Frozen contract (docs/SPECS-fase2.md, Track 1A):

- Report JSON is stable for CI: sorted keys, floats rounded to fixed
  precision, no UUIDs or variable timestamps. The single exception is
  ``processing_time_s`` (system block), reported but excluded from the
  stability diff.
- Every report carries a ``system`` provenance block.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from voxera import __version__

FLOAT_DIGITS = 4
PIPELINE_VERSION = "1.0.0"

STABLE_KEYS = ("system",)  # system block is emitted by callers; sorted anyway


def stable_round(value):
    """Recursively round floats to the fixed report precision."""
    if isinstance(value, float):
        return round(value, FLOAT_DIGITS)
    if isinstance(value, dict):
        return {k: stable_round(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [stable_round(v) for v in value]
    return value


def dump_report(report: dict) -> str:
    """Serialize a report deterministically (sorted keys, fixed precision)."""
    return (
        json.dumps(
            stable_round(report),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    )


def model_fingerprint(model_dir: str | Path) -> str:
    """Cheap stable fingerprint of a model directory.

    Full-file hashing of a multi-hundred-MB model per run is too slow; we hash
    the (relative path, size) manifest, which changes whenever the model
    changes. Format: ``sha256:<hex>``.
    """
    root = Path(model_dir)
    if not root.is_dir():
        return "sha256:none"
    manifest = sorted(
        f"{p.relative_to(root)}:{p.stat().st_size}" for p in root.rglob("*") if p.is_file()
    )
    digest = hashlib.sha256("\n".join(manifest).encode("utf-8")).hexdigest()[:16]
    return f"sha256:{digest}"


def system_block(
    *,
    device: str = "cpu",
    seed: int | None = None,
    preset: str | None = None,
    sample_rate: int = 48000,
    backend: str | None = None,
    model: str | None = None,
    model_dir: str | Path | None = None,
    processing_time_s: float | None = None,
) -> dict:
    """Build the provenance block present in every report."""
    block: dict = {
        "voxera_version": __version__,
        "pipeline_version": PIPELINE_VERSION,
        "device": device,
        "sample_rate": sample_rate,
    }
    if seed is not None:
        block["seed"] = seed
    if preset is not None:
        block["preset"] = preset
    if backend is not None:
        block["backend"] = backend
    if model is not None:
        block["model"] = model
    if model_dir is not None:
        block["model_hash"] = model_fingerprint(model_dir)
    if processing_time_s is not None:
        block["processing_time_s"] = processing_time_s
    return block
