"""Normal acceptance pipeline driver for voxera.

Orchestrates the APS normal run for every feature file:

    feature file -> gherkin-parser -> JSON IR
                  -> gherkin-ir-dry-checker (advisory report)
                  -> acceptance-entrypoint-generator -> generated entry points
                  -> pytest (project test runner)

Usage: python -m acceptance.pipeline [features-dir] [--pytest-args <args>]

Default features dir: ``features/`` at the project root. Work artifacts are
project-local under ``build/acceptance/``. Generated tests stay separate from
unit tests (``tests/``).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from acceptance.generator import slug

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FEATURES_DIR = PROJECT_ROOT / "features"
IR_DIR = PROJECT_ROOT / "build" / "acceptance" / "ir"
DRY_DIR = PROJECT_ROOT / "build" / "acceptance" / "dry"
GENERATED_DIR = PROJECT_ROOT / "acceptance" / "generated"
TMP_DIR = PROJECT_ROOT / "build" / "acceptance" / "tmp"
PARSER_ENV = "GHERKIN_PARSER"


def find_parser() -> str:
    """Locate the APS-supplied gherkin-parser (Babashka preferred)."""
    configured = os.environ.get(PARSER_ENV)
    if configured:
        return configured
    on_path = shutil.which("gherkin-parser")
    if on_path:
        return on_path
    home_bin = Path.home() / "swarmforge-bin" / "gherkin-parser"
    if home_bin.exists():
        return str(home_bin)
    raise FileNotFoundError(
        "gherkin-parser not found; install the APS Babashka tools "
        "(see github.com/unclebob/Acceptance-Pipeline-Specification)"
    )


def find_features(features_dir: Path) -> list[Path]:
    if not features_dir.is_dir():
        return []
    return sorted(features_dir.glob("*.feature"))


def clean_build() -> None:
    """Reset project-local acceptance build artifacts for a fresh run."""
    for path in [IR_DIR, DRY_DIR, GENERATED_DIR, TMP_DIR]:
        shutil.rmtree(path, ignore_errors=True)
    for path in [IR_DIR, DRY_DIR, GENERATED_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def _wrap_for_windows(command: list[str]) -> list[str]:
    """Run bash-wrapper tools through bash on Windows."""
    if os.name == "nt":
        bash = shutil.which("bash") or r"C:\Program Files\Git\bin\bash.exe"
        return [bash, *command]
    return command


def parse_feature(feature: Path, ir_path: Path) -> None:
    parser = find_parser()
    subprocess.run(
        _wrap_for_windows([parser, str(feature), str(ir_path)]),
        check=True,
        capture_output=True,
        text=True,
    )


def find_dry_checker() -> str | None:
    """Locate the APS-supplied gherkin-ir-dry-checker, or ``None``."""
    on_path = shutil.which("gherkin-ir-dry-checker")
    if on_path:
        return on_path
    home_bin = Path.home() / "swarmforge-bin" / "gherkin-ir-dry-checker"
    return str(home_bin) if home_bin.exists() else None


def dry_check(ir_path: Path, dry_path: Path) -> None:
    """Run the advisory IR-DRY checker; report-only, never fails the run."""
    checker = find_dry_checker()
    if checker is None:
        print(f"note: gherkin-ir-dry-checker not found; skipping dry check for {ir_path.name}")
        return
    dry_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        _wrap_for_windows([checker, str(ir_path), str(dry_path)]),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(f"warning: dry check failed for {ir_path.name}: {proc.stderr.strip()}")
        return
    report = dry_path.read_text(encoding="utf-8")
    if "duplicate" in report.lower() or "near-duplicate" in report.lower():
        print(f"note: dry-check report for {ir_path.name}:")
        print(report[:2000])


def generate_entry_points(ir_path: Path, feature: Path) -> None:
    env = os.environ.copy()
    env["ACCEPTANCE_FEATURE_PATH"] = str(feature)
    env["PYTHONPATH"] = str(PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.run(
        [sys.executable, "-m", "acceptance.generator", str(ir_path), str(GENERATED_DIR)],
        check=True,
        env=env,
    )


def run_generated_tests(pytest_args: list[str]) -> int:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(GENERATED_DIR), "-q", *pytest_args],
        capture_output=True,
        text=True,
        env=env,
    )
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.returncode != 0 and proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    return proc.returncode


def run_acceptance(features_dir: Path = FEATURES_DIR, pytest_args: list[str] | None = None) -> int:
    features = find_features(features_dir)
    if not features:
        print(f"no feature files found under {features_dir}")
        return 1
    clean_build()
    for feature in features:
        ir_path = IR_DIR / f"{slug(str(feature))}.json"
        dry_path = DRY_DIR / f"{slug(str(feature))}.json"
        print(f"parsing {feature}")
        parse_feature(feature, ir_path)
        dry_check(ir_path, dry_path)
        print(f"generating entry points for {feature.name}")
        generate_entry_points(ir_path, feature)
    return run_generated_tests(list(pytest_args or []))


def _extract_pytest_args(args: list[str]) -> tuple[list[str], list[str]] | int:
    """Pull ``--pytest-args <value>`` pairs out of ``args``.

    Returns ``(pytest_args, remaining)`` or an exit code when a flag
    appears without a value.
    """
    pytest_args: list[str] = []
    rest: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--pytest-args":
            if i + 1 >= len(args):
                print(f"unknown option: {arg}", file=sys.stderr)
                return 2
            pytest_args = args[i + 1].split()
            i += 2
            continue
        rest.append(arg)
        i += 1
    return pytest_args, rest


def parse_cli_args(
    args: list[str],
) -> tuple[Path, list[str]] | int:
    """Parse pipeline CLI args into (features_dir, pytest_args).

    Returns an exit code when the invocation is malformed.
    """
    extracted = _extract_pytest_args(args)
    if isinstance(extracted, int):
        return extracted
    pytest_args, rest = extracted
    for arg in rest:
        if arg.startswith("-"):
            print(f"unknown option: {arg}", file=sys.stderr)
            return 2
    if len(rest) > 1:
        print(
            "usage: python -m acceptance.pipeline [features-dir] [--pytest-args <args>]",
            file=sys.stderr,
        )
        return 2
    features_dir = Path(rest[0]) if rest else FEATURES_DIR
    return features_dir, pytest_args


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    parsed = parse_cli_args(args)
    if isinstance(parsed, int):
        return parsed
    features_dir, pytest_args = parsed
    return run_acceptance(features_dir, pytest_args)


if __name__ == "__main__":
    sys.exit(main())
