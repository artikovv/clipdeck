"""Qt imports that work with either PySide6 or PyQt6.

pip, Flatpak, Snap and AppImage builds use PySide6. Distro packages use the
distro's PyQt6, because Debian and Ubuntu (and so Linux Mint) don't package
PySide6. Set CLIPDECK_QT=pyqt6 or pyside6 to force one.
"""
import os

_choice = os.environ.get("CLIPDECK_QT", "").lower()

try:
    if _choice == "pyqt6":
        raise ImportError
    from PySide6.QtCore import *  # noqa: F401,F403
    from PySide6.QtGui import *  # noqa: F401,F403
    from PySide6.QtNetwork import *  # noqa: F401,F403
    from PySide6.QtWidgets import *  # noqa: F401,F403
    from PySide6.QtCore import Signal  # noqa: F401
    BINDING = "PySide6"
except ImportError:
    if _choice == "pyside6":
        raise
    from PyQt6.QtCore import *  # noqa: F401,F403
    from PyQt6.QtGui import *  # noqa: F401,F403
    from PyQt6.QtNetwork import *  # noqa: F401,F403
    from PyQt6.QtWidgets import *  # noqa: F401,F403
    from PyQt6.QtCore import pyqtSignal as Signal  # noqa: F401
    BINDING = "PyQt6"


def dbus():
    """QtDBus classes, or None if this binding lacks them."""
    try:
        if BINDING == "PySide6":
            from PySide6.QtDBus import QDBusConnection, QDBusMessage
        else:
            from PyQt6.QtDBus import QDBusConnection, QDBusMessage
        return QDBusConnection, QDBusMessage
    except ImportError:
        return None
