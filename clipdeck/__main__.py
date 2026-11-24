"""Entry point. `--show` and `--quit` talk to the running instance over a
Unix socket without importing Qt, so the hotkey responds quickly."""
import os
import socket
import sys
import tempfile

USAGE = """usage: clipdeck [--show | --background | --quit]
  (no option)   start Clipdeck, or open the history if it's already running
  --show        open the history window (bind this to a keyboard shortcut)
  --background  start silently if not running (used at login)
  --quit        stop the running instance
  --version     show the version"""


def ipc_path() -> str:
    base = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    return os.path.join(base, f"clipdeck-{os.getuid()}.sock")


def send(cmd: str) -> bool:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            s.connect(ipc_path())
            s.sendall(cmd.encode() + b"\n")
        return True
    except OSError:
        return False


def main() -> int:
    args = sys.argv[1:]
    if "-h" in args or "--help" in args:
        print(USAGE)
        return 0
    if "--version" in args:
        from . import __author__, __version__
        print(f"Clipdeck {__version__} by {__author__}")
        return 0
    if "--quit" in args:
        return 0 if send("quit") else 1
    background = "--background" in args
    if send("noop" if background else "show"):
        return 0  # already running
    from .app import run
    return run(ipc_path(), show_now="--show" in args, background=background)


if __name__ == "__main__":
    sys.exit(main())
