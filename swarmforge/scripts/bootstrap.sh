#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ASSETS_DIR="$SCRIPT_DIR/../assets"

usage() {
  echo "Usage: bootstrap.sh <project-dir> [branch]" >&2
  echo "Installs the SwarmForge configuration into <project-dir> using the" >&2
  echo "scripts and assets bundled with this skill (no network required)." >&2
  echo "  project-dir   existing project directory to bootstrap" >&2
  echo "  branch        config/roles/articles variant to install (default: four-pack)" >&2
  exit 1
}

if [[ $# -lt 1 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
fi

PROJECT="${1%/}"
BRANCH="${2:-four-pack}"
SWARMFORGE_DIR="$PROJECT/swarmforge"

if [[ ! -d "$PROJECT" ]]; then
  echo "Error: project directory does not exist: $PROJECT" >&2
  exit 1
fi

mkdir -p "$SWARMFORGE_DIR"

# Scripts bundle: this directory itself.
if [[ ! -d "$SWARMFORGE_DIR/scripts" ]]; then
  mkdir -p "$SWARMFORGE_DIR/scripts"
  cp -R "$SCRIPT_DIR/." "$SWARMFORGE_DIR/scripts/"
  echo "Installed scripts -> $SWARMFORGE_DIR/scripts/"
else
  echo "Skipping scripts: already present at $SWARMFORGE_DIR/scripts/"
fi

# Shared articles.
if [[ ! -d "$SWARMFORGE_DIR/scripts/shared-articles" ]]; then
  if [[ -d "$ASSETS_DIR/constitution/articles" ]]; then
    mkdir -p "$SWARMFORGE_DIR/scripts/shared-articles"
    cp -R "$ASSETS_DIR/constitution/articles/." "$SWARMFORGE_DIR/scripts/shared-articles/"
    echo "Installed shared articles -> $SWARMFORGE_DIR/scripts/shared-articles/"
  else
    echo "Warning: no shared articles found at $ASSETS_DIR/constitution/articles" >&2
  fi
else
  echo "Skipping shared articles: already present at $SWARMFORGE_DIR/scripts/shared-articles/"
fi

# Branch config file.
if [[ ! -f "$SWARMFORGE_DIR/swarmforge.conf" ]]; then
  if [[ -f "$ASSETS_DIR/examples/swarmforge.conf.$BRANCH" ]]; then
    cp "$ASSETS_DIR/examples/swarmforge.conf.$BRANCH" "$SWARMFORGE_DIR/swarmforge.conf"
    echo "Installed swarmforge.conf (branch $BRANCH)"
  elif [[ -f "$ASSETS_DIR/examples/swarmforge.conf" ]]; then
    cp "$ASSETS_DIR/examples/swarmforge.conf" "$SWARMFORGE_DIR/swarmforge.conf"
    echo "Installed swarmforge.conf"
  else
    echo "Warning: no swarmforge.conf found in assets/examples for branch $BRANCH" >&2
  fi
else
  echo "Skipping swarmforge.conf: already present"
fi

# Branch constitution prompt.
if [[ ! -f "$SWARMFORGE_DIR/constitution.prompt" ]]; then
  if [[ -f "$ASSETS_DIR/constitution/constitution.prompt" ]]; then
    cp "$ASSETS_DIR/constitution/constitution.prompt" "$SWARMFORGE_DIR/constitution.prompt"
    echo "Installed constitution.prompt"
  else
    echo "Warning: no constitution.prompt found at $ASSETS_DIR/constitution" >&2
  fi
else
  echo "Skipping constitution.prompt: already present"
fi

# Branch roles.
if [[ ! -d "$SWARMFORGE_DIR/roles" ]]; then
  if [[ -d "$ASSETS_DIR/roles/$BRANCH" ]]; then
    mkdir -p "$SWARMFORGE_DIR/roles"
    cp -R "$ASSETS_DIR/roles/$BRANCH/." "$SWARMFORGE_DIR/roles/"
    echo "Installed roles -> $SWARMFORGE_DIR/roles/ (branch $BRANCH)"
  else
    echo "Warning: no roles found at $ASSETS_DIR/roles/$BRANCH" >&2
  fi
else
  echo "Skipping roles: already present at $SWARMFORGE_DIR/roles/"
fi

# Branch local articles (mirrors the repo layout referenced by the constitution).
if [[ ! -d "$SWARMFORGE_DIR/constitution/articles" ]]; then
  if [[ -d "$ASSETS_DIR/constitution/articles" ]]; then
    mkdir -p "$SWARMFORGE_DIR/constitution/articles"
    cp -R "$ASSETS_DIR/constitution/articles/." "$SWARMFORGE_DIR/constitution/articles/"
    echo "Installed local articles -> $SWARMFORGE_DIR/constitution/articles/"
  else
    echo "Warning: no articles found at $ASSETS_DIR/constitution/articles" >&2
  fi
else
  echo "Skipping local articles: already present at $SWARMFORGE_DIR/constitution/articles/"
fi

echo
echo "SwarmForge installed into $SWARMFORGE_DIR (branch $BRANCH)."
echo "To launch:"
echo "  cd $PROJECT && ./swarmforge/scripts/swarmforge.sh"
