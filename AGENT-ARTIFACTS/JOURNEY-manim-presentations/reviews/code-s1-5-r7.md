# Code review S1–5, round 7: narrow, the round-6 fix only

Reviewer: a fresh Claude subagent. Scope: `git diff 4f82541 2720d08` and the code it touches: `take`, `ref`, `shadowing_clean_up`, `align_structure` and `shadowing_become` in `manim_presentations/manim_hooks.py`, the size-mismatch message in `geometry.py`, `EmptyLoop`/`call` in `records.py`, the empty-beat message in `build.py`, and the new and changed tests and the `swap` overlay. Judged against code-principles.md and `code-s1-5-r6.md` with its "## Fixes (round 6)" section.

Host: mac-personal, clean clone at 2720d08 (`/tmp/rv7`, deleted after), Manim 0.22.0. Nothing ran on mac-work-2 or ox-dev. The repo was not edited.

## What holds

- **Manim's pairing, read from source (0.22.0).** `Transform.begin` aligns `self.mobject` with `self.target_copy`, so pairing those two is exact. `Mobject.become` copies its argument only when a keyword is truthy, then runs `align_data(..., skip_point_alignment=True)`. That method skips point alignment only at the top level, because its recursion calls `m1.align_data(m2)` with no flag. So `align_structure` is needed: `align_data` cannot replace it. Its claim is correct.
- **Observation only.** I took a sha256 over type, points, fill and stroke for every node of the result, with the hook and without, in separate processes. All 16 probes gave equal digests: Text into MathTex and back, one-part into three-part MathTex and back, an empty MathTex part, DecimalNumber, `TransformFromCopy` ×3, `always_redraw(MathTex)`, keyword `become` with a swap, `stretch` with growth, a positional keyword, the Transform swap, `Restore`, and Text retext.
- **No new false failure in the common idioms.** In 0.22 the parts of a MathTex are not size-checked, so tex-parts, its reverse, an empty part, Text↔MathTex, DecimalNumber and `always_redraw` all come out with no `Mismatch`. Each has the right size: 40 for a 40-pt target, and 48 otherwise.
- **The new tests can fail.** The round-6 mutants (`sized-subsequence`, `become-no-copy`, `become-no-align`, `empty-loop-says-beat`) each target one new test, and I checked each against the code. The changed assertion in `test_text_transformed_into_a_non_text_slot_is_marked` is stronger than before: `a` reads 36, and only `b` is marked.

---

## MEDIUM

### M1. `TransformFromCopy` is paired backwards: a false `size-mismatch` on the textbook equation idiom, and a wrong size for text

- **Where:** `manim_presentations/manim_hooks.py:227-229` (`shadowing_clean_up`), which every Transform subclass inherits.
- **Problem:** `TransformFromCopy(a, b)` is `Transform(b, a.copy())` with `interpolate(1 - alpha)`. At the end it interpolates at 0, so `b` draws its own points. The hook still gives `b`'s family the references of `target_copy`, the copy of `a`. The docstring and the round-6 notes say the hook uses "Manim's own pairing", and this subclass breaks that claim. This defect predates round 6, because the old pairing by size-checked subsequence gave the same marks. But it lives in the function the fix rewrote, and it fails the brief's test: does the pairing match Manim for every Transform?
- **Evidence (mac-personal, 2720d08):**
  - Build probe: the `edge` talk plus one chapter that runs `eq = MathTex("a", "+", "b", font_size=60)`, then `talk.play(TransformFromCopy(eq[2], MathTex("b", font_size=60).shift(DOWN)))`. Result: **exit 1**, `error: derive · chapters/fromcopy.py:8 · MathTex at (0.00, -1.00) was transformed between text and a shape …; use ReplacementTransform(a, b)`, `checks failed: size-mismatch 1`. The talk is legal, the text is 60 pt, and the suggested fix in the message is wrong. Copying an equation part into a new equation is the most common use of `TransformFromCopy`.
  - In-process: `TransformFromCopy(Square(), Text("big", 60))` marks the Text `Mismatch`. `TransformFromCopy(Text("a", 40), Text("tiny", 8))` reads the shown 8-pt text as **15.3**. Against a minimum of 12, that is a false pass.
- **Principle:** Mark, then route. Which node the source's points came from is a fact Manim decides per class. `TransformFromCopy` ends holding its own starting points, so the hook routes on the wrong fact. Second principle: No fallbacks. The false failure carries a wrong remedy, and the false pass is a green build.
- **Fix:** Give `TransformFromCopy` its own clean-up hook. Use polymorphism, not an `isinstance` arm: `setattr(TransformFromCopy, "clean_up_from_scene", …)` calls the original clean-up and does not `take`. The shown mobject keeps its own references. Nodes that alignment padded on are copies of its own nodes, so they carry their own kind and reference. Add the build probe above as an overlay row that must build clean. Its mutant is the present inherited `take`. Also add a unit test where the `Text("tiny", 8)` read must equal 8.

### M2. Nothing tests that the keyword `become` hook leaves the source unchanged

- **Where:** `manim_presentations/manim_hooks.py:244-246`, which calls `align_structure(self, target)`. That call mutates `self` as well as the copy. `tests/unit/test_hooks.py:428-441`.
- **Problem:** On the keyword path, the hook aligns structure against the live source after Manim's `become` has already run. It is observation-only today: in the "What holds" probes, digests were equal. But only probes check this. Mutant `self.align_data(target)` is the call the round-6 notes considered and rejected. It changes what is rendered: `become_kw_swap`, `become_stretch_grow` and `become_positional` give digests that differ from no-hook. Yet `tests/unit/test_hooks.py` passes in full against it (28 passed, run from the mutant copy with `PYTHONPATH` set, and the import path checked). No build fixture calls `become` with a keyword. The hook runs in pass 1 only, so a hook that changes the source makes pass 1 check a scene that the render does not draw. The build would stay green.
- **Principle:** Test design, non-vacuous and falsifiable. The round-6 notes say "the source's points are unchanged", which is load-bearing, and no test can turn red for it. Second principle: No fallbacks. The divergence would be silent.
- **Fix:** Add one unit test, parametrized over `{}`, `{"match_height": True}` and `{"stretch": True}`. Run the same `become` on a fresh swapped group with and without `size_hooks`, and assert that the families are equal by type and points. Mutant: `self.align_data(target)`, which must go red.

---

## LOW

### L1. The copy is made when any keyword is given, not when one is true

- **Where:** `manim_presentations/manim_hooks.py:244`, which is `mobject.copy() if a or k else mobject`.
- **Problem:** Manim copies only when a keyword is truthy. So `become(x, match_height=False)` makes the hook copy at 6 ms while Manim aligns `x` in place. The result is still correct, but the comment's claim "made only when needed" does not hold. The condition is a stand-in for Manim's own condition.
- **Principle:** Mark, then route, exact and not exhaust-based. Second principle: Lower latency.
- **Fix:** Optional. Bind the keywords by name the way `become` does, and copy when `any((stretch, match_height, match_width, match_depth, match_center))`. Or drop "only when needed" from the comment.

---

## Probes and tests run (mac-personal, clone at 2720d08)

| Name | What | Result |
|---|---|---|
| source read | `Mobject.become`, `Mobject.align_data`, `TransformFromCopy` (0.22.0) | as stated above |
| 16 in-process probes, hook against no hook | family digest (type, points, fill, stroke), marks, font size | all digests equal. Mismatch only where expected (swaps) and in `TransformFromCopy` ×2 (M1) |
| build `fromcopy` | `TransformFromCopy(eq[2], MathTex("b", 60))` on `edge` | **exit 1**, size-mismatch 1 (M1) |
| mutant `align_data` | `self.align_data(target)` in place of `align_structure(self, target)` | 3 keyword-`become` digests change, `tests/unit/test_hooks.py` 28 passed (M2) |

Counts: **HIGH 0 · MEDIUM 2 · LOW 1**.

## Fixes (round 7)

Commits on `s4`: b8dccc5 (the fixes and tests) and bd7f416 (a fixture fix, below). Unit mutants ran in the mac-work-2 worktree (`tests/unit/test_hooks.py`, 34 tests). The build mutant ran in the mac-personal clone. Each mutant was applied to the committed tree and restored by `git checkout`. "Restored" means the full suite at bd7f416 is green on mac-personal: 198 passed in 9m02s, and the tree is clean after the run.

| Finding | Fix | Mutant | Mutant result | Restored |
|---|---|---|---|---|
| M1 | `setattr(TransformFromCopy, "clean_up_from_scene", clean_up)`: TransformFromCopy gets Transform's unshadowed clean-up, so it does not `take`. This is polymorphism, not an `isinstance` arm. Its mobject ends at `interpolate(0)` and draws its own points, so it keeps its own references. Alignment pads it with copies of its own nodes. New: the `fromcopy` overlay (`TransformFromCopy(eq[2], MathTex("b", font_size=60).shift(DOWN))` on `edge`), a row of `test_legal_transforms_pass_the_size_check` that must build clean. That test replaces `test_a_later_matching_transform_clears_a_size_mismatch`, and `remorph` is its other row. A unit test checks `TransformFromCopy(Text("a", 40), Text("tiny", 8))`, which must read 8, and `TransformFromCopy(Square(), Text("big", 60))`, which must not be marked and must read 60 | `fromcopy-take` (delete the setattr, so the inherited `take` runs) | unit: red (1 failed, the new unit test). Build: red (`fromcopy` row, exit 1, `checks failed: size-mismatch 1`) | green |
| M2 | `test_become_draws_the_same_with_the_hook`, parametrized over `{}`, `{"match_height": True}` and `{"stretch": True}`. It runs the same `become` on a fresh swapped group without the hooks and then with them, and asserts that the families are equal by type and points | `align-data` (`self.align_data(target)` in place of `align_structure(self, target)`) | red (2 failed: `match_height` and `stretch`. The `{}` case passes, as it should: then the target is already aligned to `self`) | green |
| L1 | The hook binds the call to `become`'s own signature (`inspect.signature`, once, at install) and copies only when a keyword is true, which is Manim's condition. Positional keywords bind too. New: `test_become_copies_its_argument_only_when_manim_does`, over `{}` and `{"match_height": False}`. The argument's `copy` fails the test if it is called | `any-keyword` (`a or k`) | red (1 failed: `match_height=False`) | green |

Fixture fix (bd7f416). The size-hook fixture saved `TransformFromCopy.clean_up_from_scene` with `monkeypatch.setattr`. That gave the class its own copy of the unhooked clean-up, so the class always had its own clean-up and the `fromcopy-take` unit mutant stayed green (34 passed). Now the fixture sets the attribute and then deletes it. Undo restores the inherited state, and was checked: there is no own attribute after `undo()`, and the inherited one is Transform's. The fixture and `test_the_shadow_changes_no_frame` share one `install_size_hooks(monkeypatch)`, so the patched list lives in one place.

Observation only. A probe (not kept as a test, because it would repeat `test_the_shadow_changes_no_frame` for one more class) compared the clip digests of `TransformFromCopy(Square(), Text("big", 60))` and `TransformFromCopy(Text("a", 40), Text("tiny", 8))` without the hook and with it: they are equal. M2's test covers `become`.
