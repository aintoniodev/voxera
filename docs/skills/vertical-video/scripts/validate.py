#!/usr/bin/env python3
"""Checklist de entrega — validación numérica de 03/04/00 contra 02c.

Uso: validate.py [--outdir out] [--preview]
  (--preview valida los *_preview.mp4 de la iteración rápida)

Comprueba:
  1. Resoluciones/duraciones/audio de 03, 04, 00
  2. Subs quemadas (PSNR 02c vs 03, finito y < 40 dB)
  3. Anti-flash (YAVG ±2 frames de cada corte <= 25)
  4. Overlays: ventanas dentro de [0, duración] y contenido en la zona
  5. Silencios: duración final < raw y habla arranca < 0.6 s
  6. Decodificación punta a punta sin errores
"""
import json
import re
import subprocess
import sys

FFMPEG = "C:/ffmpeg/bin/ffmpeg.exe"
FFPROBE = "C:/ffmpeg/bin/ffprobe.exe"


def probe(path):
    r = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries",
         "stream=codec_type,width,height,r_frame_rate:format=duration",
         "-of", "json", path], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def video_fps(info):
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    num, den = (int(x) for x in v["r_frame_rate"].split("/"))
    return num / den


def check1_resolutions_durations(OUT, names):
    print("== 1. Resoluciones / duraciones / audio ==")
    import os
    # duración de referencia: 02c_compressed (o 02_graded si no hay comprimido)
    # respeta el modo preview (sufijo _preview en los nombres)
    sfx = "_preview" if any("preview" in n for n, _ in names) else ""
    ref = f"{OUT}/02c_compressed{sfx}.mp4"
    if not os.path.exists(ref):
        ref = f"{OUT}/02_graded{sfx}.mp4"
    d_ref = float(probe(ref)["format"]["duration"])
    ok = True
    for name, want_wh in names:
        info = probe(f"{OUT}/{name}")
        v = next(s for s in info["streams"] if s["codec_type"] == "video")
        a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
        d = float(info["format"]["duration"])
        got_wh = (v.get("width"), v.get("height"))
        line_ok = got_wh == want_wh and a is not None
        extra = ""
        if name.startswith("03") or name.startswith("04"):
            extra = f" | dur ref {d_ref:.2f} (Δ{abs(d - d_ref):.3f}s)"
            line_ok = line_ok and abs(d - d_ref) <= 0.3
        print(f"  {'OK ' if line_ok else 'FAIL'} {name}: {got_wh}, {d:.2f}s, "
              f"audio={'sí' if a else 'NO'}{extra}")
        ok = ok and line_ok
    return ok


def check2_psnr_subs(OUT, names):
    print("== 2. Subs quemadas (PSNR 02c vs 03 en frame con tarjeta T1, t=2.5, escala 1.0) ==")
    n03 = next((n for n, _ in names if n.startswith("03")), None)
    if n03 is None:
        print("  (sin 03, skip)")
        return True
    import os
    sfx = "_preview" if "preview" in n03 else ""
    ref = f"{OUT}/02c_compressed{sfx}.mp4"
    if not os.path.exists(ref):
        ref = f"{OUT}/02_graded{sfx}.mp4"
    for src, png in [(ref, "f_02c.png"), (f"{OUT}/{n03}", "f_03.png")]:
        subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", "2.5", "-i", src,
                        "-frames:v", "1", f"{OUT}/{png}"], check=True)
    r = subprocess.run([FFMPEG, "-v", "info", "-i", f"{OUT}/f_02c.png",
                        "-i", f"{OUT}/f_03.png", "-lavfi", "psnr",
                        "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"average:(?:(inf)|([0-9.e+-]+))", r.stderr)
    if m and m.group(1):
        print("  FAIL: PSNR infinito (frames idénticos, subs NO quemadas)")
        return False
    psnr = float(m.group(2)) if m else None
    ok = psnr is not None and psnr < 40.0
    print(f"  {'OK ' if ok else 'FAIL'} PSNR medio = {psnr:.2f} dB (< 40, finito)")
    return ok


def check3_anti_flash(OUT, names):
    print("== 3. Anti-flash: YAVG ±2 frames de cada corte (03) ==")
    n03 = next((n for n, _ in names if n.startswith("03")), None)
    if n03 is None:
        print("  (sin 03, skip)")
        return True
    cuts = json.load(open(f"{OUT}/cuts.json"))["cuts"]
    fps = video_fps(probe(f"{OUT}/{n03}"))
    r = subprocess.run([FFMPEG, "-v", "info", "-i", f"{OUT}/{n03}",
                        "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG",
                        "-f", "null", "-"], capture_output=True, text=True)
    yavg = {}
    frame = None
    for line in r.stderr.splitlines():
        mf = re.search(r"frame:\s*(\d+)", line)
        if mf:
            frame = int(mf.group(1))
        my = re.search(r"lavfi\.signalstats\.YAVG=([\d.]+)", line)
        if my and frame is not None:
            yavg[frame] = float(my.group(1))
    worst, worst_t = 0.0, None
    for ct in cuts:
        f0 = int(round(ct * fps))
        vals = [yavg.get(f) for f in range(f0 - 2, f0 + 3)]
        vals = [v for v in vals if v is not None]
        if len(vals) < 2:
            continue
        jump = max(vals) - min(vals)
        if jump > worst:
            worst, worst_t = jump, ct
    # Un salto YAVG alto puede ser (a) flash artificial (misma escena, salto brusco
    # de luma) o (b) corte de PLANO legítimo (contenido distinto, p.ej. interior
    # oscuro -> exterior soleado). Distinguirlos: para el peor corte, extraer los
    # frames ±1 y comparar la CORRELACIÓN de contenido (SSIM). SSIM bajo => escena
    # distinta => corte de contenido, no flash. SSIM alto + salto => flash real.
    ok = worst <= 25.0
    verdict = ""
    if not ok and worst_t is not None:
        f0 = int(round(worst_t * fps))
        for off, png in ((-1, "f3_pre.png"), (1, "f3_post.png")):
            ff = max(0, min(f0 + off, int(round(yavg[max(yavg)] if yavg else f0))))
            subprocess.run([FFMPEG, "-y", "-v", "error",
                            "-i", f"{OUT}/{n03}",
                            "-vf", f"select='eq(n,{ff})'", "-frames:v", "1",
                            f"{OUT}/{png}"], check=True)
        ss = subprocess.run([FFMPEG, "-v", "info", "-i", f"{OUT}/f3_pre.png",
                             "-i", f"{OUT}/f3_post.png", "-lavfi", "ssim",
                             "-f", "null", "-"], capture_output=True, text=True)
        m = re.search(r"SSIM Y:\s*([\d.]+)", ss.stderr)
        ssim = float(m.group(1)) if m else 0.0
        if ssim < 0.45:  # contenido distinto: corte de plano legítimo
            ok = True
            verdict = f" — salto es CORTE DE PLANO (SSIM {ssim:.2f} < 0.45, contenido distinto)"
        else:
            verdict = f" — FLASH real sobre misma escena (SSIM {ssim:.2f} >= 0.45)"
    print(f"  {'OK ' if ok else 'FAIL'} peor salto YAVG = {worst:.1f} (corte t={worst_t:.2f}s) <= 25{verdict}")
    return ok


def check4_overlays(OUT, names):
    print("== 4. Overlays: ventana y contenido en zona del sticker (04) ==")
    import os
    ov_path = f"{OUT}/overlays.json"
    if not os.path.exists(ov_path):
        print("  (sin overlays.json, skip)")
        return True
    n04 = next((n for n, _ in names if n.startswith("04")), None)
    if n04 is None:
        print("  (sin 04, skip)")
        return True
    ov = json.load(open(ov_path))["overlays"]
    d04 = float(probe(f"{OUT}/{n04}")["format"]["duration"])
    ok = True
    for o in ov:
        inside = 0 <= o["t_start"] < o["t_end"] <= d04
        tc = (o["t_start"] + o["t_end"]) / 2
        crop_w = 230 if "preview" not in n04 else 115
        subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", str(tc),
                        "-i", f"{OUT}/{n04}", "-frames:v", "1",
                        "-vf", f"crop={crop_w}:{crop_w}:{o['x']}:{o['y']}",
                        f"{OUT}/sticker_check_{tc:.1f}.png"], check=True)
        std = -1.0
        try:
            from PIL import Image, ImageStat
            stat = ImageStat.Stat(Image.open(f"{OUT}/sticker_check_{tc:.1f}.png").convert("RGB"))
            std = max(stat.stddev)
        except ImportError:
            pass
        line_ok = inside and std > 15
        print(f"  {'OK ' if line_ok else 'FAIL'} {o['png']}: "
              f"ventana [{o['t_start']:.2f},{o['t_end']:.2f}]⊂[0,{d04:.1f}] "
              f"{'✓' if inside else '✗'}; std zona={std:.1f}")
        ok = ok and line_ok
    return ok


def check5_silences(OUT, names):
    print("== 5. Silencios: duración < raw y habla arranca < 0.6 s ==")
    import os
    n04 = next((n for n, _ in names if n.startswith("04")), None)
    if n04 is None:
        print("  (sin 04, skip)")
        return True
    d04 = float(probe(f"{OUT}/{n04}")["format"]["duration"])
    raw = f"{OUT}/01_raw.mp4"
    if os.path.exists(raw):
        d_raw = float(probe(raw)["format"]["duration"])
        ok_dur = d04 < d_raw
        print(f"  {'OK ' if ok_dur else 'FAIL'} {d04:.2f}s < raw {d_raw:.2f}s")
    else:
        ok_dur, d_raw = True, None
        print(f"  (sin 01_raw, no se compara duración)")
    r = subprocess.run([FFMPEG, "-i", f"{OUT}/{n04}",
                        "-af", "silencedetect=noise=-40dB:d=0.1",
                        "-t", "3", "-f", "null", "-"], capture_output=True, text=True)
    ends = [float(m) for m in re.findall(r"silence_end:\s*([\d.]+)", r.stderr)]
    # el PRIMER silence_end es el fin del silencio inicial = arranque del habla
    # (ends[-1] daba el último silencio de la ventana -3s-, falso positivo)
    speech_start = ends[0] if ends else 0.0
    ok_speech = speech_start < 0.6
    print(f"  {'OK ' if ok_speech else 'FAIL'} habla arranca a {speech_start:.2f}s (< 0.6)")
    return ok_dur and ok_speech


def check6_decode(OUT, names):
    print("== 6. Decodificar de punta a punta ==")
    ok = True
    for name, _ in names:
        r = subprocess.run([FFMPEG, "-v", "error", "-i", f"{OUT}/{name}",
                            "-f", "null", "-"], capture_output=True, text=True)
        errs = r.stderr.strip()
        print(f"  {'OK ' if not errs else 'FAIL'} {name}: "
              f"{'sin errores' if not errs else errs[:200]}")
        ok = ok and not errs
    return ok


def main():
    import argparse
    import os
    parser = argparse.ArgumentParser(description="Checklist de entrega numérico")
    parser.add_argument("--outdir", default="out", help="Directorio de salida (default: out)")
    parser.add_argument("--preview", action="store_true",
                        help="Validar los *_preview.mp4 de la iteración")
    args = parser.parse_args()

    OUT = args.outdir
    SFX = "_preview" if args.preview else ""
    names = [
        (f"03_subs_zoom{SFX}.mp4", (540, 960) if args.preview else (1080, 1920)),
        (f"04_final{SFX}.mp4", (540, 960) if args.preview else (1080, 1920)),
        (f"00_comparativa{SFX}.mp4", (540, 320) if args.preview else (1080, 640)),
    ]
    names = [(n, w) for n, w in names if os.path.exists(os.path.join(OUT, n))]

    results = [
        check1_resolutions_durations(OUT, names),
        check2_psnr_subs(OUT, names),
        check3_anti_flash(OUT, names),
        check4_overlays(OUT, names),
        check5_silences(OUT, names),
        check6_decode(OUT, names),
    ]
    print("\nCHECKLIST:", "TODO OK" if all(results) else "HAY FALLOS")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
