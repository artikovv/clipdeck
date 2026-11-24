#!/usr/bin/env bash
set -uo pipefail
"$HOME/.local/bin/clipdeck" --quit 2>/dev/null
rm -rf "$HOME/.local/share/clipdeck/app" "$HOME/.local/share/clipdeck/venv"
rm -f "$HOME/.local/bin/clipdeck" "$HOME/.local/share/applications/clipdeck.desktop" \
      "$HOME/.config/autostart/clipdeck.desktop"
echo "Clipdeck removed."
echo "Your history is still in ~/.local/share/clipdeck/clips.db and settings in ~/.config/clipdeck/ — delete them if you don't need them."
echo "Remove the keyboard shortcut in System Settings → Keyboard → Shortcuts → Custom Shortcuts."
