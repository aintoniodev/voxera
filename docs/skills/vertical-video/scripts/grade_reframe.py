#!/usr/bin/env python3
"""grade_reframe.py — Color grading + vertical 9:16 reframe wrapper around ffmpeg.

Produces:
  out/01_raw.mp4   — stream-copy of the source (reference "before").
  out/02_graded.mp4 — color-graded + vertical 1080×1920 with normalized audio.
"""

import argparse
import json
import os
import subprocess
import sys

FFMPEG = r"C:/ffmpeg/bin/ffmpeg.exe"
FFPROBE = r"C:/ffmpeg/bin/ffprobe.exe"

# Exact filter chain (order matters) — el scale final se parametriza por modo
VIDEO_FILTERS = (
    "eq=contrast=1.13:brightness=0.02:saturation=1.28,"
    "colorbalance=rm=0.04:bm=-0.05:rh=0.03,"
    "unsharp=5:5:0.8:5:5:0.4,"
    "crop=ih*9/16:ih:(iw-ow)/2:0,"
    "scale={W}:{H}:flags=lanczos,"
    "format=yuv420p"
)

VIDEO_FILTERS_NO_CROP = (
    "eq=contrast=1.13:brightness=0.02:saturation=1.28,"
    "colorbalance=rm=0.04:bm=-0.05:rh=0.03,"
    "unsharp=5:5:0.8:5:5:0.4,"
    "scale={W}:{H}:flags=lanczos,"
    "format=yuv420p"
)

AUDIO_FILTERS = "loudnorm=I=-16:TP=-1.5:LRA=11"

QUALITY = {
    "fast": {"preset": "medium", "crf": 19, "abitrate": "160k"},
    "max":  {"preset": "slow", "crf": 15, "abitrate": "320k"},
}


def probe(input_path: str) -> dict:
    """Return key source properties via ffprobe."""
    cmd = [
        FFPROBE, "-v", "error",
        "-show_entries", "format=duration:format=bit_rate",
        "-show_entries", "stream=width,height,r_frame_rate,codec_type,codec_name",
        "-of", "json",
        input_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def run_ffmpeg(args: list[str], label: str):
    print(f"[grade_reframe] {label}")
    print(f"  cmd: {' '.join(args)}")
    sys.stdout.flush()
    subprocess.run(args, check=True)
    print(f"  ✓ done.\n")


def main():
    parser = argparse.ArgumentParser(description="Color grade + 9:16 reframe")
    parser.add_argument("--input", default=None,
                        help="Source video file")
    parser.add_argument("--outdir", default=None,
                        help="Output directory (defaults to <script_dir>/../out)")
    parser.add_argument("--no-crop", action="store_true",
                        help="Skip horizontal-to-vertical crop (source is already 9:16)")
    parser.add_argument("--quality", default="max", choices=["fast", "max"],
                        help="Encode quality (default: max = slow crf15 aac320k)")
    parser.add_argument("--preview", action="store_true",
                        help="Iteración: 540x960 veryfast crf20 → 02_graded_preview.mp4 "
                             "(audio idéntico al final → timings válidos)")
    cli = parser.parse_args()

    # Resolve outdir
    if cli.outdir is None:
        cli.outdir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out")
    os.makedirs(cli.outdir, exist_ok=True)

    input_path = os.path.abspath(cli.input)
    raw_path = os.path.join(cli.outdir, "01_raw.mp4")
    mode = "preview" if cli.preview else "final"
    suffix = "_preview" if cli.preview else ""
    graded_path = os.path.join(cli.outdir, f"02_graded{suffix}.mp4")
    params_path = os.path.join(cli.outdir, f"02_params{suffix}.json")

    if not os.path.isfile(input_path):
        sys.exit(f"ERROR: input not found: {input_path}")

    # ── Probe source ──────────────────────────────────────────────────
    info = probe(input_path)
    duration = float(info["format"]["duration"])
    streams = {s["codec_type"]: s for s in info["streams"]}
    v = streams.get("video", {})
    r_frame_rate = v.get("r_frame_rate", "30/1")
    fps_num, fps_den = (int(x) for x in r_frame_rate.split("/"))
    fps = fps_num / fps_den
    print(f"[grade_reframe] Source: {v.get('width')}x{v.get('height')} @ {fps} fps, {duration:.2f}s\n")

    # ── Step 1: stream-copy (01_raw.mp4) ────────────────────────────────
    run_ffmpeg([
        FFMPEG, "-y", "-i", input_path,
        "-c", "copy", "-map", "0",
        raw_path,
    ], "Step 1/2 — stream-copy → 01_raw.mp4")

    # ── Step 2: color grade + reframe (02_graded.mp4) ───────────────────
    W, H = (540, 960) if cli.preview else (1080, 1920)
    vf_tpl = VIDEO_FILTERS if not cli.no_crop else VIDEO_FILTERS_NO_CROP
    vf = vf_tpl.format(W=W, H=H)
    if cli.preview:
        enc = {"preset": "veryfast", "crf": 20, "abitrate": "320k"}
    else:
        enc = QUALITY[cli.quality]
    # El audio SIEMPRE con los mismos parámetros (aac 320k @48k): el WAV de timing
    # extraído de 02_graded es idéntico en preview y final → cortes estables.
    run_ffmpeg([
        FFMPEG, "-y", "-i", input_path,
        "-vf", vf,
        "-af", AUDIO_FILTERS,
        "-c:v", "libx264", "-preset", enc["preset"], "-crf", str(enc["crf"]),
        "-c:a", "aac", "-b:a", enc["abitrate"], "-ar", "48000",
        "-r", str(fps),
        graded_path,
    ], f"Step 2/2 — grade+reframe → {os.path.basename(graded_path)} ({mode})")

    # ── Dump params ──────────────────────────────────────────────────────
    params = {
        "source": input_path,
        "duration_s": round(duration, 4),
        "source_resolution": [v.get("width"), v.get("height")],
        "source_fps": fps,
        "mode": mode,
        "output_resolution": [W, H],
        "video_filters": vf,
        "audio_filters": AUDIO_FILTERS,
        "x264_preset": enc["preset"],
        "x264_crf": enc["crf"],
    }
    with open(params_path, "w") as f:
        json.dump(params, f, indent=2)
    print(f"[grade_reframe] Params written to {params_path}")


if __name__ == "__main__":
    main()
