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

## Procedure

1. **Análisis del source** — Extraer metadata y envolvente de energía:
   ```bash
   .venv-video/Scripts/voxera video info raw.mp4          # ffprobe JSON (resolución, fps, duración)
   .venv-video/Scripts/voxera analyze raw.mp4 --format json -o analyze.json
   ```
   La envolvente de energía (30 ms, VAD thr=max(-50, p75-12) dBFS, margen de
   respiración 200 ms SIEMPRE incluido) produce las ventanas de énfasis y el
   mapa de silencios. El mapa se reutiliza para captions (no re-detectar — la
   alucinación de Whisper en silencio es real).

2. **Transcripción word-level** — NUEVA dependencia (único gap del pipeline):
   ```
   faster-whisper (word-level JSON) → transcripts/words.json
   ```
   Opcional: WhisperX para forced alignment; pyannote para diarización
   (HF gating check). faster-whisper se instala como dependencia nueva;
   pyproject.toml aún no lo incluye — añadir a `optional-dependencies.video`.

3. **Plan de edición (LLM planner)** — El LLM lee el transcript + envolvente y
   emite el JSON edit-spec (contrato abajo). El agente **planifica, nunca ejecuta**.
   Guardas deterministas: sin cortes en medio de frase, trigger levels del
   cutsilence (light/medium/aggressive), duración máxima de clip, timestamps
   cuantizados a la rejilla de frames.

   ```json
   { "version": 1, "source": "raw.mp4",
     "keep_spans": [[0.0, 8.4], [9.1, 31.2]],
     "hook": {"type": "zoom-grow", "at": 0.0, "pct": 35, "curve": 62},
     "effects": [
       {"cmd": "video zoom", "args": {"anchor": [0.58, 0.24], "dir": "grow", "at": [12.0, 16.0]}},
       {"cmd": "audio riser", "args": {"mood": "tension", "hit": 31.2}} ],
     "captions": {"style": "karaoke-word", "highlight": ["hook", "CTA"]},
     "target": {"aspect": "9:16", "max_dur": 45, "crf": 18} }
   ```

4. **Efectos de video** — Aplicar zoom/magnify/teleport/stabilize según el plan:
   ```bash
   .venv-video/Scripts/voxera video zoom raw.mp4 -o tmp_zoom.mp4 \
       --anchor 0.58,0.24 --dir grow --pct 35 --curve 62 --auto-emphasis
   .venv-video/Scripts/voxera video magnify raw.mp4 -o tmp_mag.mp4 \
       --center 0.5,0.4 --motion voice
   ```
   Zoom: curva 62, `--auto-emphasis` en picos de voz. Todos numerically verified.

5. **Efectos de audio** — Transiciones tonales, risers, melodía (tabla 8 moods):
   ```bash
   .venv-video/Scripts/voxera audio riser raw.mp4 -o tmp_riser.mp4 \
       --mood tension --hit 31.2    # el riser TERMINA en el corte
   .venv-video/Scripts/voxera audio lowpass raw.mp4 -o tmp_lowpass.mp4 \
       --start 4 --end 12 --cutoff 800 --transition 1
   .venv-video/Scripts/voxera audio transition raw.mp4 -o tmp_trans.mp4 \
       --from calm --to hope --at 8 --dur 3
   ```
   8 moods: hope/tension/melancholy/triumph/wonder/calm/mystery/urgency.
   `--hit` en riser = instante del corte/drop en segundos. Ducking bajo voz
   recomendado (melody `--duck 6`).

6. **Corte de silencios** — Jump-cuts frame-accurate con sync A/V:
   ```bash
   .venv-video/Scripts/voxera video cutsilence tmp_effects.mp4 -o tmp_cut.mp4 \
       --level medium --keep 0.15
   ```
   Defaults: medium (gaps > 0.8 s), keep 0.15 s; aggressive gaps > 0.4 s;
   VAD envelope 30 ms thr=max(-50, p75-12) dBFS; margen respiración 200 ms
   SIEMPRE; cuantización a rejilla de frames; `gte*lt` (no `between()`); un
   solo paso ffmpeg: `libx264 CRF 18 + AAC 192k + -shortest`.

7. **Captions** — Word JSON → cues ASS karaoke (`\k` tags) → ffmpeg subtitles=
   (libass burn-in):
   - Estilo: white + black stroke, 60–80 pt, ≤3 lines, center-safe box
     900×1160 px.
   - Filtro ffmpeg: `subtitles="captions.ass":force_style='...'` sobre el
     stream de vídeo recortado. Los `\k` tags sincronizan palabra a palabra.
   - **No hay subcommands de transcribe/caption en voxera aún** — la generación
     del ASS se hace fuera del CLI (script auxiliar o módulo nuevo).

8. **Render** — UN solo paso ffmpeg (frame-grid quantized):
   ```
   vf=select='gte(t,a)*lt(t,b)+...',setpts=N/FPS/TB
   af=aresample=48000,aselect='(misma expr)',asetpts=N/48000/TB
   libx264 CRF 18 + AAC 192k + -shortest
   ```
   Aspecto 9:16 (crop/reframe). El audio y vídeo se cortan en los MISMOS
   instantes. `gte*lt` = extremo superior EXCLUSIVO. AAC delay ~44 ms →
   `-shortest`.

9. **QA** — Verificación numérica post-render:
   - Container dur == suma de tramos cuantizados (±1 frame).
   - A/V sync < 20 ms (AAC delay ~44 ms, sync real 4–16 ms medido).
   - Per-effect: SSIM zoom (0.997 en picos), FFT lowpass/tonal, frame counts
     cutsilence. Sin voz → exit 1; sin silencios > trigger → copia directa.
   - CLI check: `voxera video info short.mp4` para duración y resolución.

## Pitfalls

- **faster-whisper no está en pyproject.toml** — Hay que añadirlo a
  `optional-dependencies.video` como `faster-whisper` antes de implementar
  la etapa 2. Es la ÚNICA dependencia nueva del pipeline.
- **No existe subcommand `transcribe` ni `caption`** — El pipeline los
  necesita. La generación del ASS karaoke + word-level timing se implementa
  como módulo nuevo o script auxiliar fuera del CLI actual.
- **AAC delay ~44 ms** — El encoder de AAC añade delay; `-shortest` en el
  render evita que el stream de audio se extienda. Sync real medido: 4–16 ms.
- **`between()` en select/aselect** — El extremo superior es INCLUSIVO; usar
  SIEMPRE `gte*lt` para que el primer frame de cada silencio se cae (evita
  1 frame extra por corte).
- **Whisper alucina en silencio** — Reutilizar el mapa de silencios de la
  etapa 1 (VAD de envolvente) para los captions, NO re-detectar con Whisper.
- **Rejilla de frames** — Los timestamps se cuantizan con `round(t*fps)/fps`.
  Un corte justo en el trigger (0.8 s con medium) tiene jitter ±1 frame
  (~33 ms a 30 fps): en tests usar light/aggressive para forma exacta.
- **Hooks que resuelven muy rápido** — La evidencia mide 4–6 s como hooks que
  salvan más retención vs 2–3 s. Hook ≤1.5 s es para scroll-stop, no para
  resolver la promesa. Curiosity gap es el único mecanismo experimental.
- **Slow motion ausente** — El efecto con más apoyo experimental (N=27.227)
  no está como primitive en voxera. Para contenido de producto/demo, considerar
  añadirlo como paso futuro.

## Verification

1. **Edit-spec emitido** — El JSON tiene `version: 1`, `source`, `keep_spans`,
   `hook`, `effects`, `captions`, `target`. Todos los `cmd` en `effects` son
   subcomandos reales de voxera (video info|enhance|compare|cutsilence|zoom|
   magnify|teleport|stabilize | audio lowpass|transition|riser|melody|master|
   restore|score|silence | analyze | inspect | device).
2. **Render exitoso** — `voxera video info short.mp4` confirma resolución 9:16
   (1080×1920) y duración dentro del `max_dur` del target.
3. **Container dur** — Igualdad con suma de `keep_spans` cuantizados (±1 frame).
4. **A/V sync** — Medido < 20 ms (AAC delay ~44 ms, tolerancia 0.3 s en
   duración total; sync real típico 4–16 ms).
5. **Captions visibles** — ASS karaoke burn-in con `\k` tags; estilo white +
   black stroke, 60–80 pt, ≤3 lines, dentro del safe zone 900×1160 px.
6. **Per-effect checks** — SSIM zoom en picos ≥ 0.997; FFT lowpass confirma
   corte en frecuencia; frame count cutsilence == suma de tramos (±1).
7. **Edge cases** — Sin voz → exit 1; sin silencios > trigger → copia directa
   con nota; sin pista de audio → error; `--dry-run` imprime plan sin escribir.

## Resumen operativo

- **Hecho:** Skill draft completo con 7 etapas del pipeline (analyze →
  transcribe → plan → effects → captions → render → QA), JSON edit-spec
  contract, y verificación numérica copiada del blueprint.
- **Estado:** 5 de 7 etapas cubiertas por subcomandos existentes de voxera;
  etapa 2 (faster-whisper) y 7 (ASS generation) requieren código nuevo.
  pyproject.toml no incluye faster-whisper aún.
- **Riesgos:** La etapa de captions es el mayor gap (no hay subcommand ni
  módulo). La evidencia sobre hooks ≤1.5 s es plataformas-specific y no
  validada academicamente. Slow motion (N=27.227) no está como primitive.
