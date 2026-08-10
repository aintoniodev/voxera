# improve-my-sound

Voice/podcast post-production CLI (`voxera`) powered by pluggable neural backends.
Brand: **aintonio.dev | Antonio Gómez** — an AI Engineer's 30-day content challenge product.

> Hero: pass your rough/noisy voice audio in → get professionally-enhanced audio out.

## Quickstart

```bash
# env (Python 3.11)
uv venv --python 3.11 .venv-ims && uv pip install -p .venv-ims -e .

# enhance a file
.venv-ims/Scripts/voxera enhance in.wav -o out.wav   # default backend (deepfilternet, Pareto winner)
# tune the backend
.venv-ims/Scripts/voxera enhance in.wav -o out.wav --backend dpdfnet --model dpdfnet2 --attn-limit-db 24
.venv-ims/Scripts/voxera enhance in.wav -o out.wav --backend deepfilternet --model DeepFilterNet3 --pf

# GPU (opcional): instala los runtimes CUDA — pip install onnxruntime-gpu, o un build de torch con CUDA
```

## Backends (pluggable, metric-driven)

| Backend | Runtime | GPU | Status | Pareto (pesq / rtf) |
|---|---|---|---|---|
| `deepfilternet` | Python (`df`+torch) / Rust bin | ✅ CUDA torch auto | ✅ **DEFAULT (ganador)** | **DeepFilterNet2 pf=off: 3.28 / 0.08** |
| `dpdfnet` | ONNX (real-time CPU) | ✅ vía `onnxruntime-gpu` (CUDA) | ✅ disponible | dpdfnet2@attn24: 2.88 / 0.38 |
| `resemble` | offline diffusion | ✅ CUDA recomendado (lento en CPU) | ⚠️ evaluado, rinde peor en PESQ | full: 1.74 @ rtf 12.8 · denoise_only: 2.24 @ 0.71 |

**GPU está soportado.** Esta máquina tiene una NVIDIA RTX 2060 6GB (torch CUDA 2.11). Los backends usan CUDA donde esté disponible: `pip install onnxruntime-gpu` para dpdfnet, torch con CUDA para deepfilternet/resemble. El CLI usa CPU por defecto (real-time); la aceleración GPU es una opción a nivel de entorno (un flag `--gpu` es un follow-up).

Model/param selection is **empirical** (Pareto quality-vs-RTF on an ES+EN benchmark set), never assumed — see `.auto/` (autoresearch).

## Architecture

```
src/voxera/   enhance() contract, backend registry, CLI
acceptance/             APS Gherkin acceptance pipeline (parse→dry-check→generate→run)
tests/                  70 pytest unit tests
swarmforge/             SwarmForge four-pack (specifier→coder→refactorer→architect)
.auto/                  autoresearch harness (gitignored): measure.py, candidate.json, log.jsonl
```

- **Core is the source of truth** — everything is drivable from the terminal (premise: the agent can edit/run/tweak everything).
- Desktop (Tauri) shell planned, wrapping the CLI as a sidecar — the Rust `deep-filter` binary is the natural fit.

## Status

- **Feature 1** (`voxera enhance` happy-path CLI): ✅ complete — all 8 spec scenarios verified (exit codes per spec), 70 tests pass.
- **Model selection**: ✅ autoresearch verdict — **DeepFilterNet2 (pf=off) is the default** (pesq 3.28, rtf 0.08; 22 configs swept).
- **Next**: Tauri desktop shell; real-voice re-evaluation (UTMOS/DNSMOS no-reference); GPU RTF pass (CUDA torch).

## Operations

- Swarm: `./launch-swarm.sh` (four-pack on orca backend, agents on DeepSeek V4 Flash).
- Stop: `bash swarmforge/scripts/close-swarm.sh`.
- Autoresearch results: `.auto/log.jsonl` (Pareto cloud).
