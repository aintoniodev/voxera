"""The ims command-line interface.

The CLI is a thin adapter over the core: it parses arguments, calls
:func:`improve_my_sound.enhance.enhance`, and maps failures to exit codes and
stderr messages. All behavior lives in the core so it stays drivable and
testable from the terminal.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from improve_my_sound.enhance import EnhancementError, enhance
PROG = "ims"


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
        default="dpdfnet",
        help="enhancement backend (default: dpdfnet); the core validates the name",
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
            )
        except EnhancementError as exc:
            print(f"{PROG}: error: {exc}", file=sys.stderr)
            return 1
        print(output)
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
