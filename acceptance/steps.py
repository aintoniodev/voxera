"""Project step handlers: connect Gherkin step text to the ims CLI.

Handlers follow the APS recommended style: regex patterns capture placeholder
names, and the runtime fetches each name from the current example object.
One handler covers repeated step shapes that vary only by example values;
separate handlers exist only where the wording means genuinely different
behavior (e.g. ``exists`` vs ``does not exist``).

Input/output file paths live under a per-execution temp directory
(``build/acceptance/tmp/<execution>``), project-local so the swarm never
depends on system temp.
"""

from __future__ import annotations

import math
import os
import re
import shutil
import struct
import subprocess
import sys
import wave
from pathlib import Path

from acceptance.runtime import (
    AssertionFailure,
    Execution,
    InvalidValueError,
    StepRegistry,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TMP_ROOT = PROJECT_ROOT / "build" / "acceptance" / "tmp"

SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _safe(name: str) -> str:
    return SAFE_NAME.sub("_", name)


def _make_world(execution: Execution) -> dict:
    tmp = TMP_ROOT / _safe(execution.name)
    tmp.mkdir(parents=True, exist_ok=True)
    return {"tmp": tmp, "paths": {}, "run": None}


REGISTRY = StepRegistry(world_factory=_make_world)


def _path_for(world: dict, filename: str) -> Path:
    return Path(world["tmp"]) / filename


def _write_sine_wav(path: Path, seconds: float = 1.0, rate: int = 8000) -> None:
    """Write a small valid mono 16-bit WAV (440 Hz sine) for deterministic tests."""
    frames = max(1, int(seconds * rate))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        data = bytearray()
        for i in range(frames):
            sample = int(32767 * 0.25 * math.sin(2 * math.pi * 440 * i / rate))
            data += struct.pack("<h", sample)
        wav.writeframes(bytes(data))


def _ims_command() -> list[str]:
    """Resolve the ims CLI command: installed ``ims`` or the module fallback."""
    installed = shutil.which("ims")
    if installed:
        return [installed]
    return [sys.executable, "-m", "improve_my_sound.cli"]


def _python_path() -> str:
    return os.pathsep.join([str(PROJECT_ROOT / "src"), str(PROJECT_ROOT)])


def _run_ims(args: list[str], world: dict) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = _python_path() + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        _ims_command() + args,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    world["run"] = {
        "exit": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "args": args,
    }


def _require_run(world: dict) -> dict:
    run = world.get("run")
    if run is None:
        raise AssertionFailure("no ims command has been run in this scenario")
    return run


def _parse_int(value: str, what: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise InvalidValueError(f"{what} must be an integer, got '{value}'") from exc


@REGISTRY.register(r"^the input audio file <([A-Za-z0-9_]+)>$")
def given_input_audio(text, params, example, world):
    """Create a deterministic valid WAV input file."""
    (filename,) = params.values()
    path = _path_for(world, filename)
    _write_sine_wav(path)
    world["paths"][filename] = path


@REGISTRY.register(r"^the input audio file <([A-Za-z0-9_]+)> is empty$")
def given_empty_audio(text, params, example, world):
    """Create a zero-length input file (empty audio edge case)."""
    (filename,) = params.values()
    path = _path_for(world, filename)
    path.touch()
    world["paths"][filename] = path


@REGISTRY.register(r"^I run ims enhance <([A-Za-z0-9_]+)> -o <([A-Za-z0-9_]+)>$")
def when_run_enhance(text, params, example, world):
    """Run `ims enhance <input> -o <output>` and capture its outcome."""
    input_name, output_name = params.values()
    input_path = world["paths"].get(input_name, _path_for(world, input_name))
    output_path = _path_for(world, output_name)
    _run_ims(
        ["enhance", str(input_path), "-o", str(output_path)],
        world,
    )


@REGISTRY.register(
    r"^I run ims enhance <([A-Za-z0-9_]+)> -o <([A-Za-z0-9_]+)> --backend <([A-Za-z0-9_]+)>$"
)
def when_run_enhance_backend(text, params, example, world):
    """Run `ims enhance <input> -o <output> --backend <backend>`."""
    input_name, output_name, backend = params.values()
    input_path = world["paths"].get(input_name, _path_for(world, input_name))
    output_path = _path_for(world, output_name)
    _run_ims(
        ["enhance", str(input_path), "-o", str(output_path), "--backend", backend],
        world,
    )


@REGISTRY.register(r"^the exit status is <([A-Za-z0-9_]+)>$")
def then_exit_status(text, params, example, world):
    """Assert the captured ims exit status equals the example value."""
    (expected,) = params.values()
    run = _require_run(world)
    want = _parse_int(expected, "exit status")
    if run["exit"] != want:
        raise AssertionFailure(
            f"expected exit status {want}, got {run['exit']}\n"
            f"stderr: {run['stderr'].strip()}"
        )


@REGISTRY.register(r"^the command succeeds$")
def then_command_succeeds(text, params, example, world):
    run = _require_run(world)
    if run["exit"] != 0:
        raise AssertionFailure(
            f"expected success, got exit status {run['exit']}\n"
            f"stderr: {run['stderr'].strip()}"
        )


@REGISTRY.register(r"^the command fails$")
def then_command_fails(text, params, example, world):
    run = _require_run(world)
    if run["exit"] == 0:
        raise AssertionFailure("expected failure, but the command succeeded")


@REGISTRY.register(r"^the output file <([A-Za-z0-9_]+)> exists$")
def then_output_exists(text, params, example, world):
    (filename,) = params.values()
    path = _path_for(world, filename)
    if not path.is_file():
        raise AssertionFailure(f"expected output file to exist: {path}")


@REGISTRY.register(r"^the output file <([A-Za-z0-9_]+)> does not exist$")
def then_output_missing(text, params, example, world):
    (filename,) = params.values()
    path = _path_for(world, filename)
    if path.exists():
        raise AssertionFailure(f"expected no output file, but found: {path}")


@REGISTRY.register(r"^the output file <([A-Za-z0-9_]+)> is a wav file$")
def then_output_is_wav(text, params, example, world):
    (filename,) = params.values()
    path = _path_for(world, filename)
    if not path.is_file():
        raise AssertionFailure(f"expected output wav file to exist: {path}")
    try:
        header = path.read_bytes()[:12]
    except OSError as exc:
        raise AssertionFailure(f"cannot read output file {path}: {exc}") from exc
    if len(header) < 12 or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
        raise AssertionFailure(f"output file is not a wav file: {path}")


@REGISTRY.register(r"^stdout contains <([A-Za-z0-9_]+)>$")
def then_stdout_contains(text, params, example, world):
    (needle,) = params.values()
    run = _require_run(world)
    if needle not in run["stdout"]:
        raise AssertionFailure(f"stdout does not contain '{needle}': {run['stdout']!r}")


@REGISTRY.register(r"^stderr contains <([A-Za-z0-9_]+)>$")
def then_stderr_contains(text, params, example, world):
    (needle,) = params.values()
    run = _require_run(world)
    if needle not in run["stderr"]:
        raise AssertionFailure(f"stderr does not contain '{needle}': {run['stderr']!r}")
