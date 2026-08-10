"""CLI tests: exit codes, error mapping, and help output."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import soundfile as sf

import tests.synth as s

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run_cli(*args, cwd=None):
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(PROJECT_ROOT / "src"), str(PROJECT_ROOT)])
    return subprocess.run(
        [sys.executable, "-m", "voxera.cli", *args],
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


def write_48k(path: Path, x, sr=48000, channels=1) -> Path:
    if channels == 2:
        sf.write(str(path), __import__("numpy").stack([x, x], axis=1), sr)
    else:
        sf.write(str(path), x, sr)
    return path


def strip_timing(report: dict) -> str:
    report["system"].pop("processing_time_s", None)
    return json.dumps(report, sort_keys=True)


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


class TestAnalyzeCommand:
    def test_analyze_tty_summary(self, tmp_path):
        audio = write_48k(tmp_path / "in.wav", s.speech_like(1.5))
        proc = run_cli("analyze", str(audio))
        assert proc.returncode == 0
        assert "Loudness:" in proc.stdout
        assert "speech" in proc.stdout

    def test_analyze_json_parses_with_provenance(self, tmp_path):
        audio = write_48k(tmp_path / "in.wav", s.speech_like(1.5))
        proc = run_cli("analyze", str(audio), "--format", "json")
        assert proc.returncode == 0
        report = json.loads(proc.stdout)
        assert report["system"]["voxera_version"] == "0.2.0"
        assert "loudness" in report and "voice" in report

    def test_analyze_json_stable_across_runs(self, tmp_path):
        audio = write_48k(tmp_path / "in.wav", s.speech_like(1.5))
        p1 = run_cli("analyze", str(audio), "--format", "json")
        p2 = run_cli("analyze", str(audio), "--format", "json")
        assert p1.returncode == p2.returncode == 0
        assert strip_timing(json.loads(p1.stdout)) == strip_timing(json.loads(p2.stdout))

    def test_analyze_writes_report_file(self, tmp_path):
        audio = write_48k(tmp_path / "in.wav", s.speech_like(1.5))
        out = tmp_path / "report.json"
        proc = run_cli("analyze", str(audio), "-o", str(out), "--format", "json")
        assert proc.returncode == 0
        assert json.loads(out.read_text(encoding="utf-8"))["system"]["voxera_version"] == "0.2.0"

    def test_analyze_missing_file_exits_1(self, tmp_path):
        proc = run_cli("analyze", str(tmp_path / "nope.wav"))
        assert proc.returncode == 1
        assert "no such file" in proc.stderr


class TestMasterCommand:
    def test_master_writes_48k_pcm24(self, tmp_path):
        audio = write_48k(tmp_path / "in.wav", s.speech_like(2.0))
        out = tmp_path / "out.wav"
        proc = run_cli("master", str(audio), "-o", str(out), "--preset", "youtube")
        assert proc.returncode == 0
        info = sf.info(str(out))
        assert info.samplerate == 48000
        assert info.subtype == "PCM_24"

    def test_master_stereo_44k1_downmixed_48k(self, tmp_path):
        audio = write_48k(tmp_path / "in.wav", s.speech_like(1.5), sr=44100, channels=2)
        out = tmp_path / "out.wav"
        proc = run_cli("master", str(audio), "-o", str(out))
        assert proc.returncode == 0
        info = sf.info(str(out))
        assert info.samplerate == 48000 and info.channels == 1

    def test_master_silence_exits_20(self, tmp_path):
        audio = write_48k(tmp_path / "sil.wav", s.silence(1.0))
        proc = run_cli("master", str(audio), "-o", str(tmp_path / "out.wav"))
        assert proc.returncode == 20
        assert "no speech detected" in proc.stderr
        assert not (tmp_path / "out.wav").exists()

    def test_master_dry_run_writes_nothing(self, tmp_path):
        audio = write_48k(tmp_path / "in.wav", s.speech_like(2.0))
        out = tmp_path / "out.wav"
        proc = run_cli("master", str(audio), "-o", str(out), "--dry-run")
        assert proc.returncode == 0
        assert "VOXERA PLAN" in proc.stdout
        assert "High-pass" in proc.stdout
        assert not out.exists()

    def test_master_unknown_preset_exits_2(self, tmp_path):
        audio = write_48k(tmp_path / "in.wav", s.speech_like(1.0))
        proc = run_cli("master", str(audio), "-o", str(tmp_path / "o.wav"), "--preset", "bogus")
        assert proc.returncode == 2  # usage error (argparse choices)
        assert "invalid choice" in proc.stderr

    def test_master_verbose_reports_rtf(self, tmp_path):
        audio = write_48k(tmp_path / "in.wav", s.speech_like(2.0))
        proc = run_cli("master", str(audio), "-o", str(tmp_path / "o.wav"), "--verbose")
        assert proc.returncode == 0
        assert "RTF" in proc.stdout or "RTF" in proc.stderr

    def test_master_invalid_device_exits_2(self, tmp_path):
        audio = write_48k(tmp_path / "in.wav", s.speech_like(1.0))
        proc = run_cli("master", str(audio), "-o", str(tmp_path / "o.wav"), "--device", "bogus")
        assert proc.returncode == 2


class TestEnhancePipeline:
    def test_enhance_dsp_only_writes_24bit(self, tmp_path):
        audio = write_48k(tmp_path / "in.wav", s.speech_like(2.0))
        out = tmp_path / "out.wav"
        proc = run_cli("enhance", str(audio), "-o", str(out), "--dsp-only")
        assert proc.returncode == 0
        info = sf.info(str(out))
        assert info.samplerate == 48000 and info.subtype == "PCM_24"

    def test_enhance_dry_run_prints_plan_writes_nothing(self, tmp_path):
        audio = write_48k(tmp_path / "in.wav", s.speech_like(2.0))
        out = tmp_path / "out.wav"
        proc = run_cli("enhance", str(audio), "-o", str(out), "--preset", "youtube", "--dry-run")
        assert proc.returncode == 0
        assert "VOXERA PLAN" in proc.stdout
        assert "DeepFilterNet2" in proc.stdout
        assert not out.exists()

    def test_enhance_preset_runs_nn_and_master(self, tmp_path):
        audio = write_48k(tmp_path / "in.wav", s.speech_like(2.0))
        out = tmp_path / "out.wav"
        proc = run_cli("enhance", str(audio), "-o", str(out), "--preset")
        assert proc.returncode == 0
        info = sf.info(str(out))
        assert info.samplerate == 48000 and info.subtype == "PCM_24"

    def test_enhance_pipeline_silence_exits_20(self, tmp_path):
        audio = write_48k(tmp_path / "sil.wav", s.silence(1.0))
        proc = run_cli("enhance", str(audio), "-o", str(tmp_path / "o.wav"), "--preset")
        assert proc.returncode == 20

    def test_legacy_enhance_unchanged(self, tmp_path):
        """Sin --preset = solo backend (back-compat): 8 kHz silence still exits 0."""
        audio = write_wav(tmp_path / "in.wav")
        proc = run_cli("enhance", str(audio), "-o", str(tmp_path / "out.wav"))
        assert proc.returncode == 0
        assert (tmp_path / "out.wav").exists()

    def test_enhance_help_lists_pipeline_flags(self):
        proc = run_cli("enhance", "--help")
        assert proc.returncode == 0
        assert "--preset" in proc.stdout
        assert "--dry-run" in proc.stdout

    def test_master_help_lists_flags(self):
        proc = run_cli("master", "--help")
        assert proc.returncode == 0
        assert "--no-loudnorm" in proc.stdout
        assert "--dehum" in proc.stdout

    def test_analyze_help(self):
        proc = run_cli("analyze", "--help")
        assert proc.returncode == 0
        assert "--format" in proc.stdout
