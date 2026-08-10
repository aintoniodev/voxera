#!/usr/bin/env bash
# Setup the SwarmForge alternative stack on native Windows (no WSL, no zsh, no
# MSYS2 tmux). Installs:
#   - psmux    -> the native Windows tmux (winget). Ships a `tmux` alias.
#   - babashka -> bb.exe (direct download from GitHub releases; scoop has no
#                 manifest for babashka).
# Uses the existing Git Bash (bash) for the .sh layer.
#
# Usage: bash scripts/setup-windows.sh
set -euo pipefail

say()  { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; exit 1; }

check() {
  local tool="$1" hint="$2"
  if command -v "$tool" &>/dev/null; then
    say "$tool: OK ($(command -v "$tool"))"
    return 0
  fi
  warn "$tool: no instalado ($hint)"
  return 1
}

BB_INSTALL_DIR="${SWARMFORGE_BB_DIR:-$HOME/swarmforge-bin}"

install_bb() {
  say "Descargando babashka (bb.exe) desde GitHub releases..."
  local tag url zip
  tag="$(curl -s https://api.github.com/repos/babashka/babashka/releases/latest | grep -oE '"tag_name": "[^"]+"' | cut -d'"' -f4)"
  [[ -n "$tag" ]] || fail "No se pudo obtener la última release de babashka."
  zip="${tag}-windows-amd64.zip"
  url="https://github.com/babashka/babashka/releases/download/${tag}/babashka-${tag#v}-windows-amd64.zip"
  [[ "$tag" == v* ]] || url="https://github.com/babashka/babashka/releases/download/${tag}/babashka-${tag}-windows-amd64.zip"
  say "Release: $tag"
  curl -sL -o "$zip" "$url" || fail "Descarga falló: $url"
  mkdir -p "$BB_INSTALL_DIR"
  unzip -o -q "$zip" -d "$BB_INSTALL_DIR" || fail "Unzip falló."
  rm -f "$zip"
  # Añadir al PATH del usuario si no está
  if ! command -v bb &>/dev/null; then
    if [[ -f "$HOME/.bashrc" ]] && ! grep -q "$BB_INSTALL_DIR" "$HOME/.bashrc" 2>/dev/null; then
      echo "export PATH=\"$BB_INSTALL_DIR:\$PATH\"" >> "$HOME/.bashrc"
      say "Añadido $BB_INSTALL_DIR a ~/.bashrc (reabre el shell o ejecuta: export PATH=\"$BB_INSTALL_DIR:\$PATH\")"
    fi
  fi
}

echo
say "SwarmForge stack check — native Windows (bash + psmux + bb.exe)"
echo

check bash "viene con Git for Windows (https://gitforwindows.org) instalado."
BASH_OK=$?

if check winget "instala PowerShell 7+ o descarga winget desde Microsoft Store."; then
  if command -v tmux &>/dev/null; then
    say "tmux: ya disponible ($(command -v tmux))"
  else
    say "Instalando psmux (tmux nativo de Windows) vía winget..."
    winget install --accept-source-agreements --accept-package-agreements psmux \
      || warn "winget install psmux falló; instálalo manualmente: https://github.com/psmux/psmux/releases"
  fi
fi

if check bb "bb.exe de babashka"; then
  say "babashka: ya disponible ($(command -v bb))"
else
  install_bb
fi

echo
say "Verificando binarios de la alternativa..."
check tmux "psmux expone el alias tmux. Reabre el shell o: export PATH=\"\$PATH:\$LOCALAPPDATA/Microsoft/WinGet/Links\""
check bb   "bb.exe de babashka (instalado en $BB_INSTALL_DIR)"

echo
if command -v tmux &>/dev/null && command -v bb &>/dev/null && [[ "$BASH_OK" == 0 ]]; then
  say "Stack completo: bash + tmux(psmux) + bb(babashka). Listo para arrancar el swarm."
  say "Lanzamiento: SWARMFORGE_TERMINAL=windows-native bash scripts/bootstrap.sh <project-dir> [branch]"
else
  warn "Faltan binarios — revisa los pasos marcados arriba. Los scripts del plugin ya son bash-compatibles;"
  warn "solo hace falta psmux (tmux) y babashka (bb) en el PATH."
  exit 1
fi
