# Code review S1–5, round 4: End of Build Period, whole codebase

Reviewer: a fresh Claude subagent. Scope: branch `s4` @ c19a296, every file under `manim_presentations/`, `tests/`, `examples/`, `setup.sh`, `bin/mpres`, `pyproject.toml`, `ci.yml` and `README.md`. Reviewed against STRATA 1–5, PLAN rev 30-o §0–§3.6 and §3.11, DECISIONS, DEBT, P7, and code-principles.md.

Host: every test, mutant and probe ran on mac-personal, in a separate copy for each mutant (`/tmp/rv4m/<name>`, `PYTHONPATH` set to the copy). A control mutant ran green. Nothing ran on mac-work-2, and the repo was not edited.

Counts: **HIGH 2 · MEDIUM 9 · LOW 9**.

---

## HIGH

### H1. An empty `talk.loop()` crashes pass 1 with a traceback instead of the empty-beat error
- **Where:** `manim_presentations/talk.py:83` (`_Beat.record`), reached from `pass1.py:126`.
- **Problem:** A loop beat with no play never reaches `Pass1Talk.play`, so `rasters` stays `None`. `record()` then asserts. The build prints a bare `AssertionError: pass 1 captures every loop's rasters` traceback. The authoring error ("has no animation; give it one") is never reported. `talk.beat()` gets the named error (the `empty-beat` overlay), but the same mistake on `talk.loop()` does not.
- **Principle:** No fallbacks / robustness at the boundary (an authoring error must be named at its line). Mark, then route: the build's empty-beat check exists, but the loop variant never reaches it.
- **Evidence (probe, mac-personal):** an edge copy plus chapter `talk.loop("idle"); talk.add(Square(1)); talk.beat("after"); talk.play(...)`. `mpres build --workers 4` ends with `AssertionError: pass 1 captures every loop's rasters`.
- **Fix:** Make a loop with no play impossible to record. In `Pass1Talk._close`/`tear_down`, a loop with no animation raises `TalkError(f'{where} loop "{slug}" has no animation; give it one ...')`. The pass1 route already prints `TalkError` as `error: ...`. Then add an `empty-loop` overlay to the `test_each_authoring_error_is_named_at_its_line` table (its mutant: delete the raise, see the traceback).

### H2. No test observes render concurrency: a render forced to width 1 passes both "wide" tests
- **Where:** `tests/build/test_render.py:93,102` and `tests/build/test_lifecycle.py:166,172`. Each one asserts `f"peak alive {TEST_WORKERS_WIDE}" in r.stdout`.
- **Problem:** The pass-1 line also prints `peak alive N` (`build.py:407`). The edge fixture has 8 chapters (9 with `long-beat`), so pass 1 alone reaches peak 4 at `--workers 4`. The assertion therefore checks exhaust from the wrong phase. STRATUM 3 requires "peak alive = TEST_WORKERS_WIDE" for the render, for both the full build and the long-beat edit. That is the signal that the wide byte-identity runs really had 4 workers interleaving. With the render serialized, the "interference between concurrent workers" defect this test exists for cannot occur, and the test still passes.
- **Principle:** Mark, then route: exact, not exhaust. Test design: non-vacuous, can name the defect.
- **Evidence (mutant `render-width-1`):** `width = 1` after `width_for("render", …)` in `build.py:566`. Both tests passed (2 passed in 186 s).
- **Fix:** Assert on the render summary line only: `re.search(rf"^render: \d+ animations in \d+ chunks · peak alive {TEST_WORKERS_WIDE} ", r.stdout, re.M)`. Then re-run the `render-width-1` mutant (it must go red in both tests). The full-build half needs ≥ 4 render chunks: the edge full build has 8 chapters, so 8 chunks, which suffices. Check it on the line.

---

## MEDIUM

### M1. `test_a_build_waits_for_a_reader_before_it_commits` has a vacuous assertion; commit-before-lock passes
- **Where:** `tests/build/test_render.py:214`.
- **Problem:** `"Edges" not in json.dumps(index(root))` can never fail. The edit is to chapter *code* (`Text("Edges"`), and the index holds slugs, titles, shas and hashes, never chapter text. So the test checks only that a "waiting" line appears and that the build later succeeds. It does not check that the index stays unwritten while a reader holds `SH`, which is the property §3.5 step 1 promises shots/export.
- **Principle:** Test design: non-tautological (the gate: it passes if `write_index` runs before the lock).
- **Evidence (mutant `index-before-lock`):** `layout.write_index(index)` moved before `with layout.clips_exclusive(...)`. The test passed.
- **Fix:** Read `index(root)["build_id"]` before you start the build. At the "waiting" line, assert that `build_id` is unchanged and that every clip of the old index still exists. After you release the lock, assert that `build_id` changed.

### M2. The step-2 wipe has no test that can fail; the spec's "no wipe" mutant survives
- **Where:** `tests/build/test_lifecycle.py:84-89` (`test_a_killed_renders_leftovers_are_wiped`).
- **Problem:** The test plants `build/.media/chunk-0/media/videos/uncached_00000.mp4` and expects a green build. Manim overwrites that partial file, so the build is green with or without the wipe. STRATUM 3 names the mutant "no wipe → `EEXIST`". §3.11 also requires that "a killed render leaves the previous index and clips intact" and that the next build "renders exactly the to-render set". Neither is asserted.
- **Principle:** Every test is falsifiable (prove it by mutation).
- **Evidence (mutant `no-wipe`):** `shutil.rmtree(layout.media, …)` at `build.py:352` replaced by `pass`. The test passed.
- **Fix:** Plant a leftover the build cannot tolerate. For example, `build/.media/src/chapters/ghost.py`: a stale snapshot file that, without the wipe, becomes an unnamed chapter and fails pairing. Better still, SIGKILL a real render mid-chunk (block on the `render:` progress line), then assert the old `index.json` and clips are unchanged, and that the next build renders exactly the edited beat. Re-run `no-wipe`.

### M3. The start-of-build wipe swallows its own failure
- **Where:** `manim_presentations/build.py:352`. `shutil.rmtree(layout.media, ignore_errors=True)  # safe: …`
- **Problem:** The comment gives the precondition (the lock proves no writer lives), but `ignore_errors=True` also hides a wipe that *failed*. Examples: a permission problem, or a busy file. In that case stale files under `.media/src` survive into the new snapshot, because the copy loop only adds and overwrites. A deleted helper or chapter is then still importable in pass 1 and in the workers. That is a degraded path that looks like success. (The end-of-build `rmtree` at `:534` is cleanup only, and `ignore_errors` is defensible there.)
- **Principle:** No fallbacks. The worst failure is one that looks like success.
- **Fix:** `if layout.media.exists(): shutil.rmtree(layout.media)`. The mutant test from M2 then covers it.

### M4. Render cruft is committed, and the unit tests write Manim's text cache into the repo
- **Where:** `media/texts/*.svg` (13 files, added in 9c6d11c, "Stratum 5"). The cause is `tests/unit/test_hooks.py`: `played()`, `test_a_paragraph_is_sized_from_its_text` and `digests()` build `Text`/`Paragraph` under `tempconfig({"dry_run": True})` with no `media_dir`, so Manim writes `./media/texts` into the cwd (the repo root). `.gitignore` does not cover `media/`. In addition, `tempfile.mkdtemp()` at `test_hooks.py:218,278` leaks a directory under `$TMPDIR` on every run.
- **Principle:** No cruft / no stale parts. Tests must not write the repo (§3.11: "Engine-edit tests never write the repo"; the same rule holds for any test).
- **Fix:** `git rm -r media/`. Add an autouse fixture in `test_hooks.py` that sets `media_dir`, `text_dir` and `tex_dir` to `tmp_path`. Use `tmp_path` in place of `mkdtemp()`. Do not add `media/` to `.gitignore`: hiding the write would let it continue silently.

### M5. The talk file set drops every folder named `build` or `__pycache__` at any depth
- **Where:** `manim_presentations/deck.py:123`, `EXCLUDED_DIRS` applied to `dirnames` at every level of `os.walk`.
- **Problem:** §3.5 step 2 excludes the talk's own `build/` (the generated root folder) and `__pycache__/`. A talk with `assets/build/…` or `helpers/build/…` loses those files from the snapshot. A chapter that reads them fails in pass 1 with a confusing `FileNotFoundError` inside `build/.media/src`. Edits to them are also invisible to the hashes (no stale, no rebuild).
- **Principle:** Single source of truth: the talk file set must be exactly the files the user controls. Robustness at the boundary.
- **Evidence (probe):** an edge copy with `assets/build/data.txt`, read through `talk.root`, gives `FileNotFoundError: ... build/.media/src/assets/build/data.txt`.
- **Fix:** Exclude `build` only when `here == Path(".")`. Keep `__pycache__` and dot-entries at every depth. Add a unit test on `Layout.talk_files` that includes `assets/build/x` and a root `build/`.

### M6. The xdist slot cost for `build` is an average labelled as a peak, and it is not the PLAN's formula
- **Where:** `tests/conftest.py:26-30` (`TEST_COST["build"] = (1.1, 911 MiB)`).
- **Problem:** The comment says "process-tree peaks (cores, bytes) … `/usr/bin/time -l`". But `time -l` reports total CPU seconds and peak RSS, so 1.1 "cores" is CPU over wall, an average. A `--workers 4` build runs 4 pass-1 children and then 4 tee workers at ~1.3 cores each. §3.11 states the formula: parent + pass-1 peak + `TEST_WORKERS_WIDE` × (`WORKER_CORES`, worker RAM). That gives ≈ 5+ cores and more RAM than the figure, which counts four pass-1 children only and no worker overhead. As a result, `-n auto` on mac-personal picks ~12 slots, each able to run 4–5 busy processes. The suite stays correct (oversubscription only slows tests, per the PLAN), but the constant's stated origin is wrong, and the rule "pick the width from measured headroom" is not met.
- **Principle:** No arbitrary constants: every constant comes from a measurement, stated correctly beside it.
- **Fix:** Derive `build` from the PLAN's formula with `build.WORKER_CORES`, `build.worker_overhead(480·270/1e6)` and the measured pass-1 peak. Alternatively, measure the real peak (for example, sample the process tree), and correct the comment. Record the resulting CI and local widths in DECISIONS.

### M7. The size-mismatch error and its `ReplacementTransform` remedy are never asserted through a build
- **Where:** `manim_presentations/geometry.py:176-183`, `talk.py:235`.
- **Problem:** STRATUM 5 lists "family-index pairing and the `ReplacementTransform` remedy". The unit test `test_text_transformed_into_a_non_text_slot_is_marked` checks only the private `_mpres_size_mismatch` attribute. No overlay drives a mismatched group transform through `mpres build`, so the user-visible message is unverified. The same holds for the `talk.py` roll-up of the flag into `Unit.size_mismatch` and for the `size-mismatch` count kind.
- **Principle:** Hierarchical tests: the path the user takes must be exercised. Every load-bearing branch must be falsifiable.
- **Evidence (mutant `no-size-mismatch-report`):** `if u.size_mismatch:` changed to `if False and …`. All of `tests/unit` + `tests/build/test_checks.py` passed (142 tests).
- **Fix:** Add a `size-mismatch` overlay: `Transform(VGroup(Text, Text), VGroup(Text, Square))` kept on screen. Add its row to the authoring-error table with the exact message, and assert `checks failed: size-mismatch 1`.

### M8. The shadow's "source stays on screen" predicate has no test that can fail
- **Where:** `manim_presentations/manim_hooks.py:218`. The test that claims to cover it is `tests/unit/test_hooks.py:401-411` (`test_replacement_transform_leaves_no_shadow`).
- **Problem:** `take()` writes the reference only onto the *source*. The test asserts that the *target* `b` has no `_mpres_ref`, which is true whether or not the predicate exists. Neither the `fades` (FadeTransform) fixture nor the hello example's `ReplacementTransform` observes the predicate either.
- **Principle:** Test design: the gate ("would this test still pass if the code under test did nothing?").
- **Evidence (mutant `no-shadow-predicate`):** `if self.mobject in scene.get_mobject_family_members():` changed to `if True:`. `test_hooks.py` + `test_checks.py` passed (58 tests).
- **Fix:** Pick a case where the predicate decides a visible outcome. One option: a `ReplacementTransform(a, b)` with a mismatched family count, then `talk.add(a)` again. Without the predicate, `a` carries a false `_mpres_size_mismatch` and the build fails. Another option: assert directly that the source `a` has no `_mpres_ref` after a ReplacementTransform. If no visible outcome depends on the predicate, delete it (minimality) and the PLAN's claim with it.

### M9. The canonical raster's z-order, which §3.1 makes load-bearing, is untested
- **Where:** `manim_presentations/manim_hooks.py:161` (`for group in (static, moving, rest)`).
- **Problem:** §3.1 and the STRATUM 4 DECISION say the raster must draw in Manim's frame order: static, then moving, then since-added. Otherwise a closed loop can read as open, or an open loop as closed. Both start-capture tests use scenes where `scene.mobjects` order already equals static-then-moving, so drawing plain `scene.mobjects` order gives the same pixels.
- **Principle:** Every touch in §3.1 has a test that fails if it breaks (N1). Test design: falsifiable.
- **Evidence (mutant `raster-scene-order`):** `for group in (present,)`. `test_hooks.py` + `test_edge_and_hello_build_clean` passed (23 tests).
- **Fix:** Add a `first_frame_vs_raster` case where a moving mobject comes before an overlapping filled static one in `scene.mobjects`. For example: `s.add(circle_filled_red, square_filled_blue)`, then `s.play(circle.animate.shift(0))`. Manim then draws the square first and the circle on top, which differs from list order.

---

## LOW

### L1. A misplaced comment in the min-size conversion
- **Where:** `manim_presentations/geometry.py:125-130`.
- **Problem:** "under half a pixel of ink is not drawn: neither overlap nor off frame" explains `s` at line 125. The formatter wrapped it onto the `min_tex` expression, where it reads as nonsense.
- **Fix:** Move it to the `s = …` line, and keep `min_tex` on one line.

### L2. The previous-build tag is re-inspected in scattered places
- **Where:** `manim_presentations/build.py:429,530`.
- **Problem:** `isinstance(previous, PreviousBuild)` appears twice after the `match` at `:381` has already routed on it. Mark, then route.
- **Fix:** Bind `old_index: Index | None` once in the match arms. Use it for `old_beats` and the GC keep set.

### L3. `ReadGuard` allows any event on `$TMPDIR` itself
- **Where:** `manim_presentations/pass1.py:64`.
- **Problem:** `p != self.tempdir` exempts the temp directory for every event, so `os.listdir(tempfile.gettempdir())` (a read of a listing outside the talk) passes. §3.5 allows the tempdir for write-mode opens only.
- **Fix:** Exempt it only when `event == "open"`. Add a `listdir(tempfile.gettempdir())` row to the `read-tempdir` overlay.

### L4. The joined-frame-count guard has no test
- **Where:** `manim_presentations/build.py:477-481`.
- **Problem:** No test drives a join that loses frames. Mutant `no-frame-count-check` (`if False:`) passes all 65 `tests/build` tests.
- **Fix:** An engine-edit test whose `clip.join` copy drops the last packet must fail with "joined N frames, pass 1 wrote M".

### L5. The render summary does not match the STRATUM 3 human-verifiable line
- **Where:** `manim_presentations/build.py:561,635-639`.
- **Problem:** STRATUM 3 (and §3.5 output) specify `render: N beats (…) · M reused · W workers (idle …) · digests verified`. The line prints animations and chunks, puts idle cores on a separate width line, and has no reused count unless 0 beats render. The progress line shows chunks where §3.5 says beats.
- **Fix:** Add the beat and reused counts and the idle figure from `width_for` to the summary.

### L6. A sleep in the orphan-lock test
- **Where:** `tests/build/test_checks.py:161`.
- **Problem:** `time.sleep(1)  # the children are alive by now` is a timing assumption. §3.11 says phase seams block on the build's own lines, with "no sleep".
- **Fix:** Block on a phase line printed after spawn, or poll until the lock's holder set includes a child (for example with `psutil`, for children whose cmdline holds the snapshot path).

### L7. Private caches are copied serially before any child starts
- **Where:** `manim_presentations/build.py:187,571` (`copy_tree` for each job in a loop).
- **Problem:** With dozens of chunks and a warm cache, these copies serialize before the first spawn. P0 measured ~55 ms per copy, so this costs about 2 s on a cold Mixing-Deluxe build.
- **Principle:** Maximize parallelism.
- **Fix (optional):** Copy in the same `ThreadPoolExecutor` width as the phase, or copy just before each spawn in `run_all`.

### L8. `report()` always raises, and two small helpers duplicate stdlib or local code
- **Where:** `manim_presentations/build.py:327`, `build.py:636`, `deck.py:167-190`.
- **Problem:** The name `report()` hides that it always raises. `sum(1 for _ in reports)` is `len(reports)`. `clips_exclusive` duplicates `_flock` apart from the NB-then-wait step.
- **Fix:** Rename `report` to `fail_checks`. Use `len`. Fold the wait into `_flock(…, on_wait=None)`.

### L9. Typst is size-checked but not treated as glyphs for overlap
- **Where:** `manim_presentations/talk.py:36` vs `:248` and `manim_hooks.SIZED`.
- **Problem:** Typst text is in `TEX`/`SIZED` but not in `GLYPHS`, so its letters go through the stroke/fill rules (fills never overlap) instead of the glyph rule. Overlapping Typst text passes the overlap check.
- **Fix:** Add `Typst` to `GLYPHS`.

---

## Verified, and fine
- Pass 1: chdir first, `dont_write_bytecode` set after `import manim`, the audit guard with routed violations, and the parent-death watch. Killed: `lock-not-inherited`. The tee/static-image map is pixel-exact against plain Manim. Killed: `static-latest`, which failed verification in the warm-cache build. The `PYTHONHASHSEED` route works. Killed: `no-hashseed`, through the set-ordered helper.
- Exact fast-forward reproduces pass 1 and its clock. The skip-mode mutant test is in the suite. Chunking arithmetic is hand-computed. Engine edits outside `clip.py` render 0, and `clip.py` renders everything.
- GC keeps the previous index's files and pins. Old stills go one build later. Cache-id changes start a new cache. The contracts in `pyproject.toml` match the §3.1 arrows for the S1–5 modules.
- `child-chdir-late` survives, but it cannot be observed by construction. The cli refuses a root `manim.cfg`, the parent's cwd is the talk root, and the snapshot holds no `manim.cfg`. So the child's chdir order is a stated invariant, not a testable behavior. No action, unless the PLAN's named mutant must stay. In that case, plant a `manim.cfg` inside the *snapshot* through an engine-edit copy of `deck.talk_files`.

## Mutants and probes run (mac-personal, one copy per mutant)

| Name | Edit | Tests run | Result |
|---|---|---|---|
| control | comment on `CHUNK_COST` | test_failure_counts_per_kind | green (harness OK) |
| render-width-1 | `width = 1` after render `width_for` | wide byte-identity, long-beat | **SURVIVED** (H2) |
| index-before-lock | `write_index` before `clips_exclusive` | test_a_build_waits_for_a_reader | **SURVIVED** (M1) |
| no-wipe | start-of-build `rmtree` removed | test_a_killed_renders_leftovers | **SURVIVED** (M2) |
| lock-not-inherited | `set_inheritable(fd, False)` | test_the_build_lock_outlives… | killed |
| static-latest | tee `_load` promotes the latest `get_frame` | tee fidelity, full build | killed (verification fails) |
| no-hashseed | `PYTHONHASHSEED=random` | full build + rebuild | killed (verification fails) |
| no-size-mismatch-report | geometry size-mismatch branch off | tests/unit + test_checks (142) | **SURVIVED** (M7) |
| no-shadow-predicate | predicate → `if True` | test_hooks + test_checks (58) | **SURVIVED** (M8) |
| child-chdir-late | `import manim` before worker chdir | hostile cwd, path probe | survived (unobservable, see above) |
| raster-scene-order | raster draws `present` in list order | test_hooks + edge/hello build (23) | **SURVIVED** (M9) |
| no-frame-count-check | joined-frame guard off | tests/build (65) | **SURVIVED** (L4) |
| probe: empty loop | `talk.loop` with only `add` | mpres build | **traceback** (H1) |
| probe: assets/build/ | chapter reads `assets/build/data.txt` | mpres build | **FileNotFoundError in snapshot** (M5) |
| probe: chapter prints | 40 `print()` lines in a worker | progress line | progress count unaffected (no finding) |

## Fixes (round 4)

Commits on `s4`: f90d4ef (all findings), 19a9764 + 6de73da (M9), 2819548 (M8), 144d2dc (M6). Each mutant ran in its own copy (`PYTHONPATH` set to the copy). The build mutants ran on mac-personal and the unit ones on mac-work-2. "Restored" means the same tests pass on the fixed code, both alone and in the full suite.

| Finding | Fix | Mutant | Mutant result | Restored |
|---|---|---|---|---|
| H1 | `Pass1Talk._close` raises `TalkError` for a loop with no animation; `empty-loop` overlay row | `empty-loop-no-raise` (`if False:`) | red (1 failed: traceback) | green |
| H2 | `conftest.render_peak` reads `peak alive` from the render summary line only | `render-width-1` (`width = 1` after the render `width_for`) | red (2 failed) | green |
| M1 | waits on the reader line, then asserts the index is unchanged and every old clip exists; after release, `build_id` changed | `index-before-lock` | red | green |
| M2+M3 | the wipe is `if exists: rmtree` (errors raise); the test plants a ghost chapter in the old snapshot and asserts a green build that renders nothing | `no-wipe` (wipe deleted) | red | green |
| M4 | `git rm -r media/`; an autouse `chdir(tmp_path)` in test_hooks.py (render_config resets media/text/tex dirs to Manim's cwd-relative defaults, so setting them would not hold); `mkdtemp()` removed | none named; after a unit run with `media/` deleted, `media/` is not re-created | n/a | green |
| M5 | `build/` is excluded only at the talk root; `tests/unit/test_deck.py` | `build-dropped-at-depth` (`d != "build"`) | red | green |
| M6 | `conftest.build_cost()`: the PLAN formula from `build.WORKER_CORES` and `build.worker_overhead`, with parent 191 MiB and pass-1 138 MiB (edge at 480×270, index.json). Result: 5.2 cores and 1073 MiB, against a sampled tree peak of 4.37 cores and 803 MiB | constant, no mutant | n/a | n/a |
| M7 | new `size-mismatch` overlay row and count. **Bug found:** the mark sat on the source group, and `_end_state` opens plain groups, so no unit carried it. It is now marked on the source's text nodes | `no-size-mismatch-report`; `mismatch-marked-on-group` (the old code) | red (2 failed); red (3 failed) | green |
| M8 | the predicate is **deleted**. FadeTransform overrides `clean_up_from_scene`, so the predicate decided only ReplacementTransform, where it left a re-shown source at Manim's stale size (70 for a 48 glyph). The test asserts 48 | `shadow-predicate-back` (predicate restored); the review's `no-shadow-predicate` is now the shipped code | red | green |
| M9 | the grouping is **deleted**, approved by the parent. Manim's static/moving split is a prefix/suffix of the z-sorted family, and `capture_mobjects` z-sorts each call, so one call draws the same pixels (probed: z_index, a compile-added Transform, foreground). DECISIONS updated | `raster-scene-order` cannot differ by construction (3 probes) | n/a | green |
| L1 | comment moved to the `s =` line | — | — | — |
| L2 | `old_beats` and `old_files` are bound in the `match` arms | — | — | — |
| L3 | the tempdir is exempt only for `open`; a `listdir(tempdir)` row | `tempdir-any-event` | red | green |
| L4 | engine-edit test: `clip.join` drops its last packet, so the build fails with "joined N frames, pass 1 wrote N+1" | `no-frame-count-check` (`if False:`) | red | green |
| L5 | summary: `render: B beats (A animations) in C chunks · R reused · peak alive P · W workers (idle …/--workers, est, peak) · digests verified`. Progress counts whole beats from a per-worker `progress` file (chapter `print()` shares stdout) | — | — | — |
| L6 | the test blocks until the parent has a live child (psutil), not on `sleep(1)` | — | — | — |
| L7 | private caches are copied in a thread pool (`seed_caches`) | — | — | — |
| L8 | `report` renamed to `fail_checks` (`NoReturn`); one `_flock` route with `on_wait` | — | — | — |
| L9 | `Typst` added to `GLYPHS` | — | — | — |
