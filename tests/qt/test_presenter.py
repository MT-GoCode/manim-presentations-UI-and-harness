"""The Presenter View on a built talk: navigation and keys, the script editor, and the Audience kept alive by cause.
The Audience is either the real subprocess or a test-side server speaking the wire (to script what it reports)."""

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"  # never a window on the screen; set before Qt starts

import shutil
import signal
import socket
import subprocess
import sys

import pytest
from conftest import REPO, TEST_WORKERS, copy_talk, mpres
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from manim_presentations import presenter
from manim_presentations import protocol as p
from manim_presentations.deck import Deck, Layout

LAUNCH_MS = 20_000  # a launched Audience's first report: its ~1 s start (PySide import) with a loaded machine's margin
WAIT_MS = 5000  # a message between live processes
QUIET_MS = 300  # long enough for a message that should not come to arrive
BEATS = ("title-card", "the-idea", "working-card", "build-up", "keeps-going")


@pytest.fixture(scope="session")
def built(tmp_path_factory, warm_cache):
    root = copy_talk(tmp_path_factory.mktemp("built"), "hello")
    shutil.copytree(warm_cache, root / "build" / ".cache", ignore=shutil.ignore_patterns(".complete"))
    r = mpres("build", str(root), "--workers", str(TEST_WORKERS))
    assert r.returncode == 0, r.stdout + r.stderr
    return root


@pytest.fixture
def talk(built, tmp_path):
    root = tmp_path / built.name
    shutil.copytree(built, root, ignore=shutil.ignore_patterns(".cache", ".media"))
    return root


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
        window = presenter.open_presenter(Deck.open(root), start)
        qtbot.addWidget(window)
        windows.append(window)
        return window

    yield make
    for window in windows:
        qapp.removeEventFilter(window)
        window.link.retry.stop()
        window.link.quit()
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
        self.qtbot, self.got, self.buffer = qtbot, [], b""
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
        self.got += [p.to_audience(line) for line in lines]

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
        n = len(self.got)
        self.qtbot.waitUntil(lambda: len(self.got) > n, timeout=WAIT_MS)
        return self.got[n]


def clip(root, slug):
    return str(next(b.clip for b in Deck.open(root).beats if b.slug == slug))


# --- startup, through the CLI ---
def test_a_fresh_start_refuses_a_stale_build_and_launches_nothing(talk):
    chapter = talk / "chapters" / "opening.py"
    chapter.write_text(chapter.read_text() + "\n")
    r = subprocess.run(
        [sys.executable, "-P", "-m", "manim_presentations.cli", "present", str(talk)],
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
    )
    assert r.returncode == 1 and "chapters/opening.py" in r.stderr and "run: mpres build" in r.stderr
    assert not Layout(talk).audience_log.exists()


def test_an_unknown_from_beat_is_refused_with_the_beats(talk):
    r = mpres("present", str(talk), "--from", "nope")
    assert r.returncode == 2 and f"the beats are: {' '.join(BEATS)}" in r.stderr


def test_a_stale_socket_file_is_cleared_and_the_audience_starts(talk, open_, qtbot):
    with socket.socket(socket.AF_UNIX) as s:
        s.bind(presenter.socket_path(talk))  # a crashed Audience's socket file: present, nobody listening
    window = open_(talk)
    qtbot.waitUntil(now_is(window, p.Before()), timeout=LAUNCH_MS)
    assert window.now == p.NowCovered(position=p.Before(), clip=clip(talk, "title-card"))


def test_a_fatal_audience_shows_red_and_is_not_relaunched(talk, open_, qtbot, tmp_path, launches, monkeypatch):
    pkg = tmp_path / "engine" / "manim_presentations"
    shutil.copytree(REPO / "manim_presentations", pkg, ignore=shutil.ignore_patterns("__pycache__"))
    source = (pkg / "audience.py").read_text()
    (pkg / "audience.py").write_text(source.replace('REQUIRED_BACKEND = "ffmpeg"', 'REQUIRED_BACKEND = "nosuch"'))
    monkeypatch.setenv("PYTHONPATH", str(pkg.parent))  # the launched Audience imports the copy
    window = open_(talk)
    qtbot.waitUntil(lambda: "Audience failed: media backend" in window.status.text(), timeout=LAUNCH_MS)
    qtbot.wait(QUIET_MS)
    assert red(window) and launches == [1]


# --- navigation through the real Audience ---
def test_each_press_moves_one_beat_and_the_audience_follows(talk, open_, qtbot):
    window = open_(talk)
    qtbot.waitUntil(now_is(window, p.Before()), timeout=LAUNCH_MS)
    press(window, Qt.Key.Key_Down)
    qtbot.waitUntil(now_is(window, p.At(slug="title-card"), "held"), timeout=WAIT_MS)
    press(window, Qt.Key.Key_Down, repeat=True)  # a held key's repeats move nothing
    press(window, Qt.Key.Key_PageDown)
    qtbot.waitUntil(now_is(window, p.At(slug="the-idea"), "held"), timeout=WAIT_MS)
    press(window, Qt.Key.Key_Up)
    qtbot.waitUntil(now_is(window, p.At(slug="title-card"), "held"), timeout=WAIT_MS)
    press(window, Qt.Key.Key_R)
    qtbot.waitUntil(now_is(window, p.At(slug="title-card"), "playing"), timeout=WAIT_MS)
    assert window.position == p.At(slug="title-card")


def test_a_chord_is_not_navigation(talk, open_, qtbot):
    window = open_(talk)
    qtbot.waitUntil(now_is(window, p.Before()), timeout=LAUNCH_MS)
    QTest.keyClick(window.windowHandle(), Qt.Key.Key_Down, Qt.KeyboardModifier.ControlModifier)  # Cmd+↓
    qtbot.wait(QUIET_MS)
    assert window.position == p.Before()


def test_previous_at_the_start_flashes_red_and_stays(talk, open_, qtbot):
    window = open_(talk)
    qtbot.waitUntil(now_is(window, p.Before()), timeout=LAUNCH_MS)
    press(window, Qt.Key.Key_Up)
    assert window.position == p.Before() and "#c62828" in window.buttons["previous"].styleSheet()


def test_a_timeline_click_jumps_and_keeps_the_keys(talk, open_, qtbot):
    window = open_(talk)
    qtbot.waitUntil(now_is(window, p.Before()), timeout=LAUNCH_MS)
    item = window.items["build-up"]
    QTest.mouseClick(
        window.timeline.viewport(), Qt.MouseButton.LeftButton, pos=window.timeline.visualItemRect(item).center()
    )
    qtbot.waitUntil(now_is(window, p.At(slug="build-up"), "held"), timeout=WAIT_MS)
    press(window, Qt.Key.Key_Down)
    qtbot.waitUntil(now_is(window, p.At(slug="keeps-going"), "looping"), timeout=WAIT_MS)


def test_arrows_type_in_the_editor_and_page_keys_still_navigate(talk, open_, qtbot):
    window = open_(talk)
    qtbot.waitUntil(now_is(window, p.Before()), timeout=LAUNCH_MS)
    window.editor.setFocus()
    press(window, Qt.Key.Key_Down)
    qtbot.wait(QUIET_MS)
    assert window.position == p.Before()
    press(window, Qt.Key.Key_PageDown)
    qtbot.waitUntil(now_is(window, p.At(slug="title-card")), timeout=WAIT_MS)
    assert window.home.hasFocus()  # any navigation leaves the editor
    window.editor.setFocus()
    press(window, Qt.Key.Key_Escape)
    assert window.home.hasFocus()


# --- the script editor ---
def go_to_the_idea(window, qtbot):
    qtbot.waitUntil(now_is(window, p.Before()), timeout=LAUNCH_MS)
    window.go(p.At(slug="the-idea"), "show")


def test_typing_autosaves_exactly_that_beats_text(talk, open_, qtbot):
    window = open_(talk)
    go_to_the_idea(window, qtbot)
    before = (talk / "script.md").read_text()
    window.editor.setFocus()
    window.editor.moveCursor(window.editor.textCursor().MoveOperation.End)
    QTest.keyClicks(window.editor, " Smile.")
    old = "> Pause here; let the dots settle before you click."
    assert (talk / "script.md").read_text() == before.replace(old, old + " Smile.")


@pytest.mark.parametrize("how", ["in place", "atomic replace"])
def test_an_outside_edit_reloads_the_editor(talk, open_, qtbot, how):
    window = open_(talk)
    go_to_the_idea(window, qtbot)
    path = talk / "script.md"
    text = path.read_text().replace("One idea per beat.", "One idea, one beat.")
    if how == "in place":
        with path.open("w") as f:  # VS Code's default save: same inode, nothing changes in the folder
            f.write(text)
    else:
        (talk / ".script.tmp").write_text(text)
        os.replace(talk / ".script.tmp", path)
    qtbot.waitUntil(lambda: "One idea, one beat." in window.editor.toPlainText(), timeout=WAIT_MS)


def test_the_editors_own_write_is_not_reloaded(talk, open_, qtbot):
    window = open_(talk)
    go_to_the_idea(window, qtbot)
    window.editor.setFocus()
    cursor = window.editor.textCursor()
    cursor.setPosition(3)
    window.editor.setTextCursor(cursor)
    QTest.keyClicks(window.editor, "x")
    qtbot.wait(QUIET_MS)  # the watcher has seen the write by now
    assert window.editor.textCursor().position() == 4  # a reload would have reset the cursor


def test_a_heading_change_outside_turns_the_status_red(talk, open_, qtbot):
    window = open_(talk)
    go_to_the_idea(window, qtbot)
    path = talk / "script.md"
    path.write_text(path.read_text().replace("## the-idea: The idea", "## the-idea: A new idea"))
    qtbot.waitUntil(lambda: "script.md headings changed" in window.status.text(), timeout=WAIT_MS)
    assert red(window)


def test_a_refused_save_stays_red_and_blocks_reloads(talk, open_, qtbot):
    window = open_(talk)
    go_to_the_idea(window, qtbot)
    window.editor.setFocus()
    window.editor.moveCursor(window.editor.textCursor().MoveOperation.End)
    QTest.keyClick(window.editor, Qt.Key.Key_Return)  # keyClicks cannot type a newline
    QTest.keyClicks(window.editor, "## sneaky")
    assert "not saved" in window.status.text() and red(window)
    typed = window.editor.toPlainText()
    path = talk / "script.md"
    path.write_text(path.read_text().replace("One idea per beat.", "Changed outside."))
    qtbot.wait(QUIET_MS)
    assert window.editor.toPlainText() == typed  # what was typed is never overwritten


# --- the Audience by cause, with a scripted Audience ---
def test_an_audience_key_moves_the_presenter(talk, open_, qtbot):
    fake = FakeAudience(qtbot, talk)
    open_(talk)
    fake.hello()
    assert fake.next() == p.Cover(position=p.Before(), clip=clip(talk, "title-card"))
    fake.say(p.Key(action="next"))
    assert fake.next() == p.Play(position=p.At(slug="title-card"), clip=clip(talk, "title-card"))


def test_a_restarted_presenter_adopts_what_the_audience_shows(talk, open_, qtbot, launches):
    fake = FakeAudience(qtbot, talk)
    window = open_(talk)
    shown = p.NowAt(position=p.At(slug="build-up"), clip=clip(talk, "build-up"), state="held", pts=1.0)
    fake.hello(shown)
    qtbot.waitUntil(lambda: window.position == p.At(slug="build-up"), timeout=WAIT_MS)
    qtbot.wait(QUIET_MS)
    assert fake.got == [] and launches == []  # adopted as it is: nothing re-sent, nothing launched


def test_an_echo_from_another_build_is_not_adopted(talk, open_, qtbot):
    fake = FakeAudience(qtbot, talk)
    window = open_(talk)
    fake.hello(p.NowAt(position=p.At(slug="build-up"), clip="/old/clip.mp4", state="held", pts=1.0))
    assert fake.next() == p.Cover(position=p.Before(), clip=clip(talk, "title-card"))
    assert window.position == p.Before()


def test_from_wins_over_what_the_audience_shows(talk, open_, qtbot):
    fake = FakeAudience(qtbot, talk)
    open_(talk, p.before("build-up", BEATS))
    fake.hello(p.NowAt(position=p.At(slug="keeps-going"), clip=clip(talk, "keeps-going"), state="looping", pts=0.5))
    assert fake.next() == p.Hold(position=p.At(slug="working-card"), clip=clip(talk, "working-card"))


def test_a_closed_audience_waits_for_a_click_to_reopen(talk, open_, qtbot, launches):
    fake = FakeAudience(qtbot, talk)
    window = open_(talk)
    fake.hello()
    fake.next()
    fake.say(p.Closed())
    fake.drop()
    qtbot.waitUntil(lambda: "Audience closed — click to reopen" in window.status.text(), timeout=WAIT_MS)
    qtbot.wait(QUIET_MS)
    assert launches == []
    QTest.mouseClick(window.status, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(now_is(window, p.Before()), timeout=LAUNCH_MS)
    assert launches == [1] and not red(window)


def test_an_audience_of_other_code_is_quit_and_relaunched(talk, open_, qtbot, launches):
    fake = FakeAudience(qtbot, talk)
    window = open_(talk)
    fake.say(p.Hello(last=None, protocol="another version"))
    assert fake.next() == p.Quit()
    fake.drop()
    qtbot.waitUntil(now_is(window, p.Before()), timeout=LAUNCH_MS)
    assert launches == [1] and "re-share" in window.status.text()


def test_a_crashed_audience_is_relaunched_on_the_same_beat(talk, open_, qtbot, launches):
    window = open_(talk)
    qtbot.waitUntil(now_is(window, p.Before()), timeout=LAUNCH_MS)
    window.go(p.At(slug="keeps-going"), "show")
    qtbot.waitUntil(now_is(window, p.At(slug="keeps-going"), "looping"), timeout=WAIT_MS)
    first = window.link.pid
    assert first is not None
    window.now = None
    os.kill(first, signal.SIGKILL)
    qtbot.waitUntil(now_is(window, p.At(slug="keeps-going"), "looping"), timeout=LAUNCH_MS)
    assert launches == [1, 1] and window.link.pid != first
    assert "re-share the Audience View window" in window.status.text() and red(window)
    QTest.mouseClick(window.status, Qt.MouseButton.LeftButton)  # the presenter says it re-shared
    assert not red(window)


def test_a_drop_before_hello_is_a_failed_start(talk, open_, qtbot, launches):
    fake = FakeAudience(qtbot, talk)
    window = open_(talk)
    qtbot.waitUntil(lambda: fake.client is not None, timeout=WAIT_MS)
    fake.drop()
    qtbot.waitUntil(lambda: "Audience failed to start" in window.status.text(), timeout=WAIT_MS)
    assert launches == [] and red(window)


def test_closing_the_presenter_quits_the_audience(talk, open_, qtbot):
    window = open_(talk)
    qtbot.waitUntil(now_is(window, p.Before()), timeout=LAUNCH_MS)
    pid = window.link.pid
    window.close()
    assert os.waitpid(pid, 0)[0] == pid
    window.link.pid = None
    probe = QLocalSocket()
    probe.connectToServer(presenter.socket_path(talk))
    assert not probe.waitForConnected(WAIT_MS)
