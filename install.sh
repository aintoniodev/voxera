#!/usr/bin/env bash
# install.sh — Install the Stock Assets plugin for pi (Git Bash compatible)
# Idempotent: safe to run multiple times.
#
# Installs:
#   1. pi extension  → ~/.pi/agent/extensions/pixabay/     (MCP server + /pixabay command)
#   2. skill         → ~/.agents/skills/stock-assets/      (shared by ALL agent harnesses)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

install_junction_or_copy() {
    local SRC="$1" DEST="$2" NAME="$3"
    mkdir -p "$(dirname "$DEST")"

    # If destination exists, check what it is
    if [ -e "$DEST" ]; then
        if [ -L "$DEST" ] || cmd //c "dir /A:L \"$(cygpath -w "$DEST")\"" 2>/dev/null | grep -q .; then
            echo "Removing existing symlink/junction: $DEST"
            rm -f "$DEST" 2>/dev/null || cmd //c "rmdir \"$(cygpath -w "$DEST")\"" 2>/dev/null || true
        else
            echo "ERROR: $DEST exists as a real directory."
            echo "Remove it manually: rm -rf \"$(cygpath -w "$DEST")\""
            exit 1
        fi
    fi

    # Try creating a directory junction (Windows)
    DEST_WIN="$(cygpath -w "$DEST")"
    SRC_WIN="$(cygpath -w "$SRC")"
    if cmd //c mklink //J "$DEST_WIN" "$SRC_WIN" 2>/dev/null; then
        echo "Created junction: $DEST -> $SRC"
    else
        echo "Junction failed, falling back to cp -r"
        cp -r "$SRC" "$DEST"
        echo "Copied: $DEST"
    fi
}

# 1. pi extension
install_junction_or_copy \
    "$SCRIPT_DIR/extension" \
    "$HOME/.pi/agent/extensions/pixabay" \
    "extension"

# 2. skill (shared .agents location)
install_junction_or_copy \
    "$SCRIPT_DIR/skills/stock-assets" \
    "$HOME/.agents/skills/stock-assets" \
    "skill"

echo
echo "Stock Assets plugin installed:"
echo "  extension: $HOME/.pi/agent/extensions/pixabay"
echo "  skill:     $HOME/.agents/skills/stock-assets"
echo
echo "Restart pi or run /reload to activate."
