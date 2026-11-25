import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp()
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from clipdeck.qt import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app
    # Delete leftover windows while Qt is still running; otherwise Python may free
    # them after Qt has shut down, which can crash the test process on exit.
    from clipdeck.qt import QEvent
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    app.processEvents()


@pytest.fixture
def store(tmp_path):
    from clipdeck.storage import Storage
    return Storage(tmp_path / "clips.db")


def run_loop(ms):
    from clipdeck.qt import QEventLoop, QTimer
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()
