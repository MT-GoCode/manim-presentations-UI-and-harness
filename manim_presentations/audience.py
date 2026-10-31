"""Audience View: a pure clip player in its own process (macOS and Zoom share windows per app, so the shared window
never lives with the presenter's notes). It knows nothing about talks or decks: it plays, loops, covers or holds the
clip it is told, reports what the player actually shows, and echoes the Position it was given.

    python -P -m manim_presentations.audience <socket-name> <talk title>"""

import ctypes
import hashlib
import os
import sys
from pathlib import Path
from typing import Literal

os.environ["QT_MEDIA_BACKEND"] = REQUIRED_BACKEND = "ffmpeg"  # P1/P5: darwin presents nothing headless; set first

from PySide6.QtCore import QEvent, QObject, Qt, QUrl
from PySide6.QtGui import QCloseEvent, QGuiApplication, QKeyEvent, QPalette
from PySide6.QtMultimedia import QMediaPlayer, QVideoFrame
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from manim_presentations import protocol as p

NO_SCREEN_WIDTH = 0.55  # of the screen when there is no second one: rev 14's guess, confirmed or changed in P6 (D4)
PROTOCOL = hashlib.sha256(
    Path(__file__).read_bytes() + (Path(__file__).parent / "protocol.py").read_bytes()
).hexdigest()  # what this Audience does with each message: a Presenter of another version relaunches it

Shown = p.Play | p.Loop | p.Cover | p.Hold
# What the next presented frame is reported as, per shown message; "seek" waits for LoadedMedia before Hold's seek.
Expect = Literal["playing", "looping", "covered", "seek", "held"] | None


def loaded_media_plugins() -> list[str]:
    """The Qt media plugins this process has loaded, by dyld image name: Qt reports no backend identity, and an
    unloadable QT_MEDIA_BACKEND silently loads another one."""
    lib = ctypes.CDLL(None)
    lib._dyld_image_count.restype = ctypes.c_uint32
    lib._dyld_get_image_name.restype = ctypes.c_char_p
    lib._dyld_get_image_name.argtypes = [ctypes.c_uint32]
    names = (Path(lib._dyld_get_image_name(i).decode()).name for i in range(lib._dyld_image_count()))
    return sorted({n for n in names if n.endswith("mediaplugin.dylib")})


class Audience(QWidget):
    def __init__(self, socket_name: str, title: str):
        super().__init__()
        self.setWindowTitle(f"{title} — Audience View")
        self.setMinimumSize(0, 0)  # else a 3456-pixel video stretches the window past the screen
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, Qt.GlobalColor.black)
        self.setPalette(palette)
        self.video = QVideoWidget()
        self.video.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)  # letterboxed in black, never cropped
        self.video.setMinimumSize(0, 0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.video)
        self.player = QMediaPlayer()  # Qt loads the backend plugin here
        self.player.setVideoOutput(self.video)
        self.sink = self.video.videoSink()
        self.sink.videoFrameChanged.connect(self._presented)
        self.player.mediaStatusChanged.connect(self._status)
        self.player.errorOccurred.connect(self._error)
        loaded = loaded_media_plugins()
        want = f"lib{REQUIRED_BACKEND}mediaplugin.dylib"
        self.fatal = None if loaded == [want] else f"media backend {loaded} loaded, {want} required"
        self.shown: Shown | None = None
        self.expect: Expect = None
        self.last_valid: QVideoFrame | None = None  # of the shown clip
        self.now: p.NowCovered | p.NowAt | None = None
        self.client: QLocalSocket | None = None
        self.buffer = b""
        self.server = QLocalServer()
        self.server.newConnection.connect(self._connected)
        if not self.server.listen(socket_name):
            raise SystemExit(f"audience: cannot listen on {socket_name}: {self.server.errorString()}")

    def place(self) -> None:
        """A second screen if there is one, maximized; else 55% of the screen's width. Never macOS-fullscreen: a
        fullscreen window lives in its own Space, which pauses Zoom's share."""
        screens = QGuiApplication.screens()
        if len(screens) > 1:
            self.setGeometry(screens[1].availableGeometry())
            self.showMaximized()
            return
        width = round(screens[0].availableGeometry().width() * NO_SCREEN_WIDTH)
        self.resize(width, round(width * 9 / 16))
        self.show()

    # --- the socket: newline-delimited JSON, one client at a time ---
    def _connected(self) -> None:
        """The newest connection replaces any earlier one: the presenter lock allows one Presenter, and a relaunched
        one may connect before its predecessor's close is read here."""
        if self.client is not None:
            self.client.readyRead.disconnect()
            self.client.abort()
        self.client, self.buffer = self.server.nextPendingConnection(), b""
        self.client.readyRead.connect(self._read)
        if self.fatal is None:
            self.send(p.Hello(last=self.now, protocol=PROTOCOL))
            return
        self.send(p.Fatal(reason=self.fatal))
        QApplication.exit(1)

    def send(self, message: p.ToPresenter) -> None:
        if self.client is not None and self.client.state() == QLocalSocket.LocalSocketState.ConnectedState:
            self.client.write(p.encode(message))
            self.client.waitForBytesWritten()  # the next line may be the process's last

    def _read(self) -> None:
        assert self.client is not None
        self.buffer += bytes(self.client.readAll().data())
        *lines, self.buffer = self.buffer.split(b"\n")
        for line in lines:
            self.handle(p.to_audience(line))

    def handle(self, message: p.ToAudience) -> None:
        if isinstance(message, p.Quit):
            QApplication.quit()
            return
        self.shown, self.last_valid = message, None
        self.player.setSource(QUrl.fromLocalFile(message.clip))
        match message:
            case p.Play():
                self.expect = "playing"
                self.player.setLoops(1)
                self.player.play()
            case p.Loop():
                self.expect = "looping"
                self.player.setLoops(QMediaPlayer.Loops.Infinite)
                self.player.play()
            case p.Cover():
                self.expect = "covered"
                self.player.pause()  # presents pts 0
            case p.Hold():
                self.expect = "seek"
                self.player.pause()  # a seek before LoadedMedia is discarded (P1)

    # --- what the player actually shows ---
    def _status(self, status: QMediaPlayer.MediaStatus) -> None:
        loaded = status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia)
        if self.expect == "seek" and loaded:
            self.expect = "held"
            # duration - 1 ms lies inside the last frame; P1 measured it presenting exactly that frame, 5/5
            self.player.setPosition(self.player.duration() - 1)
        elif isinstance(self.shown, p.Play) and status == QMediaPlayer.MediaStatus.EndOfMedia:
            assert self.last_valid is not None
            self.sink.setVideoFrame(self.last_valid)  # an empty frame precedes EndOfMedia: show the last real one
            self.report("held", self.last_valid)

    def _presented(self, frame: QVideoFrame) -> None:
        if not frame.isValid():
            return
        self.last_valid = QVideoFrame(frame)
        if self.expect in ("playing", "looping", "covered", "held"):
            self.report(self.expect, frame)

    def report(self, state: Literal["playing", "looping", "covered", "held"], frame: QVideoFrame) -> None:
        assert self.shown is not None
        self.expect = None
        match self.shown, state:
            case p.Cover(position=position, clip=clip), "covered":
                self.now = p.NowCovered(position=position, clip=clip)
            case (p.Play() | p.Loop() | p.Hold()) as shown, "playing" | "looping" | "held":
                self.now = p.NowAt(position=shown.position, clip=shown.clip, state=state, pts=frame.startTime() / 1e6)
            case _:
                raise AssertionError(f"{state} reported for {self.shown}")
        self.send(self.now)

    def _error(self, error: QMediaPlayer.Error, reason: str) -> None:
        assert self.shown is not None
        self.expect = None
        self.send(p.Failed(position=self.shown.position, clip=self.shown.clip, reason=reason or error.name))

    def closeEvent(self, event: QCloseEvent) -> None:
        self.send(p.Closed())
        event.accept()


class KeyForwarder(QObject):
    """Keys pressed while the Audience has focus go to the Presenter, which owns navigation. A press reaches an
    application filter first as its QWindow delivery; consuming it there keeps the QWidget delivery from happening."""

    def __init__(self, audience: Audience):
        super().__init__()
        self.audience = audience

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if not (isinstance(event, QKeyEvent) and event.type() == QEvent.Type.KeyPress):
            return False
        action = p.KEYS.get(Qt.Key(event.key()).name.removeprefix("Key_"))
        if action is None:
            return False
        if not event.isAutoRepeat():  # a held key or a repeating clicker sends one action
            self.audience.send(p.Key(action=action))
        return True


def main(argv: list[str]) -> int:
    socket_name, title = argv
    app = QApplication([])
    audience = Audience(socket_name, title)
    forwarder = KeyForwarder(audience)
    app.installEventFilter(forwarder)
    if audience.fatal is None:  # a wrong backend shows no window: it waits for the Presenter, sends Fatal, exits 1
        audience.place()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
