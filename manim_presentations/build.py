"""`mpres build <talk>`: lock → snapshot → pass 1 (one process per chapter) → checks → fingerprint and reuse →
chunked, verified render → join, stream check, stills → atomic commit → GC.

Every phase prints one line with its timing, line-buffered, so a watcher sees progress."""

import contextlib
import hashlib
import importlib
import json
import os
import shutil
import signal
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NoReturn

import numpy as np

from manim_presentations import clip, geometry, headroom, schedule, stills
from manim_presentations.deck import (
    SCHEMA,
    Absent,
    Busy,
    ChapterCost,
    Index,
    IndexBeat,
    Layout,
    NoPrevious,
    PreviousBuild,
    Render,
    SchemaMismatch,
    new_build_id,
)
from manim_presentations.geometry import Finding
from manim_presentations.records import CHAPTER_RECORD, BeatRecord, ChapterRecord, EmptyLoop, LoopBeat, PlainBeat
from manim_presentations.script import Chapter, Script
from manim_presentations.script import load as load_script
from manim_presentations.settings import Settings, SettingsError
from manim_presentations.settings import load as load_settings

MiB = 2**20
# Seeds for the pass-1 width until a previous build records this talk's own peaks: one synthetic Mixing-Deluxe-scale
# chapter (6 beats, 63 s of video) at 3456×2168 measured 0.93 cores and 246 MiB peak RSS (P0).
PASS1_CORES = 0.93
PASS1_RAM = 246 * MiB
WORKER_CORES = 1.3  # P2: one worker (tee + threads=1 encode) at 960×540 to 3456×2168, 1.15–1.3 cores
STILLS_HASH = hashlib.sha256(Path(stills.__file__).read_bytes()).hexdigest()[:12]


def worker_overhead(megapixels: float) -> int:
    """P2: a worker's RSS above its chapter's pass-1 peak (tee canvas + encoder), 70 MiB + 96 MiB per megapixel; the
    line through the 0.52 and 7.49 MP points over-estimates the 2.07 MP one, the safe side."""
    return int((70 + 96 * megapixels) * MiB)


class BuildError(Exception):
    def __init__(self, code: int, lines: list[str]):
        super().__init__("\n".join(lines))
        self.code, self.lines = code, lines


def say(line: str) -> None:
    print(line, flush=True)


def copy_file(src: Path, dst: Path) -> None:
    """The one copy route, for the snapshot and every private cache copy: copy2 measured within noise of clonefile
    (P0, DECISIONS) and works on every file system."""
    shutil.copy2(src, dst)


def copy_tree(src: Path, dst: Path) -> None:
    for dirpath, _, filenames in os.walk(src):
        here = Path(dirpath)
        (dst / here.relative_to(src)).mkdir(parents=True, exist_ok=True)
        for f in filenames:
            copy_file(here / f, dst / here.relative_to(src) / f)


def seed_caches(shared: Path, privates: list[Path]) -> None:
    """Each process's private copy of the warm cache, copied in parallel: the copies wait on the disk, not a core."""
    with ThreadPoolExecutor() as pool:
        list(pool.map(lambda p: copy_tree(shared, p), privates))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        sha256(tinytex() / "TinyTeX" / "tlpkg" / "texlive.tlpdb"),
    ]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Job:
    name: str
    module: str
    args: list[str]


@dataclass(frozen=True)
class Done:
    rss: int  # peak RSS, bytes
    cores: float  # CPU seconds over wall seconds


def spawn(job: Job, out: Path, env: dict[str, str]) -> int:
    """`python -P -m manim_presentations.<module> args…` with stdout/stderr in `out` (pipes would deadlock a parent
    blocked in wait4) and its own process group."""
    out.mkdir(parents=True, exist_ok=True)
    actions = [
        (os.POSIX_SPAWN_OPEN, 1, str(out / "stdout"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644),
        (os.POSIX_SPAWN_OPEN, 2, str(out / "stderr"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644),
    ]
    argv = [sys.executable, "-P", "-m", f"manim_presentations.{job.module}", *job.args]
    env = {**env, "MPRES_BUILD_PID": str(os.getpid())}
    return os.posix_spawn(sys.executable, argv, env, file_actions=actions, setsid=True)


def run_all(
    jobs: list[Job],
    width: int,
    env: dict[str, str],
    layout: Layout,
    phase: str,
) -> tuple[dict[str, Done], int]:
    """Run jobs with at most `width` alive. The first failure kills the rest and raises with its whole stderr.
    Returns ({name: its peak RSS and cores}, peak number alive)."""
    pending, alive, done, peak = list(jobs), dict[int, tuple[Job, float]](), dict[str, Done](), 0
    try:
        while pending or alive:
            while pending and len(alive) < width:
                job = pending.pop(0)
                alive[spawn(job, layout.process(job.name), env)] = (job, time.monotonic())
                peak = max(peak, len(alive))
            pid, status, usage = os.wait4(-1, 0)
            job, started = alive.pop(pid)
            wall = max(time.monotonic() - started, 1e-6)
            done[job.name] = Done(rss=usage.ru_maxrss, cores=(usage.ru_utime + usage.ru_stime) / wall)
            if os.waitstatus_to_exitcode(status) != 0:
                log = layout.process(job.name) / "stderr"
                raise BuildError(
                    1, [f"{phase} failed in {job.name} ({log}):", log.read_text(errors="replace").rstrip()]
                )
    finally:
        for pid in alive:
            # The child leads its own group (setsid), so TeX dies with it. macOS answers EPERM for a group whose
            # leader already exited (a zombie): nothing left to kill.
            with contextlib.suppress(PermissionError):
                os.killpg(pid, signal.SIGKILL)
        for pid in list(alive):
            os.waitpid(pid, 0)
    return done, peak


def pass1_jobs(layout: Layout, chapters: list[Chapter], settings: Settings, shared: Path) -> list[Job]:
    """One pass-1 job per chapter, each with a private copy of the warm cache: Manim writes into its cache even on a
    hit (a fixed-name temp SVG) and checks-then-writes on a miss, so chapters sharing a text would race."""
    jobs: list[Job] = []
    for c in chapters:
        name = f"pass1-{c.slug}"
        args = [
            str(layout.snapshot),
            c.slug,
            c.title or c.slug,
            settings.to_argv(),
            str(layout.process(name) / "cache"),
            str(tinytex()),
            str(layout.process(name)),
        ]
        jobs.append(Job(name, "pass1", args))
    seed_caches(shared, [layout.process(j.name) / "cache" for j in jobs])
    return jobs


def engine_code() -> str:
    """Every engine module: pass 1's output depends on how the engine records a chapter, so any engine edit re-runs
    every chapter's pass 1 (rendering still reuses every beat whose frames are unchanged)."""
    h = hashlib.sha256()
    for p in sorted(Path(__file__).parent.glob("*.py")):
        h.update(p.name.encode() + b"\0" + p.read_bytes())
    return h.hexdigest()


def library_code() -> str:
    """Every installed distribution, by the file hashes its installer recorded (RECORD): any library pass 1 can import
    (svgelements parses every Text), and a reinstall at the same version too. An edit made in place is not caught."""
    from importlib.metadata import distributions

    h = hashlib.sha256()
    for d in sorted(distributions(), key=lambda d: d.metadata["Name"]):
        record = d.read_text("RECORD")
        assert record is not None, f"{d.metadata['Name']} has no RECORD: reinstall the environment (uv sync)"
        h.update(d.metadata["Name"].encode() + b"\0" + record.encode())
    return h.hexdigest()


# What a chapter's scene processes see of the environment: these, and nothing else, so a chapter cannot depend on
# a variable the key does not hold. PATH finds the TeX binaries; HOME and the locale reach fonts and text shaping.
CHILD_ENV = ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "LC_CTYPE", "PYTHONPATH")


def pass1_base(
    engine: str, identity: dict[str, str], libraries: str, cache_id: str, env: dict[str, str], settings: str, title: str
) -> list[str]:
    """Everything a chapter's pass 1 depends on besides the talk files it reads: the engine, the drawing libraries,
    the TeX/text cache identity, the environment it runs in, the settings, and the chapter's own title."""
    return [
        engine,
        json.dumps(identity, sort_keys=True),
        libraries,
        cache_id,
        json.dumps(env, sort_keys=True),
        settings,
        title,
    ]


def pass1_key(base: list[str], snapshot: Path, inputs: tuple[str, ...]) -> str:
    """`base` and the current digest of each talk path the chapter depended on: a file's sha256 with its mode and
    mtime (what a stat shows; the snapshot keeps both), a stat'ed folder's mode and mtime, a listed folder's ("dir/")
    sorted entry names, or "absent" once gone."""
    h = hashlib.sha256(json.dumps(base).encode())
    for rel in inputs:
        p = snapshot / rel.rstrip("/")
        if rel.endswith("/"):
            digest = json.dumps(sorted(os.listdir(p))) if p.is_dir() else "absent"
        else:
            s = p.stat() if p.exists() else None
            shown = f"{s.st_mode} {s.st_mtime_ns}" if s else ""
            digest = f"{sha256(p)} {shown}" if p.is_file() else f"dir {shown}" if p.is_dir() else "absent"
        h.update(f"{rel}\0{digest}\0".encode())
    return h.hexdigest()


def pairing(script: Script, records: list[ChapterRecord]) -> list[Finding]:
    """script.md's chapters and beats against the talk.beat()/talk.loop() calls: same slugs, same order, same chapter
    membership. Slugs are unique on both sides (script.parse and Talk refuse repeats)."""
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


def width_for(phase: str, workers: int | None, jobs: int, cores: float, ram: int) -> tuple[int, str]:
    """(width, what it was chosen from), as headroom.choose decides; a job too big for the machine fails the build."""
    try:
        return headroom.choose(phase, workers, jobs, cores, ram, say)
    except headroom.TooBig as e:
        raise BuildError(1, [str(e)]) from None


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
                tmp = dst.with_name(f".tmp-{os.getpid()}-{f}")
                copy_file(src, tmp)
                os.replace(tmp, dst)
                n += 1
    return n


def prune_cache(shared: Path, records: list[ChapterRecord]) -> int:
    """After commit: keep only the entries some chapter's pass 1 opened or created (a reused chapter's record keeps
    the entries it opened when it last ran), so the cache never grows past what the talk uses."""
    used = {e for r in records for e in r.cache_entries}
    n = 0
    for dirpath, _, filenames in os.walk(shared):
        for f in filenames:
            if f not in used:
                (Path(dirpath) / f).unlink()
                n += 1
    return n


# Pixels that may differ between a loop's first frame and its end state: 0. P7(d) measured pixel-closed loops
# (Mixing Deluxe's cycle() pattern) byte-equal at 480×270, 1920×1080 and 3456×2168; the edge fixture's loops re-measure.
LOOP_TOLERANCE = 0


def loop_closure(out: Path, record: ChapterRecord) -> list[Finding]:
    """A loop wraps from its last frame to frame 0 with no jump only if the state after its last play draws exactly
    what frame 0 shows: compared as pixels, since identical pictures can come from different draw calls."""
    findings: list[Finding] = []
    for b in record.beats:
        match b:
            case LoopBeat():
                start, end = np.load(out / b.s_start), np.load(out / b.s_end)
                differ = int((np.abs(start.astype(int) - end.astype(int)) > LOOP_TOLERANCE).any(axis=-1).sum())
                if differ:
                    findings.append(
                        Finding(
                            "loop",
                            f'{record.file}:{b.line} loop "{b.slug}" does not close: its end '
                            f"state differs from its first frame in {differ} pixels; end where it "
                            "began, or make it talk.beat()",
                        )
                    )
            case PlainBeat() | EmptyLoop():
                pass
    return findings


def fail_checks(findings: list[Finding]) -> NoReturn:
    counts = Counter(f.kind for f in findings)
    raise BuildError(
        1,
        [f"error: {f.text}" for f in findings]
        + ["checks failed: " + " · ".join(f"{k} {n}" for k, n in sorted(counts.items()))],
    )


def fingerprint(identity: dict[str, str], settings: Settings, beat: BeatRecord) -> str:
    """A beat's frames as pass 1 recorded them, plus everything after the frames that shapes its clip's bytes: the
    render settings, clip.py and the drawing and encoding libraries (clip.identity). Nothing else from the engine."""
    render = [settings.pixel_width, settings.pixel_height, settings.frame_rate, settings.background]
    return hashlib.sha256(
        json.dumps([identity, render, [a.digest for a in beat.animations]], sort_keys=True).encode()
    ).hexdigest()


def build(talk: Path, workers: int | None) -> int:
    layout = Layout(talk)
    t0 = time.monotonic()
    try:
        lock = layout.build_lock()
    except Busy:
        raise BuildError(3, [f"a build is running on {talk}"]) from None
    if layout.media.exists():  # safe: holding the lock proves no earlier build process lives
        shutil.rmtree(layout.media)
    files = layout.talk_files()
    for rel in files:
        dst = layout.snapshot / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        copy_file(talk / rel, dst)
    say(f"snapshot: {len(files)} files · {time.monotonic() - t0:.2f}s")

    try:
        script = load_script(talk / "script.md")
        settings = load_settings(layout.snapshot)
    except (ValueError, SettingsError) as e:
        raise BuildError(1, [f"error: {e}"]) from None
    chapters = [c.slug for c in script.chapters]
    on_disk = sorted(p.stem for p in (layout.snapshot / "chapters").glob("*.py"))
    missing = [
        Finding("pairing", f'script.md:{c.line} names chapter "{c.slug}" but chapters/{c.slug}.py does not exist')
        for c in script.chapters
        if c.slug not in on_disk
    ]
    extra = [
        Finding("pairing", f"chapters/{s}.py is not named by any `# {s}` in script.md")
        for s in on_disk
        if s not in chapters
    ]
    if missing or extra:
        fail_checks([*missing, *extra])
    pass1_cores, pass1_ram = PASS1_CORES, PASS1_RAM
    old_costs: dict[str, ChapterCost] = {}
    old_beats: dict[str, IndexBeat] = {}
    old_files: set[str] = set()  # the previous index's files: kept one more build
    match layout.previous():
        case PreviousBuild(index=old):
            pass1_cores = max(c.pass1_cores for c in old.chapters.values())
            pass1_ram = max(c.pass1_rss for c in old.chapters.values())
            old_costs = dict(old.chapters)
            old_beats = {b.fingerprint: b for b in old.beats}
            old_files = layout.files_of(old)
        case NoPrevious(reason=reason):
            match reason:
                case Absent():
                    say("previous build: none")
                case SchemaMismatch(old=o, new=n):
                    say(f"previous build: none (schema {o}≠{n})")

    # Pass 1 and the checks.
    t1 = time.monotonic()
    cid = cache_id()
    shared = layout.cache(cid)
    shared.mkdir(parents=True, exist_ok=True)
    env = {**{k: os.environ[k] for k in CHILD_ENV if k in os.environ}, "PYTHONHASHSEED": "0"}
    tex_env = {**env, "PATH": (tinytex() / "bin-path").read_text().strip() + os.pathsep + os.environ["PATH"]}
    identity = clip.identity()
    common = (engine_code(), identity, library_code(), cid, tex_env, settings.to_argv())

    def base(c: Chapter) -> list[str]:
        return pass1_base(*common, c.title or c.slug)

    def reusable(c: Chapter) -> ChapterRecord | None:
        """The stored record, if the previous build committed it and nothing it read has changed since."""
        store = layout.pass1_store(c.slug)
        if c.slug not in old_costs or not (store / "key").exists():
            return None
        record = CHAPTER_RECORD.validate_json((store / "records.json").read_bytes())
        return record if (store / "key").read_text() == pass1_key(base(c), layout.snapshot, record.inputs) else None

    stored = {c.slug: r for c in script.chapters if (r := reusable(c)) is not None}
    fresh = [c for c in script.chapters if c.slug not in stored]
    jobs = pass1_jobs(layout, fresh, settings, shared)
    pass1_done: dict[str, Done] = {}
    width = peak = 0
    if jobs:
        width, _ = width_for("pass-1", workers, len(jobs), pass1_cores, pass1_ram)
        pass1_done, peak = run_all(jobs, width, tex_env, layout, "pass 1")
    outs = {c: layout.pass1_store(c) if c in stored else layout.process(f"pass1-{c}") for c in chapters}
    records = [stored.get(c) or CHAPTER_RECORD.validate_json((outs[c] / "records.json").read_bytes()) for c in chapters]
    costs = {
        c: old_costs[c]
        if c in stored
        else ChapterCost(pass1_rss=pass1_done[f"pass1-{c}"].rss, pass1_cores=pass1_done[f"pass1-{c}"].cores)
        for c in chapters
    }
    merged = merge_caches(layout, shared, [c.slug for c in fresh])
    say(
        f"pass 1: {len(jobs)} of {len(chapters)} chapters run, {len(stored)} reused · width {width} · peak alive "
        f"{peak} · {merged} new cache entries · {time.monotonic() - t1:.2f}s"
    )
    findings = pairing(script, records)
    for r in records:  # one chapter at a time: a beat's index (transient marks) is its index in its own chapter
        findings += [
            Finding(
                "empty-beat",
                f'{r.file}:{b.line} {b.call} "{b.slug}" has no animation; give it one (talk.wait() holds the frame)',
            )
            for b in r.beats
            if not b.animations
        ]
        findings += geometry.check(r.beats, settings)
        findings += loop_closure(outs[r.chapter], r)
    if findings:
        fail_checks(findings)

    # Fingerprint and reuse: a beat whose fingerprint the previous build committed, with its clip on disk, is reused.
    prints = {(r.chapter, b.slug): fingerprint(identity, settings, b) for r in records for b in r.beats}
    reused = {key for key, fp in prints.items() if fp in old_beats and layout.clip(old_beats[fp].clip).exists()}
    to_render = {
        r.chapter: {
            b.first_anim + j: t
            for b in r.beats
            if (r.chapter, b.slug) not in reused
            for j, t in enumerate(a.run_time for a in b.animations)
        }
        for r in records
    }
    to_render = {c: plays for c, plays in to_render.items() if plays}
    megapixels = settings.pixel_width * settings.pixel_height / 1e6
    reports, render_width = render(
        layout, script, settings, records, to_render, megapixels, workers, costs, shared, env
    )

    # Join, stream check and stills, per beat, in parallel.
    t3 = time.monotonic()
    layout.clips.mkdir(exist_ok=True)
    titles = {b.slug: b.title for c in script.chapters for b in c.beats}
    beats_in_order = [(r, b) for r in records for b in r.beats]
    # Joins and still extraction run across the render width; with nothing rendered, only missing stills need a pool.
    missing_stills = sum(
        1
        for r, b in beats_in_order
        if (r.chapter, b.slug) in reused
        for which in ("first", "last")
        if not layout.still(old_beats[prints[(r.chapter, b.slug)]].clip, STILLS_HASH, which).exists()
    )
    if render_width is not None:
        join_width = render_width
    elif missing_stills:
        join_width, _ = width_for("stills", workers, missing_stills, stills.DECODE_CORES, stills.decode_ram(megapixels))
    else:
        join_width = 1  # nothing to join or extract: no pool, no sample

    def finish(rb: tuple[ChapterRecord, BeatRecord]) -> IndexBeat:
        r, b = rb
        assert not isinstance(b, EmptyLoop), "the empty-beat check fails every empty loop"
        fp = prints[(r.chapter, b.slug)]
        if (r.chapter, b.slug) in reused:
            sha = old_beats[fp].clip
        else:
            parts = [Path(reports[(r.chapter, b.first_anim + j)]) for j in range(len(b.animations))]
            tmp = layout.media / "joined" / f"{r.chapter}-{b.slug}.mp4"
            tmp.parent.mkdir(exist_ok=True)
            frames = clip.join(parts, tmp)
            total = sum(a.frames for a in b.animations)
            if frames != total:
                raise BuildError(
                    1,
                    [f"{r.file}:{b.line} beat {b.slug}: joined {frames} frames, pass 1 wrote {total}"],
                )
            if errs := clip.stream_check(tmp, settings):
                raise BuildError(1, [f"{r.file}:{b.line} beat {b.slug}: stream check failed: {'; '.join(errs)}"])
            sha = sha256(tmp)
            os.replace(tmp, layout.clip(sha))  # verified, hashed, then at its content address
        return IndexBeat(
            chapter=r.chapter,
            slug=b.slug,
            title=titles[b.slug],
            kind=b.kind,
            fingerprint=fp,
            frames=sum(a.frames for a in b.animations),
            clip=sha,
            first_png=str(layout.still(sha, STILLS_HASH, "first").relative_to(layout.build)),
            last_png=str(layout.still(sha, STILLS_HASH, "last").relative_to(layout.build)),
        )

    def extract(job: tuple[str, Literal["first", "last"], int]) -> None:
        sha, which, index = job
        stills.still_at(layout.clip(sha), index, layout.still(sha, STILLS_HASH, which))

    with ThreadPoolExecutor(join_width) as pool:
        built = list(pool.map(finish, beats_in_order))
        # Each missing still once: two beats can share a clip (identical frames), so stills go by clip, not by beat.
        needed: dict[tuple[str, Literal["first", "last"]], int] = {}
        for b in built:
            needed[(b.clip, "first")] = 0
            needed[(b.clip, "last")] = b.frames - 1
        missing = [(sha, w, i) for (sha, w), i in needed.items() if not layout.still(sha, STILLS_HASH, w).exists()]
        list(pool.map(extract, missing))
    say(f"join: {len(built) - len(reused)} clips joined and stream-checked · {time.monotonic() - t3:.2f}s")

    # Commit: the index last and atomically; then GC everything no index or live Presenter references.
    t4 = time.monotonic()
    index = Index(
        schema=SCHEMA,
        build_id=new_build_id(),
        files={str(p): sha256(layout.snapshot / p) for p in files},
        chapters=costs,
        render=Render(pixel_width=settings.pixel_width, pixel_height=settings.pixel_height, fps=settings.frame_rate),
        structure=script.structure,
        beats=tuple(built),
    )
    with layout.clips_exclusive(lambda: say("commit: waiting for shots/export to finish")):
        layout.write_index(index)
        collected = layout.gc(layout.files_of(index) | old_files, layout.live_pins(), cid)
        store_pass1(
            layout,
            fresh,
            chapters,
            {c.slug: pass1_key(base(c), layout.snapshot, records[chapters.index(c.slug)].inputs) for c in fresh},
        )
    pruned = prune_cache(shared, records)
    shutil.rmtree(layout.media, ignore_errors=True)
    os.close(lock)  # last: the next build may wipe .media only once this one is done with it
    say(
        f"commit: {collected} old files collected · {pruned} unused cache entries pruned · {time.monotonic() - t4:.2f}s"
    )
    table(script, records, reused)
    say(f"built {layout.index_path} · {time.monotonic() - t0:.2f}s")
    return 0


def store_pass1(layout: Layout, fresh: list[Chapter], chapters: list[str], keys: dict[str, str]) -> None:
    """After the index commits: each freshly run chapter's pass-1 output becomes its store (replaced whole), and stores
    of chapters no longer in the talk go."""
    root = layout.build / "pass1"
    for c in fresh:
        out, store, tmp = layout.process(f"pass1-{c.slug}"), layout.pass1_store(c.slug), root / f".tmp-{c.slug}"
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir(parents=True)
        for f in [out / "records.json", *out.glob("*.npy")]:
            copy_file(f, tmp / f.name)
        (tmp / "key").write_text(keys[c.slug])
        if store.exists():
            shutil.rmtree(store)
        os.replace(tmp, store)
    for old in root.iterdir():
        if old.name not in chapters:
            shutil.rmtree(old)


def render(
    layout: Layout,
    script: Script,
    settings: Settings,
    records: list[ChapterRecord],
    to_render: dict[str, dict[int, float]],
    megapixels: float,
    workers: int | None,
    costs: dict[str, ChapterCost],
    shared: Path,
    env: dict[str, str],
) -> tuple[dict[tuple[str, int], str], int | None]:
    """Render the to-render plays in chunks on niced workers, and verify every rendered animation's digest against
    pass 1's. Returns {(chapter, play index): its verified partial file}."""
    t2 = time.monotonic()
    n_plays = sum(len(p) for p in to_render.values())
    # A beat renders whole or not at all, so its first play marks it; reused beats are the rest.
    beats = [(r.chapter, b) for r in records for b in r.beats if b.first_anim in to_render.get(r.chapter, {})]
    n_reused = sum(len(r.beats) for r in records) - len(beats)
    if not to_render:
        say(f"render: 0 beats · {n_reused} reused")
        return {}, None
    chunks = schedule.chunks(to_render, megapixels)
    titles = {c.slug: c.title or c.slug for c in script.chapters}
    worker_ram = max(costs[c].pass1_rss for c in to_render) + worker_overhead(megapixels)
    width, chosen = width_for("render", workers, len(chunks), WORKER_CORES, worker_ram)
    jobs = []
    for k, ch in enumerate(chunks):
        name = f"chunk-{k}"
        jobs.append(
            Job(
                name,
                "worker",
                [
                    str(layout.snapshot),
                    ch.chapter,
                    titles[ch.chapter],
                    settings.to_argv(),
                    str(layout.process(name) / "cache"),
                    str(layout.process(name)),
                    str(ch.first),
                    str(ch.last),
                ],
            )
        )

    seed_caches(shared, [layout.process(j.name) / "cache" for j in jobs])
    stop = threading.Event()

    def tail() -> None:
        """Every second, the plays the workers have rendered so far (one play index per line in their progress
        files) and the beats whose every play is rendered, printed as one progress line when they move."""
        last = -1
        while not stop.wait(1.0):
            seen = {
                (ch.chapter, int(line))
                for ch, j in zip(chunks, jobs, strict=True)
                if (f := layout.process(j.name) / "progress").exists()
                for line in f.read_text().split("\n")[:-1]  # complete lines only: a worker may be mid-write
            }
            if len(seen) != last:
                last = len(seen)
                whole = sum(all((c, b.first_anim + i) in seen for i in range(len(b.animations))) for c, b in beats)
                say(
                    f"render: {len(seen)}/{n_plays} animations · {whole}/{len(beats)} beats · {width} workers · "
                    f"{time.monotonic() - t2:.0f}s"
                )

    reader = threading.Thread(target=tail, daemon=True)
    reader.start()
    try:
        done, peak = run_all(jobs, width, env, layout, "render")
    finally:
        stop.set()
        reader.join()
    expected = {
        (r.chapter, b.first_anim + j): (r.file, b, d)
        for r in records
        for b in r.beats
        for j, d in enumerate(a.digest for a in b.animations)
    }
    reports: dict[tuple[str, int], str] = {}
    for k, ch in enumerate(chunks):
        for entry in json.loads((layout.process(f"chunk-{k}") / "report.json").read_text()):
            file, beat, digest = expected[(ch.chapter, entry["anim"])]
            if entry["digest"] != digest:
                raise BuildError(
                    1,
                    [
                        f"{file}:{beat.line} beat {beat.slug}: animation {entry['anim']} drew different "
                        "frames in its worker than in pass 1: the chapter is nondeterministic. Check the "
                        "landmines: no sets of mobjects (hashed by id), no clock reads."
                    ],
                )
            reports[(ch.chapter, entry["anim"])] = entry["partial"]
    missing = sorted(set(expected) & {(c, p) for c, plays in to_render.items() for p in plays} - set(reports))
    assert not missing, f"plays rendered by no chunk: {missing}"
    max_rss = max(d.rss for d in done.values())
    say(
        f"render: {len(beats)} beats ({len(reports)} animations) in {len(chunks)} chunks · {n_reused} reused · "
        f"peak alive {peak} · {width} workers ({chosen}, {worker_ram / 2**30:.2f} GB/worker est, "
        f"{max_rss / 2**30:.2f} GB peak) · digests verified · {time.monotonic() - t2:.2f}s"
    )
    return reports, width


def table(script: Script, records: list[ChapterRecord], reused: set[tuple[str, str]]) -> None:
    n = 0
    for r in records:
        for b in r.beats:
            n += 1
            state = "reused" if (r.chapter, b.slug) in reused else "rendered"
            say(
                f"{n:>3}  {b.slug:<24} {b.kind:<4}  {len(b.animations):>2} anim  "
                f"{sum(a.run_time for a in b.animations):6.2f}s  "
                f"{state:<8}  {r.file}:{b.line}"
            )
