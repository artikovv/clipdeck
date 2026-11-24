# Clipdeck

Version 0.2.0 · by Farroukh Artikov

A clipboard history manager for Linux, inspired by [Ditto](https://ditto-cp.sourceforge.io/) on Windows.

**Features:** searchable history of text, formatted text, images and files · pinned clips and groups · paste as plain text · encrypted sync between computers on your network.

**Requirements:** a Linux desktop running X11 (see [Supported desktops](#supported-desktops)).

## Install

Download a package for your system from the [latest release](https://github.com/artikovv/clipdeck/releases/latest):

| System | Package | Install |
|---|---|---|
| Debian, Ubuntu, Linux Mint | `clipdeck_*_all.deb` | `sudo apt install ./clipdeck_*_all.deb` |
| Fedora | `clipdeck-*.noarch.rpm` | `sudo dnf install ./clipdeck-*.noarch.rpm` |
| Any distro | `Clipdeck.flatpak` | `flatpak install --user Clipdeck.flatpak` |
| Any distro | `Clipdeck-*.AppImage` | `chmod +x Clipdeck-*.AppImage` and run it |
| Ubuntu and others with Snap | `clipdeck_*.snap` | `sudo snap install --dangerous ./clipdeck_*.snap` |

Or install from source (Debian, Ubuntu, Mint, Fedora, openSUSE, Arch):

```bash
git clone https://github.com/artikovv/clipdeck.git
cd clipdeck
./install.sh
```

Clipdeck starts in the system tray and adds a **Ctrl+`** keyboard shortcut. With Flatpak, Snap and AppImage, add the shortcut yourself in your desktop's keyboard settings; the command is shown when Clipdeck first starts.

## Supported desktops

| Desktop | Works | Shortcut set up automatically |
|---|---|---|
| Cinnamon (Linux Mint) | Yes | Yes |
| MATE | Yes | Yes |
| Xfce | Yes | Yes |
| KDE Plasma (X11 session) | Yes | Yes, after logging out and back in |
| GNOME (X11 session) | Yes | Yes |
| Wayland sessions (GNOME, KDE, Sway…) | Not yet | — |

Recent Fedora Workstation and Ubuntu releases run GNOME only on Wayland. Wayland support is planned for version 0.3.0.

## Use

Press **Ctrl+`** in any app, pick a clip, and press **Enter**. Clipdeck puts it on the clipboard and pastes it into the window you were using.

| Key | Action |
|---|---|
| Type | Search (works with Cyrillic, Turkish, any language) |
| Enter / double-click | Paste |
| Shift+Enter | Paste as plain text |
| Ctrl+1 … Ctrl+9 | Paste one of the first nine clips |
| Ctrl+P | Pin or unpin |
| Shift+Delete | Delete |
| Esc | Close |

Right-click a clip to pin it, move it to a group, send it to another computer, or delete it. Pinned and grouped clips are never removed when the history fills up. Use the **Groups** button to create, rename, or delete groups, and the drop-down to view one.

Clipdeck records text, formatted text (HTML), images, and copied files (pasting files works in Nemo). It skips anything a password manager like KeePassXC marks as secret. To stop recording for a while, choose **Pause capturing** in the tray menu.

## Sync between computers

1. Install Clipdeck on each computer.
2. On each one, open **Settings → Sync**, turn on sync, enter the same passphrase, and list the other computers' IP addresses (shown at the bottom of the tab).
3. If a firewall is on, allow the port: `sudo ufw allow 47811/tcp`.

Clips are encrypted with a key made from the passphrase. Each computer's clock needs to be within five minutes of the others (Mint keeps time automatically). Turn off **Send every copy automatically** if you'd rather send clips by hand from the right-click menu.

## Files

- History: `~/.local/share/clipdeck/clips.db`
- Settings: `~/.config/clipdeck/clipdeck.conf` (includes the sync passphrase)
- Command line: `clipdeck --show`, `clipdeck --quit`, `clipdeck --version`

## Troubleshooting

- **Shortcut does nothing:** look for "Clipdeck" in your desktop's custom keyboard shortcuts. Another app may already use Ctrl+`; change it in Clipdeck's Settings.
- **Clip is copied but not pasted:** make sure `xdotool` is installed. Terminals need Ctrl+Shift+V; add your terminal's window class to Settings → General if it isn't listed (find it with `xprop WM_CLASS`, then click the terminal).
- **See error messages:** run `clipdeck --quit`, then `clipdeck` in a terminal.

If you installed from source, uninstall with `./uninstall.sh`. Packages uninstall with your package manager.

## Contributing

Run the tests with `pytest tests`. See [docs/PACKAGING.md](docs/PACKAGING.md) for how packages are built and published.

## Author

Farroukh Artikov
Clipdeck was developed with the help of Claude, an AI assistant. Farroukh Artikov designed, tested and maintains it.

## License

MIT. See [LICENSE](LICENSE).
