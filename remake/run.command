#!/bin/sh
# Double-click in Finder to play. First run installs pygame-ce (for this
# user) and bakes the game data from S_BND128.TAP.
cd "$(dirname "$0")"
PY=python3
if ! $PY -c "import pygame" 2>/dev/null; then
  echo "Installing pygame-ce..."
  $PY -m pip install --user pygame-ce || { echo "pip failed - install Python 3 from python.org first"; read x; exit 1; }
fi
if [ ! -f data/game.json ]; then
  $PY bake.py || { echo; echo "Press Return to close."; read x; exit 1; }
fi
exec $PY spellbound.py "$@"
