# HANDOFF — voxera (fase 1 completa, lista para fase 2)

> **Para el agente que tome el testigo:** lee este documento COMPLETO, luego
> `docs/milestone-1.md`, `README.md`, y busca en memoria persistente
> (`memory_search "voxera"`, `memory_search "improve-my-sound"`). Todo lo
> operativo y las decisiones viven aquí y en los commits.

## 1. Identidad del proyecto

- **Producto:** `voxera` — post-producción de voz/podcast con red neuronal.
  Tagline: **"Sound like you, only better."**
- **Repo:** https://github.com/aintoniodev/voxera (🌍 público, `master`).
  Usuario GitHub: **aintoniodev** (identidad de commits: `aintonio.dev <58003439+aintoniodev@users.noreply.github.com>`).
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
- **Tests:** suite audio/CLI en `.venv-ims` verde — `python -m pytest tests/` → **411 passed, 3 skipped**; los 12 de `test_video_stabilize` requieren cv2 y corren en `.venv-video` (44/44).
- **Spec Gherkin:** `features/{enhance,master,analyze,score,silence,restore}-cli.feature` (25 escenarios, pipeline APS verde:
  `python -m acceptance.pipeline features`). Steps en `acceptance/steps.py` (dialecto "I run voxera …").
- **Envs:**
  - `.venv-ims` (Python 3.11, uv): dpdfnet, deepfilternet, torch CPU, soundfile, soxr, scipy, pedalboard, pyloudnorm, webrtcvad-wheels, resemblyzer, pesq, pystoi, pytest → el env de producto.
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
- **Fase 2 COMPLETA**: tracks 0-8 implementados (411 tests + 25 escenarios APS; stabilize E2E en `.venv-video`).
  - **Benchmark real ejecutado** con los 15 clips de `media/` → `.auto/v2/reports/real.md` (decisión #3 ✅).
  - **Tests AB preparados**: 60 pares (A/B/C/D, -16 LUFS) en `.auto/human/conditions/` + `pairs.json`.
  - **Tauri hecho**: `voxera-desktop/src-tauri/target/release/voxera-desktop.exe` + instaladores
  (MSI + NSIS setup) en `target/release/bundle/`; icono propio generado.
- **Vídeo demo (40.5s, 1080p)**: `voxera-demo/` (Remotion, voz Piper ES, UI de voxera
  reconstruida; render: `npx remotion render voxera-demo out/video.mp4`).
  - `ui/server.py` en 127.0.0.1:8770: /enhance /score /vote /media /pairs; ab-player con botones A/B.

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

- ~~**Tracks 0/1A/1/1B/2/3/4/5/6/8/7-UI**~~ ✅ implementados (411 tests + 25 escenarios APS).
- **CLIPS REALES de Antonio (decisión #3)**: 10-30 grabaciones (mic, phone, webcam, fan, AC, room, street)
  → `.auto/v2/real/*.wav` → `python .auto/v2/benchmark.py --suite real` → reporte real.md.
- **Escucha Track 8** (decisión #12): 5-10 oyentes con `ui/ab-player.html` vía `ui/server.py` → `.auto/human/votes.csv`.
- **Tauri shell**: instalar rustup + `cargo tauri init` reutilizando `ui/` (el CLI genera todo; Tauri solo envuelve).
- **VoiceFixer/ClearerVoice**: candidatos ML de restoration para el benchmark (instalación pesada, diferida).
- **GPU**: pasada de RTF en CUDA (hoy `--device auto` ya usa CUDA si está; falta medir).
- **Re-evaluación con voz real**: `voxera analyze media/demo-chorros-antes.wav` + `enhance --preset youtube` + `score --ref`.
- Limpieza: `tmp/dfbin_test` ya borrado del repo; `.auto/` y `models/` gitignored.
- Ver vídeo fase 1: guion completado en la conversación (CTAs, tagline en cierre opcional).

## 7. Verificación rápida

```bash
cd <proyecto>
.venv-ims/Scripts/python.exe -m pytest tests/ -q          # 411 passed, 3 skipped (12 stabilize requieren cv2 → .venv-video)
.venv-video/Scripts/python.exe -m pytest tests/test_video_stabilize.py -q   # 44 passed
.venv-ims/Scripts/python.exe -m acceptance.pipeline features  # 6 features verdes (25 escenarios)
.venv-ims/Scripts/voxera analyze media/demo-chorros-antes.wav          # análisis TTY
.venv-ims/Scripts/voxera enhance media/demo-chorros-antes.wav -o out.wav --preset youtube  # NN + master
.venv-ims/Scripts/voxera score out.wav --ref media/demo-chorros-antes.wav  # CVS + voz preservada
.venv-ims/Scripts/voxera silence media/demo-chorros-antes.wav -o clean.wav --level medium
.venv-ims/Scripts/python.exe ui/server.py 8770            # UI thin: 127.0.0.1:8770
git status -s                                             # limpio
./launch-swarm.sh                                         # si hace falta el swarm
```

## 8. Contacto humano

- Antonio (usuario): escribe en español, decisivo, quiere contexto de mercado antes de decidir, y que las cosas sean terminal-driven. Le gusta que le pregunten con opciones concretas.
- Si algo de esta doc está desactualizado, actualízalo y commitea.
