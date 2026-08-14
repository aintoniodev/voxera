#!/usr/bin/env bash
# orca-agent-driver.sh — SwarmForge role window driver for the orca backend.
#
# Runs inside the tmux/psmux window SwarmForge opens for a role. Owns ONE orca
# terminal bound to the role worktree; drives a headless agent CLI in that
# terminal (default: `pi -p`, which expands `$(cat file)` itself), streams the
# agent output into the swarm window, and mediates the handoff queue between
# tasks (ready_for_next / done_with_current).
#
# Why a driver is needed: the stock backends (codex/claude/copilot/grok) are
# agent TUIs that run directly in the tmux window. An `orca`-style backend is a
# control CLI (it creates terminals, sends keys, reads output) — the agent must
# live in an orca terminal, and SOMETHING must translate the SwarmForge handoff
# queue into fresh agent invocations. That something is this driver.
#
# Wiring (per project):
#   1. Patch swarmforge.bb parse-config: add "orca" to the agent whitelist
#      ({"claude" "codex" "copilot" "grok" "orca"}).
#   2. Patch swarmforge.bb launch-command: add a "orca" case that runs
#      `bash <script-dir>/orca-agent-driver.sh <role> <worktree> <mode> <prompt>`.
#   3. swarmforge.conf: `window <role> orca <worktree> [task|batch]`.
#   4. Set ORCA_REPO_ID / ORCA_MAIN (see below) — orca only resolves worktrees
#      it has registered; `path:` selectors fail for git-worktree dirs.
# See references/ORCA_BACKEND.md for the full guide and pitfalls.
#
# Usage: orca-agent-driver.sh <role> <worktree> <receive-mode> <prompt-file>
set -u

ROLE="$1"; WORKTREE="$2"; RECEIVE_MODE="$3"; PROMPT_FILE="$4"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ORCA_BIN="${ORCA_CLI_COMMAND:-$(command -v orca 2>/dev/null || echo "$LOCALAPPDATA/Programs/orca/resources/bin/orca")}"
# the agent CLI run inside the orca terminal; `pi -p` expands $(cat <file>)
# itself, so the prompt file path can be passed shell-style.
AGENT_CMD="${SWARMFORGE_ORCA_AGENT:-pi -p \"\$(cat %s)\"}"
# orca worktree anchor: the MAIN worktree of the repo (must be registered in
# orca via `orca repo add`). The role worktrees are usually NOT registered, so
# the terminal is created against the anchor and `cd`'d into the role worktree.
ORCA_REPO_ID="${ORCA_REPO_ID:?set ORCA_REPO_ID to the orca repo id (orca repo list --json)}"
ORCA_MAIN="${ORCA_MAIN:?set ORCA_MAIN to the main worktree path (forward slashes)}"
export PATH="$WORKTREE/swarmforge/scripts:$SCRIPT_DIR:$HOME/swarmforge-bin:$PATH"
WORKTREE_WIN="$(cygpath -w "$WORKTREE" 2>/dev/null || echo "$WORKTREE")"
TITLE="SwarmForge $(echo "$ROLE" | sed 's/^./\U&/')"
TASK_PROMPT="$WORKTREE/swarmforge/task-prompt.md"
DONE_MARKER="<<<AGENT_DONE>>>"
IDLE_SLEEP="${SWARMFORGE_IDLE_SLEEP:-25}"
IDLE_MAX="${SWARMFORGE_IDLE_MAX:-500}"   # polls before giving up (~3.5h default)
TASK_TIMEOUT_POLLS="${SWARMFORGE_TASK_TIMEOUT_POLLS:-360}"  # 5s polls -> 30 min/task
HANDLE=""

log() { echo "[driver:$ROLE] $*"; }
say() { echo "$*"; }

find_or_create_terminal() {
  local title_filter="import sys, json
try:
    d = json.load(sys.stdin)
    title = '$TITLE'
    for t in d.get('result', {}).get('terminals', []):
        if t.get('title', '') == title:
            print(t.get('handle')); break
except Exception:
    pass
"
  HANDLE=$("$ORCA_BIN" terminal list --json 2>/dev/null | python -c "$title_filter")
  if [ -n "$HANDLE" ]; then
    log "reusing terminal $HANDLE"
    "$ORCA_BIN" terminal send --terminal "$HANDLE" --text "cd /d \"$WORKTREE_WIN\"" --enter >/dev/null 2>&1
    return
  fi
  local out
  # anchor on the registered main worktree; cd into the role worktree (cmd syntax)
  out=$("$ORCA_BIN" terminal create --worktree "id:$ORCA_REPO_ID::$ORCA_MAIN" --title "$TITLE" --command "cd /d \"$WORKTREE_WIN\"" --json 2>&1)
  HANDLE=$(echo "$out" | grep -o '"handle": "[^"]*"' | head -1 | cut -d'"' -f4)
  if [ -z "$HANDLE" ]; then
    HANDLE=$("$ORCA_BIN" terminal list --json 2>/dev/null | python -c "$title_filter")
  fi
  if [ -z "$HANDLE" ]; then log "FATAL: cannot create/resolve terminal: $out"; exit 1; fi
  log "terminal $HANDLE ready"
}

# Streams terminal output until the agent prints the done marker (or timeout).
stream_until_done() {
  local cursor="" polls=0 prev_tail=""
  while [ "$polls" -lt "$TASK_TIMEOUT_POLLS" ]; do
    sleep 5; polls=$((polls+1))
    local out new next_cursor tail
    out=$("$ORCA_BIN" terminal read --terminal "$HANDLE" --cursor "$cursor" --limit 3000 --json 2>/dev/null)
    new=$(echo "$out" | python -c "
import sys, json
try:
    d = json.load(sys.stdin)
    t = d.get('result', {}).get('terminal', {})
    print(t.get('nextCursor', ''))
    print('@@TAIL@@')
    print('\n'.join(t.get('tail', [])))
except Exception:
    print('')
" 2>/dev/null)
    next_cursor=$(echo "$new" | sed -n '1p')
    tail=$(echo "$new" | sed -n '/@@TAIL@@/,$p' | tail -n +2)
    if [ -n "$tail" ] && [ "$tail" != "$prev_tail" ]; then
      cursor="$next_cursor"
      prev_tail="$tail"
      echo "$tail" | grep -v '^$' | while IFS= read -r line; do
        case "$line" in
          ">"*|"C:"*">"*) ;;   # shell prompts
          *) say "$line" ;;
        esac
      done
    fi
    if echo "$out" | grep -q "$DONE_MARKER"; then
      log "agent finished (marker seen)"; return 0
    fi
  done
  log "WARN: task timeout ($((TASK_TIMEOUT_POLLS*5))s)"
  return 1
}

run_task() { # $1 = prompt file
  local prompt_file="$1"
  cp "$prompt_file" "$TASK_PROMPT" 2>/dev/null || cat "$prompt_file" > "$TASK_PROMPT"
  local cmd
  cmd=$(printf "$AGENT_CMD" "$TASK_PROMPT")
  "$ORCA_BIN" terminal send --terminal "$HANDLE" --text "$cmd" --enter >/dev/null 2>&1
  log "launched agent for $(basename "$prompt_file")"
  stream_until_done
}

queue_next() {
  local r
  if [ "$RECEIVE_MODE" = "batch" ]; then
    r=$(SWARMFORGE_ROLE="$ROLE" bash "$WORKTREE/swarmforge/scripts/ready_for_next_batch.sh" 2>/dev/null)
  else
    r=$(SWARMFORGE_ROLE="$ROLE" bash "$WORKTREE/swarmforge/scripts/ready_for_next.sh" 2>/dev/null)
  fi
  # ready_for_next prints the TASK/BATCH line plus the handoff payload; we only
  # need the first line — the payload is read from the handoff file itself.
  echo "$r" | sed -n -e 's/^TASK: *//p' -e 's/^BATCH: *//p' | head -1
}

finish_current() {
  if [ "$RECEIVE_MODE" = "batch" ]; then
    SWARMFORGE_ROLE="$ROLE" bash "$WORKTREE/swarmforge/scripts/done_with_current_batch.sh" >/dev/null 2>&1
  else
    SWARMFORGE_ROLE="$ROLE" bash "$WORKTREE/swarmforge/scripts/done_with_current.sh" >/dev/null 2>&1
  fi
}

# ---------- main ----------
cd "$WORKTREE" || { log "FATAL: cannot cd $WORKTREE"; exit 1; }
mkdir -p swarmforge
find_or_create_terminal

# task 1: role instruction (constitution + role prompt + mission) — skipped if
# the marker exists (e.g. after a driver restart mid-swarm)
if [ ! -f "$WORKTREE/.swarmforge/skip-initial" ]; then
  log "task 1: role instruction"
  run_task "$PROMPT_FILE"
else
  log "skip-initial marker present; going straight to queue polling"
fi

# subsequent tasks: poll the handoff queue
idle=0
while [ "$idle" -lt "$IDLE_MAX" ]; do
  if [ -f "$WORKTREE/.swarmforge/stop" ]; then log "stop file found; exiting"; break; fi
  q=$(queue_next)
  if [ -n "$q" ] && [ "$q" != "NONE" ]; then
    idle=0
    task_path="$(cygpath -u "$q" 2>/dev/null || echo "$q")"   # bb prints Windows-style paths
    if [ -f "$task_path" ]; then
      { cat "$PROMPT_FILE"; echo; echo "## Current task"; cat "$task_path"; } > "$TASK_PROMPT"
      log "new task from queue: $task_path"
      run_task "$TASK_PROMPT"
    elif [ -d "$task_path" ]; then
      # batch mode: the queue item is a directory of handoff files
      { cat "$PROMPT_FILE"; echo; echo "## Current batch"; cat "$task_path"/*.handoff; } > "$TASK_PROMPT"
      log "new batch from queue: $task_path"
      run_task "$TASK_PROMPT"
    else
      log "queue item missing file: $task_path"
    fi
    finish_current
    log "queue item completed"
  else
    sleep "$IDLE_SLEEP"; idle=$((idle+1))
    log "no task (idle $idle/$IDLE_MAX)"
  fi
done

log "driver exiting for role $ROLE"
exit 0
