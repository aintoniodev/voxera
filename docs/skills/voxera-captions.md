# voxera-captions — subtítulos karaoke/estáticos con ASR word-level

> Mirror en repo del skill del agente (`project:improve-my-sound:voxera-captions`).
> Canonical: skill store local de pi; este archivo versiona el conocimiento en el repo.

## When to Use

Generar subtítulos/karaoke en vídeos (`voxera video captions`), editar
`src/voxera/captions.py`, diagnosticar subtítulos que aparecen fuera de
tiempo, que tienen words_ids raros, o que no se ven (burn-in fallido),
o replicar el estilo de captions cinéticos de TikTok/CapCut/Descript.

## Procedure

1. Comando:
   `.venv/Scripts/voxera video captions IN -o OUT [--model base|small|medium|large-v3] [--lang xx|auto] [--style karaoke|static] [--text-style classic|playful] [--font-size N] [--outline N] [--max-lines N] [--chars-per-sec F] [--highlight w1,w2] [--words-json PATH] [--ass-only PATH] [--crf N] [--audio-bitrate B] [--dry-run]`.
   Defaults: `model=base`, `style=karaoke`, `text_style=classic`,
   `font_size=72`, `outline=3`, `max_lines=3`, `chars_per_sec=18`,
   `margin_v=380`, `safe_box=(900,1160)`.

2. **ASR** (`transcribe_words`): faster-whisper con `word_timestamps=True`,
   `vad_filter=True` (por defecto). Modelo `base` en CPU (int8). Importa
   bajo demanda — `import voxera.captions` no falla sin el paquete, solo
   al llamar `transcribe_words`. Las palabras se cuantizan a la rejilla
   de frames 30 fps (`round(t*30)/30`).

3. **Cues** (`words_to_cues`): packing greedy de palabras en líneas.
   Rompe línea cuando `len(chars)/chars_per_sec` se excede o la línea
   supera ~34 chars. Prefiere romper tras puntuación (`, . ! ? ; :`).
   Cada cue es un evento ASS independiente (no se solapan).

4. **ASS** (`build_ass`): documento ASS v4.00+ con PlayResX=1080, PlayResY=1920,
   WrapStyle=2, ScaledBorderAndShadow=yes. Estilo "Karaoke": DejaVu Sans Bold,
   `{\k<cs>}` por palabra (cs = duración en centésimas). Est texto plano con
   `{\fad(80,80)}`. `playful`: minúsculas + sin puntuación trailing. `highlight`:
   palabras en naranja (`\c&H0000D7FF&`).

5. **Burn-in**: ffmpeg un solo paso:
   `ffmpeg -y -i IN -vf "subtitles='<ASS>'" -c:v libx264 -crf 18 -preset medium -c:a aac -b:a 192k -shortest OUT`.
   Verificación: duración salida == entrada ± (2 frames + granularidad AAC
   21.3 ms) — el re-encode cuantiza la duración del contenedor; el burn-in
   NO cambia la línea de tiempo.

6. `--dry-run`: imprime VOXERA PLAN con modelo, estilo, safe box, etc.
   `--ass-only PATH`: escribe el ASS sin burn-in (para inspección manual).

## Pitfalls

- **Windows path escaping**: la ruta en `subtitles='...'` requiere
  `\\` → `/`, `:` → `\\:`, `'` → `\\'`. `captions._escape_ffmpeg_path`
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
- **ASS temporal limpiado**: el ASS temporal se borra tras el burn-in
  a menos que se use `--ass-only`. Si se necesita el ASS, usar
  `--ass-only PATH`.
- **faster-whisper se importa bajo demanda**: el módulo `captions.py`
  se puede importar sin faster-whisper; solo falla al llamar
  `transcribe_words`. Para tests unitarios, esto permite testear
  build_ass sin el paquete instalado.

## Verification

1. Suite unitaria: `python -m pytest tests/test_captions.py -q`
   (test_captions: ~20 tests: ASS sections, karaoke timing, static,
   playful, highlight, margins, cues packing, path escaping, ffmpeg
   time format, quantize, plan, integration burn-in).
2. Integration burn-in: words.json → testsrc2 2s → ASS → burn →
   ffprobe duration == input ± 1 frame.
3. `ass_only` returns .ASS file with valid [Script Info] and Dialogue.
4. CLI: `python -m voxera.cli video captions --help` muestra opciones
   con defaults; `--dry-run` imprime VOXERA PLAN; EnhancementError
   → stderr + exit 1.
