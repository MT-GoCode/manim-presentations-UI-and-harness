# STRATA review, round 10 (fresh eyes)

Scope read in full: STRATA.md, sub-journey-export/NORTH-STAR.md, NORTH-STAR.md, DECISIONS.md, DEBT.md, probes/P7.md, probes/P8.md, PLAN rev 30-o (all 1247 lines), strata-rules.md, code-principles.md. Spot-read for feasibility only: probes/p4/p4_webkit_ci.py header, probes/p1/results/missing_bogus.json, probes/timing/{run,synth,sampler}.py headers.

Coverage result: every §9 deliverable 1–12, every §3 mechanism and every §3.11 test maps to a stratum, the sub-journey, or a recorded DECISIONS drop/deferral (Syncing, D3, talks git repo, Deliverable 12 → FINAL, P6 → FINAL). Plan tests that are split across two strata are split coherently: mid-build edit (S3 clips, S6 `stale`), schema mismatch (S3 `NoPrevious`, S6 `IncompatibleBuild`), Fatal (S7 Audience side, S8 Presenter side). I found no ordering break. Everything a stratum uses exists in an earlier stratum or in S0. The sub-journey's Consumes list is all frozen by S6. File ownership is disjoint except for additive blocks in `cli.py` and `pyproject.toml`. The flock rule covers host contention.

Counts: HIGH 0, MEDIUM 1, LOW 11.

---

## HIGH

None.

---

## MEDIUM

### M1. P4's seek-target finding is not carried into the export NORTH-STAR, DECISIONS or the Gate part 2 list
- **Location:** sub-journey-export/NORTH-STAR.md ("last-frame pts = (frames−1)/fps"). Also STRATA.md S0 Gate part 2, and DECISIONS.md.
- **Problem:** The P4 probe found that a paused seek to the exact last-frame pts presents the frame *before* it in Chrome. The probe's player therefore seeks half a frame past the target. The plan text (§3.9 "seeking its `<video>` to the last frame's pts") and the sub-journey NORTH-STAR both say to seek to the exact pts. Gate part 2 rewrites the NORTH-STAR only "to name the branch each P4 verdict selected" (seek vs `<img>` overlay). The seek *target* is not a branch, so the gate as written may not carry it. An export agent that implements from the plan would seek to `(frames−1)/fps` and fail its own Previous displayed-frame test in Chrome. It would then have to rediscover something the probe already knows.
- **Evidence:** probes/p4/p4_webkit_ci.py:116: "Seek targets sit half a frame past the wanted pts: an exact last-frame pts presents the frame before it in Chrome." The module docstring also says the exit gate is "the paused seeks at the player's half-frame targets". DECISIONS.md has no P4 entry.
- **Fix:**
  1. When P4/P5 finish, add a DECISIONS entry with the measured seek rule per engine. For example: seek target = `(i + 0.5)/fps` for frame i, with the Chrome/WebKit evidence.
  2. Add "export seek target" to the Gate part 2 list, so the NORTH-STAR rewrite states the target explicitly.
  3. The test assertion still checks `mediaTime == (frames−1)/fps`. Only the seek target moves.
  4. Check whether P1(f) found the same thing for Qt's paused `setPosition(last_pts)`. If it did, carry it into S7 the same way.

---

## LOW

### L1. S0 gate: "If D12 misses, stop" is ambiguous against P3's pre-decided optimization
- **Location:** STRATA.md S0, Gate.
- **Problem:** §5 P3 says that if *exact fast-forward* misses D12 or D14, the stateful-tag optimization is adopted without asking Minh. Only a D12 miss after that (or a miss in P0's pass-1/barrier terms) is Minh's call (D12). The gate lists "P3 adopts" and "D12 misses" as two separate triggers with no order between them.
- **Fix:** Say "D12 misses with P3's verdict applied (pass-1 + barrier + P3's fast-forward), reported with P0's breakdown."

### L2. P0's copy route is a pre-decided branch that Gate part 2 does not name
- **Location:** STRATA.md S2 ("snapshot by P0's one copy route"). Also S0 Gate part 2.
- **Problem:** The two routes produce different code. `copy2` is one portable line. `clonefile` needs ctypes plus the "snapshot needs APFS" red line on `ENOTSUP`. S2 is the only stratum outside S7–S9 and the sub-journey whose code shape depends on a probe verdict, but Gate part 2 does not rewrite it.
- **Fix:** Add S2 to the Gate part 2 rewrite list, or rewrite the S2 bullet as soon as P0 records the route.

### L3. setup.sh's "CI → GITHUB_PATH" case reads as a setup branch, but the plan gives that job to the workflow
- **Location:** STRATA.md S1 test list ("CI → `GITHUB_PATH`").
- **Problem:** Plan §0 says: "In CI, the workflow adds `~/.local/bin` to `GITHUB_PATH` instead". CI step 1 does this before `./setup.sh --dev`, so `~/.local/bin` is already on PATH when setup runs. If setup also detects CI and writes `GITHUB_PATH`, one fact has two owners (Single source of truth).
- **Fix:** Phrase the fourth test as "with `~/.local/bin` already on PATH (the CI workflow's step 1), setup appends no rc line." Give setup no CI-specific branch.

### L4. S8 ships the fresh-start `require_fresh` refusal without its test, and S9 later edits S8's start path
- **Location:** STRATA.md S8 (`present` calls `deck.require_fresh` from the start), S9 (the refusal test plus the reconnect path that skips it).
- **Problem:** S8 can go green with an untested refusal. S9 then reorders S8's startup (connect first, then route on live-Audience) instead of only adding to it.
- **Fix:** Move the fresh-start refusal test into S8. In S8, order startup as connect, then route, then `require_fresh` on the fresh-start arm, so S9 only adds the reconnect arm.

### L5. Stills-only step-8 width constants are named only in S6, but S3 implements that path
- **Location:** STRATA.md S6 ("the same constants size STRATUM 3's step-8 stills-only path"). S3 does not mention them.
- **Problem:** The S3 implementer reads S3. `DECODE_CORES`/`DECODE_RAM(pixels)` are a STRATA addition (the plan leaves step 8's per-job constants unnamed), so the plan will not lead the implementer to them.
- **Fix:** Name `DECODE_CORES`/`DECODE_RAM(pixels)` from P4 in S3's `build.py` bullet.

### L6. S0 does not say where P4's WebKit verdicts come from
- **Location:** STRATA.md S0 (P4 "headless WebKit + `channel="chrome"`" run as a local subagent). DECISIONS demonlock entry.
- **Problem:** Local WebKit is killed during LOCKED hours. P4's WebKit loop-seam, last-frame-seek, open-to-first-frame and tab-memory numbers therefore come from the P5 workflow's `p4_webkit_ci.py --engine webkit`, that is, from runner numbers. S0 does not say this. The S0 results list does not say which machine each P4 number comes from.
- **Fix:** In S0, say that the P4 WebKit verdicts and numbers come from the P5 workflow run. Label each one "macos-latest" in DECISIONS.

### L7. P5 reuses P2's 480×270 script, which hard-codes the private Explainers checkout
- **Location:** STRATA.md S0, P5 bullet.
- **Problem:** probes/timing/run.py:17 and synth.py:20 point at `~/code/explainers/.venv` and its `.tinytex`. `MT-GoCode/explainers` is private (404 unauthenticated), so the runner cannot clone it. The P5 workflow needs its own uv env (manim 0.22, pycairo via Homebrew cairo) and TinyTeX, set through the existing `P_TEX` env override.
- **Fix:** Add one clause: the P5 workflow installs its own env/TinyTeX and runs `synth.py`/`rec.py` from the probe branch, with no Explainers checkout.

### L8. The export clone's `uv sync` skips setup's environment pieces
- **Location:** sub-journey-export/NORTH-STAR.md ("run `uv sync` and `uv run …` only").
- **Problem:** setup.sh runs `uv sync --compile-bytecode` with Homebrew cairo's `PKG_CONFIG_PATH`. A bare `uv sync` usually reuses uv's cached pycairo wheel, but if it builds pycairo from source it can fail. It also leaves Manim uncompiled until the first scene process writes bytecode.
- **Fix:** Specify `PKG_CONFIG_PATH=<setup's value> uv sync --compile-bytecode`.

### L9. S10 inherits §6's "commit to the talks repo" stop step, which DECISIONS made moot
- **Location:** STRATA.md S10 ("Stops when the hour runs out, per §6").
- **Problem:** §6's stop procedure begins with "Commit the converted sources … to the talks repo", and the acceptance step includes `git ls-files`. DECISIONS drops both, because the folder is not a git repo. S10 does not say what replaces them.
- **Fix:** Say: on stop, the converted sources stay in place in `~/manim-presentations/…`, the talk README lists the remaining failures, and `ls` shows lowercase `script.md` and none of the deleted files.

### L10. Dropping Syncing also dropped "the talks folder is absent" guidance from AGENT-INSTRUCTIONS
- **Location:** STRATA.md S11 (§3.12 minus Syncing).
- **Problem:** The only plan text for a missing `~/manim-presentations/` ("ask the user") lived in the dropped Syncing subsection. §3.12 also gives `.git` corruption as a reason to avoid `~/Documents`, which is stale now that the folder is not a repo.
- **Fix:** In S11, state that the agent creates `~/manim-presentations/` if it is absent. Keep only the iCloud clip-eviction reason.

### L11. Small mutant and test details are missing where the plan names them
- **Location:** S3 (worker RSS ≤ `WORKER_RAM`: the plan's mutant drops the pass-1 RSS term; cache-id change: the plan's mutant leaves the id out of the path). S6 (shots' `RamExceeded` routing, §3.5 step 6). S7 (`Loop` must *report* `looping`, not only keep playing).
- **Problem:** Each is specified in the PLAN, so the implementer will find it. This is listed for completeness only.
- **Fix:** Optional: name them inline.

---

## Checked and fine (not findings)
- **S7's `Fatal` test is feasible.** probes/p1/results/missing_bogus.json shows that requesting `bogus` silently loads `libffmpegmediaplugin.dylib`, so the dyld identity check sees a mismatch.
- **The index schema stays v1 from S3 onward.** S3 writes every field that S6, S9 and the export read (`build_id`, render pixel size/fps, `frames`, still paths).
- **Sub-journey interface is frozen and complete.** `Deck`, `Deck.render`, `BuiltBeat`, `require_fresh`, `clips_shared`, temp-dir naming, `script.parse`, the key map, `position_table.json` and the fixture-copy helper all exist by S6. The NORTH-STAR forbids `settings`/`av` re-derivation, and the TinyTeX copy keeps the allow-list and cache-id correct.
- **D10 still cuts without surgery.** S5 is its own stratum.
- **CI wall-time policy matches §5 P5.** The measurement moved to S3 per DECISIONS, and every heavy stratum re-checks it.
