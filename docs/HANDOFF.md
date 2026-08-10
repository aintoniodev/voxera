# HANDOFF — voxera (fase 1 completa, lista para fase 2)

> **Para el agente que tome el testigo:** lee este documento COMPLETO, luego
> `docs/milestone-1.md`, `README.md`, y busca en memoria persistente
> (`memory_search "voxera"`, `memory_search "improve-my-sound"`). Todo lo
> operativo y las decisiones viven aquí y en los commits.

## 1. Identidad del proyecto

- **Producto:** `voxera` — post-producción de voz/podcast con red neuronal.
  Tagline: **"Sound like you, only better."**
- **Repo:** https://github.com/aintoniodev/voxera (🔒 privado, `master`, 16 commits pusheados).
  Usuario GitHub: **aintoniodev** (token de gh autentica como aintoniodev aunque `gh auth status` muestre un nombre stale).
- **Marca:** aintonio.dev | Antonio Gómez — AI Engineer, reto de 30 días con @troponcho.
  El primer vídeo (fase 1) muestra: audio crudo → red neuronal → audio mejorado → CTA "descárgalo" (→ voxera).
- **Premisa NO negociable:** todo debe ser **accesible/drivable desde terminal** para que el agente edite y toquetee absolutamente todo. El CLI es el héroe; la UI (Tauri) es una envoltura.

## 2. Estado actual (FUNCIONA)

- **CLI `voxera`** — 3 comandos:
  - `voxera enhance in.wav -o out.wav` → backend-only (back-compat, fase 1).
  - `voxera enhance in.wav -o out.wav --preset X` → **siempre** NN + pipeline completo de master
    (default `creator`); `--dsp-only` = master puro; `--dry-run` = plan sin escribir ni cargar NN.
  - `voxera master in.wav -o out.wav [--preset X]` → DSP sin NN (DC→HP LR24→[dehum]→EQ→de-esser→comp→limiter→loudnorm),
    byte-equivalente, salida 48 kHz PCM 24-bit. Flags: `--lufs`, `--no-eq/--no-comp/--no-limit/--no-loudnorm`, `--dehum`, `--dry-run`.
  - `voxera analyze in.wav [--format tty|json] [-o report.json]` → LUFS-I/S/LRA/RMS/TP, VAD,
    SNR, bandas espectrales, hum 50/100/150, RT60, DC, plosives, breaths, clicks, noise type (todo con confidence).
  - Comunes: `--device auto|cpu|cuda`, `--seed N`, `--verbose` (backend/model/device/torch + RTF model/pipeline/e2e/master).
  - Exit codes: 0 OK · 1 error · 2 uso/backend · **20 VOXERA_NO_SPEECH** (gate en master + enhance con pipeline; el enhance legacy sin preset NO lleva gate).
  - Default backend: `deepfilternet` (DeepFilterNet2, pf=off) — ganador del autoresearch (pesq 3.275, rtf 0.084 CPU).
  - Política formatos: input 16/22.05/44.1/48 kHz mono/stereo → interno 48k mono (0.5·(L+R), soxr) → WAV PCM_24.
- **Tests:** 150/150 pasan — `.venv-ims/Scripts/python.exe -m pytest tests/ -q` (~2 min).
- **Spec Gherkin:** `features/{enhance-cli,master-cli,analyze-cli}.feature` (28 escenarios, pipeline APS verde:
  `python -m acceptance.pipeline features`). OJO: los steps viven en `acceptance/steps.py` (dialecto
  "I run voxera …"); la feature vieja de fase 1 se reescribió a este dialecto.
- **Envs:**
  - `.venv-ims` (Python 3.11, uv): dpdfnet, deepfilternet, torch CPU, soundfile, soxr, scipy, pedalboard, pyloudnorm, webrtcvad-wheels, pytest → el env de producto.
  - `.venv` (Python 3.11): el de autoresearch (torch, df, dpdfnet, speechmos roto, hydra roto → NO usar para pytest).
  - Sistema Python 3.13: torch 2.11+cu128 (**CUDA**, RTX 2060 6GB).
  - Modelos en `models/DeepFilterNet2/` (gitignored). `.auto/models/` tiene DF2+DF3.
- **Git:** remoto `origin` → aintoniodev/voxera. Identidad de commits: pasada a aintoniodev en fase 2.

## 3. Decisiones de arquitectura

- Core Python + CLI (terminal-first). Backends pluggables vía registry (`src/voxera/backends/`).
- **Selección de modelo EMPÍRICA** (Pareto calidad/RTF sobre test set ES+EN), nunca asumida → ganador: DeepFilterNet2 pf=off.
- Desktop Tauri planeado: wrappea el CLI como sidecar. El binario Rust `deep-filter` (sin Python) es el candidato natural para el sidecar.
- GPU soportado (README lo documenta: CUDA torch / onnxruntime-gpu).

## 4. Infraestructura (cerrada ahora; relanzable)

- **SwarmForge four-pack** (specifier→coder→refactorer→architect), backend **orca**, agentes en **DeepSeek V4 Flash** (opencode-go, cuota separada de la sesión principal GLM-5.2 — no volver a usar GLM-5.2 para el swarm, tripea rate limits).
  - Relanzar: `./launch-swarm.sh` (idempotente; exporta env necesario). Parar: `bash swarmforge/scripts/close-swarm.sh`.
  - Parches en `swarmforge.bb` (commiteados): whitelist+case orca, inyección de ORCA_REPO_ID/ORCA_MAIN/PI_PROVIDER/PI_MODEL en el base de launch-command.
  - `~/.config/psmux/psmux.conf` con default-shell Git Bash (backslashes DOBLADOS). `~/.bash_profile` carga `~/.bashrc` (bb en PATH).
  - Handoffs: helpers en `swarmforge/scripts/`; daemon `handoffd.bb`; estado en `.swarmforge/`.
- **Autoresearch:** `.auto/` (gitignored) — measure.py (test set Piper ES+EN sintetizado, 12 clips, PESQ/STOI/SI-SNR/RTF vs clean), candidate.json, log.jsonl (22 configs). **VEREDICTO FINAL: DeepFilterNet2 pf=off.** resemble rinde peor en PESQ (full 1.74@rtf12.8, denoise_only 2.24@0.71) — AB subjetivo diferido. Los 2 agentes terminaron.
- **Fase 2 (Tracks 0/1A/1/1B)**: ✅ hechos — `docs/ROADMAP-fase2.md` y `docs/SPECS-fase2.md` actualizados (7/12 decisiones resueltas). Siguiente: Track 3 (`voxera score`) → Track 2 (`silence`) → Track 4 (vídeo) → Track 6 (benchmark v2) → Track 8 (humano) → Track 5 → Track 7 (Tauri).

## 5. Landmines operativos (NO volver a pisarlos)

1. **psmux no propaga env del lanzador a los shells de sesión** → inyectar env requerido directamente en el comando por-sesión (base de launch-command en swarmforge.bb). Commits `53512fd`, `8af5f04`.
2. **Los agentes DeepSeek del swarm describen pero a veces NO ejecutan pasos mecánicos** (commit/handoff vía swarm_handoff.sh) → el supervisor los completa. Patrón esperado, no bug sorpresa.
3. **Agente que termina con pregunta en vez de `<<<AGENT_DONE>>>`** cuelga el driver hasta 30 min → reiniciar driver con `touch .swarmforge/skip-initial` (en el worktree del rol) + C-c + relanzar comando del driver.
4. **Python 3.13 rompe deepfilternet/resemble** → usar venv 3.11 (uv). **UTMOS/DNSMOS rotos en este Windows** (fairseq/speechmos/dnsmos) → métricas reference-based (PESQ/STOI) sobre habla sintetizada cuando hay refs limpias; para voz real sin ref: evaluación subjetiva (el usuario escucha) o resolver UTMOS/DNSMOS en el futuro.
4b. **Windows cp1252 rompe stdout con '✓'** → `cli.main()` reconfigura stdout/stderr a UTF-8 al arrancar. **pyloudnorm 0.2.0**: no hay `short_term_loudness` — `blockwise_loudness` es un ATRIBUTO que rellena `loudness_range()` como efecto secundario. **pedalboard.Limiter** limita picos de MUESTRA, no true peak → el guard de `loudness_normalize` re-limita y aplica trim exacto hasta ≤ -1 dBTP. **webrtcvad marca ruido/música como voz** (hum → ratio 1.0): el gate del 5% solo fiable para *ausencia* de voz; para segmentación fina (breaths/clicks) usar envolvente, no VAD.
5. Handoffs: `commit:` debe ser **10 hex**; `note` message ≤ **80 chars**. Self-handoff al specifier funciona para cebar (deja el `.error` pero entrega).
6. **Cygwin vs Windows paths**: `/tmp` difiere entre bash (Cygwin) y python (Windows) — usar rutas relativas al proyecto para archivos compartidos.
7. Context-mode (ctx_*) está confinado al workspace; archivos fuera del proyecto (p.ej. `~/.pi/...`) → bash.

## 6. Pendientes / candidatos fase 2

- ~~**Rename a voxera**~~ ✅ DONE.
- ~~**Tracks 1A + 1 + 1B**~~ ✅ DONE (analyze/master/enhance --preset, formatos, determinismo, exit 20).
- **Track 3 — `voxera score`** (Voice Score/CVS 0-100 + resemblyzer con `--ref`): siguiente.
- **Track 2 — `voxera silence`** (`--level light|medium|aggressive`, `--breaths preserve|attenuate|remove`).
- **Track 4 — vídeo** (ffmpeg, `-c:v copy`, AAC 192 kbps, drift ≤10 ms).
- **Track 6 — benchmark `.auto` v2** (sintético vs real separados; pedir clips reales a Antonio, decisión #3).
- **Track 8 — evaluación humana** (A/B player HTML; decisión #12).
- **Tauri desktop shell** (Track 7, al final; sidecar del CLI, binario Rust `deep-filter`).
- **GPU**: flag `--gpu` explícito + pasada de RTF en CUDA (hoy `--device auto` ya usa CUDA si está).
- **Re-evaluación con voz real** del usuario (media/test1.wav → `voxera analyze` + `enhance --preset youtube`).
- ~~**Identidad git**~~ ✅ pasada a aintoniodev.
- Limpieza: `tmp/dfbin_test/en01_snr15.wav` (384KB) commiteado por error (borrar en algún commit); `.auto/` y `models/` ya gitignored.
- Ver vídeo fase 1: guion completado en la conversación (CTAs, tagline en cierre opcional).

## 7. Verificación rápida

```bash
cd <proyecto>
.venv-ims/Scripts/python.exe -m pytest tests/ -q          # 150 passed (~2 min)
.venv-ims/Scripts/python.exe -m acceptance.pipeline features  # 3 features verdes (28 escenarios)
.venv-ims/Scripts/voxera analyze media/test1.wav          # análisis TTY (si media/ existe)
.venv-ims/Scripts/voxera master media/test1.wav -o out.wav --preset youtube  # 48k/24-bit
git status -s                                             # limpio
./launch-swarm.sh                                         # si hace falta el swarm
```

## 8. Contacto humano

- Antonio (usuario): escribe en español, decisivo, quiere contexto de mercado antes de decidir, y que las cosas sean terminal-driven. Le gusta que le pregunten con opciones concretas.
- Si algo de esta doc está desactualizado, actualízalo y commitea.
