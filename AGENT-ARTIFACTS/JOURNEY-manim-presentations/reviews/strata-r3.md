# STRATA review r3 (fresh eyes; did not read reviews/ or plan-reviews/)

Inputs read in full: STRATA.md, NORTH-STAR.md, DECISIONS.md, sub-journey-export/NORTH-STAR.md, probes/P7.md, PLAN rev 30-o (1247 lines), strata-rules.md, code-principles.md.

Counts: HIGH 0 · MEDIUM 5 · LOW 13.

Summary of coverage: every §9 deliverable (1–12) and every §3.11 unit/build/qt/e2e/export test maps to exactly one stratum, the sub-journey, or FINAL, with D12 deferral recorded. Induction holds: no stratum uses a module or constant before it exists, with the one exception of PASS1 seeds (M1). The gaps below are mechanisms or tests that the PLAN states outside §3.11, which no stratum owns.

---

## HIGH

None.

---

## MEDIUM

### M1. STRATUM 0 output list omits the P0 seeds that STRATUM 2 consumes (`PASS1_RAM`, `PASS1_CORES`)
- **Location:** STRATA.md STRATUM 0 "human-verifiable results" (line 27). STRATUM 2 `build.py` "parallel pass 1".
- **Problem:** PLAN §3.5 step 3 sets the pass-1 width from `PASS1_RAM`/`PASS1_CORES`. With no previous index these are "P0's measured per-chapter pass-1 peak" and "P0's rusage measurement". STRATUM 2 has no index (the index arrives in STRATUM 3), so every STRATUM 2 build runs on the seeds. The S0 list names every other constant but not these two. PLAN §5 P0 says "record pass-1 wall time and peak RSS", but it does not say "per-chapter CPU from rusage". A P0 run done to that text can miss the CPU seed. STRATUM 2 then has no stated origin for the value.
- **Fix:** Add "`PASS1_RAM` and `PASS1_CORES` seeds (P0: per-chapter pass-1 peak RSS and CPU from `wait4` rusage), P0 breakdown and barrier cost" to the S0 list. State in the P0 bullet that P0 records per-chapter rusage CPU.

### M2. §6's "failure count for each check kind" is a build feature that no stratum owns
- **Location:** PLAN §6 Budget: "The first `mpres build` of the converted talk prints a failure count for each check kind." STRATA STRATUM 2/4/5 check output. STRATUM 11.
- **Problem:** The pre-approved exit in STRATUM 11 routes on these counts: "if the count exceeds what the remaining time covers…". No stratum builds the per-kind tally. The STRATUM 2 implementer reads §3.5, not §6. So STRATUM 11 has two choices, and both are wrong. It can edit the engine inside the D9 hour, which is scope creep inside a time box. Or it can do without the counts.
- **Fix:** In STRATUM 2, the check phase prints one summary line of failure counts by kind (pairing, empty beat, overlap, off-frame, transient). Test it with two overlays applied together, and assert the exact counts. STRATUM 4 and STRATUM 5 each add their kind (loop, min-text) to the same line. This is additive.

### M3. STRATUM 3 ships GC pin-awareness with no test, and the pin reader and pin writer are in different strata
- **Location:** STRATUM 3 `deck.py` "pins read". STRATUM 9 "`.presenter.json` pins under `SH`, GC respects pins". The only pin test is in STRATUM 9 ("pinned clip survives two builds").
- **Problem:** From STRATUM 3 to STRATUM 9, the `live_pins()` path (the `flock(.presenter.lock, SH|NB)` liveness probe plus the pin-file parse) exists, but no test runs it. That is "a code path nobody has seen execute" (code-principles, No fallbacks). STRATUM 3 cannot claim verified perfection with it in place. Also, STRATUM 3 defines the `.presenter.json` format through a reader that has no writer, and STRATUM 9 writes it. The text "GC respects pins" appears in both strata, so the owner is unclear.
- **Fix:** Put `write_pins`, `live_pins` and `presenter_lock()` in `deck.py` in STRATUM 3, which makes deck the single owner of the format. Add a STRATUM 3 build test: the test holds `presenter_lock()`, calls `write_pins({old sha})`, and runs two builds that change that beat. The old clip must survive. Mutant: GC ignores pins. A second case: with the lock not held, the clip is collected. Mutant: pins always treated as live. STRATUM 9 then only uses these functions. Remove "GC respects pins" from the STRATUM 9 description.

### M4. Sub-journey reviews need FRESH subagents, but the sub-journey agent is a subagent
- **Location:** sub-journey-export/NORTH-STAR.md "Reviews: looped FRESH Claude reviewers until only LOWs". STRATA line 71.
- **Problem:** Minh's standing rule says every subagent is told it must not spawn its own subagents. Strata rules say a sub-journey runs its own adversarial reviews with fresh reviewers. The NORTH-STAR says neither who spawns the reviewers nor that the rule is set aside. The sub-journey agent can therefore break Minh's rule. Or it can skip the reviews, or review its own work, which is not fresh.
- **Fix:** State the mechanism in the sub-journey NORTH-STAR. Pick one:
  - The sub-journey asks the parent (by `send_agent_prompt`) for each review round, and the parent spawns the reviewer.
  - Name the sanctioned exception: the sub-journey may spawn Claude reviewers only, with no further delegation. Record this in DECISIONS.

### M5. The CI ≤ 30 min budget is not carried into the sub-journey or the JOIN
- **Location:** STRATA rules line 11 ("every stratum that adds `build`, `qt` or `export` tests re-checks it"). sub-journey-export/NORTH-STAR.md (silent). JOIN line 89 ("full suite + CI").
- **Problem:** The export tests are the largest additions to the `export` marker. They click through every beat in two browsers, with 2× loop waits. The sub-journey's brief does not include the bound or the §5 P5 remedy. The JOIN is where the qt tests from STRATUM 7–9 and the export tests first run in one CI job, and the JOIN does not re-check the wall time. A merged suite over 30 minutes would pass "CI green" without anyone seeing the overrun.
- **Fix:** Add the CI ≤ 30 min rule and the remedy to the sub-journey NORTH-STAR, measured on its own branch. Make the JOIN re-measure the merged suite's CI wall time and apply the remedy before the End of Player Period review.

---

## LOW

### L1. STRATUM 3's index schema list omits fields that later strata read
STRATUM 3 lists the index fields explicitly but does not list the per-beat fingerprint (the §3.5 step 5 reuse rule needs it), `kind`, `chapter`, `frames` (`BuiltBeat.frames`, and §3.5 step 8 frame counts) or titles. The implementer will add the fingerprint. `frames` and `kind` can be missed until STRATUM 6, and the sub-journey then freezes them. **Fix:** List them in STRATUM 3's schema v1 bullet.

### L2. The stale-socket test is in STRATUM 7, but the clearing code is the Presenter's
PLAN §3.7 puts `QLocalServer.removeServer(name)` in the Presenter's launch path. STRATUM 7 has no Presenter, so a STRATUM 7 test would clear the socket itself, which is tautological. Or it would force the Audience to own the clear, which is a deviation from the PLAN. **Fix:** Move "stale socket cleared, listening works" to STRATUM 8. Or record in DECISIONS that the Audience clears its own server name before `listen`.

### L3. `clips_shared`/`clips_exclusive` are added in STRATUM 2 but first used in STRATUM 3 and STRATUM 6
STRATUM 2 has no commit and no reader, so these functions have no caller and no test in STRATUM 2. That is scaffolding for a case that does not occur yet. **Fix:** Add them in STRATUM 3, which has the commit `EX` and the "build during a held `SH` waits at commit" test.

### L4. The stills-only path in §3.5 step 8 never runs in a test
A `stills.py` edit regenerates stills with nothing rendered, and step 8 then samples its own width. No stratum tests this path. **Fix:** Add `stills.py` to STRATUM 3's engine-edit pattern: render 0, new-hash stills exist, old-hash stills are collected.

### L5. "Closing the Presenter window" sends `Quit` per PLAN §3.7, but no stratum tests it
STRATUM 9 tests SIGINT and SIGTERM only. **Fix:** Add one qt case in STRATUM 9: close the Presenter window, and no Audience process remains. Mutant: `closeEvent` without `Quit`.

### L6. The P5 edge-fixture timing move is not in DECISIONS
STRATA line 22 moves P5's edge-fixture `mpres build` timing to STRATUM 3. This is a deviation from PLAN §5 P5, and it is recorded only in STRATA. **Fix:** Add one line to DECISIONS.

### L7. The Gate part 2 sentence can be misread
"before STRATUM 1, STRATUM 7, STRATUM 8 and the sub-journey NORTH-STAR are rewritten" reads as if STRATUM 1 is rewritten too. **Fix:** "Before STRATUM 1 begins, rewrite STRATUM 7, STRATUM 8 and the sub-journey NORTH-STAR whole…".

### L8. The sub-journey brief omits two things
- It does not tell the agent to write its own STRATA.md, which strata-rules require.
- It does not say where export gets the source height and fps for the `--height` default and the last-frame pts. Neither is on `Deck`/`BuiltBeat`. `av` stream probing of the clip is the natural answer.

**Fix:** State both in the NORTH-STAR, so the agent does not send a mid-run interface-change request.

### L9. The STRATUM 0 list omits some smaller probe outputs
- P1(a)'s last-frame-hold method verdict.
- P2's worker-RSS repeat spread (PLAN §3.11 cites it beside `WORKER_RAM`).
- P4's file size, open-to-first-frame time, tab memory and ≥120-beat result.
- Any extra allow-list roots (PLAN §3.5: "the probes may add roots"). No probe owns that discovery, so in practice the roots appear during STRATUM 2.

**Fix:** List these outputs. Say that extra allow-list roots are discovered in STRATUM 2, each cited beside the root.

### L10. `probes/p4/p5_browsers.py` source is missing
STRATA line 22 runs "P4's `p5_browsers.py`". Only `probes/p4/__pycache__/p5_browsers.cpython-312.pyc` exists. If P4 is still running, ignore this. Otherwise the P5 workflow cannot run.

### L11. STRATUM 5 does not state the min-text unit conversion
STRATUM 0 defines the unit as `font_size · SCALE_FACTOR_PER_FONT_POINT / frame_height`. I checked the inputs: `explainers/geometry.py:10` is 32/40, and `manim/constants.py:185` is 1/960. STRATUM 5's geometry check must compute the same expression with the `_mpres_ref` substitution. **Fix:** State the formula once in STRATUM 5, in `geometry.py`, with the frame height taken from Settings. Otherwise the defaults and the check can disagree, for example frame height 8 against Mixing Deluxe's 10.04.

### L12. The repo does not say where its list of Manim touches lives
N1 says "every Manim touch listed and tested one to one". The list exists only in PLAN §3.1, which never ships. P7 also changed the list: it nulls IO calls and wraps `save_static_frame_data`. **Fix:** Say which stratum writes the touch list into the repo (for example the header of `manim_hooks.py`/`clip.py`, or a README section), matching the P7 set, and check that each item has one hooks test.

### L13. STRATUM 1's `--help` no-manim test has no mutant it can catch yet
In STRATUM 1, `build.py` does not exist, so the PLAN's mutant (a top-level `import build`) cannot exist. **Fix:** In STRATUM 1, use the mutant "top-level `import manim` in `cli.py`". STRATUM 2 re-runs the test with the `import build` mutant.
