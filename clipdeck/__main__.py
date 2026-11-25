"""Entry point. `--show` and `--quit` talk to the running instance over a
Unix socket without importing Qt, so the hotkey responds quickly."""
import os
import socket
import sys
import tempfile

USAGE = """usage: clipdeck [--show | --paste N | --paste-plain | --save | --background | --quit]
  (no option)    start Clipdeck, or open the history if it's already running
  --show         open the history window (bind this to a keyboard shortcut)
  --paste N      paste clip number N (1 = the top of the history)
  --paste-plain  paste what's on the clipboard as plain text
  --save         save what's on the clipboard now, even while capturing is paused
  --background   start without opening anything if not running (used at login)
  --quit         stop the running instance
  --version     show the version"""


def ipc_path() -> str:
    base = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    if os.environ.get("FLATPAK_ID"):
        # Each `flatpak run` gets its own sandbox; this folder is shared between them.
        base = os.path.join(base, "app", os.environ["FLATPAK_ID"])
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
    if "--paste" in args:
        i = args.index("--paste")
        n = args[i + 1] if i + 1 < len(args) else ""
        if not n.isdigit():
            print("clipdeck: --paste needs a clip number, for example --paste 1", file=sys.stderr)
            return 2
        command = f"paste {n}"
    elif "--paste-plain" in args:
        command = "paste-plain"
    elif "--save" in args:
        command = "save"
    elif background:
        command = ""
    elif "--show" in args or not args:
        command = "show"
    else:
        print(USAGE)
        return 2
    if send(command or "noop"):
        return 0  # the running instance does it
    from .app import run
    # Not running yet: start, and do the command once started. Starting with no
    # option just starts quietly in the tray, as before.
    return run(ipc_path(), command="" if not args else command, background=background)


if __name__ == "__main__":
    sys.exit(main())
