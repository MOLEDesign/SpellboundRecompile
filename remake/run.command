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
  TAP=""
  for t in S_BND128.TAP ../original/S_BND128.TAP ../S_BND128.TAP; do [ -f "$t" ] && TAP="$t" && break; done
  if [ -z "$TAP" ]; then
    echo "Put S_BND128.TAP in the remake folder (or original/) and run again."; read x; exit 1
  fi
  $PY bake.py "$TAP" || { echo "baking failed (needs Xcode command line tools: xcode-select --install)"; read x; exit 1; }
fi
exec $PY spellbound.py "$@"
