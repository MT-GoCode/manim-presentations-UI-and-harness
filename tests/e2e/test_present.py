"""Presenting live: the real Presenter and the real Audience through a whole talk, rebuilds adopted while presenting,
one Presenter per talk, and closing by cause through `bin/mpres`, the path an agent uses."""

import os
import shutil
import signal
import subprocess
import threading
import time

import pytest
from conftest import REPO, SUBPROCESS_TIMEOUT, TEST_WORKERS, mpres
from presenting import (
    BEATS,
    LAUNCH_MS,
    QUIET_MS,
    WAIT_MS,
    FakeAudience,
    build_once,
    copy_built,
    now_is,
    open_,
    press,
)
from PySide6.QtCore import Qt

from manim_presentations import presenter
from manim_presentations import protocol as p
from manim_presentations.deck import Deck, Layout

__all__ = ["open_"]  # a fixture, used by name

TALK = (*BEATS, "wrap-up")
LOG = REPO / "test-results" / "present-e2e.log"
SHOT = REPO / "test-results" / "presenter.png"  # the Presenter View at the end of the walk, offscreen


@pytest.fixture(scope="session")
def built(tmp_path_factory, warm_cache):
    return build_once(tmp_path_factory, warm_cache, "after-loop")


@pytest.fixture
def talk(built, tmp_path):
    return copy_built(built, tmp_path)


def edit(path, old, new):
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new))


def build(root):
    r = mpres("build", str(root), "--workers", str(TEST_WORKERS))
    assert r.returncode == 0, r.stdout + r.stderr


def settled(qtbot, window, root):
    """Until the Presenter has adopted the build now committed."""
    qtbot.waitUntil(lambda: window.deck.build_id == Layout(root).build_id(), timeout=WAIT_MS)


def kind(slug):
    return "looping" if slug == "keeps-going" else "held"


def test_every_key_through_the_whole_talk(talk, open_, qtbot):
    """↓ through every beat, then ↑ into the loop, Next out of the running loop, and R on a loop and on a beat;
    after each key, what the Audience reports. The log is the stratum's human-verifiable result."""
    window = open_(talk)
    log = []

    def expect(position, state=None):
        qtbot.waitUntil(now_is(window, position, state), timeout=LAUNCH_MS if not log else WAIT_MS)
        log.append(f"{window.position!r} -> {window.now!r}")

    expect(p.Before())
    for slug in TALK:
        press(window, Qt.Key.Key_Down)
        expect(p.At(slug=slug), kind(slug))
    press(window, Qt.Key.Key_Up)
    expect(p.At(slug="keeps-going"), "looping")
    press(window, Qt.Key.Key_R)
    expect(p.At(slug="keeps-going"), "looping")
    press(window, Qt.Key.Key_Down)  # out of the running loop at once
    qtbot.waitUntil(now_is(window, p.At(slug="wrap-up"), "playing"), timeout=WAIT_MS)
    assert window.now.pts == 0.0
    expect(p.At(slug="wrap-up"), "held")
    press(window, Qt.Key.Key_R)
    qtbot.waitUntil(now_is(window, p.At(slug="wrap-up"), "playing"), timeout=WAIT_MS)
    expect(p.At(slug="wrap-up"), "held")
    LOG.parent.mkdir(exist_ok=True)
    LOG.write_text("\n".join(log) + "\n")
    window.resize(1728, 1117)  # a 16-inch MacBook Pro's default scaled screen: what Minh presents on
    assert window.grab().save(str(SHOT))


# --- rebuilds while presenting ---
def commit_from(root, other):
    """Commit `other`'s build into `root` as a build would: clips and stills first, the index last (atomically)."""
    build_dir, other_build = Layout(root).build, Layout(other).build
    for path in other_build.rglob("*"):
        rel = path.relative_to(other_build)
        if path.is_file() and rel.parts[0] in ("clips", "stills"):
            (build_dir / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, build_dir / rel)
    for rel in ("chapters", "helpers"):
        shutil.copytree(other / rel, root / rel, dirs_exist_ok=True)
    shutil.copy2(other_build / "index.json", build_dir / ".incoming.json")
    os.replace(build_dir / ".incoming.json", build_dir / "index.json")


@pytest.fixture
def rebuilt(talk, tmp_path):
    """Factory: a copy of `talk`, edited by `change`, built."""

    def make(change, name="other"):
        other = tmp_path / name / talk.name
        shutil.copytree(talk, other, ignore=shutil.ignore_patterns(".presenter*", ".media"))
        change(other)
        build(other)
        return other

    return make


def sends(window, monkeypatch):
    sent = []
    send = window.link.send
    monkeypatch.setattr(window.link, "send", lambda m: (sent.append(m), send(m)))
    return sent


def test_a_rebuild_that_keeps_the_playing_clip_leaves_the_audience_alone(talk, open_, qtbot, rebuilt, monkeypatch):
    other = rebuilt(lambda r: edit(r / "chapters" / "opening.py", "One idea per beat", "One idea per click"))
    window = open_(talk)
    qtbot.waitUntil(now_is(window, p.Before()), timeout=LAUNCH_MS)
    window.go(p.At(slug="build-up"), "play")
    qtbot.waitUntil(now_is(window, p.At(slug="build-up"), "playing"), timeout=WAIT_MS)
    sent = sends(window, monkeypatch)
    commit_from(talk, other)
    settled(qtbot, window, talk)
    assert window.now.state == "playing"  # the swap landed mid-play
    qtbot.waitUntil(now_is(window, p.At(slug="build-up"), "held"), timeout=WAIT_MS)  # it finishes on its own
    assert sent == []


def test_a_rebuild_that_changes_the_current_beat_shows_its_new_held_state(talk, open_, qtbot, rebuilt):
    other = rebuilt(lambda r: edit(r / "chapters" / "working.py", "color=YELLOW", "color=GREEN"))
    window = open_(talk)
    qtbot.waitUntil(now_is(window, p.Before()), timeout=LAUNCH_MS)
    window.go(p.At(slug="build-up"), "show")
    qtbot.waitUntil(now_is(window, p.At(slug="build-up"), "held"), timeout=WAIT_MS)
    old = window.now.clip
    commit_from(talk, other)
    settled(qtbot, window, talk)
    qtbot.waitUntil(lambda: window.now is not None and window.now.clip != old, timeout=WAIT_MS)
    assert window.now == p.NowAt(
        position=p.At(slug="build-up"), clip=window.clip_of(p.At(slug="build-up")), state="held", pts=window.now.pts
    )


def test_a_rebuild_without_the_current_beat_moves_back_and_says_so(talk, open_, qtbot, rebuilt):
    def drop_the_idea(r):
        edit(r / "script.md", "## the-idea: The idea\n", "")
        edit(r / "script.md", "One idea per beat. The title stays put while the picture changes.\n\n", "")
        edit(r / "script.md", "> Pause here; let the dots settle before you click.\n\n", "")
        edit(r / "chapters" / "opening.py", '    talk.beat("the-idea")\n', "")

    other = rebuilt(drop_the_idea)
    window = open_(talk)
    qtbot.waitUntil(now_is(window, p.Before()), timeout=LAUNCH_MS)
    window.go(p.At(slug="the-idea"), "show")
    qtbot.waitUntil(now_is(window, p.At(slug="the-idea"), "held"), timeout=WAIT_MS)
    shutil.copy2(other / "script.md", talk / "script.md")
    commit_from(talk, other)
    settled(qtbot, window, talk)
    assert window.position == p.At(slug="title-card")
    assert "beat the-idea was removed by the rebuild; now at title-card" in window.status.text()
    qtbot.waitUntil(now_is(window, p.At(slug="title-card"), "held"), timeout=WAIT_MS)  # and the Audience shows it


def test_a_build_committed_while_the_last_one_opens_is_adopted(talk, open_, qtbot, rebuilt, monkeypatch):
    """The folder event for build C arrives while B's deck is still opening, and is dropped then; the Presenter
    looks again once B is adopted. A scripted Audience: a real one logs into build/, and that event would make the
    Presenter look again by luck."""
    b = rebuilt(lambda r: edit(r / "chapters" / "working.py", "Circle(1.0", "Circle(1.1"), "b")
    c = rebuilt(lambda r: edit(r / "chapters" / "working.py", "Circle(1.0", "Circle(1.2"), "c")
    fake = FakeAudience(qtbot, talk)
    window = open_(talk)
    fake.hello()
    fake.next()
    release = threading.Event()
    opening = []
    open_deck = presenter.open_deck

    def slow(root):
        deck = open_deck(root)  # B, read now; C commits while this opening is held
        opening.append(1)
        release.wait()
        return deck

    monkeypatch.setattr(presenter, "open_deck", slow)
    # Opening a deck rewrites the pins in build/, and that event would trigger a look by luck: take it away.
    monkeypatch.setattr(Layout, "write_pins", lambda self, shas: None)
    commit_from(talk, b)
    qtbot.waitUntil(lambda: opening == [1], timeout=WAIT_MS)
    commit_from(talk, c)
    qtbot.wait(QUIET_MS)  # C's folder event lands while B is opening
    release.set()
    settled(qtbot, window, talk)
    assert window.deck.build_id == Layout(c).build_id()


def test_a_chapter_edited_mid_build_is_adopted_as_stale(talk, open_, qtbot):
    window = open_(talk)
    qtbot.waitUntil(now_is(window, p.Before()), timeout=LAUNCH_MS)
    cmd = [str(REPO / "bin" / "mpres"), "build", str(talk), "--workers", str(TEST_WORKERS)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    assert proc.stdout is not None
    for line in proc.stdout:  # the build's own phase line: its snapshot is taken
        if line.startswith("snapshot:"):
            edit(talk / "chapters" / "opening.py", "One idea per beat", "One idea per breath")
            break
    proc.communicate(timeout=SUBPROCESS_TIMEOUT)
    assert proc.returncode == 0
    settled(qtbot, window, talk)
    qtbot.waitUntil(lambda: "changed since the build: chapters/opening.py" in window.status.text(), timeout=WAIT_MS)


def test_the_clip_on_screen_survives_two_builds(talk, open_, qtbot):
    """The Presenter pins its deck's clips; the GUI thread is blocked during both builds, so the Audience keeps
    showing the first clip while the builds collect what is not pinned."""
    window = open_(talk)
    qtbot.waitUntil(now_is(window, p.Before()), timeout=LAUNCH_MS)
    window.go(p.At(slug="build-up"), "show")
    qtbot.waitUntil(now_is(window, p.At(slug="build-up"), "held"), timeout=WAIT_MS)
    shown = window.now.clip
    for old, new in (("Circle(1.0", "Circle(1.1"), ("Circle(1.1", "Circle(1.2")):  # each build replaces the shown clip
        edit(talk / "chapters" / "working.py", old, new)
        build(talk)
    assert os.path.exists(shown)
    settled(qtbot, window, talk)
    qtbot.waitUntil(now_is(window, p.At(slug="build-up"), "held"), timeout=WAIT_MS)
    assert window.now.clip == window.clip_of(p.At(slug="build-up"))


def test_a_reconnect_adopts_a_stale_deck_in_amber(talk, open_, qtbot):
    """A restarted Presenter after unbuilt edits: the live Audience is a reconnect, which never refuses."""
    first = open_(talk)
    qtbot.waitUntil(now_is(first, p.Before()), timeout=LAUNCH_MS)
    first.go(p.At(slug="build-up"), "show")
    qtbot.waitUntil(now_is(first, p.At(slug="build-up"), "held"), timeout=WAIT_MS)
    # This Presenter dies as a killed process does: its socket and lock close, nothing is said, nothing is killed.
    first.link.told, first.link.pid = "quit", None
    first.link.socket.abort()
    os.close(first.lock_fd)
    first.lock_fd = -1
    edit(talk / "chapters" / "opening.py", "One idea per beat", "One idea per minute")
    second = open_(talk)
    qtbot.waitUntil(lambda: second.position == p.At(slug="build-up"), timeout=WAIT_MS)
    assert "changed since the build: chapters/opening.py" in second.status.text()


# --- one Presenter per talk, and closing by cause, through bin/mpres ---
class Present:
    """`bin/mpres present` as an agent runs it: `uv run` between the caller and the Python Presenter."""

    def __init__(self, talk):
        env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
        cmd = [str(REPO / "bin" / "mpres"), "present", str(talk)]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            if line.startswith("present: Audience connected"):
                break
        else:
            raise AssertionError(f"present exited {self.proc.wait()} before the Audience connected")
        self.python = int(subprocess.check_output(["pgrep", "-P", str(self.proc.pid)], text=True).split()[0])

    def signal(self, number):
        os.kill(self.proc.pid, number)


def audiences(talk):
    found = subprocess.run(["pgrep", "-f", presenter.socket_path(talk)], capture_output=True, text=True).stdout
    return [int(pid) for pid in found.split()]


def gone(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


def wait(condition, ms):
    deadline = time.monotonic() + ms / 1000
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.05)


@pytest.fixture
def presented(talk):
    """The talk presented through bin/mpres; on teardown every Presenter and Audience of it is gone."""
    started = []

    def start():
        started.append(Present(talk))
        return started[-1]

    yield start
    for run in started:
        run.proc.kill()
        run.proc.wait()
        if not gone(run.python):
            os.kill(run.python, signal.SIGKILL)
    for pid in audiences(talk):
        os.kill(pid, signal.SIGKILL)


def test_sigterm_closes_presenter_and_audience(talk, presented):
    run = presented()
    [audience] = audiences(talk)
    run.signal(signal.SIGTERM)
    run.proc.wait(WAIT_MS / 1000)
    wait(lambda: gone(audience) and gone(run.python), WAIT_MS)


@pytest.mark.parametrize("accident", ["SIGHUP", "SIGKILL to Python"])
def test_an_accident_leaves_the_audience_up_and_a_rerun_reconnects(talk, presented, accident):
    run = presented()
    [audience] = audiences(talk)
    if accident == "SIGHUP":
        run.signal(signal.SIGHUP)
    else:
        os.kill(run.python, signal.SIGKILL)
    wait(lambda: gone(run.python), WAIT_MS)
    time.sleep(QUIET_MS / 1000)  # a Quit, if one was sent, has reached the Audience by now
    assert audiences(talk) == [audience]
    presented()  # connects to the same Audience: no second one is launched
    assert audiences(talk) == [audience]


def test_a_killed_uv_takes_the_presenter_with_it(talk, presented):
    run = presented()
    [audience] = audiences(talk)
    run.signal(signal.SIGKILL)  # uv cannot forward this; the Presenter's parent-death watch notices
    wait(lambda: gone(run.python), 2 * presenter.PARENT_WATCH_MS + WAIT_MS)
    assert audiences(talk) == [audience]
    presented()  # the lock went with the Presenter: no exit 3


def test_a_second_present_exits_3_even_after_a_pin_rewrite(talk, presented):
    presented()
    pins = Layout(talk).build / ".presenter.json"
    before = pins.read_text()
    edit(talk / "chapters" / "working.py", "color=YELLOW", "color=GREEN")
    build(talk)  # the live Presenter adopts it and rewrites its pins
    wait(lambda: pins.read_text() != before, WAIT_MS)
    r = mpres("present", str(talk))
    assert r.returncode == 3 and "already being presented" in r.stderr
    assert Deck.open(talk).build_id == Layout(talk).build_id()
