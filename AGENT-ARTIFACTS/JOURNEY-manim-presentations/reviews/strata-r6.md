# STRATA review r6 (fresh eyes; reviews/ and plan-reviews/ not read)

Scope read in full: STRATA.md, NORTH-STAR.md, DECISIONS.md, DEBT.md, sub-journey-export/NORTH-STAR.md, probes/P7.md, probes/P8.md, PLAN rev 30-o, strata-rules.md, code-principles.md. Spot-checked probes/p4 scripts for the P5 gate.

Coverage result: every §9 deliverable 1–12, every §3 mechanism and every §3.11 test maps to exactly one stratum, the sub-journey, FINAL, or a DECISIONS entry, with the exceptions below. Ordering holds: no stratum uses a module, fixture, constant or probe result before it exists.

Counts: HIGH 0, MEDIUM 4, LOW 6.

---

## HIGH

None.

---

## MEDIUM

### M1. The export sub-journey's clone has no TinyTeX, so no `mpres build` can run in it
- **Location:** sub-journey-export/NORTH-STAR.md ("In that clone run `uv sync` and `uv run …` only — never `./setup.sh`").
- **Problem:** TinyTeX is repo-local. PLAN §2 prior art: "Repo-local TinyTeX". §3.5 step 3 allow-list root: "the engine repo's `.tinytex`". `.tinytex` is gitignored and only `setup.sh` installs it. The `cache-id` (§3.5 step 3) hashes "the TinyTeX revision and dvisvgm version". So every build computes the cache-id from `.tinytex`, including builds with no MathTex. In `export-clone/` that directory does not exist. Every export test that builds a fixture fails on its first run, and so does conftest's session-scoped warm TeX cache.
- **Evidence:** PLAN lines 152, 423, 450, 939. The NORTH-STAR bans `setup.sh` because setup re-links `~/.local/bin/mpres`. Nothing else provides `.tinytex`, and the PKG_CONFIG_PATH that setup exports is also missing.
- **Fix:** In the sub-journey NORTH-STAR, give the clone its toolchain without re-linking. Add one step: `cp -cR <main-clone>/.tinytex <export-clone>/.tinytex`. This is an APFS clone, so it costs no disk. Run it before `uv sync`, with setup's `PKG_CONFIG_PATH` exported. Do not use a symlink. The allow-list compares `realpath`, and a symlink would resolve into the main clone. State that Playwright browsers come from the shared `~/Library/Caches/ms-playwright`, which the main clone's `setup.sh --dev` filled. Both clones resolve the same Playwright version from the same `uv.lock`.

### M2. S6 hands present's stale refusal and its reconnect branch to S9, and S9 has no test for either
- **Location:** STRATUM 6 tests ("`present`'s fresh-start refusal of a stale build is S9's"). STRATUM 9 description and tests.
- **Problem:** S9's description names `require_fresh` and the reconnect path. Its test list has neither. Two routes ship untested:
  - A fresh start on a stale build refuses and names the file (§3.4, §3.6, §3.10 step 1). Mutant: `present` never calls `require_fresh`.
  - A reconnect to a live Audience adopts the stale deck and shows `stale` in amber instead of refusing (§3.6). This is Rule 4's promise that a crashed Presenter "can always be restarted mid-talk, even after unbuilt edits". Mutant: `present` calls `require_fresh` on every path. Then a mid-talk restart after an edit exits, and the presenter is stuck on stage.
  
  The PLAN's §3.11 list also omits these tests. But STRATA explicitly hands them to S9, and the handoff dropped them.
- **Fix:** Add two qt tests to S9:
  - Edit a chapter after the build, then run `present` with no Audience alive. It exits nonzero, names the file and prints the `mpres build` command.
  - Edit a chapter, SIGKILL a running Presenter so its Audience stays up, then re-run `present`. It connects, adopts the deck and shows amber `stale`, with no refusal.
  
  Name both mutants above.

### M3. STRATUM 1's setup.sh still installs `gh`, but the only reason for `gh` was dropped
- **Location:** STRATUM 1 `setup.sh` ("uv/cairo/pkg-config/gh via brew").
- **Problem:** PLAN §3.1 gives one reason to install `gh`: "talk syncing needs it". The §3.12 `gh auth status` text exists for the same reason. DECISIONS (2026-10-30, Minh) drops syncing, the talks repo and D3. Its drop list never mentions `gh`, and STRATA explicitly tells S1 to install it. Setup would then install a dependency that nothing uses. That breaks the "fewest parts" and "no stale parts" principles. It also puts a gh/auth mention into a public tool's install path and possibly into AGENT-INSTRUCTIONS.
- **Fix:** Remove `gh` from S1's setup.sh list. Extend the DECISIONS syncing entry to drop §3.1's `gh` prerequisite and §3.12's `gh auth status` instruction. The engine repo's own git and gh use goes through `gitas` for Minh and needs nothing from setup.

### M4. The P5 check "rVFC fires after a paused seek" has no gate, but export's no-black-frame design depends on it
- **Location:** STRATUM 0 Gate, parts 1 and 1b.
- **Problem:** PLAN §5 P5 says "Check that `requestVideoFrameCallback` fires after a paused seek and reports the target pts". It gives no pre-decided branch. The export player depends on it in several places:
  - It holds the previous video "until the incoming one's first `requestVideoFrameCallback`" on every transition, including seeked-while-paused ones (Previous, jump, `Before`).
  - The §3.11 frame-identity tests also depend on it.
  
  P4's `<img>` overlay branch fixes frame identity, not callback firing. If rVFC does not fire after a paused seek in WebKit or Chrome, the player stays stuck behind the previous video. S0's gate stops only on "WebKit or Chrome fails". That wording reads as play-to-ended. Part 1b lists only P1 outcomes. So STRATA lists this result as an output but never routes on it.
- **Evidence:** p4_webkit_ci.py's docstring says it exits 0 only if "play-to-ended and the paused seeks … pass (the P5 gate)". The script gates on it, but STRATA's wording does not.
- **Fix:** Add one line to Gate part 1b: "stop and replan (Minh told) if rVFC does not fire after a paused seek with the target pts in headless WebKit or `channel=\"chrome\"`". Or name the failing `p4_webkit_ci.py` exit as the gate condition.

---

## LOW

### L1. P1 and P4 run at the same time, which contradicts the timing-isolation rationale
- **Location:** STRATUM 0 ("P1 … and P4 … run as parallel subagents").
- **Problem:** Both probes contain wall-clock measurements: P1(b) clip-switch latency, and P4's open-to-first-frame time and peak tab memory. P4 also runs 9×57 encodes. P0/P2/P3 run serially "so no probe contends with a timing probe", but P1 and P4 contend with each other. DEBT also records load from other agents.
- **Fix:** Record the load average beside each P1(b) and P4 timing (p4_talk.py already does), and take the timing portions under `/tmp/mpres-heavy.lock`. The black-frame verdict reads sink frames, so it is load-robust and unaffected.

### L2. Gate part 2 should also rewrite STRATUM 9
- **Location:** STRATUM 0 Gate part 2.
- **Problem:** S9's e2e test asserts `Now` after ↑ and after a timeline jump. S9's hot-swap test asserts `playing → held`. If P1(f) selects the muted-Hold fallback, a held state first reports `playing` and then `held`. If P1(c) selects double-buffered loops, "looping" is no longer observed as `loops() == Infinite`. S9's expectations therefore depend on the branch that P1 picks.
- **Fix:** List STRATUM 9 alongside 7 and 8 in Gate part 2.

### L3. The "every beat has at least one animation" check has no test
- **Location:** STRATUM 2 checks and tests.
- **Problem:** §6's way-out table routes on this check ("a beat that only `add`ed"). No overlay exercises it, and the PLAN's §3.11 list has none either. A mutant that drops the check passes the suite.
- **Fix:** Add a `tests/fixtures/broken/` overlay with a beat that only calls `add`. Assert the exact message and `chapters/x.py:line`.

### L4. STRATUM 11 does not exclude the old `build/` from the copy
- **Location:** STRATUM 11 ("Copy the talk … first").
- **Problem:** §6 says the old manim-slides `build/` is "Not copied". If it is copied, its files sit under the new `build/`, which `deck` owns. GC sweeps only `clips/` and the wipe removes only `.media`, so the leftovers stay as permanent cruft.
- **Fix:** Write "copy excluding `build/` and `__pycache__/`".

### L5. FINAL does not say what happens if P6's minimums fail the fixtures
- **Location:** FINAL ("re-run the full suite and CI").
- **Problem:** If Minh's P6 picks exceed the provisional 32/40 equivalents, then hello, the edge fixture and the S5 "legal size" fixtures may fail. Re-running the suite says nothing about who fixes them.
- **Fix:** Add one line: "resize any fixture or `examples/hello` text the new minimums reject, then re-run the suite and CI".

### L6. S10 documents a Mixing-Deluxe-scale cold-build time that was never measured with `mpres build`
- **Location:** STRATUM 10 ("Mixing-Deluxe-scale cold build from P3"). STRATUM 11.
- **Problem:** P3 measured throwaway code. The real number appears in S11's first build, after S10's docs are already written. Agents size their timeouts from this number.
- **Fix:** S11 records its cold-build wall time and replaces the number in AGENT-INSTRUCTIONS, with its origin. A CI run follows.
