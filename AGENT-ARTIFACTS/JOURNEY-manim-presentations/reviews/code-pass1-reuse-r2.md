# Code review: incremental pass 1 (pass1-reuse at 8e9b4a2), round 2

Scope: the r1 fixes (`git diff d99c8fa 8e9b4a2`), checked against the DECISIONS entries "INCREMENTAL PASS 1",
"D12 PASSES" and "Incremental pass 1, review r1". I read pass1.py whole and build.py from 100 to 600.
All probes and mutants ran on mac-personal, in a clone of 8e9b4a2 (scripts probes.sh, probeG.sh, probeF.sh and
mutants.sh, deleted after the review). Builds called `.venv/bin/python -m manim_presentations.cli` directly, so
`uv run` could not re-sync the venv in the middle of a probe.

Each probe works the same way:
1. Edit the edge fixture's `chapters/sizes.py` and build it once to prime it.
2. Change one thing (the trigger) and build again. This is the "incremental" build.
3. Copy the talk without build/, apply the same trigger, and build it. This is the "cold" build.

Every incremental build below printed `pass 1: 0 of 8 chapters run, 8 reused` and `render: 0 beats · 21 reused`,
and exited 0. The bar: a reused record must equal what a fresh pass 1 would produce now.

## Round-1 fixes: verdict
- Stats are inputs (r1 H1): **partly fixed.** `Path.exists()` is now caught (mutant M1 below turns the new test red).
  But the stat *result* is not keyed beyond content and existence, `os.access` is not wrapped, and the re-entrancy
  flag is shared across threads (M1-M3 below).
- clip.identity() and RECORD hashes in the key (r1 H2): **fixed for the five named libraries only.** Every other
  library that pass 1 runs is still outside the key (H1 below). No test checks the wiring (L1).
- Fixed child environment (r1 M1): **fixed.** Mutant M2 (`env = {**os.environ, ...}`) turns
  `test_no_environment_variable_reaches_a_chapter` red. Every variable that is passed (CHILD_ENV plus PYTHONHASHSEED,
  with the TeX PATH) is in the key through `tex_env`. The render workers get `env`, which is a subset of the same
  values. MPRES_BUILD_PID is added by `spawn` and is not in the key, but it is the parent's pid, so no chapter can
  depend on it reproducibly.
- Chapter title, not talk title (r1 M2): **fixed.** Mutant M4 (`pass1_base(*common, "")`) turns
  `test_a_chapter_title_runs_that_chapter_and_the_talk_title_none` red. `pass1_jobs` passes the same
  `c.title or c.slug` that `base` keys.

## HIGH

### H1. A dependency upgrade outside the five named libraries ships stale clips
- Where: manim_presentations/build.py:205-213 (`library_code` hashes RECORD for manim, pycairo, av, numpy and pillow
  only), plus clip.py:363 (`identity` holds versions of the same five).
- Principle: single source of truth ("what runs is not what was edited"), and no failure that looks like a success.
  Pass 1 also runs svgelements (it parses every Text and Tex SVG: manim/mobject/svg/svg_mobject.py:206), scipy,
  skia-pathops, networkx and mapbox_earcut, and the RECORD of manimpango is not hashed either. The "in-place edit"
  limit does not cover this case. This is a normal install of a new version.
- Evidence (probe F): the probe built a real wheel `svgelements 1.9.6.post1` (the installed source plus a
  `skewX(15)` transform in `SVG.parse`) and installed it with `uv pip install`. Before the upgrade, the primed fixture
  had `words` = `455e1fb79a`, `grows` = `21b843720f` and `fades` = `bca11d07fe`. After the upgrade, the incremental
  build reused everything and kept those three fingerprints. The cold build gave `words` = `6b5e7ff53b`,
  `grows` = `d6d9cc5364` and `fades` = `9770e0f703`. The venv was restored with `uv sync` (svgelements back to 1.9.6).
- Effect: a lock update that bumps svgelements changes every Text in every talk, and incremental builds keep the old
  clips. If any beat is rendered again for another reason, the worker draws with the new library and fails with the
  false "the chapter is nondeterministic" error, as in r1 probe D.
- Fix: replace `library_code` with a hash of every installed distribution:
  `sorted((d.metadata["Name"], d.read_text("RECORD")) for d in importlib.metadata.distributions())`. That covers every
  library pass 1 can import, with one source and no list to keep in step with `clip.identity`. Drop the unused
  `identity` parameter (L2).

## MEDIUM

### M1. The stat fix keys existence and content only: `os.access`, mode bits and mtime still give stale clips
- Where: pass1.py:115 (only os.stat and os.lstat are wrapped), build.py:244 (a stat'ed file's digest is its sha256),
  build.py:74 (the snapshot uses `copy2`, so it keeps the source's mode and mtime).
- Principle: mark, then route, exact and not exhaust-based. The key holds content as a stand-in for "what the stat
  returned", but `st_mode` and `st_mtime` reach the chapter unchanged and the key does not see them.
  `os.access` raises no audit event and is not wrapped.
- Evidence (probes.sh). In each case the cold `grows` differs from the incremental one:
  - A: a branch on `os.access(assets/flagA.txt, F_OK)`, trigger: create the file. Incremental `21b843720f`, cold
    `3116267de4`. The recorded inputs do not contain `assets/flagA.txt`.
  - B: a branch on `(assets/swatch.png).stat().st_mode & 0o100`, trigger: `chmod +x`. Incremental `21b843720f`, cold
    `64f83f8c8b`.
  - C: a branch on `(assets/backdrop.png).stat().st_mtime > 2e9`, trigger: `touch -t 203501010000`. Incremental
    `21b843720f`, cold `718acf6da3`.
- Fix: wrap `os.access` with the same `guard.stat` wrapper. Make a stat'ed file's digest
  `sha256 + st_mode + st_mtime_ns`. That takes the values from the snapshot, which `copy2` made equal to the source.
  For a stat'ed directory, use `st_mode + st_mtime_ns` as well. Add one test case for `os.access` and one for
  `chmod`.

### M2. A file read by a child process is not an input
- Where: pass1.py:19 (`READ_EVENTS`). A subprocess's reads raise no audit event in the parent.
- Principle: no failure that looks like a success. The DECISIONS claim "a chapter that now reads new files can only
  do so because something it read before changed" is false for a chapter that starts a process.
- Evidence (probe D): a branch on `subprocess.run(["/bin/cat", "assets/flagD.txt"]).stdout == b"on"`, trigger: write
  "on" into the file. Incremental `grows` = `21b843720f`, cold `fa87c435df`. The guard also let `/bin/cat` read the
  file without a check.
- Fix: in `ReadGuard.__call__`, handle the `subprocess.Popen` and `os.posix_spawn` audit events (and `os.system`,
  `os.exec`) while the guard is active. Refuse every executable that is not in the TinyTeX bin folder. Manim's own
  latex and dvisvgm calls then still work, and every other child is an error that names the chapter. If that is
  too strict, write "reads by a child process" as a stated limit next to system fonts.

### M3. The re-entrancy flag is shared across threads, so a stat on one thread hides a stat on another
- Where: pass1.py:53 and :84-89 (`self.noting` is one bool for the whole process).
- Principle: parallel work must be correct. "State the concurrent-access behavior of every shared resource."
- Evidence (probe E): `clockwise` starts a thread that calls `os.path.exists(helpers/shapes.py)` in a loop. The main
  thread then branches on `(assets/flagE.txt).exists()`. In the primed build's recorded inputs, `helpers/shapes.py` is
  present and `assets/flagE.txt` is absent: the main thread's stat ran while the other thread held `noting`. After
  `assets/flagE.txt` was created, the incremental build kept `clockwise` = `1e0500c279`, and the cold build gave
  `a490f68650`. This is a race, so the miss can depend on timing. One run showed it.
- Fix: make the flag per thread (`self.noting = threading.local()` and `getattr(self.noting, "on", False)`). Set the
  same flag around the realpath in `__call__` as well (L3).

## LOW

### L1. No test checks that the build actually puts identity, libraries and environment into the key
- Where: build.py:433 (`common`). tests/unit/test_pass1_key.py tests `pass1_base` alone.
- Evidence (mutant M3): `common = (engine_code(), {}, "", cid, {}, settings.to_argv())` left the 20 tests of
  test_pass1_reuse.py, test_pass1_key.py and the pass-1 lifecycle test all green (`20 passed in 38.85s`).
- Fix: one build test with an engine copy whose `library_code` (or `clip.identity`) returns a different value, which
  asserts that every chapter runs. test_pass1_reuse.py:73-78 already builds an engine copy this way. If that is not
  worth its cost, accept the gap in writing.

### L2. `library_code(identity)` ignores its parameter and falls back to an empty string
- Where: build.py:205-213. The docstring says "each library `identity` names", but the body repeats the tuple from
  clip.py:363. `read_text("RECORD") or ""` turns a missing RECORD into a constant instead of an error.
- Principle: single source of truth, no fallbacks.
- Fix: covered by the H1 fix. If H1 is not taken: iterate `identity`'s distribution names, and raise when RECORD is
  missing.

### L3. The audit hook's own realpath records stats, against the wrapper's comment
- Where: pass1.py:61 (`realpath` in `__call__` runs with `noting` False). pass1.py:85 says "note only the chapter's
  own call".
- Evidence (probe prime): the inputs of sizes are `['.', 'assets/backdrop.png', 'assets/swatch.png', 'chapters',
  'chapters/__pycache__', 'chapters/__pycache__/sizes.cpython-312.pyc', 'chapters/sizes.py', 'helpers/shapes.py']`.
  `.`, `chapters` and `chapters/__pycache__` are path components that realpath stat'ed. Each wrapped lstat inside the
  hook's realpath also starts a nested realpath, so one open costs a number of lstats that grows with the square of
  the path depth.
- Effect: not a correctness defect (the digests of these entries are constant), but the code does not do what the
  comment says. It is noise in the key and in records.json.
- Fix: set the per-thread flag from M3 around the realpath in `__call__` too.

### L4. A read under an allowed system root is not an input, which is wider than the stated limit
- Where: pass1.py:43-45 (`SYSTEM_ROOTS`, sys.prefix and others may be read) and :73-77 (`note` records snapshot paths
  only).
- Evidence (probe G): a branch on `open("/opt/homebrew/share/rvr2-probe.txt").read() == "on"`, trigger: write "on".
  Incremental `grows` = `21b843720f`, cold `3116267de4`. The probe file was removed afterwards.
- Effect: the stated limits name system fonts and in-place edits to installed libraries. A data file under
  /opt/homebrew, /usr/local (through /usr), /Library or the venv is neither of those, and a `brew upgrade` can change
  one.
- Fix: widen the DECISIONS limit to "anything read under the system roots (/System, /usr, /Library, /opt/homebrew,
  the interpreter and the venv)". Recording those reads would key on far more than chapters need.

## Checked and found sound
- The settings are keyed through `to_argv` in `common`, and the same string goes to pass 1.
- The engine copy that tests use through PYTHONPATH is the engine that `engine_code` hashes. The build process and
  its children import the same package.
- Mutants M1, M2 and M4 each turn their new test red, so those tests can fail (above).
- Baseline on the restored clone (git status clean, svgelements 1.9.6, no probe file left under /opt/homebrew):
  test_pass1_reuse.py and test_pass1_key.py gave `19 passed in 40.88s`.

## Count
HIGH 1 · MEDIUM 3 · LOW 4
