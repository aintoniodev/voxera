"""Step handler tests: the voxera acceptance vocabulary."""

import os
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import pytest

import acceptance.steps as steps
from acceptance.runtime import (
    AssertionFailure,
    Execution,
    InvalidValueError,
    UnsupportedStepError,
    dispatch_step,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def project_tmp(monkeypatch, tmp_path):
    """Keep step artifacts out of the project build dir during tests."""
    monkeypatch.setattr(steps, "TMP_ROOT", tmp_path)


def make_world():
    execution = Execution(scenario_index=0, example_index=1, name="test/example_1", example={})
    return steps.REGISTRY.make_world(execution)


def run_step(text, example=None, world=None):
    world = world or make_world()
    dispatch_step({"keyword": "Given", "text": text}, example or {}, steps.REGISTRY, world)
    return world


class TestInputFiles:
    def test_valid_wav_input_created(self, tmp_path, monkeypatch):
        monkeypatch.setattr(steps, "TMP_ROOT", tmp_path)
        world = run_step("the input audio file <input>", {"input": "voice.wav"})
        path = world["tmp"] / "voice.wav"
        assert path.is_file()
        with wave.open(str(path), "rb") as wav:
            assert wav.getnframes() > 0
            assert wav.getnchannels() == 1

    def test_empty_audio_input_created(self, tmp_path, monkeypatch):
        monkeypatch.setattr(steps, "TMP_ROOT", tmp_path)
        world = run_step("the input audio file <input> is empty", {"input": "empty.wav"})
        assert (world["tmp"] / "empty.wav").is_file()
        assert (world["tmp"] / "empty.wav").stat().st_size == 0


class TestRunEnhance:
    def test_run_captures_exit_status(self, tmp_path, monkeypatch):
        monkeypatch.setattr(steps, "TMP_ROOT", tmp_path)
        world = run_step("the input audio file <input>", {"input": "in.wav"})
        run_step("I run voxera enhance <input> -o <output>", {"input": "in.wav", "output": "out.wav"}, world)
        run = world["run"]
        assert run["exit"] == 0  # default backend wired -> CLI succeeds
        assert (world["tmp"] / "out.wav").exists()

    def test_run_with_backend_flag(self, tmp_path, monkeypatch):
        monkeypatch.setattr(steps, "TMP_ROOT", tmp_path)
        world = run_step("the input audio file <input>", {"input": "in.wav"})
        run_step(
            "I run voxera enhance <input> -o <output> --backend <backend>",
            {"input": "in.wav", "output": "out.wav", "backend": "dpdfnet"},
            world,
        )
        assert world["run"]["exit"] == 0

    def test_unknown_backend_reported(self, tmp_path, monkeypatch):
        monkeypatch.setattr(steps, "TMP_ROOT", tmp_path)
        world = run_step("the input audio file <input>", {"input": "in.wav"})
        run_step(
            "I run voxera enhance <input> -o <output> --backend <backend>",
            {"input": "in.wav", "output": "out.wav", "backend": "nope"},
            world,
        )
        assert "unknown backend" in world["run"]["stderr"]
        assert "dpdfnet" in world["run"]["stderr"]


class TestAssertions:
    def test_exit_status_match(self, tmp_path, monkeypatch):
        monkeypatch.setattr(steps, "TMP_ROOT", tmp_path)
        world = run_step("the input audio file <input>", {"input": "in.wav"})
        run_step("I run voxera enhance <input> -o <output>", {"input": "in.wav", "output": "out.wav"}, world)
        run_step("the exit status is <status>", {"status": "0"}, world)

    def test_exit_status_mismatch_fails(self, tmp_path, monkeypatch):
        monkeypatch.setattr(steps, "TMP_ROOT", tmp_path)
        world = run_step("the input audio file <input>", {"input": "in.wav"})
        run_step("I run voxera enhance <input> -o <output>", {"input": "in.wav", "output": "out.wav"}, world)
        with pytest.raises(AssertionFailure):
            run_step("the exit status is <status>", {"status": "1"}, world)

    def test_command_fails(self, tmp_path, monkeypatch):
        monkeypatch.setattr(steps, "TMP_ROOT", tmp_path)
        world = run_step("the input audio file <input>", {"input": "in.wav"})
        run_step(
            "I run voxera enhance <input> -o <output> --backend <backend>",
            {"input": "in.wav", "output": "out.wav", "backend": "nope"},
            world,
        )
        run_step("the command fails", {}, world)

    def test_command_succeeds_requires_exit_zero(self, tmp_path, monkeypatch):
        monkeypatch.setattr(steps, "TMP_ROOT", tmp_path)
        world = run_step("the input audio file <input>", {"input": "in.wav"})
        run_step("I run voxera enhance <input> -o <output>", {"input": "in.wav", "output": "out.wav"}, world)
        run_step("the command succeeds", {}, world)  # exit 0 -> passes now

    def test_output_does_not_exist(self, tmp_path, monkeypatch):
        monkeypatch.setattr(steps, "TMP_ROOT", tmp_path)
        world = run_step("the input audio file <input>", {"input": "in.wav"})
        run_step("I run voxera enhance <input> -o <output>", {"input": "in.wav", "output": "out.wav"}, world)
        run_step("the output file <output> does not exist", {"output": "never-written.wav"}, world)

    def test_stderr_contains(self, tmp_path, monkeypatch):
        monkeypatch.setattr(steps, "TMP_ROOT", tmp_path)
        world = make_world()
        run_step(
            "I run voxera enhance <input> -o <output>",
            {"input": "in.wav", "output": "out.wav"},
            world,
        )
        run_step("stderr contains <message>", {"message": "no such file"}, world)

    def test_assertion_before_run_fails(self, tmp_path, monkeypatch):
        monkeypatch.setattr(steps, "TMP_ROOT", tmp_path)
        world = make_world()
        with pytest.raises(AssertionFailure):
            run_step("the command fails", {}, world)

    def test_invalid_exit_status_value(self, tmp_path, monkeypatch):
        monkeypatch.setattr(steps, "TMP_ROOT", tmp_path)
        world = run_step("the input audio file <input>", {"input": "in.wav"})
        run_step("I run voxera enhance <input> -o <output>", {"input": "in.wav", "output": "out.wav"}, world)
        with pytest.raises(InvalidValueError):
            run_step("the exit status is <status>", {"status": "one"}, world)

    def test_unknown_step_unsupported(self):
        with pytest.raises(UnsupportedStepError):
            run_step("do something entirely different", {})
