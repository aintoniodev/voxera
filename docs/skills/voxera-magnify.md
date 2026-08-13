---
name: "voxera-magnify"
description: "Efecto 'Magnify' (lupa) en voxera: `voxera video magnify` (lente circular que amplía la zona, pluma, aro, estática). Usar al aplicar lupas a vídeos, modificar src/voxera/video_magnify.py, o verificar renders de magnify. Incluye la medición del tutorial de @billycreative_ (Premiere 26.3) y cómo verificar numéricamente."
version: 1
created: "2026-08-13"
updated: "2026-08-13"
---
## When to Use
Aplicar lupas programáticas a vídeos (voxera video magnify), editar src/voxera/video_magnify.py, diagnosticar renders de magnify que no amplían, o replicar el efecto "Magnify" del tutorial de @billycreative_ (lente circular que amplía la zona, como una lupa al enseñar un paper).

## Procedure
1. Comando: `.venv-video/Scripts/voxera video magnify IN -o OUT [--center X,Y] [--size F] [--zoom Z] [--feather F] [--ring-width F] [--start/--end] [--dry-run]`
2. Defaults medidos del tutorial (2026-08-13, anillo detectado por Hough + continuidad de borde sobre el TikTok de @billycreative_, 720x1280): lente estática en ~(0.36, 0.29), radio ~255 px = 0.35 del ancho, borde nítido, presente varios segundos. El zoom exacto NO es medible de forma fiable (el vídeo está muy editado, sin frame de referencia limpio): default 3x.
3. Arquitectura del filtro (100 % ffmpeg + numpy): split → crop del área bajo la lente (lado 2r/zoom, centrado) → scale lanczos a 2r → format=rgba → alphamerge con la máscara (alphaextract del PNG) → overlay sobre el original → overlay del aro. Fuera de la lente el frame pasa intacto (diff media < 1 en el vídeo real).
4. Máscaras: PNG RGBA generados con numpy+zlib (sin dependencias nuevas): disco con pluma lineal (alpha = clip((r-d)/f, 0, 1)) y aro blanco antialias ~1 px. Se escriben en un TemporaryDirectory y se limpian tras el encode.
5. Entradas ffmpeg: `-loop 1 -framerate <fps> -t <dur> -i mask.png` (y ring.png) — el -t limita el bucle; overlay con eof_action default (repeat) mantiene el último frame.

## Pitfalls
- Verificación numérica del zoom: el conteo de transiciones de onda cuadrada se rompe con lanczos (ringing crea cruces falsos — 28 cruces para 9 bordes). Usar senoide (lanczos es lineal, solo cambia la escala) + FFT con ventana de >= 6 ciclos; el pico FFT se parte entre bins si hay < 3 ciclos (leakage: pico k=2+k=3 para 2.3 ciclos).
- La lente muestra las franjas zoom veces MÁS anchas (periodo interior = periodo_base · zoom, p. ej. 8px → 8·2.04 = 16.3px), no más estrechas — el periodo pequeño es el del crop fuente.
- FFT sobre región que mezcla filas dentro/fuera del band del crop (el patch ampliado solo cubre ±crop/2 de alto) contamina el pico: medir x en disco 0.6r pero y en ±0.45r.
- ffmpeg 7.1: crop con w/h constantes y x/y estáticos funciona (solo w/h animados congelan); el overlay en posiciones float es correcto.
- argparse: los '%' de los help strings hay que escaparlos como '%%' (ValueError: unsupported format character).
- El venv editable apunta al repo principal, no al worktree: para probar el CLI del worktree usar `PYTHONPATH=src`.

## Verification
1. tests: `.venv-ims/Scripts/python.exe -m pytest tests/test_video_magnify.py -q` (27 tests: validación, geometría, máscaras PNG, filtro, plan, e2e con senoide + segmento + sin aro). Suite completa: 303 passed.
2. E2E numérico: senoide de 8 px + zoom 2 → dentro periodo 8·zoom_eff ± 1 px, fuera 8 px, aro en el radio (pico del perfil radial), diff fuera de la lente < 3.
3. Demo real (media/videos/magnified/, gitignored): sobre el propio TikTok (segmento 21-26 s) — aro en r=252, diff fuera 0.93, dentro 30.7; paper sintético — aro en r=272, diff fuera 0.35, dentro 99.6.
