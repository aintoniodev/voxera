#!/usr/bin/env python3
"""Transcribe audio/video with faster-whisper → word-level timestamps → words.json

Uso (audio-first):
  transcribe.py --input out/audio.wav --outdir out [--glossary glossary.json]

- --device auto: intenta CUDA float16 (GPU, ~10× más rápido) y cae a CPU int8.
- --glossary: corrige AUTOMÁTICAMENTE errores típicos del ASR (nombres propios,
  inglés) con ventanas temporales; el glosario es persistente por serie/contenido
  (ver SKILL.md — glosario ASR). Formato:
    {"glossary": [{"asr": "Beathome", "fix": "Bizum", "window": [24.0, 27.0], "why": "app de pago"}]}
- Reporta palabras de baja confianza para revisión manual (y las guarda en
  words.json como "low_confidence").
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

FFPROBE = r"C:/ffmpeg/bin/ffprobe.exe"

CONFIDENCE_WARN = 0.45


def get_duration(path: str) -> float:
    result = subprocess.run(
        [FFPROBE, "-v", "error",
         "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1",
         path],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def load_model(model_name: str, device: str):
    from faster_whisper import WhisperModel

    if device == "auto":
        try:
            model = WhisperModel(model_name, device="cuda", compute_type="float16")
            print(f"  device: CUDA float16 (GPU)")
            return model, "cuda", "float16"
        except Exception as exc:
            print(f"  CUDA no disponible ({exc}); cayendo a CPU int8")
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    print(f"  device: CPU int8")
    return model, "cpu", "int8"


def transcribe(path: str, model_name: str, device: str, language: str):
    model, dev, ct = load_model(model_name, device)
    segments, info = model.transcribe(
        path, language=language, word_timestamps=True, vad_filter=True,
    )
    words = []
    low_conf = []
    for seg in segments:
        for w in seg.words:
            word = {
                "w": w.word.strip(),
                "s": round(w.start, 3),
                "e": round(w.end, 3),
            }
            if hasattr(w, "probability") and w.probability is not None:
                word["prob"] = round(w.probability, 3)
                if w.probability < CONFIDENCE_WARN:
                    low_conf.append({"w": word["w"], "s": word["s"], "prob": word["prob"]})
            words.append(word)
    return words, low_conf, dev, ct


def apply_glossary(words, glossary_path):
    """Apply ASR corrections (asr→fix within time windows). Returns applied list.
    Supports prefix match ("prefix": true) and deletion (fix="" = removes word).
    """
    with open(glossary_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    entries = data.get("glossary", data)  # acepta lista directa también
    applied = []
    to_delete = set()
    for entry in entries:
        asr, fix = entry["asr"], entry["fix"]
        t0, t1 = entry.get("window", [0.0, float("inf")])
        use_prefix = entry.get("prefix", False)
        for i, w in enumerate(words):
            if i in to_delete:
                continue
            if use_prefix:
                match = w["w"].lower().startswith(asr.lower()) and t0 <= w["s"] <= t1
            else:
                match = (w["w"] == asr or w["w"].lower() == asr.lower()) and t0 <= w["s"] <= t1
            if match:
                if fix == "":
                    wname, ws = w["w"], w["s"]
                    applied.append(f"[del] '{wname}'@{ws:.2f}"
                                   + (f' ({entry["why"]})' if entry.get("why") else ""))
                    w["w"] = "\x00DEL"
                    to_delete.add(i)
                else:
                    wname, ws = w["w"], w["s"]
                    applied.append(f'{wname}@{ws:.2f} -> {fix}'
                                   + (f' ({entry["why"]})' if entry.get("why") else ""))
                    if use_prefix and w["w"].lower().startswith(asr.lower()):
                        # prefix: el fix reemplaza SOLO el prefijo asr; se conserva el sufijo
                        # ("Beathome," -> "Bizum," sin perder la coma/puntuación)
                        w["w"] = fix + w["w"][len(asr):]
                    else:
                        w["w"] = fix
                # sin break: el glosario es persistente y debe corregir TODAS las
                # apariciones dentro de la ventana (p.ej. "Beathome" x3 en el vídeo)
    words[:] = [w for i, w in enumerate(words) if i not in to_delete]
    return applied


def main():
    parser = argparse.ArgumentParser(description="Transcribe → words.json (audio-first)")
    parser.add_argument("--input", required=True, help="Video o WAV a transcribir")
    parser.add_argument("--outdir", default="out", help="Directorio de salida")
    parser.add_argument("--model", default="small", help="Modelo faster-whisper (default: small)")
    parser.add_argument("--language", default="es", help="Idioma (default: es)")
    parser.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"],
                        help="auto = CUDA float16 si hay GPU, si no CPU int8")
    parser.add_argument("--glossary", default=None,
                        help="JSON de correcciones ASR persistentes (ver docstring)")
    args = parser.parse_args()

    out_dir = Path(args.outdir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "words.json"

    duration = get_duration(args.input)
    print(f"Duration: {duration:.3f}s | model: {args.model} | lang: {args.language}")

    words, low_conf, dev, ct = transcribe(args.input, args.model, args.device, args.language)
    print(f"Got {len(words)} words ({dev}/{ct})")

    applied = []
    if args.glossary:
        applied = apply_glossary(words, args.glossary)
        if applied:
            print(f"Glossary: {len(applied)} correcciones aplicadas:")
            for a in applied:
                print(f"  - {a}")
        else:
            print("Glossary: ninguna corrección coincidió en ventana")

    if low_conf:
        print(f"\nPalabras de baja confianza (< {CONFIDENCE_WARN}) — revisar (las "
              f"primeras 40; completa en words.json 'low_confidence'):")
        for lc in low_conf[:40]:
            print(f"  {lc['s']:8.2f}s  {lc['w']!r:30} prob={lc['prob']:.2f}")

    payload = {
        "model": args.model,
        "device": dev,
        "duration": duration,
        "language": args.language,
        "glossary": args.glossary,
        "patches_applied": applied,
        "low_confidence": low_conf[:200],
        "words": words,
    }
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\nWrote {out_file}")


if __name__ == "__main__":
    main()
