"""CLI tests: exit codes, error mapping, and help output."""

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run_cli(*args, cwd=None):
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(PROJECT_ROOT / "src"), str(PROJECT_ROOT)])
    return subprocess.run(
        [sys.executable, "-m", "improve_my_sound.cli", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd or PROJECT_ROOT,
    )


def write_wav(path: Path) -> Path:
    import wave

    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * 8000)
    return path


class TestEnhanceCommand:
    def test_missing_input_exits_1_with_stderr(self, tmp_path):
        proc = run_cli("enhance", str(tmp_path / "nope.wav"), "-o", str(tmp_path / "out.wav"))
        assert proc.returncode == 1
        assert "no such file" in proc.stderr
        assert proc.stdout == ""

    def test_unsupported_format_exits_1(self, tmp_path):
        audio = write_wav(tmp_path / "clip.mp3")
        proc = run_cli("enhance", str(audio), "-o", str(tmp_path / "out.wav"))
        assert proc.returncode == 1
        assert "unsupported format" in proc.stderr

    def test_empty_audio_exits_1(self, tmp_path):
        audio = tmp_path / "empty.wav"
        audio.write_bytes(b"")
        proc = run_cli("enhance", str(audio), "-o", str(tmp_path / "out.wav"))
        assert proc.returncode == 1
        assert "invalid wav" in proc.stderr

    def test_unknown_backend_exits_2(self, tmp_path):
        audio = write_wav(tmp_path / "in.wav")
        proc = run_cli(
            "enhance", str(audio), "-o", str(tmp_path / "out.wav"), "--backend", "bogus"
        )
        assert proc.returncode == 2
        assert "unknown backend" in proc.stderr

    def test_default_backend_produces_output(self, tmp_path):
        audio = write_wav(tmp_path / "in.wav")
        proc = run_cli("enhance", str(audio), "-o", str(tmp_path / "out.wav"))
        assert proc.returncode == 0
        assert (tmp_path / "out.wav").exists()

    def test_missing_output_flag_exits_2(self, tmp_path):
        audio = write_wav(tmp_path / "in.wav")
        proc = run_cli("enhance", str(audio))
        assert proc.returncode == 2

    def test_help_exits_0(self):
        proc = run_cli("--help")
        assert proc.returncode == 0
        assert "enhance" in proc.stdout

    def test_enhance_help_exits_0(self):
        proc = run_cli("enhance", "--help")
        assert proc.returncode == 0
        assert "--backend" in proc.stdout

    def test_no_command_exits_2(self):
        proc = run_cli()
        assert proc.returncode == 2
