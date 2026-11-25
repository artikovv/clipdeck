%global appid io.github.artikovv.Clipdeck

Name:           clipdeck
Version:        0.3.0
Release:        1%{?dist}
Summary:        Clipboard history manager with search, pins and sync
License:        MIT
URL:            https://github.com/artikovv/clipdeck
Source0:        %{url}/archive/v%{version}/%{name}-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  desktop-file-utils
BuildRequires:  libappstream-glib
# Fedora packages PySide6, so the automatic Python dependencies resolve.
Requires:       python3-pyside6
Requires:       python3-cryptography
Requires:       xdotool
Requires:       xprop
Requires:       hicolor-icon-theme

%description
Clipdeck remembers what you copy so you can paste it again later. Press a
shortcut, type a few letters to find a clip, and press Enter to paste it into
the window you were using. It keeps text, formatted text, images and copied
files, lets you pin clips and sort them into groups, and can sync clips between
computers over an encrypted connection. It works on X11 desktops such as
Cinnamon, Xfce and MATE.

%prep
%autosetup -n %{name}-%{version}

%generate_buildrequires
%pyproject_buildrequires -R

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files clipdeck
install -Dm644 data/%{appid}.desktop %{buildroot}%{_datadir}/applications/%{appid}.desktop
install -Dm644 data/%{appid}.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/%{appid}.svg
install -Dm644 data/%{appid}.metainfo.xml %{buildroot}%{_metainfodir}/%{appid}.metainfo.xml
install -Dm644 docs/clipdeck.1 %{buildroot}%{_mandir}/man1/clipdeck.1

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/%{appid}.desktop
appstream-util validate-relax --nonet %{buildroot}%{_metainfodir}/%{appid}.metainfo.xml

%files -f %{pyproject_files}
%license LICENSE
%doc README.md CHANGELOG.md
%{_bindir}/clipdeck
%{_datadir}/applications/%{appid}.desktop
%{_datadir}/icons/hicolor/scalable/apps/%{appid}.svg
%{_metainfodir}/%{appid}.metainfo.xml
%{_mandir}/man1/clipdeck.1*

%changelog
* Wed Nov 25 2026 Farroukh Artikov <farroukh.tj@gmail.com> - 0.3.0-1
- Ditto-style keyboard shortcuts, tray menu and Options window

* Tue Nov 24 2026 Farroukh Artikov <farroukh.tj@gmail.com> - 0.2.0-1
- Shortcut setup for Cinnamon, GNOME, MATE, Xfce and KDE
- Packages for major distros, Flatpak, Snap and AppImage
