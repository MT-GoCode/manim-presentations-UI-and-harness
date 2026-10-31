"""`mpres build <talk>`: lock → snapshot → pass 1 (one process per chapter, in parallel) → checks.

Every phase prints one line with its timing, line-buffered, so a watcher sees progress."""

import contextlib
import hashlib
import importlib
import os
import shutil
import signal
import sys
import threading
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from manim_presentations import geometry, headroom
from manim_presentations.deck import Busy, Layout
from manim_presentations.geometry import Finding
from manim_presentations.records import CHAPTER_RECORD, ChapterRecord
from manim_presentations.script import Script
from manim_presentations.script import load as load_script
from manim_presentations.settings import SettingsError
from manim_presentations.settings import load as load_settings

# P0 seeds for the pass-1 width, used until a previous build's index records this talk's own peaks.
PASS1_CORES = None  # set from P0
PASS1_RAM = None  # set from P0


class BuildError(Exception):
    def __init__(self, code: int, lines: list[str]):
        super().__init__("\n".join(lines))
        self.code, self.lines = code, lines


def say(line: str) -> None:
    print(line, flush=True)


def copy_file(src: Path, dst: Path) -> None:
    """The one copy route, for the snapshot and every private cache copy (P0)."""
    shutil.copy2(src, dst)


def copy_tree(src: Path, dst: Path) -> None:
    for dirpath, _, filenames in os.walk(src):
        here = Path(dirpath)
        (dst / here.relative_to(src)).mkdir(parents=True, exist_ok=True)
        for f in filenames:
            copy_file(here / f, dst / here.relative_to(src) / f)


def tinytex() -> Path:
    """The engine repo's own TeX (setup.sh installs it next to the package)."""
    return Path(__file__).resolve().parents[1] / ".tinytex"


def cache_id() -> str:
    """The TeX/text cache is keyed by the identity of the tools that fill it: Manim keys entries on text and template
    only, so without this a Pango or TeX upgrade would keep old glyphs forever. manimpango bundles its own Pango and
    cairo; TinyTeX's package database pins every TeX package's revision, dvisvgm included."""
    manimpango = importlib.import_module("manimpango")  # a C extension with no type information

    parts = [
        manimpango.__version__,
        manimpango.pango_version(),
        manimpango.cairo_version(),
        hashlib.sha256((tinytex() / "TinyTeX" / "tlpkg" / "texlive.tlpdb").read_bytes()).hexdigest(),
    ]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Child:
    name: str
    out: Path


def spawn(module: str, args: list[str], out: Path, env: dict[str, str]) -> int:
    """`python -P -m manim_presentations.<module> args…` with stdout/stderr in `out` (pipes would deadlock a parent
    blocked in wait4) and its own process group."""
    out.mkdir(parents=True, exist_ok=True)
    actions = [
        (os.POSIX_SPAWN_OPEN, 1, str(out / "stdout"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644),
        (os.POSIX_SPAWN_OPEN, 2, str(out / "stderr"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644),
    ]
    argv = [sys.executable, "-P", "-m", f"manim_presentations.{module}", *args]
    return os.posix_spawn(sys.executable, argv, env, file_actions=actions, setsid=True)


def run_all(
    jobs: list[tuple[str, str, list[str]]], width: int, env: dict[str, str], layout: Layout, phase: str
) -> tuple[dict[str, int], int]:
    """Run (name, module, args) jobs with at most `width` alive. The first failure kills the rest and raises with its
    stderr. Returns ({name: peak RSS bytes}, peak number alive)."""
    pending, alive, rss, peak = list(jobs), dict[int, Child](), dict[str, int](), 0
    try:
        while pending or alive:
            while pending and len(alive) < width:
                name, module, args = pending.pop(0)
                out = layout.process(name)
                alive[spawn(module, args, out, env)] = Child(name, out)
                peak = max(peak, len(alive))
            pid, status, usage = os.wait4(-1, 0)
            child = alive.pop(pid)
            rss[child.name] = usage.ru_maxrss  # bytes on macOS
            if os.waitstatus_to_exitcode(status) != 0:
                err = (child.out / "stderr").read_text(errors="replace").rstrip().splitlines()
                raise BuildError(1, [f"{phase} failed in {child.name}:", *err[-40:]])
    finally:
        for pid in alive:
            # The child leads its own group (setsid), so TeX dies with it. macOS answers EPERM for a group whose
            # leader already exited (a zombie): nothing left to kill.
            with contextlib.suppress(PermissionError):
                os.killpg(pid, signal.SIGKILL)
        for pid in list(alive):
            os.waitpid(pid, 0)
    return rss, peak


def pairing(script: Script, records: list[ChapterRecord]) -> list[Finding]:
    """script.md's chapters and beats against the talk.beat()/talk.loop() calls: same slugs, same order, same chapter
    membership."""
    errs: list[Finding] = []
    by_chapter = {r.chapter: r for r in records}
    for c in script.chapters:
        r = by_chapter[c.slug]
        heads, calls = [b.slug for b in c.beats], [b.slug for b in r.beats]
        line = {b.slug: b.line for b in r.beats}
        errs += [
            Finding("pairing", f'script.md:{b.line} has "## {b.slug}" but {r.file} has no talk.beat/loop("{b.slug}")')
            for b in c.beats
            if b.slug not in calls
        ]
        errs += [
            Finding(
                "pairing",
                f'{r.file}:{line[s]} calls talk.beat/loop("{s}") but script.md has no "## {s}" under "# {c.slug}"',
            )
            for s in calls
            if s not in heads
        ]
        if heads != calls and set(heads) == set(calls):
            n = next(i for i, (a, b) in enumerate(zip(heads, calls, strict=True)) if a != b)
            errs.append(
                Finding(
                    "pairing",
                    f'{r.file}:{line[calls[n]]} order differs at beat {n + 1} of "{c.slug}": '
                    f'script.md "## {heads[n]}", chapter "{calls[n]}"',
                )
            )
    return errs


def build(talk: Path, workers: int | None) -> int:
    layout = Layout(talk)
    t0 = time.monotonic()
    try:
        lock = layout.build_lock()
    except Busy:
        raise BuildError(3, [f"a build is running on {talk}"]) from None
    shutil.rmtree(layout.media, ignore_errors=True)  # safe: holding the lock proves no earlier build process lives
    files = layout.talk_files()
    for rel in files:
        dst = layout.snapshot / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        copy_file(talk / rel, dst)
    say(f"snapshot: {len(files)} files · {time.monotonic() - t0:.2f}s")

    script = load_script(talk / "script.md")
    try:
        settings = load_settings(layout.snapshot)
    except SettingsError as e:
        raise BuildError(1, [str(e)]) from None
    chapters = [c.slug for c in script.chapters]
    on_disk = sorted(p.stem for p in (layout.snapshot / "chapters").glob("*.py"))
    extra = [
        Finding("pairing", f"chapters/{s}.py is not named by any `# {s}` in script.md")
        for s in on_disk
        if s not in chapters
    ]
    missing = [
        Finding("pairing", f'script.md:{c.line} names chapter "{c.slug}" but chapters/{c.slug}.py does not exist')
        for c in script.chapters
        if c.slug not in on_disk
    ]
    if extra or missing:
        report([*missing, *extra])

    t1 = time.monotonic()
    cid = cache_id()
    shared = layout.cache(cid)
    shared.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "PYTHONHASHSEED": "0",
        "PATH": (tinytex() / "bin-path").read_text().strip() + os.pathsep + os.environ["PATH"],
    }
    jobs = []
    for c in script.chapters:
        private = layout.process(f"pass1-{c.slug}") / "cache"
        copy_tree(shared, private)
        args = [
            str(layout.snapshot),
            c.slug,
            c.title or c.slug,
            settings.to_argv(),
            str(private),
            str(tinytex()),
            str(layout.process(f"pass1-{c.slug}")),
        ]
        jobs.append((f"pass1-{c.slug}", "pass1", args))
    width = pass1_width(workers, len(jobs))
    rss, peak = run_all(jobs, width, env, layout, "pass 1")
    records = [
        CHAPTER_RECORD.validate_json((layout.process(f"pass1-{c}") / "records.json").read_bytes()) for c in chapters
    ]
    merged = merge_caches(layout, shared, chapters)
    say(
        f"pass 1: {len(jobs)} chapters · width {width} · peak alive {peak} · max RSS "
        f"{max(rss.values()) / 2**30:.2f} GB · {merged} new cache entries · {time.monotonic() - t1:.2f}s"
    )

    findings = pairing(script, records)
    findings += [
        Finding(
            "empty-beat",
            f'{r.file}:{b.line} beat "{b.slug}" has no animation; give it one (talk.wait() holds the frame)',
        )
        for r in records
        for b in r.beats
        if not b.run_times
    ]
    findings += geometry.check(
        [b for r in records for b in r.beats], settings.frame_width, settings.frame_height, settings.pixel_width
    )
    if findings:
        report(findings)
    say(f"checks passed · {time.monotonic() - t0:.2f}s")
    os.close(lock)
    shutil.rmtree(layout.media, ignore_errors=True)
    return 0


def pass1_width(workers: int | None, jobs: int) -> int:
    if workers is not None:
        say(f"pass-1 width: {workers} (--workers)")
        return workers
    import psutil

    if jobs == 1:
        tagged = headroom.ram_only(psutil.virtual_memory().available, PASS1_RAM)
    else:
        h = headroom.sample(headroom.MIN_SAMPLE_WINDOW)
        tagged = headroom.width(h, PASS1_CORES, PASS1_RAM, jobs)
        say(
            f"headroom: idle {h.idle_cores:.1f} cores, {h.available_ram / 2**30:.0f} GB free · "
            f"machine: idle_cores={h.idle_cores!r} available_ram={h.available_ram} per_job_cores={PASS1_CORES!r} "
            f"per_job_ram={PASS1_RAM} jobs={jobs}"
        )
    match tagged:
        case headroom.Width(n):
            return n
        case headroom.RamExceeded(per_job, available):
            raise BuildError(
                1,
                [
                    f"one pass-1 job needs {per_job / 2**30:.1f} GB, more than 75% of the "
                    f"{available / 2**30:.1f} GB free; pass --workers 1 to run it anyway"
                ],
            )


def merge_caches(layout: Layout, shared: Path, chapters: list[str]) -> int:
    """Only the parent writes the shared cache: each new entry from each chapter's private copy, temp-written then
    renamed. Entries are content-addressed by file name, so the merge is idempotent."""
    n = 0
    for c in chapters:
        private = layout.process(f"pass1-{c}") / "cache"
        for dirpath, _, filenames in os.walk(private):
            for f in filenames:
                src = Path(dirpath) / f
                dst = shared / src.relative_to(private)
                if dst.exists():
                    continue
                dst.parent.mkdir(parents=True, exist_ok=True)
                tmp = dst.with_name(f".tmp-{os.getpid()}-{threading.get_ident()}-{f}")
                copy_file(src, tmp)
                os.replace(tmp, dst)
                n += 1
    return n


def report(findings: list[Finding]) -> None:
    counts = Counter(f.kind for f in findings)
    raise BuildError(
        1,
        [f"error: {f.text}" for f in findings]
        + ["checks failed: " + " · ".join(f"{k} {n}" for k, n in sorted(counts.items()))],
    )
