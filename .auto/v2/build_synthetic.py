#!/usr/bin/env python
"""Build the synthetic benchmark suite (Track 6A).

Degrades the existing clean Piper testset (.auto/testset/<lang>/*_clean.wav)
into controlled degradations, all at 48 kHz mono:

    clean                    (as-is, ground truth)
    noise_snr{0,10,20}       additive white noise at fixed SNR
    reverb                   convolution with a synthetic decaying IR
    clip                    hard clipping at 0.9

Output: .auto/v2/synthetic/<lang>/<name>_<deg>.wav  (deg in {clean,noise_snr00,
noise_snr10,noise_snr20,reverb,clip}).
"""
from __future__ import annotations

import glob
import os
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parent
SRC = ROOT.parent / "testset"
OUT = ROOT / "synthetic"
SR = 48000
SNRS = [0, 10, 20]
RNG = np.random.default_rng(42)


def reverb_ir(seconds: float = 0.8, decay: float = 8.0) -> np.ndarray:
    """Synthetic exponentially-decaying noise IR (decay in dB/s)."""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    ir = RNG.standard_normal(n) * np.exp(-decay * t)
    return ir / (np.linalg.norm(ir) + 1e-12)


def main() -> None:
    clips = sorted(glob.glob(str(SRC / "*" / "*_clean.wav")))
    if not clips:
        raise SystemExit(f"no clean clips under {SRC}")
    out_root = OUT
    for clip in clips:
        lang = Path(clip).parent.name
        stem = Path(clip).name.replace("_clean.wav", "")
        x, sr = sf.read(clip, dtype="float32")
        if sr != SR:
            import soxr

            x = soxr.resample(x, sr, SR).astype("float32")
        out_dir = out_root / lang
        out_dir.mkdir(parents=True, exist_ok=True)
        sf.write(out_dir / f"{stem}_clean.wav", x, SR)
        for snr in SNRS:
            noise = RNG.standard_normal(len(x)).astype("float32")
            noise *= 10 ** (-snr / 20.0) / (np.linalg.norm(noise) / np.linalg.norm(x) + 1e-12)
            sf.write(out_dir / f"{stem}_noise_snr{snr:02d}.wav", (x + noise).astype("float32"), SR)
        # reverb (wet 40%)
        ir = reverb_ir().astype("float32")
        import scipy.signal

        wet = scipy.signal.fftconvolve(x, ir)[: len(x)]
        sf.write(out_dir / f"{stem}_reverb.wav", (0.6 * x + 0.4 * wet).astype("float32"), SR)
        # clipping
        sf.write(out_dir / f"{stem}_clip.wav", np.clip(x * 2.5, -0.9, 0.9).astype("float32"), SR)
        print(f"  {lang}/{stem}: clean + {len(SNRS)} noise + reverb + clip")
    print(f"synthetic suite ready at {out_root}")


if __name__ == "__main__":
    main()
