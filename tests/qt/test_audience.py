"""The Audience View, driven by a scripted socket client: what the player shows for each message, as it reports it
and as its video sink presents it."""

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"  # never a window on the screen; set before Qt starts

import itertools
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
import pytest
from conftest import REPO, SUBPROCESS_TIMEOUT
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtMultimedia import QMediaPlayer, QVideoFrame
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from manim_presentations import audience, clip
from manim_presentations import protocol as p

FPS = 30
FRAMES = 30
WAIT_MS = 5000  # per expected message; P1's slowest first frame was 120 ms at 3456×2168, these clips are 480×270


@pytest.fixture(scope="module")
def clips(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Clips encoded the way builds encode them; frame i is the flat gray 8·i, so a presented frame names its index."""
    out = {}
    for name in ("a", "b"):
        path = out[name] = tmp_path_factory.mktemp("clips") / f"{name}.mp4"
        with av.open(str(path), "w") as f:
            stream = f.add_stream(clip.OUTPUT["video_codec"], rate=FPS, options=clip.ENCODE)
            stream.width, stream.height, stream.pix_fmt = 480, 270, clip.OUTPUT["pixel_format"]
            stream.time_base = Fraction(1, FPS)
            for i in range(FRAMES):
                frame = av.VideoFrame.from_ndarray(np.full((270, 480, 3), 8 * i, np.uint8), format="rgb24")
                frame.pts = i
                f.mux(stream.encode(frame))
            f.mux(stream.encode())
    return out


def socket_path() -> str:
    """Absolute, so QLocalServer listens exactly there; under /tmp to fit the 104-byte sun_path."""
    return str(Path(tempfile.mkdtemp(prefix="mpres-", dir="/tmp")) / "audience")


def index_of(frame: QVideoFrame) -> int:
    image = frame.toImage()
    return round(image.pixelColor(image.width() // 2, image.height() // 2).red() / 8)


class Client:
    """The test's Presenter: one QLocalSocket, every message the Audience sends kept in order."""

    def __init__(self, qtbot, name: str):
        self.qtbot, self.got, self.buffer = qtbot, [], b""
        self.socket = QLocalSocket()
        self.socket.readyRead.connect(self._read)
        self.socket.connectToServer(name)
        assert self.socket.waitForConnected(WAIT_MS), self.socket.errorString()

    def _read(self):
        self.buffer += bytes(self.socket.readAll().data())
        *lines, self.buffer = self.buffer.split(b"\n")
        self.got += [p.to_presenter(line) for line in lines]

    def send(self, message):
        self.socket.write(p.encode(message))
        self.socket.flush()

    def next(self):
        n = len(self.got)
        self.qtbot.waitUntil(lambda: len(self.got) > n, timeout=WAIT_MS)
        return self.got[n]


@pytest.fixture
def rig(qtbot):
    """An Audience in this process (its player and sink are inspectable) and a connected client."""
    view = audience.Audience(socket_path(), "Test talk")
    qtbot.addWidget(view)
    view.place()
    presented: list[QVideoFrame] = []
    view.sink.videoFrameChanged.connect(lambda f: f.isValid() and presented.append(QVideoFrame(f)))
    client = Client(qtbot, view.server.fullServerName())
    hello = client.next()
    assert hello == p.Hello(last=None, protocol=audience.PROTOCOL)
    yield view, client, presented
    client.socket.disconnectFromServer()


def at(slug="s"):
    return p.At(slug=slug)


def test_the_loaded_media_backend_is_ffmpeg(rig):
    view, _, _ = rig
    assert view.fatal is None and audience.loaded_media_plugins() == ["libffmpegmediaplugin.dylib"]


def test_an_unloadable_backend_sends_fatal_and_exits(tmp_path):
    """Qt loads ffmpeg in place of an unknown backend without a word: the dyld check is what notices."""
    pkg = tmp_path / "engine" / "manim_presentations"
    shutil.copytree(REPO / "manim_presentations", pkg, ignore=shutil.ignore_patterns("__pycache__"))
    source = (pkg / "audience.py").read_text()
    assert 'REQUIRED_BACKEND = "ffmpeg"' in source
    (pkg / "audience.py").write_text(source.replace('REQUIRED_BACKEND = "ffmpeg"', 'REQUIRED_BACKEND = "nosuch"'))
    name = socket_path()
    env = {**os.environ, "PYTHONPATH": str(pkg.parent), "QT_QPA_PLATFORM": "offscreen"}
    proc = subprocess.Popen([sys.executable, "-P", "-m", "manim_presentations.audience", name, "T"], env=env)
    try:
        with socket.socket(socket.AF_UNIX) as s:
            while s.connect_ex(name) != 0:  # until the Audience listens
                assert proc.poll() is None, "the Audience exited before listening"
                time.sleep(0.01)
            line = s.makefile("rb").readline()
        assert p.to_presenter(line) == p.Fatal(
            reason="media backend ['libffmpegmediaplugin.dylib'] loaded, libnosuchmediaplugin.dylib required"
        )
        assert proc.wait(SUBPROCESS_TIMEOUT) == 1
    finally:
        proc.kill()


def test_play_reports_playing_then_holds_the_last_frame(rig, clips):
    view, client, _ = rig
    client.send(p.Play(position=at(), clip=str(clips["a"])))
    first = client.next()
    assert isinstance(first, p.NowAt) and (first.position, first.clip, first.state) == (
        at(),
        str(clips["a"]),
        "playing",
    )
    held = client.next()
    assert isinstance(held, p.NowAt) and held.state == "held" and round(held.pts * FPS) == FRAMES - 1
    assert view.player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia
    assert index_of(view.sink.videoFrame()) == FRAMES - 1  # still on screen after the end, not an empty frame


def test_loop_is_still_playing_after_two_durations(rig, clips, qtbot):
    view, client, presented = rig
    client.send(p.Loop(position=at(), clip=str(clips["a"])))
    assert client.next() == p.NowAt(position=at(), clip=str(clips["a"]), state="looping", pts=0.0)
    start = len(presented)
    qtbot.wait(round(2 * FRAMES / FPS * 1000))
    indices = [index_of(f) for f in presented[start:]]
    assert view.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
    assert any(b < a for a, b in itertools.pairwise(indices)), indices  # it wrapped to the start
    assert client.got[-1].state == "looping"  # nothing reported since: a loop never holds


def test_a_missing_clip_fails_naming_it(rig, tmp_path):
    _, client, _ = rig
    gone = str(tmp_path / "gone.mp4")
    client.send(p.Play(position=at(), clip=gone))
    failed = client.next()
    assert isinstance(failed, p.Failed) and (failed.position, failed.clip) == (at(), gone) and failed.reason


def test_cover_shows_frame_zero_paused(rig, clips):
    view, client, _ = rig
    client.send(p.Cover(position=p.Before(), clip=str(clips["b"])))
    assert client.next() == p.NowCovered(position=p.Before(), clip=str(clips["b"]))
    assert index_of(view.sink.videoFrame()) == 0
    assert view.player.playbackState() == QMediaPlayer.PlaybackState.PausedState


def test_hold_shows_only_the_last_frame_paused(rig, clips):
    view, client, presented = rig
    client.send(p.Play(position=at("x"), clip=str(clips["b"])))
    assert client.next().state == "playing" and client.next().state == "held"
    start = len(presented)
    client.send(p.Hold(position=at(), clip=str(clips["a"])))
    held = client.next()
    assert isinstance(held, p.NowAt) and (held.clip, held.state) == (str(clips["a"]), "held")
    assert round(held.pts * FPS) == FRAMES - 1
    assert [index_of(f) for f in presented[start:]] == [FRAMES - 1]  # frame 0 never flashes first
    assert view.player.playbackState() == QMediaPlayer.PlaybackState.PausedState


def test_a_reconnecting_presenter_is_told_what_is_on_screen(rig, clips, qtbot):
    view, client, _ = rig
    client.send(p.Cover(position=p.Before(), clip=str(clips["a"])))
    now = client.next()
    client.socket.disconnectFromServer()
    again = Client(qtbot, view.server.fullServerName())
    assert again.next() == p.Hello(last=now, protocol=audience.PROTOCOL)


def test_a_new_presenter_replaces_the_old_connection(rig, clips, qtbot):
    view, client, _ = rig
    second = Client(qtbot, view.server.fullServerName())
    assert second.next() == p.Hello(last=None, protocol=audience.PROTOCOL)
    qtbot.waitUntil(lambda: client.socket.state() == QLocalSocket.LocalSocketState.UnconnectedState, timeout=WAIT_MS)
    second.send(p.Cover(position=p.Before(), clip=str(clips["a"])))
    assert second.next() == p.NowCovered(position=p.Before(), clip=str(clips["a"]))
    assert client.got[1:] == []


def test_keys_pressed_on_the_audience_reach_the_presenter_once(rig, qtbot, qapp):
    view, client, _ = rig
    forwarder = audience.KeyForwarder(view)
    qapp.installEventFilter(forwarder)
    try:
        for key in (Qt.Key.Key_PageDown, Qt.Key.Key_Up, Qt.Key.Key_R):
            QTest.keyClick(view.windowHandle(), key)  # through the window, as a real press arrives
        repeat = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier, "", True)
        QApplication.sendEvent(view, repeat)  # a held key's repeats
        qtbot.waitUntil(lambda: len(client.got) >= 4, timeout=WAIT_MS)
        qtbot.wait(200)  # a duplicate or a forwarded repeat would arrive in this window
    finally:
        qapp.removeEventFilter(forwarder)
    assert client.got[1:] == [p.Key(action=a) for a in ("next", "previous", "replay")]


def test_closing_the_window_tells_the_presenter(rig):
    view, client, _ = rig
    view.close()
    assert client.next() == p.Closed()
