#!/usr/bin/env bash
# TypeR for Krita — install (Linux / macOS).
# Copies the plugin into Krita's pykrita resource folder. Run it from the
# TypeR-Krita folder:  ./install.sh
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ "$(uname)" = "Darwin" ]; then
  DEST="$HOME/Library/Application Support/krita/pykrita"
else
  DEST="${XDG_DATA_HOME:-$HOME/.local/share}/krita/pykrita"
fi

echo "============================================"
echo "  TypeR - Installation"
echo "============================================"
echo "Source: $SRC"
echo "Target: $DEST"
echo

if [ ! -f "$SRC/typer_kr.desktop" ] || [ ! -d "$SRC/typer_kr" ]; then
  echo "[ERROR] typer_kr.desktop / typer_kr not found."
  echo "        Run this script from inside the TypeR-Krita folder."
  exit 1
fi

mkdir -p "$DEST"
cp -f "$SRC/typer_kr.desktop" "$DEST/"
rm -rf "$DEST/typer_kr"
cp -rf "$SRC/typer_kr" "$DEST/"
# don't ship stale bytecode
find "$DEST/typer_kr" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true

echo "Done."
echo "In Krita: Settings > Configure Krita > Python Plugin Manager >"
echo "enable \"TypeR for Krita\", then restart Krita."
