#!/usr/bin/env bash
# TypeR for Krita — uninstall (Linux / macOS).
# Removes the plugin from Krita's pykrita resource folder. Run:  ./uninstall.sh
set -uo pipefail

if [ "$(uname)" = "Darwin" ]; then
  DEST="$HOME/Library/Application Support/krita/pykrita"
else
  DEST="${XDG_DATA_HOME:-$HOME/.local/share}/krita/pykrita"
fi

echo "TypeR - Uninstall"
echo "Folder: $DEST"
echo

if [ -f "$DEST/typer_kr.desktop" ]; then
  rm -f "$DEST/typer_kr.desktop"
  echo "Removed: typer_kr.desktop"
else
  echo "typer_kr.desktop was not present."
fi

if [ -d "$DEST/typer_kr" ]; then
  rm -rf "$DEST/typer_kr"
  echo "Removed: typer_kr/"
else
  echo "typer_kr/ was not present."
fi

echo
echo "Done. Restart Krita for the change to take effect."
