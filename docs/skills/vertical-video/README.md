# vertical-video — mirror en repo (skill del agente)

> Copia versionada de la skill procedimental del agente `project:improve-my-sound:vertical-video`.
> Canonical: `C:/Users/otero/.agents/skills/vertical-video/` (repo git `~/.agents/skills`, commits
> `a66a2c6` `f2e7064` `45d790d` sobre `cccbb02`).
> Este directorio versiona el conocimiento en el repo voxera para que viaje con el proyecto.

## Qué es

Producción de vídeo vertical (9:16) "producto final" estilo TikTok/Reels desde material crudo:
color + reframe, corte de silencios **audio-first** (timing calculado UNA vez sobre el WAV,
los re-encodes nunca mueven cortes), transcripción con **glosario ASR persistente por serie**,
subtítulos kinéticos palabra a palabra, stickers de emoji contextuales, punch-ins y tarjetas
de título ancladas por palabra.

## Contenido

| Ruta | Qué es |
|---|---|
| `SKILL.md` | El skill completo: flujo de 8 pasos, decisiones por defecto, checklist de entrega, ritual post-corrida (sync + git) |
| `scripts/` | Los 11 scripts del pipeline (autosuficientes, Windows): `grade_reframe`, `compress_silences`, `transcribe`, `patch_words`, `remap_words`, `make_subs`, `make_titles`, `make_effects`, `assemble`, `validate` + `test_make_subs` |
| `references/` | Formatos ASS (karaoke/pop-in) y taxonomía de emojis contextuales |

Diferencia con las demás skills de `docs/skills/`: estas son mirrors .md porque su código
núcleo vive en `src/voxera/`; **vertical-video tiene scripts propios** que no están en `src/`,
por eso el mirror incluye la carpeta completa.

## Notas

- Es el **único mirror con scripts completos ejecutables** en `docs/skills/`. Uso: copiar a
  `~/.agents/skills/vertical-video/` para usarlo desde el skill store, o ejecutar los scripts
  directamente sobre una sala `tmp/vertical-video-<etiqueta>/`.
- Entornos: `faster_whisper` en `.venv`; PIL/opencv en `.venv-video`; ffmpeg en `C:/ffmpeg/bin`.
- El glosario de la serie churrería vive fuera del repo: `tmp/vertical-video-churreria/glossary.json`
  (gitignored). Copiar el que corresponda junto al vídeo.
- Cambios de esta semana (2026-08-18): remap_words.py (dominio WAV→comprimido, bug de tarjeta
  fuera de vídeo), validate.py --preview + anti-flash por SSIM, glosario con prefix/delete,
  assemble --input-video.