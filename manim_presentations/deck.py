"""The built talk as data. This module owns everything under a talk's build/ folder: no other module builds a
build/... path. It also defines the talk file set, the files whose bytes can change what the talk shows."""

import fcntl
import os
from pathlib import Path

EXCLUDED_DIRS = frozenset({"build", "__pycache__"})


class Busy(Exception):
    """Another build holds the build lock."""


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
