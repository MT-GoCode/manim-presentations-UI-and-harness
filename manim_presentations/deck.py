"""The built talk as data. This module owns everything under a talk's build/ folder: no other module builds a
build/... path. It also defines the talk file set, the files whose bytes can change what the talk shows."""

import contextlib
import fcntl
import hashlib
import json
import os
import secrets
import shutil
from collections.abc import Callable, Generator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from manim_presentations import script
from manim_presentations.records import BeatKind

EXCLUDED_DIRS = frozenset({"build", "__pycache__"})


SCHEMA = 1  # the index format; any other value is a build this engine cannot read (NoPrevious, IncompatibleBuild)


class Busy(Exception):
    """Another build holds the build lock."""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class IndexBeat(_Frozen):
    chapter: str
    slug: str
    title: str | None
    kind: BeatKind
    fingerprint: str
    frames: int
    clip: str  # the clip's content sha
    first_png: str  # paths relative to build/
    last_png: str


class ChapterCost(_Frozen):
    """This chapter's measured pass-1 peaks: the next build sizes pass 1 and its workers from them."""

    pass1_rss: int
    pass1_cores: float


class Render(_Frozen):
    pixel_width: int
    pixel_height: int
    fps: int


class Index(_Frozen):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)
    schema_: int = Field(alias="schema")  # `schema` is a BaseModel method name
    build_id: str  # a fresh random token per commit: the exact identity a hot-swap compares
    files: dict[str, str]  # the talk file set: relative path → sha256
    chapters: dict[str, ChapterCost]
    render: Render
    structure: tuple[tuple[str, str | None, tuple[tuple[str, str | None], ...]], ...]
    beats: tuple[IndexBeat, ...]


INDEX: TypeAdapter[Index] = TypeAdapter(Index)


class Absent(_Frozen):
    kind: Literal["absent"] = "absent"


class SchemaMismatch(_Frozen):
    kind: Literal["schema-mismatch"] = "schema-mismatch"
    old: int
    new: int


class NoPrevious(_Frozen):
    """There is no previous build this engine can reuse; the reason is marked where it is found."""

    reason: Absent | SchemaMismatch


class PreviousBuild(_Frozen):
    index: Index


def new_build_id() -> str:
    return secrets.token_hex(8)


class Layout:
    def __init__(self, talk_root: Path):
        self.root = talk_root
        self.build = talk_root / "build"

    @property
    def media(self) -> Path:
        """Scratch for one build: the snapshot, each process's output and private caches. Wiped at the start of every
        build (under the build lock), removed at its end."""
        return self.build / ".media"

    @property
    def snapshot(self) -> Path:
        return self.media / "src"

    def process(self, name: str) -> Path:
        return self.media / name

    def cache(self, cache_id: str) -> Path:
        """The warm TeX/text cache for one tool identity; only the build parent writes here."""
        return self.build / ".cache" / cache_id

    def talk_files(self) -> list[Path]:
        """The talk file set, relative paths, sorted: every file under the talk folder except build/, dot-entries,
        __pycache__/ and root-level *.md (the talk README, and script.md, whose structure is compared separately and
        which scene code never reads)."""
        out: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in EXCLUDED_DIRS)
            here = Path(dirpath).relative_to(self.root)
            for f in filenames:
                if f.startswith(".") or (here == Path(".") and f.endswith(".md")):
                    continue
                out.append(here / f)
        return sorted(out)

    @property
    def clips(self) -> Path:
        return self.build / "clips"

    def clip(self, sha: str) -> Path:
        return self.clips / f"{sha}.mp4"

    def still(self, sha: str, stills_hash: str, which: Literal["first", "last"]) -> Path:
        """A clip's still, named by the hash of the code that extracted it, so a change to still extraction makes
        new stills from existing clips."""
        return self.clips / f"{sha}.{stills_hash}.{which}.png"

    @property
    def index_path(self) -> Path:
        return self.build / "index.json"

    def write_index(self, index: Index) -> None:
        """The last write of a commit, atomic: a reader sees a whole old build or a whole new one."""
        tmp = self.build / ".index.json.tmp"
        tmp.write_bytes(INDEX.dump_json(index, by_alias=True))
        os.replace(tmp, self.index_path)

    def previous(self) -> PreviousBuild | NoPrevious:
        if not self.index_path.exists():
            return NoPrevious(reason=Absent())
        raw = json.loads(self.index_path.read_bytes())
        if raw.get("schema") != SCHEMA:
            return NoPrevious(reason=SchemaMismatch(old=raw.get("schema", -1), new=SCHEMA))
        return PreviousBuild(index=INDEX.validate_python(raw))

    @contextlib.contextmanager
    def clips_shared(self) -> Generator[None]:
        """Readers (shots, export) hold this across opening the deck and reading clips: no commit can GC them."""
        with self._flock(".clips.lock", fcntl.LOCK_SH):
            yield

    @contextlib.contextmanager
    def clips_exclusive(self, on_wait: Callable[[], None]) -> Generator[None]:
        """A build's commit and GC, blocking until readers finish (`on_wait` runs once if it has to wait)."""
        self.build.mkdir(exist_ok=True)
        fd = os.open(self.build / ".clips.lock", os.O_RDWR | os.O_CREAT)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                on_wait()
                fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    @contextlib.contextmanager
    def _flock(self, name: str, mode: int) -> Generator[None]:
        self.build.mkdir(exist_ok=True)
        fd = os.open(self.build / name, os.O_RDWR | os.O_CREAT)
        try:
            fcntl.flock(fd, mode)
            yield
        finally:
            os.close(fd)

    def presenter_lock(self) -> int:
        """Exactly one Presenter per talk: an EX|NB flock held for the Presenter's lifetime. Raises Busy."""
        self.build.mkdir(exist_ok=True)
        fd = os.open(self.build / ".presenter.lock", os.O_RDWR | os.O_CREAT)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            raise Busy from None
        return fd

    def write_pins(self, shas: set[str]) -> None:
        """The clips a live Presenter shows or may replay; rewritten atomically on each adopt."""
        tmp = self.build / ".presenter.json.tmp"
        tmp.write_text(json.dumps(sorted(shas)))
        os.replace(tmp, self.build / ".presenter.json")

    def live_pins(self) -> set[str]:
        """The pins, exactly while a Presenter holds its lock (probed for microseconds); none otherwise."""
        path = self.build / ".presenter.lock"
        if not path.exists():
            return set()
        fd = os.open(path, os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:  # a live Presenter; before its first adopt it has written no pins, and pins none
            pins = self.build / ".presenter.json"
            return set(json.loads(pins.read_text())) if pins.exists() else set()
        finally:
            os.close(fd)
        return set()

    def gc(self, keep: set[str], pinned: set[str], cache_id: str) -> int:
        """Delete every file under clips/ that is neither named in `keep` (the new and previous indexes' clips and
        stills) nor of a sha a live Presenter pins (every file of it, stills included), and every TeX/text cache
        directory but this tool identity's. Call under clips_exclusive."""
        n = 0
        for f in self.clips.iterdir():
            if f.name not in keep and f.name.split(".")[0] not in pinned:
                f.unlink()
                n += 1
        for d in (self.build / ".cache").iterdir():
            if d.name != cache_id:
                shutil.rmtree(d)
        return n

    def files_of(self, index: Index) -> set[str]:
        """The clips/ file names an index references."""
        return {Path(p).name for b in index.beats for p in (self.clip(b.clip), b.first_png, b.last_png)}

    def build_lock(self) -> int:
        """Hold the one-build-at-a-time lock for this process's lifetime; returns its fd, inheritable, so every
        child of this build holds it too and it is released only when the last of them exits. Raises Busy."""
        self.build.mkdir(exist_ok=True)
        fd = os.open(self.build / ".build.lock", os.O_RDWR | os.O_CREAT)  # never truncated: the pid is display only
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            raise Busy from None
        os.ftruncate(fd, 0)
        os.write(fd, str(os.getpid()).encode())
        os.set_inheritable(fd, True)
        return fd

    @property
    def audience_log(self) -> Path:
        """The Audience process's stdout and stderr, truncated at each launch; outside .media, which builds wipe."""
        return self.build / "audience.log"

    @property
    def export_tmp(self) -> Path:
        """Scratch for `mpres export`'s re-encodes, outside .media, so a concurrent build's wipe never touches it."""
        return self.build / ".export"


def file_hashes(layout: Layout) -> dict[str, str]:
    return {str(p): hashlib.sha256((layout.root / p).read_bytes()).hexdigest() for p in layout.talk_files()}


class IncompatibleBuild(Exception):
    """No build this engine can read: `mpres build <talk>` makes one (and always succeeds at it)."""


class Stale(Exception):
    """The talk changed since its build; the message names what changed and the command to run."""


@dataclass(frozen=True)
class BuiltBeat:
    chapter: str
    slug: str
    title: str | None
    kind: BeatKind
    clip: Path
    first_png: Path
    last_png: Path
    frames: int


@dataclass(frozen=True)
class Deck:
    """The built talk: its beats in order, the render settings its clips were made with, and what changed since."""

    root: Path
    build_id: str
    render: Render
    beats: tuple[BuiltBeat, ...]
    stale: tuple[str, ...]  # talk files whose bytes differ from the build's, or that were added or removed
    structure: script.Structure  # the script.md structure the build was made from
    structure_mismatch: bool  # script.md's chapters, beats or titles differ from the build's

    @classmethod
    def open(cls, root: Path) -> "Deck":
        layout = Layout(root)
        previous = layout.previous()
        if isinstance(previous, NoPrevious):
            raise IncompatibleBuild(why_not(previous, root))
        index = previous.index
        beats = tuple(
            BuiltBeat(
                chapter=b.chapter,
                slug=b.slug,
                title=b.title,
                kind=b.kind,
                clip=layout.clip(b.clip),
                first_png=layout.build / b.first_png,
                last_png=layout.build / b.last_png,
                frames=b.frames,
            )
            for b in index.beats
        )
        missing = [str(p) for b in beats for p in (b.clip, b.first_png, b.last_png) if not p.exists()]
        if missing:
            raise IncompatibleBuild(f"{root}: the build lost {', '.join(missing)}; run: mpres build {root}")
        now = file_hashes(layout)
        stale = tuple(sorted(p for p in now.keys() | index.files.keys() if now.get(p) != index.files.get(p)))
        return cls(
            root=root,
            build_id=index.build_id,
            render=index.render,
            beats=beats,
            stale=stale,
            structure=index.structure,
            structure_mismatch=structure_mismatch((root / "script.md").read_text(encoding="utf-8"), index.structure),
        )


def why_not(none: NoPrevious, root: Path) -> str:
    match none.reason:
        case Absent():
            return f"{root} was never built; run: mpres build {root}"
        case SchemaMismatch(old=old, new=new):
            return (
                f"{root} was built by another engine version (index schema {old}, this engine reads {new}); "
                f"run: mpres build {root}"
            )


def structure_mismatch(text: str, built: script.Structure) -> bool:
    """script.md's chapters, beats and titles against the build's. The one comparison: the CLI refuses on it, and the
    Presenter's script.md watcher shows it. Raises ValueError for a script.md that does not parse."""
    return script.parse(text).structure != built


def require_fresh(deck: Deck) -> None:
    """For a fresh start (shots, export, a present with no live Audience): refuse a build the talk has moved past."""
    if deck.stale or deck.structure_mismatch:
        changed = [*deck.stale, *(["script.md headings"] if deck.structure_mismatch else [])]
        raise Stale(f"{deck.root} changed since its build ({', '.join(changed)}); run: mpres build {deck.root}")
