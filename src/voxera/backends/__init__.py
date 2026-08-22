"""Backend registry: name -> backend implementation.

The registry is the single seam where concrete neural-network engines plug
into the core. The CLI exposes only registered backends, so the contract and
the user interface can never drift apart.
"""

from __future__ import annotations

from voxera.backends.base import Backend
from voxera.backends.deepfilternet import DeepFilterNetBackend
from voxera.backends.dpdfnet import DpdfNetBackend

BACKENDS: dict[str, type[Backend]] = {
    DeepFilterNetBackend.name: DeepFilterNetBackend,
    DpdfNetBackend.name: DpdfNetBackend,
}


def get_backend(name: str, **kwargs) -> Backend | None:
    """Return the backend instance for ``name``, or ``None`` if unknown.

    Extra ``kwargs`` are forwarded to the backend constructor (per-run tuning).
    """
    cls = BACKENDS.get(name)
    return cls(**kwargs) if cls is not None else None


def list_backends() -> list[str]:
    """Return registered backend names in stable order."""
    return sorted(BACKENDS)


__all__ = ["Backend", "get_backend", "list_backends", "BACKENDS"]
