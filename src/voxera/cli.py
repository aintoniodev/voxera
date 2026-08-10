"""The voxera command-line interface (Track 0 + Track 1).

Thin adapter over the core: parse args, dispatch, map failures to exit codes.

Exit codes (docs/SPECS-fase2.md):
    0  OK
    1  processing error (EnhancementError)
    2  usage error / unknown backend
    20 VOXERA_NO_SPEECH (VAD speech ratio < 5%)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from voxera import __version__
from voxera.analyze import analyze
from voxera.determinism import dump_report
from voxera.dsp import DEFAULT_PRESET, preset_names
from voxera.enhance import EnhancementError, UnknownBackendError, enhance
from voxera.errors import NO_SPEECH_EXIT_CODE, NoSpeechError
from voxera.master import master_file

PROG = "voxera"


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--device",
        choices=("auto", "cpu", "cuda"),
        default="auto",
        help="device policy (default: auto — CUDA if available)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="print the system block (backend, model, device, torch, RTF)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Voice/podcast post-production powered by pluggable neural backends.",
    )
    parser.add_argument("--version", action="version", version=f"voxera {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    # --- enhance -----------------------------------------------------------
    enhance_parser = subparsers.add_parser(
        "enhance",
        help="enhance an audio file (NN backend + optional master pipeline)",
        description="Load an audio file, run one pluggable backend's enhancement, "
        "and write the improved file. With --preset the full master pipeline "
        "always runs after the backend; without it, backend-only (back-compat).",
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
    enhance_parser.add_argument(
        "--preset",
        nargs="?",
        const=DEFAULT_PRESET,
        default=None,
        help="voice preset — ALWAYS runs the full master pipeline after the NN "
        f"(default preset: {DEFAULT_PRESET})",
    )
    enhance_parser.add_argument(
        "--dsp-only",
        action="store_true",
        help="pipeline without any neural network (master puro)",
    )
    enhance_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the plan and exit 0 without writing OUT or loading the NN",
    )
    enhance_parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="inference seed (determinism on CPU)",
    )
    _add_common(enhance_parser)

    # --- master ------------------------------------------------------------
    master_parser = subparsers.add_parser(
        "master",
        help="voice mastering ONLY: DSP pipeline, no neural network",
        description="Run the frozen voice-mastering pipeline (DC removal, "
        "high-pass, vocal EQ, de-esser, compressor, limiter, loudness) "
        "without any neural network. Byte-equivalent deterministic.",
    )
    master_parser.add_argument("input", help="source audio file (WAV)")
    master_parser.add_argument(
        "-o", "--output", required=True, help="output path for the mastered audio"
    )
    master_parser.add_argument(
        "--preset",
        default=DEFAULT_PRESET,
        choices=preset_names(),
        help=f"voice preset (default: {DEFAULT_PRESET})",
    )
    master_parser.add_argument(
        "--lufs",
        type=float,
        default=None,
        help="override the preset loudness target (LUFS-I)",
    )
    master_parser.add_argument(
        "--dehum",
        action="store_true",
        help="notch the dominant mains hum (50/100/150 Hz) detected in the input",
    )
    master_parser.add_argument(
        "--no-eq", action="store_true", help="disable vocal EQ and de-esser"
    )
    master_parser.add_argument(
        "--no-comp", action="store_true", help="disable the compressor"
    )
    master_parser.add_argument(
        "--no-limit", action="store_true", help="disable the limiter"
    )
    master_parser.add_argument(
        "--no-loudnorm", action="store_true", help="disable loudness normalization"
    )
    master_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the plan and exit 0 without writing OUT",
    )
    _add_common(master_parser)

    # --- analyze -----------------------------------------------------------
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="analyze an audio file (analysis ONLY, never modifies audio)",
        description="Report loudness, VAD, SNR, spectral bands, hum, RT60, "
        "DC offset, plosives, breaths, mouth clicks and a heuristic noise "
        "type — every estimate with confidence.",
    )
    analyze_parser.add_argument("input", help="source audio file (WAV)")
    analyze_parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="write the JSON report to this path (in addition to stdout)",
    )
    analyze_parser.add_argument(
        "--format",
        choices=("tty", "json"),
        default="tty",
        help="report format (default: tty human summary)",
    )
    _add_common(analyze_parser)

    return parser


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _fmt(value, digits: int = 1) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def _analyze_tty(report: dict) -> str:
    inp = report["input"]
    ch = {1: "mono", 2: "stereo"}.get(inp["channels"], f"{inp['channels']}ch")
    loud = report["loudness"]
    voice = report["voice"]
    spec = report["spectral"]
    hum = spec["hum_db"]
    room = report["room"]
    art = report["artifacts"]
    nt = art["noise_type"]
    hum_str = f" {hum['dominant']} ({_fmt(hum['h50'] if hum.get('h50') is not None else hum.get('h100'))})" if hum.get("dominant") else ""
    snr = voice["snr_db"]
    snr_str = f"SNR {_fmt(snr['value'])} dB (conf {snr['confidence']:.2f})" if snr["value"] is not None else "SNR n/a"
    rt = f"RT60 {_fmt(room['rt60_s'], 2)} s (conf {room['confidence']:.2f}) · {room['reverb']}" if room["rt60_s"] is not None else "RT60 n/a"
    return "\n".join(
        [
            "",
            f"Input:      {inp['format']} · {inp['sample_rate']} Hz · {ch} · {inp['duration_s']:.2f} s",
            f"Loudness:   LUFS-I {_fmt(loud['integrated_lufs'])} · LUFS-S {_fmt(loud['short_term_lufs'])}"
            f" · LRA {_fmt(loud['lra'])} · TP {_fmt(loud['true_peak_db'])} dBTP · RMS {_fmt(loud['rms_db'])} dB",
            f"Voice:      speech {report['voice']['speech_ratio'] * 100:.0f}% · {snr_str}",
            f"Spectral:   rumble {_fmt(spec['rumble_db'])} · hum{hum_str} · mud {_fmt(spec['mud_db'])}"
            f" · boxiness {_fmt(spec['boxiness_db'])} · presence {_fmt(spec['presence_db'])} · air {_fmt(spec['air_db'])}",
            f"Room:       {rt}",
            f"Artifacts:  DC {_fmt(art['dc_offset_db'])} dBFS · plosives {art['plosives']['candidates']}"
            f" ({art['plosives']['confidence']:.2f}) · breaths {art['breaths']['count']}"
            f" · clicks {art['mouth_click_candidates']['count']} ({art['mouth_click_candidates']['confidence']:.2f})",
            f"Noise type: {nt['type']} (conf {nt['confidence']:.2f})"
            + (" · stationary" if nt["stationary"] else "")
            + (" · tonal" if nt["tonal"] else "")
            + (" · broadband" if nt["broadband"] else ""),
        ]
    )


def _print_verbose(result: dict) -> None:
    device = result.get("device", "cpu")
    print(f"Backend:  {result.get('backend') or '—'}")
    print(f"Model:    {result.get('model') or '—'}")
    print(f"Device:   {device}")
    try:
        import torch

        print(f"Torch:    {'CUDA ' + torch.version.cuda if torch.cuda.is_available() else 'CPU'}")
    except Exception:  # noqa: BLE001
        print("Torch:    n/a")
    for key in ("rtf_model", "rtf_pipeline", "rtf_e2e", "rtf_master"):
        if result.get(key) is not None:
            print(f"RTF:      {result[key]:.3f} ({key.removeprefix('rtf_')})", file=sys.stderr)


def _print_stages(result: dict) -> None:
    for stage in result.get("stages", []):
        print(f"  ✓ {stage}")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def _cmd_enhance(args) -> int:
    try:
        result = enhance(
            Path(args.input),
            Path(args.output),
            backend=args.backend,
            model=args.model,
            attn_limit_db=args.attn_limit_db,
            pf=args.pf,
            preset=args.preset,
            dsp_only=args.dsp_only,
            dry_run=args.dry_run,
            device=args.device,
            seed=args.seed,
        )
    except UnknownBackendError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return 2
    except NoSpeechError as exc:
        print(f"{PROG}: {exc}", file=sys.stderr)
        return NO_SPEECH_EXIT_CODE
    except EnhancementError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return 1

    if isinstance(result, dict):
        if args.dry_run:
            print(result["plan"])
        else:
            if args.verbose:
                _print_verbose(result)
            print(f"✓ {result['output']}")
            if args.verbose:
                _print_stages(result)
            else:
                print(f"  stages: {', '.join(result['stages'])}")
    else:
        print(result)
    return 0


def _cmd_master(args) -> int:
    dehum_hz = None
    if args.dehum and not args.dry_run:
        try:
            hum = analyze(args.input, device=args.device)["spectral"]["hum_db"]
        except EnhancementError:
            hum = {}
        dominant = hum.get("dominant")
        dehum_hz = {"50 Hz": 50, "100 Hz": 100, "150 Hz": 150}.get(dominant or "", None)
        if dehum_hz is None and not args.verbose:
            print("note: no dominant hum detected; --dehum no-op", file=sys.stderr)
    try:
        result = master_file(
            Path(args.input),
            Path(args.output),
            preset_name=args.preset,
            lufs=args.lufs,
            dehum_hz=dehum_hz,
            no_eq=args.no_eq,
            no_comp=args.no_comp,
            no_limit=args.no_limit,
            no_loudnorm=args.no_loudnorm,
            device=args.device,
            dry_run=args.dry_run,
        )
    except NoSpeechError as exc:
        print(f"{PROG}: {exc}", file=sys.stderr)
        return NO_SPEECH_EXIT_CODE
    except EnhancementError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(result["plan"])
    else:
        if args.verbose:
            _print_verbose(result)
            _print_stages(result)
        else:
            print(f"✓ {result['output']} · LUFS {_fmt(result['lufs_out'])}"
                  f" · TP {_fmt(result['true_peak_out'])} dBTP"
                  f" · {result['duration_s']:.2f} s")
    return 0


def _cmd_analyze(args) -> int:
    try:
        report = analyze(args.input, device=args.device)
    except EnhancementError as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return 1
    text = dump_report(report)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    if args.format == "json" or args.output:
        print(text, end="")
    else:
        print(_analyze_tty(report))
    if args.verbose:
        sys_block = report["system"]
        print(
            f"system: voxera {sys_block['voxera_version']} · pipeline "
            f"{sys_block['pipeline_version']} · {sys_block['device']} · "
            f"{sys_block['processing_time_s']:.3f} s",
            file=sys.stderr,
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    # Windows console/pipes default to cp1252 and crash on '✓' etc.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # pragma: no cover - exotic streams
            pass
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "enhance":
        return _cmd_enhance(args)
    if args.command == "master":
        return _cmd_master(args)
    if args.command == "analyze":
        return _cmd_analyze(args)

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
