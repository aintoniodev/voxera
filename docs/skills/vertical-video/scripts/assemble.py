#!/usr/bin/env python3
"""Assemble final pipeline: punch-ins, subtitles, titles, flashes, comparison."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import re

# ─── paths (all relative to CWD = tmp/pipeline-demo) ───────────────────────

FFMPEG = r"C:/ffmpeg/bin/ffmpeg.exe"
FFPROBE = r"C:/ffmpeg/bin/ffprobe.exe"
PYTHON = sys.executable  # python del entorno activo (portable; antes: .venv hardcodeado)
SYSTEM_FONT = r"C:/Windows/Fonts/ariblk.ttf"
DEFAULT_OUT = "out"

FRAME_TIMES = [2, 5, 8, 11]

QUALITY = {
    "fast": {"preset": "medium", "crf": 19, "abitrate": "160k"},
    "max":  {"preset": "slow", "crf": 15, "abitrate": "320k"},
}
PREVIEW_ENC = {"preset": "veryfast", "crf": 20, "abitrate": "128k"}


def run(cmd, label=""):
    print(f"\n▶ {label}: {' '.join(str(c) for c in cmd[:5])}...")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  STDERR (last 3000 chars):\n{r.stderr[-3000:]}")
        sys.exit(f"FAIL: {label} exited with {r.returncode}")
    print(f"  ✓ done")
    return r


def get_duration(path):
    r = subprocess.run(
        [FFPROBE, "-v", "error",
         "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True
    )
    return float(r.stdout.strip())


def write_fc_script(text, label=""):
    """Write filter_complex text to a temp file, return its path."""
    fd, path = tempfile.mkstemp(suffix=".txt", prefix=f"fc_{label}_")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    return path


def classify_soft_flashes(cuts, words):
    """Return list of cut times that qualify for a soft flash."""
    qualified = []
    for ct in cuts:
        # Condition (a): silence >= 0.7s just before cut
        # Find the last word ending before ct
        prev_end = 0.0
        prev_word_text = ""
        for w in words:
            if w["e"] <= ct:
                prev_end = w["e"]
                prev_word_text = w["w"]
            else:
                break
        gap = ct - prev_end

        # Condition (b): word immediately before cut ends in . ! ?
        punct_match = bool(re.search(r"[.!?]$", prev_word_text.strip()))

        if gap >= 0.7 or punct_match:
            qualified.append(ct)
    return qualified


def main():
    parser = argparse.ArgumentParser(description="Assemble final pipeline outputs")
    parser.add_argument("--outdir", default=DEFAULT_OUT,
                        help="Output/input directory (default: out)")
    parser.add_argument("--flash", default="off", choices=["hard", "soft", "off"],
                        help="Flash mode: hard=every cut, soft=idea-change only, off=none (default)")
    parser.add_argument("--overlays", default=None,
                        help="Path to overlays.json for emoji sticker overlays")
    parser.add_argument("--cmp-label", default="COLOR + REFRAME",
                        help="Middle comparison panel label")
    parser.add_argument("--skip-make-subs", action="store_true",
                        help="Skip regenerating subs/titles/cuts (use existing)")
    parser.add_argument("--quality", default="max", choices=["fast", "max"],
                        help="Encode quality (default: max = slow crf15 aac320k)")
    parser.add_argument("--preview", action="store_true",
                        help="Iteración: 540x960 veryfast crf20 → *_preview.mp4 "
                             "(omite comparativa; cortes idénticos al final)")
    parser.add_argument("--delivery", action="store_true",
                        help="Además de 04_final, generar 04_delivery.mp4 (crf18 +fastdecode, "
                             "para subir/WhatsApp — la plataforma re-encodea igual)")
    parser.add_argument("--input-video", default=None,
                        help="Override source video (e.g. 02t_tonal.mp4 remux with tonal audio)")
    args = parser.parse_args()

    OUT = args.outdir
    FONT_LOCAL = f"{OUT}/ariblk.ttf"
    SFX = "_preview" if args.preview else ""

    # Input: prefer --input-video override, then compressed/graded
    if args.input_video:
        INPUT_GRADED = args.input_video
        print(f"  Using override input: {INPUT_GRADED}")
    else:
        candidates = ([f"02c_compressed{SFX}.mp4", "02c_compressed.mp4"] if args.preview
                      else ["02c_compressed.mp4", f"02c_compressed_preview.mp4"])
        candidates += [f"02_graded{SFX}.mp4", "02_graded.mp4"]
        INPUT_GRADED = next((f"{OUT}/{c}" for c in candidates if os.path.exists(f"{OUT}/{c}")), None)
        if INPUT_GRADED is None:
            sys.exit(f"FAIL: no se encuentra 02c_compressed/02_graded en {OUT}")
        print(f"  Using input: {INPUT_GRADED}")
    INPUT_RAW = f"{OUT}/01_raw.mp4"
    SUBS_ASS = f"{OUT}/subs.ass"
    TITLES_ASS = f"{OUT}/titles.ass"
    CUTS_JSON = f"{OUT}/cuts.json"
    WORDS_JSON = f"{OUT}/words.json"

    OUT_03 = f"{OUT}/03_subs_zoom{SFX}.mp4"
    OUT_04 = f"{OUT}/04_final{SFX}.mp4"
    OUT_00 = f"{OUT}/00_comparativa{SFX}.mp4"
    FRAMES_DIR = f"{OUT}/frames_check"
    OV_F = 0.5 if args.preview else 1.0
    if args.preview:
        enc = PREVIEW_ENC
        print("  MODO PREVIEW (540×960, iteración rápida) — el final se renderiza sin --preview")
    else:
        enc = QUALITY[args.quality]
        print(f"  Calidad: {args.quality} (preset {enc['preset']} crf {enc['crf']} aac {enc['abitrate']})")

    os.makedirs(FRAMES_DIR, exist_ok=True)

    # Copy font locally so drawtext can use it without C: colon issues
    if not os.path.exists(FONT_LOCAL):
        shutil.copy2(SYSTEM_FONT, FONT_LOCAL)
        print(f"  Copied font → {FONT_LOCAL}")

    # ─── Step 1: regenerate subs/titles/cuts (unless skipped) ─────────────
    if not args.skip_make_subs:
        print("=" * 60)
        print("Step 1: Regenerate subs.ass, titles.ass, cuts.json")
        print("=" * 60)
        # Pass through to make_subs.py with same outdir
        make_subs_cmd = [PYTHON, "src/make_subs.py", "--outdir", OUT]
        if os.path.exists(os.path.join(OUT, "words.json")):
            make_subs_cmd.extend(["--input", os.path.join(OUT, "words.json")])
        run(make_subs_cmd, label="make_subs")

    with open(CUTS_JSON, "r", encoding="utf-8") as f:
        cuts_data = json.load(f)
    segments = cuts_data["segments"]
    cuts = cuts_data["cuts"]

    duration = get_duration(INPUT_GRADED)
    if segments:
        segments[-1]["end"] = duration
    print(f"  Video duration: {duration:.6f}s | segments: {len(segments)} | cuts: {len(cuts)}")

    # ─── Determine flash cuts ──────────────────────────────────────────────
    if args.flash == "soft":
        with open(WORDS_JSON, "r", encoding="utf-8") as f:
            words_data = json.load(f)
        flash_cuts = classify_soft_flashes(cuts, words_data["words"])
        print(f"  Soft flash: {len(flash_cuts)} of {len(cuts)} cuts qualified → {flash_cuts}")
    elif args.flash == "hard":
        flash_cuts = cuts
        print(f"  Hard flash: {len(flash_cuts)} cuts")
    else:
        flash_cuts = []
        print(f"  Flash: off")

    # ─── Load overlays if provided ──────────────────────────────────────
    overlays_data = []
    if args.overlays and os.path.exists(args.overlays):
        with open(args.overlays, "r", encoding="utf-8") as f:
            ov = json.load(f)
        overlays_data = ov.get("overlays", [])
        print(f"  Overlays: {len(overlays_data)} loaded")

    # ─── Step 2: 03_subs_zoom.mp4 ──────────────────────────────────────────
    print("\n" + "=" * 60)
    print("Step 2: 03_subs_zoom.mp4  (punch-ins + kinetic subs)")
    print("=" * 60)

    fp = []
    vl, al = [], []
    for i, seg in enumerate(segments):
        s, e, k = seg["start"], seg["end"], seg["scale"]
        base_w, base_h = (540, 960) if args.preview else (1080, 1920)
        sw, sh = int(base_w * k), int(base_h * k)
        fp.append(
            f"[0:v]trim=start={s}:end={e},setpts=PTS-STARTPTS,"
            f"scale={sw}:{sh}:flags=lanczos,crop={base_w}:{base_h},setsar=1,format=yuv420p[v{i}]"
        )
        fp.append(
            f"[0:a]atrim=start={s}:end={e},asetpts=PTS-STARTPTS[a{i}]"
        )
        vl.append(f"[v{i}]")
        al.append(f"[a{i}]")

    n = len(segments)
    concat_inputs = "".join(f"[v{i}][a{i}]" for i in range(n))
    fp.append(f"{concat_inputs}concat=n={n}:v=1:a=1[vc][ac]")
    last_v = "vc"
    subs_filter = f"[{last_v}]subtitles=filename={SUBS_ASS}[vsub]"
    fp.append(subs_filter)
    last_v = "vsub"

    # Apply overlays (emoji stickers) after subtitles, chained
    if overlays_data:
        for oi, ov in enumerate(overlays_data):
            ts = ov["t_start"]
            te = ov["t_end"]
            x = int(ov["x"] * OV_F)
            y = int(ov["y"] * OV_F)
            drift = int(25 * OV_F)
            ov_in_idx = 1 + oi  # overlay inputs start at index 1 (after main video)
            if OV_F != 1.0:
                # preview: escalar el PNG del sticker a la resolución reducida
                ssize = int(230 * OV_F)
                fp.append(f"[{ov_in_idx}:v]scale={ssize}:{ssize}[ovi{oi}]")
                ov_label = f"[ovi{oi}]"
            else:
                ov_label = f"[{ov_in_idx}:v]"
            # Pop-in: drift up by 25px (or 12px preview) over 0.3s from t_start
            fp.append(
                f"[{last_v}]{ov_label}overlay=x={x}:y='if(lte(t-{ts},0),{y + drift},{y}-{drift}*min(1\, (t-{ts})/0.3))':enable='between(t\, {ts}\, {te})'[vov{oi}]"
            )
            last_v = f"vov{oi}"

    fp.append(f"[{last_v}]copy[vout]")

    fc_text = ";\n".join(fp)
    fc_path = write_fc_script(fc_text, "03")

    ffmpeg_cmd = [
        FFMPEG, "-y", "-i", INPUT_GRADED,
    ]
    # Add overlay image inputs
    for ov in overlays_data:
        png_path = os.path.join(OUT, ov["png"])
        ffmpeg_cmd.extend(["-loop", "1", "-framerate", "30", "-i", png_path])

    ffmpeg_cmd.extend([
        "-filter_complex_script", fc_path,
        "-map", "[vout]", "-map", "[ac]",
        "-c:v", "libx264", "-preset", enc["preset"], "-crf", str(enc["crf"]),
        "-c:a", "aac", "-b:a", enc["abitrate"], "-movflags", "+faststart",
        "-shortest",
        OUT_03,
    ])

    try:
        run(ffmpeg_cmd, label="render_03")
    finally:
        os.unlink(fc_path)

    # ─── Step 3: 04_final.mp4 ──────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"Step 3: 04_final.mp4  (titles + flashes({args.flash}) + fades)")
    print("=" * 60)

    d3 = get_duration(OUT_03)

    vf_parts = [
        f"[0:v]subtitles=filename={TITLES_ASS}",
        f"fade=t=in:st=0:d=0.25",
        f"fade=t=out:st={d3 - 0.5:.3f}:d=0.5",
    ]

    for ct in flash_cuts:
        if args.flash == "hard":
            vf_parts.append(
                f"drawbox=color=white@0.85:t=fill:enable='between(t\\,{ct}\\,{ct + 0.09})'"
            )
        elif args.flash == "soft":
            vf_parts.append(
                f"drawbox=color=white@0.45:t=fill:enable='between(t\\,{ct}\\,{ct + 0.067})'"
            )

    # build chain: [0:v]filter1,filter2,...,filterN[v]
    vf = ",".join(vf_parts) + "[v]"
    vf_path = write_fc_script(vf, "04")

    try:
        run([
            FFMPEG, "-y", "-i", OUT_03,
            "-filter_complex_script", vf_path,
            "-map", "[v]",
            "-map", "0:a",
            "-c:v", "libx264", "-preset", enc["preset"], "-crf", str(enc["crf"]),
            "-c:a", "copy", "-movflags", "+faststart",
            OUT_04,
        ], label="render_04")
    finally:
        os.unlink(vf_path)

    # ─── Step 3.5: 04_delivery.mp4 (copia de distribución, solo final) ───
    if args.delivery and not args.preview:
        print("\n" + "=" * 60)
        print("Step 3.5: 04_delivery.mp4  (crf18 + fastdecode para subir/WhatsApp)")
        print("=" * 60)
        run([
            FFMPEG, "-y", "-i", OUT_04,
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-tune", "fastdecode",
            "-c:a", "copy", "-movflags", "+faststart",
            f"{OUT}/04_delivery.mp4",
        ], label="delivery_copy")

    # ─── Step 4: 00_comparativa.mp4 ─────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"Step 4: 00_comparativa.mp4  (RAW | {args.cmp_label} | FINAL)")
    print("=" * 60)

    if args.preview:
        print("  (preview: se omite la comparativa — es artefacto de entrega, no de iteración)")
    else:
        dt = (
            f"fontsize=30:fontcolor=white:box=1:boxcolor=black@0.55:"
            f"boxborderw=10:x=(w-text_w)/2:y=14:fontfile={FONT_LOCAL}"
        )

        fc_cmp = (
            f"[0:v]scale=360:202:flags=lanczos,pad=360:640:0:(oh-ih)/2,"
            f"setsar=1,drawtext=text='RAW':{dt}[p0];\n"
            f"[1:v]scale=360:640:flags=lanczos,setsar=1,"
            f"drawtext=text='{args.cmp_label}':{dt}[p1];\n"
            f"[2:v]scale=360:640:flags=lanczos,setsar=1,"
            f"drawtext=text='FINAL':{dt}[p2];\n"
            f"[p0][p1][p2]xstack=inputs=3:layout=0_0|w0_0|w0+w1_0[v]"
        )
        fc_path = write_fc_script(fc_cmp, "00")

        try:
            run([
                FFMPEG, "-y",
                "-i", INPUT_RAW, "-i", INPUT_GRADED, "-i", OUT_04,
                "-filter_complex_script", fc_path,
                "-map", "[v]", "-map", "2:a",
                "-c:v", "libx264", "-preset", "medium", "-crf", "21",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
                OUT_00,
            ], label="render_00")
        finally:
            os.unlink(fc_path)

    # ─── Step 5: verification frames ─────────────────────────────────────────
    print("\n" + "=" * 60)
    print("Step 5: Extract verification frames")
    print("=" * 60)

    for t in FRAME_TIMES:
        if t >= d3:
            print(f"  frame_{t}: skipped (beyond video duration {d3:.1f}s)")
            continue
        run([
            FFMPEG, "-y", "-ss", str(t), "-i", OUT_04,
            "-frames:v", "1", "-q:v", "2",
            f"{FRAMES_DIR}/frame_{t:02d}.jpg",
        ], label=f"frame_{t}")

    # ─── Verification summary ───────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    for path, label in [
        (OUT_03, "03_subs_zoom"),
        (OUT_04, "04_final"),
    ]:
        if not os.path.exists(path):
            continue
        d = get_duration(path)
        sz = os.path.getsize(path) / (1024 * 1024)
        print(f"  {label}: {d:.3f}s, {sz:.1f} MB")
    if os.path.exists(OUT_00):
        d = get_duration(OUT_00)
        sz = os.path.getsize(OUT_00) / (1024 * 1024)
        print(f"  00_comparativa: {d:.3f}s, {sz:.1f} MB")
    if not args.preview and args.delivery and os.path.exists(f"{OUT}/04_delivery.mp4"):
        sz = os.path.getsize(f"{OUT}/04_delivery.mp4") / (1024 * 1024)
        print(f"  04_delivery: {sz:.1f} MB (crf18 fastdecode, para subir)")

    for t in FRAME_TIMES:
        fp = f"{FRAMES_DIR}/frame_{t:02d}.jpg"
        if os.path.exists(fp):
            sz = os.path.getsize(fp)
            ok = "✓" if sz > 30_000 else "✗ TOO SMALL"
            print(f"  frame_{t:02d}.jpg: {sz:,} bytes {ok}")
        else:
            print(f"  frame_{t:02d}.jpg: MISSING")

    print(f"\n  Flash mode: {args.flash}")
    print(f"  Flash count: {len(flash_cuts)}")
    print("\n✅ Assembly complete!")


if __name__ == "__main__":
    main()
