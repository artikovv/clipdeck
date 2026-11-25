# Changelog

## Unreleased

- Delete removes the selected clip(s); while you type a search, it still edits the search text.
- Select several clips with Ctrl+A, Shift+arrows, Shift+click or Ctrl+click, then paste, copy, pin, move or delete them together. Pasting several clips joins them one per line.
- Ctrl+C copies clips without pasting; Ctrl+E or F2 edits a text clip; F3 shows a preview of the full text or image.
- Esc clears the search before closing the window.
- Clips show their Ctrl+1–9 quick-paste number.
- Long clips are shortened with "…" instead of adding a horizontal scrollbar.
- Settings reorganized like Ditto's Options, with new tabs and options:
  - General: delete clips not used for a number of days, turn the clip limit off, light or dark theme, window position (mouse pointer, centre, or where you left it), font, and a custom history file location. The history window can be dragged and resized, and remembers its size.
  - Supported types: choose which kinds of copies to save, and include or exclude apps.
  - Keyboard shortcuts: paste the clipboard as plain text, save the clipboard, and paste any of the 10 most recent clips directly. Shortcuts are recorded by pressing them and work with any keyboard layout.
  - Stats and About tabs.
- New commands: `--paste N`, `--paste-plain` and `--save`.
- A tray menu modelled on Ditto's: delete clip data by age, delete unused clips, back up and restore the history, import text files and images, add a clip by hand, save the current clipboard while paused, a startup message you can turn off, and a Help window.

## 0.2.0 (2026-11-24)

- Sets up the keyboard shortcut automatically on Cinnamon, GNOME, MATE, Xfce and KDE.
- The source installer works on Debian, Ubuntu, Linux Mint, Fedora, openSUSE and Arch.
- Packaging for .deb, .rpm, Arch (AUR), Flatpak, Snap and AppImage, built automatically for each release.
- Runs with either PySide6 or PyQt6, so distro packages can use the distro's own Qt bindings.
- `clipdeck --version` and a man page.
- Automated tests.

## 0.1.0 (2026-11-24)

- First release: clipboard history with search, pins, groups, images, files, plain-text paste and encrypted sync.
