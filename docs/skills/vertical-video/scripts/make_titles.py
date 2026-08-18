#!/usr/bin/env python3
"""Tarjetas de título ancladas POR PALABRA desde un config JSON → titles.ass.

Anclar por palabra (no por timestamp) hace que las tarjetas sobrevivan a
re-renders con cortes/timings ligeramente distintos.

Config (--config titles_config.json):
    {"cards": [
        {"anchor": "primero", "after": 15.0, "start_delta": -0.2, "end_delta": 2.4,
         "text": r"7 sistemas {\fnGeorgia\fs52\i1\c&H007FFF00&}de IA{\r} para tu churrería"},
        {"anchor": "tranquilidad", "after": 170.0, "start_delta": -0.2, "end_delta": 1.2,
         "text": r"tiempo, dinero {\fnGeorgia\fs52\i1\c&H0000FFFF&}y tranquilidad{\r}"}
    ]}
Anclaje: primera palabra (sin puntuación, case-insensitive) con s >= after.
Tipografía combinada: Arial Black base + Georgia itálica de acento ({\\fnGeorgia\\i1}).
"""
import argparse
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from make_subs import script_info, V4_FORMAT, STYLE_TITLE, ANIM_TITLE, fmt_time  # noqa: E402

DIALOG_FMT = "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"


def find_anchor(words, text, after):
    target = text.lower().strip(".,!?;:")
    for w in words:
        if w["w"].lower().strip(".,!?;:") == target and w["s"] >= after:
            return w
    raise SystemExit(f"ERROR: ancla no encontrada en words.json: {text!r} (after={after}s). "
                     f"Revisa el transcript — el ASR pudo escribirla distinto.")


def main():
    parser = argparse.ArgumentParser(description="Title cards word-anchored → titles.ass")
    parser.add_argument("--words", required=True, help="Path to words.json")
    parser.add_argument("--config", required=True, help="Path to titles config JSON")
    parser.add_argument("--out", default=None, help="Output titles.ass (default: junto al config)")
    args = parser.parse_args()

    with open(args.words, "r", encoding="utf-8") as f:
        words = json.load(f)["words"]
    with open(args.config, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.config)), "titles.ass")

    lines = [script_info(), "[V4+ Styles]\n", V4_FORMAT, STYLE_TITLE, "[Events]\n", DIALOG_FMT]
    for card in cfg["cards"]:
        anchor = find_anchor(words, card["anchor"], card.get("after", 0.0))
        start = anchor["s"] + card.get("start_delta", -0.2)
        end = anchor["s"] + card.get("end_delta", 2.4)
        lines.append(
            f"Dialogue: 0,{fmt_time(start)},{fmt_time(end)},Title,,0,0,0,,{ANIM_TITLE}{card['text']}\n"
        )
        print(f"  card '{card['anchor']}' @ {start:.2f}-{end:.2f}s")

    with open(out, "w", encoding="utf-8") as f:
        f.write("".join(lines))
    print(f"Wrote {out} ({len(cfg['cards'])} tarjetas)")


if __name__ == "__main__":
    main()
