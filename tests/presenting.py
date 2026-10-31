"""Driving a Presenter in tests: the startup path, waits on what the Audience reports, real key delivery, and a
test-side Audience that speaks the wire. Shared by the qt and e2e levels."""

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"  # never a window on the screen; set before Qt starts

import signal

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from manim_presentations import presenter
from manim_presentations import protocol as p
from manim_presentations.deck import Deck

LAUNCH_MS = 20_000  # a launched Audience's first report: its ~1 s start (PySide import) with a loaded machine's margin
WAIT_MS = 5000  # a message between live processes
QUIET_MS = 300  # long enough for a message that should not come to arrive
BEATS = ("title-card", "the-idea", "working-card", "build-up", "keeps-going")


@pytest.fixture
def launches(monkeypatch):
    """Every Audience launch any Presenter makes, counted."""
    count = []
    launch = presenter.Link.launch

    def counted(self):
        count.append(1)
        launch(self)

    monkeypatch.setattr(presenter.Link, "launch", counted)
    return count


@pytest.fixture
def open_(qtbot, qapp):
    """Factory: a Presenter on `root` through the one startup path; on teardown its Audience is gone."""
    windows = []

    def make(root, start=None):
        window = presenter.open_presenter(root, start)
        qtbot.addWidget(window)
        windows.append(window)
        return window

    yield make
    for window in windows:
        qapp.removeEventFilter(window)
        window.link.close()
        if window.link.pid is not None:
            os.kill(window.link.pid, signal.SIGKILL)
            os.waitpid(window.link.pid, 0)
            window.link.pid = None  # reaped here: the Link must not reap it again


def now_is(window, position, state=None):
    def check():
        now = window.now
        return now is not None and now.position == position and (state is None or getattr(now, "state", None) == state)

    return check


def red(window):
    return window.status.styleSheet().count("#c62828") == 1


def press(window, key, repeat=False):
    if repeat:
        event = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, "", True)
        QApplication.sendEvent(window.windowHandle(), event)
    else:
        QTest.keyClick(window.windowHandle(), key)  # through the window, as a real press arrives


class FakeAudience:
    """A test-side Audience: listens on the talk's socket, records what the Presenter sends, says what it is told."""

    def __init__(self, qtbot, root):
        self.qtbot, self.got, self.buffer, self.read = qtbot, [], b"", 0
        self.client: QLocalSocket | None = None
        self.name = presenter.socket_path(root)
        QLocalServer.removeServer(self.name)
        self.server = QLocalServer()
        assert self.server.listen(self.name)
        self.server.newConnection.connect(self._connected)

    def _connected(self):
        self.client = self.server.nextPendingConnection()
        self.client.readyRead.connect(self._read)

    def _read(self):
        assert self.client is not None
        self.buffer += bytes(self.client.readAll().data())
        *lines, self.buffer = self.buffer.split(b"\n")
        for line in lines:
            message = p.to_audience(line)
            self.got.append(message)
            if isinstance(message, p.Quit):  # as the real Audience does: Quit closes its window, which says Closed
                self.client.write(p.encode(p.Closed()))
                self.client.flush()

    def say(self, message_or_bytes):
        self.qtbot.waitUntil(lambda: self.client is not None, timeout=WAIT_MS)
        data = message_or_bytes if isinstance(message_or_bytes, bytes) else p.encode(message_or_bytes)
        assert self.client is not None
        self.client.write(data)
        self.client.flush()

    def hello(self, last=None):
        self.say(p.Hello(last=last, protocol=p.AUDIENCE_CODE))

    def drop(self):
        assert self.client is not None
        self.client.disconnectFromServer()
        self.server.close()

    def next(self):
        """The next message not yet read, however early it arrived."""
        self.qtbot.waitUntil(lambda: len(self.got) > self.read, timeout=WAIT_MS)
        self.read += 1
        return self.got[self.read - 1]


def clip(root, slug):
    return str(next(b.clip for b in Deck.open(root).beats if b.slug == slug))
