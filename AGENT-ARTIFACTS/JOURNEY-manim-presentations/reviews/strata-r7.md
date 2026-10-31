# STRATA review r7 (fresh eyes)

Scope read in full: STRATA.md, NORTH-STAR.md, DECISIONS.md, DEBT.md, OTHER.md, sub-journey-export/NORTH-STAR.md, probes/P7.md, probes/P8.md, the PLAN rev 30-o, strata-rules.md, code-principles.md. reviews/ and plan-reviews/ not read.

Coverage result: I mapped every §9 deliverable (1–12), every §3 mechanism and every §3.11 test (unit, hooks, build, qt, e2e, export, CI steps) to a stratum, the sub-journey, FINAL, or a DECISIONS drop. I found no omission. Deliverable 12, P6 and the talks-repo/Syncing/D3 parts are deferred or dropped, and DECISIONS records why. Probe order (P1/P4, then P0/P2/P3, then P5) supplies every constant before the stratum that reads it. The gates handle every pre-decided P1/P3/P4/P5 branch.

Counts: HIGH 0 · MEDIUM 1 · LOW 8.

---

## HIGH

None.

---

## MEDIUM

### M1. STRATUM 11 runs after STRATUM 10's first-contact verification and can change what STRATUM 10 verified
- **Location:** STRATA.md STRATUM 10 and STRATUM 11 (line 102: "Its measured cold build replaces the probe-based Mixing-Deluxe-scale time in AGENT-INSTRUCTIONS").
- **Problem:** STRATUM 11 edits AGENT-INSTRUCTIONS.md after STRATUM 10 verified it. This is surgery on a verified artifact. Also, STRATUM 11 is the first real-scale build (57 beats, 3456×2168, real helpers and assets). It is the stratum most likely to find an engine defect, for example an allow-list root, `WORKER_RAM` at full resolution, or a check that misfires on real code. Any engine fix there comes after the End of Player Period review and after the first-contact run. The End of Project review re-checks the code, but nothing re-runs the first-contact run (§9.10) or setup's example build against the final engine and docs.
- **Evidence:** PLAN §9.10 requires the first-contact run against the shipped AGENT-INSTRUCTIONS and README. STRATA's rule says "everything after [a stratum] is either purely additive, or a wholesale deletion". STRATUM 11 has no dependency on STRATUM 10: it needs only the engine, `shots`, and the edge fixture's `cycle()` loop (STRATUM 4).
- **Fix:** Swap the two strata. Migrate Mixing Deluxe first (old S11), and record its measured cold build in DECISIONS. Then write AGENT-INSTRUCTIONS and README once, with the real number, and run first contact last (old S10). Put "End of Project Period" on the first-contact stratum. With this order, the probe-based number never enters the doc, and first contact verifies the final engine.

---

## LOW

### L1. STRATUM 4's file list omits `pass1.py`
- **Location:** STRATUM 4 "Files: manim_hooks.py, talk.py/records.py, build.py".
- **Problem:** PLAN §3.1 (pass1.py) says pass 1 "writes records.json + rasters .npy to its .media/<process>/ dir", after the pass-1 flag is cleared (§3.5 read allow-list). The rasters first exist in STRATUM 4, so `pass1.py` changes there.
- **Fix:** Add `pass1.py` (+ raster `.npy` write after the audit flag clears) to STRATUM 4's file list.

### L2. STRATUM 9 does not list the `deck.py` additions that hot-swap needs
- **Location:** STRATUM 9 description.
- **Problem:** Hot-swap watches the `build/` directory and reads `index.json`'s `build_id` (§3.7). PLAN §3.1 says "`deck` owns all of `build/`, and no other module builds a `build/...` path". So STRATUM 9 must add a `deck` function for the build directory and the `build_id` read. STRATUM 8 lists its own `deck.py` addition (`audience_log`), but STRATUM 9 lists none. If the implementer reads the path directly in `presenter.py`, the single-owner rule breaks.
- **Fix:** Add "`deck.py` (+ build-dir path for the watcher, `build_id(talk)` read)" to STRATUM 9.

### L3. The main stream has no freeze or broadcast rule for interfaces the sub-journey consumes
- **Location:** sub-journey-export/NORTH-STAR.md "Consumes (frozen by STRATUM 6 …)". STRATA.md has no matching rule.
- **Problem:** The freeze binds only the sub-journey. STRATUM 7–9 (and their review rounds) can change `deck`, `headroom`, `script`, `protocol` or the conftest fixture-copy helper. A breaking change would surface only at JOIN. Strata-rules make the originator responsible for broadcasting changes, and STRATA does not say this.
- **Fix:** Add one rule to STRATA: during STRATUM 7–9, changes to the consumed list are additive only. Any non-additive change is sent to the sub-journey agent before it lands.

### L4. The sub-journey's dependency and lockfile ownership is not stated
- **Location:** sub-journey-export/NORTH-STAR.md "Owns only".
- **Problem:** It owns one additive import-linter block in `pyproject.toml`, but it does not say whether it may add dependencies. A new dependency changes `[project.dependencies]` and `uv.lock`, which the main stream also owns. Merge conflicts in `uv.lock` are not simple additions.
- **Fix:** State "no new dependencies; if one is needed, report to the parent". Playwright, av and psutil are already in STRATUM 1.

### L5. Creating the repo empty for P5 makes `probe/p5` the default branch
- **Location:** STRATUM 0 P5 bullet ("the repo is created empty, and a `probe/p5` branch holds only a probe workflow … The branch is deleted afterwards").
- **Problem:** On an empty GitHub repo, the first pushed branch becomes the default branch. GitHub refuses to delete the default branch. So the step "branch deleted afterwards" fails as written.
- **Fix:** Push `main` with LICENSE only (STRATUM 1's file) before `probe/p5`, or create the repo with `--add-readme`. STRATUM 1 then builds on that commit.

### L6. The D12 latency target is never measured on the real engine
- **Location:** STRATUM 0 gate (D12 judged from P0 + P3), STRATUM 11.
- **Problem:** D12 (edit the last beat, rebuild in ≤ 20 s) is accepted from proxies: Explainers' pass 1, P3's throwaway fast-forward and P2's render rate. The real engine adds costs the proxies do not include: the snapshot copy, private cache copies, the `MIN_SAMPLE_WINDOW` sample before pass 1, the audit hook and tee verification. The PLAN makes P0 the acceptance, so this is not a gap against the PLAN. But STRATUM 11 already has the one real Mixing-Deluxe-scale talk, so one timing costs one command.
- **Fix:** In the Mixing Deluxe stratum, edit the last beat, rebuild, and record the wall time against D12 in DECISIONS. A miss goes to Minh with the phase breakdown, as D12 already says.

### L7. The min-text unit conversion is a resolved ambiguity, but it lives only in STRATA
- **Location:** STRATUM 0 P6 bullet (32/40 → 0.0041667/0.0052083 via `SCALE_FACTOR_PER_FONT_POINT / 8`). STRATUM 5 uses the same unit.
- **Problem:** The PLAN gives the unit only as "declared font_size as a fraction of frame height" and does not give the conversion. STRATA picks one. That choice is a resolved ambiguity, and DECISIONS is where those go. DECISIONS has the provisional values but not the formula. STRATA is an ordering document, and a later regeneration (Gate part 1) could drop the formula.
- **Fix:** Add one DECISIONS line with the formula and its two sources (explainers/geometry.py:10, manim/constants.py:185).

### L8. The sub-journey re-derives clip facts with `av` that the build already marked
- **Location:** sub-journey-export/NORTH-STAR.md "Source height, fps and last-frame pts come from probing each clip with `av` (not from `Deck`)".
- **Problem:** The build's stream check proved that each clip's size, fps and time base equal the settings. The index also records `frames` per beat. Re-probing every clip derives the same fact a second time, which code-principles "Mark, then route" and "Single source of truth" name as a tell. Export needs to decode the clips to re-encode them anyway, so the cost is small. The issue is having two sources for one fact.
- **Fix:** Either let `deck` expose the render settings and `frames` (deck → settings is already an arrow), or keep `av` probing and state in the sub-journey NORTH-STAR why it is a boundary read. The sub-journey's own review can decide. Note it there so the choice is explicit.
