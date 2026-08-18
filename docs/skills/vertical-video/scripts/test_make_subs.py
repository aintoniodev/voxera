#!/usr/bin/env python3
"""Tests for make_subs.py – run with: .venv/Scripts/python.exe src/test_make_subs.py"""

import json
import os
import sys
import tempfile
import re

# ensure src is importable
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
from make_subs import (
    fmt_time, group_cards, build_karaoke, make_subs, make_titles, make_cuts,
    _norm, is_emphasis,
)

# ─── fixture ──────────────────────────────────────────────────────────────────

FIXTURE_WORDS = [
    {"w": "Escucha", "s": 0.10, "e": 0.60},
    {"w": "la", "s": 0.62, "e": 0.70},
    {"w": "diferencia", "s": 0.72, "e": 1.30},
    {"w": "antes", "s": 1.35, "e": 1.80},
    {"w": "y", "s": 2.40, "e": 2.55},
    {"w": "después", "s": 2.57, "e": 3.40},
]
FIXTURE_DURATION = 6.0
FIXTURE_JSON = {"model": "small", "duration": FIXTURE_DURATION, "language": "es", "words": FIXTURE_WORDS}

def run_test(name, fn):
    try:
        fn()
        print(f"  PASS  {name}")
    except AssertionError as e:
        print(f"  FAIL  {name}: {e}")
        sys.exit(1)

# ─── tests ───────────────────────────────────────────────────────────────────

def test_group_cards_two():
    """Gap 1.80→2.40 (>0.45) must split into 2 cards."""
    cards = group_cards(FIXTURE_WORDS)
    assert len(cards) == 2, f"expected 2 cards, got {len(cards)}"
    assert len(cards[0]) == 4, f"card0 len={len(cards[0])}"
    assert len(cards[1]) == 2, f"card1 len={len(cards[1])}"

def test_subs_dialogue_count():
    subs = make_subs(FIXTURE_WORDS, FIXTURE_DURATION)
    dialogues = [l for l in subs.splitlines() if l.startswith("Dialogue:")]
    assert len(dialogues) == 2, f"expected 2 Dialogue lines, got {len(dialogues)}"

def test_subs_karaoke_tags():
    subs = make_subs(FIXTURE_WORDS, FIXTURE_DURATION)
    lines = [l for l in subs.splitlines() if l.startswith("Dialogue:")]
    first = lines[0]
    count = first.count("{\\k")
    assert count >= 4, f"expected >=4 {{\\k tags in first line, got {count}"

def test_subs_emphasis_keywords_param():
    """El énfasis se colorea según el conjunto de keywords PASADO (no hardcoded)."""
    subs = make_subs(FIXTURE_WORDS, FIXTURE_DURATION, keywords=["diferencia"])
    # check green color wrapping
    assert "{\\c&H007FFF00&}" in subs, "missing green emphasis color"
    # the keyword appears with emphasis
    assert "diferencia" in subs.lower()
    # content-agnostic: una palabra FUERA del conjunto NO se colorea
    # (el texto aparece, pero sin el wrapper de color verde)
    subs2 = make_subs(FIXTURE_WORDS, FIXTURE_DURATION, keywords=["otracosa"])
    assert "{\\c&H007FFF00&}diferencia" not in subs2

def test_cuts_segments_durations():
    cuts_data = make_cuts(FIXTURE_WORDS, FIXTURE_DURATION)
    segs = cuts_data["segments"]
    for i, seg in enumerate(segs[:-1]):
        dur = seg["end"] - seg["start"]
        assert 2.4 <= dur <= 3.4, f"segment {i} duration {dur:.2f} outside [2.4, 3.4]"
    # last segment can be shorter
    last = segs[-1]
    assert last["end"] == FIXTURE_DURATION, f"last segment end={last['end']}, expected {FIXTURE_DURATION}"
    assert segs[0]["start"] == 0.0, "first segment must start at 0"

def test_cuts_scales_cycle():
    cuts_data = make_cuts(FIXTURE_WORDS, FIXTURE_DURATION)
    for seg in cuts_data["segments"]:
        assert seg["scale"] in [1.0, 1.14, 1.07, 1.21], f"invalid scale {seg['scale']}"

def test_titles_have_two_dialogues():
    titles = make_titles(FIXTURE_WORDS, FIXTURE_DURATION)
    dialogues = [l for l in titles.splitlines() if l.startswith("Dialogue:")]
    assert len(dialogues) == 2, f"expected 2 title Dialogues, got {len(dialogues)}"

def test_title_t1_anchor():
    titles = make_titles(FIXTURE_WORDS, FIXTURE_DURATION)
    dialogues = [l for l in titles.splitlines() if l.startswith("Dialogue:")]
    # T1 should contain "diferencia"
    assert "diferencia" in dialogues[0].lower(), "T1 must mention diferencia"

def test_title_t2_last_word():
    titles = make_titles(FIXTURE_WORDS, FIXTURE_DURATION)
    dialogues = [l for l in titles.splitlines() if l.startswith("Dialogue:")]
    # T2 text should contain "mejor"
    assert "mejor" in dialogues[1].lower(), "T2 must mention mejor"

def test_time_format():
    assert fmt_time(0.0) == "0:00:00.00"
    assert fmt_time(1.5) == "0:00:01.50"
    assert fmt_time(61.23) == "0:01:01.23"
    assert fmt_time(3661.0) == "1:01:01.00"

def test_norm():
    assert _norm("diferencia,") == "diferencia"
    assert _norm("Vídeo") == "video"
    assert _norm("Saturación") == "saturacion"

def test_roundtrip_via_files():
    """Write fixture to a temp words.json, run the pipeline, verify output files."""
    with tempfile.TemporaryDirectory() as td:
        wpath = os.path.join(td, "words.json")
        with open(wpath, "w") as f:
            json.dump(FIXTURE_JSON, f)
        # Call internal functions directly
        subs = make_subs(FIXTURE_WORDS, FIXTURE_DURATION)
        titles = make_titles(FIXTURE_WORDS, FIXTURE_DURATION)
        cuts = make_cuts(FIXTURE_WORDS, FIXTURE_DURATION)
        # write and re-read cuts
        cpath = os.path.join(td, "cuts.json")
        with open(cpath, "w") as f:
            json.dump(cuts, f)
        with open(cpath) as f:
            reloaded = json.load(f)
        assert reloaded["cuts"] == cuts["cuts"]
        assert len(reloaded["segments"]) == len(cuts["segments"])

# ─── runner ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Running make_subs tests...")
    tests = [
        ("group_cards_two", test_group_cards_two),
        ("subs_dialogue_count", test_subs_dialogue_count),
        ("subs_karaoke_tags", test_subs_karaoke_tags),
        ("subs_emphasis_keywords_param", test_subs_emphasis_keywords_param),
        ("cuts_segments_durations", test_cuts_segments_durations),
        ("cuts_scales_cycle", test_cuts_scales_cycle),
        ("titles_have_two_dialogues", test_titles_have_two_dialogues),
        ("title_t1_anchor", test_title_t1_anchor),
        ("title_t2_last_word", test_title_t2_last_word),
        ("time_format", test_time_format),
        ("norm", test_norm),
        ("roundtrip_via_files", test_roundtrip_via_files),
    ]
    for name, fn in tests:
        run_test(name, fn)
    print("TEST OK")
