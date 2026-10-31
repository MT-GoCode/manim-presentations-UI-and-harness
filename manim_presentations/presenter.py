"""Presenter View: the presenter's window, and the only owner of the talk's Position. It derives every message the
Audience gets (`show_for`), reads what the Audience reports, and keeps the Audience process alive by cause: a startup
failure stays down, a closed window waits for a click, a crash is relaunched."""

import json
import os
import sys
import time
from collections.abc import Callable
from functools import partial
from hashlib import sha256
from pathlib import Path
from typing import Literal

from PySide6.QtCore import QEvent, QFileSystemWatcher, QObject, QSignalBlocker, QSize, Qt, QTimer
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QFont,
    QIcon,
    QKeyEvent,
    QMouseEvent,
    QPixmap,
    QResizeEvent,
    QSyntaxHighlighter,
    QTextCharFormat,
)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from manim_presentations import deck as d
from manim_presentations import protocol as p
from manim_presentations import script

How = Literal["play", "show"]  # play the beat's animation, or show it as last seen
Shown = p.Play | p.Loop | p.Cover | p.Hold
EDITOR_FLOOR_PT = 16  # P1(e): the smallest editor text legible at presenter distance
FLASH_MS = 150  # a pressed button stays lit this long: long enough to see, shorter than a fast double press
CONNECT_RETRY_MS = 50  # polling a launched Audience's socket: invisible against its ~1 s start (PySide import)
# A key held with these is a shortcut (Cmd+R, Cmd+W), never navigation; Shift and the keypad flag (arrows on macOS)
# do not count.
CHORD = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier
ACCENT = "#3d7eff"
TEXT_EDIT_KEYS = ("Up", "Down", "R")  # typed while the editor has focus; PageUp/PageDown always navigate


def show_for(position: p.Before | p.At, beat: d.BuiltBeat, how: How) -> Shown:
    """The message that puts `position` on the Audience; `beat` is the beat at that position (beat 0 at Before). A
    loop beat always loops, whether it is played or shown."""
    clip = str(beat.clip)
    match position, beat.kind, how:
        case p.Before(), _, _:
            return p.Cover(position=position, clip=clip)
        case p.At(), "loop", _:
            return p.Loop(position=position, clip=clip)
        case p.At(), "beat", "play":
            return p.Play(position=position, clip=clip)
        case p.At(), "beat", "show":
            return p.Hold(position=position, clip=clip)


def held(message: Shown) -> Shown:
    """What `message` shows once it settles: a Play ends holding its last frame."""
    return p.Hold(position=message.position, clip=message.clip) if isinstance(message, p.Play) else message


def socket_path(root: Path) -> str:
    """Absolute, so both sides use exactly this path; under $TMPDIR, inside macOS's 104-byte socket path limit."""
    return str(Path(os.environ["TMPDIR"]) / f"mpres-{sha256(str(root).encode()).hexdigest()[:16]}")


class Link(QObject):
    """The Audience process and its socket. It hides launching, reaping and relaunching, and reports two things up:
    every message after the code check, and its own trouble line (None once there is none)."""

    def __init__(
        self,
        root: Path,
        title: str,
        received: Callable[[p.NowCovered | p.NowAt | p.Hello | p.Failed | p.Key], None],
        trouble: Callable[[str | None], None],
    ):
        super().__init__()
        self.root, self.title, self.received, self.trouble = root, title, received, trouble
        self.name = socket_path(root)
        self.pid: int | None = None  # the Audience this Presenter launched; None for an adopted one
        self.hello = False  # a Hello arrived on this connection
        self.fatal: str | None = None
        self.closed = False  # the Audience window was closed by hand
        self.quitting = False  # this Presenter sent Quit on purpose
        self.replacing = False  # Quit sent to an Audience of other code; relaunch when it is gone
        self.on_click: Callable[[], None] | None = None
        self.buffer = b""
        self.socket = QLocalSocket()
        self.socket.readyRead.connect(self._read)
        self.socket.disconnected.connect(self._dropped)
        self.socket.connected.connect(lambda: self.retry.stop())
        self.retry = QTimer(self)
        self.retry.setInterval(CONNECT_RETRY_MS)
        self.retry.timeout.connect(self._try_connect)

    def connect_live(self) -> bool:
        """Connect to an Audience already serving this talk (a restarted Presenter's reconnect)."""
        self.socket.connectToServer(self.name)
        return self.socket.waitForConnected()

    def launch(self) -> None:
        QLocalServer.removeServer(self.name)  # a crashed Audience leaves its socket file behind
        log = d.Layout(self.root).audience_log
        argv = [sys.executable, "-P", "-m", "manim_presentations.audience", self.name, self.title]
        actions = [
            (os.POSIX_SPAWN_OPEN, 0, os.devnull, os.O_RDONLY, 0),
            (os.POSIX_SPAWN_OPEN, 1, str(log), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644),
            (os.POSIX_SPAWN_DUP2, 1, 2),
        ]
        # setsid: the terminal's SIGHUP never reaches the Audience; stdout to a file: it never holds the caller's pipe
        self.pid = os.posix_spawn(sys.executable, argv, os.environ, file_actions=actions, setsid=True)
        self.hello, self.fatal, self.closed, self.buffer = False, None, False, b""
        self.retry.start()

    def _try_connect(self) -> None:
        """Runs only while a launched Audience has not been connected to: `connected` and `_dropped` stop it."""
        assert self.pid is not None
        done, status = os.waitpid(self.pid, os.WNOHANG)
        if done:
            self.retry.stop()
            self.pid = None
            log = d.Layout(self.root).audience_log
            self.trouble(f"Audience failed to start (exit {os.waitstatus_to_exitcode(status)}); see {log}")
            return
        self.socket.connectToServer(self.name)

    def send(self, message: Shown | p.Quit) -> None:
        if self.socket.state() == QLocalSocket.LocalSocketState.ConnectedState:
            self.socket.write(p.encode(message))
            self.socket.waitForBytesWritten()

    def quit(self) -> None:
        self.quitting = True
        self.send(p.Quit())

    def click(self) -> None:
        if self.on_click is not None:
            action, self.on_click = self.on_click, None
            action()

    def _read(self) -> None:
        self.buffer += bytes(self.socket.readAll().data())
        *lines, self.buffer = self.buffer.split(b"\n")
        for line in lines:
            raw = json.loads(line)
            if raw["type"] == "hello" and raw["protocol"] != p.AUDIENCE_CODE:
                # Decoded by that one field: an Audience of other code may not speak this union at all.
                self.replacing = True
                self.send(p.Quit())
                return
            message = p.to_presenter(line)
            match message:
                case p.Hello():
                    self.hello = True
                    self.received(message)
                case p.Fatal(reason=reason):
                    self.fatal = reason
                case p.Closed():
                    self.closed = True
                case p.NowCovered() | p.NowAt() | p.Failed() | p.Key():
                    self.received(message)

    def _dropped(self) -> None:
        """Route on what this connection told us before it dropped."""
        self.retry.stop()
        if self.pid is not None and os.waitpid(self.pid, os.WNOHANG)[0]:
            self.pid = None
        if self.quitting:
            return
        if self.replacing:
            self.replacing = False
            self._relaunch()
        elif self.fatal is not None:
            self.trouble(f"Audience failed: {self.fatal}")
        elif not self.hello:
            self.trouble(f"Audience failed to start; see {d.Layout(self.root).audience_log}")
        elif self.closed:
            self.trouble("Audience closed — click to reopen")
            self.on_click = self._reopen
        else:
            self._relaunch()

    def _relaunch(self) -> None:
        self.launch()
        self.trouble("Audience relaunched — re-share the Audience View window (click when done)")
        self.on_click = lambda: self.trouble(None)

    def _reopen(self) -> None:
        self.trouble(None)
        self.launch()


class Notes(QSyntaxHighlighter):
    """`> ` note lines dimmed: they are for the presenter, never spoken."""

    def highlightBlock(self, text: str) -> None:
        if script.is_note(text):
            dim = QTextCharFormat()
            dim.setForeground(QColor("#7d8799"))
            self.setFormat(0, len(text), dim)


class Still(QLabel):
    """A PNG scaled to fit, aspect kept."""

    def __init__(self) -> None:
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(1, 1)
        self.source = QPixmap()

    def show_png(self, path: Path | None) -> None:
        self.source = QPixmap(str(path)) if path is not None else QPixmap()
        self._scale()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._scale()

    def _scale(self) -> None:
        if self.source.isNull():
            self.clear()
            return
        self.setPixmap(
            self.source.scaled(
                self.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )


class Status(QLabel):
    def __init__(self, clicked: Callable[[], None]):
        super().__init__()
        self.clicked = clicked
        self.setWordWrap(True)

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        self.clicked()


class Presenter(QMainWindow):
    def __init__(self, deck: d.Deck, start: p.Before | p.At | None):
        """`start` is `--from`'s Position, which wins over what a reconnected Audience reports; None adopts."""
        super().__init__()
        self.deck, self.start = deck, start
        self.root = deck.root
        self.script_path = self.root / "script.md"
        self.title_text = script.load(self.script_path).title
        self.setWindowTitle(f"{self.title_text} — Presenter View")
        self.slugs = tuple(b.slug for b in deck.beats)
        self.position: p.Before | p.At = p.Before()
        self.now: p.NowCovered | p.NowAt | None = None
        self.red: dict[str, str] = {}  # what is wrong, by source; the status line shows red while any is set
        self.amber: dict[str, str] = {}
        self.started: float | None = None  # monotonic time of the first Next
        self.link = Link(self.root, self.title_text, self.received, self.audience_trouble)
        self._build_ui()
        # The talk folder alone: macOS's FSEvents backend reports in-place rewrites and atomic replaces of its files
        # alike (measured), and a folder watch survives the replace that drops a file watch.
        self.watcher = QFileSystemWatcher([str(self.root)])
        self.watcher.directoryChanged.connect(self.script_changed)
        self.clock = QTimer(self)
        self.clock.timeout.connect(self.refresh_status)
        self.clock.start(1000)  # the elapsed field counts seconds
        if deck.stale:
            self.amber["stale"] = f"changed since the build: {', '.join(deck.stale)}"
        if deck.structure_mismatch:
            self.red["structure"] = "script.md headings changed — run `mpres build`"
        self.show_position()

    # --- layout ---
    def _build_ui(self) -> None:
        self.timeline = QTreeWidget()
        self.timeline.setHeaderHidden(True)
        self.timeline.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # a click jumps without taking the keys
        self.timeline.setIconSize(QSize(128, round(128 * self.deck.render.pixel_height / self.deck.render.pixel_width)))
        self.items: dict[str, QTreeWidgetItem] = {}
        beats = {b.slug: b for b in self.deck.beats}
        for chapter, chapter_title, chapter_beats in self.deck.structure:
            parent = QTreeWidgetItem(self.timeline, [chapter_title or chapter])
            parent.setFlags(parent.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            for slug, title in chapter_beats:
                item = QTreeWidgetItem(parent, [title or slug])
                item.setIcon(0, QIcon(str(beats[slug].last_png)))
                item.setData(0, Qt.ItemDataRole.UserRole, slug)
                self.items[slug] = item
            parent.setExpanded(True)
        self.timeline.itemClicked.connect(self.clicked)
        self.now_still, self.next_still = Still(), Still()
        self.next_label = QLabel("Next")
        center = QWidget()
        column = QVBoxLayout(center)
        column.addWidget(self.now_still, stretch=3)
        column.addWidget(self.next_label)
        column.addWidget(self.next_still, stretch=1)
        self.editor = QTextEdit()
        self.editor.setAcceptRichText(False)
        self.editor.setStyleSheet(f"QTextEdit:focus {{ border: 2px solid {ACCENT}; }}")  # the visible editing state
        self.notes = Notes(self.editor.document())
        self.editor.textChanged.connect(self.save)
        # Refit after the edit completes: changing the document's font inside textChanged aborts Qt mid-insert.
        self.refit = QTimer(self)
        self.refit.setSingleShot(True)
        self.refit.timeout.connect(self.fit)
        self.editor.textChanged.connect(self.refit.start)
        self.buttons: dict[p.Action, QPushButton] = {}
        row = QHBoxLayout()
        buttons: tuple[tuple[p.Action, str, int], ...] = (
            ("previous", "▲ Previous (↑)", 1),
            ("next", "▼ Next (↓)", 2),  # the largest: the press made most often
            ("replay", "⟲ Replay (R)", 1),
        )
        for action, label, stretch in buttons:
            button = QPushButton(label)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setMinimumHeight(72)  # big: hit without looking, mid-sentence
            button.clicked.connect(partial(self.act, action))
            row.addWidget(button, stretch=stretch)
            self.buttons[action] = button
        self.status = Status(self.status_clicked)
        right = QWidget()
        script_column = QVBoxLayout(right)
        script_column.addWidget(self.editor, stretch=1)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        for widget in (self.timeline, center, right):
            splitter.addWidget(widget)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.addWidget(splitter, stretch=1)
        layout.addLayout(row)
        layout.addWidget(self.status)
        self.setCentralWidget(body)
        body.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.home = body  # where focus lives when the editor does not have it
        self.flash_base = {a: b.styleSheet() for a, b in self.buttons.items()}
        self.buttons["next"].setStyleSheet(f"background: {ACCENT}; font-size: 20pt;")
        self.flash_base["next"] = self.buttons["next"].styleSheet()

    # --- navigation: the Presenter owns the Position ---
    def beat_at(self, position: p.Before | p.At) -> d.BuiltBeat:
        match position:
            case p.Before():
                return self.deck.beats[0]
            case p.At(slug=slug):
                return self.deck.beats[self.slugs.index(slug)]

    def clip_of(self, position: p.Before | p.At) -> str:
        return str(self.beat_at(position).clip)

    def act(self, action: p.Action) -> None:
        self.home.setFocus()  # any button or key action leaves the editor
        match p.step(self.position, action, self.slugs):
            case p.Boundary():
                self.flash(action, "#c62828")
            case p.Moved(position=position):
                self.flash(action, None)
                if action == "next" and self.started is None:
                    self.started = time.monotonic()
                self.go(position, "show" if action == "previous" else "play")

    def clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        slug = item.data(0, Qt.ItemDataRole.UserRole)
        if slug is not None:
            self.go(p.At(slug=slug), "show")

    def go(self, position: p.Before | p.At, how: How) -> None:
        self.position = position
        self.link.send(show_for(position, self.beat_at(position), how))
        self.show_position()

    def flash(self, action: p.Action, color: str | None) -> None:
        button = self.buttons[action]
        button.setDown(True)
        if color is not None:
            button.setStyleSheet(f"background: {color};")
        # The button is the timer's context: a window closed mid-flash cancels it.
        QTimer.singleShot(
            FLASH_MS, button, lambda: (button.setDown(False), button.setStyleSheet(self.flash_base[action]))
        )

    def show_position(self) -> None:
        beat = self.beat_at(self.position)
        i = self.slugs.index(beat.slug)
        match self.position:
            case p.Before():
                self.now_still.show_png(beat.first_png)
                self.next_still.show_png(beat.last_png)
            case p.At():
                self.now_still.show_png(beat.last_png)
                nxt = self.deck.beats[i + 1] if i + 1 < len(self.deck.beats) else None
                self.next_still.show_png(nxt.last_png if nxt else None)
                self.next_label.setText("Next" if nxt else "Next: end of talk")
        with QSignalBlocker(self.timeline):
            self.timeline.setCurrentItem(self.items[beat.slug])
        self.load_editor()
        self.refresh_status()

    # --- the Audience ---
    def received(self, message: p.NowCovered | p.NowAt | p.Hello | p.Failed | p.Key) -> None:
        match message:
            case p.Hello(last=last):
                self.adopt(last)
            case p.NowCovered() | p.NowAt():
                if message.position == self.position:
                    self.now = message
                    self.red.pop("failed", None)
                    self.refresh_status()
            case p.Failed(position=position, clip=clip, reason=reason):
                self.red["failed"] = f"Audience could not play {Path(clip).name} at {position}: {reason}"
                self.refresh_status()
            case p.Key(action=action):
                self.act(action)

    def adopt(self, last: p.NowCovered | p.NowAt | None) -> None:
        """On each Hello: `--from` wins once; else keep what the Audience shows if it is this deck's; else show ours."""
        if self.start is not None:
            start, self.start = self.start, None
            self.go(start, "show")
            return
        match last:
            case p.NowAt(position=p.At(slug=slug), clip=clip) if (
                slug in self.slugs and self.clip_of(last.position) == clip
            ):
                self.position, self.now = last.position, last
                self.show_position()
            case p.NowCovered(clip=clip) if clip == self.clip_of(p.Before()):
                self.position, self.now = p.Before(), last
                self.show_position()
            case _:
                self.go(self.position, "show")

    def audience_trouble(self, text: str | None) -> None:
        if text is None:
            self.red.pop("audience", None)
        else:
            self.red["audience"] = text
        self.refresh_status()

    def status_clicked(self) -> None:
        self.link.click()

    def refresh_status(self) -> None:
        if self.red:
            text, color = " · ".join(self.red.values()), "#c62828"
        elif self.amber:
            text, color = " · ".join(self.amber.values()), "#e0a100"
        else:
            beat = self.beat_at(self.position)
            n = len(self.slugs)
            i = self.slugs.index(beat.slug) + 1 if isinstance(self.position, p.At) else 0
            match self.now:
                case p.NowAt(state=state):
                    seen = f"{beat.slug} {state}"
                case p.NowCovered():
                    seen = f"{beat.slug} covered"
                case None:
                    seen = "connecting"
            elapsed = int(time.monotonic() - self.started) if self.started is not None else 0
            text, color = f"Audience: {seen} · beat {i}/{n} · {elapsed // 60}:{elapsed % 60:02d}", "#2e7d32"
        self.status.setText(text)
        self.status.setStyleSheet(f"color: white; background: {color}; padding: 6px; font-size: 14pt;")

    # --- the script editor ---
    def load_editor(self) -> None:
        slug = self.beat_at(self.position).slug
        try:
            text = script.load(self.script_path).beat(slug).text
        except ValueError as e:
            text = ""
            self.red["structure"] = f"script.md: {e}"
        with QSignalBlocker(self.editor):
            self.editor.setPlainText(text)
        self.fit()

    def save(self) -> None:
        slug = self.beat_at(self.position).slug
        try:
            script.save_beat(self.script_path, slug, self.editor.toPlainText())
        except (ValueError, OSError) as e:
            self.red["save"] = f"not saved: {e}"
        else:
            self.red.pop("save", None)
        self.refresh_status()

    def script_changed(self, _path: str) -> None:
        try:
            text = self.script_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return  # between an editor's unlink and its rename; the rename fires again
        if "save" in self.red:
            return  # a failed save: what was typed must not be overwritten by a reload
        try:
            mismatch = d.structure_mismatch(text, self.deck.structure)
        except ValueError as e:
            self.red["structure"] = f"script.md: {e}"
            self.refresh_status()
            return
        if mismatch:
            self.red["structure"] = "script.md headings changed — run `mpres build`"
        else:
            self.red.pop("structure", None)
        slug = self.beat_at(self.position).slug
        beat = next((b for c in script.parse(text).chapters for b in c.beats if b.slug == slug), None)
        if beat is not None and beat.text != self.editor.toPlainText():  # never true for the editor's own write
            with QSignalBlocker(self.editor):
                self.editor.setPlainText(beat.text)
            self.fit()
        self.refresh_status()

    def fit(self) -> None:
        """The largest point size, at least the floor, at which the beat's text shows without scrolling."""
        viewport = self.editor.viewport()
        if viewport.height() <= 0:
            return
        document = self.editor.document()
        font = QFont(self.editor.font())

        def fits(size: int) -> bool:
            font.setPointSize(size)
            document.setDefaultFont(font)
            document.setTextWidth(viewport.width())
            return document.size().height() <= viewport.height()

        lo, hi, best = EDITOR_FLOOR_PT, max(EDITOR_FLOOR_PT, viewport.height()), None
        while lo <= hi:
            mid = (lo + hi) // 2
            if fits(mid):
                best, lo = mid, mid + 1
            else:
                hi = mid - 1
        fits(best or EDITOR_FLOOR_PT)
        if best is None:
            self.amber["overflow"] = "beat text overflows"
        else:
            self.amber.pop("overflow", None)
        self.font_points = best or EDITOR_FLOOR_PT

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.fit()

    # --- keys: one application filter routes the five mapped keys before any widget sees them ---
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if not (isinstance(event, QKeyEvent) and event.type() == QEvent.Type.KeyPress):
            return False
        name = Qt.Key(event.key()).name.removeprefix("Key_")
        if name == "Escape" and self.editor.hasFocus():
            self.home.setFocus()
            return True
        action = p.KEYS.get(name)
        if action is None or (self.editor.hasFocus() and name in TEXT_EDIT_KEYS):
            return False
        if event.modifiers() & CHORD:
            return False
        if not event.isAutoRepeat():  # a held key or a repeating clicker advances one beat
            self.act(action)
        return True  # consumed at its first (QWindow) delivery, so the QWidget delivery never happens

    def closeEvent(self, event: QCloseEvent) -> None:
        self.link.quit()
        event.accept()


def open_presenter(deck: d.Deck, start: p.Before | p.At | None) -> Presenter:
    """Startup order: connect to the talk's socket; a live Audience is a reconnect (it adopts this deck, stale or
    not); none is a fresh start, which refuses a stale deck before anything launches. Needs a QApplication."""
    window = Presenter(deck, start)
    if not window.link.connect_live():
        d.require_fresh(deck)
        window.link.launch()
    app = QApplication.instance()
    assert app is not None
    app.installEventFilter(window)
    window.showMaximized()
    window.home.setFocus()
    return window


def present(deck: d.Deck, start: p.Before | p.At | None) -> int:
    fd = d.Layout(deck.root).presenter_lock()
    try:
        app = QApplication([])
        open_presenter(deck, start)
        return app.exec()
    finally:
        os.close(fd)
