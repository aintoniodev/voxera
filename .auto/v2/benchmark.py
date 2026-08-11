#!/usr/bin/env python
"""Benchmark v2 (Track 6): synthetic and real suites, NEVER merged.

Usage:
    python .auto/v2/benchmark.py --suite synthetic
    python .auto/v2/benchmark.py --suite real
    python .auto/v2/benchmark.py            # both

Synthetic suite: ground truth exists -> PESQ/STOI/ESTOI/SI-SDR + control
(LUFS, true peak, clipping) + RTF (model/pipeline/e2e from the CLI result).

Real suite: no ground truth -> LUFS, TP, speech ratio, SNR est., artifact
proxy (crest anomaly), speaker preservation vs the original clip (resemblyzer),
RTF. Clips: .auto/v2/real/*.wav (grabaciones reales de Antonio, decision #3).

Deliverable: one markdown table per suite under .auto/v2/reports/ — never fused.
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent.parent / "src"))
sys.path.insert(0, str(ROOT.parent.parent))

from voxera import audioio  # noqa: E402
from voxera.analyze import quick_metrics  # noqa: E402
from voxera.dsp.filters import true_peak_db  # noqa: E402
from voxera.enhance import enhance  # noqa: E402
from voxera.errors import EnhancementError  # noqa: E402

SR = 48000
REPORTS = ROOT / "reports"
REAL_DIR = ROOT / "real"

CANDIDATES = {
    "DF2": {"backend": "deepfilternet", "model": "DeepFilterNet2"},
    "DF3": {"backend": "deepfilternet", "model": "DeepFilterNet3"},
    "DF2+creator": {"backend": "deepfilternet", "model": "DeepFilterNet2", "preset": "creator"},
    "DF2+youtube": {"backend": "deepfilternet", "model": "DeepFilterNet2", "preset": "youtube"},
    "dpdfnet": {"backend": "dpdfnet"},
}


def _metrics_reference(est: np.ndarray, ref: np.ndarray) -> dict:
    """PESQ (16k) / STOI / ESTOI / SI-SDR at 48k."""
    from pesq import pesq as pesq_fn
    from pystoi import stoi

    def res16(y):
        import soxr

        return soxr.resample(y.astype("float32"), SR, 16000) if SR != 16000 else y

    e16, r16 = res16(est), res16(ref)
    d = {"pesq": None, "stoi": None, "estoi": None, "si_sdr": None}
    try:
        d["pesq"] = float(pesq_fn(16000, r16, e16, "wb"))
    except Exception:
        pass
    try:
        d["stoi"] = float(stoi(r16, e16, 16000, extended=False))
        d["estoi"] = float(stoi(r16, e16, 16000, extended=True))
    except Exception:
        pass
    est, ref = est.astype(np.float64), ref.astype(np.float64)
    est, ref = est - est.mean(), ref - ref.mean()
    a = float(np.dot(est, ref) / (np.dot(est, est) + 1e-12))
    target = a * est
    d["si_sdr"] = float(
        10 * np.log10((np.dot(target, target) + 1e-12) / (np.dot(ref - target, ref - target) + 1e-12))
    )
    return d


def _run_candidate(clip: Path, out_wav: Path, cand: dict) -> dict:
    """Run one candidate on a clip; reuses cached outputs when fresh."""
    if out_wav.exists() and out_wav.stat().st_mtime >= clip.stat().st_mtime:
        return {"output": out_wav, "cached": True}
    t0 = time.perf_counter()
    try:
        result = enhance(
            clip,
            out_wav,
            backend=cand["backend"],
            model=cand.get("model"),
            preset=cand.get("preset"),
        )
    except EnhancementError as exc:
        return {"error": str(exc)}
    elapsed = time.perf_counter() - t0
    if isinstance(result, dict):
        return result
    # legacy backend-only path: no dict; report e2e RTF manually
    return {"output": out_wav, "rtf_e2e": elapsed, "rtf_model": None, "rtf_pipeline": None}


def _control(est: np.ndarray) -> dict:
    import pyloudnorm as pyln

    lufs = pyln.Meter(SR).integrated_loudness(est)
    return {
        "lufs": round(lufs, 2) if np.isfinite(lufs) else None,
        "true_peak": round(true_peak_db(est), 2),
        "clipping": round(float(np.mean(np.abs(est) >= 0.999)), 5),
    }


def synthetic_suite() -> None:
    clips = sorted(glob.glob(str(ROOT / "synthetic" / "*" / "*.wav")))
    if not clips:
        raise SystemExit("no synthetic clips; run build_synthetic.py first")
    rows: list[dict] = []
    import re

    for cand_name, cand in CANDIDATES.items():
        agg = {m: [] for m in ("pesq", "stoi", "estoi", "si_sdr")}
        rtfs = {"rtf_model": [], "rtf_pipeline": [], "rtf_e2e": []}
        for clip in clips:
            if clip.endswith("_clean.wav"):
                continue
            ref_name = re.sub(r"_(noise_snr\d+|reverb|clip)\.wav$", "_clean.wav", Path(clip).name)
            ref = sf.read(str(Path(clip).parent / ref_name), dtype="float32")[0]
            out_wav = ROOT / "tmp" / f"{cand_name}_{Path(clip).stem}.wav"
            out_wav.parent.mkdir(exist_ok=True)
            res = _run_candidate(Path(clip), out_wav, cand)
            if "error" in res:
                print(f"  {cand_name} on {Path(clip).name}: {res['error']}")
                continue
            est = sf.read(str(out_wav), dtype="float32")[0]
            m = _metrics_reference(est, ref)
            for k, v in m.items():
                if v is not None:
                    agg[k].append(v)
            for k in rtfs:
                if res.get(k) is not None:
                    rtfs[k].append(res[k] / (len(est) / SR))
        row = {"model": cand_name}
        for k, vals in agg.items():
            row[k] = round(float(np.mean(vals)), 3) if vals else None
        for k, vals in rtfs.items():
            row[k] = round(float(np.mean(vals)), 3) if vals else None
        rows.append(row)
    _write_table(REPORTS / "synthetic.md", rows, "Synthetic suite (ground truth) — nunca fusionar con la suite real")


def real_suite(real_dir: Path) -> None:
    clips = sorted(glob.glob(str(real_dir / "*")))
    clips = [c for c in clips if Path(c).suffix.lower() in (".wav", ".mp3", ".m4a", ".flac", ".ogg")]
    if not clips:
        print(f"note: {real_dir} vacío — añade clips reales y re-ejecuta")
        return
    # stage everything to 48k mono wav so every candidate sees the same input
    staging = ROOT / "tmp" / "real_stage"
    staging.mkdir(parents=True, exist_ok=True)
    staged: dict[str, Path] = {}
    for clip in clips:
        out = staging / (Path(clip).stem + "_st.wav")
        if not out.exists():
            data = audioio.load_audio(clip)
            sf.write(str(out), data.samples, SR)
        staged[str(clip)] = out
    rows: list[dict] = []
    for cand_name, cand in CANDIDATES.items():
        for clip in clips:
            out_wav = ROOT / "tmp" / f"{cand_name}_{Path(clip).stem}.wav"
            out_wav.parent.mkdir(exist_ok=True)
            res = _run_candidate(staged[str(clip)], out_wav, cand)
            if "error" in res:
                continue
            est = sf.read(str(out_wav), dtype="float32")[0]
            m = quick_metrics(est, SR)
            ctrl = _control(est)
            crest = 20 * np.log10(np.max(np.abs(est)) / (np.sqrt((est**2).mean()) + 1e-12))
            from voxera.vad import speech_ratio as _sr

            row = {
                "model": cand_name,
                "clip": Path(clip).name,
                "snr_est": round(m["snr_db"], 1) if m["snr_db"] is not None else None,
                "lufs": ctrl["lufs"],
                "true_peak": ctrl["true_peak"],
                "crest_db": round(float(crest), 1),
                "speech_ratio": round(_sr(est, SR), 2),
            }
            if res.get("rtf_e2e") is not None:
                row["rtf_e2e"] = round(res["rtf_e2e"] / (len(est) / SR), 3)
            if cand_name != "DF2" and cand_name != "dpdfnet":
                row["speaker_sim"] = round(_speaker_sim(Path(clip), out_wav), 3)
            rows.append(row)
    _write_table(REPORTS / "real.md", rows, "Real-world suite (sin ground truth) — nunca fusionar con la suite sintética")


def _speaker_sim(orig: Path, enhanced: Path) -> float:
    """Cosine of resemblyzer embeddings (original vs enhanced), 0-1."""
    import contextlib
    import io

    from resemblyzer import VoiceEncoder, preprocess_wav

    def _emb(path: Path) -> np.ndarray:
        data = audioio.load_audio(path)
        wav = preprocess_wav(data.samples, source_sr=SR)
        with contextlib.redirect_stdout(io.StringIO()):
            return VoiceEncoder().embed_utterance(wav)

    try:
        e1, e2 = _emb(orig), _emb(enhanced)
        return float(np.dot(e1, e2) / (np.linalg.norm(e1) * np.linalg.norm(e2) + 1e-12))
    except Exception:
        return float("nan")


def _write_table(path: Path, rows: list[dict], title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = list(rows[0].keys()) if rows else ["model"]
    lines = [f"# {title}", "", "| " + " | ".join(keys) + " |", "|" + "|".join(["---"] * len(keys)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(k, "")) for k in keys) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"reporte: {path}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", choices=("synthetic", "real"), default=None)
    ap.add_argument("--real-dir", type=Path, default=REAL_DIR, help="carpeta con clips reales (default: .auto/v2/real)")
    args = ap.parse_args()
    t0 = time.perf_counter()
    if args.suite in (None, "synthetic"):
        synthetic_suite()
    if args.suite in (None, "real"):
        real_suite(args.real_dir)
    print(f"benchmark v2 done in {time.perf_counter() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
