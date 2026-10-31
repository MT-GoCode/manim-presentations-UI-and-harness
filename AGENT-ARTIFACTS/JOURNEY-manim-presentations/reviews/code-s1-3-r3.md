# Code review S1–3, round 3 (branch s3 @ 062e150)

Fresh reviewer, Claude. Mutants run on mac-personal (`~/work/s3`, `uv run pytest -n 8`), each restored with `git checkout -- .`; the tree was clean after the run. Lens: code-principles.md. Spec: STRATA.md STRATUM 1–3, PLAN rev 30-o §0–§3.5 and §3.11, DECISIONS.md, probes/P7.md.

The core verified render holds. Mutants on the tee, the exact fast-forward, verification, the stream check, the fingerprint identity, the previous-index GC root, the hash seed, the lock inheritance, the worker-RAM term and the private pass-1 caches all go red. Strata 1–3 still lack a group of named deliverables. Several guards in build.py and worker.py have no test, and eight mutants survive the whole build and unit suite.

## HIGH

### H1. Seven named STRATUM 3 tests are missing; their mutants survive the full suite
STRATUM 3's test list names each of these. None exists (grep `pin`, `wipe`, `bytecode`, `disjoint`, `PASS1`, `mid-build` over tests/). Each mutant below ran against `tests/build` plus `tests/unit` (or `tests/build/test_render.py` plus `tests/unit`) and stayed green:
- **GC spares pinned clips.** Mutant: drop `and f.name.split(".")[0] not in pinned` in `deck.py:229`. GREEN (129 s). `write_pins`, `live_pins` and the pin root are untested. STRATUM 3 says this protocol is "owned and tested here".
- **Killed render, then rebuild.** Mutant: `build.py:322` wipe changed to `pass`. GREEN (91 s). There is no test that leaves a killed render's `.media` behind, so the `EEXIST` defect the PLAN names cannot show.
- **Mid-build chapter edit yields pass-1-equal clips.** No test exists.
- **`dont_write_bytecode` in the worker.** Mutant: `worker.py:27` changed to `pass`. GREEN (67 s). Only pass 1 is tested (`test_hooks.py:173`).
- **Encoder-key mutant trips the disjoint-keys assertion.** Mutant: delete the assert at `worker.py:43`. GREEN (64 s).
- **Pass-1 width read from the previous index (mutant: always the seed).** Mutant: replace `build.py:353-354` with `pass`. GREEN (97 s).
- **`check_render_config` (PLAN §3.5 step 7: "a worker asserts … the live render-affecting config equals `render_config(settings)`").** Mutant: `worker.py:48` changed to `pass`. GREEN (64 s). The stream test (`test_render.py:282`) writes `clip._applied` on purpose to get past this guard, so nothing tests the guard itself.

Principles: test design (every guard needs a test that can fail), "Every test names the defect that turns it red". Fix: add one build test per item. Each must go red on the mutant listed. For example: hold `presenter_lock` from the test process, write pins for one old sha, run two builds, then assert the clip still exists. Or: seed `build/.media/chunk-0/media` with a stale partial, run a build, then assert it succeeds.

### H2. No long-beat fixture, and the "long-beat edit" byte-identity case was swapped for a four-chapter edit
STRATUM 3 fixtures: "a beat long enough for ≥ `TEST_WORKERS_WIDE` chunks at 480×270 (duration from P3's `CHUNK_COST` and P2's 480×270 rate, arithmetic cited beside it)". Tests: "`--workers 1` vs wide byte-identical for full build **and long-beat edit** with peak alive = `TEST_WORKERS_WIDE`".
- edge.manim-presentation has no such beat. At 480×270 every chapter is one chunk: rate 0.095 s/s, so one chunk needs about 210 s of video.
- `test_render.py:93-101` edits four chapters, so `peak alive 4` comes from four one-chapter chunks. The PLAN's "even one edited long beat spreads across workers" is never exercised by a build. No test runs a cut inside one beat through real workers.
- `test_schedule.py:14` uses 7.49 MP and synthetic plays, not the fixture.

At CHUNK_COST = 20 s the fixture needs about 14 minutes of 480×270 video (about 80 s of render CPU). That cost is probably why it was dropped, but DECISIONS has no entry for it.

Principles: No spec drift. Tests use the real thing. Fix: add the fixture with its arithmetic, or record a DECISIONS deviation. One option: add a test-only `CHUNK_COST` override through the engine-edit pattern (a package copy), which keeps schedule.py's constant intact. Either way, one test must cut one beat into at least 4 chunks and compare `--workers 1` with wide byte for byte.

### H3. The child-output reader thread and `chunk k: animation i/n` streaming are missing
DECISIONS (S1-2 r1 resolutions) moved "the child-output reader thread … lands there [STRATUM 3]". PLAN §3.5 step 7: workers stream `chunk k: animation i/n`, and a parent reader thread tails them into one progress line. `build.py:543` prints one line only when a chunk finishes. `worker.py` prints nothing, and there is no thread (grep `thread` in build.py: none). For a long chunk, a watcher sees no progress for its whole duration. Principle: missing STRATUM deliverable, observability. Fix: the worker prints per play. A thread in `run_all` tails each live child's `stdout` file and prints the folded progress line.

### H4. setup.sh has no example build
STRATUM 3 file list: "`setup.sh` (+ example build in /tmp)". `setup.sh:82-84` ends with `mpres --help`. So `./setup.sh` never shows that a render works on a new machine, and CI's `./setup.sh --dev` never builds `examples/hello`. Fix: add a phase that copies `examples/hello.manim-presentation` into `mktemp -d` and runs `mpres build` on it.

## MEDIUM

### M1. `live_pins` crashes the commit when a Presenter holds its lock but has not written pins yet (`deck.py:209-221`)
Reproduced on mac-personal: `presenter_lock()` and then `live_pins()` raise `FileNotFoundError … build/.presenter.json`. In `build.py:481-486` this happens after `write_index` and inside `clips_exclusive`. The new index is committed, GC never runs, `.media` is left behind, and the build exits with a traceback. A Presenter's startup window (lock taken, before its first adopt) is a real interleaving. Principles: robustness at the boundary, illegal states. Fix: the pin protocol makes the empty state explicit. `presenter_lock()` writes `[]` atomically right after it takes the lock, under `SH` on `.clips.lock`. Then "lock held" always means "pins file exists". Test it together with H1's pin test.

### M2. The hostile-cwd test lacks the `sys.path` assertion it names (`test_render.py:168-183`)
STRATUM 3 / PLAN §3.11: "… identical clips, **no cwd or live root on any child `sys.path`** (mutants: no `-P`, chdir after `import manim`)". The test compares clips only. The no-`-P` mutant goes red, but not through this test's property. With the live talk root as the child's `sys.path[0]`, pass 1's read guard refuses `helpers/__init__.py` under the live root. That fails every build, including the session warm-cache build. The worker has no read guard, so a worker-side `sys.path` leak would pass. The chdir-after-import mutant went red once in the `-n 8` batch, but a rerun at `-n 1` shows no failure line. It cannot fail by construction: the cli has already chdir'd into the talk root, which the boundary proved holds no `manim.cfg`, and `render_config` rebuilds the config anyway. So this test does not catch it. Fix: have pass 1 or the worker write `sys.path` beside `records.json`/`report.json`, or read it from a fixture chapter that prints it. Assert that neither the test's cwd nor the live root appears in it.

### M3. Step 8 always samples a new width, even when there is nothing to join or extract (`build.py:418`)
`width_for("join", workers, len(beats_in_order), …)` counts every beat as a job, reused ones included. Without `--workers`, every build with more than one beat pays another `MIN_SAMPLE_WINDOW` (1 s). A rebuild that renders 0 and needs no stills still pays it, though it then joins nothing. PLAN §3.5 step 8 samples only on the stills-only path and otherwise uses the render width. Principles: latency of glue ("a status … takes longer than reading its output"), wrong job count. Fix: jobs = beats to join plus stills missing. Skip the pool when that is 0. Reuse the render width when a render ran.

### M4. The scene-side import contract omits `worker` (`pyproject.toml`, contract "the scene side never imports…")
PLAN §3.1: "The scene side (`talk`, `pass1`, `worker`) imports neither `deck` nor `script`". `source_modules` lists only `talk` and `pass1`. The layers contract puts `worker` above `deck`/`script`, which allows `worker` to import them. So an `import manim_presentations.deck` in worker.py passes `lint-imports`. The PLAN also maps `worker` to {talk, clip, manim_hooks, settings}. `worker.py:21` imports `pass1` to get `watch_parent`, an arrow the PLAN does not list. Fix: add `manim_presentations.worker` to that contract. Move `watch_parent` to a module both entry points may share (talk or manim_hooks are on the scene side), or state the arrow in DECISIONS.

### M5. The CI wall-time check is not recorded
STRATA rule: "Every stratum that adds `build` … tests records and re-checks it". STRATUM 3: "measure one edge-fixture `mpres build` cold and warm on `macos-latest`, project the suite, apply the remedy if over 30 min". DECISIONS and DEBT hold no S3 number or projection. The session-scoped warm cache (commit 12e9b13) suggests work was done, but the measurement and verdict are not written down. Fix: add the measured cold/warm times, the projection and the CI run URL to DECISIONS.

## LOW

- **L1.** `test_schedule.py:8` `test_cuts_are_the_same_for_the_same_inputs` calls a pure function twice on equal inputs. No mutant short of randomness turns it red, and `chunks` takes no width parameter. Delete it, or have it assert cuts against a hand-computed list.
- **L2.** `test_schedule.py:34` `len(far[0:1]) == 1` is always true for a non-empty list. Drop that half.
- **L3.** `test_render.py:162` `test_a_set_ordered_helper_rebuilds_to_zero` repeats the rebuild-to-0 assertion of `test_render.py:45` on the same fixture. That costs two extra builds per run. Fold its name or comment into the first test.
- **L4.** `test_checks.py:129` uses `time.sleep(1)` at a phase seam. PLAN §3.11: "no sleep". The test also probes the flock directly instead of running `mpres build` to see exit 3 and then success, as STRATUM 3 words it, and it kills during pass 1, not render. Block on a line the child prints, or poll for the children's pids.
- **L5.** No test drops the frame-count check (`build.py:431`). Mutant `if False:` is GREEN. A mismatch cannot arise without an engine defect, so this guard is acceptable untested, but it is unfalsifiable as it stands.
- **L6.** Reuse requires `layout.clip(...).exists()` (`build.py:399`). Mutant: drop it. GREEN (101 s). Add a test: delete one clip, rebuild, assert exactly that beat renders.
- **L7.** `deck.previous` (`deck.py:159`) lets a schema-1 index that fails validation crash with a pydantic traceback. Consider the same one-line error as other boundaries.
- **L8.** The default-width test (`test_render.py:230`) checks only the pass-1 machine line. PLAN §3.11's "`WORKER_RAM` estimate ≤ total RAM" bound is not asserted. A KiB-for-bytes mutant would still go red through `RamExceeded`, so the gap is small.
- **L9.** The stream-check test is a worker `pix_fmt` override, not an `ENCODE` mutant as PLAN §3.11 words it. Changing `ENCODE` (crf/preset/g) cannot fail a codec/pix_fmt/size/fps check. It re-renders through the clip.py hash instead. One sentence in DECISIONS would close the wording gap.

## Mutants run

| # | Mutant (file) | Tests run | Result |
|---|---|---|---|
| 1 | spawn without `-P` (build.py:135) | hostile-cwd | RED, through pass 1's read guard (live-root `helpers/__init__.py`), not the clip comparison (M2) |
| 2 | worker imports manim before chdir (worker.py:11) | hostile-cwd | RED once at -n 8; no failure at the -n 1 rerun. Not caught by this test's assertion (M2) |
| 3 | tee `_load` promotes the latest snapshot, not the static map (clip.py:288) | test_render.py | RED (8 failures) |
| 4 | digest verification skipped (build.py:557) | clock overlay | RED |
| 5 | worker without exact fast-forward (worker.py:46) | late-beat edit, 1-vs-wide | RED |
| 6 | stream_check returns [] (clip.py:348) | stream test | RED |
| 7 | no PYTHONHASHSEED in child env (build.py:367) | set-ordered | RED |
| 8 | build lock fd not inheritable (deck.py:253) | killed parent | RED |
| 9 | WORKER_RAM drops the pass-1 RSS term (build.py:519) | peak RSS ≤ estimate | RED |
| 10 | GC ignores the previous index (build.py:484) | engine-edit | RED |
| 11 | fingerprint without clip identity (build.py:311) | engine-edit | RED |
| 12 | tee drops the `display_image_mobject` forward (clip.py:282) | tee fidelity | RED |
| 13 | pass 1 on the shared cache (build.py:184) | pass1_jobs unit, cold twins | RED |
| 14 | GC ignores pins (deck.py:229) | tests/build + tests/unit | **GREEN (survived)** H1 |
| 15 | pass-1 width always the seed (build.py:353) | tests/build + tests/unit | **GREEN (survived)** H1 |
| 16 | no `.media` wipe at start (build.py:322) | tests/build | **GREEN (survived)** H1 |
| 17 | worker writes bytecode (worker.py:27) | test_render.py + tests/unit | **GREEN (survived)** H1 |
| 18 | `check_render_config` removed (worker.py:48) | test_render.py + tests/unit | **GREEN (survived)** H1 |
| 19 | disjoint-keys assert removed (worker.py:43) | test_render.py + tests/unit | **GREEN (survived)** H1 |
| 20 | frame-count check removed (build.py:431) | test_render.py | **GREEN (survived)** L5 |
| 21 | reuse ignores clip existence (build.py:399) | tests/build + tests/unit | **GREEN (survived)** L6 |
| — | `live_pins` with lock held, no pins file | direct call | FileNotFoundError, M1 |
