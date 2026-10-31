# STRATA review r4 (fresh eyes; reviews/ and plan-reviews/ not read)

Inputs read in full: STRATA.md, NORTH-STAR.md, DECISIONS.md, probes/P7.md, sub-journey-export/NORTH-STAR.md, OTHER.md, DEBT.md, PLAN rev 30-o (all 1247 lines), strata-rules.md, code-principles.md. I also spot-checked the in-progress P1 results files under probes/p1/results/.

Coverage result: every §9 deliverable (1–12), every §3 mechanism and every §3.11 test and fixture maps to exactly one stratum, or it is deferred with a recorded reason (P6 and Deliverable 12 go to FINAL; P5's build timing goes to STRATUM 3; both are in DECISIONS). Each overlay and each edge-fixture case maps to exactly one stratum. The findings below are the gaps that remain.

Counts: HIGH 0 · MEDIUM 3 · LOW 9

---

## MEDIUM

### M1. STRATUM 3's stills engine-edit test contradicts the PLAN's GC root set
- **Location:** STRATUM 3, Tests: "`stills.py` → 0 rendered, new-hash stills present, old-hash stills collected".
- **Problem:** the GC roots in PLAN §3.5 step 9 are the new index, the previous index and the pins. After a `stills.py` edit, the previous index still references the old-hash still paths (the index records "each beat's still paths", §3.5 step 9 and §3.1 deck). So one build after the edit must **keep** the old-hash stills. They become collectable only after a second build. The test as written can only pass if GC drops previous-index stills. An implementer who makes it green that way ships a GC that breaks the "previous index" root. That root is what keeps the Presenter's Replay safe across back-to-back builds.
- **Evidence:** PLAN §3.5 step 9: "GC deletes every file under `clips/` … that none of these reference: the new index; the previous index; …". This test does not appear in PLAN §3.11. STRATA added it.
- **Fix:** reword it as follows. After the `stills.py` edit build: 0 rendered, new-hash stills present, old-hash stills still present (rooted by the previous index). After one more build: old-hash stills gone. Mutant: GC that ignores the previous index.

### M2. The export sub-journey has no working copy of its own
- **Location:** STRATA "SUB-JOURNEY: export" line, and sub-journey-export/NORTH-STAR.md ("Branch `sj/export`").
- **Problem:** only a branch is named. If the sub-journey agent and the main stream (STRATUM 7–9) share the one clone at `conversation-contexts/manim-presentations-harness/manim-presentations-UI-and-harness`, each `git checkout` changes the other agent's working tree mid-edit and mid-test. Also, the second working copy needs its own `.venv` and `.tinytex`, so it must run `./setup.sh --dev`. That run takes the "link to a different clone" case (§0) and re-links `~/.local/bin/mpres` to the sub-journey copy. Nothing in the suite may resolve `mpres` through `~/.local/bin`. `uv run` puts `.venv/bin` first, so that holds today, but no rule states it.
- **Evidence:** the North Star says "Branch `sj/export`; all work and reviews scoped to it", with no path. The STRATA "Repo clone" line names one clone. Minh's flow puts one clone per feature under `conversation-contexts/<topic>/`.
- **Fix:** in both files, name a separate clone, for example `conversation-contexts/manim-presentations-harness/manim-presentations-UI-and-harness-sj-export` (a fresh `git clone`, or `git worktree add` with its own `uv sync`). State three things in the North Star:
  - The clone runs its own `./setup.sh --dev`.
  - That run re-links `~/.local/bin/mpres`. This is expected, and STRATUM 10's `readlink` cleanup restores the link.
  - Tests call `mpres` only through the venv or `bin/mpres`, never through `~/.local/bin`.

### M3. The STRATUM 0 gate has no route for P1 outcomes that have no pre-decided branch
- **Location:** STRATUM 0, "Gate (end of STRATUM 0)" and "Gate, part 2".
- **Problem:** the gate stops only on D12, the stateful-tag adoption, and the PLAN's "Minh is told before the strata begin" outcomes. For everything else it says "Otherwise proceed". Two P1 verdicts that STRATA lists as results have no pre-decided branch in the PLAN, and no stop:
  - **P1(a) last-frame hold.** The PLAN says only "P1 confirms" rev 14's sink-frame method (§3.7). There is no alternative if no method holds. STRATUM 7's `Play → playing → held at last-frame pts` and N3 rest on it. The partial probe data already shows the plain method failing (`probes/p1/results/ffmpeg_widget.json`: `"holds_last_frame": false` under `raw`). So this outcome is live.
  - **No-reopen-on-wrap.** PLAN §3.5 ("Parallel correctness") rests the crashed-Presenter and GC safety on "P1 confirms the chosen backend does not reopen the file on each loop wrap". The PLAN gives no remedy if it does reopen.
  
  As written, a failure of either is recorded in DECISIONS and STRATUM 1 proceeds. STRATUM 7 would then rest on an unverified or false assumption, which strata-rules forbid.
- **Fix:** add to the gate: "If P1(a) finds no method that presents the last-frame pts on the chosen backend and stack, or if the chosen backend reopens the file on loop wrap, stop and report to Minh before STRATUM 1." If P1(a) passes, part 2 names the winning method (raw or sink-reset) in STRATUM 7.

---

## LOW

### L1. Gate part 2's rewrite list omits the biggest Audience branches
STRATUM 7 still says "the P1/P5-chosen widget stack" and leaves `QT_MEDIA_BACKEND` unnamed. Part 2 lists the switch buffering, loop seam, Cover/Hold, export seam and last-frame seek. It does not list the backend (`darwin`/`ffmpeg`), the widget stack (`QVideoWidget`/sink-paint) or the P1(a) hold method. Fix: add those three to part 2's list, so the rewritten STRATUM 7 names them and carries no if/else. The partial P1 data shows `darwin` presenting 0 frames offscreen, so this choice is real.

### L2. The literal `4` should be `TEST_WORKERS_WIDE`
STRATUM 3 says "`--workers 1` vs `4` byte-identical … peak alive = `TEST_WORKERS_WIDE`" and "fixtures 1 vs 4". P5 can set `TEST_WORKERS_WIDE` to 3 (STRATUM 0). In that case `--workers 4` with "peak alive = 3" is self-contradictory. Fix: write `--workers TEST_WORKERS_WIDE` everywhere.

### L3. P5 ordering and scope in STRATUM 0
- P5 consumes P2's 480×270 script and the build-marker cost (parent + pass-1 peak + `TEST_WORKERS_WIDE` × worker), so it depends on P0 and P2. STRATA says only "before any stratum code". State "after P0/P2".
- PLAN §3.5 step 6 measures `MIN_SAMPLE_WINDOW` "on the runner **and** on mac-work-2". STRATUM 0 mentions only the runner workflow.
- STRATUM 0 cites "P4's `p5_browsers.py`". `probes/p4/` holds `p4_webkit_ci.py` and no `p5_browsers.py`. Use the real name, or note the name is pending.
- PLAN P5's "`./setup.sh --dev` succeeds" item cannot run before STRATUM 1, because `setup.sh` does not exist yet. In effect it moved to STRATUM 1's CI, but DECISIONS has no record of the move. Add one line, as was done for the build-timing move.

### L4. STRATUM 2 needs the peak-live counter that STRATUM 3 introduces
STRATUM 2's test "`--workers 1` peak live pass-1 children = 1" needs a printed peak-alive count. "peak-alive counter" first appears in STRATUM 3's `build.py` list. Fix: move it to STRATUM 2's `build.py` (pass 1 is its first user). STRATUM 3 then reuses it for workers.

### L5. No listed test for the `show_for`/`held` table
PLAN §3.7 says `show_for` is "tested exhaustively" and `held()` "is tested in the same table". STRATUM 8 lists both functions but not the table test. STRATUM 9 tests only the hot-swap behavior. Fix: add "`show_for`/`held` exhaustive table (Position × BeatKind × action); mutant: a held loop beat mapped to `Hold`" to STRATUM 8's tests.

### L6. No plain `Text` below `min_text` case
PLAN §3.11 build says "Text below `min_text` fails". STRATUM 5's overlays cover the Transform-then-scale cases, `DecimalNumber`, `Code` and `Table`, but not a plain small `Text` or `MathTex`. The `min_tex` path has no failing case at all. Fix: add `small Text` and `small MathTex` overlays. Together they exercise both keys of the provisional defaults.

### L7. CI ≤ 30 min has no escalation past the pre-decided remedy
STRATA's rule applies the §5 P5 remedy on a miss. If the suite is still over 30 min after the remedy (plausible: a 3-vCPU runner at xdist width 1 with dozens of build subprocesses), "CI green" cannot be reached and no route exists. The PLAN says the bound is Minh's to change. Fix: "if still over after the remedy, report to Minh with the projection".

### L8. Reviewers who mutation-test must also hold the heavy-lock rule
The `flock /tmp/mpres-heavy.lock` rule binds "main stream and sub-journey". The reviewer subagents of both run `build`/`qt`/`export` tests for mutation testing, on mac-work-2, while the other stream's qt real-time assertions run. Fix: state in the Rules and the sub-journey North Star that every reviewer prompt carries the flock rule and the host.

### L9. The README's duration warning has no owning stratum
Deliverable 2: "Its first printed line, **and the README's first paragraph**, say that the first run takes several minutes…". STRATUM 1's README is a stub (quick start, badge). STRATUM 10 covers the quick start, browsers and measured durations, but does not name the first-paragraph warning. Fix: name it in STRATUM 10, or in STRATUM 1's README stub.
