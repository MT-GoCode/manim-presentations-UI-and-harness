"""Presenter View: the presenter's window, and the only owner of the talk's Position. It derives every message the
Audience gets (`show_for`), reads what the Audience reports, and keeps the Audience process alive by cause: a startup
failure stays down, a closed window waits for a click, a crash is relaunched."""

import json
import os
import signal
import sys
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from hashlib import sha256
from pathlib import Path
from types import TracebackType
from typing import Literal

from PySide6.QtCore import (
    QEvent,
    QFileSystemWatcher,
    QObject,
    QSignalBlocker,
    QSize,
    Qt,
    QTimer,
    Signal,
)
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
    QTextOption,
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
ACCENT = "#3d7eff"
LOCK_RETRY_S = 1.0  # §3.7: GC's liveness probe holds the presenter lock for microseconds; 1 s is imperceptible
PARENT_WATCH_MS = 1000  # the parent-death watch's interval, as the scene processes' (talk.watch_parent)
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


class UnknownBeat(Exception):
    """`--from` names no beat of the deck; args: the slug, the deck's slugs."""


def open_deck(root: Path) -> d.Deck:
    """The deck, and its clips pinned, under the shared clips lock: no commit can collect a clip between the two."""
    layout = d.Layout(root)
    with layout.clips_shared():
        deck = d.Deck.open(root)
        layout.write_pins({b.clip.stem for b in deck.beats})
    return deck


def socket_path(root: Path) -> str:
    """Absolute, so both sides use exactly this path; under $TMPDIR, inside macOS's 104-byte socket path limit."""
    return str(Path(os.environ["TMPDIR"]) / f"mpres-{sha256(str(root).encode()).hexdigest()[:16]}")


@dataclass(frozen=True)
class FatalSaid:
    reason: str


# What this connection has told the Presenter, set where each message is decoded; a drop routes on it alone.
# "quit" and "replace" are the Presenter's own Quit: on purpose, or to an Audience of other code (relaunched).
Told = Literal["nothing", "hello", "closed", "quit", "replace"] | FatalSaid


class Link(QObject):
    """The Audience process and its socket. It hides launching, reaping and relaunching, and reports two things up:
    every message after the code check, and its own trouble line (None once there is none)."""

    def __init__(
        self,
        root: Path,
        title: str,
        received: Callable[[p.NowCovered | p.NowAt | p.Hello | p.Failed | p.Key], None],
        trouble: Callable[[str | None], None],
        lost: Callable[[], None],
    ):
        super().__init__()
        self.root, self.title, self.received, self.trouble, self.lost = root, title, received, trouble, lost
        self.name = socket_path(root)
        self.pid: int | None = None  # the Audience this Presenter launched and has not reaped; None for an adopted one
        self.told: Told = "nothing"
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
        if self.pid is not None:
            os.waitpid(self.pid, 0)  # the previous Audience dropped its socket: it is exiting; reap it before the next
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
        self.told, self.buffer = "nothing", b""
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

    def close(self) -> None:
        """Intent: the Audience goes too. Quit if it is connected; a launched one not yet listening is terminated."""
        self.told = "quit"
        self.retry.stop()
        if self.socket.state() == QLocalSocket.LocalSocketState.ConnectedState:
            self.send(p.Quit())
        elif self.pid is not None:
            os.kill(self.pid, signal.SIGTERM)
            os.waitpid(self.pid, 0)
            self.pid = None

    def click(self) -> None:
        if self.on_click is not None:
            action, self.on_click = self.on_click, None
            action()

    def _read(self) -> None:
        self.buffer += bytes(self.socket.readAll().data())
        *lines, self.buffer = self.buffer.split(b"\n")
        for line in lines:
            if self.told in ("quit", "replace") or isinstance(self.told, FatalSaid):
                return  # after our own Quit nothing this connection says changes why it ends (Quit sends Closed)
            raw = json.loads(line)
            if raw["type"] == "hello" and raw["protocol"] != p.AUDIENCE_CODE:
                # Decoded by that one field: an Audience of other code may not speak this union at all. One this
                # Presenter launched means the engine on disk changed under it: every relaunch would differ again.
                self.told = (
                    "replace"
                    if self.pid is None
                    else FatalSaid("the engine changed on disk since present started; restart mpres present")
                )
                self.send(p.Quit())
                return
            message = p.to_presenter(line)
            match message:
                case p.Hello():
                    self.told = "hello"
                    self.received(message)
                case p.Fatal(reason=reason):
                    self.told = FatalSaid(reason)
                case p.Closed():
                    self.told = "closed"
                case p.NowCovered() | p.NowAt() | p.Failed() | p.Key():
                    self.received(message)

    def _dropped(self) -> None:
        self.retry.stop()
        self.lost()
        match self.told:
            case "quit":
                pass
            case "replace" | "hello":  # other code, or a crash after Hello
                self.launch()
                self.trouble("Audience relaunched — re-share the Audience View window (click when done)")
                self.on_click = lambda: self.trouble(None)
            case FatalSaid(reason=reason):
                self.trouble(f"Audience failed: {reason}")
            case "nothing":
                self.trouble(f"Audience failed to start; see {d.Layout(self.root).audience_log}")
            case "closed":
                self.trouble("Audience closed — click to reopen")
                self.on_click = self._reopen

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
    opened = Signal(object)  # a newly committed Deck, opened off the GUI thread
    open_failed = Signal(str)

    def __init__(self, deck: d.Deck, start: p.Before | p.At | None):
        """`start` is `--from`'s Position, which wins over what a reconnected Audience reports; None adopts."""
        super().__init__()
        self.deck, self.start = deck, start
        self.root = deck.root
        self.script_path = self.root / "script.md"
        self.title_text = script.load(self.script_path).title
        self.setWindowTitle(f"{self.title_text} — Presenter View")
        self.slugs = tuple(b.slug for b in deck.beats)
        self.position: p.Before | p.At = start or p.Before()  # `--from` shows at once; the Audience follows on Hello
        self.now: p.NowCovered | p.NowAt | None = None
        self.red: dict[str, str] = {}  # what is wrong, by source; the status line shows red while any is set
        self.amber: dict[str, str] = {}
        self.started: float | None = None  # monotonic time of the first Next
        self.last_sent: Shown | None = None  # what the Audience was last told to show, or adopted as showing
        self.opening = False  # a Deck.open of a new build is running off the GUI thread
        self.lock_fd = -1  # the presenter lock, set by open_presenter
        self.link = Link(self.root, self.title_text, self.received, self.audience_trouble, self.audience_lost)
        self.opened.connect(self.hot_swap)
        self.open_failed.connect(self.open_failed_with)
        self._build_ui()
        # The talk folder alone: macOS's FSEvents backend reports in-place rewrites and atomic replaces of its files
        # alike (measured), and a folder watch survives the replace that drops a file watch.
        self.watcher = QFileSystemWatcher([str(self.root)])
        self.watcher.directoryChanged.connect(self.folder_changed)
        # build/, not index.json: a commit's os.replace never drops a folder watch. Lock and pin rewrites and .media
        # churn fire it too; each costs one read of build_id.
        self.build_watcher = QFileSystemWatcher([str(d.Layout(self.root).build)])
        self.build_watcher.directoryChanged.connect(self.build_changed)
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
        self.fill_timeline()
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
        self.editor.setWordWrapMode(QTextOption.WrapMode.WordWrap)  # never inside a word
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
        self.flash_base: dict[p.Action, str] = {
            "previous": "font-size: 16pt;",
            "next": f"background: {ACCENT}; font-size: 20pt;",
            "replay": "font-size: 16pt;",
        }
        for action, button in self.buttons.items():
            button.setStyleSheet(self.flash_base[action])

    def fill_timeline(self) -> None:
        self.timeline.clear()
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
        self.tell(show_for(position, self.beat_at(position), how))
        self.show_position()

    def tell(self, message: Shown) -> None:
        """The one place the Audience is told what to show; what it reported before no longer describes the screen."""
        self.last_sent, self.now = message, None
        self.link.send(message)

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
                self.next_label.setText("Next")
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
                print(f"present: Audience connected, showing {self.position}", flush=True)  # for an agent's log
            case p.NowCovered() | p.NowAt():
                sent = self.last_sent
                if sent is not None and (message.position, message.clip) == (sent.position, sent.clip):
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
        if self.start is not None:  # once: a later Hello (a relaunch) adopts as usual
            self.start = None
            self.go(self.position, "show")
            return
        match last:
            case p.NowAt(position=p.At(slug=slug) as at, clip=clip) if slug in self.slugs and self.clip_of(at) == clip:
                self.position, self.now = at, last
                self.last_sent = show_for(at, self.beat_at(at), "show")  # what the echo settles to
                self.show_position()
            case p.NowCovered(position=before, clip=clip) if clip == self.clip_of(before):
                self.position, self.now = before, last
                self.last_sent = show_for(before, self.beat_at(before), "show")
                self.show_position()
            case _:
                self.go(self.position, "show")

    # --- hot-swap: every committed build is adopted while presenting ---
    def folder_changed(self, path: str) -> None:
        build = d.Layout(self.root).build
        if build.is_dir() and str(build) not in self.build_watcher.directories():
            self.build_watcher.addPath(str(build))  # build/ was removed and made again
            self.build_changed(str(build))
        self.script_changed(path)

    def build_changed(self, _path: str) -> None:
        if self.opening or d.Layout(self.root).build_id() in (None, self.deck.build_id):
            return

        def run() -> None:
            try:
                self.opened.emit(open_deck(self.root))
            except Exception as e:  # any failure is shown; a thread's exception would otherwise vanish
                self.open_failed.emit(f"{type(e).__name__}: {e}")

        self.opening = True
        threading.Thread(target=run, daemon=True).start()

    def hot_swap(self, deck: d.Deck) -> None:
        """Keep the Position by slug (or the nearest earlier surviving beat), and tell the Audience only what its
        settled picture changes: a beat whose clip is unchanged is never restarted, cut short or replayed."""
        self.opening = False
        old = self.slugs
        self.deck, self.slugs = deck, tuple(b.slug for b in deck.beats)
        self.red.pop("rebuild", None)
        self.red.pop("removed", None)
        if isinstance(self.position, p.At) and self.position.slug not in self.slugs:
            gone = self.position.slug
            kept = [s for s in old[: old.index(gone)] if s in self.slugs]
            self.position = p.At(slug=kept[-1]) if kept else p.Before()
            where = kept[-1] if kept else "the start"
            self.red["removed"] = f"beat {gone} was removed by the rebuild; now at {where}"
        self.amber.pop("stale", None)
        if deck.stale:
            self.amber["stale"] = f"changed since the build: {', '.join(deck.stale)}"
        if deck.structure_mismatch:
            self.red["structure"] = "script.md headings changed — run `mpres build`"
        else:
            self.red.pop("structure", None)
        self.fill_timeline()
        settled = show_for(self.position, self.beat_at(self.position), "show")
        if self.last_sent is None or held(settled) != held(self.last_sent):
            self.tell(settled)
        self.show_position()
        self.build_changed("")  # a build committed while this one was opening

    def open_failed_with(self, error: str) -> None:
        """The new build's deck could not be opened: say so, and let the next build try again."""
        self.opening = False
        self.red["rebuild"] = f"the new build could not be read: {error}"
        self.refresh_status()

    def audience_lost(self) -> None:
        self.now = None  # the Audience that reported it is gone
        self.refresh_status()

    def audience_trouble(self, text: str | None) -> None:
        if text is None:
            self.red.pop("audience", None)
        else:
            self.red["audience"] = text
        self.refresh_status()

    def status_clicked(self) -> None:
        self.link.click()

    def refresh_status(self) -> None:
        """Red problems, then amber ones, then always what the Audience reported, the beat and the elapsed time."""
        match self.now:  # only what the Audience said about the current position (received drops the rest)
            case p.NowAt(position=p.At(slug=slug), state=state):
                seen = f"{slug} {state}"
            case p.NowCovered():
                seen = f"{self.slugs[0]} covered"
            case None:
                seen = "waiting"
        i = self.slugs.index(self.position.slug) + 1 if isinstance(self.position, p.At) else 0
        elapsed = int(time.monotonic() - self.started) if self.started is not None else 0
        fields = f"Audience: {seen} · beat {i}/{len(self.slugs)} · {elapsed // 60}:{elapsed % 60:02d}"
        color = "#c62828" if self.red else "#e0a100" if self.amber else "#2e7d32"
        text = " · ".join([*self.red.values(), *self.amber.values(), fields])
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
            # Between an editor's unlink and its rename the rename clears this; a real deletion keeps it red.
            self.red["structure"] = "script.md is missing"
            self.refresh_status()
            return
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
            # idealWidth: the widest unbreakable run; wider than the viewport would be cut mid-word
            return document.size().height() <= viewport.height() and document.idealWidth() <= viewport.width()

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
        if any(event.modifiers() & Qt.KeyboardModifier[m] for m in p.CHORD):
            return False
        if not event.isAutoRepeat():  # a held key or a repeating clicker advances one beat
            self.act(action)
        return True  # consumed at its first (QWindow) delivery, so the QWidget delivery never happens

    def closeEvent(self, event: QCloseEvent) -> None:
        self.link.close()
        if self.lock_fd >= 0:  # a second close must not close whatever fd reuses the number
            os.close(self.lock_fd)  # pins count only while this lock is held
            self.lock_fd = -1
        event.accept()


def open_presenter(root: Path, start: str | None) -> Presenter:
    """Startup order: take the presenter lock (the window holds it until it closes); open and pin the deck; connect
    to the talk's socket; a live Audience is a reconnect (it adopts
    this deck, stale or not); none is a fresh start, which refuses a stale deck before anything launches. `start` is
    `--from`'s beat. Needs a QApplication."""
    fd = lock(d.Layout(root))
    try:
        deck = open_deck(root)
        slugs = tuple(b.slug for b in deck.beats)
        if start is not None and start not in slugs:
            raise UnknownBeat(start, slugs)
        window = Presenter(deck, None if start is None else p.before(start, slugs))
        if not window.link.connect_live():
            d.require_fresh(deck)
            window.link.launch()
    except BaseException:
        os.close(fd)
        raise
    window.lock_fd = fd
    app = QApplication.instance()
    assert app is not None
    app.installEventFilter(window)
    window.showMaximized()
    window.home.setFocus()
    return window


def lock(layout: d.Layout) -> int:
    deadline = time.monotonic() + LOCK_RETRY_S
    while True:
        try:
            return layout.presenter_lock()
        except d.Busy:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.01)


def route_signals(intent: Callable[[], None]) -> list[object]:
    """Closing by cause. Intent (SIGINT, SIGTERM) runs `intent`. Accident is left to the defaults: SIGHUP terminates
    (or is ignored under nohup), and a dead parent exits; both close the lock and socket without Quit, so the Audience
    and the Zoom share stay up and a re-run reconnects. A Python handler runs when Python next runs; the parent watch
    below wakes it at least every PARENT_WATCH_MS. Returns what must stay alive."""
    for number in (signal.SIGINT, signal.SIGTERM):
        signal.signal(number, lambda *_: intent())
    parent = os.getppid()  # uv, under bin/mpres: its SIGKILL cannot be forwarded (macOS has no PR_SET_PDEATHSIG)
    watch = QTimer()
    watch.timeout.connect(lambda: os.getppid() != parent and os._exit(1))
    watch.start(PARENT_WATCH_MS)
    return [watch]


def report_errors(window: Presenter) -> None:
    """Qt prints a slot's exception and carries on: show it red rather than lose the Presenter mid-talk."""

    def failed(kind: type[BaseException], error: BaseException, trace: TracebackType | None) -> None:
        traceback.print_exception(kind, error, trace)
        window.red["error"] = f"{kind.__name__}: {error}"
        window.refresh_status()

    sys.excepthook = failed


def present(root: Path, start: str | None) -> int:
    app = QApplication([])
    windows: list[Presenter] = []
    stop: list[bool] = []  # an intent signal; acted on in the event loop, once the window (and its Link) exists

    def intent() -> None:
        stop.append(True)
        if windows:
            QTimer.singleShot(0, windows[0].close)  # in the loop: closing there also ends it

    kept = route_signals(intent)
    print(f"present: opening {root}", flush=True)  # signals are routed from here on
    windows.append(open_presenter(root, start))
    report_errors(windows[0])
    if stop:
        QTimer.singleShot(0, windows[0].close)
    code = app.exec()
    del kept
    return code
