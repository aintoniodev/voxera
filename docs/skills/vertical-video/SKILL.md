---
name: vertical-video
description: Produce un vídeo vertical (9:16) "producto final" estilo TikTok/Reels a partir de material crudo — color grading, corte de silencios, subtítulos kinéticos palabra a palabra, stickers de emoji CONTEXTUALES al discurso, punch-ins y tarjetas de título — y entrega el MP4 final más una tira comparativa antes/después. Usar cuando el usuario dé o mencione un vídeo y quiera "el vídeo final", "edítamelo", "hazle el montaje", "estilo reels/tiktok", "con subtítulos grandes", "quita los silencios", aunque solo diga la ruta del archivo. NO usar para edición textual de vídeos ya editados ni para subtítulos sueltos sin montaje.
---

# vertical-video — de material crudo a producto final en una petición

El usuario te da un vídeo (o una ruta) y quiere VOLVER A RECIBIR EL PRODUCTO TERMINADO,
no un proceso. Entregable estándar en `<workspace>/tmp/vertical-video-<etiqueta>/`:
`00_comparativa.mp4` (tira RAW | COLOR | FINAL), `04_final.mp4`, `04_delivery.mp4`
(copia para subir), los intermedios y un `README.md` de una página. Todo se valida
antes de entregar (ver checklist). **Nombrar la sala por contenido** (p.ej.
`vertical-video-churreria-parte2`), nunca genérico: el usuario debe poder mapear
entrada → salida sin preguntar.

## Decisiones por defecto (lo que el usuario ya eligió en conversaciones previas)

- **Nada de flashes blancos**: `--flash off` es el default y NO se cambia salvo petición
  explícita. La literatura de montaje (Adobe, r/editors) y el propio usuario los rechazan
  como patrón repetitivo; WCAG 2.3.3 los tolera por debajo de 3/s pero aquí no es cuestión
  médica sino de gusto.
- **El efecto es contextual, no decorativo**: en vez de flash, stickers de emoji que
  SIGNIFICAN lo que se dice (europa/dinero → 💸, sonido → 🔊, crear → ✨). Máx. 1 sticker
  cada ~3 s de habla; 2-4 por vídeo corto. Menos es más.
- **Silencios fuera**: jump-cut automático de silencios internos y colas (mantiene 0.18 s
  de aire). Es la feature que más "pro" hace quedar el resultado.
- Subs kinéticas ON (karaoke palabra a palabra, keywords en color), punch-ins ON (~2.8 s,
  alineados a palabras), títulos ON (2 tarjetas, tipografía combinada).
- **Calidad máxima por defecto** (`--quality max` = slow crf15 + aac 320k): el usuario la
  pidió explícitamente en 2 corridas seguidas (medido: +3.5 dB PSNR vs crf19). El coste
  extra ya no duele gracias al timing audio-first (ver paso 2): re-encodes NUNCA invalidan
  los cortes.

## Flujo (audio-first, 8 pasos)

Los scripts de referencia (probados, Windows) están en `scripts/` de esta skill. Cópialos
al workspace y ajústalos allí; no reinventas lo que ya funciona.

### 0. Sondeo + huella (determinista, siempre primero)

```bash
ffprobe -v error -show_entries stream=codec_type,width,height,r_frame_rate,sample_rate \
  -show_entries format=duration -of default=noprint_wrappers=1 <vídeo>
sha256sum <vídeo>   # guardar en README: la huella identifica la entrada sin ambigüedad
```

- Ya vertical (≈9:16): sin crop, `grade_reframe.py --no-crop` (solo color+escala).
- Horizontal (16:9 u otras): crop centrado a 9:16 (o sobre el sujeto si está descentrado).
- Duración >90 s: avisar del coste de render y ofrecer iterar en modo preview (paso 6).
- Entornos python: `faster_whisper` está en `.venv` del repo improve-my-sound; PIL/opencv
  en `.venv-video` (comprobar con `pip show`, puede cambiar). Necesita ffmpeg con libx264 +
  libass en el PATH (aquí `C:/ffmpeg/bin`).

### 1. Color + reframe → `02_graded.mp4`

`grade_reframe.py [--no-crop] [--quality max|fast] [--preview]`:
`eq=contrast=1.13:brightness=0.02:saturation=1.28` + `colorbalance=rm=.04:bm=-.05:rh=.03`
(cálidos) + `unsharp` + crop/scale a 1080x1920 + `loudnorm=I=-16:TP=-1.5:LRA=11`.
`--preview` → `02_graded_preview.mp4` (540×960, veryfast) con el AUDIO idéntico al final
(no cambiar jamás los parámetros de audio entre preview y final: el timing depende de él).

### 2. TIMING y transcripción — AUDIO-FIRST (la clave del pipeline)

El timing (cortes de silencio + palabras) se calcula UNA sola vez sobre el WAV y es la
**fuente de verdad**; los encodes de vídeo solo lo consumen. Así un cambio de calidad,
resolución o un re-render NUNCA mueve los cortes → nada de re-transcribir ni regenerar
subs/títulos/overlays/anclas (esto pasaba en cada re-encode y costaba ~1h de cascada).

```bash
# 2a. extraer WAV del grade FINAL (idéntico en preview y final)
ffmpeg -y -i out/02_graded.mp4 -vn -c:a pcm_s16le out/audio.wav
# 2b. timing de cortes (una vez): 
scripts/compress_silences.py --input out/audio.wav --timing-only \
  --save-timing out/silence_timing.json --noise -25
# 2c. transcripción sobre el WAV (misma base temporal):
scripts/transcribe.py --input out/audio.wav --outdir out --glossary glossary.json
# 2d. REMAPEAR palabras al dominio comprimido (OBLIGATORIO tras comprimir):
#   words.json está en dominio WAV (~198 s); subs/tarjetas/overlays/punch-ins se
#   aplican sobre el vídeo comprimido (~187 s). Sin el remap, todo va desplazado y
#   las anclas tardías quedan FUERA del vídeo (bug real detectado en la prueba bsl
#   2026-08-18: tarjeta final a 190.2 s en un vídeo de 187.3 s).
scripts/remap_words.py --words out/words.json --timing out/silence_timing.json
```

OJO aprendido: el ruido ambiente (calle, viento) sube el suelo a ~-22 dB y `-35dB` no
 detecta nada — empezar en `noise=-25dB:d=0.35` y ajustar mirando los silencios reportados;
 si el inicio sigue sin detectarse, `--trim-start <s>` manual (sabiendo dónde empieza el
 habla, p.ej. por la transcripción).

OJO aprendido (remap): el glosario/parches ASR se aplican SIEMPRE antes del remap (sus
ventanas temporales están en dominio original). Después del remap, `after:` en
`titles_config.json` se expresa en dominio COMPRIMIDO (ver prueba: tranquilidad a 180 s
comprimido, after=175). El remap es determinista (concat exacto de segments).

### 3. Cortar silencios del vídeo (aplica el timing guardado)

```bash
scripts/compress_silences.py --input out/02_graded.mp4 --output out/02c_compressed.mp4 \
  --load-timing out/silence_timing.json [--quality max|fast]
```

Validar SIEMPRE que audio y vídeo quedan ±0.1 s (A/V en par por construcción: trim+concat
de ambas pistas juntas).

### 4. El paso semántico (este lo haces TÚ, no un script)

Lee el transcript completo y decide, con contexto:

a) `effects.json` — qué palabras merecen sticker y cuál. Anclaje por texto de palabra:
```json
{"effects": [
  {"word": "euro", "emoji": "💸", "why": "dinero: sin pagar un EURO"},
  {"word": "sonido", "emoji": "🔊", "why": "efecto de sonido"}
]}
```
   Regla: el emoji debe añadir SIGNIFICADO (dinero, tiempo, sonido, growth, warning…),
   no adornar. Si no hay nada que merezca sticker, se omite sin miedo.
   Taxonomía de inspiración en `references/emoji-taxonomy.md`.
   OJO: make_effects ancla por PRIMERA aparición y por subcadena ('foto' cae en
   'fotógrafos', no en 'hazte una foto') — elige palabra única o verifica los tiempos
   que reporta antes de asumir el momento.
b) keywords de énfasis → fichero `keywords.json` (lista): conceptos portadores del mensaje.
   Son CONTENIDO del vídeo, no del script: ver `make_subs.py --keywords`.
c) Copy de las 2 tarjetas de título → `titles_config.json` (ver `make_titles.py`):
   anclarlas a la frase pivote y al cierre con ancla POR PALABRA + `after` (segundos
   mínimos), nunca por timestamp fijo: sobreviven a re-renders con cortes distintos.
   Tipografía combinada: Arial Black (base) + Georgia itálica (acento, `\fnGeorgia\i1`).
d) **Glosario ASR** (`glossary.json`, persistente por serie/contenido): cada vez que
   corrijas un error del ASR (nombres propios, inglés), AÑÁDELO al glosario para que la
   próxima pasada lo aplique sola. Real (serie churrería): Bizum (ASR: Beathoon/Beathome/
   Vizum según pasada), Troponcho, GPT, Séptimo. Formato:
```json
{"glossary": [
  {"asr": "Beathome", "fix": "Bizum", "window": [24.0, 27.0], "why": "app de pago española"},
  {"asr": "churro", "fix": "churros", "window": [167.9, 168.6], "prefix": true},
  {"asr": "de", "fix": "", "window": [19.6, 19.9], "prefix": true, "why": "borrar preposición"}
]}
```
   - Sin `prefix` y `fix` no vacío: match exacto case-insensitive, reemplazo in-place (comportamiento
     original).
   - `"prefix": true`: match por `startswith` case-insensitive ("churro" matchea "churros", "churro"
     pero NO "churrera"). Útil cuando el ASR añade/omite letras al final. El fix reemplaza SOLO el
     prefijo y conserva el sufijo: "Beathome," → "Bizum," (la coma/puntuación no se pierde).
   - `"fix": ""` (string vacío): BORRA la palabra de la lista (no la deja vacía). El log muestra
     `[del] 'palabra'@s`.
   - Corrige TODAS las apariciones dentro de la ventana (no solo la primera): el glosario es
     persistente por serie y el mismo error puede repetirse ("Beathome" x3 en un vídeo).
   `transcribe.py --glossary` lo aplica automáticamente al transcribir (reporta qué aplicó)
   y marca palabras de baja confianza (`low_confidence` en words.json) para tu revisión;
   `patch_words.py` hace lo mismo sobre un words.json ya generado. Cada pasada del ASR
   escribe los nombres propios DISTINTO (real: "Beathoon" y luego "Beathome" para el mismo
   Bizum) — por eso el glosario con ventanas temporales, no texto exacto global.

Técnicas de subtítulos/títulos en `references/ass-format.md` (karaoke `{\k}`, pop-in con
rebote `\t()`, colores &HAABBGGRR, keyword highlight). **No uses emojis dentro del ASS**:
libass renderiza tofu con Segoe UI Emoji. Los stickers van como PNG vía PIL (paso 5).

### 5. Generación → subs/títulos/plan de cortes/stickers

```
make_subs.py     --outdir out --keywords keywords.json   → subs.ass, cuts.json
make_titles.py   --words out/words.json --config titles_config.json  → titles.ass
make_effects.py  --words out/words.json --effects effects.json --outdir out
                 (python CON PIL) → emoji/*.png (Segoe UI Emoji, embedded_color=True),
                 overlays.json  [verifica píxeles coloridos: si sale vacío, la fuente
                 no es CBDT — buscar otra vía]
```

`cuts.json`: punch-ins ~2.8 s alineados a inicios de palabra, ciclo de escalas
[1.0, 1.14, 1.07, 1.21] (instantáneos; para zoom suave: zoompan con pre-upscale).
NOTA: `make_subs.py` genera también titles.ass con contenido por defecto — si usas
`make_titles.py`, sus títulos ganan (los tuyos).

### 6. Ensamblaje → 03, 04_final, 00_comparativa (+ delivery)

```
assemble.py --outdir out --flash off --overlays out/overlays.json \
  --skip-make-subs [--quality max|fast] [--preview] [--delivery] [--input-video <file>]
```

- `--skip-make-subs` SIEMPRE si generaste subs/títulos con tus keywords/config
  (OJO aprendido: `assemble.py` invoca `src/make_subs.py` relativo al CWD, no tu copia).
- **Iterar en `--preview`** (540×960 veryfast crf20, ~4-6× más rápido): renders
  `*_preview.mp4` con los MISMOS cortes que el final (el timing viene del WAV). El look
  (subs, stickers, zoom, tarjetas) se aprueba en preview; el render final sin `--preview`.
- `--delivery` genera `04_delivery.mp4` (crf18 + tune fastdecode, audio copy) desde el
  master: para subir a TikTok/WhatsApp (~2-4× más pequeño; la plataforma re-encodea a
  3-5 Mbps, el master de 378 MB no viaja). Entregar AMBOS al usuario con sus tamaños.
- `--input-video <file>`: override del vídeo fuente (p.ej. un remux con audio tonal `02t_tonal.mp4`).
  Si se indica, se usa directamente; si no, fallback a `02c_compressed.mp4` → `02_graded.mp4`.
- La comparativa es la tira RAW | COLOR | FINAL con etiquetas (`ariblk.ttf`); dura lo que
  el panel más largo (el RAW) y el panel FINAL queda CONGELADO en su último frame tras
  agotarse: conocido, no es bug. En preview se omite.

### 7. Validación → `validate.py` (numérica) + ojos

```
scripts/validate.py --outdir out [--preview]
```

Corre todo el checklist numérico (resoluciones, PSNR de subs, anti-flash, overlays,
duración/habla, decode) y sale 0/1. Copia el bloque al README y al mensaje de entrega.
Lo que los números no ven: extraer 2-3 frames y MIRARLOS (modelo de visión; si no hay
visión disponible, pedir al usuario / delegar). Para verificar TEXTO de tarjetas,
recorta la zona al 100% (en miniatura el modelo de visión puede leer ecos/duplicaciones
que no existen).

### 8. Entrega

README.md con: huella del fuente (ffprobe + sha256), comandos, parámetros, tabla de
correcciones ASR aplicadas, validación, decisiones. En el mensaje final: el mapeo
ENTRADA → SALIDA con duración/fps/huella (el usuario no debe tener que adivinar qué
vídeo produjo qué salida), tamaños de master vs delivery, y los pendientes humanos
(frames a mirar, comparativa a reproducir).

## Checklist de entrega (valida TODO antes de decir "listo")

1. `validate.py` → TODO OK (equivalente numérico de: resoluciones 03/04=1080x1920,
   00=1080x640; duraciones = 02c ±0.3 s; audio presente; PSNR subs finito < 40 dB;
   anti-flash YAVG <= +25; overlays dentro de rango con contenido; duración < raw;
   habla arranca < 0.6 s; decode punta a punta).
2. Visual: 2-3 frames MIRADOS (caption legible, keyword coloreada, sticker visible,
   sin artefactos) + recorte 100% de las tarjetas de título.
3. Reproducir la comparativa una vez de punta a punta.
4. README actualizado con huella del fuente y tabla de validación.

## Parámetros que el usuario puede pedir (y cómo se mapean)

| Petición | Flag/cambio |
|---|---|
| "sin emojis" / "más sobrio" | omitir paso effects (o `--overlays` vacío) |
| "con flash" (insista) | `--flash soft` (solo cambios de idea, alpha 0.45) |
| "no recortes nada" | saltar paso 3 (timing sobre el vídeo entero: mismo flujo audio-first) |
| "más/menos zoom" | ajustar ciclo de escalas o desactivar punch-ins (escala 1.0) |
| "otra tipografía" | Style del ASS (el repo de fuentes: C:/Windows/Fonts) |
| clip ya vertical | `--no-crop` (paso 1) |
| "máxima calidad" | ya es el default (`--quality max`); medir mejora con PSNR vs 02_graded en segmento ESCALA 1.0 y SIN subs (en un segmento con punch-in mides el desfase geométrico, no el códec) |
| "quiero verlo antes" / iterar | modo `--preview` (pasos 1-6 con `--preview`, validar con `validate.py --preview`) |
| "para subirlo" | `--delivery` → `04_delivery.mp4` (crf18 fastdecode, audio copy) |
| "han bajado los fps" / "se ve a tirones" | casi siempre es decode del reproductor (bitrate alto + preset slow = más refs), no el archivo: verificar fps midiendo nb_frames/duración (r_frame_rate y el "23.89" del panel de propiedades engañan). Si hace falta reproducción local fluida: usar la delivery (fastdecode) |

## Post-corrida: ritual de sync (IMPORTANTE)

Cada vídeo terminado deja aprendizajes. Antes de cerrar la sesión:

1. ¿Parcheaste o escribiste un script nuevo en la sala? → promuévelo a `scripts/` de la
   skill (generalizado: parámetros CLI, sin rutas de la sala) o fusiona la mejora en el
   script existente.
2. ¿Corregiste errores ASR? → añádelos al glosario de la serie (archivo junto al vídeo o
   en la sala de la serie).
3. ¿Aprendiste un OJO nuevo (gotcha de ffmpeg/libass/ASR)? → añádelo a SKILL.md.
4. ¿Cambiaste el flujo? → actualiza este documento.
5. `git add -A && git commit` en `~/.agents/skills` (repositorio de la skill).

Sin este ritual, el conocimiento se queda en las salas (`tmp/vertical-video-*/`) y la
próxima corrida vuelve a tropezar (pasó de verdad: patch_words.py, make_titles.py y
validate.py existían en salas y no en la skill).
