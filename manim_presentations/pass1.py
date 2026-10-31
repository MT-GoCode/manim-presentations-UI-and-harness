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
from pathlib import Path
from typing import Any

READ_EVENTS = frozenset({"open", "os.listdir", "os.scandir", "glob.glob"})
SYSTEM_ROOTS = ("/System", "/usr", "/Library", "/opt/homebrew", "/dev/null")


def watch_parent() -> None:
    """A killed build never leaves a pass-1 child writing into build/.media (vendored from Explainers' render.py)."""
    parent = os.getppid()

    def watch() -> None:
        while True:
            threading.Event().wait(1)
            if os.getppid() != parent:
                os._exit(1)

    threading.Thread(target=watch, daemon=True).start()


class ReadGuard:
    """An audit hook, live only while `active`. It fails any read outside an exact allow-list of roots (raising in the
    audited call, and listing the violation, so a try/except in talk code cannot swallow it), and records which
    private TeX/text cache entries were opened or created (observation only)."""

    def __init__(self, snapshot: Path, cache: Path, tinytex: Path):
        import manim_presentations

        real = lambda p: os.path.realpath(p)  # noqa: E731 — /tmp and /var are symlinks into /private
        self.cache = real(cache)
        self.roots = tuple(
            real(p)
            for p in (snapshot, sys.prefix, sys.base_prefix, Path(manim_presentations.__file__).parent, tinytex, cache)
        ) + tuple(real(p) for p in SYSTEM_ROOTS)
        self.listing_roots = tuple(real(p) for p in sys.path if p)
        self.write_roots = (real(tempfile.gettempdir()),)
        self.active = False
        self.violations: list[str] = []
        self.cache_entries: set[str] = set()

    def __call__(self, event: str, args: tuple[Any, ...]) -> None:
        if not self.active or event not in READ_EVENTS:
            return
        path, writing = args[0], False
        if event == "open":
            mode, flags = args[1], args[2]
            writing = bool(mode and any(c in mode for c in "wax+")) or bool(flags & (os.O_WRONLY | os.O_RDWR))
        if not isinstance(path, (str, bytes, os.PathLike)):  # a file descriptor or None: already opened, or cwd
            return
        p = os.path.realpath(os.fsdecode(path))
        if p.startswith(self.cache + os.sep):
            self.cache_entries.add(os.path.basename(p))
        roots = self.roots + (self.listing_roots if event != "open" else ()) + (self.write_roots if writing else ())
        if not any(p == r or p.startswith(r + os.sep) for r in roots):
            self.violations.append(p)
            raise PermissionError(
                f"a talk reads only files inside its own folder; {p} is outside it "
                "(copy it into assets/ and read it through talk.root)"
            )


def main(argv: list[str]) -> int:
    snapshot, slug, title, settings_json, cache, tinytex, out = argv
    snapshot_path, cache_path, out_path = Path(snapshot), Path(cache), Path(out)
    watch_parent()
    os.nice(10)
    import manim  # noqa: F401 — Manim's own bytecode is still used; ours never written

    sys.dont_write_bytecode = True
    from manim import config

    from manim_presentations import clip, manim_hooks
    from manim_presentations.records import CHAPTER_RECORD, ChapterRecord
    from manim_presentations.settings import Settings
    from manim_presentations.talk import Pass1Talk, TalkError

    chapter = snapshot_path / "chapters" / f"{slug}.py"
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
    guard.active = True
    try:
        scene = Pass1Talk(chapter, snapshot_path, title)
        scene.render()
    except TalkError as e:
        guard.active = False
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        guard.active = False
    if guard.violations:  # also when talk code caught the PermissionError
        for v in dict.fromkeys(guard.violations):
            print(
                f"error: {chapter.relative_to(snapshot_path)} read {v}, outside the talk folder; copy it into "
                "assets/ and read it through talk.root",
                file=sys.stderr,
            )
        return 1
    record = ChapterRecord(
        chapter=slug,
        file=str(chapter.relative_to(snapshot_path)),
        beats=tuple(b.record() for b in scene.beats),
        cache_entries=tuple(sorted(guard.cache_entries)),
    )
    (out_path / "records.json").write_bytes(CHAPTER_RECORD.dump_json(record))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
