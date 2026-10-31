# STRATA review r2 (fresh eyes; reviews/ not read)

Inputs read in full: STRATA.md, NORTH-STAR.md, DECISIONS.md, sub-journey-export/NORTH-STAR.md, probes/P7.md, PLAN rev 30-o (all 1247 lines), strata-rules.md, code-principles.md. Spot-checked probes/p1/p5_qt.py and probes/p4/p5_browsers.py for scope.

Counts: HIGH 0 · MEDIUM 8 · LOW 9.

Overall: coverage of §9 1–12, §3.1 and §3.11 is close to complete, and ordering is sound. The gaps are a few unassigned tests and fixtures, sub-journey ownership/contention details, and probe verdicts and deviations that are not yet recorded where the strata need them. None breaks induction if fixed before execution.

---

## HIGH

None.

---

## MEDIUM

### M1. The render-path edge-fixture cases have no owning stratum
- **Location:** STRATA.md STRATUM 2 (fixtures line), STRATUM 3 (no fixtures line), STRATUM 4/5 (fixtures lines).
- **Problem:** S2 creates `edge.manim-presentation` with "the must-pass cases that need only pass 1". S4 adds its loops and S5 adds its transforms. No stratum adds the §3.11 cases that S3's tests depend on:
  - the dt updater and the scene `add_updater`, each cleared mid-talk and followed by a later cut;
  - the `UpdateFromFunc` closure that persists across ≥2 cuts, and the accumulating non-time updater;
  - `ImageMobject`, `PMobject` and the background-image VMobject (needed by tee fidelity);
  - the long beat of ≥ `TEST_WORKERS_WIDE` chunks, with its cited arithmetic;
  - the 8-string set-iterating helper.
- **Evidence:** S3 tests cite "UpdateFromFunc + closure-updater fixtures", "long beat ≥ TEST_WORKERS_WIDE chunks", "set-iterating helper" and "tee fidelity", but S3 lists no fixture files. PLAN §3.11 Fixtures lists all of these as edge-fixture contents.
- **Fix:** Add a "Fixtures:" line to S3 that names each case above as added to `edge.manim-presentation` in S3. Say in S2 which edge cases S2 adds: `attach`/`transient`/`bleed`, the one-chapter helper, and the object made in a helper.

### M2. The session-scoped warm TeX/text cache fixture is not assigned
- **Location:** STRATUM 1 `tests/conftest.py` list; STRATUM 2/3.
- **Problem:** PLAN §3.11 Fixtures says each test seeds its copy's `build/.cache` from one session-scoped warm cache, built once per session under the `fcntl.flock` xdist recipe. The cold-cache MathTex test keeps its own cold copy. No stratum creates this fixture. S1's conftest list omits it, and it cannot work before S2's `build` exists.
- **Fix:** Assign it to S2's `conftest.py` additions, in the same stratum as the cold-cache test that opts out of it. Name its mutant, for example "seed from a shared, non-copied cache" or "no flock".

### M3. A named routing test for `RamExceeded` is missing
- **Location:** STRATUM 1 tests, STRATUM 2/3 tests.
- **Problem:** PLAN §3.5 step 6 names a unit test: "`RamExceeded` without `--workers` exits; with it, it builds". S1 tests only the `width()` tag. The build's routing on that tag exists from S2, because the pass-1 width uses it. No stratum owns the routing test.
- **Fix:** Add the routing test to S2, where `build` first routes on `Width | RamExceeded`. Have the sub-journey add the export equivalent, and S6 add the shots equivalent if wanted.

### M4. "A build during `export` waits at commit" is rewritten and the real test is dropped
- **Location:** STRATUM 3 ("build during a held `SH` waits at commit"); sub-journey-export/NORTH-STAR.md scope.
- **Problem:** PLAN §3.11 build: "A build during `export` renders, waits at commit, and then commits." S3's held-SH test proves the build side. Nothing proves that `export` takes `SH` before `Deck.open` and holds it while it reads clips. The sub-journey scope does not include this test, so the defect "export reads clips without `SH`" is uncaught.
- **Fix:** Keep S3's test. Add the PLAN's exact test to the sub-journey scope, blocking on the build's `waiting for shots/export` phase line. Its mutant is export without `clips_shared()`.

### M5. Sub-journey file ownership omits `pyproject.toml` (import-linter contracts)
- **Location:** sub-journey-export/NORTH-STAR.md "Owns only"; STRATA.md rule 3.
- **Problem:** The STRATA rule says every stratum adds the import-linter contracts for the modules it creates, in the same commit. `export.py` needs the PLAN §3.1 contract `export → {deck, script, headroom, protocol}`. The sub-journey does not own `pyproject.toml`, and S7/S8 edit that file's contracts at the same time. The sub-journey therefore either breaks the rule or edits a file it does not own.
- **Fix:** Add one additive `[[tool.importlinter.contracts]]` block for `export` to the sub-journey's owned list. Say that the JOIN resolves it as an additive merge, like the `cli.py` subparser block.

### M6. Host contention: only the sub-journey document mentions the heavy-work lock, and the sub-journey's `not qt` suite is outside it
- **Location:** sub-journey-export/NORTH-STAR.md scope; STRATUM 7–9.
- **Problem:**
  - (a) Only the sub-journey document says that "the main stream holds the same lock around its qt runs". STRATA S7–S9 do not mention `/tmp/mpres-heavy.lock`, so the main agent can forget it.
  - (b) The sub-journey runs `pytest -m "not qt"` without the lock. That suite includes every `build` test at xdist width from headroom, the heaviest load in the repo. It can run while the main stream's qt tests run, and PLAN §3.11 says Qt real-time playback is the one assertion that oversubscription can change.
  - (c) The sub-journey's own export tests are also partly real-time ("still playing after 2× its duration"). The main stream's `build` runs are not under the lock.
- **Fix:** Use one rule in both documents: every `uv run pytest` invocation on mac-work-2 that selects `qt`, `export` or `e2e` tests, and every heavy probe or encode, holds `flock /tmp/mpres-heavy.lock` for its whole run. Write it in STRATA.md's "Rules for every stratum". Do not limit it to the sub-journey.

### M7. The S0 results list omits probe verdicts that later strata need as constants or pre-decided branches
- **Location:** STRATUM 0 "human-verifiable results"; STRATUM 7, 8; sub-journey NORTH-STAR.
- **Problem:** The DECISIONS list in S0 names `g`, the backend and widget stack, and so on. It omits these:
  - P1(b) single vs double-buffered clip switch;
  - P1(c) loop-seam verdict (pre-decided double-buffer);
  - P1(f) paused Cover/Hold verdict and, if it fails, `k`;
  - P1(e) editor font floor (S8 uses "P1's floor");
  - the §3.5 "backend does not reopen the file on each loop wrap" check (p5_qt.py has an `unlink` check, but no stratum consumes the result);
  - P4 loop-seam and last-frame-seek verdicts (the sub-journey consumes them);
  - P5 rVFC-after-paused-seek.

  S7's description lists no double buffer and no muted-Hold path. Each pre-decided branch changes S7's or the sub-journey's code shape. Strata-rules forbid if/else in a stratum and forbid resting on an unverified result.
- **Fix:** Add every item above to S0's results list. Extend the Gate: "after S0, the S7/S8/sub-journey descriptions are rewritten to name the branch each pre-decided P1/P4 verdict selected, before STRATUM 1 starts."

### M8. Two deviations from the PLAN are not in DECISIONS.md
- **Location:** DECISIONS.md; STRATUM 0 (P6 bullet), STRATUM 3 description, probes/P7.md.
- **Problem:**
  - (a) **P6 timing.** PLAN §5 P6: "Schedule it first, in parallel with the other probes," and §3.2 makes the `min_text`/`min_tex` defaults "measured by P6". STRATA moves P6 to FINAL and ships provisional constants through S5 and S11. DECISIONS.md has no entry that Minh accepted this. NORTH-STAR allows omissions only "where reasonable from discoveries", and this one has no recorded reason.
  - (b) **Fast-forward mechanism.** PLAN §3.1 specifies a re-implemented replay: undo skip time, an `update_to_time` loop, `finish`, `clean_up`, `update_mobjects(0)`. P7 found and STRATA adopts a different mechanism: Manim's own `play_internal` with IO nulled and `update_skipping_status` overridden. Loop tolerance = 0 is also a P7 result. S0 says results "go to DECISIONS.md with evidence", but DECISIONS.md has no P7 entry. S3's reviewers read the PLAN as the source of truth and will flag the mismatch, or reimplement §3.1's text.
- **Fix:**
  - Add a DECISIONS entry for P7: the mechanism supersedes §3.1's sequence, with the evidence and mutants from P7.md, plus loop tolerance 0.
  - Ask Minh to schedule P6 now, in parallel, as the PLAN says. If he defers it, record his decision in DECISIONS.md and add to FINAL: "re-run the full suite and CI after the P6 constants change, because the fixtures are sized against the provisional minimum."

---

## LOW

### L1. Where the Position transition function lives is unstated
S1 tests "Position boundary table" from `tests/position_table.json`, but `Position` transitions (Next/Previous/Replay/click/`--from`) have no home module in S1. If they live in `presenter.py`, the S1 test has no subject until S8. **Fix:** state that the pure transition function lives in `protocol.py` beside `Position`. Otherwise move the Python table test to S8.

### L2. Deleting S7's scripted peer is surgery on green tests
S7's Audience tests drive the real Audience over the real protocol through a test-side client. That client is not a mock of production code. Deleting it in S8 forces S7's per-message tests (Cover, Hold, missing clip → `Failed`) to be rewritten to go through Presenter behavior, which is harder to aim at one message. **Fix:** keep the scripted peer as the Audience tests' permanent driver, with no scaffold label. S8 adds Presenter tests over the real socket, as PLAN §3.11 lists.

### L3. A title-card fixture for the S6 title-edit test is not named
"title edit → `structure_mismatch` and the rebuild renders only the card beat" needs a chapter card that uses `talk.title`. The edge fixture list has none. `hello` gets its card in "final" S10. **Fix:** give `hello`'s first version in S2 its `talk.title` card. Better, make `hello` complete in S2/S3, since setup builds it from S3, and leave S10 only the docs.

### L4. `deck.py` is missing from S8's file list
The Audience log `build/audience.log` must be named by `deck` (§3.1: no other module builds a `build/...` path). S8's files omit `deck.py`. **Fix:** add `deck.py (+ audience_log path)` to S8.

### L5. Cache prune and old-cache-id GC are not named in S3
§3.5 step 7 says the post-commit prune of `build/.cache` to audit-recorded entries. §3.5 step 3 says step 9's GC removes the old `cache-id` directory. S3 lists only "GC over `clips/`". **Fix:** list both in S3's `build.py`/`deck.py` items.

### L6. Junit output path not stated
PLAN §3.11: junit to `test-results/junit.xml`, which CI uploads. S1's `pyproject.toml` lists only `addopts = "-n auto"`. **Fix:** add `--junitxml=test-results/junit.xml` to S1.

### L7. The e2e CLI chain test file needs a stated owner layout
The sub-journey "appends" the export step to a test created in S6, while S9 also adds e2e tests. **Fix:** S6 puts the CLI chain test alone in `tests/e2e/test_cli_chain.py`. S9's Presenter e2e goes in a separate file, so the append is the only edit to that file.

### L8. The export code first gets a whole-codebase review at End of Project Period
"End of Player Period" (S9) precedes the JOIN, so `export.py` and `player.html` get only a merge review until S11. **Fix:** move the JOIN above the End of Player Period marker, or make the JOIN review whole-codebase.

### L9. Minor sub-journey and S7 scope omissions
- Sub-journey NORTH-STAR omits "frame rate stays at the source rate" (§3.9).
- S7 omits "the Audience accepts one client at a time" and "a test asserts the active backend" (§3.7) in its normal path, beyond the mismatch `Fatal`.
- S8/S9 omit `--from` unknown-slug rejection at the `cli` boundary, and fresh-start `present` refusing a stale build (§3.4/§3.6).

**Fix:** add each item as one phrase to the named stratum.
