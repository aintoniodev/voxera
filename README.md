# improve-my-sound

Voice/podcast post-production CLI (`ims`) powered by pluggable neural backends.
Brand: **aintonio.dev | Antonio Gómez** — an AI Engineer's 30-day content challenge product.

> Hero: pass your rough/noisy voice audio in → get professionally-enhanced audio out.

## Quickstart

```bash
# env (Python 3.11)
uv venv --python 3.11 .venv-ims && uv pip install -p .venv-ims -e .

# enhance a file
.venv-ims/Scripts/ims enhance in.wav -o out.wav
# tune the backend
.venv-ims/Scripts/ims enhance in.wav -o out.wav --backend dpdfnet --model dpdfnet2 --attn-limit-db 24
```

## Backends (pluggable, metric-driven)

| Backend | Runtime | Status | Pareto (pesq / rtf) |
|---|---|---|---|
| `dpdfnet` | ONNX, real-time CPU | ✅ default | dpdfnet2@attn24: **2.88 / 0.38** |
| `deepfilternet` | Rust binary / Python | 🔄 autoresearch | **DeepFilterNet2 pf=off: 3.28 / 0.08** (leader) |
| `resemble` | offline diffusion (GPU) | ⏳ pending eval | — |

Model/param selection is **empirical** (Pareto quality-vs-RTF on an ES+EN benchmark set), never assumed — see `.auto/` (autoresearch).

## Architecture

```
src/improve_my_sound/   enhance() contract, backend registry, CLI
acceptance/             APS Gherkin acceptance pipeline (parse→dry-check→generate→run)
tests/                  70 pytest unit tests
swarmforge/             SwarmForge four-pack (specifier→coder→refactorer→architect)
.auto/                  autoresearch harness (gitignored): measure.py, candidate.json, log.jsonl
```

- **Core is the source of truth** — everything is drivable from the terminal (premise: the agent can edit/run/tweak everything).
- Desktop (Tauri) shell planned, wrapping the CLI as a sidecar — the Rust `deep-filter` binary is the natural fit.

## Status

- **Feature 1** (`ims enhance` happy-path CLI): ✅ complete — all 8 spec scenarios verified (exit codes per spec), 70 tests pass.
- **Model selection**: 🔄 autoresearch running (see `.auto/log.jsonl`); winner gets wired as the new default.
- **Next**: Tauri desktop shell; more backends (resemble); real-voice re-evaluation (UTMOS/DNSMOS no-reference).

## Operations

- Swarm: `./launch-swarm.sh` (four-pack on orca backend, agents on DeepSeek V4 Flash).
- Stop: `bash swarmforge/scripts/close-swarm.sh`.
- Autoresearch results: `.auto/log.jsonl` (Pareto cloud).
