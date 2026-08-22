# voxera — voz profesional de vídeo

**Tagline:** *Sound like you, only better.*

CLI de post-producción de voz y vídeo para creadores: convierte una grabación
cruda (wav/mp4) en audio con sonido profesional, medible y reproducible desde
terminal. El CLI es el héroe; todo es accesible/drivable desde terminal para
que un agente (o tú) pueda editar y verificar absolutamente todo.

```
INPUT ──► ANALYZE ──► ENHANCE ──► VOICE DSP ──► MASTER ──► OUTPUT
(wav/mp4)  VAD          NN          DC removal    comp      WAV 48 kHz/24-bit
           LUFS         backends    high-pass     de-esser  MP4: vídeo copy
           clipping     pluggables  dehum         limiter   + AAC 192 kbps
           SNR/RT60                 EQ vocal      loudnorm
                                   presence/air   (-14 LUFS)
```

## CLI

```bash
voxera enhance in.wav -o out.wav [--preset creator]   # NN + pipeline completo
voxera master  in.wav -o out.wav [--lufs -14]         # DSP puro, byte-equivalente
voxera analyze in.wav [--format json]                 # LUFS/VAD/SNR/RT60/hum… con confidence
voxera score   a.wav b.wav                            # métricas objetivas A vs B
voxera silence in.wav                                 # mapa de silencios (VAD)
voxera restore in.wav                                 # reparación (declip/dehum)
voxera inspect in.wav                                 # probe interno de etapas
```

Subcomandos de efectos (fase 3):

```bash
voxera audio lowpass|tonal …        # pase bajo; musicalidad tonal (transition/riser/melody)
voxera video info|enhance|compare   # probe, upscaling 9:16 (animevideov3), A/B
voxera video zoom|teleport|levitate|magnify|slowmo|stabilize|cutsilence|captions
```

Comunes: `--device auto|cpu|cuda`, `--seed N`, `--verbose` (RTF por etapa),
`--dry-run`, `--backend/--model` (registry pluggable; default **DeepFilterNet2**,
ganador de la selección empírica PESQ/RTF). Exit codes: 0 OK · 1 error · 2 uso ·
20 `VOXERA_NO_SPEECH`.

## Estado del producto

- **Fase 1 (denoiser): completa.** Backends pluggables, benchmark propio
  (PESQ/STOI/SI-SNR/RTF, test set ES+EN sintetizado).
- **Fase 2 ("voz profesional de vídeo"): completa.** Tracks 0-8: presets,
  DSP de master completo, análisis con confidence, gate de no-speech,
  determinismo (`--seed`), provenance, benchmark real (15 clips de `media/`) y
  **evaluación humana** (Track 8, `docs/track8-results.md`). Suite:
  411 tests + 25 escenarios Gherkin (APS). Desktop Tauri:
  `voxera-desktop/`.
- **Fase 3 (vídeo vertical 9:16): especificada e implementada** — ver
  `docs/SPECS-fase3-video.md` (upscaling con AB humano, efectos de énfasis,
  captions). UI experimental: `ui/video.html`.

Documentación de producto: `docs/HANDOFF.md` (estado operativo y decisiones),
`docs/SPECS-fase2.md`, `docs/ROADMAP-fase2.md`, `docs/milestone-1.md`.

## Layout

```
src/voxera/        producto (cli.py + módulos por comando; backends/ pluggable)
tests/             suite pytest (audio/CLI) · features/ + acceptance/  (Gherkin APS)
plugins/           bundles portables de skills short-form (métricas, editing science)
skills/stock-assets/  plugin de agente: stock media (Pixabay/Freesound/Jamendo) —
                     tiene su propio README; se instala con install.sh / install.ps1
extension/         extensión pi del plugin stock-assets (MCP server)
ui/                UIs experimentales (video.html)
voxera-desktop/    app Tauri (wrappea el CLI)
voxera-demo/       demo de la fase 1
swarmforge/        infra de agentes (four-pack) usada para desarrollar
research-notes/    corpus de investigación (R1–R4, synthesis-matrix) que alimenta
                   las síntesis científicas de edición/captions
docs/              specs por fase + HANDOFF
```

## Entornos

- `.venv` — env de producto (Python 3.11, uv): backends NN, DSP, pytest.
- `.venv-video` — env de vídeo (torch CUDA, opencv, faster-whisper).
- Freezes de referencia: `docs/envs/` (`venv.txt`, `venv-video.txt`,
  `recreate.sh`).

```bash
uv venv && uv pip install -e ".[dev]"   # producto
python -m pytest tests/                 # suite audio/CLI
python -m acceptance.pipeline features  # escenarios Gherkin
```

## Nota histórica

El conocimiento procedimental del agente (skills de dominio: vertical-video,
video-from-lessons, retake-audit, copywriting…) ya no se versiona en este repo:
vive versionado en el canon de skills de brand-os, servido a los agentes vía
junctions en `~/.agents/skills`. Este repo cuenta una sola historia: el
**producto voxera**.
