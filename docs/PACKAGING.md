# Packaging and publishing Clipdeck

This repository contains everything needed to build Clipdeck for each major Linux packaging system. Pushing a version tag builds them all automatically (see `.github/workflows/release.yml`) and attaches them to a GitHub Release.

## One-time setup

1. Put your GitHub username and email into every file:
   ```bash
   scripts/set-owner.sh <github-username> <email>
   git commit -am "Set project owner"
   ```
   This sets the app ID to `io.github.<username>.Clipdeck`. Flathub requires this form, and it must match the GitHub account that owns the repository. Don't change it after you publish: stores treat a new ID as a different app.
2. Take a screenshot of the history window, save it as `docs/screenshot.png`, and commit it. Flathub and most software centers require one; the AppStream file already points to it.

## Making a release

```bash
scripts/bump-version.sh 0.3.0 "Short summary"
# Add details under the new heading in CHANGELOG.md, then:
git commit -am "Release 0.3.0" && git tag v0.3.0 && git push && git push origin v0.3.0
scripts/release-hashes.sh 0.3.0   # fills the Arch checksum, prints it for Flathub
```

## Where each package lives

| Format | Recipe | Built with | Qt binding |
|---|---|---|---|
| .deb (Debian, Ubuntu, Mint) | `debian/` | `dpkg-buildpackage -b -us -uc` | distro PyQt6 |
| .rpm (Fedora) | `packaging/rpm/clipdeck.spec` | `rpmbuild -bb` | distro PySide6 |
| Arch | `packaging/arch/PKGBUILD` | `makepkg -si` | distro PySide6 |
| Flatpak | `packaging/flatpak/*.yml` | `flatpak-builder` | KDE runtime + PySide BaseApp |
| Snap | `snap/snapcraft.yaml` | `snapcraft` | bundled PySide6 |
| AppImage | `packaging/appimage/build.sh` | python-appimage | bundled PySide6 |
| PyPI | `pyproject.toml` | `python -m build` | PySide6 from pip |

Debian and Ubuntu (and therefore Linux Mint) don't package PySide6, which is why the .deb uses PyQt6. Clipdeck chooses whichever binding is installed (`clipdeck/qt.py`); CI tests both.

## Getting listed in software stores

Start with the stores that cover the most users for the least effort. Rough order:

1. **Flathub**: appears in GNOME Software, KDE Discover, Mint's Software Manager (as a Flatpak), Fedora and many others. Fork https://github.com/flathub/flathub, add the manifest (switch the `clipdeck` module's source from `dir` to the release tarball), and open a pull request against the `new-pr` branch. Reviewers check the metadata, permissions and app ID. Expect questions about `--socket=x11`; explain that Clipdeck needs X11 to read and paste the clipboard. Read Flathub's submission requirements before opening the pull request.
2. **AUR** (Arch, Manjaro, EndeavourOS): create an account at aur.archlinux.org, add your SSH key, then push the PKGBUILD and a generated `.SRCINFO` (`makepkg --printsrcinfo > .SRCINFO`) to `ssh://aur@aur.archlinux.org/clipdeck.git`. Check first that the name isn't taken.
3. **Snap Store** (Ubuntu Software): register the name with `snapcraft register clipdeck`, then upload with `snapcraft upload --release=stable`. Strictly confined apps that use the `x11` plug may be held for manual review.
4. **Ubuntu PPA** (Ubuntu and Mint users get updates through apt): create a Launchpad account and PPA, upload a signed source package (`debuild -S`) with `dput`. Each Ubuntu release (noble, oracular…) needs its own upload with the series name in `debian/changelog`.
5. **Fedora COPR**: create a project at copr.fedorainfracloud.org and point it at the spec file or an SRPM. Users install with `dnf copr enable <user>/clipdeck`.
6. **openSUSE Build Service** (build.opensuse.org): can build the spec for openSUSE; package names differ (for example `python3-pyside6` → `python3-PySide6`), so the spec needs small adjustments there.
7. **PyPI**: `pipx run twine upload dist/*` after a release build. Users then install with `pipx install clipdeck`.
8. **AppImageHub**: submit the AppImage's release URL at https://github.com/AppImage/appimage.github.io.

Getting into the official Debian, Ubuntu or Fedora repositories is a longer process that needs a sponsor or packager sponsor; the PPA and COPR are the usual first steps.

## What still needs a real machine

These recipes are written but can only be fully tested on the real systems:

- The .deb was built and installed on Ubuntu 24.04 during development; the others haven't been built yet.
- Flatpak: shortcuts can't be registered from inside the sandbox, so users bind `flatpak run <app-id> --show` themselves. Autostart goes through the Background portal.
- Snap: same shortcut limitation, and the Snap Store may ask questions about the `x11` plug.
- The AppImage uses the system's `xdotool` for auto-paste, so users need it installed.
