"""The Presenter View on a built talk: navigation and keys, the script editor, and the Audience kept alive by cause.
The Audience is either the real subprocess or a test-side server speaking the wire (to script what it reports)."""

import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from conftest import REPO, mpres
from presenting import (
    BEATS,
    LAUNCH_MS,
    QUIET_MS,
    WAIT_MS,
    FakeAudience,
    clip,
    launches,
    now_is,
    open_,
    press,
    red,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtTest import QTest

from manim_presentations import audience, presenter
from manim_presentations import protocol as p
from manim_presentations.deck import Deck, Layout

__all__ = ["launches", "open_"]  # fixtures, used by name


@pytest.fixture
def talk(prebuilt):
    return prebuilt("hello")


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


def test_keys_on_the_audience_window_move_the_presenter_once(talk, open_, qtbot, qapp):
    """The Audience's window class in this process, on the Presenter's real socket; its forwarder is installed
    last, so it sees the Audience's key presses first, as it would in its own process."""
    view = audience.Audience(presenter.socket_path(talk), "T")
    qtbot.addWidget(view)
    view.place()
    window = open_(talk)
    qtbot.waitUntil(now_is(window, p.Before()), timeout=WAIT_MS)
    forwarder = audience.KeyForwarder(view)
    qapp.installEventFilter(forwarder)
    try:
        press(view, Qt.Key.Key_Down)
        qtbot.waitUntil(now_is(window, p.At(slug="title-card"), "held"), timeout=WAIT_MS)
        press(view, Qt.Key.Key_Down, repeat=True)  # a held key on the Audience: one beat, not two
        qtbot.wait(QUIET_MS)
    finally:
        qapp.removeEventFilter(forwarder)
    assert window.position == p.At(slug="title-card")


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
    open_(talk, "build-up")
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
    os.kill(first, signal.SIGKILL)
    qtbot.waitUntil(lambda: "re-share" in window.status.text(), timeout=WAIT_MS)
    assert window.now is None  # forgotten at the drop, ~1 s before the new Audience can say anything
    qtbot.waitUntil(now_is(window, p.At(slug="keeps-going"), "looping"), timeout=LAUNCH_MS)
    assert launches == [1, 1] and window.link.pid != first
    with pytest.raises(ChildProcessError):
        os.waitpid(first, os.WNOHANG)  # reaped before the relaunch
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
    assert pid is not None
    window.close()
    deadline = time.monotonic() + LAUNCH_MS / 1000
    while os.waitpid(pid, os.WNOHANG)[0] != pid:  # a hang would hide an Audience that stays up
        assert time.monotonic() < deadline, "the Audience did not quit"
        time.sleep(0.05)
    window.link.pid = None
    probe = QLocalSocket()
    probe.connectToServer(presenter.socket_path(talk))
    assert not probe.waitForConnected(WAIT_MS)


# --- what the Presenter shows: the status line, the stills, the editor's fit ---
def test_the_status_line_shows_only_what_the_audience_said_about_this_beat(talk, open_, qtbot):
    fake = FakeAudience(qtbot, talk)
    window = open_(talk)
    fake.hello()
    fake.next()
    fake.say(p.NowCovered(position=p.Before(), clip=clip(talk, "title-card")))
    qtbot.waitUntil(lambda: "title-card covered" in window.status.text(), timeout=WAIT_MS)
    press(window, Qt.Key.Key_Down)
    assert "Audience: waiting · beat 1/5" in window.status.text()
    fake.say(p.NowCovered(position=p.Before(), clip=clip(talk, "title-card")))  # late, about the previous position
    qtbot.wait(QUIET_MS)
    assert "Audience: waiting" in window.status.text() and window.now is None


def test_previous_shows_the_beat_as_last_seen_and_never_replays_it(talk, open_, qtbot):
    fake = FakeAudience(qtbot, talk)
    window = open_(talk)
    fake.hello()
    fake.next()
    for _ in range(2):
        press(window, Qt.Key.Key_Down)
        fake.next()
    press(window, Qt.Key.Key_Up)
    assert fake.next() == p.Hold(position=p.At(slug="title-card"), clip=clip(talk, "title-card"))
    press(window, Qt.Key.Key_Up)
    assert fake.next() == p.Cover(position=p.Before(), clip=clip(talk, "title-card"))


def test_the_stills_show_now_and_next(talk, open_, qtbot):
    window = open_(talk)
    beats = {b.slug: b for b in Deck.open(talk).beats}

    def same(still, png):
        return still.source.toImage() == QPixmap(str(png)).toImage()

    assert same(window.now_still, beats["title-card"].first_png) and same(
        window.next_still, beats["title-card"].last_png
    )
    window.go(p.At(slug="the-idea"), "show")
    assert same(window.now_still, beats["the-idea"].last_png) and same(
        window.next_still, beats["working-card"].last_png
    )
    window.go(p.At(slug="keeps-going"), "show")
    assert same(window.now_still, beats["keeps-going"].last_png) and window.next_still.source.isNull()
    assert window.next_label.text() == "Next: end of talk"
    window.go(p.Before(), "show")
    assert window.next_label.text() == "Next"


def test_the_editor_fits_a_short_beat_and_floors_a_long_one(talk, open_, qtbot):
    window = open_(talk)
    window.resize(1600, 1000)
    window.go(p.At(slug="the-idea"), "show")
    window.fit()
    short = window.editor.document().defaultFont().pointSize()
    assert short > presenter.EDITOR_FLOOR_PT and "beat text overflows" not in window.status.text()
    window.editor.setPlainText("A long beat.\n" * 300)  # ~7500 px at the 16 pt floor, in a 1000 px window
    qtbot.waitUntil(lambda: "beat text overflows" in window.status.text(), timeout=WAIT_MS)
    assert window.editor.document().defaultFont().pointSize() == presenter.EDITOR_FLOOR_PT
    assert window.editor.verticalScrollBar().maximum() > 0  # below the floor, it scrolls


def test_the_clock_counts_from_the_first_next(talk, open_, qtbot, monkeypatch):
    window = open_(talk)
    qtbot.waitUntil(now_is(window, p.Before()), timeout=LAUNCH_MS)
    assert window.status.text().endswith("0:00")
    press(window, Qt.Key.Key_Down)
    later = time.monotonic() + 75
    monkeypatch.setattr(presenter.time, "monotonic", lambda: later)
    window.refresh_status()
    assert window.status.text().endswith("1:15")


def test_from_shows_its_position_before_the_audience_answers(talk, open_):
    window = open_(talk, "build-up")
    assert window.position == p.At(slug="working-card")


def test_each_launch_truncates_the_audience_log(talk, open_, qtbot):
    log = Layout(talk).audience_log
    log.write_text("a previous launch's output\n")
    window = open_(talk)
    qtbot.waitUntil(now_is(window, p.Before()), timeout=LAUNCH_MS)
    assert "a previous launch's output" not in log.read_text()


def test_a_deleted_script_turns_red(talk, open_, qtbot):
    window = open_(talk)
    (talk / "script.md").unlink()
    qtbot.waitUntil(lambda: "script.md is missing" in window.status.text(), timeout=WAIT_MS)
    assert red(window)


def test_closing_before_the_audience_listens_leaves_no_audience(talk, open_, qtbot):
    window = open_(talk)
    pid = window.link.pid
    assert pid is not None and window.link.socket.state() != QLocalSocket.LocalSocketState.ConnectedState
    window.close()  # within its ~1 s start: Quit cannot reach it yet
    assert window.link.pid is None
    with pytest.raises(ChildProcessError):
        os.waitpid(pid, os.WNOHANG)  # terminated and reaped, not left listening


def test_an_older_audience_is_quit_and_relaunched(talk, open_, qtbot, launches, tmp_path):
    """A real Audience whose code differs (one comment), as after a `git pull`: it answers Quit with Closed, and the
    Presenter still relaunches it, because its own Quit is the cause."""
    pkg = tmp_path / "engine" / "manim_presentations"
    shutil.copytree(REPO / "manim_presentations", pkg, ignore=shutil.ignore_patterns("__pycache__"))
    (pkg / "audience.py").write_text((pkg / "audience.py").read_text() + "\n# another version\n")
    env = {**os.environ, "PYTHONPATH": str(pkg.parent), "QT_QPA_PLATFORM": "offscreen"}
    name = presenter.socket_path(talk)
    older = subprocess.Popen([sys.executable, "-P", "-m", "manim_presentations.audience", name, "T"], env=env)
    try:
        probe = QLocalSocket()
        qtbot.waitUntil(lambda: (probe.connectToServer(name), probe.waitForConnected(50))[1], timeout=LAUNCH_MS)
        probe.abort()
        window = open_(talk)
        qtbot.waitUntil(lambda: older.poll() == 0, timeout=LAUNCH_MS)  # it quit (the Qt loop keeps running)
        qtbot.waitUntil(now_is(window, p.Before()), timeout=LAUNCH_MS)
        assert launches == [1] and "re-share" in window.status.text()
    finally:
        older.kill()


def test_a_failed_clip_is_red_until_the_audience_shows_one(talk, open_, qtbot):
    fake = FakeAudience(qtbot, talk)
    window = open_(talk)
    fake.hello()
    cover = fake.next()
    fake.say(p.Failed(position=p.Before(), clip=cover.clip, reason="decoder said no"))
    qtbot.waitUntil(lambda: "could not play" in window.status.text(), timeout=WAIT_MS)
    assert red(window) and Path(cover.clip).name in window.status.text() and "decoder said no" in window.status.text()
    fake.say(p.NowCovered(position=p.Before(), clip=cover.clip))
    qtbot.waitUntil(lambda: not red(window), timeout=WAIT_MS)


def test_a_report_about_another_clip_is_not_shown(talk, open_, qtbot):
    """The same position with an older clip (a report from before a hot-swap) does not describe the screen."""
    fake = FakeAudience(qtbot, talk)
    window = open_(talk)
    fake.hello()
    fake.next()
    fake.say(p.NowCovered(position=p.Before(), clip="/an/older/clip.mp4"))
    qtbot.wait(QUIET_MS)
    assert window.now is None and "Audience: waiting" in window.status.text()


def test_a_word_wider_than_the_editor_shrinks_the_text(talk, open_, qtbot):
    """Through a window resize, as live: the refit must read the editor's new size, not the one before the resize."""
    window = open_(talk)
    window.go(p.At(slug="the-idea"), "show")
    window.editor.setPlainText("Antidisestablishmentarianism")
    window.showNormal()
    window.resize(1728, 1117)
    qtbot.wait(QUIET_MS)
    window.fit()  # fitted to the wide editor
    wide = window.editor.document().idealWidth()
    window.resize(1400, 1117)  # narrower, still above the floor for this word: it must shrink to fit again
    qtbot.waitUntil(lambda: window.editor.viewport().width() < wide, timeout=WAIT_MS)  # the old fit no longer fits

    def fits():
        return window.editor.document().idealWidth() <= window.editor.viewport().width()

    qtbot.waitUntil(fits, timeout=WAIT_MS)
    assert window.editor.horizontalScrollBar().maximum() == 0


def test_a_presenter_lock_held_briefly_is_waited_for(talk, open_):
    """GC's liveness probe holds the lock for microseconds; present waits for it instead of exiting 3."""
    fd = Layout(talk).presenter_lock()
    threading.Timer(0.2, os.close, [fd]).start()
    open_(talk)


def test_an_audience_it_launched_with_other_code_is_not_relaunched(talk, open_, qtbot, launches, monkeypatch, tmp_path):
    """The engine changed on disk under a running Presenter: every relaunch would differ again, so it stops red."""
    pkg = tmp_path / "engine" / "manim_presentations"
    shutil.copytree(REPO / "manim_presentations", pkg, ignore=shutil.ignore_patterns("__pycache__"))
    (pkg / "audience.py").write_text((pkg / "audience.py").read_text() + "\n# another version\n")
    monkeypatch.setenv("PYTHONPATH", str(pkg.parent))  # what the launched Audience imports
    window = open_(talk)
    qtbot.waitUntil(lambda: "restart mpres present" in window.status.text(), timeout=LAUNCH_MS)
    pid = window.link.pid
    assert pid is not None
    deadline = time.monotonic() + LAUNCH_MS / 1000
    while os.waitpid(pid, os.WNOHANG)[0] != pid:  # it quit
        assert time.monotonic() < deadline, "the Audience did not quit"
        time.sleep(0.05)
    window.link.pid = None
    qtbot.wait(QUIET_MS)
    assert launches == [1] and red(window)


def test_an_exception_in_a_slot_is_shown_red(talk, open_, monkeypatch):
    window = open_(talk)
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)  # restored after the test
    presenter.report_errors(window)
    sys.excepthook(KeyError, KeyError("no such beat"), None)
    assert red(window) and "KeyError: 'no such beat'" in window.status.text()


def test_an_audience_dropping_after_the_window_is_gone_reaches_nothing(talk, qtbot, qapp):
    """The Link goes with its window: a late drop must not call into deleted widgets (pytest-qt fails on any slot
    exception)."""
    window = presenter.open_presenter(talk, None)
    qtbot.waitUntil(now_is(window, p.Before()), timeout=LAUNCH_MS)
    pid, fd = window.link.pid, window.lock_fd
    assert pid is not None
    qapp.removeEventFilter(window)
    window.deleteLater()  # destroyed without closing: no Quit, the Audience is still connected
    qtbot.wait(QUIET_MS)
    os.kill(pid, signal.SIGKILL)  # its socket drops now
    os.waitpid(pid, 0)
    os.close(fd)
    qtbot.wait(QUIET_MS)


def test_moving_while_the_script_is_missing_shows_red(talk, open_, qtbot):
    """The editor loads a beat's text on every move: with script.md gone it says so instead of raising in a slot."""
    window = open_(talk)
    (talk / "script.md").unlink()
    window.go(p.At(slug="the-idea"), "show")
    assert "script.md is missing" in window.status.text() and red(window)
