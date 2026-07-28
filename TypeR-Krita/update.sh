#!/usr/bin/env bash
# TypeR for Krita — update (Linux / macOS).
# Re-copies the plugin after a new version or source edits. If TypeR isn't
# installed yet it runs the install instead. Run:  ./update.sh
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ "$(uname)" = "Darwin" ]; then
  DEST="$HOME/Library/Application Support/krita/pykrita"
else
  DEST="${XDG_DATA_HOME:-$HOME/.local/share}/krita/pykrita"
fi

echo "============================================"
echo "  TypeR - Update"
echo "============================================"
echo "Target: $DEST"
echo

if [ ! -f "$SRC/typer_kr.desktop" ] || [ ! -d "$SRC/typer_kr" ]; then
  echo "[ERROR] Run this script from inside the TypeR-Krita folder."
  exit 1
fi

if [ ! -d "$DEST/typer_kr" ]; then
  echo "Not installed yet - running install.sh ..."
  exec "$SRC/install.sh"
fi

cp -f "$SRC/typer_kr.desktop" "$DEST/"
rm -rf "$DEST/typer_kr"
cp -rf "$SRC/typer_kr" "$DEST/"
find "$DEST/typer_kr" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true

echo "Updated. Restart Krita for the changes to take effect."
