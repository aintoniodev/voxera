"""The backend-agnostic enhance() contract.

The core is the source of truth and the primary interface: everything the CLI
does flows through :func:`enhance`. Backends plug in behind the contract, so
the neural-network engine is swappable without touching the core.
"""

from __future__ import annotations

import wave
from pathlib import Path

from improve_my_sound.backends import get_backend, list_backends
from improve_my_sound.errors import EnhancementError

SUPPORTED_EXTENSIONS = frozenset({".wav"})


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


def enhance(
    input_path: str | Path,
    output_path: str | Path,
    backend: str = "dpdfnet",
) -> Path:
    """Enhance ``input_path`` and write the improved audio to ``output_path``.

    Parameters
    ----------
    input_path:
        Path to the source audio file (WAV, non-empty).
    output_path:
        Where the enhanced audio is written.
    backend:
        Name of the pluggable backend engine (default ``dpdfnet``).

    Returns
    -------
    Path
        The resolved ``output_path`` on success.

    Raises
    ------
    EnhancementError
        For missing inputs, directories, unsupported formats, empty or
        invalid audio, unknown backends, or backend failures.
    """
    inp = Path(input_path)
    out = Path(output_path)

    _validate_input(inp)

    impl = get_backend(backend)
    if impl is None:
        available = ", ".join(list_backends())
        raise EnhancementError(f"unknown backend: {backend} (available: {available})")

    impl.enhance(inp, out)
    if not out.exists():
        raise EnhancementError(f"backend '{backend}' did not produce output: {out}")
    return out
