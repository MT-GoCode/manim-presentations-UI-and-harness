"""Pass 1 for one chapter, in its own process: run the chapter's scene with no pixels under the frame recorder and
write what the build checks and fingerprints to <out>/records.json.

    python -P -m manim_presentations.pass1 <snapshot> <chapter> <title> <settings-json> <cache> <tinytex> <out>

The first statement changes into the snapshot, before anything imports manim (Manim reads ./manim.cfg at import)."""

import os
import sys

if __name__ == "__main__":
    os.chdir(sys.argv[1])

import tempfile
import threading
from os.path import realpath
from pathlib import Path
from typing import Any

READ_EVENTS = frozenset({"open", "os.listdir", "os.scandir", "glob.glob"})
SYSTEM_ROOTS = ("/System", "/usr", "/Library", "/opt/homebrew", "/dev/null")
EXCLUSIVE_CREATE = os.O_CREAT | os.O_EXCL


def watch_parent() -> None:
    """A killed build never leaves a pass-1 child writing into build/.media (vendored from Explainers' render.py)."""
    parent = os.getppid()

    def watch() -> None:
        while True:
            threading.Event().wait(1)
            if os.getppid() != parent:
                os._exit(1)

    threading.Thread(target=watch, daemon=True).start()


def cannot_read(flags: int) -> bool:
    """An open that cannot return existing bytes: write-only, or an exclusive create (`tempfile` probes its directory
    with O_RDWR | O_CREAT | O_EXCL, which only ever makes a new, empty file)."""
    return flags & os.O_ACCMODE == os.O_WRONLY or flags & EXCLUSIVE_CREATE == EXCLUSIVE_CREATE


class ReadGuard:
    """An audit hook, live only while `active`. It fails any read outside an exact allow-list of roots (raising in the
    audited call, and listing the violation, so a try/except in talk code cannot swallow it), and records which
    private TeX/text cache entries were opened or created (observation only). Roots are compared after realpath:
    /tmp and /var are symlinks into /private."""

    def __init__(self, snapshot: Path, cache: Path, tinytex: Path):
        import manim_presentations

        self.cache = realpath(cache)
        package = Path(manim_presentations.__file__).parent
        self.roots = tuple(
            realpath(p) for p in (snapshot, sys.prefix, sys.base_prefix, package, tinytex, cache, *SYSTEM_ROOTS)
        )
        self.listing_roots = tuple(realpath(p) for p in sys.path if p)  # importlib scans every sys.path entry
        self.write_roots = (realpath(tempfile.gettempdir()),)
        self.active = False
        self.violations: list[str] = []
        self.cache_entries: set[str] = set()

    def __call__(self, event: str, args: tuple[Any, ...]) -> None:
        if not self.active or event not in READ_EVENTS:
            return
        path = args[0]
        if not isinstance(path, (str, bytes, os.PathLike)):  # a file descriptor or None: already opened, or cwd
            return
        p = realpath(os.fsdecode(path))
        if p.startswith(self.cache + os.sep):
            self.cache_entries.add(os.path.basename(p))
        roots = self.roots
        if event != "open":
            roots += self.listing_roots
        elif cannot_read(args[2]):
            roots += self.write_roots
        if not any(p == r or p.startswith(r + os.sep) for r in roots):
            self.violations.append(p)
            raise PermissionError(f"a talk reads only files inside its own folder; {p} is outside it")


def main(argv: list[str]) -> int:
    snapshot, slug, title, settings_json, cache, tinytex, out = argv
    snapshot_path, cache_path, out_path = Path(snapshot), Path(cache), Path(out)
    watch_parent()
    os.nice(10)
    import manim  # noqa: F401  — Manim's own bytecode is still used; ours is never written

    sys.dont_write_bytecode = True
    from manim import config

    from manim_presentations import clip, manim_hooks
    from manim_presentations.records import CHAPTER_RECORD, ChapterRecord
    from manim_presentations.settings import Settings
    from manim_presentations.talk import Pass1Talk, TalkError

    chapter = snapshot_path / "chapters" / f"{slug}.py"
    where = chapter.relative_to(snapshot_path)
    guard = ReadGuard(snapshot_path, cache_path, Path(tinytex))
    sys.addaudithook(guard)
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
    scene: Pass1Talk | None = None
    failure: Exception | None = None
    guard.active = True
    try:
        scene = Pass1Talk(chapter, snapshot_path, title, clip.RecordContext)
        scene.render()
    except Exception as e:  # routed below: the guard's own mark first, then an authoring error, then a real crash
        failure = e
    finally:
        guard.active = False
    if guard.violations:  # whether or not talk code caught the PermissionError
        for v in dict.fromkeys(guard.violations):
            print(
                f"error: {where} read {v}, outside the talk folder; copy it into assets/ and read it through talk.root",
                file=sys.stderr,
            )
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
    )
    (out_path / "records.json").write_bytes(CHAPTER_RECORD.dump_json(record))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
