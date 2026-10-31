# STRATA review r9 (fresh eyes)

Scope read in full: STRATA.md, sub-journey-export/NORTH-STAR.md, NORTH-STAR.md, DECISIONS.md, DEBT.md, probes/P7.md, probes/P8.md, PLAN rev 30-o, strata-rules.md, code-principles.md.

Coverage result: every §9 deliverable 1–12, every §3 mechanism and every §3.11 test maps to exactly one stratum, the sub-journey, FINAL, or a recorded DECISIONS drop (syncing, gh, D3, git ls-files, P6 → FINAL, deliverable 12 → FINAL). Ordering holds: no stratum uses a module, constant or probe result before it exists. The sub-journey's interface is frozen at STRATUM 6, its file set is disjoint except for additive cli.py/pyproject blocks, and host contention is handled by the shared flock. Findings below are the remaining gaps.

Counts: HIGH 0, MEDIUM 1, LOW 6.

---

## HIGH

None.

---

## MEDIUM

### M1. `mpres shots`' parallel decode pool has no measured per-job cost
- **Location:** STRATUM 6 (`shots.py`); STRATUM 0 constants list. A smaller instance is in STRATUM 3 (step 8's own-width path when nothing rendered).
- **Problem:** PLAN §3.8 sizes the `middle`-still decode pool with `headroom.width(sample, per_job_cores, per_job_ram, n)`. No probe measures a decode job's cores or RAM. STRATUM 0's list of constants has `ENCODE_CORES/ENCODE_RAM` for export (P4) and `WORKER_*` for render (P2), but nothing for `stills.still_at`. `shots` may import only `{deck, stills, headroom}` (§3.1 arrows). So it cannot borrow `WORKER_RAM`, which build derives from the index's pass-1 peak plus P2's `worker_overhead`. An implementer of STRATUM 6 must invent a number. That violates "every constant comes from a measurement" and is an unverified assumption with no probe or gate behind it.
- **Evidence:** PLAN §3.8 "sized by `headroom.width`, with `--workers N` as the override". PLAN §5 P2/P4 list no decode measurement. STRATA STRATUM 0 "human-verifiable results" has no decode constant. STRATUM 6 says only "`shots.py`".
- **Fix:** Add one measurement to P4, which already times `av` jobs per height. Measure a single `still_at` decode job's process CPU and peak RSS at 480×270, 1920×1080 and 3456×2168. Record them as `DECODE_CORES` and `DECODE_RAM(pixels)` in DECISIONS, and add them to STRATUM 0's human-verifiable list. Name them in STRATUM 6 as `stills.py` constants, cited beside the code. For STRATUM 3's step-8 fallback, say explicitly that it uses the same `DECODE_*` constants, or `WORKER_*` as the PLAN's "conservative upper bound". Pick one and write it down.

---

## LOW

### L1. STRATUM 0 and DECISIONS disagree on when `probe/p5` is deleted
- **Location:** STRATUM 0, P5 bullet ("The branch is deleted afterwards"). DECISIONS: "default branch is set to `main` in STRATUM 1 … before `probe/p5` is deleted".
- **Problem:** The repo is created empty, and `probe/p5` is its first and only branch, so it is the default branch. GitHub refuses to delete the default branch. The deletion therefore cannot happen in STRATUM 0. STRATUM 1's file and step list does not name the `gh repo edit --default-branch main`, the branch delete, or the `gh run delete` cleanup.
- **Fix:** Remove "The branch is deleted afterwards" from STRATUM 0. Add one line to STRATUM 1: after the first push of `main`, run `gitas exec personal -- gh repo edit --default-branch main`, delete `probe/p5`, and run `gh run delete` on its runs.

### L2. `Deck.render` and the render settings in the index are not recorded as a deviation
- **Location:** STRATUM 3 (index adds "the render settings the clips were made with"), STRATUM 6 (`Deck.render`), and the sub-journey's Consumes list.
- **Problem:** PLAN §3.5 step 9's index field list and §3.6's `Deck` contents do not include these. The addition is sound: export needs the source size and fps without importing `settings`. But it is a frozen sub-journey interface that exists only in STRATA.md. Later readers checking against the PLAN will see an unexplained field.
- **Fix:** Add one DECISIONS line. It should state that the index records pixel width, pixel height and fps, that `Deck.render` exposes them, and why: §3.1 forbids `export → settings`, and the export must not re-derive these with `av`.

### L3. STRATUM 8 ships `mpres present` without the fresh-start staleness refusal and without graceful close
- **Location:** STRATUM 8 / STRATUM 9 split.
- **Problem:** At STRATUM 8, `present` exists but does not call `require_fresh` on a fresh start. That breaks PLAN §3.4 ("no fallback to an old build") for one stratum, and the gap is not named as scaffolding. STRATUM 8's qt tests also spawn real `setsid` Audience processes, and `closeEvent → Quit` lands only in STRATUM 9. Unless teardown sends `Quit`, each test leaves an Audience running on mac-work-2 or CI, where it competes with the qt real-time assertion.
- **Fix:** Move the fresh/reconnect routing (`require_fresh` on a fresh start only) into STRATUM 8. `Deck.require_fresh` exists since STRATUM 6, and STRATUM 8 already decides connect-or-launch. STRATUM 9 keeps the amber/red reconnect tests. Separately, state that STRATUM 8's qt fixtures send `Quit` over the socket at teardown and assert that no Audience pid survives.

### L4. The STRATUM 6 `IncompatibleBuild` tests cover a missing clip but not a missing still
- **Location:** STRATUM 6 tests.
- **Problem:** PLAN §3.6 names "a clip or still file named by the index is missing". A `Deck.open` that checks only clips passes the listed tests.
- **Fix:** Add a test case: delete one `first.png`, and expect `IncompatibleBuild`. The mutant is "checks clip existence only".

### L5. P3 should name P7's fast-forward mechanism explicitly
- **Location:** STRATUM 0, the P3 bullet.
- **Problem:** DECISIONS says P7's null-IO `play_internal` replaces PLAN §3.1's re-implemented fast-forward. P3 produces `fast_forward_cost(start)`, `CHUNK_COST` and the D12/D14 verdicts. Read literally from PLAN §5, P3 would time the re-implementation instead. The cost difference is probably small, but the constants should come from the shipped mechanism.
- **Fix:** Add to the STRATUM 0 P3 bullet: "fast-forward timed with P7's null-IO mechanism (`probes/p7`)".

### L6. setup.sh's link-routing cases have no automated check
- **Location:** STRATUM 1, setup.sh (shadowing refusal, re-link to this clone, idempotent rc append, CI `GITHUB_PATH`).
- **Problem:** Only STRATUM 11's `readlink` assertion and CI's single fresh run exercise setup. The shadowing and re-link branches never run in any test. PLAN §3.11 does not require such a test, so this is LOW. But it is "a code path nobody has seen execute".
- **Fix (optional):** Add one `unit`-marked test. Run the routing step of `setup.sh` with `HOME` and `ZDOTDIR` pointed at `tmp_path`, using a pre-made decoy link and a decoy `mpres` earlier on `PATH`. Assert the re-link message, the shadowing failure, and that the rc line appears exactly once after two runs. Splitting setup so that the routing step runs without TinyTeX would be needed.
