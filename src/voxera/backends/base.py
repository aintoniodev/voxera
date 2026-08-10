"""Backend contract for the voxera enhancement engine.

Backends are pluggable neural-network engines. The core only depends on this
contract; model/parameter selection is an empirical decision driven by measured
quality-vs-RTF (see project metrics), never a hard code coupling.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class Backend(ABC):
    """A pluggable audio-enhancement engine.

    Implementations must be deterministic for a fixed input and write the
    enhanced audio to ``output_path`` before returning.
    """

    name: str = ""

    @abstractmethod
    def enhance(self, input_path: Path, output_path: Path) -> Path:
        """Enhance ``input_path`` and write the result to ``output_path``.

        Returns ``output_path`` on success. Raises :class:`EnhancementError`
        (from ``voxera.enhance``) on failure.
        """
