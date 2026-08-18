"""Tests del autopilot: validación de spec, planner rule/llm, executor, A/B.

Suite rápida: tests unitarios (sin ffmpeg) + integración con video sintético
(testsrc2 + sine audio) que solo necesita ffmpeg en PATH.

Spanish docstrings matching repo tone.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from voxera.errors import EnhancementError

# ---------------------------------------------------------------------------
# Canonical valid spec (el del skill draft, adaptado al schema v1)
# ---------------------------------------------------------------------------


def _canonical_spec(**overrides) -> dict:
    """Devuelve un edit-spec válido canónico."""
    spec = {
        "version": 1,
        "source": "raw.mp4",
        "level": "medium",
        "keep_spans": [],
        "hook": {
            "type": "zoom-grow",
            "at": 0.0,
            "pct": 35.0,
            "curve": 62.0,
            "anchor": [0.5, 0.33],
        },
        "effects": [
            {"cmd": "audio riser", "args": {"mood": "tension", "hit": 31.2}},
        ],
        "captions": {
            "enabled": True,
            "style": "karaoke",
            "text_style": "classic",
            "highlight": [],
        },
        "target": {
            "aspect": "9:16",
            "max_dur": 45.0,
            "crf": 18,
        },
    }
    spec.update(overrides)
    return spec


def _words_fixture():
    """Words de ejemplo (2 palabras sobre 4 s)."""
    return [
        {"w": "Hola", "s": 0.5, "e": 1.2},
        {"w": "mundo", "s": 2.0, "e": 3.0},
    ]


# ===================================================================
# TestValidateEditSpec
# ===================================================================


class TestValidateEditSpec:
    """Unit tests de validate_edit_spec."""

    def test_accepts_canonical(self):
        from voxera.autopilot import validate_edit_spec
        spec = _canonical_spec()
        result = validate_edit_spec(spec)
        assert result["version"] == 1
        assert result["level"] == "medium"
        assert len(result["effects"]) == 1

    def test_rejects_bad_version(self):
        from voxera.autopilot import validate_edit_spec
        spec = _canonical_spec(version=2)
        with pytest.raises(EnhancementError, match="version"):
            validate_edit_spec(spec)

    def test_rejects_unknown_cmd(self):
        from voxera.autopilot import validate_edit_spec
        spec = _canonical_spec(effects=[
            {"cmd": "video fakeeffect", "args": {}},
        ])
        with pytest.raises(EnhancementError, match="desconocido"):
            validate_edit_spec(spec)

    def test_rejects_unknown_arg_key(self):
        from voxera.autopilot import validate_edit_spec
        spec = _canonical_spec(effects=[
            {"cmd": "video zoom", "args": {"pct": 30, "frobnicate": True}},
        ])
        with pytest.raises(EnhancementError, match="key desconocida"):
            validate_edit_spec(spec)

    def test_rejects_bad_keep_spans_s_ge_e(self):
        from voxera.autopilot import validate_edit_spec
        spec = _canonical_spec(keep_spans=[[5.0, 3.0]])
        with pytest.raises(EnhancementError, match="s.*debe ser < e"):
            validate_edit_spec(spec)

    def test_rejects_bad_hook_type(self):
        from voxera.autopilot import validate_edit_spec
        spec = _canonical_spec(hook={
            "type": "pan-left", "at": 0.0, "pct": 30, "curve": 62,
        })
        with pytest.raises(EnhancementError, match="zoom-grow"):
            validate_edit_spec(spec)

    def test_rejects_bad_target_max_dur(self):
        from voxera.autopilot import validate_edit_spec
        spec = _canonical_spec(target={
            "aspect": "9:16", "max_dur": -5.0, "crf": 18,
        })
        with pytest.raises(EnhancementError, match="max_dur"):
            validate_edit_spec(spec)

    def test_hook_null_is_ok(self):
        from voxera.autopilot import validate_edit_spec
        spec = _canonical_spec(hook=None)
        result = validate_edit_spec(spec)
        assert result["hook"] is None

    def test_captions_missing_key(self):
        from voxera.autopilot import validate_edit_spec
        spec = _canonical_spec(captions={
            "enabled": True, "style": "karaoke",
        })
        with pytest.raises(EnhancementError, match="falta"):
            validate_edit_spec(spec)

    def test_empty_effects_is_ok(self):
        from voxera.autopilot import validate_edit_spec
        spec = _canonical_spec(effects=[])
        result = validate_edit_spec(spec)
        assert result["effects"] == []

    def test_multiple_cmds_valid(self):
        """Todos los cmds permitidos aceptan args vacíos."""
        from voxera.autopilot import validate_edit_spec
        for cmd in (
            "video zoom", "video magnify", "video teleport",
            "video stabilize", "audio lowpass", "audio transition",
            "audio riser", "audio melody",
        ):
            spec = _canonical_spec(effects=[{"cmd": cmd, "args": {}}])
            result = validate_edit_spec(spec)
            assert len(result["effects"]) == 1


# ===================================================================
# TestRulePlan
# ===================================================================


class TestRulePlan:
    """Unit tests del planner determinista."""

    def test_determinism(self):
        """Dos llamadas con los mismos inputs → mismo output."""
        from voxera.autopilot import rule_plan
        words = _words_fixture()
        a = rule_plan(words, max_dur=30.0, level="light", source="x.mp4")
        b = rule_plan(words, max_dur=30.0, level="light", source="x.mp4")
        assert a == b

    def test_hook_present(self):
        from voxera.autopilot import rule_plan
        spec = rule_plan([], source="x.mp4")
        assert spec["hook"] is not None
        assert spec["hook"]["type"] == "zoom-grow"
        assert spec["hook"]["at"] == 0.0

    def test_riser_hit_equals_last_word_end(self):
        from voxera.autopilot import rule_plan
        words = _words_fixture()
        spec = rule_plan(words, source="x.mp4")
        riser = [e for e in spec["effects"] if e["cmd"] == "audio riser"]
        assert len(riser) == 1
        assert riser[0]["args"]["hit"] == 3.0  # last word end

    def test_no_riser_without_words(self):
        from voxera.autopilot import rule_plan
        spec = rule_plan([], source="x.mp4")
        assert spec["effects"] == []

    def test_captions_enabled(self):
        from voxera.autopilot import rule_plan
        spec = rule_plan([], source="x.mp4")
        assert spec["captions"]["enabled"] is True
        assert spec["captions"]["style"] == "karaoke"

    def test_target_from_args(self):
        from voxera.autopilot import rule_plan
        spec = rule_plan([], max_dur=60.0, target_aspect="keep", crf=22, source="x.mp4")
        assert spec["target"]["max_dur"] == 60.0
        assert spec["target"]["aspect"] == "keep"
        assert spec["target"]["crf"] == 22


# ===================================================================
# TestLlmPlan
# ===================================================================


class TestLlmPlan:
    """Unit tests del LLM planner — sin llamar a un LLM real."""

    def test_default_llm_cmd_used_when_none(self, monkeypatch):
        """llm_cmd=None usa el comando por defecto (opencode/mimo)."""
        from voxera import autopilot
        import subprocess

        called = {}

        def fake_run(cmd, *a, **kw):
            called["cmd"] = cmd
            class R:
                returncode = 1
                stdout = ""
                stderr = "boom"
            return R()

        monkeypatch.setattr(subprocess, "run", fake_run)
        with pytest.raises(EnhancementError, match="boom"):
            autopilot.llm_plan([], llm_cmd=None)
        assert "opencode" in called["cmd"]
        assert "mimo-v2.5" in called["cmd"]

    def test_error_on_garbage_output(self):
        """Si el LLM devuelve basura, EnhancementError con stderr tail."""
        from voxera.autopilot import llm_plan
        # Create a fake command that outputs garbage
        # On Windows, use a bat/cmd that echoes garbage
        if sys.platform == "win32":
            # Write a small script that always outputs garbage
            garbage_script = Path(__file__).parent / "_garbage_llm.bat"
            garbage_script.write_text("@echo THIS IS NOT JSON\necho more garbage\n", encoding="utf-8")
            try:
                cmd = f'cmd /c "{garbage_script}"'
                with pytest.raises(EnhancementError, match="(no es JSON|output vacío|LLM falló)"):
                    llm_plan([], llm_cmd=cmd)
            finally:
                garbage_script.unlink(missing_ok=True)
        else:
            with pytest.raises(EnhancementError):
                llm_plan([], llm_cmd="echo THIS IS NOT JSON")

    def test_error_on_nonzero_exit(self):
        """Si el LLM devuelve exit code != 0, EnhancementError."""
        from voxera.autopilot import llm_plan
        if sys.platform == "win32":
            fail_script = Path(__file__).parent / "_fail_llm.bat"
            fail_script.write_text("@exit /b 1\n", encoding="utf-8")
            try:
                cmd = f'cmd /c "{fail_script}"'
                with pytest.raises(EnhancementError, match="LLM falló"):
                    llm_plan([], llm_cmd=cmd)
            finally:
                fail_script.unlink(missing_ok=True)
        else:
            with pytest.raises(EnhancementError, match="LLM falló"):
                llm_plan([], llm_cmd="exit 1")


# ===================================================================
# Integration tests (ffmpeg only, fast)
# ===================================================================


def _create_test_video(path: Path, duration: float = 4.0) -> Path:
    """Crea un vídeo sintético 1080x1920@30 con audio sine."""
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i",
        f"testsrc2=size=1080x1920:rate=30:duration={duration}",
        "-f", "lavfi", "-i",
        f"sine=frequency=440:duration={duration}:sample_rate=48000",
        "-c:v", "libx264", "-crf", "28", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "64k",
        "-shortest", str(path),
    ], check=True, capture_output=True, timeout=60)
    return path


def _words_for_4s():
    """2 palabras sobre 4 s, para captions."""
    return [
        {"w": "Hola", "s": 0.5, "e": 1.5},
        {"w": "mundo", "s": 2.5, "e": 3.5},
    ]


class TestIntegrationDryRun:
    """run_autopilot dry_run → manifest sin archivos escritos."""

    def test_dry_run_rule(self, tmp_path):
        from voxera.autopilot import run_autopilot
        src = _create_test_video(tmp_path / "src.mp4")
        manifest = run_autopilot(
            str(src), str(tmp_path / "out.mp4"),
            planner="rule", dry_run=True,
        )
        assert manifest["version"] == 1
        assert manifest["planner"] == "rule"
        assert "spec" in manifest
        assert "stages" in manifest
        assert manifest["spec"]["version"] == 1

    def test_dry_run_with_words_json(self, tmp_path):
        from voxera.autopilot import run_autopilot
        src = _create_test_video(tmp_path / "src.mp4")
        words_path = tmp_path / "words.json"
        words_path.write_text(
            json.dumps({"words": _words_for_4s()}),
            encoding="utf-8",
        )
        manifest = run_autopilot(
            str(src), str(tmp_path / "out.mp4"),
            planner="rule", dry_run=True,
            words_json=str(words_path),
        )
        assert manifest["planner"] == "rule"


class TestIntegrationRuleRun:
    """run_autopilot planner=rule con words_json → output existe, QA OK."""

    def test_rule_run_with_words(self, tmp_path):
        from voxera.autopilot import run_autopilot
        src = _create_test_video(tmp_path / "src.mp4")
        out = tmp_path / "out.mp4"
        words_path = tmp_path / "words.json"
        words_path.write_text(
            json.dumps({"words": _words_for_4s()}),
            encoding="utf-8",
        )
        manifest = run_autopilot(
            str(src), str(out),
            planner="rule",
            words_json=str(words_path),
            max_dur=45.0,
            level="medium",
        )
        assert out.exists(), "output file should exist"
        qa = manifest.get("qa", {})
        assert "dur_out" in qa
        # duración output ≈ duración input (cutsilence on sine = no cuts)
        assert abs(qa["dur_out"] - 4.0) < 1.0
        # manifest file written
        manifest_file = Path(str(out) + ".manifest.json")
        assert manifest_file.exists()


class TestIntegrationAB:
    """run_ab con planner_a=rule, planner_b=rule → dos outputs + manifest."""

    def test_ab_both_rule(self, tmp_path):
        from voxera.autopilot import run_ab
        src = _create_test_video(tmp_path / "src.mp4")
        prefix = str(tmp_path / "short")
        words_path = tmp_path / "words.json"
        words_path.write_text(
            json.dumps({"words": _words_for_4s()}),
            encoding="utf-8",
        )
        # Run A/B (both rule — no LLM dependency, pass words_json)
        ab_manifest = run_ab(
            str(src), prefix,
            planner_a="rule",
            planner_b="rule",
            max_dur=45.0,
            level="medium",
            model="base",
            words_json=str(words_path),
        )
        # Both outputs should exist
        assert Path(f"{prefix}.rule.mp4").exists()
        assert Path(f"{prefix}.llm.mp4").exists()
        # ab_manifest.json should exist
        ab_file = Path(f"{prefix}.ab_manifest.json")
        assert ab_file.exists()
        # Checklist present
        assert len(ab_manifest["checklist"]) == 4
        # Both variants have QA
        for label in ("rule", "llm"):
            v = ab_manifest["variants"][label]
            assert "qa" in v
            assert "output" in v

    def test_ab_graceful_llm_failure(self, tmp_path):
        """Si planner_b falla, el harness no crashea."""
        from voxera.autopilot import run_ab
        src = _create_test_video(tmp_path / "src.mp4")
        prefix = str(tmp_path / "short")
        words_path = tmp_path / "words.json"
        words_path.write_text(
            json.dumps({"words": _words_for_4s()}),
            encoding="utf-8",
        )
        ab_manifest = run_ab(
            str(src), prefix,
            planner_a="rule",
            planner_b="llm",
            llm_cmd="comando-inexistente-xyz-123",  # fallará → failure aislado
            max_dur=45.0,
            words_json=str(words_path),
        )
        # rule variant should succeed (words available for captions)
        assert ab_manifest["variants"]["rule"]["qa"]
        # llm variant should have error
        assert "error" in ab_manifest["variants"]["llm"]
        # No crash
        assert len(ab_manifest["checklist"]) == 4


# ===================================================================
# TestCLI
# ===================================================================


class TestCLI:
    """Tests de las ventanas de ayuda del CLI."""

    def test_autopilot_help(self):
        env = dict(os.environ)
        root = Path(__file__).resolve().parent.parent
        env["PYTHONPATH"] = str(root / "src")
        proc = subprocess.run(
            [sys.executable, "-m", "voxera.cli", "autopilot", "--help"],
            capture_output=True, text=True, env=env, timeout=10,
        )
        assert proc.returncode == 0
        assert "raw→short" in proc.stdout.lower() or "plan" in proc.stdout.lower()

    def test_autopilot_run_help(self):
        env = dict(os.environ)
        root = Path(__file__).resolve().parent.parent
        env["PYTHONPATH"] = str(root / "src")
        proc = subprocess.run(
            [sys.executable, "-m", "voxera.cli", "autopilot", "run", "--help"],
            capture_output=True, text=True, env=env, timeout=10,
        )
        assert proc.returncode == 0
        assert "--planner" in proc.stdout
        assert "--dry-run" in proc.stdout

    def test_autopilot_ab_help(self):
        env = dict(os.environ)
        root = Path(__file__).resolve().parent.parent
        env["PYTHONPATH"] = str(root / "src")
        proc = subprocess.run(
            [sys.executable, "-m", "voxera.cli", "autopilot", "ab", "--help"],
            capture_output=True, text=True, env=env, timeout=10,
        )
        assert proc.returncode == 0
        assert "--planner-a" in proc.stdout
        assert "--planner-b" in proc.stdout
