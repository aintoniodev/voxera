#!/usr/bin/env python3
"""Remapea words.json del dominio ORIGINAL (WAV del grade, ~198 s) al dominio
COMPRIMIDO (vídeo 02c con silencios cortados, ~187 s).

Por qué: en el flujo audio-first, el timing (silence_timing.json) se calcula una
sola vez sobre el WAV y la transcripción también (misma base temporal, así los
re-encodes nunca invalidan las palabras). Pero subs/tarjetas/overlays/punch-ins
se aplican sobre el vídeo COMPRIMIDO, cuyos tiempos son distintos (los silencios
se eliminaron). Este script mapea cada palabra al dominio comprimido usando los
SEGMENTS del timing (exactamente el concat que produce compress_silences).

Uso:
  remap_words.py --words out/words.json --timing out/silence_timing.json [--out out/words.json]

El remap es determinista y biyectivo por segmentos: comp(t) = acum + (t - seg.start).
"""
import argparse
import json


def build_mapping(segments):
    """Devuelve (bounds, accums, segs): para un tiempo t en dominio original,
    comp(t) = accums[i] + (t - segs[i][0]) si t cae en el segmento i.
    bounds = lista de [start, end] de cada segmento (dominio original).
    accums = silencio acumulado ANTES de cada segmento.
    """
    bounds = [[s, e] for s, e in segments]
    accums = []
    acum = 0.0
    for s, e in segments:
        accums.append(acum)
        acum += e - s
    return bounds, accums, acum  # acum total = duración del comprimido


def remap_time(t, bounds, accums, total_comp):
    import bisect
    # buscar segmento que contiene t
    starts = [s for s, _ in bounds]
    i = bisect.bisect_right(starts, t) - 1
    if i < 0:
        return 0.0  # antes del primer segmento
    s, e = bounds[i]
    if t <= e:
        return accums[i] + (t - s)
    # t cae en un hueco (silencio eliminado): alinear al final del segmento previo
    return accums[i] + (e - s)


def main():
    parser = argparse.ArgumentParser(description="Remap words.json a dominio comprimido")
    parser.add_argument("--words", required=True, help="words.json (dominio original)")
    parser.add_argument("--timing", required=True, help="silence_timing.json (segments)")
    parser.add_argument("--out", default=None, help="Salida (default: in-place)")
    args = parser.parse_args()

    with open(args.words, "r", encoding="utf-8") as f:
        data = json.load(f)
    with open(args.timing, "r", encoding="utf-8") as f:
        timing = json.load(f)

    segments = [(s, e) for s, e in timing["segments"]]
    bounds, accums, total_comp = build_mapping(segments)

    words = data["words"]
    n = 0
    for w in words:
        ns = remap_time(w["s"], bounds, accums, total_comp)
        ne = remap_time(w["e"], bounds, accums, total_comp)
        if ns != w["s"] or ne != w["e"]:
            n += 1
        w["s"] = round(ns, 3)
        w["e"] = round(ne, 3)

    # low_confidence y patches_applied también llevan tiempos
    if "low_confidence" in data:
        for lc in data["low_confidence"]:
            lc["s"] = round(remap_time(lc["s"], bounds, accums, total_comp), 3)

    data["remapped"] = {
        "original_seconds": round(sum(e - s for s, e in segments), 3),
        "compressed_seconds": round(total_comp, 3),
        "words_shifted": n,
    }

    out = args.out or args.words
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Remap: {n}/{len(words)} palabras desplazadas; "
          f"dominio {data['remapped']['original_seconds']}s -> "
          f"{data['remapped']['compressed_seconds']}s")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()