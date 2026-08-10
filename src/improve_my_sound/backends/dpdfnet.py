"""Default backend: dpdfnet.

This is an adapter shell for the environmental dpdfnet engine (package
``dpdfnet``, which pulls a neural model and torch runtime). Keeping it behind
the :class:`Backend` contract keeps the core testable without the engine.

The engine wiring is implemented per the Feature 1 acceptance spec; until the
spec lands, the adapter fails with a clear, user-facing message.
"""

from __future__ import annotations

from pathlib import Path

from improve_my_sound.backends.base import Backend
from improve_my_sound.errors import EnhancementError


class DpdfNetBackend(Backend):
    """Enhancement backend backed by the dpdfnet neural engine."""

    name = "dpdfnet"

    def enhance(self, input_path: Path, output_path: Path) -> Path:
        try:
            import dpdfnet  # noqa: F401
        except ImportError as exc:
            raise EnhancementError(
                "backend 'dpdfnet' is unavailable: install the 'dpdfnet' package"
            ) from exc
        raise EnhancementError(
            "backend 'dpdfnet' engine wiring is not implemented yet"
        )
