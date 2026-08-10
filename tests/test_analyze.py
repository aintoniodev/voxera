"""Track 1: analyze report contract, heuristics and JSON stability."""

import json

import pytest

import tests.synth as s
from voxera.analyze import analyze
from voxera.determinism import dump_report
from voxera.errors import EnhancementError

SR = 48000


def write_fixture(tmp_path, x, name="in.wav", sr=SR):
    import soundfile as sf

    p = tmp_path / name
    sf.write(str(p), x, sr, subtype="PCM_16")
    return str(p)


def strip_timing(text: str) -> str:
    report = json.loads(text)
    report["system"].pop("processing_time_s", None)
    return json.dumps(report, sort_keys=True)


class TestReportStructure:
    def test_all_blocks_present(self, tmp_path):
        report = analyze(write_fixture(tmp_path, s.speech_like(2.0)))
        for block in ("input", "loudness", "voice", "spectral", "room", "artifacts", "system"):
            assert block in report

    def test_input_block(self, tmp_path):
        report = analyze(write_fixture(tmp_path, s.speech_like(2.0)))
        inp = report["input"]
        assert inp["sample_rate"] == 48000
        assert inp["channels"] == 1
        assert inp["bit_depth"] == "16-bit"
        assert inp["format"] == "WAV PCM 16-bit"
        assert abs(inp["duration_s"] - 2.0) < 0.05

    def test_loudness_block_values(self, tmp_path):
        report = analyze(write_fixture(tmp_path, s.speech_like(2.0)))
        loud = report["loudness"]
        for key in ("integrated_lufs", "short_term_lufs", "lra", "true_peak_db", "rms_db", "clipping_ratio"):
            assert key in loud
        assert loud["integrated_lufs"] is not None

    def test_estimates_carry_confidence(self, tmp_path):
        report = analyze(write_fixture(tmp_path, s.speech_like(2.0)))
        assert 0.0 <= report["voice"]["snr_db"]["confidence"] <= 1.0
        assert 0.0 <= report["room"]["confidence"] <= 1.0
        assert 0.0 <= report["artifacts"]["plosives"]["confidence"] <= 1.0
        assert 0.0 <= report["artifacts"]["mouth_click_candidates"]["confidence"] <= 1.0
        assert 0.0 <= report["artifacts"]["noise_type"]["confidence"] <= 1.0

    def test_system_block_provenance(self, tmp_path):
        report = analyze(write_fixture(tmp_path, s.speech_like(2.0)))
        sys_block = report["system"]
        assert sys_block["voxera_version"] == "0.2.0"
        assert sys_block["pipeline_version"]
        assert "processing_time_s" in sys_block

    def test_analyze_works_on_silence(self, tmp_path):
        """analyze/inspect siguen funcionando sin voz (spec exit 20 table)."""
        report = analyze(write_fixture(tmp_path, s.silence(1.0)))
        assert report["voice"]["speech_ratio"] == 0.0


class TestHeuristics:
    def test_hum_detected(self, tmp_path):
        report = analyze(write_fixture(tmp_path, s.hum_buzz()))
        hum = report["spectral"]["hum_db"]
        assert hum["dominant"] == "50 Hz"
        assert report["artifacts"]["noise_type"]["type"] == "hum"

    def test_speech_ratio_high_on_speech(self, tmp_path):
        report = analyze(write_fixture(tmp_path, s.speech_like(2.0)))
        assert report["voice"]["speech_ratio"] > 0.5

    def test_noise_type_field_shape(self, tmp_path):
        report = analyze(write_fixture(tmp_path, s.speech_like(2.0)))
        nt = report["artifacts"]["noise_type"]
        assert isinstance(nt["stationary"], bool)
        assert isinstance(nt["broadband"], bool)
        assert isinstance(nt["tonal"], bool)
        assert nt["type"] in (
            "fan ac hiss hum keyboard traffic people music "
            "stationary non-stationary unknown"
        ).split()

    def test_breaths_and_clicks_detected(self, tmp_path):
        report = analyze(write_fixture(tmp_path, s.with_breaths()))
        assert report["artifacts"]["breaths"]["count"] >= 1
        report2 = analyze(write_fixture(tmp_path, s.with_clicks()))
        assert report2["artifacts"]["mouth_click_candidates"]["count"] >= 2

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(EnhancementError, match="no such file"):
            analyze(str(tmp_path / "nope.wav"))


class TestJsonStability:
    def test_reports_stable_between_runs(self, tmp_path):
        p = write_fixture(tmp_path, s.speech_like(2.0))
        r1 = dump_report(analyze(p))
        r2 = dump_report(analyze(p))
        assert strip_timing(r1) == strip_timing(r2)

    def test_no_variable_timestamps_or_uuids(self, tmp_path):
        text = dump_report(analyze(write_fixture(tmp_path, s.speech_like(2.0))))
        assert "uuid" not in text.lower()
        assert "timestamp" not in text.lower()
