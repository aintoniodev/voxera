# Milestone 1 — Feature 1 (`voxera enhance`) complete + model-selection Pareto in progress

**Date:** 2026-08-10 · **Repo:** improve-my-sound · **Brand:** aintonio.dev | Antonio Gómez

## What was delivered

1. **SwarmForge four-pack fully operational** on native Windows (Windows Terminal + psmux, orca backend):
   - Fixed psmux env-propagation bug (ORCA_REPO_ID/ORCA_MAIN injected into session shells — commit `53512fd`).
   - Agents rerouted from GLM-5.2 (rate-limited, shared with the main session) to **DeepSeek V4 Flash** via opencode-go (`8af5f04`) — zero rate-limit errors since.
   - Specifier → coder → refactorer → architect cycle ran end-to-end on DeepSeek.

2. **Feature 1 — `voxera enhance` happy-path CLI (approved spec, 8 Gherkin scenarios):**
   - specifier: `features/enhance-cli.feature` (8 scenarios; pruning + ir-dry-checker).
   - coder: `ea36d1b` — core contract (`enhance()`), pluggable backend registry, dpdfnet adapter boundary, validation, acceptance pipeline, 70 unit tests.
   - refactorer: `d18c1e208a` — acceptance pipeline hardening (behavior-preserving).
   - architect: reviewed (no commit).
   - **Supervisor completion (`b3a4e71`)**: the coder left the dpdfnet engine wiring as a stub ("not implemented yet") and mapped unknown backend to exit 1 (spec: 2). Completed: real dpdfnet call (defaults dpdfnet2@attn24), `UnknownBackendError` → exit 2, `--model`/`--attn-limit-db` overrides, pyproject dep, tests updated from stub-encoded to real behavior.
   - **Verified:** all 8 spec scenarios pass exactly (exit codes), 70/70 tests green.

## Pareto model selection (autoresearch — FINAL verdict)

Harness: `.auto/` (measure.py: 12 ES+EN noisy clips → PESQ/STOI/SI-SNR + warm RTF vs known clean; candidate.json; log.jsonl). **22 configs swept** by two autonomous agents; verdict 2026-08-10.

| Config | pesq | rtf | verdict |
|---|---|---|---|
| **DeepFilterNet2 (pf=off)** | **3.275** | **0.084** | **🏆 WINNER → wired as voxera default** |
| DeepFilterNet3 (pf=off) | 3.268 | 0.225 | strong |
| dpdfnet2@attn24 | 2.882 | 0.383 | previous default |
| dpdfnet8@attn24 | 2.911 | 1.044 | max pesq in dpdfnet |
| resemble full (diffusion) | 1.74 | 12.8 | ⚠️ worst on PESQ here |
| resemble denoise_only | 2.24 | 0.71 | weak vs DF |

**Insights:** `attn_limit_db` is the dominant quality lever in dpdfnet (6→24 nearly doubles PESQ). DeepFilterNet2 beats everything on BOTH quality and speed (~12× faster than dpdfnet8). pf=on never wins. Resemble (diffusion, deepspeed unbuildable on Windows but unneeded for inference) underperforms on reference PESQ — a subjective AB test is deferred (it may still sound good; PESQ favors denoising fidelity).

## Operational learnings

- **psmux (native Windows tmux) does not reliably propagate the launcher's env to session shells** — inline required env (ORCA anchors, PI_PROVIDER/MODEL) into the per-session command (swarmforge.bb launch-command base). (commits `53512fd`, `8af5f04`)
- **DeepSeek agents sometimes describe-but-don't-execute mechanical steps** (commit/handoff via swarm_handoff.sh). Supervisor completed: specifier's approval→handoff, refactorer's commit+handoff, architect's completion, coder's backend wiring + exit codes.
- Agents that end with a question instead of `<<<AGENT_DONE>>>` hang the driver up to its 30-min timeout — restart with `.swarmforge/skip-initial` to force queue polling.
- **Python 3.13 + ML packages = pain** (deepfilternet/resemble don't build); use a 3.11 venv (uv). UTMOS/DNSMOS packages are broken on this Windows env (fairseq/speechmos/dnsmos issues) — reference-based PESQ/STOI/SI-SNR on synthesized Piper test speech is the reliable choice when clean refs exist.

## Next

- ~~Wire the autoresearch winner as default~~ ✅ DONE: DeepFilterNet2 (pf=off) wired in `voxera` (commit below), models in `models/` (gitignored).
- **GPU is available** (RTX 2060 6GB, CUDA torch 2.11 on system Python): a CUDA pass is an open Pareto dimension (RTF + heavier models). dpdfnet can use `onnxruntime-gpu`; deepfilternet/resemble can use CUDA torch.
- Evaluate resemble (offline max-quality variant).
- Tauri desktop shell wrapping the CLI.
- Real-voice re-evaluation (no-reference UTMOS/DNSMOS) once the brand owner's audio is available.
