#!/usr/bin/env bash
# Terminal backend for native Windows (no WSL): opens Windows Terminal windows
# that attach to the psmux/tmux session. psmux is the native Windows tmux
# (https://github.com/psmux/psmux); it ships a `tmux` alias so the swarm's
# tmux commands work unchanged.
#
# Select with: SWARMFORGE_TERMINAL=windows-native ./swarm

terminal_backend_label() {
  echo "Windows Terminal (native, psmux)"
}

terminal_backend_can_open_sessions() {
  command -v wt.exe &>/dev/null
}

terminal_backend_tracks_windows() {
  return 1
}

terminal_window_exists() {
  return 1
}

terminal_open_session() {
  local session="$1"
  local title="$2"
  local escaped_working_dir
  local escaped_tmux_socket
  local escaped_session

  escaped_working_dir="$(printf '%q' "$WORKING_DIR")"
  escaped_tmux_socket="$(printf '%q' "$TMUX_SOCKET")"
  escaped_session="$(printf '%q' "$session")"

  # Native Windows: run Git Bash (or the configured bash) and attach to the
  # psmux session. No wsl.exe involved.
  local bash_exe="${SWARMFORGE_BASH:-bash}"
  wt.exe -w new --title "$title" "$bash_exe" -lc \
    "cd $escaped_working_dir && exec tmux -S $escaped_tmux_socket attach-session -t $escaped_session"
}

terminal_close_window() {
  return 0
}
