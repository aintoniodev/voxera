"""Default backend: dpdfnet.

Adapter for the ``dpdfnet`` package (ONNX-based, real-time CPU speech
enhancement). Default model/params follow the measured Pareto result:
dpdfnet2 @ attn_limit_db=24 is the best real-time CPU config on the ES+EN
benchmark set (pesq ~2.88, rtf ~0.38).
"""

from __future__ import annotations

from pathlib import Path

from voxera.backends.base import Backend
from voxera.errors import EnhancementError

DEFAULT_MODEL = "dpdfnet2"
DEFAULT_ATTN_LIMIT_DB = 24.0


class DpdfNetBackend(Backend):
    """Enhancement backend backed by the dpdfnet neural engine."""

    name = "dpdfnet"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        attn_limit_db: float = DEFAULT_ATTN_LIMIT_DB,
        seed: int | None = None,
    ) -> None:
        self.model = model
        self.attn_limit_db = attn_limit_db
        self.seed = seed

    def enhance(self, input_path: Path, output_path: Path) -> Path:
        try:
            import numpy as np
            import dpdfnet
            import soundfile as sf
        except ImportError as exc:
            raise EnhancementError(
                "backend 'dpdfnet' is unavailable: install the 'dpdfnet' package"
            ) from exc
        if self.seed is not None:
            np.random.seed(self.seed)
            try:
                import torch

                torch.manual_seed(self.seed)
            except ImportError:
                pass
        try:
            audio, sr = sf.read(str(input_path), dtype="float32", always_2d=False)
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            enhanced = dpdfnet.enhance(
                audio, sample_rate=sr, model=self.model, attn_limit_db=self.attn_limit_db
            )
            sf.write(str(output_path), enhanced, sr, subtype="PCM_16")
        except EnhancementError:
            raise
        except Exception as exc:  # noqa: BLE001 - user-facing error boundary
            raise EnhancementError(f"backend 'dpdfnet' failed: {exc}") from exc
        if not output_path.exists():
            raise EnhancementError(f"backend 'dpdfnet' did not produce output: {output_path}")
        return output_path
