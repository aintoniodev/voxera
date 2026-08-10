"""The voxera command-line interface.

The CLI is a thin adapter over the core: it parses arguments, calls
:func:`voxera.enhance.enhance`, and maps failures to exit codes and
stderr messages. All behavior lives in the core so it stays drivable and
testable from the terminal.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from voxera.enhance import UnknownBackendError, enhance
PROG = "voxera"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Voice/podcast post-production powered by pluggable neural backends.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    enhance_parser = subparsers.add_parser(
        "enhance",
        help="enhance an audio file and write the improved file",
        description="Load an audio file, run one pluggable backend's enhancement, "
        "and write the improved file.",
    )
    enhance_parser.add_argument("input", help="source audio file (WAV)")
    enhance_parser.add_argument(
        "-o", "--output", required=True, help="output path for the enhanced audio"
    )
    enhance_parser.add_argument(
        "--backend",
        default="deepfilternet",
        help="enhancement backend (default: deepfilternet); the core validates the name",
    )
    enhance_parser.add_argument(
        "--model",
        default=None,
        help="backend model override (default: backend's own default)",
    )
    enhance_parser.add_argument(
        "--attn-limit-db",
        type=float,
        default=None,
        help="dpdfnet attenuation limit in dB (default: 24)",
    )
    enhance_parser.add_argument(
        "--pf",
        action="store_true",
        default=None,
        help="deepfilternet post-filter (default: off — the measured Pareto winner)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "enhance":
        try:
            output = enhance(
                Path(args.input),
                Path(args.output),
                backend=args.backend,
                model=args.model,
                attn_limit_db=args.attn_limit_db,
                pf=args.pf,
            )
        except UnknownBackendError as exc:
            print(f"{PROG}: error: {exc}", file=sys.stderr)
            return 2
        except EnhancementError as exc:
            print(f"{PROG}: error: {exc}", file=sys.stderr)
            return 1
        print(output)
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
