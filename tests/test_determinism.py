"""Track 1A: determinism, provenance and report stability tests."""

import json

from voxera.determinism import dump_report, model_fingerprint, stable_round, system_block


class TestStableRound:
    def test_floats_rounded_to_fixed_precision(self):
        assert stable_round(1.0 / 3) == round(1.0 / 3, 4)
        assert stable_round(3.14159265) == 3.1416

    def test_recursive(self):
        out = stable_round({"a": [1.23456, {"b": 2.34567}], "c": "text"})
        assert out == {"a": [1.2346, {"b": 2.3457}], "c": "text"}

    def test_non_floats_untouched(self):
        assert stable_round(None) is None
        assert stable_round(7) == 7
        assert stable_round("7.00001") == "7.00001"


class TestDumpReport:
    def test_sorted_keys_and_no_uuids_or_timestamps(self):
        text = dump_report({"z": 1, "a": {"y": 2.0, "b": None}})
        assert json.loads(text) == {"a": {"b": None, "y": 2.0}, "z": 1}

    def test_stable_across_calls(self):
        report = {"loudness": {"lufs": -20.696666, "x": 1}, "z": [1.0, 2.0]}
        assert dump_report(report) == dump_report(report)


class TestSystemBlock:
    def test_minimal_block(self):
        block = system_block()
        assert block["voxera_version"] == "0.2.0"
        assert block["pipeline_version"]
        assert block["device"] == "cpu"
        assert block["sample_rate"] == 48000
        assert "processing_time_s" not in block

    def test_full_block_omits_none_fields(self):
        block = system_block(
            device="cuda", seed=42, preset="youtube", backend="deepfilternet",
            model="DeepFilterNet2", model_dir="models", processing_time_s=0.72,
        )
        assert block["seed"] == 42
        assert block["preset"] == "youtube"
        assert block["backend"] == "deepfilternet"
        assert block["model"] == "DeepFilterNet2"
        assert block["model_hash"].startswith("sha256:")
        assert block["processing_time_s"] == 0.72

    def test_model_fingerprint_stable_and_sensitive(self, tmp_path):
        d = tmp_path / "model"
        d.mkdir()
        (d / "a.bin").write_bytes(b"x" * 10)
        (d / "b.bin").write_bytes(b"y" * 20)
        f1 = model_fingerprint(d)
        assert f1.startswith("sha256:")
        assert model_fingerprint(d) == f1  # stable
        (d / "b.bin").write_bytes(b"y" * 21)  # changed size
        assert model_fingerprint(d) != f1
