#!/usr/bin/env bash
# SwarmForge launch wrapper — improve-my-sound
# Stack: four-pack roles, orca backend, native Windows (Windows Terminal + psmux).
#
# This wrapper guarantees the runtime env the orca driver needs:
#   - bb (babashka) on PATH  (installed to ~/swarmforge-bin by setup-windows.sh)
#   - ORCA_REPO_ID / ORCA_MAIN  (required by orca-agent-driver.sh)
#   - SWARMFORGE_TERMINAL=windows-native
#
# Re-run any time: ./launch-swarm.sh
set -euo pipefail

SCRIPT_HOME="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_HOME"

# 1. babashka on PATH (login psmux shells get it via ~/.bash_profile -> ~/.bashrc,
#    but set it here too so a plain `bash launch-swarm.sh` always works).
export PATH="$HOME/swarmforge-bin:$PATH"

# 2. orca anchors. ORCA_MAIN = main worktree, forward slashes (mixed mode).
export ORCA_MAIN="$(cygpath -m "$SCRIPT_HOME" 2>/dev/null || echo "$SCRIPT_HOME")"
# ORCA_REPO_ID is the orca-assigned id for this repo (stable). If the repo is
# re-registered, refresh it with:  orca repo list --json   (id field).
export ORCA_REPO_ID="${ORCA_REPO_ID:-fb88f0de-ce39-4263-8407-b99e3a25f064}"

# 3. native Windows terminal backend (no WSL).
export SWARMFORGE_TERMINAL=windows-native

command -v bb   >/dev/null || { echo "ERROR: bb (babashka) not found on PATH." >&2; exit 1; }
command -v tmux >/dev/null || { echo "ERROR: tmux (psmux) not found on PATH." >&2; exit 1; }
command -v orca >/dev/null || { echo "ERROR: orca CLI not found on PATH." >&2; exit 1; }

echo "==> SwarmForge launch"
echo "    ORCA_MAIN     = $ORCA_MAIN"
echo "    ORCA_REPO_ID  = $ORCA_REPO_ID"
echo "    TERMINAL      = $SWARMFORGE_TERMINAL"
echo "    backend agent = \${SWARMFORGE_ORCA_AGENT:-pi -p}  (override if desired)"
echo

exec bash "$SCRIPT_HOME/swarmforge/scripts/swarmforge.sh" "$@"
