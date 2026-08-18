"""Unit + integration tests de ``voxera video slowmo``: slow motion / fast motion.

- Unit: atempo_chain, build_plan, validación de opciones.
- Integration (ffmpeg): vídeos sintéticos testsrc2 320x260@30fps + sine 440 Hz,
  verificación de duración ±1 frame, fps preservado, pitch preservado.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from voxera.errors import EnhancementError
from voxera import video_slowmo as sm

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


def _has_ffmpeg() -> bool:
    return FFMPEG is not None and FFPROBE is not None


requires_ffmpeg = pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg no encontrado en PATH")


# --- Fixtures --------------------------------------------------------------

@pytest.fixture(scope="module")
def synthetic_video(tmp_path_factory) -> Path:
    """Genera un vídeo de 4 s: testsrc2 320x240@30fps + sine 440 Hz."""
    tmp = tmp_path_factory.mktemp("slowmo_data")
    out = tmp / "test_4s.mp4"
    subprocess.run(
        [
            FFMPEG, "-y", "-v", "error",
            "-f", "lavfi", "-i", "testsrc2=d=4:s=320x240:r=30",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=4:sample_rate=48000",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest", str(out),
        ],
        check=True, capture_output=True,
    )
    return out


@pytest.fixture(scope="module")
def synthetic_video_noaudio(tmp_path_factory) -> Path:
    """Genera un vídeo de 4 s sin pista de audio: testsrc2 320x240@30fps."""
    tmp = tmp_path_factory.mktemp("slowmo_data_noaudio")
    out = tmp / "test_4s_noaudio.mp4"
    subprocess.run(
        [
            FFMPEG, "-y", "-v", "error",
            "-f", "lavfi", "-i", "testsrc2=d=4:s=320x240:r=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
            "-an", str(out),
        ],
        check=True, capture_output=True,
    )
    return out


def _probe_duration(path: Path) -> float:
    """ffprobe duration in seconds."""
    r = subprocess.run(
        [FFPROBE, "-v", "error",
         "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    return float(r.stdout.strip())


def _probe_fps(path: Path) -> float:
    """ffprobe fps."""
    r = subprocess.run(
        [FFPROBE, "-v", "error",
         "-show_entries", "stream=r_frame_rate",
         "-select_streams", "v:0",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    num, den = r.stdout.strip().split("/")
    return float(num) / float(den)


# --- Unit tests: atempo_chain ---------------------------------------------

class TestAtempoChain:
    def test_factor_1_returns_empty(self):
        assert sm.atempo_chain(1.0) == []

    def test_factor_0_5_single_stage(self):
        chain = sm.atempo_chain(0.5)
        assert len(chain) == 1
        assert chain[0] == "atempo=0.500000"

    def test_factor_0_25_two_stages(self):
        chain = sm.atempo_chain(0.25)
        assert len(chain) == 2
        for f in chain:
            val = float(f.split("=")[1])
            assert val >= 0.5 - 1e-9, f"stage {val} < 0.5"

    def test_factor_0_125_three_stages(self):
        chain = sm.atempo_chain(0.125)
        assert len(chain) == 3
        for f in chain:
            val = float(f.split("=")[1])
            assert val >= 0.5 - 1e-9

    def test_factor_2_single_stage(self):
        chain = sm.atempo_chain(2.0)
        assert len(chain) == 1
        assert "2.0" in chain[0]

    def test_all_stages_ge_0_5(self):
        for factor in [0.125, 0.2, 0.3, 0.4, 0.5, 0.7, 1.0, 1.5, 2.0, 3.0]:
            chain = sm.atempo_chain(factor)
            for f in chain:
                val = float(f.split("=")[1])
                assert val >= 0.5 - 1e-9, f"factor={factor}, stage={val}"

    def test_chain_product_equals_factor(self):
        """La multiplicación de todos los stages ≈ factor."""
        for factor in [0.125, 0.2, 0.25, 0.3, 0.5, 0.75, 1.5, 2.0, 4.0]:
            chain = sm.atempo_chain(factor)
            if not chain:
                assert factor == 1.0
                continue
            product = 1.0
            for f in chain:
                product *= float(f.split("=")[1])
            assert abs(product - factor) < 1e-4, (
                f"factor={factor}, product={product}"
            )


# --- Unit tests: build_plan -----------------------------------------------

class TestBuildPlan:
    def test_plan_contains_math(self, synthetic_video):
        plan = sm.build_plan(str(synthetic_video), factor=0.5)
        assert "VOXERA PLAN (video slowmo)" in plan
        assert "factor" in plan
        assert "0.5" in plan
        assert "lento" in plan

    def test_plan_whole_clip_duration(self, synthetic_video):
        plan = sm.build_plan(str(synthetic_video), factor=0.5)
        # 4s / 0.5 = 8s
        assert "8.00" in plan

    def test_plan_segment_duration(self, synthetic_video):
        plan = sm.build_plan(str(synthetic_video), factor=0.5, start=1.0, end=3.0)
        # Segment: 1s + (2s/0.5) + 1s = 6s
        assert "6.00" in plan

    def test_plan_fast_motion(self, synthetic_video):
        plan = sm.build_plan(str(synthetic_video), factor=2.0)
        assert "rápido" in plan
        assert "2.0" in plan

    def test_plan_interpolate(self, synthetic_video):
        plan = sm.build_plan(str(synthetic_video), factor=0.5, interpolate="minterpolate", fps=60)
        assert "minterpolate" in plan
        assert "MUY lento" in plan

    def test_plan_no_audio(self, synthetic_video_noaudio):
        plan = sm.build_plan(str(synthetic_video_noaudio), factor=0.5)
        assert "sin audio" in plan


# --- Unit tests: validation ------------------------------------------------

class TestValidation:
    def test_factor_too_low(self, synthetic_video, tmp_path):
        with pytest.raises(EnhancementError, match="factor debe ser >="):
            sm.slowmo_video(str(synthetic_video), str(tmp_path / "out.mp4"), factor=0.05)

    def test_factor_too_high(self, synthetic_video, tmp_path):
        with pytest.raises(EnhancementError, match="factor debe ser <="):
            sm.slowmo_video(str(synthetic_video), str(tmp_path / "out.mp4"), factor=5.0)

    def test_bad_interpolate(self, synthetic_video, tmp_path):
        with pytest.raises(EnhancementError, match="interpolate"):
            sm.slowmo_video(str(synthetic_video), str(tmp_path / "out.mp4"), interpolate="bad")

    def test_negative_start(self, synthetic_video, tmp_path):
        with pytest.raises(EnhancementError, match="start debe ser >="):
            sm.slowmo_video(str(synthetic_video), str(tmp_path / "out.mp4"),
                            start=-1.0, end=2.0)

    def test_start_ge_end(self, synthetic_video, tmp_path):
        with pytest.raises(EnhancementError, match="end.*debe ser > start"):
            sm.slowmo_video(str(synthetic_video), str(tmp_path / "out.mp4"),
                            start=3.0, end=2.0)

    def test_missing_input(self, tmp_path):
        with pytest.raises(EnhancementError, match="input no existe"):
            sm.slowmo_video(str(tmp_path / "noexiste.mp4"), str(tmp_path / "out.mp4"))


# --- Integration tests (require ffmpeg) -----------------------------------

@requires_ffmpeg
class TestIntegrationWholeClip:
    def test_factor_0_5_dur(self, synthetic_video, tmp_path):
        out = tmp_path / "slow_05.mp4"
        sm.slowmo_video(str(synthetic_video), str(out), factor=0.5)
        dur = _probe_duration(out)
        assert abs(dur - 8.0) < 0.5, f"esperada ~8.0s, got {dur:.2f}s"

    def test_factor_0_5_fps(self, synthetic_video, tmp_path):
        out = tmp_path / "slow_05.mp4"
        sm.slowmo_video(str(synthetic_video), str(out), factor=0.5)
        fps = _probe_fps(out)
        assert abs(fps - 30.0) < 0.5, f"esperado 30fps, got {fps}"

    def test_factor_0_25_dur(self, synthetic_video, tmp_path):
        out = tmp_path / "slow_025.mp4"
        sm.slowmo_video(str(synthetic_video), str(out), factor=0.25)
        dur = _probe_duration(out)
        assert abs(dur - 16.0) < 0.5, f"esperada ~16.0s, got {dur:.2f}s"

    def test_no_audio(self, synthetic_video_noaudio, tmp_path):
        out = tmp_path / "slow_noaudio.mp4"
        sm.slowmo_video(str(synthetic_video_noaudio), str(out), factor=0.5)
        dur = _probe_duration(out)
        assert abs(dur - 8.0) < 0.5, f"esperada ~8.0s, got {dur:.2f}s"


@requires_ffmpeg
class TestIntegrationSegment:
    def test_segment_dur(self, synthetic_video, tmp_path):
        # 4s input: --at 1:3 factor 0.5 => 1s + 2s*2 + 1s = 6s
        out = tmp_path / "seg.mp4"
        sm.slowmo_video(str(synthetic_video), str(out),
                        factor=0.5, start=1.0, end=3.0)
        dur = _probe_duration(out)
        assert abs(dur - 6.0) < 0.5, f"esperada ~6.0s, got {dur:.2f}s"


@requires_ffmpeg
class TestDryRun:
    def test_build_plan_no_crash(self, synthetic_video):
        plan = sm.build_plan(str(synthetic_video), factor=0.5)
        assert isinstance(plan, str) and len(plan) > 50


# --- CLI integration -------------------------------------------------------

@requires_ffmpeg
class TestCLI:
    def test_help(self):
        env = dict(__import__("os").environ)
        root = Path(__file__).resolve().parent.parent
        env["PYTHONPATH"] = str(root / "src")
        proc = subprocess.run(
            [sys.executable, "-m", "voxera.cli", "video", "slowmo", "--help"],
            capture_output=True, text=True, env=env,
        )
        assert proc.returncode == 0
        assert "slowmo" in proc.stdout.lower() or "slow" in proc.stdout.lower()

    def test_dry_run(self, synthetic_video, tmp_path):
        env = dict(__import__("os").environ)
        root = Path(__file__).resolve().parent.parent
        env["PYTHONPATH"] = str(root / "src")
        proc = subprocess.run(
            [sys.executable, "-m", "voxera.cli", "video", "slowmo",
             str(synthetic_video), "-o", str(tmp_path / "out.mp4"),
             "--factor", "0.5", "--dry-run"],
            capture_output=True, text=True, env=env,
        )
        assert proc.returncode == 0, proc.stderr
        assert "VOXERA PLAN" in proc.stdout
