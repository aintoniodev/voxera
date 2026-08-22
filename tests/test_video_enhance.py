"""Fase 3: video_enhance — probe, plan, opciones, pesos y compare.

Unit tests corren sin GPU (solo ffmpeg). El test de enhance end-to-end
(con masterización de audio) se salta sin CUDA — corre en .venv-video.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

import tests.synth as s
from voxera import video_enhance as ve
from voxera.errors import EnhancementError

FFMPEG = shutil.which("ffmpeg") or (
    Path("C:/ffmpeg/bin/ffmpeg.exe").exists() and "C:/ffmpeg/bin/ffmpeg.exe"
)
pytestmark = pytest.mark.skipif(not FFMPEG, reason="ffmpeg required")

SR = 48000


def make_video(tmp_path, name="test.mp4", duration=2.0, size="320x640", rate="10") -> Path:
    """testsrc + voz sintética (mismo patrón que test_video.py)."""
    wav = tmp_path / "audio.wav"
    import soundfile as sf

    sf.write(str(wav), s.speech_like(duration), SR)
    out = tmp_path / name
    subprocess.run(
        [FFMPEG, "-y", "-v", "error", "-f", "lavfi",
         "-i", f"testsrc=duration={duration}:size={size}:rate={rate}",
         "-i", str(wav), "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "96k", "-shortest", str(out)],
        check=True, capture_output=True,
    )
    return out


class TestProbe:
    def test_probe_fields(self, tmp_path):
        info = ve.probe_video(make_video(tmp_path))
        assert info["width"] == 320
        assert info["height"] == 640
        assert info["codec"] == "h264"
        assert info["has_audio"] is True
        assert info["duration_s"] > 1.0
        assert info["fps"] > 0

    def test_probe_rejects_non_video(self, tmp_path):
        wav = tmp_path / "x.wav"
        import soundfile as sf

        sf.write(str(wav), s.speech_like(0.5), SR)
        with pytest.raises(EnhancementError):
            ve.probe_video(wav)


class TestOptions:
    def test_bad_model(self):
        with pytest.raises(EnhancementError):
            ve.VideoOptions(model="nope").validate()

    def test_bad_fps(self):
        with pytest.raises(EnhancementError):
            ve.VideoOptions(fps=0).validate()

    def test_bad_seg(self):
        with pytest.raises(EnhancementError):
            ve.VideoOptions(seg=(5, 2)).validate()

    def test_defaults(self):
        assert ve.VideoOptions().model == ve.DEFAULT_VIDEO_MODEL == "animevideov3"
        assert ve.VideoOptions().fps == 30


class TestPlan:
    def test_plan_contract(self, tmp_path):
        plan = ve.build_plan(make_video(tmp_path), ve.VideoOptions())
        assert "VOXERA PLAN (video)" in plan
        assert "animevideov3" in plan
        assert "1080x1920" in plan
        assert "RTX 2060" in plan

    def test_plan_x4plus(self, tmp_path):
        assert "x4plus" in ve.build_plan(
            make_video(tmp_path), ve.VideoOptions(model="x4plus")
        )

    def test_plan_no_nn_load(self, tmp_path):
        """El plan nunca debe importar torch/realesrgan (corre en venv sin GPU)."""
        plan = ve.build_plan(make_video(tmp_path), ve.VideoOptions())
        assert "CUDA" in plan


class TestWeights:
    def test_missing_weight_hint(self, tmp_path, monkeypatch):
        monkeypatch.setenv("VOXERA_VIDEO_MODELS", str(tmp_path / "nope"))
        with pytest.raises(EnhancementError) as ei:
            ve.resolve_weight_path("animevideov3")
        assert "curl" in str(ei.value)


class TestCompare:
    def test_compare_2panel(self, tmp_path):
        pytest.importorskip("cv2")
        a = make_video(tmp_path, "a.mp4")
        b = make_video(tmp_path, "b.mp4")
        out = ve.compare_videos(a, b, tmp_path / "ab.mp4", fps=10)
        info = ve.probe_video(out)
        assert info["width"] == 2160  # 2 paneles x 1080
        assert info["height"] == 1920

    def test_compare_3panel(self, tmp_path):
        pytest.importorskip("cv2")
        a = make_video(tmp_path, "a.mp4")
        b = make_video(tmp_path, "b.mp4")
        out = ve.compare_videos(a, b, tmp_path / "ab3.mp4", source=a, fps=10)
        assert ve.probe_video(out)["width"] == 3240  # 3 paneles x 1080


def _cuda_ready() -> bool:
    try:
        import torch

        return torch.cuda.is_available()
    except Exception:  # noqa: BLE001
        return False


@pytest.mark.skipif(not _cuda_ready(), reason="CUDA GPU required (venv-video)")
class TestEnhanceGPU:
    def test_enhance_mini_with_master_audio(self, tmp_path):
        """End-to-end: frames -> animevideov3 -> 720x1280 + audio masterizado."""
        v = make_video(tmp_path, duration=1.0, size="180x320", rate="10")
        out = tmp_path / "enh.mp4"
        opts = ve.VideoOptions(fps=10, width=720, height=1280,
                               master_audio=True, master_preset="creator")
        ve.enhance_video(v, out, opts)
        info = ve.probe_video(out)
        assert info["width"] == 720
        assert info["height"] == 1280
        assert info["has_audio"] is True
        assert Path(str(out) + ".compare.png").exists()
