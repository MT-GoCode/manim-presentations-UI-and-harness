# Code review: incremental pass 1 (pass1-reuse, 925a771..d99c8fa), round 1

Scope: the diff, read against the "D12 follow-up ... INCREMENTAL PASS 1" and "D12 PASSES" entries in DECISIONS, plus
build.py, pass1.py, records.py and deck.py read whole. Probes and mutants ran on mac-personal in a clone of d99c8fa
(scripts probes.sh, probeD.sh and mutants.sh; deleted after the review). In each probe,
"incremental" is a rebuild of an already built copy of the edge fixture, and "cold" is the same talk with no build/.
The bar was: a reused record must equal what a fresh pass 1 would produce now.

## HIGH

### H1. An existence check or stat on a talk file is not an input, so reuse ships a stale clip
- Where: manim_presentations/pass1.py:19 (`READ_EVENTS`) and :61-63 (inputs are recorded only for open/listdir/scandir/glob); build.py:205-216 (`pass1_key`).
- Principle: Mark, then route, exact and not exhaust-based. The key stands in for "everything pass 1 depended on", but it holds only what the audit hook can see. CPython raises no audit event for `os.stat`, so `Path.exists()`, `os.path.isfile`, `.stat().st_size` and the like are not recorded. The DECISIONS claim "a chapter that now reads new files can only do so because something it read before changed" is false for this case.
- Evidence (probe A): in the edge fixture's `chapters/sizes.py`, beat "grows" was edited to run `if (talk.root / "assets" / "flag.txt").exists(): small.shift([1, 0, 0])`. The recorded inputs were `['chapters/__pycache__/sizes.cpython-312.pyc', 'chapters/sizes.py']`. After `touch assets/flag.txt`, the incremental build said `pass 1: 0 of 8 chapters run, 8 reused`, `render: 0 beats · 21 reused`, and kept `grows` at fingerprint `21b843720f`. The cold build gave `grows` = `3116267de4`. The build exited 0 and shipped the old clip.
- Fix: record stat targets as inputs too. In pass1.main, before `guard.active = True`, wrap `os.stat` and `os.lstat` (Path.exists/is_file/is_dir/stat and os.path.* all go through them) with a function that adds the snapshot-relative path to `guard.inputs` while the guard is active. Record a directory as "dir/" and anything else as a file entry. Keep the existing digest rules: sha256 for a file, sorted names for a directory, "absent" when gone. Size and existence then follow from content. Add a test "an existence check is an input": a chapter that branches on `assets/x.exists()` must re-run when that file appears. Amend the DECISIONS claim so it says reads and stats.

### H2. Third-party code and the interpreter are not in the key: an upgrade gives a false failure or a stale clip
- Where: manim_presentations/build.py:196-202 (`engine_code` hashes only manim_presentations/*.py) and :401-402 (`base`).
- Principle: Single source of truth. "What runs is not what was edited." Pass 1's output also depends on manim, numpy, pycairo, Pillow and Python. Before this change, every build re-ran pass 1 and so picked up any change to them. `clip.identity()` covers them only for what happens after the frames, by version.
- Evidence (probe C, the same version with edited code): the probe changed manim's `ClockwiseTransform` default `path_arc` from `-np.pi` to `-np.pi / 2` in the clone's venv, by writing a new file, not by editing in place. The incremental build said `pass 1: 0 of 8 chapters run`, `render: 0 beats · 21 reused`, and kept sizes `clockwise` at `1e0500c279`. The cold build gave `clockwise` = `62d4e3aa00`, `becomes` = `135d1d3ffd` and `fades` = `24477a1edc`. The build exited 0 and shipped stale clips.
- Evidence (probe D, the same edit plus a version bump in manim's METADATA, which is what `uv sync` to a new manim does): `clip.identity()` changes, so every beat re-renders against the stale pass-1 digests. The build failed with `chapters/sizes.py:10 beat clockwise: animation 1 drew different frames in its worker than in pass 1: the chapter is nondeterministic`. That error blames the author's chapter for an engine upgrade. It recurs on every build until someone deletes build/pass1/, and nothing tells them to do that.
- Fix: put `clip.identity()` in `base` (it is already computed in `build`, so compute it before pass 1 and pass it to `base`). That covers every version upgrade (probe D) and the Python version. To also cover a reinstall or edit within one version (probe C), hash the RECORD file of each dist that `identity` names, for example `importlib.metadata.distribution(d).read_text("RECORD")`. uv writes per-file hashes there, so a changed wheel changes the key. That still misses a hand edit made in place, which is acceptable. Write the remaining limit beside the existing system-font limit in DECISIONS. Add a test that uses an engine copy with a patched `clip.identity` result, or a mutant check that the key moves when identity moves.

## MEDIUM

### M1. Environment variables are not inputs: reuse ships a stale clip
- Where: manim_presentations/build.py:398 (`env = {**os.environ, ...}` passes the whole environment to pass 1) and :401-402 (`base`).
- Principle: No fallbacks / the failure that looks like a success. Before this change, a chapter that read the environment was re-run on every build. Now its first record lives on silently.
- Evidence (probe B): beat "grows" was edited to run `if os.environ.get("RVR_PROBE"): small.shift([1, 0, 0])`. A rebuild with `RVR_PROBE=1` said `pass 1: 0 of 8 chapters run`, `0 beats` rendered, and kept `grows` at `21b843720f`. The cold build with the same environment gave `3116267de4`.
- Fix (choose one, then write it in DECISIONS): (a) give pass 1 and the workers a fixed environment (PATH, HOME, TMPDIR, PYTHONHASHSEED, MPRES_BUILD_PID and the TeX path). The environment is then a constant, and render and pass 1 also agree by construction. Or (b) keep the whole environment and list "environment reads" as a known limit beside system fonts. (a) is the exact fix. (b) leaves a silent path open.

### M2. The titles test does not test the chapter title, which is the title pass 1 actually gets
- Where: tests/build/test_pass1_reuse.py:73-75.
- Principle: Test design, non-tautological and falsifiable. The test renames `lines[0]` of script.md, which is the talk title ("Edge cases"). Pass 1 never receives the talk title. It receives `c.title or c.slug` (build.py:184) as `Talk.title`, which chapter code can read. The test passes only because `script.title` is also in `base`.
- Evidence (mutant M1): the probe removed `c.title or c.slug` from `base` (build.py:402). `test_settings_titles_and_the_engine_run_every_chapter` still passed (`1 passed in 27.78s`). No other test covers it.
- Fix: rename one chapter heading (for example "# sizes: Sizes after transforms" to "# sizes: Renamed") and assert `ran(...) == {"sizes"}`. That test turns the mutant red, and it also checks that a chapter title edit re-runs only that chapter. Decide whether `script.title` belongs in `base` at all. Pass 1 cannot see it, so it only forces needless re-runs. If it stays, say why in a comment.

## LOW

### L1. The cache-id in the key has no test
- Where: build.py:402 (`cid`). tests/build/test_pass1_reuse.py has no case for it.
- Evidence (mutant M2): the probe removed `cid` from `base`, and all 8 tests in test_pass1_reuse.py passed (`8 passed in 47.75s`).
- Fix: the engine-copy setup at test_pass1_reuse.py:76-78 can also provide a `.tinytex` whose `TinyTeX/tlpkg/texlive.tlpdb` is a changed copy (symlink every other entry). Then assert that every chapter runs. If the extra test is not worth its cost, accept the gap in writing.

### L2. Spec drift: the store does not hold the pass-1 cost, and reuse depends on the previous index
- Where: build.py:406-407 (`c.slug not in old_costs`), :423-428 (costs come from the old index) and :567-584 (`store_pass1` writes only records.json, *.npy and key).
- Principle: No spec drift. DECISIONS item (3) says the store holds "records.json, loop rasters, its key and its pass-1 cost". The code keeps the cost only in index.json. A store is therefore usable only while the previous index lists its chapter. That is safe: a missing index or a schema mismatch only forces a full pass 1, and probe and code reading confirm this. But the store and the spec do not agree.
- Fix: either write the cost into the store and drop the `old_costs` gate, or amend DECISIONS (3) to say that the cost stays in the index and that reuse needs the previous index. The second fix is smaller.

### L3. Every chapter records a pyc path that cannot exist as an input
- Where: pass1.py:61-63. The `spec_from_file_location` loader tries `chapters/__pycache__/<slug>.cpython-312.pyc` (probe A's inputs).
- Effect: none on correctness. `talk_files` excludes `__pycache__`, so the digest is always "absent". The entry is noise in the reuse key and in records.json.
- Fix: optional. Skip the entry when one of its path parts is `__pycache__`, because the snapshot never contains one.

## Checked and found sound
- Stores are written only after `write_index`, inside `clips_exclusive` (build.py:547-555). A build that fails or crashes (`run_all` raises, a check fails, the render fails) leaves the stores untouched.
- A kill during `store_pass1` leaves either the old store, no store (between `rmtree` and `os.replace`) or a `.tmp-<slug>` folder that the next sweep removes. A kill between `write_index` and `store_pass1` leaves an older store. The key is a pure function of the record's own inputs on the new snapshot, so that older store is still reused only when it is correct.
- A missing previous index (Absent) or a SchemaMismatch makes `old_costs` empty, so every chapter runs.
- Concurrent builds are serialized by `build_lock`.
- Chapter order is not an input: each pass-1 process receives only its own slug, chapter title, settings and paths.
- The settings are complete: `to_argv` is the whole `model_dump_json`.
- manim.cfg cannot affect pass 1: cli.py:26 refuses a talk that has one.
- Imports of helpers are seen as `open` of the source (through `io.open_code`) and as a FileFinder `listdir` of each sys.path folder in the snapshot.
- Baseline: test_pass1_reuse.py 8 passed on d99c8fa after every probe was restored (manim file and METADATA copied back from saved originals; `cmp` confirmed the manim file).

## Count
HIGH 2 · MEDIUM 2 · LOW 3
