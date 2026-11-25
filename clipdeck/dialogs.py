"""Small dialogs opened from the tray menu."""
from __future__ import annotations

import html
from importlib import metadata

from . import APP_ID, __version__
from .qt import (QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                 QRadioButton, QSpinBox, Qt, QVBoxLayout)
from .storage import Storage

KEYS = [
    ("Enter / double-click", "Paste the selected clip(s)"),
    ("Shift+Enter", "Paste as plain text"),
    ("Ctrl+1 … Ctrl+9", "Paste the clip with that number"),
    ("Delete", "Delete the selected clip(s)"),
    ("Ctrl+A", "Select all clips"),
    ("Shift+↑/↓, Ctrl+click", "Select several clips"),
    ("Ctrl+C", "Copy without pasting"),
    ("Ctrl+E or F2", "Edit a text clip"),
    ("Ctrl+P", "Pin or unpin"),
    ("F3", "Show or hide the preview"),
    ("Esc", "Clear the search, or close"),
]


def project_url() -> str:
    """The project page, from the installed package's metadata if available."""
    try:
        for entry in metadata.metadata("clipdeck").get_all("Project-URL") or []:
            label, _, url = entry.partition(",")
            if label.strip().lower() == "homepage":
                return url.strip()
    except metadata.PackageNotFoundError:
        pass
    owner = APP_ID.split(".")[2] if APP_ID.count(".") >= 3 else ""
    return f"https://github.com/{owner}/clipdeck"


def help_html(hotkey: str) -> str:
    rows = "".join(f"<tr><td><b>{html.escape(k)}</b>&nbsp;&nbsp;</td><td>{html.escape(v)}</td></tr>"
                   for k, v in KEYS)
    url = project_url()
    return (f"<h3>Clipdeck {__version__}</h3>"
            f"<p>Press <b>{html.escape(hotkey)}</b> in any app to open your clipboard history, "
            "type to search, and press Enter to paste.</p>"
            f"<table>{rows}</table>"
            "<p>Right-click clips for more actions. Pinned and grouped clips are kept "
            "when the history fills up.</p>"
            f'<p><a href="{url}">Project page, instructions and bug reports</a></p>')


class DeleteDataDialog(QDialog):
    """Delete clips by age, like Ditto's "Delete Clip Data"."""

    def __init__(self, store: Storage, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Delete clip data")
        self.setMinimumWidth(380)

        self.older = QRadioButton("Clips not used in the last")
        self.days = QSpinBox(minimum=1, maximum=3650, value=30, suffix=" days")
        self.everything = QRadioButton("All clips")
        self.older.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.older)
        group.addButton(self.everything)
        self.include_kept = QCheckBox("Also delete pinned and grouped clips")
        self.summary = QLabel()

        row = QHBoxLayout()
        row.addWidget(self.older)
        row.addWidget(self.days)
        row.addStretch()
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.delete_btn = self.buttons.addButton("Delete", QDialogButtonBox.ButtonRole.AcceptRole)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addLayout(row)
        lay.addWidget(self.everything)
        lay.addSpacing(6)
        lay.addWidget(self.include_kept)
        lay.addSpacing(6)
        lay.addWidget(self.summary)
        lay.addWidget(self.buttons)

        for signal in (self.older.toggled, self.include_kept.toggled):
            signal.connect(self._update)
        self.days.valueChanged.connect(self._update)
        self._update()

    def choice(self) -> dict:
        return {"older_than_days": self.days.value() if self.older.isChecked() else None,
                "include_kept": self.include_kept.isChecked()}

    def _update(self, *_):
        self.days.setEnabled(self.older.isChecked())
        n = self.store.count_matching(**self.choice())
        self.summary.setText("Nothing to delete." if n == 0 else
                             f"{n} clip{'s' if n != 1 else ''} will be deleted. This can't be undone.")
        self.delete_btn.setEnabled(n > 0)
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
