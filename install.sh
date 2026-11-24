#!/usr/bin/env bash
# Installs Clipdeck from source for the current user.
# Supports Debian, Ubuntu, Linux Mint, Fedora, openSUSE, Arch and their derivatives.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
APP_ID="$(sed -n 's/^APP_ID = "\(.*\)"/\1/p' "$SRC/clipdeck/__init__.py")"
APP_DIR="$HOME/.local/share/clipdeck"
SHARE="$HOME/.local/share"
BIN="$HOME/.local/bin/clipdeck"

. /etc/os-release
family=" ${ID:-} ${ID_LIKE:-} "
if command -v apt-get >/dev/null && [[ $family =~ (debian|ubuntu) ]]; then
    pkgs=(python3-venv xdotool x11-utils libxcb-cursor0)
    install_cmd=(sudo apt-get install -y)
elif command -v dnf >/dev/null; then
    pkgs=(python3 xdotool xprop xcb-util-cursor)
    install_cmd=(sudo dnf install -y)
elif command -v zypper >/dev/null; then
    pkgs=(python3 xdotool xprop libxcb-cursor0)
    install_cmd=(sudo zypper --non-interactive install)
elif command -v pacman >/dev/null; then
    pkgs=(python xdotool xorg-xprop xcb-util-cursor)
    install_cmd=(sudo pacman -S --needed --noconfirm)
else
    echo "Unrecognized distribution. Install these yourself, then run this script again with SKIP_DEPS=1:"
    echo "  Python 3.10+ with venv, xdotool, xprop, and the xcb-cursor library"
    [[ ${SKIP_DEPS:-0} == 1 ]] || exit 1
    pkgs=()
fi

if [[ ${SKIP_DEPS:-0} != 1 && ${#pkgs[@]} -gt 0 ]]; then
    echo "==> Installing system packages: ${pkgs[*]} (asks for your password)"
    "${install_cmd[@]}" "${pkgs[@]}"
fi

if [[ ${XDG_SESSION_TYPE:-x11} == wayland ]]; then
    echo "Note: you're in a Wayland session. Clipdeck currently needs X11 to capture and paste."
    echo "      Choose an X11 or Xorg session on the login screen if your desktop offers one."
fi

echo "==> Creating a Python environment in $APP_DIR/venv"
mkdir -p "$APP_DIR"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet "$SRC"

mkdir -p "$(dirname "$BIN")"
ln -sf "$APP_DIR/venv/bin/clipdeck" "$BIN"

echo "==> Adding Clipdeck to your applications menu"
install -Dm644 "$SRC/data/$APP_ID.desktop" "$SHARE/applications/$APP_ID.desktop"
sed -i "s|^Exec=clipdeck|Exec=$BIN|" "$SHARE/applications/$APP_ID.desktop"
install -Dm644 "$SRC/data/$APP_ID.svg" "$SHARE/icons/hicolor/scalable/apps/$APP_ID.svg"
install -Dm644 "$SRC/data/$APP_ID.metainfo.xml" "$SHARE/metainfo/$APP_ID.metainfo.xml"
command -v update-desktop-database >/dev/null && update-desktop-database "$SHARE/applications" || true

echo "==> Starting Clipdeck"
"$BIN" --quit >/dev/null 2>&1 || true
sleep 0.5
nohup "$BIN" --background >/dev/null 2>&1 &
echo
echo "Done. Clipdeck is in your system tray. Press Ctrl+\` to open your clipboard history."
