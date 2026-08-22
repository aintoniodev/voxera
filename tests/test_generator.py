"""Entrypoint generator contract tests (APS acceptance-generator spec)."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from acceptance.generator import FEATURE_PATH_ENV, TEST_SUFFIX, generate, generated_test_text, main, slug

IR = {
    "name": "probe feature",
    "scenarios": [
        {
            "name": "scenario one",
            "steps": [{"keyword": "Then", "text": "the result is <result>", "parameters": ["result"]}],
            "examples": [{"result": "ok"}],
        }
    ],
}


def write_ir(tmp_path, name="probe.json"):
    path = tmp_path / name
    path.write_text(json.dumps(IR), encoding="utf-8")
    return path


class TestSlug:
    def test_spec_examples(self):
        assert slug("features/Hunt The Wumpus.feature") == "features-hunt-the-wumpus-feature"
        assert slug("features/orders/Cancel Order.feature") == "features-orders-cancel-order-feature"
        assert slug("Features/API v2/Happy Path.feature") == "features-api-v2-happy-path-feature"

    def test_trims_leading_and_trailing_hyphens(self):
        assert slug("!!leading.feature").startswith("leading")
        assert slug("trailing!!").endswith("trailing")


class TestMain:
    def test_wrong_usage_exits_2(self, capsys):
        assert main(["only-one-arg"]) == 2
        assert main([]) == 2
        assert main(["a", "b", "c"]) == 2

    def test_missing_ir_exits_1(self, tmp_path, capsys):
        assert main([str(tmp_path / "nope.json"), str(tmp_path / "out")]) == 1

    def test_invalid_ir_exits_1(self, tmp_path, capsys):
        bad = tmp_path / "bad.json"
        bad.write_text('{"name": 1}', encoding="utf-8")
        assert main([str(bad), str(tmp_path / "out")]) == 1

    def test_generates_test_and_metadata(self, tmp_path, monkeypatch):
        ir_path = write_ir(tmp_path)
        out_dir = tmp_path / "generated"
        monkeypatch.setenv(FEATURE_PATH_ENV, "features/probe.feature")
        assert main([str(ir_path), str(out_dir)]) == 0

        test_file = out_dir / f"features-probe-feature{TEST_SUFFIX}"
        assert test_file.exists()
        content = test_file.read_text(encoding="utf-8")
        # Entry points must embed or load the IR and run every execution.
        assert "SCENARIO_EXECUTIONS" in content
        assert "scenario one/example_1" in content
        assert 'os.environ.get("ACCEPTANCE_IR"' in content

        metadata = json.loads((out_dir / "metadata" / "features-probe-feature.json").read_text(encoding="utf-8"))
        assert metadata["schema_version"] == 1
        assert metadata["feature_path"] == "features/probe.feature"
        assert metadata["hash_scope"] == "generated_files"
        assert metadata["generated_files"][0].endswith(f"features-probe-feature{TEST_SUFFIX}")
        expected_hash = "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
        assert metadata["implementation_hash"] == expected_hash

    def test_generated_files_relative_to_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ir_path = write_ir(tmp_path)
        monkeypatch.setenv(FEATURE_PATH_ENV, "features/probe.feature")
        assert main([str(ir_path), "generated"]) == 0
        metadata = json.loads((tmp_path / "generated" / "metadata" / "features-probe-feature.json").read_text(encoding="utf-8"))
        assert metadata["generated_files"] == [str(Path("generated") / f"features-probe-feature{TEST_SUFFIX}")]

    def test_deterministic_output(self, tmp_path, monkeypatch):
        ir_path = write_ir(tmp_path)
        out1 = tmp_path / "out1"
        out2 = tmp_path / "out2"
        monkeypatch.setenv(FEATURE_PATH_ENV, "features/probe.feature")
        assert main([str(ir_path), str(out1)]) == 0
        assert main([str(ir_path), str(out2)]) == 0
        f1 = out1 / f"features-probe-feature{TEST_SUFFIX}"
        f2 = out2 / f"features-probe-feature{TEST_SUFFIX}"
        assert f1.read_bytes() == f2.read_bytes()

    def test_feature_path_falls_back_to_convention(self, tmp_path, monkeypatch):
        monkeypatch.delenv(FEATURE_PATH_ENV, raising=False)
        ir_path = write_ir(tmp_path, name="happy-path.json")
        out_dir = tmp_path / "out"
        assert main([str(ir_path), str(out_dir)]) == 0
        metadata = json.loads((out_dir / "metadata" / "features-happy-path-feature.json").read_text(encoding="utf-8"))
        assert metadata["feature_path"] == "features/happy-path.feature"


class TestGeneratedEntryPointRuns:
    def test_generated_test_passes_against_ir(self, tmp_path, monkeypatch):
        """The generated entry point runs every execution via runtime + steps."""
        ir_path = write_ir(tmp_path)
        out_dir = tmp_path / "generated"
        monkeypatch.setenv(FEATURE_PATH_ENV, "features/probe.feature")
        assert main([str(ir_path), str(out_dir)]) == 0
        # The probe IR's step is not in the voxera vocabulary -> must fail.
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent)
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(out_dir), "-q"],
            capture_output=True,
            text=True,
            env=env,
            cwd=Path(__file__).resolve().parent.parent,
        )
        assert proc.returncode != 0
        assert "unsupported step" in proc.stdout
