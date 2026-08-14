---
name: "voxera-magnify"
description: "Efecto 'Magnify' (lupa) en voxera: `voxera video magnify` (lente circular que amplía la zona, se mueve por voz o barrido, pluma, aro). Usar al aplicar lupas a vídeos, modificar src/voxera/video_magnify.py, o verificar renders de magnify. Incluye la medición del tutorial de @billycreative_ (Premiere 26.3) y cómo verificar numéricamente."
version: 2
created: "2026-08-13"
updated: "2026-08-13"
---
## When to Use
Aplicar lupas programáticas a vídeos (voxera video magnify), editar src/voxera/video_magnify.py, diagnosticar renders de magnify que no amplían o no se mueven, o replicar el efecto "Magnify" del tutorial de @billycreative_ (lente circular que amplía la zona, como una lupa al enseñar un paper).

## Procedure
1. Comando: `.venv-video/Scripts/voxera video magnify IN -o OUT [--center X,Y] [--size F] [--zoom Z] [--feather F] [--ring-width F] [--motion static|scan|voice|auto] [--grid COLSxROWS] [--hold S] [--move-dur S] [--min-gap S] [--sharpen F] [--start/--end] [--dry-run]`
2. Defaults medidos del tutorial (2026-08-13, anillo detectado por Hough + continuidad de borde sobre el TikTok de @billycreative_, 720x1280): lente estática en ~(0.36, 0.29), radio ~255 px = 0.35 del ancho, borde nítido, presente varios segundos. El zoom exacto NO es medible de forma fiable (el vídeo está muy editado, sin frame de referencia limpio): default 3x.
3. Movimiento (decisión del usuario, 2026-08-13): default `--motion auto` = movimientos disparados por picos de energía de voz (detect_emphasis_moments compartido con zoom), barrido automático si no hay voz. scan = barrido por celdas en orden de lectura con pausa; voice = solo voz (error si no detecta); static = quieta. El plan de movimiento incluye la celda inicial: plan[0] = (0, 0, P0), cada segmento i>0 mueve de plan[i-1] a plan[i].
4. Calidad (prioridad del usuario): pipeline TODO en YUV sin conversiones RGB. Ventana (2r + 2·pluma + 8, par) que sigue a la lente (crop animado por 't') -> split x3 -> crop local (2r/zoom) -> scale lanczos a 2r (+ unsharp opcional) -> overlay del patch centrado -> maskedmerge(disco) -> maskedmerge(aro) -> overlay de la ventana sobre el original. Máscaras PNG gris (numpy+zlib): disco con pluma lineal y aro blanco antialias ~1 px.
5. Expresiones de movimiento: ifs anidados por segmento con curva S (pow(P,a)/(pow(P,a)+pow(1-P,a))), redondeo par 2*floor(v/2) para alineación de croma, clamp al frame. crop y overlay comparten la MISMA expresión (mismo 't'). Tras -ss (decode-seek de salida) 't' NO se reinicia: restar opts.start (t-{start}).

## Pitfalls
- ffmpeg 7.1: un label de salida solo puede consumirse UNA vez como input — para dos consumidores usar split con más salidas (split=3) o un segundo split. Síntoma: "Binding input with label 'X' to input stream 0:0" + maskedmerge con el primer input del tamaño del frame.
- El label `[base]` colisiona con el pad `base` de maskedmerge (misma sintomatología). Usar nombres que no sean pads (bg, wb, pps, dsc...).
- `color` sin duración genera frames infinitos -> el framesync de maskedmerge/overlay nunca hace EOF -> ffmpeg cuelga. Siempre `color=...:d={dur}`.
- Los momentos de voz se detectan sobre el audio COMPLETO: son tiempos absolutos; con --start hay que desplazarlos (m - start) y descartar los que quedan fuera del segmento.
- Verificación numérica del zoom: el conteo de transiciones de onda cuadrada se rompe con lanczos (ringing crea cruces falsos). Usar senoide (lanczos es lineal) + FFT con >= 6 ciclos; el pico FFT se parte entre bins si hay < 3 ciclos (leakage).
- La lente muestra las franjas zoom veces MÁS anchas (periodo interior = periodo_base · zoom), no más estrechas.
- FFT sobre región que mezcla filas dentro/fuera del band del crop contamina: medir x en disco 0.6r pero y en ±0.45r.
- Detectar el centro del aro con umbral de brillo se rompe con contenido brillante: el overshoot de lanczos/unsharp clipea a 255 DENTRO de la lente (p. ej. paper 248 -> 49k px >248). Usar score sobre el círculo exacto (>252) buscando el mejor centro en ventana + refinamiento fino; el aro es la única estructura blanca sobre el círculo exacto.
- El centro REAL del aro difiere del pedido: la ventana se redondea a par y se clampa -> el centro efectivo = clamp_par(centro - win/2) + win/2.
- argparse: los '%' de los help strings hay que escaparlos como '%%'.
- El venv editable apunta al repo principal, no al worktree: para probar el CLI del worktree usar `PYTHONPATH=src`.

## Verification
1. tests: `.venv-ims/Scripts/python.exe -m pytest tests/test_video_magnify.py -q` (43 tests: validación, geometría, máscaras PNG, waypoints, filtro YUV, e2e senoide + calidad de amplitud + movimiento scan/voice + timing con --start). Suite completa: 319 passed.
2. E2E numérico: senoide 8 px + zoom 2 -> dentro periodo 8·zoom_eff ± 1 px, fuera 8 px, aro en el radio (perfil radial), diff fuera < 3; amplitud interior >= 90% de la fuente (calidad).
3. Movimiento: centro del aro por score circular en frames clave — paper scan 2x2 (6 s): (235,319) -> (485,319) -> (235,959); tutorial voice (segmento 21-31 s): (235,319) -> (485,319) tras el momento de voz en t=2.76 s del segmento.
4. Demos: media/videos/magnified/paper_magnify_motion.mp4 (barrido) y tutorial_magnify_voice.mp4 (voz) — diff fuera de la lente 0.52 (paper) en ambas.

## Reference Implementation (código núcleo)

La lente es un pipeline 100% YUV (sin conversiones RGB): ventana que sigue a la lente → crop local → scale lanczos → overlay del patch → maskedmerge(disco) → maskedmerge(aro) → overlay de vuelta. Las piezas que no se pueden inventar: la geometría (con redondeos), las máscaras PNG y la expresión de movimiento con ifs anidados.

```python
import numpy as np

def lens_geometry(width: int, height: int, size=0.35, zoom=3.0, feather=0.05,
                  ring_width=0.025) -> dict:
    """Radio, ventana, lado del crop local y zoom efectivo tras redondeos."""
    radius = max(int(round(size * min(width, height))), 4)
    feather_px = feather * radius
    win = max(int(2 * radius + 2 * feather_px + 8) // 2 * 2, 2 * radius)  # par
    crop = max(int(2.0 * radius / zoom) // 2 * 2, 4)
    return {"radius": radius, "win": win, "crop": crop,
            "zoom_eff": 2.0 * radius / crop, "feather_px": feather_px,
            "ring_px": max(1.0, ring_width * radius)}
# Restricción: win < min(w,h) — la lente no cabe en frames pequeños.

def build_lens_masks(radius: int, feather: float, ring_width: float, win: int):
    """Máscaras del disco (pluma lineal) y del aro (antialias ~1px) como gris."""
    y, x = np.mgrid[0:win, 0:win]
    d = np.hypot(x - win / 2 + 0.5, y - win / 2 + 0.5)
    a_disc = np.clip((radius - d) / max(feather * radius, 0.01), 0.0, 1.0)
    disc = (a_disc * 255).astype(np.uint8)          # PNG gris, guardar con zlib
    w = max(ring_width * radius, 0.5)
    a_ring = np.clip(np.minimum(1.0, w / 2 + 1.0 - np.abs(d - radius)), 0.0, 1.0)
    ring = (a_ring * 255).astype(np.uint8)
    return disc, ring
```

```python
# --- expresión ffmpeg del centro de la lente: ifs anidados por segmento ---
# plan = [(T0,D0,P0), (T1,D1,P1), ...] — P_i = posición destino (px)
# expr: if(t<S0, P0, if(t<E0, ease(P0->P1), if(t<S1, P1, if(t<E1, ... Pn))))
# ease = p^a/(p^a+(1-p)^a) con a=1+62/25=3.48; p = clamp01((t-Si)/Di)
# crop y overlay usan la MISMA expresión (mismo 't' -> mismo frame);
# redondeo 2*floor(v/2) para alineación de croma 4:2:0.
# TRAS -ss, 't' NO se reinicia (ffmpeg 7.1): restar opts.start -> tvar = (t-start)
```

```python
# --- build_magnify_filter: esqueleto exacto del graph (entradas: [0] vídeo,
#     [1] disco.png, [2] aro.png) ---
# x_expr, y_expr = posición del borde de la ventana (ver _axis_expr: centro - win/2)
# ploc = (win - 2r) // 2            # patch centrado en la ventana
# cloc = (win - crop) / 2.0         # crop local centrado
# sharp = ",unsharp=5:5:0.5:5:5:0.0" si --sharpen
# [0:v]split=2[bg][src];
# [src]crop=W:W:x='X':y='Y'[wn];                    # ventana sigue a la lente
# [wn]split=3[wb][wm][wq];
# [wm]crop=c:c:cloc:cloc,scale=2r:2r:flags=lanczos,setsar=1[+sharp][pch];
# [1:v]format=yuv420p[dsc];  [2:v]format=yuv420p[rgm];
# [wb][pch]overlay=x=ploc:y=ploc[pps];
# [wq][pps][dsc]maskedmerge[mgd];                   # blend por luma del disco
# color=c=white:s=WxW:r=FPS:d=DUR[wht];             # OJO: sin :d -> cuelga (EOF nunca)
# [mgd][wht][rgm]maskedmerge[fin];                  # aro
# [bg][fin]overlay=x='X':y='Y',format=yuv420p[vout]
```

Verificación de réplica: senoide 8 px + zoom 2 → periodo interior = base·zoom_eff (±1 px), exterior intacto, diff fuera de la lente < 3; la amplitud interior ≥ 90% de la fuente. El centro REAL difiere del pedido: `centro_efectivo = clamp_par(centro - win/2) + win/2`.
