#!/usr/bin/env bash
# Builds Clipdeck-<version>-x86_64.AppImage into dist/ using python-appimage.
# The AppImage bundles Python, PySide6 and cryptography. It uses the system's
# xdotool for auto-paste if installed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APP_ID="$(sed -n 's/^APP_ID = "\(.*\)"/\1/p' "$ROOT/clipdeck/__init__.py")"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/clipdeck/__init__.py")"
PYVER="${PYVER:-3.12}"
WORK="$(mktemp -d)"
RECIPE="$WORK/clipdeck"
mkdir -p "$RECIPE" "$ROOT/dist"

# Build tools go in a throwaway venv (Debian/Ubuntu block system-wide pip).
python3 -m venv "$WORK/venv"
PY="$WORK/venv/bin/python"
"$PY" -m pip install --quiet --upgrade pip python-appimage setuptools wheel
"$PY" -m pip wheel --quiet --no-deps -w "$WORK/wheels" "$ROOT"

printf '%s\nPySide6-Essentials>=6.6\ncryptography>=41\n' "$(ls "$WORK"/wheels/clipdeck-*.whl)" > "$RECIPE/requirements.txt"
cp "$ROOT/data/$APP_ID.desktop" "$RECIPE/"
cp "$ROOT/data/$APP_ID.svg" "$RECIPE/"
cp "$ROOT/data/$APP_ID.metainfo.xml" "$RECIPE/$APP_ID.appdata.xml"
cat > "$RECIPE/entrypoint.sh" <<'ENTRY'
{{ python-executable }} -s -m clipdeck "$@"
ENTRY

cd "$WORK"
"$PY" -m python_appimage build app --python-version "$PYVER" \
    --name "Clipdeck-$VERSION-x86_64" "$RECIPE"
mv "$WORK"/Clipdeck-*.AppImage "$ROOT/dist/"
echo "Built: $(ls "$ROOT"/dist/Clipdeck-*.AppImage)"
