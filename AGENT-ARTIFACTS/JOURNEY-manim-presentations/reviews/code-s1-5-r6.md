# Code review S1–5, round 6: End of Build Period, whole codebase

Reviewer: a fresh Claude subagent. Scope: `s4` @ 4f82541, every file under `manim_presentations/`, `tests/`, `examples/`, `setup.sh`, `bin/mpres`, `pyproject.toml` and `ci.yml`. Reviewed against STRATA 1–5, PLAN §0–§3.6 and §3.11, DECISIONS, DEBT, rounds 4 and 5 and their fixes (`c19a296..4f82541`), and code-principles.md.

Host: probes and tests ran on mac-personal in a clean clone at 4f82541 (`/tmp/rv6/repo`, deleted after). Nothing heavy ran on mac-work-2 or ox-dev. The repo was not edited.

## Round-5 fixes verified

Each fix was read in full against its finding.

- **M1** (`manim_hooks.py:214-223`): every `take` rewrites `_mpres_ref` on the whole source family, so the latest Transform wins. `theirs` is read before any write, so shared nodes are safe. `mismatched()` is the one reader. `_smallest` skips mismatched nodes, and `font_size` asserts it never reads one. The `remorph` overlay builds clean, and the unit test reads 36 and 44 from the last target. Correct.
- **M2**: on a count mismatch every source node gets `Mismatch()`. Probe `become-shape` (`Square().become(Text(font_size=8))`) fails with `size-mismatch 1`. Correct for the case it names. M1 below is the same defect class on the matched-count path, which this fix does not reach.
- **L3** (`talk.py:79-85`, `records.py:66-72`, `build.py:324,473`): an empty loop is recorded as `EmptyLoop`, reported by the one empty-beat check and counted (`empty-beat 1`). `loop_closure` passes it. `finish` asserts that none reach the render. `IndexBeat.kind` (`BeatKind`) never receives `"empty-loop"`, because `fail_checks` raises first. Correct. See L1 for two small leftovers.
- **L1** (`test_lifecycle.py:98-124`): the parent is SIGKILLed after its `render width` line, once a worker is alive. The test checks that `index.json` and every clip are byte-equal, then that the next build renders exactly `["words"]`. Correct.
- **L2** (`conftest.py:35-40`): the exception is stated beside `build_cost`. Correct.

---

## MEDIUM

### M1. Text and a shape that swap places in a group escape the min-text check

- **Where:** `manim_presentations/manim_hooks.py:214-223` (`take`), called from `shadowing_clean_up` (`:227-229`) and `shadowing_become` (`:233-237`).
- **Problem:** `take` pairs the source's size-checked nodes with the target's size-checked nodes by their order *among size-checked nodes*. Manim does not pair that way. `Transform` aligns the two families (`align_data`), then gives source node *i* the points of target-copy node *i* over the **whole** family. `Mobject.become` does the same (`zip(self.get_family(), mobject.get_family(), strict=True)`, Manim 0.22.0). So when the counts match but the positions differ, the reference goes to the wrong node:
  `Transform(VGroup(Text("a", 40), Square()), VGroup(Square(), Text("tiny", 8)))`. Source and target each have one Text, so `matched` is true. The source `Text` gets the 8-pt reference but now draws a square, so its size reads as about 8 · (square height / text height), far above the minimum. The source `Square` now draws the 8-pt glyphs (Manim padded it with four glyph-carrying children), but it is not size-checked and gets `None`. The build passes with 8-pt text on screen.
  This is the same failure as round 5's M2 (a shape holding text glyphs, reported as nothing), reached through the matched-count branch instead of the mismatch branch. It is also not the PLAN's design: §3.5 line 493 and §3.11 line 841 say "paired by **family index**". The code pairs by index among size-checked nodes only.
- **Principle:** No fallbacks (a failure that looks like success: tiny text, green build). Mark, then route; exact, not exhaust-based: equal *counts* of text nodes are exhaust that stands in for "which node received which points". Manim's own family alignment is the exact fact.
- **Evidence (probes, mac-personal, `mpres build --workers 2`, test size 480×270, minimum 32.0):**
  - `swap`: the Transform above. **exit 0**, `built …`.
  - `swap-replace` (control: the same with `ReplacementTransform`): exit 1, `Text at (0.75, 0.00) font size 8.0 is below the minimum 32.0`. So the 8-pt text is on screen.
  - In-process, after the play: `g.get_family()` zipped with `tr.target_copy.get_family()` (8 = 8 nodes) gives `Text <- Square`, `VMobjectFromSVGPath <- Square`, `Square <- Text`, `Square <- VMobjectFromSVGPath` ×4.
- **Fix:** Pair over the aligned whole family, as Manim does, and drop the count comparison:
  - In `shadowing_clean_up`, pair `self.mobject.get_family()` with `self.target_copy.get_family()`. Both are aligned and of equal length after `begin`. `target_copy` is a `copy()`, so it carries the target's `initial_height`, `font_size` and `_mpres_ref`.
  - In `shadowing_become`, do what `become` does: `t = mobject.copy()`, apply the same `match_*` and `stretch` keywords as `become`, then `self.align_data(t, skip_point_alignment=True)` (a no-op on `self`, which `become` already aligned) and pair `self.get_family()` with `t.get_family()`. Check this on a probe before relying on it.
  - Per pair `(x, t)`: if both are size-checked, `x._mpres_ref = size_ref(t)`. If neither is, `None`. If exactly one is, `Mismatch()`. Read every `size_ref(t)` before the first write, as now.
  - Then `take(source, target_family)` is one zip over aligned nodes, and "unequal numbers" is one case of "a text node paired with a non-text node". The finding text stays correct (`Text`/`Square` "was transformed between groups of unequal numbers of text objects") but would read better as "into a slot that is not the same kind of text".
  - Add the `swap` probe as an overlay row that must fail (`Square at … was transformed …`). Its mutant is the present sized-subsequence pairing, which builds clean.
  - Re-run the existing rows. `remorph` must stay clean, and `size-mismatch` and `shape-to-text` must still fail. Also re-run `tex-parts` (`Transform(MathTex("a^2+b^2=c^2"), MathTex("c", "=", r"\sqrt{a^2+b^2}"))`), which builds clean today. It is the common Manim idiom most likely to produce new Text-to-non-Text pairs under exact pairing. If it then fails, that is a new `size-mismatch` on a legal talk, and the decision belongs in DECISIONS before the fix lands.

---

## LOW

### L1. The empty-loop variant is told apart by its payload, and its message calls it a beat

- **Where:** `manim_presentations/build.py:418-426`, `manim_presentations/records.py:66-69`.
- **Problem:** The empty-beat check routes on `not b.animations` (the payload) for both `PlainBeat` and `EmptyLoop`, while `EmptyLoop` is the mark. `EmptyLoop` also still carries an `animations` field that is always empty: `EmptyLoop(animations=(a,))` validates, which is an illegal state the type allows. The author wrote `talk.loop("idle")`, but the message reads `beat "idle" has no animation`.
- **Principle:** Make illegal states unrepresentable. Mark, then route.
- **Fix:** Optional. Give `EmptyLoop` `animations: tuple[()] = ()`, or move `animations` off `_Beat` onto the two variants that have plays. Name the kind in the message (`loop "idle" has no animation`).

---

## Probes and tests run (mac-personal, clone at 4f82541)

| Name | What | Result |
|---|---|---|
| probe `swap` | `Transform(VGroup(Text 40, Square), VGroup(Square, Text 8))` | **exit 0** (M1) |
| control `swap-replace` | the same with `ReplacementTransform` | exit 1, min-text 1 (8.0 < 32.0) |
| probe alignment | source family zipped with `target_copy` family after the play | `Text <- Square`, `Square <- Text`, `Square <- VMobjectFromSVGPath` ×4 |
| probe `animate-shrink` | `group.animate.scale(0.2)` (matched path) | exit 1, min-text 1 |
| probe `become-shape` | `Square().become(Text(font_size=8))` | exit 1, size-mismatch 1 (round-5 M2 holds) |
| probe `tex-parts` | one-part MathTex into three-part MathTex | exit 0 (no false mismatch today) |
| probe `text-retext` | `Transform(Text("Hello"), Text("Hello world"))` | exit 0 |
| round-5 tests | `tests/unit/test_hooks.py`, `test_failure_counts_per_kind`, `test_a_later_matching_transform_clears_a_size_mismatch`, `test_each_authoring_error_is_named_at_its_line`, `test_a_killed_render_leaves_the_previous_build_whole` (`-n 2`, under the heavy lock) | 55 passed in 82 s. The only untracked entry, `media/`, came from this reviewer's in-process alignment probe (made 1 s after the probe script), not from the suite |

Counts: **HIGH 0 · MEDIUM 1 · LOW 1**.

## Fixes (round 6)

Commit on `s4`: 2720d08. Each mutant ran in its own copy of `manim_presentations/` (`PYTHONPATH` set to the copy, `python -P` checked that the copy was imported, the engine's `.tinytex`, `pyproject.toml` and `uv.lock` linked beside it) on mac-personal, with `/tmp/r6/mutants.sh` (deleted after). "Restored" means the full suite at 2720d08 is green on mac-personal: 191 passed in 8m10s, and the tree is clean after the run.

| Finding | Fix | Mutant | Mutant result | Restored |
|---|---|---|---|---|
| M1 | `take(source, aligned_target)` is one strict zip over the two aligned families, which is Manim's own pairing. Per pair: both size-checked, the target's reference; neither, `None`; exactly one, `Mismatch()`. All references are read before the first write. Transform's clean-up pairs `self.mobject` with `self.target_copy`, which `begin` aligned. `become` pairs `self` with its argument, which Manim aligns in place when no keyword is given. With a keyword, Manim aligns a private copy, so the hook copies the argument and aligns only its family structure (`null_point_align` and `align_submobjects`, recursively). `align_data` would also align points, and the probe showed that this rewrites the source's points. The copy costs about 35 times a bare `become` (6 ms against 0.17 ms for one line of Text, measured), so the hook makes it only when a keyword is given. Probes, by provenance tags: the hook's pairing equals Manim's in-place alignment for swap, shape to text, text to shape, retext, and a group that grows or shrinks, each with no keyword, with `match_height`, and with `stretch` plus `match_center`. The source's points are unchanged. The message now reads `was transformed between text and a shape (Manim pairs the two groups node by node)`. New: the `swap` overlay row (`Square at … was transformed between text and`, exit 1), the per-kind count row moved to `swap` (`size-mismatch 2`), and unit tests for the Transform swap, `become` with and without a keyword, and a keyword `become` that leaves its argument's family as it was. `size-mismatch` now counts 1: its Square-to-Square pair is correctly no longer marked. Re-run on a build: `remorph` exit 0, `size-mismatch` and `shape-to-text` exit 1, **`tex-parts` exit 0** (no new mismatch, so no DECISIONS entry), `text-retext` exit 0, and `become-swap` (with `match_center=True`) exit 1, `size-mismatch 2` | `sized-subsequence` (the old pairing by order among size-checked nodes) | red (5 failed: the Transform swap unit test, both `become` cases, the `swap` row and the `swap` count row) | green |
| M1 | the same | `become-no-copy` (align the caller's argument itself) | red (1 failed: the argument gains padding nodes) | green |
| M1 | the same | `become-no-align` (pair the keyword copy without aligning it) | red (1 failed: the `match_height` case, a strict-zip length error. The no-keyword case passes, as it should) | green |
| L1 | `EmptyLoop.animations: tuple[()] = ()`, so `EmptyLoop(animations=(a,))` fails validation (probe: `ValidationError`). Each beat variant declares `call: ClassVar[BeatKind]` (the talk call that started it), and the empty-beat message names it: `loop "idle" has no animation`. The empty-loop row now expects `loop` | `empty-loop-says-beat` (the message hard-codes `beat`) | red (1 failed) | green |

The typed field has no test of its own. It is a declaration that pydantic enforces, and a test would only restate it.
