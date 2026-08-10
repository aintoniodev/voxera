"""``voxera score`` — Voice Score / CVS (Track 3).

Product metrics only (docs/SPECS-fase2.md, Track 3):

| Dimensión | Proxy |
|---|---|
| Noise | SNR estimado vía VAD (0 dB→30, 20 dB→90) |
| Clarity | presence/mud band-ratio (proxy de claridad, no inteligibilidad) |
| Loudness | distancia a -14 LUFS (LUFS-I + LRA) |
| Room Echo | RT60 estimado + confidence |
| Dynamics | crest factor / LRA |

CVS = weighted mean (0.25/0.25/0.2/0.15/0.15) → 0-100 + veredicto.
Con ``--ref``: Voice Preservation % = cosine(speaker_embedding(IN), speaker_embedding(REF))
con resemblyzer — "la voz sigue siendo la misma persona".

Research metrics (PESQ/STOI/ESTOI/SI-SDR/RTF/DNSMOS) viven SOLO en el benchmark
(Track 6), nunca en el score de producto.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from voxera import audioio
from voxera.analyze import analyze, _band_energy_db
from voxera.device import resolve_device
from voxera.determinism import system_block
from voxera.errors import EnhancementError

TARGET_LUFS = -14.0
WEIGHTS = {"noise": 0.25, "clarity": 0.25, "loudness": 0.20, "room": 0.15, "dynamics": 0.15}

VERDICTS = [
    (80.0, "Your voice is ready for publishing"),
    (60.0, "Close — needs a little polish"),
    (0.0, "Needs work"),
]


def _clip(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return float(np.clip(value, lo, hi))


def _score_noise(snr: float | None) -> tuple[float, str]:
    if snr is None:
        return 50.0, "SNR n/a"
    return _clip(30.0 + 3.0 * snr), f"SNR {snr:.1f} dB"


def _score_clarity(proxy: float | None) -> tuple[float, str]:
    if proxy is None:
        return 50.0, "presence/mud n/a"
    return _clip(proxy * 100.0), "presence/mud proxy"


def _score_loudness(lufs: float | None) -> tuple[float, str]:
    if lufs is None:
        return 50.0, "LUFS n/a"
    delta = abs(lufs - TARGET_LUFS)
    return _clip(100.0 - 5.0 * delta), f"LUFS-I {lufs:.1f}, target {TARGET_LUFS:g}"


def _score_room(rt60: float | None, confidence: float) -> tuple[float, str]:
    if rt60 is None:
        return 60.0, "RT60 n/a"
    # Estimates beyond ~2 s on short clips are unreliable fits (compressor/
    # loudnorm shift the tail); cap them and discount the confidence.
    if rt60 > 2.0:
        confidence = confidence * 0.3
        rt60 = 2.0
    base = 100.0 - min(70.0, max(0.0, (rt60 - 0.25) * 150.0))
    blended = 60.0 * (1.0 - confidence) + base * confidence
    return _clip(blended), f"RT60 {rt60:.2f} s (conf {confidence:.2f})"


def _score_dynamics(lra: float | None, crest_db: float | None) -> tuple[float, str]:
    parts = []
    if lra is not None:
        parts.append(100.0 - min(50.0, 8.0 * abs(lra - 8.0)))
    if crest_db is not None:
        parts.append(100.0 - min(50.0, 3.0 * abs(crest_db - 11.0)))
    if not parts:
        return 60.0, "LRA n/a"
    detail = f"LRA {lra:.1f} LU" if lra is not None else "crest only"
    return _clip(float(np.mean(parts))), detail


def _crest_db(samples: np.ndarray) -> float:
    peak = float(np.max(np.abs(samples)))
    rms = float(np.sqrt((samples**2).mean()))
    if rms <= 1e-12:
        return 0.0
    return 20.0 * np.log10(peak / rms)


def voice_preservation_pct(input_path: Path, ref_path: Path) -> float:
    """Cosine similarity of resemblyzer speaker embeddings, in %."""
    try:
        from resemblyzer import VoiceEncoder, preprocess_wav
    except ImportError as exc:  # pragma: no cover - declared dependency
        raise EnhancementError(
            "voice preservation (--ref) requires the 'resemblyzer' package"
        ) from exc

    import contextlib
    import io

    def _embed(path: Path) -> np.ndarray:
        data = audioio.load_audio(path)
        wav = preprocess_wav(data.samples, source_sr=audioio.INTERNAL_SAMPLE_RATE)
        # resemblyzer prints "Loaded the voice encoder model…" to stdout, which
        # would corrupt JSON reports.
        with contextlib.redirect_stdout(io.StringIO()):
            encoder = VoiceEncoder()
            return encoder.embed_utterance(wav)

    try:
        emb_in, emb_ref = _embed(input_path), _embed(ref_path)
    except Exception as exc:  # noqa: BLE001 - model download/IO failures
        raise EnhancementError(f"voice preservation failed: {exc}") from exc
    cosine = float(np.dot(emb_in, emb_ref) / (np.linalg.norm(emb_in) * np.linalg.norm(emb_ref) + 1e-12))
    return _clip(cosine * 100.0, 0.0, 100.0)


def _verdict(cvs: float) -> str:
    for threshold, text in VERDICTS:
        if cvs >= threshold:
            return text
    return VERDICTS[-1][1]


def score_file(
    input_path: str | Path,
    ref_path: str | Path | None = None,
    device: str = "auto",
) -> dict:
    """Score ``input_path``; returns the full report dict (never modifies audio)."""
    t0 = time.perf_counter()
    resolved_device = resolve_device(device, probe=False)
    inp = Path(input_path)

    report = analyze(inp, device=device)
    samples = audioio.load_audio(inp).samples
    sr = audioio.INTERNAL_SAMPLE_RATE

    snr = report["voice"]["snr_db"]["value"]
    clarity_value = report["voice"]["intelligibility_proxy"]["value"]
    lufs = report["loudness"]["integrated_lufs"]
    lra = report["loudness"]["lra"]
    rt60 = report["room"]["rt60_s"]
    room_conf = report["room"]["confidence"]

    noise_score, noise_detail = _score_noise(snr)
    clarity_score, clarity_detail = _score_clarity(clarity_value)
    loudness_score, loudness_detail = _score_loudness(lufs)
    room_score, room_detail = _score_room(rt60, room_conf)
    dynamics_score, dynamics_detail = _score_dynamics(lra, _crest_db(samples))

    dims = {
        "noise": {"value": round(noise_score, 1), "detail": noise_detail},
        "clarity": {"value": round(clarity_score, 1), "detail": clarity_detail},
        "loudness": {"value": round(loudness_score, 1), "detail": loudness_detail},
        "room": {"value": round(room_score, 1), "detail": room_detail},
        "dynamics": {"value": round(dynamics_score, 1), "detail": dynamics_detail},
    }
    cvs = sum(WEIGHTS[k] * dims[k]["value"] for k in WEIGHTS)

    result: dict = {
        "score": {
            "cvs": round(cvs, 1),
            "verdict": _verdict(cvs),
            "dimensions": dims,
        },
        "system": system_block(
            device=resolved_device,
            sample_rate=sr,
            processing_time_s=time.perf_counter() - t0,
        ),
    }
    if ref_path is not None:
        result["voice_preservation_pct"] = round(voice_preservation_pct(inp, Path(ref_path)), 1)
    return result
