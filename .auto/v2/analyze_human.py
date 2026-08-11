#!/usr/bin/env python
"""Analyze the human AB votes (Track 8), combining sources.

Sources (auto-detected in .auto/human/):
  1. votes.csv              — server votes (clip_id = "<clip>:<pair>", side A/B =
                              player sides; for "B vs C" side A is the _B file).
  2. <anything>_votes.csv / voxer_*.csv — standalone test exports, which carry
                              side_a_file/side_b_file (the randomized mapping).

Output: B vs C preference per listener + combined, MOS, and the >=60% verdict
(decision #12). Also prints A vs C when present.

Usage: python .auto/v2/analyze_human.py
"""
from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HUMAN = ROOT / ".auto" / "human"

COND_OF_FILE = {
    "_B.wav": "B", "_C.wav": "C", "_D.wav": "D", "_A.wav": "A",
}


def cond_of(filename: str) -> str:
    for suffix, cond in COND_OF_FILE.items():
        if filename.endswith(suffix):
            return cond
    return "?"


def parse_votes_csv(path: Path) -> list[dict]:
    """Server-format rows: clip_id='clip:pair', preferred = player side."""
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("listener") == "test":
                continue
            clip_id = r.get("clip_id", "")
            if ":" not in clip_id:
                continue
            clip, pair = clip_id.split(":", 1)
            if pair != "B vs C":
                continue
            # server rows: side A = first file of the pair (the _B condition)
            side_a = f"{clip}_B.wav"
            side_b = f"{clip}_C.wav"
            rows.append({
                "listener": r["listener"], "clip": clip, "pair": pair,
                "side_a_cond": "B", "side_b_cond": "C",
                "preferred": r.get("preferred", ""),
                "mos_a": r.get("mos_a", ""), "mos_b": r.get("mos_b", ""),
                "comment": r.get("comment", ""), "src": path.name,
                "side_a_file": side_a, "side_b_file": side_b,
            })
    return rows


def parse_standalone_csv(path: Path) -> list[dict]:
    """Standalone exports carry side_a_file/side_b_file (randomized mapping)."""
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("pair") != "B vs C":
                continue
            rows.append({
                "listener": r.get("listener", "anon"), "clip": r.get("clip", ""),
                "pair": r.get("pair", "B vs C"),
                "side_a_cond": cond_of(r.get("side_a_file", "")),
                "side_b_cond": cond_of(r.get("side_b_file", "")),
                "preferred": r.get("preferred", ""),
                "mos_a": r.get("mos_a", ""), "mos_b": r.get("mos_b", ""),
                "comment": r.get("comment", ""), "src": path.name,
                "side_a_file": r.get("side_a_file", ""),
                "side_b_file": r.get("side_b_file", ""),
            })
    return rows


def winner_cond(row: dict) -> str:
    pref = row["preferred"]
    if pref == "A":
        return row["side_a_cond"]
    if pref == "B":
        return row["side_b_cond"]
    return "tie"


def main() -> int:
    sources = sorted(HUMAN.glob("votes.csv")) + sorted(HUMAN.glob("*_votes.csv")) + sorted(HUMAN.glob("voxer_*.csv"))
    # standalone exports may live in media/ab_csv (e.g. votos_<name>.csv)
    ab_dir = ROOT / "media" / "ab_csv"
    if ab_dir.is_dir():
        sources += sorted(ab_dir.glob("*.csv"))
    seen_paths = {p.name for p in sources}
    rows = []
    for path in sources:
        if path.name == "votes.csv":
            rows += parse_votes_csv(path)
        else:
            rows += parse_standalone_csv(path)
    if not rows:
        print("no hay votos B vs C (votes.csv o *_votes.csv) en", HUMAN)
        return 1

    # dedup: same listener + clip, keep the latest (last source wins)
    dedup: dict[tuple, dict] = {}
    for r in rows:
        dedup[(r["listener"], r["clip"])] = r
    rows = list(dedup.values())

    per_listener = defaultdict(Counter)
    mos = defaultdict(lambda: defaultdict(list))
    for r in rows:
        per_listener[r["listener"]][winner_cond(r)] += 1
        try:
            mos[r["listener"]]["B"].append(int(r["mos_a"]) if r["side_a_cond"] == "B" else int(r["mos_b"]))
            mos[r["listener"]]["C"].append(int(r["mos_b"]) if r["side_b_cond"] == "C" else int(r["mos_a"]))
        except ValueError:
            pass

    print(f"fuentes: {seen_paths}")
    print(f"votos B vs C unicos: {len(rows)} | oyentes: {sorted(per_listener)}\n")
    for listener, c in sorted(per_listener.items()):
        total = sum(c.values())
        cw, bw, tw = c.get("C", 0), c.get("B", 0), c.get("tie", 0)
        m = mos[listener]
        mc = sum(m["C"]) / len(m["C"]) if m["C"] else float("nan")
        mb = sum(m["B"]) / len(m["B"]) if m["B"] else float("nan")
        print(f"  {listener:10s} n={total:2d} | C(DF2+master) gana {cw:2d} ({cw/total*100:.0f}%) · "
              f"B(DF2) gana {bw:2d} ({bw/total*100:.0f}%) · empate {tw:2d} | MOS C {mc:.2f} vs B {mb:.2f}")

    total = len(rows)
    cw = sum(1 for r in rows if winner_cond(r) == "C")
    bw = sum(1 for r in rows if winner_cond(r) == "B")
    tw = sum(1 for r in rows if winner_cond(r) == "tie")
    print(f"\nTOTAL: n={total} | C gana {cw} ({cw/total*100:.0f}%) · B gana {bw} ({bw/total*100:.0f}%) · "
          f"empate {tw} ({tw/total*100:.0f}%)")
    pct = cw / total * 100
    print(f"Umbral #12 (DF2+master >= 60%): {'[OK] CUMPLIDO' if pct >= 60 else '[NO] no alcanzado'} ({pct:.0f}%)")
    print(f"Alternativa (C >= B incl. empates): {100 - bw/total*100:.0f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
