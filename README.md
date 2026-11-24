# Clipdeck

Version 0.1.0 · by Farroukh Artikov

A clipboard history manager for Linux, inspired by [Ditto](https://ditto-cp.sourceforge.io/) on Windows. Built for Linux Mint (Cinnamon, X11) and should work on other X11 desktops.

**Features:** searchable history of text, formatted text, images and files · pinned clips and groups · paste as plain text · encrypted sync between computers on your network.

**Requirements:** Linux with an X11 session, Python 3.10+.

## Install

```bash
git clone https://github.com/YOUR-USERNAME/clipdeck.git
cd clipdeck
./install.sh
```

Clipdeck starts in the system tray and registers **Ctrl+`** as a Cinnamon keyboard shortcut. It also starts automatically when you log in.

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

- **Shortcut does nothing:** check System Settings → Keyboard → Shortcuts → Custom Shortcuts for "Clipdeck". Another app may already use Ctrl+`; change it in Clipdeck's Settings.
- **Clip is copied but not pasted:** make sure `xdotool` is installed. Terminals need Ctrl+Shift+V; add your terminal's window class to Settings → General if it isn't listed (find it with `xprop WM_CLASS`, then click the terminal).
- **See error messages:** run `clipdeck --quit`, then `clipdeck` in a terminal.

Uninstall with `./uninstall.sh`.

## Author

Farroukh Artikov

## License

MIT. See [LICENSE](LICENSE).
