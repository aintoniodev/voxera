# voxera-autopilot — raw MP4 → short optimizado por métricas

> Mirror en repo del skill del agente (`project:improve-my-sound:voxera-autopilot`).
> Canonical: skill store local de pi; este archivo versiona el conocimiento en el repo.

## When to Use

Convertir un MP4 crudo (podcast, talking-head, cámara única, cualquier aspecto)
en un short 9:16 optimizado para métricas de plataforma (TikTok/Reels/Shorts):
hook ≤1.5 s, silencios recortados, efectos de énfasis, captions karaoke-word,
render en un solo paso ffmpeg, y verificación numérica — todo orquestado por un
agente que planifica (JSON edit-spec) y delega la ejecución a voxera.

Aplicar cuando el usuario pida "hazme un short", "edita esto para TikTok",
"optimiza para métricas", o cualquier variante de raw→short con effects+captions.

## Subcomandos disponibles

### autopilot run

```bash
voxera autopilot run INPUT -o OUT \
    [--planner rule|llm] [--words-json PATH] [--llm-cmd CMD] \
    [--max-dur F] [--level light|medium|aggressive] \
    [--aspect 9:16|keep] [--crf N] [--model base|tiny|small] [--dry-run]
```

Pipeline: cutsilence → hook zoom → effects (riser/lowpass/transition/melody) → captions → output.
El manifest QA se escribe a `OUT.manifest.json`.

### autopilot ab

```bash
voxera autopilot ab INPUT -o PREFIX \
    [--planner-a rule|llm] [--planner-b rule|llm] \
    [--llm-cmd CMD] [--max-dur F] [--level ...] \
    [--aspect ...] [--crf N] [--model ...]
```

Ejecuta ambas variantes → `PREFIX.rule.mp4` y `PREFIX.llm.mp4` (o el label elegido);
genera `PREFIX.ab_manifest.json` con checklist de publicación.

## Edit-spec JSON (contrato v1)

```json
{
  "version": 1,
  "source": "raw.mp4",
  "level": "medium",
  "keep_spans": [],
  "hook": {"type": "zoom-grow", "at": 0.0, "pct": 35, "curve": 62, "anchor": [0.5, 0.33]},
  "effects": [
    {"cmd": "audio riser", "args": {"mood": "tension", "hit": 31.2}}
  ],
  "captions": {
    "enabled": true,
    "style": "karaoke",
    "text_style": "classic",
    "highlight": [],
    "hooks": [
      {"text": "¿LO SABÍAS?", "anchor": "clave", "dur": 0.9},
      {"text": "PERO OJO", "anchor": "trampa"}
    ],
    "es_variant": "es-ES",
    "strict_qa": false
  },
  "target": {"aspect": "9:16", "max_dur": 45, "crf": 18}
}
```

### captions (keys opcionales)

- `hooks` — lista de `{"text", "anchor", "dur"?}`: texto de pantalla arriba
  (≤4 palabras, 0.8–2.0 s, MAYÚSCULAS, fade), sincronizado a la palabra `anchor`
  del transcript (Síntesis Theme 5; ver `voxera-captions`). `dur` opcional, se
  clampa a [0.8, 2.0]. Los hooks en conflicto (2 simultáneos o sobre un cue de
  2+ líneas) se descartan con nota `QA:` — no rompen el burn-in.
- `es_variant` — `"es-ES"` (decimales con coma) | `"es-LATAM"` (punto y hora
  a. m./p. m.). El modo `playful` nunca elimina ¿/¡.
- `strict_qa` — `true` aborta la edición si algún cue supera 20 cps (QA de
  lectura, Síntesis §7 CAMBIO 1).

### Cmds permitidos en effects

| Cmd | Args válidos |
|-----|-------------|
| `video zoom` | pct, curve, easing, direction, anchor [x,y], start, end, hold, pulse_dur, max_pulses |
| `video magnify` | center [x,y], radius, grid, hold, move_dur, sharpen, start, end |
| `video teleport` | start, end, shift |
| `video stabilize` | smoothing, max_shift |
| `audio lowpass` | cutoff, transition, start, end |
| `audio transition` | from, to, at, dur, mood, key, curve, easing, gain |
| `audio riser` | mood, hit, dur, gain, seed, tail |
| `audio melody` | mood, from, to, duck, seed, gain, bars, start |

Validación: `validate_edit_spec()` rechaza version != 1, cmd desconocido, key de arg
desconocida, valores malformados, keep_spans inválidos, hook type != "zoom-grow",
captions sin keys requeridas, target.max_dur <= 0, hooks sin `text`/`anchor` o con
`dur` no numérico, `es_variant` fuera de (es-ES, es-LATAM), `strict_qa` no bool.

## Pipeline stages

1. **cutsilence** — `video_silence.cut_silence` con `level` del spec. Genera S1.
2. **hook zoom** — `video_zoom.zoom_video` con `ZoomOptions` del hook del spec. Genera S2.
3. **effects** — Por cada effect en orden: riser (audio_tonal), lowpass (audio_lowpass),
   transition (audio_tonal), melody (audio_tonal). Cada uno extrae audio, aplica,
   y remuxea con ffmpeg. Genera S3, S4...
4. **captions** — `captions.captions_video` con `words_json` y estilo del spec,
   pasando `hooks`, `es_variant` y `strict_qa` (el stage registra el nº de hooks
   en el manifest). **Captions SIEMPRE van al final** sobre el timeline ya
   cortado (burn-in final).

### Transcripción y timing de captions

- **words_json dado**: se usa directamente (caller garantiza tiempos en la timeline final).
- **Sin words_json**: se transcribe del vídeo ORIGINAL (mejor ASR en speech continuo),
  pero captions se aplican al vídeo ya cortado. Esto puede causar desfase temporal;
  la solución correcta es pasar `--words-json` con tiempos del vídeo final, o transcribir
  después del cutsilence.

## Inventario de subcomandos de voxera (referencia)

### video
`info` · `enhance` · `compare` · `cutsilence` · `zoom` · `magnify` · `teleport` · `stabilize` · `captions`

### audio
`lowpass` · `transition` · `riser` · `melody` · `master` · `restore` · `score` · `silence`

### autopilot
`run` · `ab`

## A/B protocol (checklist de `run_ab`)

```json
[
  "publicar ambas variantes el mismo día (mismo contenido, solo difiere la edición)",
  "registrar medianas (no medias) de views/completion/3s-retention a los 7-14 días",
  "replicar el ganador en un segundo lote antes de fijar criterios",
  "gate humano Track-8 (≥60% preferencia) si hay oyentes disponibles"
]
```

Variantes: `{prefix}.{planner_a}.mp4` y `{prefix}.{planner_b}.mp4` +
`{prefix}.ab_manifest.json`. Si planner_b falla, se registra el error pero
el harness no crashea (fail-open para la variante A).

## Pitfalls

- **Transcribir DESPUÉS de cutsilence** — Si se transcribe el vídeo original, los
  timestamps de las palabras corresponden a la timeline pre-cortes. Al aplicar captions
  al vídeo ya cortado, los tiempos están desplazados. Solución: pasar `--words-json`
  con tiempos del vídeo final, o transcribir del cutsilence output.
- **El LLM nunca ejecuta** — El planner LLM genera el spec; el executor compone
  APIs de voxera directamente (sin subprocess al CLI). El LLM se ejecuta via
  shell-out con timeout 600s y validación estricta del output JSON.
- **Validar specs antes de ejecutar** — `validate_edit_spec()` rechaza cmds
  desconocidos, args inválidos, y valores fuera de rango antes de que toque ffmpeg.
- **Aislamiento de fallos en ab** — Si planner_b falla, la variante A se completa
  normalmente y el error se registra en el manifest. El harness nunca aborta
  por un solo planner.
- **No pip install** — El módulo autopilot solo importa módulos de voxera ya
  existentes. No añade dependencias nuevas.

## Verification

1. **Unit tests**: `pytest tests/test_autopilot.py -q`
   - validate_edit_spec: canonical, bad version, bad cmd, bad arg, bad keep_spans, bad hook, bad target, captions missing key
   - rule_plan: determinism, structure, riser hit, captions enabled
   - llm_plan: error paths (llm_cmd roto → error, garbage output → error;
     llm_cmd=None usa el default `opencode run -m opencode/mimo-v2.5-free`)
2. **Integration tests**: run_autopilot dry_run (sin archivos), rule run con words_json (output existe, QA dur ≈ input dur), run_ab con ambos rule (2 outputs + manifest con checklist)
3. **CLI help**: `python -m voxera.cli autopilot --help`, `autopilot run --help`, `autopilot ab --help`
4. **QA manifest**: `{output}.manifest.json` con version, spec, stages, qa (dur_in, dur_out, fps, frames)

## Reference Implementation (arquitectura)

```
 raw.mp4
   │
   ▼ [1 ANALYZE]   ffprobe info + optional energy envelope
   ▼
   │ [2 TRANSCRIBE] faster-whisper word-level JSON (or --words-json)
   ▼
   │ [3 PLAN]       rule_plan (determinista) o llm_plan (shells out to LLM)
   │               → edit-spec JSON validado por validate_edit_spec
   ▼
   │ [4 EXECUTE]    cutsilence → hook_zoom → effects → captions
   │               Cada stage: module API directa (sin subprocess al CLI)
   ▼
   │ [5 QA]         ffprobe → manifest con dur/fps/frames
   ▼
 short.mp4 + manifest.json
```

## Resumen operativo

- **Hecho:** Módulo autopilot.py con validate_edit_spec, rule_plan, llm_plan,
  execute_spec, run_autopilot, run_ab; CLI autopilot run|ab; tests unitarios
  e integración; skill doc actualizada.
- **Estado:** 4 archivos nuevos (autopilot.py, CLI additions, test_autopilot.py,
  voxera-autopilot.md). Suite de tests rápida pasa.
- **Riesgos:** La transcripción con words_json del caller requiere que los
  timestamps estén en la timeline del vídeo final. El LLM planner depende de
  un comando externo (opencode); sin él, solo rule planner funciona.
