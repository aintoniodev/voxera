#!/usr/bin/env python3
"""Parchea errores de ASR en words.json conservando s/e de cada palabra.

Formato de glosario (mismo que transcribe.py --glossary):
    {"glossary": [
        {"asr": "hay", "fix": "estás", "window": [10.0, 11.5], "why": "tú hay en medio"},
        {"asr": "Beathome,", "fix": "Bizum,", "window": [24.0, 27.0], "why": "app de pago"}
    ]}

Uso:
  patch_words.py --words out/words.json --glossary glossary.json [--out words.json]
"""
import argparse
import json
import sys


def apply_glossary(words, entries):
    """Apply ASR corrections in-place. Supports:
    - exact match (case-insensitive) with fix replacement
    - prefix match (entry with "prefix": true) with fix replacement
    - deletion (fix="") — removes the word from the list
    """
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
    parser = argparse.ArgumentParser(description="Patch ASR errors in words.json")
    parser.add_argument("--words", required=True, help="Path to words.json")
    parser.add_argument("--glossary", required=True, help="Glossary JSON (mismo formato que transcribe.py)")
    parser.add_argument("--out", default=None, help="Output path (default: in-place)")
    args = parser.parse_args()

    with open(args.words, "r", encoding="utf-8") as f:
        data = json.load(f)
    with open(args.glossary, "r", encoding="utf-8") as f:
        g = json.load(f)
    entries = g.get("glossary", g)

    applied = apply_glossary(data["words"], entries)
    if applied:
        print(f"{len(applied)} parches aplicados:")
        for a in applied:
            print("  ", a)
    else:
        print("Ningún parche coincidió (revisa texto exacto y ventanas).")
        sys.exit(1)

    out = args.out or args.words
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
