"""Device policy (Track 1A): ``--device auto|cpu|cuda``.

``auto`` means CUDA when a CUDA-enabled torch is importable, else CPU. Probing
torch costs seconds on this machine, so pure-DSP commands (analyze/master) skip
the probe unless the user explicitly asks for ``cuda``; only NN commands
(enhance) probe by default.
"""

from __future__ import annotations

from voxera.errors import EnhancementError

DEVICES = ("auto", "cpu", "cuda")


def _cuda_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:  # noqa: BLE001 - any torch failure means no CUDA
        return False


def resolve_device(request: str = "auto", *, probe: bool = True) -> str:
    """Resolve a device request to ``"cuda"`` or ``"cpu"``.

    Parameters
    ----------
    request:
        ``auto`` (default), ``cpu`` or ``cuda``.
    probe:
        When False, ``auto`` resolves to ``cpu`` without importing torch —
        used by pure-DSP commands where the device cannot matter.
    """
    if request not in DEVICES:
        raise EnhancementError(f"invalid device: {request} (expected auto|cpu|cuda)")
    if request == "cpu":
        return "cpu"
    if request == "cuda":
        if not _cuda_available():
            raise EnhancementError(
                "device 'cuda' requested but CUDA torch is not available; "
                "use --device cpu or install a CUDA-enabled torch"
            )
        return "cuda"
    # auto
    if not probe:
        return "cpu"
    return "cuda" if _cuda_available() else "cpu"
