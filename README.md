# voxera

Voice/podcast post-production CLI (`voxera`) powered by pluggable neural backends.
Brand: **aintonio.dev | Antonio Gómez** — an AI Engineer's 30-day content challenge product.

> Tagline: **"Sound like you, only better."** — phase 1 = denoiser; phase 2 = *"haz que mi voz
> grabada suene como una voz profesional de vídeo"* (denoiser → analyzer + voice mastering).

## Quickstart

```bash
# env (Python 3.11)
uv venv --python 3.11 .venv-ims && uv pip install -p .venv-ims -e .

# enhance (NN backend only — back-compat)
.venv-ims/Scripts/voxera enhance in.wav -o out.wav   # default backend (deepfilternet, Pareto winner)

# enhance + voice master pipeline (fase 2): NN SIEMPRE + DSP completo
.venv-ims/Scripts/voxera enhance in.wav -o out.wav --preset creator    # preset por defecto
.venv-ims/Scripts/voxera enhance in.wav -o out.wav --preset youtube --dry-run   # plan sin procesar

# voice mastering ONLY (sin red neuronal)
.venv-ims/Scripts/voxera master in.wav -o out.wav --preset youtube

# analyze (nunca modifica audio)
.venv-ims/Scripts/voxera analyze in.wav                       # resumen TTY
.venv-ims/Scripts/voxera analyze in.wav --format json -o report.json

# tune the backend (fase 1)
.venv-ims/Scripts/voxera enhance in.wav -o out.wav --backend dpdfnet --model dpdfnet2 --attn-limit-db 24
```

## Comandos (Track 1, spec fase 2)

| Comando | Qué hace |
|---|---|
| `voxera enhance IN -o OUT [--preset X]` | Restoration + voice mastering: backend NN + pipeline DSP completo. `--preset` **siempre** ejecuta el pipeline (default `creator`); sin flag = solo backend (back-compat). |
| `voxera enhance IN -o OUT --dsp-only` | Pipeline sin red neuronal (master puro). |
| `voxera enhance IN -o OUT --dry-run` | Plan `VOXERA PLAN` sin escribir OUT ni cargar la NN. |
| `voxera master IN -o OUT [--preset X]` | Voice mastering ONLY: DC → high-pass LR24 → [dehum] → EQ vocal → de-esser → comp → limiter -1 dBTP → loudnorm. |
| `voxera analyze IN [--format tty\|json] [-o report.json]` | Análisis completo con confidence: LUFS-I/S/LRA/RMS/TP, VAD, SNR, bandas espectrales, hum 50/100/150, RT60, DC, plosives, breaths, mouth clicks, noise type. |

**Presets congelados:** `creator` (-16 LUFS, natural+clear, default) · `youtube` (-14, warm+present) ·
`podcast` (-16, rich+consistent) · `social` (-14, loud+punchy) · `bad-room` (-16, high-pass 90 Hz).

**Exit codes:** `0` OK · `1` error de procesamiento · `2` error de uso/backend desconocido ·
`20` `VOXERA_NO_SPEECH` (VAD speech ratio < 5%; `analyze` sigue funcionando).

**Política de formatos (congelada, Track 1A):** input WAV 16/22.05/44.1/48 kHz mono/stereo →
interno **48 kHz mono** (downmix energía `0.5·(L+R)`, resample soxr) → salida **WAV PCM 24-bit**.
Determinismo: DSP byte-equivalente; JSON de reports estable para CI (claves ordenadas, floats fijos,
única excepción `processing_time_s`). Device: `--device auto|cpu|cuda`; `--seed N` para la NN.

## Backends (pluggable, metric-driven)

| Backend | Runtime | GPU | Status | Pareto (pesq / rtf) |
|---|---|---|---|---|
| `deepfilternet` | Python (`df`+torch) / Rust bin | ✅ CUDA torch auto | ✅ **DEFAULT (ganador)** | **DeepFilterNet2 pf=off: 3.28 / 0.08** |
| `dpdfnet` | ONNX (real-time CPU) | ✅ vía `onnxruntime-gpu` (CUDA) | ✅ disponible | dpdfnet2@attn24: 2.88 / 0.38 |
| `resemble` | offline diffusion | ✅ CUDA recomendado (lento en CPU) | ⚠️ evaluado, rinde peor en PESQ | full: 1.74 @ rtf 12.8 · denoise_only: 2.24 @ 0.71 |

**GPU está soportado.** Esta máquina tiene una NVIDIA RTX 2060 6GB (torch CUDA 2.11). Los backends
usan CUDA donde esté disponible; el CLI usa `--device auto` (CUDA si hay, si no CPU).

Model/param selection is **empirical** (Pareto quality-vs-RTF on an ES+EN benchmark set), never
assumed — see `.auto/` (autoresearch).

## Architecture

```
src/voxera/   enhance() contract, backend registry, audioio (policy), dsp/ (pipeline+presets),
              analyze.py, master.py, vad.py, device.py, determinism.py, CLI
features/     Gherkin: enhance-cli (10 escenarios), master-cli (5), analyze-cli (3)
acceptance/   APS Gherkin acceptance pipeline (parse→dry-check→generate→run)
tests/        150 pytest unit tests (Track 1A + Track 1 + fase 1)
swarmforge/   SwarmForge four-pack (specifier→coder→refactorer→architect)
.auto/        autoresearch harness (gitignored): measure.py, candidate.json, log.jsonl
```

- **Core is the source of truth** — everything is drivable from the terminal (premise: the agent can edit/run/tweak everything).
- Desktop (Tauri) shell planned (Track 7), wrapping the CLI as a sidecar — the Rust `deep-filter` binary is the natural fit.

## Status

- **Fase 1** (`voxera enhance` happy-path CLI): ✅ complete — 70 tests, exit codes per spec.
- **Model selection**: ✅ autoresearch verdict — **DeepFilterNet2 (pf=off) is the default**.
- **Fase 2 — Track 0 (rename)**: ✅ `improve_my_sound`/`ims` → `voxera`.
- **Fase 2 — Track 1A (fundaciones)**: ✅ format policy, downmix/resample soxr, determinismo
  (JSON estable + DSP byte-equivalente), device policy, RTF model/pipeline/e2e/master, provenance,
  exit 20 `VOXERA_NO_SPEECH`.
- **Fase 2 — Track 1 (analyze + master, con 1B)**: ✅ `voxera analyze` (métricas + confidence),
  `voxera master` (pipeline congelado + presets), `enhance --preset/--dsp-only/--dry-run`,
  de-esser con criterio de no-daño, breaths/plosives/clicks/hum/DC/noise-type heurísticos.
- **Next**: Track 3 (`voxera score`) → Track 2 (`silence`) → Track 4 (vídeo) → Track 6 (benchmark v2)
  → Track 8 (humano) → Track 5 (restoration) → Track 7 (Tauri). Detalle: `docs/ROADMAP-fase2.md`.

## Operations

- Swarm: `./launch-swarm.sh` (four-pack on orca backend, agents on DeepSeek V4 Flash).
- Stop: `bash swarmforge/scripts/close-swarm.sh`.
- Autoresearch results: `.auto/log.jsonl` (Pareto cloud).
- Acceptance: `bash acceptance/scripts/accept features` (o `python -m acceptance.pipeline features`).
