#!/usr/bin/env bash
# Recrea los venvs del pipeline tras el rename del repo (improve-my-sound -> voxera).
# Ejecutar desde la raíz del repo, con esta sesión (y cualquier otra con CWD dentro) cerrada:
#   mv improve-my-sound voxera && cd voxera && bash docs/envs/recreate.sh
set -euo pipefail

# uv está en ~/.local/bin, que solo añade el .bashrc interactivo;
# lanzado no-interactivo desde PowerShell no estaría en el PATH.
command -v uv >/dev/null 2>&1 || export PATH="$HOME/.local/bin:$PATH"

uv venv .venv --python 3.11 --clear
# --no-deps: el freeze ya es el cierre completo; el resolver estricto de uv
# rechazaría pines históricamente inconsistentes (p.ej. fairseq 0.12.2 + omegaconf 2.3.0)
uv pip install --no-deps -r docs/envs/venv.txt --python .venv/Scripts/python.exe
uv venv .venv-video --python 3.11 --clear
# unsafe-best-match: con el índice de PyTorch como extra, uv debe poder tomar
# cada pin de cualquiera de los dos índices (certifi et al. también están en el de PyTorch)
uv pip install --no-deps --index-strategy unsafe-best-match -r docs/envs/venv-video.txt --python .venv-video/Scripts/python.exe

.venv/Scripts/python.exe -c "import faster_whisper, PIL; print('venv OK')"
.venv-video/Scripts/python.exe -c "import cv2, faster_whisper; print('venv-video OK')"
echo "Venvs recreados bajo el nombre nuevo."
