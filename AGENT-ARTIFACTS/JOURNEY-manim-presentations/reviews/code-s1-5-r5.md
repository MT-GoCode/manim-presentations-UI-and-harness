# Code review S1–5, round 5: End of Build Period, whole codebase

Reviewer: a fresh Claude subagent. Scope: `s4` @ 144d2dc, every file under `manim_presentations/`, `tests/`, `examples/`, `setup.sh`, `bin/mpres`, `pyproject.toml`, `ci.yml` and `README.md`. Reviewed against STRATA 1–5, PLAN §0–§3.6 and §3.11, DECISIONS, DEBT, round 4 and its fixes (`c19a296..144d2dc`), and code-principles.md.

Host: probes and tests ran on mac-personal in a clean clone at 144d2dc (`/tmp/rv5/base`). Nothing heavy ran on mac-work-2. The repo was not edited.

## Round-4 fixes verified

Each fix was read in full against its finding.

- **H1** (`talk.py:196-203`): an empty loop raises `TalkError` at its line, and the overlay row passes. Correct.
- **H2** (`conftest.render_peak`): the regex `^render: \d+ beats .* · peak alive (\d+) ` matches only the render summary. The progress line (`render: 3/10 animations`) and the zero-render line (no `peak alive`) cannot match. Correct.
- **M1**: the test asserts the whole old index and every old clip while the reader holds `SH`, and asserts a new `build_id` after release. An index written before the lock fails it. Correct.
- **M2+M3**: the wipe raises on failure. The ghost chapter in the old snapshot fails pairing if the wipe is gone. Correct (see L1 for the half of PLAN line 866 that is still unasserted).
- **M4**: after `tests/unit` (107 passed), `git status --porcelain` is empty. No `media/` and no temp leaks. Correct.
- **M5**: `test_deck.py` covers nested `build/`, root `build/`, `__pycache__` at depth, dot-entries and root `*.md`. Correct.
- **M6**: the formula and its two measured inputs are stated beside the constant. Correct for `--workers 4` tests (see L2 for the auto-width tests).
- **M7**: the overlay row and the `size-mismatch 1` count are asserted through a build. The moved mark has a new defect (see M1 below).
- **M8, M9**: the deletions are recorded in DECISIONS with their probes. The new shadow test asserts a visible size (48). Correct.
- **L1–L9**: each is present and correct. The L3 overlay lists `tempfile.gettempdir()`. The L4 engine-edit string exists in `clip.py:317`, and `edit()` asserts it. The L6 wait blocks on a real child (psutil). L8 has one `_flock` route.

---

## MEDIUM

### M1. A size-mismatch mark never clears: a later, matching Transform still fails the build
- **Where:** `manim_presentations/manim_hooks.py:200-209` (`take`), read at `talk.py:241`.
- **Problem:** On a count mismatch, `take` sets `_mpres_size_mismatch = True` on the source's text nodes and returns. No route ever sets it back. A later Transform (or `become`) of the same group into a target with matching counts writes correct references (`_mpres_ref`), but the old mark stays. The beat then fails with "was transformed between groups of unequal numbers of text objects", although the text on screen is correctly sized. Round 4's M7 fix introduced this for groups: it moved the mark from the group (which was opened and lost) to the text nodes, which stay on screen.
  A realistic case is a beat or loop that morphs a labelled group into shapes and back (the cycle pattern loops use to close). The node holds two independent facts, a reference and a mismatch flag, that can disagree. That is an illegal state the data shape allows.
- **Principle:** Make illegal states unrepresentable. No fallbacks: a false failure on a valid talk.
- **Evidence (probe, mac-personal, `mpres build --workers 2`):** chapter
  `g = VGroup(Text("a"), Text("b")).arrange(); talk.add(g)`; `talk.play(Transform(g, VGroup(Text("c"), Square(0.3)).arrange()))`; `talk.play(Transform(g, VGroup(Text("d"), Text("e")).arrange()))`. Exit 1, `checks failed: size-mismatch 2`, one error per text node.
- **Fix:** Keep one fact per node, written by every `take`: `_mpres_ref: tuple[float, float] | Mismatch`, where `Mismatch` is a marker. A matching take overwrites it with the reference. A mismatching take overwrites it with `Mismatch`. `size_ref` and the `Unit.size_mismatch` roll-up route on that one attribute. The latest Transform then wins. Add the probe above as an overlay that must build clean. Its mutant (the current sticky flag) must go red.

### M2. A shape transformed into text escapes the min-text check
- **Where:** `manim_presentations/manim_hooks.py:201-206`.
- **Problem:** When the source has no size-checked node (`mine == []`) and the target has text, the count differs, but there is nothing to mark. A `Square` that ends holding a `Text`'s glyph points is not a size-checked class, so its text is drawn at any size and the build passes. `Transform(circle, Text("…"))` is a common Manim idiom. This is a failure that looks like success: the min-text check reports nothing for text that is on screen.
- **Principle:** No fallbacks (a silent pass). Mark, then route: the mismatch is known at `take`, but no node carries it.
- **Evidence (probe):** `sq = Square(0.5); talk.add(sq); talk.play(Transform(sq, Text("tiny", font_size=8)))` builds clean (exit 0). Control: `FadeIn(Text("tiny", font_size=8))` fails with `min-text 1` (minimum 32.0).
- **Fix:** On a mismatch, mark every node of the source family, not only its text nodes (with M1's single attribute, a non-text node can carry `Mismatch` too). The `Unit` roll-up already reads the whole family. The error's remedy, `ReplacementTransform`, then puts the real `Text` on screen, where its size is checked. Add an overlay row: a `Square` transformed into a small `Text` fails with `size-mismatch`.

---

## LOW

### L1. PLAN line 866's killed-render property is still unasserted
- **Where:** `tests/build/test_lifecycle.py:84` (`test_a_killed_builds_leftovers_are_wiped`).
- **Problem:** The test plants a ghost snapshot file and checks the wipe, which is correct. But PLAN §3.11 line 866 also says "a killed render leaves the previous index and clips intact, and a plain `mpres build` right after it … renders exactly the to-render set". No test kills a render. Also, the SIGKILL-parent test (line 867 says "during render") kills during pass 1. The property holds by construction: the index is written only at commit. So this is a gap in the spec's list, not a live defect.
- **Fix:** In the existing SIGKILL test, or a new one, kill the parent after the first `render:` progress line. Assert that `index.json` and its clips are byte-equal to before, then that the next build's `rendered` list equals the edited beats. Alternatively, record in DECISIONS that the pass-1 kill and the ghost plant stand in for line 866.

### L2. Two build tests run at auto width, above the slot cost they are scheduled with
- **Where:** `tests/conftest.py:27-42` (`build_cost`), `tests/build/test_lifecycle.py:163` and `tests/build/test_render.py:236` (no `--workers`).
- **Problem:** `build_cost` sizes every build slot for `TEST_WORKERS_WIDE` (4) render workers, and the comment says slots never oversubscribe. Two tests build with no `--workers`. On an idle 16-core mac, the edge fixture's 8 chapters and 8+ chunks can run up to 8 at once, about twice the slot. The tests stay correct (the build sizes itself from sampled idle headroom), but the stated invariant is false for them.
- **Principle:** No arbitrary constants: a constant's stated origin must hold for every case it covers.
- **Fix:** State the exception beside `build_cost` (these two tests sample live headroom, so they adapt to the load around them). Or size `build` from the edge fixture's chunk count, which bounds any width.

### L3. An empty loop is reported on a different route from an empty beat
- **Where:** `manim_presentations/talk.py:196-203` vs `build.py:418-426`.
- **Problem:** An empty `talk.beat()` is a build `Finding` (`empty-beat`). It is listed with every other finding and counted in `checks failed:`. An empty `talk.loop()` is a `TalkError` that aborts its chapter's pass 1. `run_all` then kills the other chapters, so the author sees one error and no count, and fixes errors one build at a time. The same authoring mistake has two routes. This is acceptable because a loop with no play has no rasters to record, but it is worth stating.
- **Fix:** Optional. Either record this split in DECISIONS, or record the loop with no rasters as its own variant (`EmptyLoop`) and let the build's empty-beat check report both kinds.

---

## Probes and tests run (mac-personal, clone at 144d2dc)

| Name | What | Result |
|---|---|---|
| unit suite | `pytest tests/unit`, then `git status --porcelain` | 107 passed; tree clean (M4 verified) |
| build rows | test_checks rows empty-loop, size-mismatch, read-tempdir, counts, the lock test; the ghost wipe; the lost-frame join | 7 passed; tree clean after |
| probe: sticky mark | group → (text, square) → (text, text) in one beat | **exit 1, size-mismatch 2** (M1) |
| probe: remedy | the size-mismatch overlay with `ReplacementTransform` | exit 0 (remedy works) |
| probe: shape → text | `Transform(Square, Text(font_size=8))` | **exit 0** (M2) |
| control: small text | `FadeIn(Text(font_size=8))` | exit 1, min-text 1 |

Counts: **HIGH 0 · MEDIUM 2 · LOW 3**.

## Fixes (round 5)

Commit on `s4`: 4f82541. Each mutant ran in its own copy of `manim_presentations/` (`PYTHONPATH` set to the copy, and `python -P` checked that the copy was imported) on mac-personal, with `/tmp/r5mut/mutants.sh`. "Restored" means the full suite at 4f82541 is green on mac-personal: 186 passed in 8m10s, and the tree is clean after the run.

| Finding | Fix | Mutant | Mutant result | Restored |
|---|---|---|---|---|
| M1 | Each node holds one fact, `_mpres_ref: tuple[float, float] \| Mismatch`. Every `take` rewrites it for the whole source family: on a match, size-checked nodes get the target's reference and other nodes get `None`; on a mismatch, every node gets `Mismatch()`. So the latest Transform wins. `mismatched()` is the one reader (isinstance, because `Mobject.copy` deep-copies the marker). `Unit.size_mismatch` and `_smallest` route on it, and `font_size` asserts it never reads a mismatched node. The `_mpres_size_mismatch` flag is gone. New: the `remorph` overlay builds clean, and a unit test checks that the sizes come from the last target (36, 44) | `match-keeps-mark` (a marked node is never rewritten: the old sticky flag) | red (2 failed: unit, and a build with `size-mismatch 2`) | green |
| M2 | A mismatch marks every node of the source family, not only its text nodes. New: the `shape-to-text` overlay row (`Square at … was transformed …`) and a unit test. The existing `size-mismatch` overlay now counts 2, because its source's Text and its Square are both on screen and both marked | `mark-text-only` (on a mismatch, mark only size-checked nodes) | red (2 failed) | green |
| L1 | New `test_a_killed_render_leaves_the_previous_build_whole`. After the `render width` line and once a render worker is alive, the test SIGKILLs the parent and waits for the workers to exit. Then it checks that `index.json` and every clip are byte-equal to before, and that the next build renders exactly `["words"]` | `early-clip-cleanup` (unlink unreused old clips before render) | red | green |
| L2 | The `build_cost` docstring states the exception: the two tests with no `--workers` may exceed their slot, but they size themselves from the idle cores and free RAM sampled at their start | constant, no mutant | n/a | n/a |
| L3 | The `Pass1Talk._close` raise is removed. A loop with no play is recorded as a new `EmptyLoop` variant (no rasters), so the build's one empty-beat check reports it (`beat "idle" has no animation`) and counts it (`empty-beat 1`). `loop_closure` passes it, and `finish` asserts that none reach the render | `empty-loop-raises` (the old raise restored) | red (2 failed: the row, and the new `empty-loop` → `empty-beat 1` count row) | green |
