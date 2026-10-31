"""Pass 1 for one chapter, in its own process: run the chapter's scene with no pixels under the frame recorder and
write what the build checks and fingerprints to <out>/records.json.

    python -P -m manim_presentations.pass1 <snapshot> <chapter> <title> <settings-json> <cache> <tinytex> <out>

The first statement changes into the snapshot, before anything imports manim (Manim reads ./manim.cfg at import)."""

import os
import sys

if __name__ == "__main__":
    os.chdir(sys.argv[1])

import shutil
import tempfile
import threading
from os.path import realpath
from pathlib import Path
from typing import Any

READ_EVENTS = frozenset({"open", "os.listdir", "os.scandir", "glob.glob"})
# A child process reads files no audit event shows, so a chapter may start only TinyTeX's own programs (Manim's
# latex and dvisvgm calls).
SPAWN_EVENTS = frozenset({"subprocess.Popen", "os.posix_spawn", "os.exec", "os.system", "os.spawn"})
SYSTEM_ROOTS = ("/System", "/usr", "/Library", "/opt/homebrew", "/dev/null")
EXCLUSIVE_CREATE = os.O_CREAT | os.O_EXCL


def cannot_read(flags: int) -> bool:
    """An open that cannot return existing bytes: write-only, or an exclusive create (O_RDWR | O_CREAT | O_EXCL only
    ever makes a new, empty file; `tempfile` opens its files that way)."""
    return flags & os.O_ACCMODE == os.O_WRONLY or flags & EXCLUSIVE_CREATE == EXCLUSIVE_CREATE


class ReadGuard:
    """An audit hook, live only while `active`. It fails any read outside an exact allow-list of roots (raising in the
    audited call, and listing the violation, so a try/except in talk code cannot swallow it), and records which
    private TeX/text cache entries were opened or created and which talk files and folders were read (observation
    only: they key the chapter's reuse by the next build). Roots are compared after realpath:
    /tmp and /var are symlinks into /private."""

    def __init__(self, snapshot: Path, cache: Path, tinytex: Path):
        import manim_presentations

        self.cache = realpath(cache)
        self.snapshot = realpath(snapshot)
        self.tinytex = realpath(tinytex)
        package = Path(manim_presentations.__file__).parent
        self.roots = tuple(
            realpath(p) for p in (snapshot, sys.prefix, sys.base_prefix, package, tinytex, cache, *SYSTEM_ROOTS)
        )
        self.listing_roots = tuple(realpath(p) for p in sys.path if p)  # importlib scans every sys.path entry
        # tempfile opens its directory itself (O_RDWR | O_CREAT on a directory: no file bytes); nothing inside it
        self.tempdir = realpath(tempfile.gettempdir())
        self.active = False
        self.violations: list[str] = []  # what the chapter did, ending its error line
        self.cache_entries: set[str] = set()
        self.inputs: set[str] = set()  # snapshot-relative: files opened or stat'ed, and folders listed (as "dir/")
        self.quiet = threading.local()  # per thread: the guard's own stats (in realpath) are not the chapter's

    def own(self, path: str) -> str:
        """realpath without noting the stats it makes."""
        self.quiet.on = True
        try:
            return realpath(path)
        finally:
            self.quiet.on = False

    def __call__(self, event: str, args: tuple[Any, ...]) -> None:
        if not self.active:
            return
        if event in SPAWN_EVENTS:
            self.spawned(event, args)
            return
        if event not in READ_EVENTS:
            return
        path = args[0]
        if not isinstance(path, (str, bytes, os.PathLike)):  # a file descriptor or None: already opened, or cwd
            return
        p = self.own(os.fsdecode(path))
        self.note(p, listed=event != "open")
        if event == "open":
            if p.startswith(self.cache + os.sep):
                self.cache_entries.add(os.path.basename(p))
            if cannot_read(args[2]):  # only reads are checked; writes are confined by dry_run and media_dir
                return
        roots = self.roots + (self.listing_roots if event != "open" else ())
        if not (event == "open" and p == self.tempdir) and not any(p == r or p.startswith(r + os.sep) for r in roots):
            self.violations.append(
                f"read {p}, outside the talk folder; copy it into assets/ and read it through talk.root"
            )
            raise PermissionError(f"a talk reads only files inside its own folder; {p} is outside it")

    def note(self, p: str, listed: bool) -> None:
        """A talk path the chapter depends on: a file it opened or stat'ed, or a folder it listed ("dir/")."""
        if p == self.snapshot or p.startswith(self.snapshot + os.sep):
            rel = os.path.relpath(p, self.snapshot)
            self.inputs.add(rel.rstrip("/") + "/" if listed else rel)

    def spawned(self, event: str, args: tuple[Any, ...]) -> None:
        """Refuse any child process but TinyTeX's programs: what a child reads is invisible to this guard."""
        match event:
            case "subprocess.Popen":
                command = args[0] or (args[1] if isinstance(args[1], (str, bytes, os.PathLike)) else args[1][0])
            case "os.system":
                command = os.fsdecode(args[0]).split()[0]
            case _:
                command = args[0]
        found = shutil.which(os.fsdecode(command)) or os.fsdecode(command)
        program = self.own(found)
        if not program.startswith(self.tinytex + os.sep):
            self.violations.append(f"started {program}; a talk may not start other programs")
            raise PermissionError(f"a talk may not start other programs; it started {program}")

    def stat(self, real: Any) -> Any:
        """os.stat/os.lstat/os.access noting their path: CPython raises no audit event for these, yet
        `Path.exists()`, `.stat()` and `os.access()` decide what a chapter draws as surely as a read does."""

        def noted(path: Any, *args: Any, **kwargs: Any) -> Any:
            if self.active and not getattr(self.quiet, "on", False) and isinstance(path, (str, bytes, os.PathLike)):
                self.note(self.own(os.fsdecode(path)), listed=False)
            return real(path, *args, **kwargs)

        return noted


def main(argv: list[str]) -> int:
    snapshot, slug, title, settings_json, cache, tinytex, out = argv
    snapshot_path, cache_path, out_path = Path(snapshot), Path(cache), Path(out)
    os.nice(10)
    import manim  # noqa: F401  — Manim's own bytecode is still used; ours is never written

    sys.dont_write_bytecode = True
    from manim import config

    from manim_presentations import clip, manim_hooks
    from manim_presentations.records import CHAPTER_RECORD, ChapterRecord
    from manim_presentations.settings import Settings
    from manim_presentations.talk import Pass1Talk, TalkError, watch_parent

    watch_parent()

    chapter = snapshot_path / "chapters" / f"{slug}.py"
    where = chapter.relative_to(snapshot_path)
    guard = ReadGuard(snapshot_path, cache_path, Path(tinytex))
    sys.addaudithook(guard)
    os.stat, os.lstat, os.access = guard.stat(os.stat), guard.stat(os.lstat), guard.stat(os.access)
    clip.render_config(Settings.from_argv(settings_json))
    config.update(
        {
            "dry_run": True,
            "media_dir": str(out_path / "media"),
            "tex_dir": str(cache_path / "tex"),
            "text_dir": str(cache_path / "text"),
        }
    )
    manim_hooks.record_creation_lines(frozenset({str(chapter)}))
    manim_hooks.install_size_references()
    scene: Pass1Talk | None = None
    failure: Exception | None = None
    guard.active = True
    try:
        scene = Pass1Talk(chapter, snapshot_path, title, clip.RecordContext, out_path)
        scene.render()
    except Exception as e:  # routed below: the guard's own mark first, then an authoring error, then a real crash
        failure = e
    finally:
        guard.active = False
    if guard.violations:  # whether or not talk code caught the PermissionError
        for v in dict.fromkeys(guard.violations):
            print(f"error: {where} {v}", file=sys.stderr)
        return 1
    if isinstance(failure, TalkError):
        print(f"error: {failure}", file=sys.stderr)
        return 1
    if failure is not None:
        raise failure
    assert scene is not None
    record = ChapterRecord(
        chapter=slug,
        file=str(where),
        beats=tuple(b.record() for b in scene.beats),
        cache_entries=tuple(sorted(guard.cache_entries)),
        inputs=tuple(sorted(guard.inputs)),
    )
    (out_path / "records.json").write_bytes(CHAPTER_RECORD.dump_json(record))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
