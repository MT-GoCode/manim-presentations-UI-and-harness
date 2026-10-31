# Strata review r8 (fresh eyes)

Scope read in full: STRATA.md, sub-journey-export/NORTH-STAR.md, NORTH-STAR.md, DECISIONS.md, DEBT.md, probes/P7.md, probes/P8.md, PLAN rev 30-o, strata-rules.md, code-principles.md. Spot-checked Manim 0.22 source (Explainers venv) for S5's assumptions: `Code` and default `Table` build `Paragraph`; `AnimationGroup.clean_up_from_scene` forwards to each child; `SCALE_FACTOR_PER_FONT_POINT = 1/960`. `flock` exists at /opt/homebrew/bin.

Coverage result: every §9 deliverable (1–11 in strata; 12 deferred to FINAL with a DECISIONS reason), every §3 mechanism, and every §3.11 unit/build/qt/e2e/export test maps to exactly one stratum or the sub-journey. The only dropped items (Syncing, gh, talks git repo, `git ls-files`, D3) are recorded in DECISIONS. Probe outputs are all produced in STRATUM 0 before the first stratum that needs them.

## HIGH

None.

## MEDIUM

### M1. Export has no sanctioned source for source height/width/fps
- **Location:** sub-journey-export/NORTH-STAR.md ("Source height and fps come from the talk's `Settings`" and the Consumes list); STRATUM 6 (`Deck`/`BuiltBeat`); STRATUM 3 (index schema v1 fields).
- **Problem:** Export needs the source height (`--height` default `min(H₀, source)`, refusal above source), the source width (`2·round(H·src_w/src_h/2)`) and fps (last-frame pts = (frames−1)/fps, frame rate kept at source). The NORTH-STAR says to take them from the talk's `Settings`, but:
  - `settings` is not in the frozen Consumes list, so the main stream may change it while the sub-journey depends on it;
  - PLAN §3.1 gives `export → {deck, script, headroom, protocol}`. `export → settings` is not an allowed arrow, and DECISIONS does not sanction it;
  - `Deck`/`BuiltBeat` (§3.6, STRATUM 6) carry no render settings, and the index fields in STRATUM 3 (§3.5 step 9) do not record them;
  - the NORTH-STAR forbids re-deriving them with `av`.
  The sub-journey therefore cannot finish without either breaking the freeze (a mid-flight interface change) or adding an unplanned arrow. No import-linter contract forbids `export → settings`, so the second route would pass CI without anyone noticing.
- **Fix:** In STRATUM 6, make `Deck` carry the build's render settings (`deck → settings` is already an allowed arrow): either `Deck.settings: Settings`, loaded from the talk's `talk.toml` (which `require_fresh` proves unchanged since the build), or, better for single source of truth, have STRATUM 3's index record `render` (pixel_width, pixel_height, frame_rate) and have `Deck` expose it. Add that field to the sub-journey's Consumes list. Change the NORTH-STAR line to "from `Deck`'s render settings". Add an import-linter contract in the sub-journey that `export` imports only `{deck, script, headroom, protocol}` inside the package, so the §3.1 arrow is enforced as data.

## LOW

### L1. Gate part 2 rewrites S7–S9 and the sub-journey NORTH-STAR with no review round
- **Location:** STRATUM 0, "Gate, part 2".
- **Problem:** Four already-reviewed documents are rewritten whole (one of them is the frozen sub-journey contract), and nothing states that the rewrite is reviewed again.
- **Fix:** Append "then one FRESH strata review round on the rewritten sections, repeated until it returns no HIGH/MEDIUM, before STRATUM 1".

### L2. `probe/p5` deletion timing contradicts DECISIONS
- **Location:** STRATUM 0 P5 bullet ("The branch is deleted afterwards") vs DECISIONS ("default branch set to `main` in STRATUM 1 … before `probe/p5` is deleted").
- **Problem:** The repo is created empty, so `probe/p5` is its only branch and becomes the default branch. GitHub refuses to delete the default branch. The S0 wording implies deletion in S0.
- **Fix:** In STRATUM 0, write "deleted in STRATUM 1, after `main` becomes the default branch". Name that step in STRATUM 1's description.

### L3. STRATUM 5's file list omits the files that carry the size reference
- **Location:** STRATUM 5, Files.
- **Problem:** Geometry is pure over recorded units, so the `_mpres_ref`/`Paragraph` size reference must flow through `records.py` (model field) and `talk.py`/`pass1.py` (recording). The new failure kind also touches `build.py`. Only `manim_hooks.py` and `geometry.py` are listed. The implementer will add these from the PLAN.
- **Fix:** Add `records.py`, `talk.py`/`pass1.py` and `build.py` to the S5 file list.

### L4. setup.sh's link-routing cases have no execution evidence in STRATUM 1
- **Location:** STRATUM 1 (`setup.sh`, the four link-routing cases).
- **Problem:** CI exercises only the GITHUB_PATH case. STRATUM 11 exercises re-link and rc-append. The shadowing-refusal case never runs. Under code-principles, this is "a code path nobody has seen execute".
- **Fix:** In STRATUM 1, add a `unit` test that runs `setup.sh`'s link step (or the whole script with a phase filter, if setup supports it) under a throwaway `HOME`/`ZDOTDIR`/`PATH`. Cover the four cases and give each one its mutant. If that costs too much, record the shadowing case as an accepted gap in DECISIONS.

### L5. STRATUM 10's D12 re-timing has no routing on a miss
- **Location:** STRATUM 10 ("record the wall time against 20 s").
- **Problem:** The D12 decision is judged in S0 on the synthetic. If the real-engine number misses, the stratum says nothing about what happens. A measurement without a consequence is exhaust.
- **Fix:** Add "on a miss, report to Minh with the phase breakdown (D12: Minh decides)".

### L6. Local Qt real-time assertion under other agents' load
- **Location:** STRATUM 7 (`Loop` still playing after 2×) and the Rules' host-contention bullet; DEBT (load 159 observed).
- **Problem:** `flock` serializes only our own heavy runs. §3.11 names Qt real-time playback as the suite's one timing-based assertion, so a heavily loaded mac-work-2 can turn it red locally for no defect.
- **Fix:** In the Rules bullet, state that a local `qt` red is re-run when load < 4 (the DEBT threshold), with the load recorded, and that CI is authoritative for it. This matches how WebKit is already handled.

### L7. The sub-journey's `uv sync` may not install dev dependencies
- **Location:** sub-journey NORTH-STAR ("run `uv sync` and `uv run …` only").
- **Problem:** If STRATUM 1 declares pytest/playwright as an extra rather than a `[dependency-groups] dev`, a plain `uv sync` omits them. The NORTH-STAR also mentions `[project.optional-dependencies]`, which hints at extras.
- **Fix:** Write the exact command that `setup.sh --dev` uses (for example `uv sync --compile-bytecode --all-extras`, or `--group dev`), copied from STRATUM 1's setup.sh, so the export clone has the same environment as the main clone.

### L8. STRATUM 11's first-contact run is heavy but not under the flock rule
- **Location:** STRATUM 11 (fresh-clone `./setup.sh` with TinyTeX install and example build, run through Claude).
- **Problem:** The Rules bullet covers pytest runs, probes and encodes, but not this one. It also produces the "measured setup duration" that the README publishes, and contention would skew that number.
- **Fix:** Run it under `flock /tmp/mpres-heavy.lock`. Record the load average beside the measured durations, as DEBT requires for timings.
