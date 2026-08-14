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

## Reference Implementation (código núcleo)

La cadena completa es: VAD de envolvente → tramos a conservar → snap a rejilla de frames → un solo paso ffmpeg con select/aselect. Sin estas funciones exactas es fácil cortar respiraciones, desincronizar A/V o dejar un frame extra por corte.

```python
import numpy as np

SR = 48000          # rejilla interna (aresample antes del aselect)
TRIGGERS = {"light": 1.5, "medium": 0.8, "aggressive": 0.4}  # gaps > trigger se recortan
MARGIN_S = 0.2      # margen de respiración SIEMPRE incluido (nunca se cortan respiraciones)

def envelope_segments(samples: np.ndarray) -> list[tuple[int, int]]:
    """Segmentos de voz en samples: envolvente RMS 30 ms sobre umbral relativo.
    webrtcvad es poco fiable a nivel de gap (marca ruido de piso como voz):
    activo = env > max(-50, p75(env)-12) dBFS. Expandidos por el margen y fusionados."""
    frame_len = int(SR * 30 / 1000)
    n = len(samples) // frame_len
    if n == 0:
        return []
    frames = samples[: n * frame_len].reshape(n, frame_len).astype(np.float64)
    env = 20.0 * np.log10(np.sqrt((frames**2).mean(axis=1)) + 1e-12)
    threshold = max(-50.0, float(np.percentile(env, 75)) - 12.0)
    active = env > threshold
    margin = int(MARGIN_S * SR / frame_len)
    runs, start = [], None
    for i, flag in enumerate(np.concatenate([[False], active, [False]])):
        if flag and start is None:
            start = i - 1
        elif not flag and start is not None:
            runs.append((start - 1, i - 2))
            start = None
    expanded = []
    for a, b in runs:
        ea, eb = max(0, a - margin), min(b + margin, n - 1)
        if expanded and ea <= expanded[-1][1]:
            expanded[-1] = (expanded[-1][0], max(expanded[-1][1], eb))
        else:
            expanded.append((ea, eb))
    return [(a * frame_len, min((b + 1) * frame_len, len(samples))) for a, b in expanded]

def detect_keep_parts(samples: np.ndarray, level: str, keep: float) -> list[tuple[float, float]]:
    """Tramos [inicio, fin) s que se CONSERVAN. Voz siempre entera; cada gap
    > trigger se recorta a `keep` s desde su inicio; gaps cortos intactos."""
    trigger = TRIGGERS[level]
    x = np.asarray(samples, dtype=np.float32)
    total = len(x) / SR
    segs_s = [(a / SR, min(b / SR, total)) for a, b in envelope_segments(x)]
    if not segs_s:
        return []  # sin voz: error "sin voz detectable"
    parts, prev = [], 0.0
    for a, b in segs_s:
        parts.append((prev, min(prev + keep, a)) if a - prev > trigger else (prev, a))
        parts.append((a, b))  # voz: siempre entera
        prev = b
    if total - prev > trigger:
        parts.append((prev, min(prev + keep, total)))
    else:
        parts.append((prev, total))
    merged = []  # fusión de tramos contiguos
    for a, b in parts:
        if b - a <= 1e-6:
            continue
        if merged and a <= merged[-1][1] + 1e-6:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged

def quantize_frames(parts: list[tuple[float, float]], fps: float) -> list[tuple[float, float]]:
    """Snap de cortes a la rejilla de frames round(t*fps)/fps — ES el sync A/V:
    el audio se corta en los MISMOS instantes que el vídeo. Tramos sub-frame
    se descartan; tramos pegados tras el snap se fusionan."""
    out, frame = [], 1.0 / fps
    for a, b in parts:
        qa, qb = round(a * fps) / fps, round(b * fps) / fps
        if qb - qa < 0.5 * frame:
            continue
        if out and qa <= out[-1][1] + 1e-9:
            out[-1] = (out[-1][0], max(out[-1][1], qb))
        else:
            out.append((qa, qb))
    return out

def build_cut_filters(parts: list[tuple[float, float]], fps: float) -> tuple[str, str]:
    """(vf, af) con la MISMA expresión. gte*lt en vez de between(): el extremo
    superior es EXCLUSIVO — el primer frame de cada silencio se cae."""
    terms = "+".join(f"gte(t,{a:.6f})*lt(t,{b:.6f})" for a, b in parts)
    vf = f"select='{terms}',setpts=N/{fps:.6f}/TB"
    af = f"aresample={SR},aselect='{terms}',asetpts=N/{SR}/TB"
    return vf, af

# Un solo paso ffmpeg:  -vf "$vf" -af "$af" libx264 CRF 18 + AAC 192k + -shortest
```

Notas de réplica: AAC añade delay de encoder (~44 ms) → `-shortest` + tolerancia 0.3 s (sync real 4-16 ms); el gap justo en el trigger es inestable (jitter ±1 frame) — en tests usar light/aggressive y solo estructura para medium; `keep 0` = cortes a cero (sonido encadenado).
