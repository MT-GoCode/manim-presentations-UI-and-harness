# STRATA review r5 (fresh eyes)

Read in full: STRATA.md, sub-journey-export/NORTH-STAR.md, NORTH-STAR.md, DECISIONS.md, DEBT.md, OTHER.md, probes/P7.md, PLAN rev 30-o, strata-rules.md, code-principles.md. reviews/ and plan-reviews/ not read.

Coverage walk: every §9 deliverable 1–12, every §3.11 test (unit, hooks, build, qt Audience, qt Presenter, e2e, CLI chain, export, CI steps and caches), and the §3.1/§3.5/§3.6/§3.7/§3.8/§3.9 mechanisms were mapped to a stratum. Deliverable 12 and P6 are deferred to FINAL with recorded reasons. All §3.11 tests land in exactly one stratum, or are split cleanly across two (build side in S3, `Deck` side in S6). No HIGH found. Ordering is sound. Probes feed every constant before first use. Gate part 2 rewrites S7, S8 and the sub-journey before S1, so no stratum carries a P1/P4 branch.

## HIGH

None.

## MEDIUM

### M1. `PASS1_RAM`/`PASS1_CORES` read from the previous index has no owning stratum
- **Location:** STRATUM 2 (§3.5 steps 1–4), STRATUM 3 (§3.5 steps 5–9).
- **Problem:** §3.5 step 3 says the pass-1 width uses `PASS1_RAM` = the largest per-chapter pass-1 peak in the *previous index* and `PASS1_CORES` = the largest per-chapter pass-1 CPU in the previous index. P0 seeds them only when no index exists. S2 has no index, so it runs on P0's seeds only (S0 says this explicitly). S3 adds the index fields that feed this ("per-chapter pass-1 RSS/CPU"). But S3 claims steps 5–9 only, and its `build.py` list does not include switching the step-3 width to `deck.previous(...)`. S2 is already closed. So the step-3 read is never wired, and every build would size pass 1 from P0's seeds forever.
- **Evidence:** STRATA S0 results: "`PASS1_RAM`/`PASS1_CORES` seeds (STRATUM 2 runs on them alone, since it has no index)". S3 build.py: "deletes STRATUM 2's stop; post-commit prune …; steps 5–9; width lines …". PLAN §3.5 step 3, step 9 ("`PASS1_RAM` and `PASS1_CORES` are read from the previous index; P0's measurements seed them only when there is none").
- **Fix:** Add to S3 `build.py`: "pass-1 width inputs read from `deck.previous` (`PreviousBuild` → index maxima; `NoPrevious` → P0 seeds)". Add one test: after a build, the printed machine-readable pass-1 line carries the index maximum, not the P0 seed (mutant: always use the seed). Route on the `PreviousBuild | NoPrevious` tag, which S3 already builds.

### M2. Tests must invoke the engine of the clone under test, never `mpres` from `PATH`
- **Location:** STRATUM 1/2 `tests/conftest.py` (build-subprocess helper); sub-journey NORTH-STAR; STRATUM 9 signal tests; STRATUM 10.
- **Problem:** PLAN §3.11 says "Builds run as `mpres build` subprocesses". On mac-work-2, `mpres` on `PATH` is `~/.local/bin/mpres`. That link runs `uv run --project <main clone>`. Three cases then test the wrong code without any error:
  1. Sub-journey tests in `export-clone/` that call `mpres build` run the main clone's build.
  2. Main-stream tests that run during S10's first-contact run use the throwaway clone, because that run re-links `mpres` until cleanup.
  3. Engine-edit tests use `PYTHONPATH=<copy>` on top of whichever venv the link names.
  The sub-journey NORTH-STAR guards the link (never `./setup.sh`), but not this lookup. No stratum states how the helper resolves the command. The S1 implementer cannot know a second clone will exist. This is the "what runs is not what was edited" trap.
- **Evidence:** sub-journey NORTH-STAR: "never `./setup.sh`, which would re-link `~/.local/bin/mpres` away from the main clone". STRATA S9: "signals through `bin/mpres`". PLAN §3.11 test rules. CI is unaffected, because there `~/.local/bin/mpres` links to the checkout under test.
- **Fix:** In S1, state that the conftest build helper invokes `[sys.executable, "-P", "-m", "manim_presentations.cli", …]`, or the repo's own `bin/mpres` resolved from `Path(manim_presentations.__file__)`. It must never resolve `mpres` through `PATH`. S9's `bin/mpres` signal tests use the repo-relative `bin/mpres`. Add the matching line to the sub-journey "Consumes" list.

### M3. S10 first-contact isolation rests on an unprobed assumption, and S10 drops the PLAN's stated condition
- **Location:** STRATUM 10; STRATUM 0 (no matching probe).
- **Problem:** S10 says "real Claude binary, `bypassPermissions`, isolated `CLAUDE_CONFIG_DIR`" with no condition. PLAN §9.10 says `CLAUDE_CONFIG_DIR=<throwaway>` "if the auth route allows", and it accepts the gap otherwise. Three facts are unverified:
  1. That a fresh config dir can authenticate. A fresh dir starts with no login, and the macOS keychain credential entry may be keyed per config dir.
  2. That `~/.local/share/claude/versions/<v>` exists on mac-work-2 and is what the wrapper resolves.
  3. That `-p` plus `--permission-mode bypassPermissions` runs non-interactively in a fresh config dir.
  Strata rules forbid an unverified assumption and an if/else inside a stratum. The PLAN's conditional must be settled by a probe, not at S10.
- **Fix:** Add a cheap probe P8 to S0. It runs the resolved real binary with a throwaway `CLAUDE_CONFIG_DIR`, a stripped `PATH` and a throwaway `ZDOTDIR`, with `-p "reply ok"` and the bypass flag. Record in DECISIONS (a) the binary path, (b) whether isolation authenticates and by which route, and (c) if it does not, the accepted gap. Then rewrite S10's sentence to name the one route chosen.

## LOW

### L1. Name the static-image-map mutant in S3
S3 adopts the P7 touch "static-image map via `save_static_frame_data`" (DECISIONS). Its hooks list names no test or mutant for it. That means the End of Project one-to-one hooks check (S10/S11 line 103) would find a gap late. Fix: in S3, name it under the `TeeContext` test with the mutant from P7, "side map promotes the latest `get_frame` snapshot". Tee verification on any multi-play beat turns that mutant red.

### L2. The CI-time re-check starts at S3, but S2 already adds `build` tests
Rules line 11 says "From STRATUM 3 on". PLAN §5 P5 says every stratum that adds `build` tests re-checks. S2's tests are pass-1 only and cheap, so the risk is small. Fix: S2 records its CI wall time too. The record costs nothing.

### L3. The sub-journey is told to apply the P5 remedy, but it may not edit `tests/conftest.py`
Sub-journey NORTH-STAR: "CI wall time ≤ 30 min holds after your tests land, else apply PLAN §5 P5's remedy". The remedy is a session-scoped built edge fixture in `conftest.py`, and conftest is on the frozen "Consumes" list. Fix: "else report to the parent with the projection". The parent then applies the remedy in the main stream, or S3 has already applied it.

### L4. S11: do the deletions in the new talk copy, never in the old checkout
"delete `SCRIPT.md` and the other listed files first" does not say where. The old checkout must stay presentable until Minh's cutover call (DECISIONS, §6 stop rule). `render.json` and `__pycache__/` may be untracked, so git cannot restore them. Fix: say "in the copy under `~/manim-presentations/…`".

### L5. The move of extra allow-list roots to S2 is not in DECISIONS
PLAN §3.5: "The probes may add roots … each one cited". S0 moves that discovery to S2. This is a reasonable deviation, but it is not recorded. Fix: add one DECISIONS line.

### L6. S0 says probe scripts are "never in the repo", but it pushes them to `probe/p5` in the public repo
Deleting the branch does not remove public Actions logs, which stay for the retention period. The PLAN keeps probe logs out of the public repo. Fix: note the exception in DECISIONS (it is already partly sanctioned: "Probes needing WebKit run in the repo's probe workflow"), or remove the logs after use with `gh run delete`.

### L7. The flock rationale overstates what it protects
Rules line 13 says the lock exists "so no heavy run overlaps the real-time Qt/browser assertions". Inside one `uv run pytest -n auto`, xdist still runs `qt` tests beside `build` tests. Other agents' jobs also load the host (DEBT: load 159). The PLAN accepts in-run overlap (§3.11 "Oversubscription only slows tests", P5 confirms). Fix: reword to "no two runs of ours overlap". Optionally state that a local Qt timing failure under high external load is re-run, with CI authoritative.

### L8. S6 title-edit test needs a fixture with a `talk.title` card
"title edit → `structure_mismatch` and the rebuild renders only the card beat" needs a chapter card drawn from `talk.title`. That card is in `examples/hello` (S2), not in the edge fixture. Fix: name the hello copy as the test's fixture.

### L9. S10 states supported browsers only for the README
Deliverable 7 says the README *and* AGENT-INSTRUCTIONS state Safari and Chrome, with Firefox unclaimed. Fix: add AGENT-INSTRUCTIONS to that S10 clause.

### L10. S11 does not name the talks-repo `.gitignore`
§3.2/§3.12 require `*/build/` and `__pycache__/` in the talks repo's `.gitignore` before the first push. Otherwise gigabytes of clips go to the private remote. Fix: add it to S11's ordered steps.

## Counts
HIGH 0 · MEDIUM 3 · LOW 10
