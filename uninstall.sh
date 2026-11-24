#!/usr/bin/env bash
# Removes a Clipdeck installed with install.sh. Packages (deb, rpm, Flatpak, Snap) uninstall with their own tools.
set -uo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
APP_ID="$(sed -n 's/^APP_ID = "\(.*\)"/\1/p' "$SRC/clipdeck/__init__.py")"
SHARE="$HOME/.local/share"
"$HOME/.local/bin/clipdeck" --quit 2>/dev/null
rm -rf "$SHARE/clipdeck/venv" "$SHARE/clipdeck/app"
rm -f "$HOME/.local/bin/clipdeck" \
      "$SHARE/applications/$APP_ID.desktop" "$SHARE/applications/clipdeck.desktop" \
      "$SHARE/applications/clipdeck-show.desktop" \
      "$SHARE/icons/hicolor/scalable/apps/$APP_ID.svg" "$SHARE/metainfo/$APP_ID.metainfo.xml" \
      "$HOME/.config/autostart/$APP_ID.desktop" "$HOME/.config/autostart/clipdeck.desktop"
echo "Clipdeck removed."
echo "Your history (~/.local/share/clipdeck/clips.db) and settings (~/.config/clipdeck/) were kept; delete them if you don't need them."
echo "Remove the Clipdeck keyboard shortcut in your desktop's keyboard settings."
