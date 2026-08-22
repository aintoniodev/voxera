"""Project step handlers: connect Gherkin step text to the voxera CLI.

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
    """Resolve the voxera CLI command: installed ``voxera`` or the module fallback."""
    installed = shutil.which("voxera")
    if installed:
        return [installed]
    return [sys.executable, "-m", "voxera.cli"]


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
        raise AssertionFailure("no voxera command has been run in this scenario")
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


@REGISTRY.register(r"^I run voxera enhance <([A-Za-z0-9_]+)> -o <([A-Za-z0-9_]+)>$")
def when_run_enhance(text, params, example, world):
    """Run `voxera enhance <input> -o <output>` and capture its outcome."""
    input_name, output_name = params.values()
    input_path = world["paths"].get(input_name, _path_for(world, input_name))
    output_path = _path_for(world, output_name)
    _run_ims(
        ["enhance", str(input_path), "-o", str(output_path)],
        world,
    )


@REGISTRY.register(
    r"^I run voxera enhance <([A-Za-z0-9_]+)> -o <([A-Za-z0-9_]+)> --backend <([A-Za-z0-9_]+)>$"
)
def when_run_enhance_backend(text, params, example, world):
    """Run `voxera enhance <input> -o <output> --backend <backend>`."""
    input_name, output_name, backend = params.values()
    input_path = world["paths"].get(input_name, _path_for(world, input_name))
    output_path = _path_for(world, output_name)
    _run_ims(
        ["enhance", str(input_path), "-o", str(output_path), "--backend", backend],
        world,
    )


@REGISTRY.register(r"^the exit status is <([A-Za-z0-9_]+)>$")
def then_exit_status(text, params, example, world):
    """Assert the captured voxera exit status equals the example value."""
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


def _require_file(path: Path, what: str) -> None:
    """Raise :class:`AssertionFailure` unless ``path`` is an existing file."""
    if not path.is_file():
        raise AssertionFailure(f"expected {what} to exist: {path}")


@REGISTRY.register(r"^the output file <([A-Za-z0-9_]+)> exists$")
def then_output_exists(text, params, example, world):
    (filename,) = params.values()
    _require_file(_path_for(world, filename), "output file")


@REGISTRY.register(r"^the output file <([A-Za-z0-9_]+)> does not exist$")
def then_output_missing(text, params, example, world):
    (filename,) = params.values()
    path = _path_for(world, filename)
    if path.exists():
        raise AssertionFailure(f"expected no output file, but found: {path}")


def _assert_wav_header(path: Path) -> None:
    """Assert ``path`` carries a RIFF/WAVE header; raise :class:`AssertionFailure`."""
    try:
        header = path.read_bytes()[:12]
    except OSError as exc:
        raise AssertionFailure(f"cannot read output file {path}: {exc}") from exc
    if len(header) < 12 or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
        raise AssertionFailure(f"output file is not a wav file: {path}")


@REGISTRY.register(r"^the output file <([A-Za-z0-9_]+)> is a wav file$")
def then_output_is_wav(text, params, example, world):
    (filename,) = params.values()
    path = _path_for(world, filename)
    _require_file(path, "output wav file")
    _assert_wav_header(path)


def _assert_stream_contains(run: dict, stream: str, needle: str, what: str) -> None:
    """Assert ``needle`` appears in the captured ``stream`` of a CLI run."""
    if needle not in run[stream]:
        raise AssertionFailure(f"{what} does not contain '{needle}': {run[stream]!r}")


@REGISTRY.register(r"^stdout contains <([A-Za-z0-9_]+)>$")
def then_stdout_contains(text, params, example, world):
    (needle,) = params.values()
    _assert_stream_contains(_require_run(world), "stdout", needle, "stdout")


@REGISTRY.register(r"^stderr contains <([A-Za-z0-9_]+)>$")
def then_stderr_contains(text, params, example, world):
    (needle,) = params.values()
    _assert_stream_contains(_require_run(world), "stderr", needle, "stderr")


# ---------------------------------------------------------------------------
# Fase 2: speech-like/silent fixtures, master, analyze, pipeline enhance
# ---------------------------------------------------------------------------


def _write_speech_like_wav(path: Path, seconds: float = 2.0) -> None:
    """48 kHz mono speech-like WAV (passes the webrtcvad 5% gate)."""
    import soundfile as sf

    import tests.synth as s

    sf.write(str(path), s.speech_like(seconds), 48000, subtype="PCM_16")


def _write_silent_wav(path: Path, seconds: float = 1.0) -> None:
    """48 kHz mono silent WAV (triggers VOXERA_NO_SPEECH)."""
    import numpy as np
    import soundfile as sf

    sf.write(str(path), np.zeros(int(seconds * 48000), np.float32), 48000)


@REGISTRY.register(r"^the input audio file <([A-Za-z0-9_]+)> is speech-like$")
def given_input_speech_like(text, params, example, world):
    """Create a 48 kHz speech-like WAV input (passes the no-speech gate)."""
    (filename,) = params.values()
    path = _path_for(world, filename)
    _write_speech_like_wav(path)
    world["paths"][filename] = path


@REGISTRY.register(r"^the input audio file <([A-Za-z0-9_]+)> is silent$")
def given_input_silent(text, params, example, world):
    """Create a 48 kHz silent WAV input (VAD speech ratio 0)."""
    (filename,) = params.values()
    path = _path_for(world, filename)
    _write_silent_wav(path)
    world["paths"][filename] = path


@REGISTRY.register(r"^I run voxera master <([A-Za-z0-9_]+)> -o <([A-Za-z0-9_]+)>$")
def when_run_master(text, params, example, world):
    """Run `voxera master <input> -o <output>` (default preset)."""
    input_name, output_name = params.values()
    input_path = world["paths"].get(input_name, _path_for(world, input_name))
    output_path = _path_for(world, output_name)
    _run_ims(["master", str(input_path), "-o", str(output_path)], world)


@REGISTRY.register(
    r"^I run voxera master <([A-Za-z0-9_]+)> -o <([A-Za-z0-9_]+)> --preset <([A-Za-z0-9_]+)>$"
)
def when_run_master_preset(text, params, example, world):
    """Run `voxera master <input> -o <output> --preset <preset>`."""
    input_name, output_name, preset = params.values()
    input_path = world["paths"].get(input_name, _path_for(world, input_name))
    output_path = _path_for(world, output_name)
    _run_ims(
        ["master", str(input_path), "-o", str(output_path), "--preset", preset],
        world,
    )


@REGISTRY.register(r"^I run voxera master <([A-Za-z0-9_]+)> -o <([A-Za-z0-9_]+)> --dry-run$")
def when_run_master_dry_run(text, params, example, world):
    """Run `voxera master <input> -o <output> --dry-run` (plan, no write)."""
    input_name, output_name = params.values()
    input_path = world["paths"].get(input_name, _path_for(world, input_name))
    output_path = _path_for(world, output_name)
    _run_ims(["master", str(input_path), "-o", str(output_path), "--dry-run"], world)


@REGISTRY.register(r"^I run voxera analyze <([A-Za-z0-9_]+)> --format json$")
def when_run_analyze_json(text, params, example, world):
    """Run `voxera analyze <input> --format json`."""
    (input_name,) = params.values()
    input_path = world["paths"].get(input_name, _path_for(world, input_name))
    _run_ims(["analyze", str(input_path), "--format", "json"], world)


@REGISTRY.register(r"^I run voxera enhance <([A-Za-z0-9_]+)> -o <([A-Za-z0-9_]+)> --dsp-only$")
def when_run_enhance_dsp_only(text, params, example, world):
    """Run `voxera enhance <input> -o <output> --dsp-only` (no NN)."""
    input_name, output_name = params.values()
    input_path = world["paths"].get(input_name, _path_for(world, input_name))
    output_path = _path_for(world, output_name)
    _run_ims(
        ["enhance", str(input_path), "-o", str(output_path), "--dsp-only"],
        world,
    )


def _wav_info(path: Path) -> tuple[int, str, int]:
    import soundfile as sf

    info = sf.info(str(path))
    return info.samplerate, info.subtype, info.channels


@REGISTRY.register(r"^the output file <([A-Za-z0-9_]+)> is a 48 kHz 24-bit mono wav file$")
def then_output_48k24_mono(text, params, example, world):
    """Assert the output is a 48 kHz PCM 24-bit mono WAV (frozen policy)."""
    (filename,) = params.values()
    path = _path_for(world, filename)
    _require_file(path, "output wav file")
    sr, subtype, channels = _wav_info(path)
    if (sr, subtype, channels) != (48000, "PCM_24", 1):
        raise AssertionFailure(
            f"expected 48 kHz PCM_24 mono wav, got {sr} Hz {subtype} {channels}ch"
        )


@REGISTRY.register(r"^the output file <([A-Za-z0-9_]+)> differs from the input$")
def then_output_differs_from_input(text, params, example, world):
    """Assert the output bytes differ from the source input file."""
    (filename,) = params.values()
    out_path = _path_for(world, filename)
    run = _require_run(world)
    args = run["args"]
    input_name = next((a for a in args if a.endswith(".wav") and a != str(out_path)), None)
    if input_name is None:
        raise AssertionFailure("cannot infer the input path from the captured run")
    input_path = Path(input_name)
    _require_file(out_path, "output wav file")
    if input_path.read_bytes() == out_path.read_bytes():
        raise AssertionFailure("output file is identical to the input file")


@REGISTRY.register(r"^the input audio file <([A-Za-z0-9_]+)> is not a wav$")
def given_input_not_wav(text, params, example, world):
    """Create a non-WAV input file (unsupported-format path)."""
    (filename,) = params.values()
    path = _path_for(world, filename)
    path.write_bytes(b"this is not a wav file")
    world["paths"][filename] = path


@REGISTRY.register(r"^the input audio file <([A-Za-z0-9_]+)> is speech-like stereo 44.1 kHz$")
def given_input_speech_like_stereo_441(text, params, example, world):
    """Create a 44.1 kHz stereo speech-like WAV (resample + downmix path)."""
    import numpy as np
    import soundfile as sf

    import tests.synth as s

    (filename,) = params.values()
    path = _path_for(world, filename)
    x = s.speech_like(2.0)
    sf.write(str(path), np.stack([x, 0.8 * x], axis=1), 44100, subtype="PCM_16")
    world["paths"][filename] = path


@REGISTRY.register(r"^I run voxera enhance <([A-Za-z0-9_]+)>$")
def when_run_enhance_no_output(text, params, example, world):
    """Run `voxera enhance <input>` without -o (usage error path)."""
    (input_name,) = params.values()
    input_path = world["paths"].get(input_name, _path_for(world, input_name))
    _run_ims(["enhance", str(input_path)], world)


@REGISTRY.register(r"^I run voxera enhance -o <([A-Za-z0-9_]+)>$")
def when_run_enhance_no_input(text, params, example, world):
    """Run `voxera enhance -o <output>` without an input (usage error path)."""
    (output_name,) = params.values()
    output_path = _path_for(world, output_name)
    _run_ims(["enhance", "-o", str(output_path)], world)


@REGISTRY.register(r"^the input audio file <([A-Za-z0-9_]+)> has long gaps$")
def given_input_long_gaps(text, params, example, world):
    """Speech 1s + gap 2s + speech 1s + gap 1.2s + speech 1s (Track 2 fixture)."""
    import soundfile as sf

    import tests.synth as s

    (filename,) = params.values()
    path = _path_for(world, filename)
    sf.write(str(path), s.long_gaps(), 48000, subtype="PCM_16")
    world["paths"][filename] = path


@REGISTRY.register(r"^the input audio file <([A-Za-z0-9_]+)> is speech-like clipped$")
def given_input_clipped(text, params, example, world):
    """Speech-like signal hard-clipped at 0.95 (restore --declip fixture)."""
    import numpy as np
    import soundfile as sf

    import tests.synth as s

    (filename,) = params.values()
    path = _path_for(world, filename)
    x = np.clip(s.speech_like(2.0) * 3.0, -0.95, 0.95).astype(np.float32)
    sf.write(str(path), x, 48000, subtype="PCM_16")
    world["paths"][filename] = path


@REGISTRY.register(r"^I run voxera score <([A-Za-z0-9_]+)>$")
def when_run_score(text, params, example, world):
    """Run `voxera score <input>` (TTY summary)."""
    (input_name,) = params.values()
    input_path = world["paths"].get(input_name, _path_for(world, input_name))
    _run_ims(["score", str(input_path)], world)


@REGISTRY.register(r"^I run voxera score <([A-Za-z0-9_]+)> --ref <([A-Za-z0-9_]+)> --format json$")
def when_run_score_ref(text, params, example, world):
    """Run `voxera score <input> --ref <ref> --format json`."""
    input_name, ref_name = params.values()
    input_path = world["paths"].get(input_name, _path_for(world, input_name))
    ref_path = world["paths"].get(ref_name, _path_for(world, ref_name))
    _run_ims(["score", str(input_path), "--ref", str(ref_path), "--format", "json"], world)


@REGISTRY.register(r"^I run voxera silence <([A-Za-z0-9_]+)> -o <([A-Za-z0-9_]+)> --level <([A-Za-z0-9_]+)>$")
def when_run_silence(text, params, example, world):
    """Run `voxera silence <input> -o <output> --level <level>`."""
    input_name, output_name, level = params.values()
    input_path = world["paths"].get(input_name, _path_for(world, input_name))
    output_path = _path_for(world, output_name)
    _run_ims(["silence", str(input_path), "-o", str(output_path), "--level", level], world)


@REGISTRY.register(r"^I run voxera restore <([A-Za-z0-9_]+)> -o <([A-Za-z0-9_]+)> --declip$")
def when_run_restore_declip(text, params, example, world):
    """Run `voxera restore <input> -o <output> --declip`."""
    input_name, output_name = params.values()
    input_path = world["paths"].get(input_name, _path_for(world, input_name))
    output_path = _path_for(world, output_name)
    _run_ims(["restore", str(input_path), "-o", str(output_path), "--declip"], world)


@REGISTRY.register(r"^I run voxera restore <([A-Za-z0-9_]+)> -o <([A-Za-z0-9_]+)>$")
def when_run_restore_noop(text, params, example, world):
    """Run `voxera restore <input> -o <output>` without stages (usage error)."""
    input_name, output_name = params.values()
    input_path = world["paths"].get(input_name, _path_for(world, input_name))
    output_path = _path_for(world, output_name)
    _run_ims(["restore", str(input_path), "-o", str(output_path)], world)
