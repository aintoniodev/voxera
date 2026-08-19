# voxera-captions — subtítulos karaoke/estáticos con ASR word-level

> Mirror en repo del skill del agente (`project:improve-my-sound:voxera-captions`).
> Canonical: skill store local de pi; este archivo versiona el conocimiento en el repo.
> Base científica: `synthesis-subtitles-captions.md` (scientific-synthesis, 2026-08-19).
> Implementación: `src/voxera/captions.py` (CAMBIOs 1–4 aplicados; CAMBIO 5 = gate A/B).

## When to Use

Generar subtítulos/karaoke en vídeos (`voxera video captions`), editar
`src/voxera/captions.py`, diagnosticar subtítulos que aparecen fuera de
tiempo, que tienen words_ids raros, o que no se ven (burn-in fallido),
o replicar el estilo de captions cinéticos de TikTok/CapCut/Descript.

## Cómo se construye (base científica)

Los 5 cambios de la síntesis científica (`synthesis-subtitles-captions.md`)
están aplicados al pipeline. Reglas que la evidencia valida y que el código
impone automáticamente:

| Regla | Fuente | Dónde se aplica |
|---|---|---|
| Velocidad 16–18 cps (objetivo ES intralingual); warn >18, fail >20 cps | Szarkowska & Gerber-Morón 2018 (PLOS ONE, eye-tracking N=74); Netflix ES 17 cps; UNE 153010 15 cps | `audit_cues` en cada ejecución (QA a stderr) |
| Duración mínima de cue 0.83 s (20 frames) y out-time +0.15 s tras la última palabra | Netflix Subtitle Timing Guidelines | `build_ass` (pad automático) |
| Cortes SIEMPRE en unidades sintácticas: tras puntuación, antes de conjunciones/preposiciones; nunca partir artículo+nombre, preposición+frase, auxiliar+verbo, nombre+apellido | BBC Subtitle Guidelines + Netflix US/ES | `words_to_cues` (reglas negativas + backtrack al último buen corte) |
| 2 líneas = punto dulce en vertical 9:16 (más atención que 1 línea) | Li 2026 (N=211, eye-tracking TikTok) | `_group_two_lines` (eventos de 2 líneas, nunca 3) |
| Hook de texto arriba: ≤4 palabras, 0.8–2.0 s, MAYÚSCULAS, fade, sincronizado a la palabra ancla, nunca sobre cue de 2+ líneas | Netflix "texto en pantalla" + Amir et al. 2026 (QoMEX: overlays no degradan calidad pero 62% molestos) | `resolve_hooks` + `place_hooks` (los conflictos se descartan con nota) |
| Español: ¿/¡ obligatorios (playful nunca los elimina); decimales y hora según variante | RAE / Netflix ES guide | `_apply_es_variant` (es-ES / es-LATAM) |
| Estilo: blanco + contorno, 68–80 px (~4% altura en 9:16), 1 keyword en color | BBC (75–86 px en 1920) + Krejtz 2016 (content words) | `font_size=72`, `outline=3`, `highlight` |
| Cinético \\k = marcador de ritmo de lectura (defendible); pop/bounce por palabra SIN evidencia → no añadir | gap declarado en la síntesis | `style=karaoke` (solo \\k) |

## Procedure

1. Comando:
   `.venv/Scripts/voxera video captions IN -o OUT [--model base|small|medium|large-v3] [--lang xx|auto] [--style karaoke|static] [--text-style classic|playful] [--font-size N] [--outline N] [--max-lines N] [--chars-per-sec F] [--es-variant es-ES|es-LATAM] [--hook "TEXTO@ANCLA[@DUR]"]... [--strict-qa] [--highlight w1,w2] [--words-json PATH] [--ass-only PATH] [--crf N] [--audio-bitrate B] [--dry-run]`.
   Defaults: `model=base`, `style=karaoke`, `text_style=classic`,
   `font_size=72`, `outline=3`, `max_lines=3`, `chars_per_sec=18`,
   `margin_v=380`, `safe_box=(900,1160)`, `two_lines=True` (2 líneas en vertical).

2. **ASR** (`transcribe_words`): faster-whisper con `word_timestamps=True`,
   `vad_filter=True` (por defecto). Modelo `base` en CPU (int8). Importa
   bajo demanda — `import voxera.captions` no falla sin el paquete, solo
   al llamar `transcribe_words`. Las palabras se cuantizan a la rejilla
   de frames 30 fps (`round(t*30)/30`).

3. **Cues** (`words_to_cues`): packing greedy con segmentación sintáctica.
   Rompe línea cuando `len(chars)/chars_per_sec` se excede o la línea
   supera ~34 chars. Prefiere romper tras puntuación, antes de
   conjunciones (`y, e, o, pero, que…`) y antes de preposiciones.
   Reglas negativas (NUNCA partir): artículo+nombre, preposición+frase,
   auxiliar/negación+verbo, nombre+apellido (capitalizadas). Si el punto
   de ruptura cae en una unidad prohibida, retrocede al último buen corte
   de la línea (backtrack). Cada cue es un evento ASS independiente.

4. **2 líneas** (`_group_two_lines`): cues consecutivos con corte
   sintácticamente bueno y ≤25 chars por línea se agrupan en un evento
   de 2 líneas (`\N` entre líneas, karaoke fluye por ambas). Es el punto
   dulce de atención en vertical (Li 2026). Desactivar con `max_lines=1`.

5. **QA de lectura** (`audit_cues`, corre en cada ejecución y en `--dry-run`):
   warn >18 cps, fail >20 cps, duración mínima 0.83 s por cue. Los hallazgos
   van a stderr con prefijo `QA:`; `--strict-qa` aborta si hay algún fail.
   `build_ass` además respeta out-time (+0.15 s tras la última palabra) y
   hueco de 2 frames antes del cue siguiente.

6. **Hooks** (`--hook "TEXTO@ANCLA[@DUR]"`, repetible): texto de pantalla
   arriba (estilo `Hook`, `\an8`, MAYÚSCULAS, fade 80 ms, tamaño ~1.15×).
   Aparece 0.1 s tras terminar la palabra ancla del transcript (sincronía
   con el audio). Duración clampa a [0.8, 2.0] s. Reglas automáticas:
   ≤4 palabras (error si más), 1 hook simultáneo, nunca solapando un cue
   de 2+ líneas o >30 chars (el hook se descarta con nota `QA:`).

7. **Español** (`--es-variant`): es-ES → decimales con coma (`3,5`);
   es-LATAM → decimales con punto y hora 12h (`2:00 p. m.`). El modo
   `playful` NUNCA elimina ¿/¡ (obligatorios en español).

8. **ASS** (`build_ass`): documento ASS v4.00+ con PlayResX=1080,
   PlayResY=1920, WrapStyle=2, ScaledBorderAndShadow=yes. Estilo "Karaoke":
   DejaVu Sans Bold, `{\k<cs>}` por palabra (cs = duración en centésimas).
   Estilo "Hook": alineación 8 (arriba-centro), margin_v=269 (14% del
   canvas, bajo la franja de UI). `playful`: minúsculas + sin puntuación
   trailing. `highlight`: palabras en naranja (`\c&H0000D7FF&`).

9. **Burn-in**: ffmpeg un solo paso:
   `ffmpeg -y -i IN -vf "subtitles='<ASS>'" -c:v libx264 -crf 18 -preset medium -c:a aac -b:a 192k -shortest OUT`.
   Verificación: duración salida == entrada ± (2 frames + granularidad AAC
   21.3 ms) — el re-encode cuantiza la duración del contenedor; el burn-in
   NO cambia la línea de tiempo.

10. `--dry-run`: imprime VOXERA PLAN con modelo, estilo, safe box, es_variant,
    nº de hooks y umbrales QA. `--ass-only PATH`: escribe el ASS sin burn-in.

## Pitfalls

- **Windows path escaping**: la ruta en `subtitles='...'` requiere
  `\\` → `/`, `:` → `\:`, `'` → `\'`. `captions._escape_ffmpeg_path`
  lo maneja; si se construye el filtro a mano, usar esa función.
- **Whisper hallucination en silencio**: si el vídeo tiene tramos largos
  de silencio, Whisper puede "inventar" texto. Usar `vad_filter=True`
  (default) para minimizar esto. Si se desactiva VAD, el módulo puede
  devolver palabras fantasma.
- **Sin voz detectable**: si `transcribe_words` devuelve 0 palabras,
  lanza `EnhancementError("sin voz detectable")`. Verificar que el
  vídeo tiene pista de audio con contenido de voz.
- **Frame-grid quantization**: los timings de palabra se redondean a
  la rejilla de 30 fps. Words que empiezan/terminan entre frames se
  ajustan al frame más cercano. Esto puede causar diferencias de ±1
  frame vs los timestamps originales de Whisper.
- **Ancla de hook inexistente**: `--hook "OJO@palabranoencontrada"` lanza
  EnhancementError. El ancla debe ser una palabra real del transcript
  (case-insensitive, sin puntuación).
- **Hook descartado silenciosamente**: si el hook solapa otro hook o un
  cue ancho/2 líneas se descarta con nota `QA:` en stderr — no rompe el
  burn-in. Revisar las notas si el hook "no aparece".
- **playful NO toca ¿/¡**: a diferencia de la puntuación trailing, los
  signos de apertura españoles son parte de la palabra y se conservan.
- **ASS temporal limpiado**: el ASS temporal se borra tras el burn-in
  a menos que se use `--ass-only`. Si se necesita el ASS, usar
  `--ass-only PATH`.
- **faster-whisper se importa bajo demanda**: el módulo `captions.py`
  se puede importar sin faster-whisper; solo falla al llamar
  `transcribe_words`. Para tests unitarios, esto permite testear
  build_ass sin el paquete instalado.

## A/B de estilo (CAMBIO 5 — gate de decisión)

La ciencia no puede decidir si el cinético gana retención en el feed real
(gap declarado en la síntesis). Plan de experimento con baseline ya
disponible en el pipeline:

- Variante A (actual): `--style karaoke` + 1 keyword en color.
- Variante B: `--style static` + `--highlight palabra_clave`.
- Gate: métricas propias (medianas, 7–14 días) + Track-8 humano ≥60%.
  No añadir pop/bounce/escala por palabra sin A/B propio que lo gane.

## Verification

1. Suite unitaria: `python -m pytest tests/test_captions.py -q`
   (test_captions: ASS sections, karaoke timing, static, playful,
   highlight, margins, cues packing + segmentación sintáctica +
   backtrack, 2 líneas, hooks, es_variant, QA, path escaping, ffmpeg
   time format, quantize, plan, integration burn-in).
2. Integration burn-in: words.json → testsrc2 2s → ASS → burn →
   ffprobe duration == input ± 1 frame.
3. `ass_only` returns .ASS file with valid [Script Info] y Dialogue
   (incluye estilo Hook y eventos `Dialogue: 2,` cuando hay hooks).
4. CLI: `python -m voxera.cli video captions --help` muestra opciones
   con defaults (`--es-variant`, `--hook`, `--strict-qa`); `--dry-run`
   imprime VOXERA PLAN; EnhancementError → stderr + exit 1.
