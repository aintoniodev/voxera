"""Track 4: video pipeline — extraction, bit-identical video, AAC, drift."""

import shutil
import subprocess
from pathlib import Path

import pytest

import tests.synth as s
from voxera import video as v

FFMPEG = shutil.which("ffmpeg") or (Path("C:/ffmpeg/bin/ffmpeg.exe").exists() and "C:/ffmpeg/bin/ffmpeg.exe")

pytestmark = pytest.mark.skipif(
    not FFMPEG, reason="ffmpeg required for video tests"
)

SR = 48000


def make_video(tmp_path, x, name="test.mp4", duration=3.0) -> Path:
    wav = tmp_path / "audio.wav"
    import soundfile as sf

    sf.write(str(wav), x[: int(duration * SR)], SR)
    out = tmp_path / name
    subprocess.run(
        [FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=duration={duration}:size=320x240:rate=25",
         "-i", str(wav), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
         "-shortest", str(out)],
        check=True, capture_output=True,
    )
    return out


def extract_video_stream(mp4: Path, out: Path) -> Path:
    subprocess.run(
        [FFMPEG, "-y", "-v", "error", "-i", str(mp4), "-map", "0:v:0", "-c", "copy", "-f", "h264", str(out)],
        check=True, capture_output=True,
    )
    return out


class TestVideoHelpers:
    def test_is_video_path(self):
        assert v.is_video_path("clip.mp4")
        assert v.is_video_path("clip.MOV")
        assert not v.is_video_path("clip.wav")

    def test_probe_and_stream_detection(self, tmp_path):
        mp4 = make_video(tmp_path, s.speech_like(3.0))
        assert v.has_video_stream(mp4)
        assert abs(v.probe_duration(mp4) - 3.0) < 0.2

    def test_extract_audio_48k_mono(self, tmp_path):
        mp4 = make_video(tmp_path, s.speech_like(3.0))
        wav = v.extract_audio(mp4, tmp_path / "audio.wav")
        import soundfile as sf

        info = sf.info(str(wav))
        assert info.samplerate == 48000 and info.channels == 1


class TestVideoPipeline:
    def _run(self, args, cwd):
        import os
        import sys

        env = os.environ.copy()
        env["PYTHONPATH"] = str(cwd / "src") + os.pathsep + str(cwd)
        return subprocess.run(
            [sys.executable, "-m", "voxera.cli", *args], capture_output=True, text=True, env=env, cwd=cwd
        )

    def test_master_video_bit_identical_and_aac(self, tmp_path, monkeypatch):
        import sys

        from voxera.cli import main

        mp4 = make_video(tmp_path, s.speech_like(3.0))
        out = tmp_path / "out.mp4"
        monkeypatch.setattr(sys, "argv", ["voxera", "master", str(mp4), "-o", str(out), "--preset", "youtube"])
        assert main() == 0
        assert out.exists()
        # video stream bit-identical
        s1 = extract_video_stream(mp4, tmp_path / "v1.h264")
        s2 = extract_video_stream(out, tmp_path / "v2.h264")
        assert s1.read_bytes() == s2.read_bytes()
        # AAC 192k
        proc = subprocess.run(
            [FFMPEG, "-v", "error", "-i", str(out), "-map", "0:a:0", "-c", "copy", "-f", "null", "-"],
            capture_output=True, text=True,
        )
        import json

        probe = subprocess.run(
            [shutil.which("ffprobe") or "C:/ffmpeg/bin/ffprobe.exe", "-v", "error",
             "-select_streams", "a:0", "-show_entries", "stream=codec_name,bit_rate", "-of", "json", str(out)],
            capture_output=True, text=True,
        )
        stream = json.loads(probe.stdout)["streams"][0]
        assert stream["codec_name"] == "aac"
        assert abs(int(stream["bit_rate"]) - 192000) < 20000
        # drift within tolerance
        assert v.check_drift(mp4, out) <= v.DRIFT_TOLERANCE_S

    def test_enhance_video_requires_pipeline(self, tmp_path, monkeypatch):
        import sys

        from voxera.cli import main

        mp4 = make_video(tmp_path, s.speech_like(3.0))
        monkeypatch.setattr(
            sys, "argv", ["voxera", "enhance", str(mp4), "-o", str(tmp_path / "x.mp4")]
        )
        assert main() == 2  # video requires --preset/--dsp-only

    def test_enhance_video_dsp_only(self, tmp_path, monkeypatch):
        import sys

        from voxera.cli import main

        mp4 = make_video(tmp_path, s.speech_like(3.0))
        out = tmp_path / "out.mp4"
        monkeypatch.setattr(
            sys, "argv", ["voxera", "enhance", str(mp4), "-o", str(out), "--dsp-only"]
        )
        assert main() == 0
        assert out.exists()

    def test_wav_output_rejected_for_video(self, tmp_path, monkeypatch):
        import sys

        from voxera.cli import main

        mp4 = make_video(tmp_path, s.speech_like(3.0))
        monkeypatch.setattr(
            sys, "argv", ["voxera", "master", str(mp4), "-o", str(tmp_path / "out.wav")]
        )
        assert main() == 1
