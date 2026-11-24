#!/usr/bin/env bash
# Installs Clipdeck for the current user on Linux Mint / Ubuntu (X11).
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$HOME/.local/share/clipdeck"
BIN="$HOME/.local/bin/clipdeck"

echo "==> Installing system packages (asks for your password)"
sudo apt-get install -y python3-venv xdotool x11-utils libxcb-cursor0

echo "==> Creating a Python environment in $APP_DIR/venv"
mkdir -p "$APP_DIR"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet -r "$SRC/requirements.txt"

echo "==> Copying the app"
rm -rf "$APP_DIR/app" && mkdir -p "$APP_DIR/app"
cp -r "$SRC/clipdeck" "$APP_DIR/app/"

mkdir -p "$(dirname "$BIN")"
cat > "$BIN" <<LAUNCHER
#!/bin/sh
export PYTHONPATH="$APP_DIR/app"
exec "$APP_DIR/venv/bin/python" -m clipdeck "\$@"
LAUNCHER
chmod +x "$BIN"

mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/clipdeck.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Clipdeck
Comment=Clipboard history manager
Exec=$BIN
Icon=edit-paste
Categories=Utility;
DESKTOP

echo "==> Starting Clipdeck"
"$BIN" --quit >/dev/null 2>&1 || true
sleep 0.5
nohup "$BIN" --background >/dev/null 2>&1 &
echo
echo "Done. Clipdeck is in your system tray. Press Ctrl+\` to open your clipboard history."
