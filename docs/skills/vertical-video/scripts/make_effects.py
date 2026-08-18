#!/usr/bin/env python3
"""Generate emoji sticker PNGs + overlays.json from effects.json + words.json."""

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("ERROR: Pillow required. Run with .venv-video", file=sys.stderr)
    sys.exit(1)

FFPROBE = r"C:/ffmpeg/bin/ffprobe.exe"
EMOJI_FONT = r"C:/Windows/Fonts/seguiemj.ttf"
EMOJI_SIZE = 170
CANVAS_SIZE = 230
OVERLAY_X = 760
OVERLAY_Y = 1150


def _norm(text: str) -> str:
    """Normalize: lowercase, remove accents, remove punctuation/spaces."""
    t = text.lower()
    # Remove accents
    for a, b in [("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"),
                 ("ü", "u"), ("ñ", "n"), ("Á", "a"), ("É", "e"), ("Í", "i"),
                 ("Ó", "o"), ("Ú", "u"), ("Ü", "u"), ("Ñ", "n")]:
        t = t.replace(a, b)
    t = re.sub(r"[^a-z0-9]", "", t)
    return t


def get_duration(path):
    r = subprocess.run(
        [FFPROBE, "-v", "error",
         "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True
    )
    return float(r.stdout.strip())


def render_emoji(emoji_char, output_path):
    """Render an emoji to a transparent PNG. Returns True if pixels are colorful."""
    font = ImageFont.truetype(EMOJI_FONT, EMOJI_SIZE)
    img = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.text(
        (CANVAS_SIZE // 2, CANVAS_SIZE // 2),
        emoji_char,
        font=font,
        embedded_color=True,
        anchor="mm"
    )
    # Verify the image has color (not blank)
    pixels = list(img.getdata())
    # Get RGB values of non-transparent pixels
    rgb_pixels = [(r, g, b) for r, g, b, a in pixels if a > 10]
    if not rgb_pixels:
        print(f"  ERROR: rendered PNG has no visible pixels for emoji '{emoji_char}'", file=sys.stderr)
        sys.exit("ABORT: Font rendered empty image. Check seguiemj.ttf availability.")
    # Check color range
    r_vals = [p[0] for p in rgb_pixels]
    g_vals = [p[1] for p in rgb_pixels]
    b_vals = [p[2] for p in rgb_pixels]
    max_range = max(max(r_vals) - min(r_vals), max(g_vals) - min(g_vals), max(b_vals) - min(b_vals))
    if max_range < 40:
        print(f"  ERROR: rendered PNG is nearly flat (range={max_range}) for emoji '{emoji_char}'", file=sys.stderr)
        sys.exit("ABORT: Font produced flat/uniform image. Check seguiemj.ttf.")
    img.save(output_path, "PNG")
    return True


def find_word_in_transcript(words, search_text):
    """Find the FIRST word in the transcript whose normalized text contains the search_text normalized."""
    search_norm = _norm(search_text)
    for w in words:
        word_norm = _norm(w["w"])
        if search_norm in word_norm:
            return w
    return None


def main():
    parser = argparse.ArgumentParser(description="Generate emoji overlays from effects.json")
    parser.add_argument("--words", required=True, help="Path to words.json")
    parser.add_argument("--effects", required=True, help="Path to effects.json")
    parser.add_argument("--outdir", default="new", help="Output directory")
    args = parser.parse_args()

    with open(args.words, "r", encoding="utf-8") as f:
        words_data = json.load(f)
    with open(args.effects, "r", encoding="utf-8") as f:
        effects_data = json.load(f)

    words = words_data["words"]
    duration = words_data.get("duration", None)

    emoji_dir = os.path.join(args.outdir, "emoji")
    os.makedirs(emoji_dir, exist_ok=True)

    overlays = []

    for idx, eff in enumerate(effects_data["effects"]):
        search = eff["word"]
        emoji_char = eff["emoji"]

        match = find_word_in_transcript(words, search)
        if match is None:
            print(f"  WARNING: word '{search}' not found in transcript, skipping.")
            continue

        # Anchor: word.s - 0.10 to word.e + 0.70, clamped to [0, duration]
        t_start = max(0.0, match["s"] - 0.10)
        t_end = match["e"] + 0.70
        if duration is not None:
            t_end = min(t_end, duration)

        if t_end <= t_start:
            print(f"  WARNING: invalid time range for '{search}' ({t_start:.2f}-{t_end:.2f}), skipping.")
            continue

        # Render PNG
        png_name = f"{idx}_{search}.png"
        png_path = os.path.join(emoji_dir, png_name)
        render_emoji(emoji_char, png_path)
        print(f"  [{idx}] '{search}' -> {emoji_char} | {t_start:.2f}-{t_end:.2f}s | {png_path}")

        overlays.append({
            "png": f"emoji/{png_name}",
            "t_start": round(t_start, 3),
            "t_end": round(t_end, 3),
            "x": OVERLAY_X,
            "y": OVERLAY_Y,
        })

    # Write overlays.json
    out_path = os.path.join(args.outdir, "overlays.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"overlays": overlays}, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {out_path} with {len(overlays)} overlays")


if __name__ == "__main__":
    main()
