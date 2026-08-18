#!/usr/bin/env python3
"""Generate kinetic ASS subtitles, title cards, and punch-in cuts from words.json."""

import argparse
import json
import math
import os
import re
import sys

# ─── constants ───────────────────────────────────────────────────────────────

# Conjunto por defecto (voxera). Para contenido nuevo pasar --keywords <file>:
# un JSON con lista de strings, o lista separada por comas. Las keywords son
# CONTENIDO del vídeo, no del script: se colorean en las subs y el conjunto
# correcto lo decide el paso semántico (ver SKILL.md paso 4b).
DEFAULT_KEYWORDS = [
    "voz", "diferencia", "antes", "despues", "mejor",
    "limpia", "limpio", "eco", "ruido", "saturacion",
    "respiraciones", "video", "voxera",
    "efecto", "sonido", "herramienta", "editar", "edicion", "gratis", "pagar",
]
EMPHASIS_WORDS = DEFAULT_KEYWORDS  # alias backward-compat

SCALE_CYCLE = [1.0, 1.14, 1.07, 1.21]
CUT_TARGET = 2.8
CUT_MIN, CUT_MAX = 2.4, 3.4
CUT_ALIGN_TOL = 0.6

ANIM_KINETIC = (
    r"{\fad(60,80)\fscx70\fscy70"
    r"\t(0,120,\fscx105\fscy105)"
    r"\t(120,220,\fscx100\fscy100)}"
)
ANIM_TITLE = (
    r"{\fad(150,180)\fscx60\fscy60"
    r"\t(0,160,\fscx108\fscy108)"
    r"\t(160,300,\fscx100\fscy100)}"
)

GREEN_TK = "&H007FFF00&"
YELLOW = "&H0000FFFF&"

# ─── helpers ─────────────────────────────────────────────────────────────────

def _strip_punct(w: str) -> str:
    return re.sub(r"[.,!?;:]+", "", w).strip()

def _norm(w: str) -> str:
    return re.sub(r"[áÁ]", "a", re.sub(r"[éÉ]", "e", re.sub(r"[íÍ]", "i",
        re.sub(r"[óÓ]", "o", re.sub(r"[úÚ]", "u", re.sub(r"[.,!?;:\s]+", "", w).lower()))))).lower()

def is_emphasis(w: str, keywords=None) -> bool:
    return _norm(w) in (keywords if keywords is not None else EMPHASIS_WORDS)

def fmt_time(sec: float) -> str:
    """H:MM:SS.cc"""
    sec = max(0.0, sec)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    cs = round((sec - int(sec)) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

# ─── card grouping ───────────────────────────────────────────────────────────

def group_cards(words):
    """Split words into cards (max 4, break on gap > 0.45 or punctuation end)."""
    cards = []
    cur = []
    for w in words:
        if cur:
            last = cur[-1]
            gap = w["s"] - last["e"]
            prev_ends_punct = bool(re.search(r"[.!?]$", last["w"]))
            prev_ends_comma = bool(re.search(r",$", last["w"]))
            if len(cur) >= 4 or gap > 0.45 or prev_ends_punct or prev_ends_comma:
                cards.append(cur)
                cur = []
        cur.append(w)
    if cur:
        cards.append(cur)
    return cards

# ─── ASS header / styles ────────────────────────────────────────────────────

def script_info():
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "WrapStyle: 2\n"
        "ScaledBorderAndShadow: yes\n"
    )

V4_FORMAT = (
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
    "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
    "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
    "Alignment, MarginL, MarginR, MarginV, Encoding\n"
)

STYLE_KINETIC = (
    "Style: Kinetic,Arial Black,84,&H0000FFFF,&H00DCDCDC,"
    "&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,7,2,2,60,60,430,1\n"
)
STYLE_TITLE = (
    "Style: Title,Arial Black,62,&H00FFFFFF,&H00FFFFFF,"
    "&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,5,2,2,60,60,640,1\n"
)

# ─── subs.ass generation ────────────────────────────────────────────────────

def build_karaoke(card, keywords=None):
    """Build the karaoke tag string for a card of words."""
    start = card[0]["s"]
    parts = []
    for i, w in enumerate(card):
        cs_val = round((w["e"] - (card[i - 1]["e"] if i > 0 else start)) * 100)
        if cs_val < 0:
            cs_val = 0
        raw = _strip_punct(w["w"])
        if is_emphasis(w["w"], keywords):
            text = f"{{\\c&H007FFF00&}}{raw}{{\\c&H00FFFFFF&}}"
        else:
            text = raw
        parts.append(f"{{\\k{cs_val}}}{text}")
    return " ".join(parts)

def make_subs(words, duration, keywords=None):
    lines = [script_info(), "[V4+ Styles]\n", V4_FORMAT, STYLE_KINETIC, "[Events]\n",
             "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"]
    cards = group_cards(words)
    for card in cards:
        card_start = card[0]["s"]
        card_end = card[-1]["e"] + 0.25
        if card_end - card_start < 0.7:
            card_end = card_start + 0.7
        karo = build_karaoke(card, keywords)
        text = f"{ANIM_KINETIC}{karo}"
        lines.append(
            f"Dialogue: 0,{fmt_time(card_start)},{fmt_time(card_end)},Kinetic,,0,0,0,,{text}\n"
        )
    return "".join(lines)

# ─── titles.ass generation ──────────────────────────────────────────────────

def _find_anchor_word(words, target_norm, duration, fallback_pct=0.6):
    """Find first word whose normalized form matches or starts with target_norm."""
    for w in words:
        n = _norm(w["w"])
        if n == target_norm or n.startswith(target_norm):
            return w
    # fallback
    if target_norm == "pagar":
        return words[-1]
    target_t = duration * fallback_pct
    best = min(words, key=lambda w: abs((w["s"] + w["e"]) / 2 - target_t))
    return best


def make_titles(words, duration, content_mode="default"):
    lines = [script_info(), "[V4+ Styles]\n", V4_FORMAT, STYLE_TITLE, "[Events]\n",
             "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"]

    if content_mode == "v2":
        # T1 – anchor on "efecto"
        anchor1 = _find_anchor_word(words, "efecto", duration, fallback_pct=0.6)
        t1_start = anchor1["s"] - 0.2
        t1_end = anchor1["s"] + 2.4
        t1_text = r"este {\fnGeorgia\fs58\i1\c&H007FFF00&}efecto{\r} de sonido"
        lines.append(
            f"Dialogue: 0,{fmt_time(t1_start)},{fmt_time(t1_end)},Title,,0,0,0,,{ANIM_TITLE}{t1_text}\n"
        )

        # T2 – anchor on "pagar"
        anchor2 = _find_anchor_word(words, "pagar", duration)
        t2_start = anchor2["e"] - 1.8
        t2_end = min(anchor2["e"] + 1.2, duration)
        t2_text = r"sin pagar {\fnGeorgia\fs58\i1\c&H0000FFFF&}nada{\r}"
        lines.append(
            f"Dialogue: 0,{fmt_time(t2_start)},{fmt_time(t2_end)},Title,,0,0,0,,{ANIM_TITLE}{t2_text}\n"
        )
    else:
        # Original titles for backward compat
        anchor1 = _find_anchor_word(words, "diferencia", duration, fallback_pct=0.6)
        t1_start = anchor1["s"] - 0.2
        t1_end = anchor1["s"] + 2.4
        t1_text = f"escucha la {{\\fnGeorgia\\fs58\\i1\\c&H007FFF00&}}diferencia{{\\r}}"
        lines.append(
            f"Dialogue: 0,{fmt_time(t1_start)},{fmt_time(t1_end)},Title,,0,0,0,,{ANIM_TITLE}{t1_text}\n"
        )

        last = words[-1]
        t2_start = last["e"] - 1.8
        t2_end = min(last["e"] + 1.2, duration)
        t2_text = f"el mismo tú, {{\\fnGeorgia\\fs58\\i1\\c&H0000FFFF&}}solo que mejor{{\\r}}"
        lines.append(
            f"Dialogue: 0,{fmt_time(t2_start)},{fmt_time(t2_end)},Title,,0,0,0,,{ANIM_TITLE}{t2_text}\n"
        )

    return "".join(lines)

# ─── cuts.json generation ────────────────────────────────────────────────────

def make_cuts(words, duration):
    cuts_t = []
    t = 0.0
    idx = 0
    while True:
        target = t + CUT_TARGET
        if target >= duration:
            break
        # find closest word start within ±0.6s
        best_diff = CUT_ALIGN_TOL + 1
        best_t = target
        for w in words:
            d = abs(w["s"] - target)
            if d < best_diff:
                best_diff = d
                best_t = w["s"]
        if best_diff <= CUT_ALIGN_TOL:
            cuts_t.append(best_t)
            t = best_t
        else:
            cuts_t.append(target)
            t = target

    cuts_t = [ct for ct in cuts_t if ct < duration - 0.1]  # trim near-end cuts

    # build segments
    boundaries = [0.0] + cuts_t + [duration]
    segments = []
    for i in range(len(boundaries) - 1):
        seg = {"start": boundaries[i], "end": boundaries[i + 1], "scale": SCALE_CYCLE[i % len(SCALE_CYCLE)]}
        segments.append(seg)

    return {"cuts": cuts_t, "segments": segments}

# ─── main ───────────────────────────────────────────────────────────────────

def main():
    base = os.path.dirname(os.path.abspath(__file__))
    project = os.path.dirname(base)
    default_out = os.path.join(project, "out")

    parser = argparse.ArgumentParser(description="Generate subs, titles, cuts from words.json")
    parser.add_argument("--input", default=None,
                        help="Path to words.json (default: <outdir>/words.json)")
    parser.add_argument("--outdir", default=None,
                        help="Output directory (default: ../out)")
    parser.add_argument("--content", default="default", choices=["default", "v2"],
                        help="Title content set (default=original, v2=new titles)")
    parser.add_argument("--keywords", default=None,
                        help="Keywords file (JSON list) o lista separada por comas; "
                             "default: conjunto embebido")
    args = parser.parse_args()

    out_dir = args.outdir or default_out
    os.makedirs(out_dir, exist_ok=True)

    words_path = args.input or os.path.join(out_dir, "words.json")
    with open(words_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    words = data["words"]
    duration = data["duration"]

    keywords = None
    if args.keywords:
        kw_path = args.keywords
        if os.path.exists(kw_path) and kw_path.endswith(".json"):
            with open(kw_path, "r", encoding="utf-8") as f:
                keywords = json.load(f)
        else:
            keywords = [k.strip() for k in kw_path.split(",") if k.strip()]
        print(f"Keywords ({len(keywords)}): {keywords}")

    subs = make_subs(words, duration, keywords=keywords)
    titles = make_titles(words, duration, content_mode=args.content)
    cuts = make_cuts(words, duration)

    for name, content in [("subs.ass", subs), ("titles.ass", titles), ("cuts.json", json.dumps(cuts, indent=2))]:
        path = os.path.join(out_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  wrote {path}")

if __name__ == "__main__":
    main()
