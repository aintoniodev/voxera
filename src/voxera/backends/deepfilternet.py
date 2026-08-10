"""DeepFilterNet backend — the autoresearch-confirmed winner.

DeepFilterNet2 (post-filter off) dominates the measured Pareto front on the
ES+EN benchmark set: pesq ~3.28, rtf ~0.08 (CPU) — better quality than dpdfnet
and ~12x faster. Runs via the ``deepfilternet`` Python package (torch); CUDA is
used automatically when a CUDA-enabled torch is installed.
"""

from __future__ import annotations

import os
from pathlib import Path

from voxera.backends.base import Backend
from voxera.errors import EnhancementError

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = PROJECT_ROOT / "models"


class DeepFilterNetBackend(Backend):
    """Enhancement backend backed by DeepFilterNet (torch)."""

    name = "deepfilternet"

    def __init__(self, model: str = "DeepFilterNet2", pf: bool = False, seed: int | None = None) -> None:
        self.model = model
        self.pf = pf
        self.seed = seed

    def _resolve_model_dir(self) -> str | None:
        """Return an explicit model dir, or None to let the df package auto-resolve."""
        if os.path.isdir(self.model):
            return self.model
        cand = MODELS_DIR / self.model / self.model
        if cand.exists():
            return str(cand)
        return None

    def enhance(self, input_path: Path, output_path: Path) -> Path:
        try:
            import numpy as np  # noqa: F401
            import soundfile as sf
            import torch
            from df import enhance as df_enhance
            from df import init_df
        except ImportError as exc:
            raise EnhancementError(
                "backend 'deepfilternet' is unavailable: install 'deepfilternet' and torch"
            ) from exc
        if self.seed is not None:
            torch.manual_seed(self.seed)
            np.random.seed(self.seed)
        try:
            audio, sr = sf.read(str(input_path), dtype="float32", always_2d=False)
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            kwargs = {"post_filter": self.pf, "log_file": None, "log_level": "WARNING"}
            model_dir = self._resolve_model_dir()
            if model_dir is not None:
                kwargs["model_base_dir"] = model_dir
            df_model, df_state, _ = init_df(**kwargs)
            yt = torch.from_numpy(audio.astype("float32")).unsqueeze(0)
            enhanced = df_enhance(df_model, df_state, yt, atten_lim_db=None)
            sf.write(str(output_path), enhanced.squeeze(0).numpy(), sr, subtype="PCM_16")
        except EnhancementError:
            raise
        except Exception as exc:  # noqa: BLE001 - user-facing error boundary
            raise EnhancementError(f"backend 'deepfilternet' failed: {exc}") from exc
        if not output_path.exists():
            raise EnhancementError(
                f"backend 'deepfilternet' did not produce output: {output_path}"
            )
        return output_path
