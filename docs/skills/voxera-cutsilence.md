# voxera-cutsilence — eliminar silencios de vídeos automáticamente

> Mirror en repo del skill del agente (`project:improve-my-sound:voxera-cutsilence`).
> Canonical: skill store local de pi; este archivo versiona el conocimiento en el repo.

## When to Use

Aplicar edición automática de silencios a vídeos (`voxera video cutsilence`),
editar `src/voxera/video_silence.py`, diagnosticar cortes que desincronizan
audio/vídeo o que cortan respiraciones, o replicar el "remove silence" de
TikTok/CapCut/Descript.

## Procedure

1. Comando:
   `.venv-video/Scripts/voxera video cutsilence IN -o OUT [--level light|medium|aggressive] [--keep S] [--dry-run]`.
   Defaults: `medium` (gaps > 0.8 s) + `keep` 0.15 s; `aggressive` = gaps > 0.4 s;
   `keep 0` = cortes a cero (sonido encadenado).
2. Detección: reutiliza `silence._envelope_segments_samples` (VAD de envolvente
   30 ms, umbral `max(-50, p75-12)` dBFS, margen de respiración 200 ms SIEMPRE
   incluido — las respiraciones nunca se cortan). `detect_keep_parts()`
   conserva voz entera + gaps > trigger recortados a `keep` s desde su inicio;
   gaps ≤ trigger intactos; sin voz → lista vacía (error "sin voz detectable").
3. Sync A/V: los cortes se cuantizan a la rejilla de frames
   (`quantize_frames`: `round(t*fps)/fps`) y el audio se corta en los MISMOS
   instantes. Un solo paso de ffmpeg:
   `vf=select='gte(t,a)*lt(t,b)+...',setpts=N/FPS/TB` y
   `af=aresample=48000,aselect='(misma expr)',asetpts=N/48000/TB`,
   libx264 CRF 18 + AAC 192k + `-shortest`.
4. `gte*lt` en vez de `between()`: el extremo superior es EXCLUSIVO — el
   primer frame de cada silencio se cae (`between()` incluiría 1 frame extra
   por corte). Los tramos pegados tras el snap se fusionan; tramos sub-frame
   se descartan.
5. Verificación del módulo:
   `python -m pytest tests/test_video_silence.py -q --import-mode=importlib`
   (26 tests: partes, cuantización, filtros, opciones, plan, e2e con
   `s.long_gaps()` = voz 1s + gap 2s + voz 1s + gap 1.2s + voz 1s = 6.2 s totales).

## Pitfalls

- El paquete `tests` de Ultralytics en site-packages sombrea el `tests/` local
  (sin `__init__.py`): pytest falla con `ModuleNotFoundError: No module named
  tests.synth`. Usar SIEMPRE `--import-mode=importlib` en este entorno; los
  scripts directos deben cargar `synth.py` por `spec_from_file_location`.
- `s.long_gaps()` dura 6.2 s (1+2+1+1.2+1), no 5.2 s como dice su docstring —
  las expectativas de los tests usan 6.2.
- Tras encode AAC, un audio de silencio puro se extrae a ceros exactos
  (max abs 0.0) pero el VAD puede devolver segmentos: `detect_keep_parts()`
  con `segs_s` vacío debe devolver `[]` explícitamente (si no, el gap final
  conserva `keep` s al inicio y no salta el error de sin-voz).
- El gap justo en el trigger (p. ej. 0.8 s tras márgenes con level medium) es
  inestable (jitter de ±1 frame de 30 ms): en tests usar light/aggressive para
  fijar forma exacta y solo estructura para medium.
- AAC añade delay de encoder (~44 ms): usar `-shortest` y tolerancia 0.3 s en
  duración; sync A/V verificado < 0.1 s (en la práctica 4-16 ms) y conteo de
  frames exacto (±1).
- ffmpeg evalúa select/aselect por frame: un corte cae dentro de un bloque de
  audio (hasta ~21 ms de error de corte) — irrelevante frente a 1 frame de vídeo.
- Los venvs `.venv-video`/`.venv-ims` no existen en todos los checkouts:
  probar con `PYTHONPATH=src python -m voxera.cli` + Python global
  (ffmpeg en `C:/ffmpeg/bin`).

## Verification

1. Suite del módulo: 26 passed (`tests/test_video_silence.py --import-mode=importlib`).
2. E2E sintético: demo 12.8 s con 3 gaps (1.6/0.9/2.3 s) → `aggressive`/`keep 0.10`
   → 9.43 s: ffprobe container == suma de tramos cuantizados (±1 frame),
   frames == `round(dur*fps)` (±1), sync audio/vídeo < 20 ms.
3. E2E real: `media/demo-video.mp4` (40.55 s, 1920x1080@30) → `medium` →
   32.40 s exactos (5 cortes, 8.15 s eliminados), 973 frames (esperado 972±1),
   audio 32.384 s (sync 16 ms).
4. Sin voz (silencio puro) → `EnhancementError` exit 1; sin silencios > trigger
   → copia directa con nota; sin pista de audio → `EnhancementError`.
5. CLI: `--dry-run` imprime VOXERA PLAN con tramos/cortes/filtro; `-o`
   obligatorio (argparse exit 2).
