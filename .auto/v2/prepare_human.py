#!/usr/bin/env python
"""Generate the AB test conditions (Track 8) from real clips.

For every clip in media/ (or --dir):
    A = original, loudness-normalized to -16 LUFS (pure gain + TP guard)
    B = DF2, normalized
    C = DF2 + youtube preset, normalized
    D = DF3, normalized

All four conditions end at the SAME loudness so "the loudest" never wins.
Output: .auto/human/conditions/<stem>_{A,B,C,D}.wav + .auto/human/pairs.json
(pares clave: B vs C = ¿aporta el master? · B vs D = DF2 vs DF3 · C vs D).

Usage: python .auto/v2/prepare_human.py [--dir media] [--lufs -16]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from voxera import audioio  # noqa: E402
from voxera.dsp import filters  # noqa: E402
from voxera.enhance import enhance  # noqa: E402

SR = 48000
HUMAN = ROOT / ".auto" / "human"
COND = HUMAN / "conditions"
EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}
PAIRS = [("B vs C", "B", "C"), ("B vs D", "B", "D"), ("C vs D", "C", "D"), ("A vs C", "A", "C")]


def normalize(x: np.ndarray, target: float) -> np.ndarray:
    return filters.loudness_normalize(x, SR, target)


def make_conditions(clip: Path, target: float, force: bool) -> dict[str, Path]:
    stem = clip.stem
    data = audioio.load_audio(clip)
    x = data.samples
    out: dict[str, Path] = {}

    # stage to 48k mono wav so the NN path (legacy backend-only) accepts it
    staged = COND / f"{stem}_stage.wav"
    if not staged.exists() or clip.stat().st_mtime > staged.stat().st_mtime:
        sf.write(str(staged), x, SR)

    def done(key: str) -> Path | None:
        p = COND / f"{stem}_{key}.wav"
        if not force and p.exists():
            return p
        return None

    def nn(preset=None, model=None):
        tmp = COND / f"{stem}_nn_tmp.wav"
        if preset:
            enhance(staged, tmp, preset=preset)
        else:
            enhance(staged, tmp, backend="deepfilternet", model=model)
        y, _ = sf.read(str(tmp), dtype="float32")
        tmp.unlink(missing_ok=True)
        return y

    p = done("A")
    if p is None:
        out["A"] = COND / f"{stem}_A.wav"
        sf.write(str(out["A"]), normalize(x, target), SR)
    else:
        out["A"] = p

    for key, preset, model in (("B", None, None), ("C", "youtube", None), ("D", None, "DeepFilterNet3")):
        p = done(key)
        if p is not None:
            out[key] = p
            continue
        y = nn(preset=preset, model=model)
        out[key] = COND / f"{stem}_{key}.wav"
        sf.write(str(out[key]), normalize(y, target), SR)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=ROOT / "media")
    ap.add_argument("--lufs", type=float, default=-16.0)
    ap.add_argument("--force", action="store_true", help="re-run conditions even if cached")
    args = ap.parse_args()
    COND.mkdir(parents=True, exist_ok=True)
    clips = sorted(
        p for p in args.dir.iterdir()
        if p.is_file() and p.suffix.lower() in EXTENSIONS
    )
    if not clips:
        print(f"no clips in {args.dir}")
        return 1
    pairs: list[dict] = []
    for clip in clips:
        stem = clip.stem
        print(f"  {stem} ...")
        cond = make_conditions(clip, args.lufs, args.force)
        for pair, a_key, b_key in PAIRS:
            pairs.append({"clip": stem, "pair": pair, "a": cond[a_key].name, "b": cond[b_key].name})
    (HUMAN / "pairs.json").write_text(json.dumps(pairs, indent=1), encoding="utf-8")
    print(f"{len(clips)} clips -> {len(pairs)} pares en {COND} (LUFS target {args.lufs:g})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
