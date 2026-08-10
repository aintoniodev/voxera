"""End-to-end pipeline smoke test: feature -> IR -> entry points -> pytest."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from acceptance.generator import slug
from acceptance.pipeline import (
    DRY_DIR,
    GENERATED_DIR,
    IR_DIR,
    PROJECT_ROOT,
    clean_build,
    find_parser,
    run_acceptance,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SMOKE = FIXTURES / "smoke.feature"

pytestmark = pytest.mark.skipif(
    not shutil.which("gherkin-parser") and not (Path.home() / "swarmforge-bin" / "gherkin-parser").exists(),
    reason="APS gherkin-parser not installed",
)


class TestPipeline:
    def test_parser_available(self):
        assert find_parser()

    def test_smoke_feature_passes_end_to_end(self):
        """The smoke feature exercises the real CLI error path through the
        whole pipeline: gherkin-parser -> generator -> pytest."""
        assert SMOKE.exists()
        exit_code = run_acceptance(FIXTURES)
        assert exit_code == 0

        ir = IR_DIR / f"{slug(str(SMOKE))}.json"
        assert ir.exists()
        dry = DRY_DIR / f"{slug(str(SMOKE))}.json"
        assert dry.exists()
        generated = GENERATED_DIR / f"{slug(str(SMOKE))}_acceptance_test.py"
        assert generated.exists()
        metadata = GENERATED_DIR / "metadata" / f"{slug(str(SMOKE))}.json"
        assert metadata.exists()

    def test_clean_build_resets_artifacts(self):
        clean_build()
        assert not IR_DIR.exists() or not any(IR_DIR.iterdir())
