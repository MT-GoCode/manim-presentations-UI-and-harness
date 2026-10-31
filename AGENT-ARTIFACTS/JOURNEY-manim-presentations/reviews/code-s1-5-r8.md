# Code review S1–5, round 8: narrow, the round-7 fix only

Reviewer: a fresh Claude subagent. Scope: `git diff 2720d08 bd7f416` and the code it touches. That is TransformFromCopy's clean-up, the `become` copy condition read from become's own signature, their tests, and the `fromcopy` overlay. Judged against code-principles.md and `code-s1-5-r7.md` with its "## Fixes (round 7)" section.

Host: mac-personal, clean clone at bd7f416 (`/tmp/rv8`, deleted after), Manim 0.22.0. Nothing ran on mac-work-2 or ox-dev. The repo was not edited.

## What holds

- **TransformFromCopy, read from source (0.22.0).** `TransformFromCopy(a, b)` is `Transform.__init__(b, a)` with `interpolate(1 - alpha)`. So `self.mobject` is `b`, and it ends at `interpolate(0)`, which is its own aligned starting points. When the hook leaves `b`'s references alone, it matches what Manim draws. `setattr(TransformFromCopy, "clean_up_from_scene", clean_up)` binds the unshadowed `Transform.clean_up_from_scene`. That method still runs `replace_mobject_with_target_in_scene`, which is False here. `pass1.py:99` calls `install_size_references` once per chapter process, so `clean_up` can never be the shadow. No other Manim class subclasses TransformFromCopy.
- **The copy condition is Manim's own.** `Mobject.become` (0.22.0) copies exactly when `stretch or match_height or match_width or match_depth or match_center`. `signature.bind` leaves out defaults, so `arguments.values()[2:]` holds exactly the keywords that were passed, positional or by name. `any` over them is the same condition.
- **Observation only.** I took a sha256 over type, points, fill and stroke for every node, with the hook and without, in separate processes. All 13 probes gave equal digests:
  - TransformFromCopy: equation part into MathTex, a later Transform on the copy, a group padded 1→3, shape↔text inside groups, Text→Square;
  - ReplacementTransform, TransformMatchingShapes, TransformMatchingTex (3 → 5 parts);
  - become with `match_height` + `match_center`, with a positional `match_width=True`, and with `match_height=False`;
  - Write and FadeTransform (Text→MathTex).
- **No new false failure in these idioms.** Sizes read correctly: the fromcopy equation reads 60/60, the padded copies read 20 ×3, matching shapes/tex read 40 and 50, FadeTransform reads 40/50, and TransformFromCopy into a Square reads 40 on the source. The only marks are on real swaps (positional `become` that swaps the Text and the Square). There is one exception, and it predates this round (see the out-of-scope note).
- **The `fromcopy` build row is green** at bd7f416: `remorph` and `fromcopy` both passed.
- **Each new test can fail.** I applied every mutant to the committed tree. `git checkout` restored the tree, and it was clean after.
  - `fromcopy-take` (delete the setattr) turns `test_transform_from_copy_keeps_the_shown_mobjects_own_size` red.
  - `fromcopy-shadow` (give TransformFromCopy `shadowing_clean_up`) turns the same test red.
  - `never-copy` (`copies = False`) turns `test_become_with_a_keyword_leaves_its_argument_as_it_was` red. So the copy is load-bearing.
  - `always-copy-slice` (`[1:]`, so `mobject` is counted and the hook always copies) turns both rows of `test_become_copies_its_argument_only_when_manim_does` red.
  - Round 7 already showed that `align-data` turns `test_become_draws_the_same_with_the_hook` red. I did not repeat it.
- **The fixture's set-then-delete is correct.** For classes, pytest's `monkeypatch.setattr` records `__dict__.get(name, notset)`. Undo runs in reverse, so it ends with a `delattr` and leaves the class inheriting again.

## HIGH

None.

## MEDIUM

None.

## LOW

None.

## Outside scope (round-6 pairing, not this fix; not counted)

A group that grows by Manim's padding gets a false `Mismatch`. Example: `Transform(VGroup(Text("a", 40), Square()), VGroup(Text("x", 40), Square(), Square()))`, and the same with `become`. To pad 2 to 3, `add_n_more_submobjects` duplicates the source's Text. Pairing by index then sets that duplicate against a Square, so the duplicate is marked `Mismatch`. On screen it is a square, which is a legal result. I saw this in-process only (`['Text', 'Text:MISMATCH']` for both calls). I did not run a build with it. It comes from the aligned-family pairing that round 6 decided, so this round does not fix it. The owner should decide whether a padded duplicate that a non-sized node overwrites should be marked at all, because nothing renders text there. Defer to OTHER.md if accepted.

## Probes and tests run (mac-personal, clone at bd7f416)

| Name | What | Result |
|---|---|---|
| source read | `TransformFromCopy`, `Mobject.become`, Transform subclasses (0.22.0) | as stated above |
| 13 probes, hook against no hook | family digest, marks, font sizes | all equal, sizes correct |
| `tests/unit/test_hooks.py` | baseline | 34 passed |
| mutants `fromcopy-take`, `fromcopy-shadow`, `never-copy`, `always-copy-slice` | one at a time on the unit file | all red (1, 1, 1, 2 failed) |
| `test_legal_transforms_pass_the_size_check` | `remorph`, `fromcopy` builds | 2 passed |
| padding probe | 2→3 group via Transform and become | false `Mismatch` on a padded Text (outside scope) |

Counts: **HIGH 0 · MEDIUM 0 · LOW 0**.
