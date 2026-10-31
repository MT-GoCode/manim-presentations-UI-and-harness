# STRATA review — round 1

Scope: STRATA.md, NORTH-STAR.md, DECISIONS.md, sub-journey-export/NORTH-STAR.md against PLAN rev 30-o (`manim-cleanup-opus-plan.md`), through strata-rules.md and code-principles.md. Size alone is not flagged (DECISIONS line 4).

Counts: HIGH 2 · MEDIUM 10 · LOW 13.

---

## HIGH

### H1. P5 and STRATUM 1 depend on each other (induction is broken)
- **Location:** STRATA.md:14 (P5 runs "right after STRATUM 1's repo exists"), STRATA.md:23 (`headroom.py` "constants from P5/STRATUM 0"), STRATA.md:24 (`conftest.py` xdist width hook, `TEST_WORKERS*`).
- **Problem:** STRATUM 1 must ship with constants that only P5 measures, and P5 runs only after STRATUM 1 exists. STRATUM 1 therefore cannot be "completely green" with real constants. The constants:
  - `MIN_SAMPLE_WINDOW` (PLAN §3.5 step 6: "measured by P5 on the runner and on mac-work-2");
  - the per-marker costs for the xdist hook: `qt`/`export`/`e2e` "from P5's probe scripts", `build` from P2's 480×270 point "on `macos-latest`" (PLAN §3.11 Width, §5 P2 last bullet);
  - `TEST_WORKERS_WIDE` 4 or 3 (PLAN §5 P5, pre-decided on the runner).
- **Second break:** P5 also says "time one edge-fixture `mpres build` cold and warm on `macos-latest`" and projects the suite time from it (PLAN §5 P5). The edge fixture arrives in STRATUM 2 and a rendering `mpres build` in STRATUM 3. That measurement cannot run at the point STRATA.md schedules P5.
- **Third break:** PLAN §5 says "Minh is told **before the strata begin**" for P5 outcomes (no H.264 in WebKit/Chrome, no backend decodes, widget-stack or backend split between P1 and P5). Running P5 after STRATUM 1 means strata already began. The P1+P5 widget-stack choice also feeds STRATUM 6.
- **Fix:** Make P5 independent of STRATUM 1. Run it from a throwaway probe repo (or the new repo's `probe/p5` branch created *before* any stratum code), with a probe-only workflow that runs the throwaway setup steps, P2's 480×270 repeat, the Qt/Playwright scripts and the sampler-window measurement. Replace "time one edge-fixture `mpres build`" with an explicit deferral: the first projected suite time is measured in STRATUM 3 (when `mpres build` and the edge fixture exist) and the PLAN's pre-decided remedy is applied there. State that STRATUM 1 starts only after all P0–P5, P7 numbers and their "Minh is told" gates are in DECISIONS.md.

### H2. STRATUM 2 lists tests that need rendered clips (STRATUM 3)
- **Location:** STRATA.md:32 ("hostile `manim.cfg`", "cwd shadowing (`-P`, chdir)", "`PYTHONHASHSEED` passed").
- **Problem:** STRATUM 2's `mpres build` stops after checks. The PLAN defines these tests by clip output:
  - hostile `manim.cfg`: "asserts identical clips" (PLAN §3.1);
  - cwd shadowing: "succeeds with identical clips, and no child's `sys.path` contains that cwd" (PLAN §3.11 build);
  - `PYTHONHASHSEED`: the only PLAN test is "the set-iterating helper rebuilds to 0 and verifies" with the mutant that drops the env var (PLAN §3.11 build). It needs reuse and verification, which STRATUM 3 has, and STRATUM 3 already lists it.
- STRATUM 2's verification line ("`uv run pytest -m "unit or build"` green") cannot be met as written.
- **Fix:** Move the hostile-`manim.cfg` and cwd-shadowing tests to STRATUM 3. Delete "`PYTHONHASHSEED` passed" from STRATUM 2, since STRATUM 3's set-iteration test is the PLAN's test for it. If an earlier pass-1-only version is wanted, say it asserts identical pass-1 digests and the `sys.path` property, and that STRATUM 3 upgrades it to clips. A wholesale replace is cleaner than leaving two versions.

---

## MEDIUM

### M1. No gate after STRATUM 0 for outcomes that change the strata
- **Location:** STRATA.md:16.
- **Problem:** "Pre-decided outcomes are followed exactly" hides two outcomes that change later strata or need Minh:
  - P3 adopts the stateful-tag optimization. The PLAN then rewrites §3.1, §3.3, §3.5 step 7, §3.11 and §6 (author marks, state-digest routing). STRATUM 3's file and test lists would be wrong.
  - P0 misses D12 (≤ 20 s). The PLAN says "Minh decides with P0's breakdown in hand" (D12).
  - The P1/P5 "Minh is told" outcomes (see H1).
- **Fix:** Add an explicit gate at the end of STRATUM 0: if P3 adopts the optimization, regenerate STRATA.md before STRATUM 1 (no surgery on S3). If D12 misses, or a P1/P4/P5 "Minh is told" outcome occurs, stop and report to Minh before STRATUM 1.

### M2. STRATUM 4 puts loop closure and D10 in one stratum
- **Location:** STRATA.md:42–45.
- **Problem:** D10 says "The shadow and the `Paragraph` hook land in their own late stratum, so declining D10 cuts them without surgery." STRATUM 4 mixes them with loop closure, which is not D10. D10 was accepted, but the PLAN still fixes the shape so it can be cut cleanly. Today a cut of D10 is surgery inside STRATUM 4.
- **Fix:** Split into STRATUM 4 (loop closure: capture points, canonical raster, loop fixtures and overlays) and STRATUM 5 (min-text: declared-size check, `Paragraph` hook, shadow, size fixtures and overlays). Renumber the rest. Place the "End of Build Period" review after the min-text stratum (see L1).

### M3. The provisional min-text defaults use the wrong unit
- **Location:** STRATA.md:15.
- **Problem:** PLAN §3.2 defines `checks.min_text`/`min_tex` as "declared `font_size` as a fraction of frame height". STRATA.md sets them to "32/40 at an 8-unit frame height". 32 and 40 are `font_size` values (PLAN §3.2: "Explainers keeps 32 and 40 apart"), not fractions. As written, the default is either the wrong unit or needs a conversion that nobody states. Also, "Explainers' measured" is unverified; the PLAN only says Explainers keeps them apart.
- **Fix:** State the conversion to a fraction of frame height (with the Manim relation used) and the Explainers file and line the 32/40 come from. Write `origin` as provisional until P6. Also note that the 55% Audience width (D4) lives in `audience.py`; "P6 replaces them without code change" is true only for the `settings.py` keys, so say that the 55% constant is a one-line code change with its origin.

### M4. `chunks()` unit tests are in no stratum
- **Location:** STRATA.md:37 (STRATUM 3 adds `schedule.py`).
- **Problem:** PLAN §3.11 unit: "`chunks`: identical cuts for identical inputs regardless of width, and cuts at to-render run boundaries." PLAN §3.11 fixtures: "A unit-level `chunks()` assertion checks the count" for the long beat (≥ `TEST_WORKERS_WIDE` chunks at 480×270). Neither appears.
- **Fix:** Add both to STRATUM 3's tests.

### M5. The Presenter half of the `Fatal` test is in no stratum
- **Location:** STRATA.md:55 (S6), STRATA.md:60 (S7).
- **Problem:** PLAN §3.11 qt: on `Fatal`, "The Presenter shows red, and exactly one Audience process exists afterwards. A mutant Presenter that relaunches on any disconnect goes red." STRATUM 6 has no Presenter. STRATUM 7's test list has no `Fatal`/disconnect-before-`Hello` case. The routing "Fatal or disconnect before Hello: red, no relaunch" (PLAN §3.7) is therefore untested.
- **Fix:** Add to STRATUM 7: package-copy Audience with an unloadable backend, Presenter shows red, exactly one Audience process, mutant relaunch-on-any-disconnect goes red.

### M6. The export temp-dir naming is "frozen" but no stratum creates it
- **Location:** STRATA.md:52, sub-journey-export/NORTH-STAR.md:7.
- **Problem:** The sub-journey consumes "`deck` temp-dir naming" (PLAN §3.9: "a directory `deck` names outside `build/.media`"). No stratum's file list adds it to `deck.py`. Strata rules say the interface must exist before fan-out. If the sub-journey must add it, it edits `deck.py`, which it is forbidden to edit.
- **Fix:** Add `deck`'s export temp-dir function (and confirm `clips_shared()`, `require_fresh`) to STRATUM 5's `deck.py` list, with one unit test that the path is outside `build/.media` and survives the build's step-2 wipe.

### M7. CI-time bound is re-checked only in STRATUM 3
- **Location:** STRATA.md:38.
- **Problem:** PLAN §5 P5: the CI ≤ 30 min acceptance "is re-checked in every stratum that adds `build`, `qt` or `export` tests", with a pre-decided remedy. STRATUM 4, 5, 6, 7, 8 and the sub-journey add such tests and do not mention it.
- **Fix:** Put the re-check in the global per-stratum rule (STRATA.md:7–9) so every stratum's "CI green" includes "CI wall time ≤ 30 min, else apply the §5 P5 remedy now".

### M8. import-linter contracts name modules that do not exist yet
- **Location:** STRATA.md:22–24 (`[tool.importlinter]` contracts §3.1, "import-linter run" test in STRATUM 1).
- **Problem:** The §3.1 contracts name `presenter`, `audience`, `talk`, `pass1`, `worker`, `export`, `shots`, `build`. In STRATUM 1 none of them exist. Whether `lint-imports` accepts a contract whose source or forbidden module is missing is an unverified assumption. If it errors, STRATUM 1's import-linter test is red. If it passes silently, the contract is vacuous until the module lands, and the mutant ("`import deck` in `talk.py`") cannot be run in STRATUM 1.
- **Fix:** Verify the behavior with a 2-minute probe. Then state the rule: each stratum adds the contracts for the modules it creates, in the same commit, and mutation-tests them (additive edits to `pyproject.toml`).

### M9. STRATUM 1 CLI: "four subparsers" contradicts "unimplemented subcommands do not exist yet"
- **Location:** STRATA.md:23, STRATA.md:24 ("cli boundary refusals"), STRATA.md:30 (STRATUM 2's file list has no `cli.py`).
- **Problem:** Line 23 says both "four subparsers" and "each stratum adds its subparser". With no subparser, the boundary refusal tests have no command to drive. STRATUM 2 needs the `build` subparser but does not list `cli.py`.
- **Fix:** STRATUM 1: argparse root plus the shared `<talk>` boundary, tested through a direct call of the boundary function (or add the `build` subparser in STRATUM 1, pointing at STRATUM 2's module). STRATUM 2: list `cli.py (+ build)`. Delete "four subparsers".

### M10. Cleanup (deliverable 12) is gated differently from the PLAN
- **Location:** STRATA.md:86.
- **Problem:** PLAN §9.12 and §6 Cutover: cleanup runs "once §6's acceptance passes", and is Minh's call only "if the D9 box ran out". STRATA.md makes it Minh's call in all cases. Minh's goal is "deliver the PLAN completely". Either STRATA.md follows the PLAN or DECISIONS.md records why not (archiving a repo and deleting checkouts is irreversible, which is a fair reason to confirm).
- **Fix:** Pick one and write it down. Either: "after S10 acceptance, run §6 cutover cleanup" in STRATUM 10. Or: add a DECISIONS.md entry that the irreversible cleanup waits for Minh's confirmation even on acceptance, with that reason.

---

## LOW

- **L1. "End of Build Period" sits before the build is finished.** STRATA.md:40. Loop closure and min-text are §3.5 step 4 build checks (N2). Move the period marker after the last build-check stratum.
- **L2. Narration edit leaves `stale` empty is not listed.** PLAN §3.11 build: "A narration edit renders 0, and `Deck.open(...).stale` stays empty." STRATUM 3 has "renders 0"; STRATUM 5 should add the `stale` half.
- **L3. `IncompatibleBuild` cases.** PLAN §3.6 has three: never built, schema mismatch, missing file. STRATUM 5 lists only the missing clip. Add "never built" and "schema mismatch raises `IncompatibleBuild`" (the PLAN's build-test pairs it with STRATUM 3's `NoPrevious` rebuild).
- **L4. Dedicated `dont_write_bytecode` test** in `pass1` and `worker` (PLAN §3.11 hooks group) is not named. Add it to STRATUM 2 (pass1) and STRATUM 3 (worker).
- **L5. Hooks for "both Recorder types"** (PLAN §3.11 hooks group) are not named one to one. Add a `RecordContext` hook test to STRATUM 2; STRATUM 3's tee fidelity covers `TeeContext`, say so.
- **L6. P7(d) re-measure.** PLAN §5 P7(d): "Re-measure on the edge fixture's loops before the tolerance is committed." Add to the loop stratum.
- **L7. Supported-browsers statement.** PLAN §9.7: README and AGENT-INSTRUCTIONS state Safari and Chrome, Firefox untested and unclaimed (D18). Add to STRATUM 9.
- **L8. Sub-journey scope misses §3.4's export flags.** sub-journey-export/NORTH-STAR.md:3 scopes §3.9 only. `--height` (even, ≤ source, refuse above, print chosen height, width formula) and `--crf` 0–51 are in §3.4. Add §3.4's export flags and the §3.9 transcript panel (highlight, scroll, click-jump, toggle, aspect-ratio media query) to its scope.
- **L9. Sub-journey host is not stated.** Subagents inherit nothing about machines. State mac-work-2 in its NORTH-STAR, and that its Playwright runs and the main stream's qt/build tests share the laptop. Qt real-time playback is the one timing-based assertion (PLAN §3.11). Say whether the two streams' suites may run at the same time, or serialize the heavy runs.
- **L10. STRATUM 2's "checks passed" stop.** STRATA.md:30. STRATUM 3 must remove that stop. Name it as the scaffold STRATUM 3 deletes, so the edit is a stated cut-over.
- **L11. Index schema v1 fields.** STRATA.md:37. Say STRATUM 3 writes every §3.5 step 9 field (`build_id`, talk-file-set hashes, pass-1 peaks, still paths, `script.md` structure), so STRATUM 5 and STRATUM 8 read fields that exist and the schema never changes mid-journey.
- **L12. Presenter status details.** STRATUM 7 does not name the elapsed-time field ("12:34 since first Next") or the "beat text overflows" line (PLAN §3.7). Add them.
- **L13. STRATUM 10 `gh` use.** `gh` is not logged in on Minh's machines. Say the private talks repo is created with `gitas exec personal -- gh …`, and `<gh-user>` is read the same way. Also state the §6 order "delete `SCRIPT.md` first" (case-insensitive APFS), since it is an ordering trap.

---

## Checked and found sound
- Every §9 deliverable 1–11 maps to a stratum; 12 maps to FINAL (see M10).
- §3.7 protocol, Audience, Presenter, hot-swap, pins, closing-by-cause map to S6–S8 with their PLAN tests, except M5 and L12.
- The export sub-journey is justified: its files (`export.py`, `player.html`, `tests/export/`) are disjoint, and its only shared files take additive blocks (`cli.py` subparser, e2e chain step). Its interface is frozen by S5 except M6.
- P6 moved to FINAL has a stated reason (needs Minh live) and a provisional default path (subject to M3).
