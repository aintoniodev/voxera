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

- **CLI `voxera`**: `voxera enhance in.wav -o out.wav` → exit 0, wav mejorado.
  - Default: `deepfilternet` (DeepFilterNet2, pf=off) — **ganador del autoresearch** (pesq 3.275, rtf 0.084 CPU).
  - Alternativa: `--backend dpdfnet --model dpdfnet2 --attn-limit-db 24` (pesq 2.88, rtf 0.38).
  - Flags: `--backend`, `--model`, `--attn-limit-db`, `--pf`. Exit codes por spec: happy=0, unknown backend=2, bad path/formato/empty=1, falta -o/input=2.
  - Mono out (promedia canales estéreo). GPU: CUDA torch auto-detectado; `--gpu` flag = follow-up.
- **Tests:** 70/70 pasan — `.venv-ims/Scripts/python.exe -m pytest tests/ -q` (~75s).
- **Spec Gherkin:** `features/enhance-cli.feature` (8 escenarios, verificados). Pipeline APS en `acceptance/`.
- **Envs:**
  - `.venv-ims` (Python 3.11, uv): dpdfnet, deepfilternet, torch CPU, soundfile, pytest → el env de producto.
  - `.venv` (Python 3.11): el de autoresearch (torch, df, dpdfnet, speechmos roto, hydra roto → NO usar para pytest).
  - Sistema Python 3.13: torch 2.11+cu128 (**CUDA**, RTX 2060 6GB).
  - Modelos en `models/DeepFilterNet2/` (gitignored). `.auto/models/` tiene DF2+DF3.
- **Git:** limpio, remoto `origin` → aintoniodev/voxera. Commits firmados como `burgerbytes` (pendiente: cambiar identidad a aintoniodev).

## 3. Decisiones de arquitectura

- Core Python + CLI (terminal-first). Backends pluggables vía registry (`src/improve_my_sound/backends/`).
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

## 5. Landmines operativos (NO volver a pisarlos)

1. **psmux no propaga env del lanzador a los shells de sesión** → inyectar env requerido directamente en el comando por-sesión (base de launch-command en swarmforge.bb). Commits `53512fd`, `8af5f04`.
2. **Los agentes DeepSeek del swarm describen pero a veces NO ejecutan pasos mecánicos** (commit/handoff vía swarm_handoff.sh) → el supervisor los completa. Patrón esperado, no bug sorpresa.
3. **Agente que termina con pregunta en vez de `<<<AGENT_DONE>>>`** cuelga el driver hasta 30 min → reiniciar driver con `touch .swarmforge/skip-initial` (en el worktree del rol) + C-c + relanzar comando del driver.
4. **Python 3.13 rompe deepfilternet/resemble** → usar venv 3.11 (uv). **UTMOS/DNSMOS rotos en este Windows** (fairseq/speechmos/dnsmos) → métricas reference-based (PESQ/STOI) sobre habla sintetizada cuando hay refs limpias; para voz real sin ref: evaluación subjetiva (el usuario escucha) o resolver UTMOS/DNSMOS en el futuro.
5. Handoffs: `commit:` debe ser **10 hex**; `note` message ≤ **80 chars**. Self-handoff al specifier funciona para cebar (deja el `.error` pero entrega).
6. **Cygwin vs Windows paths**: `/tmp` difiere entre bash (Cygwin) y python (Windows) — usar rutas relativas al proyecto para archivos compartidos.
7. Context-mode (ctx_*) está confinado al workspace; archivos fuera del proyecto (p.ej. `~/.pi/...`) → bash.

## 6. Pendientes / candidatos fase 2

- **Rename a voxera**: paquete `improve_my_sound`→`voxera`, CLI `ims`→`voxera`(?), README con tagline, pyproject. (Decidir alcance con el usuario.)
- **Tauri desktop shell** (sidecar del CLI; candidato: binario Rust `deep-filter`).
- **GPU**: torch CUDA en `.venv-ims`, flag `--gpu`, pasada de RTF en GPU.
- **Re-evaluación con voz real** del usuario (media/test1.wav ya probado subjetivamente → "ha funcionado").
- **Identidad git** → aintoniodev para commits futuros.
- Limpieza: `tmp/dfbin_test/en01_snr15.wav` (384KB) commiteado por error; `.auto/` y `models/` ya gitignored.
- Ver vídeo fase 1: guion completado en la conversación (CTAs, tagline en cierre opcional).

## 7. Verificación rápida

```bash
cd <proyecto>
.venv-ims/Scripts/python.exe -m pytest tests/ -q          # 70 passed
.venv-ims/Scripts/voxera enhance media/test1.wav -o out.wav  # exit 0 (si media/ existe)
git status -s                                             # limpio
./launch-swarm.sh                                         # si hace falta el swarm
```

## 8. Contacto humano

- Antonio (usuario): escribe en español, decisivo, quiere contexto de mercado antes de decidir, y que las cosas sean terminal-driven. Le gusta que le pregunten con opciones concretas.
- Si algo de esta doc está desactualizado, actualízalo y commitea.
