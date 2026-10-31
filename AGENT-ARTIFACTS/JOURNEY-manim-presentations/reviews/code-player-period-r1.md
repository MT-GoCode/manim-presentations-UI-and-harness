# Code review: End of Player Period, round 1 (whole codebase at cb69400, branch join)

Reviewer: FRESH adversarial subagent. I read these files whole: protocol.py, audience.py, presenter.py, export.py, player.html, cli.py, deck.py, headroom.py, script.py, settings.py, the pyproject contracts, conftest.py, tests/presenting.py, tests/e2e/test_present.py, tests/e2e/test_cli_chain.py, tests/export/{frames,frames_plugin,test_file}.py, tests/unit/{test_cli,test_protocol}.py, setup.sh, bin/mpres, ci.yml, README.md and AGENT-INSTRUCTIONS.md. I read the test names of tests/qt and tests/export. I checked them against STRATA, DECISIONS, DEBT, sub-journey-export/DECISIONS and every earlier review. I re-raise no fixed, decided or recorded item.

Baseline:
- mac-work-2: `tests/unit tests/qt tests/e2e/test_present.py`: 220 passed (99 s).
- mac-personal, clone at cb69400: the full suite passed, 359 tests in 8 min 44 s, WebKit included. `lint-imports`: 11 kept, 0 broken.
- CI on cb69400 (run 41188388646) was cancelled by later pushes to `join`, so this commit has no CI result.

Clean-up: every mutant was restored with `git checkout`, and `git status` is clean in both copies. No Audience or browser of mine is still running. The mac-personal clone `/tmp/rvp` is deleted.

## HIGH

### H1. The JOIN carries the export sub-journey's open HIGH, the Chrome raise-before-frame race. (manim_presentations/player.html:88-98)
- Principle: no wrong frame on any transition (export NORTH-STAR). A period does not close with a red CI or an open HIGH.
- Evidence:
  - CI 41184605858 failed on `test_the_jump_list_follows_the_position_so_a_jump_back_works[chrome]` (review e8-r8 H1).
  - sub-journey-export/DECISIONS (the r8 line) still ends with "Under investigation". It is not fixed, not decided and not in DEBT.
  - `git diff 27d2db8 cb69400 -- manim_presentations/player.html` is empty, so the show route that failed is the route merged at the JOIN.
  - Later CI passes (sj/export d92c157) do not prove that the race is gone. r8 states this, and the DECISIONS line agrees.
- Fix: finish the r8 route on `sj/export`. Repeat the real player tests on CI to measure the rate. Then either fix it (for example, a presented-frame signal in Chrome), or record it with Minh's decision. Merge the result into `join` before this period closes.

## MEDIUM

### M1. The JOIN does not hold the sub-journey's last commits. The r8 fixes recorded as done are missing. (manim_presentations/player.html:16, 148; tests/export/test_player.py)
- Principle: single source of truth (one version of the codebase), and tests must be falsifiable.
- Evidence:
  - `git merge-base --is-ancestor d92c157 cb69400` is false. `origin/sj/export` has since gained 6d5b64e (r9) as well.
  - sub-journey DECISIONS says "r8 L1 (jump list reset at Before tested) and L2 (CSS comment) fixed". On `join`, line 16 still has the false comment `/* last: it overrides … */`, and the test is absent.
  - Mutant `jump-not-reset-at-before` (player.html:148 `: ""` changed to `: jump.value`) SURVIVED on mac-personal: tests/export plus the CLI chain, 49 passed.
- Fix: merge the tip of `sj/export` into `join` (and every later sub-journey commit, until the sub-journey ends). Re-run the mutant. Make "the JOIN holds the branch tip" a check at each JOIN, for example `git merge-base --is-ancestor origin/sj/export HEAD` in the JOIN step.

### M2. A hot-swap that clears an earlier red or amber has no test. (presenter.py:559, 565)
- Principle: tests must be falsifiable. A status that stays wrong after the fix is a failure that looks like a known state.
- Mutants (tests/unit + tests/qt + tests/e2e/test_present.py, 220 tests):
  - `structure-red-kept` (the `else: self.red.pop("structure", None)` arm deleted) SURVIVED.
  - `stale-amber-kept` (`self.amber.pop("stale", None)` deleted) SURVIVED.
- Mechanism: the presenter edits a heading and sees red ("run `mpres build`"). The rebuild commits, but the red stays until the next script.md event. That event may never come, because the build writes into build/, not the watched talk folder. The amber "changed since the build" likewise outlives the build that included the change. Today's e2e tests check only that red or amber appears (`test_a_chapter_edited_mid_build_is_adopted_as_stale`, the heading tests), never that a later build clears it.
- Fix: extend `test_a_chapter_edited_mid_build_is_adopted_as_stale`: run one more `mpres build` after the amber, and assert that "changed since the build" is gone. Add a qt or e2e test: change a heading, see red, commit a build of the new script.md, and assert that the status is not red.

### M3. A reconnect to an Audience that covers beat 0 of another build is adopted with no clip check under test. (presenter.py:517)
- Principle: tests must be falsifiable. No wrong frame on the shared screen.
- Mutant `adopt-covered-any-clip` (`if clip == self.clip_of(before)` changed to `if True`) SURVIVED (220 passed). The At branch's twin (`adopt-at-any-clip`) is killed by `test_an_echo_from_another_build_is_not_adopted`, so only the NowAt case is tested.
- Mechanism: the Presenter dies while the Audience covers beat 0. The talk is rebuilt with a new beat 0, and the Presenter is restarted. Under the mutant it adopts the cover and never re-tells it, so the audience sees the old beat 0 while the Presenter's stills show the new one.
- Fix: parametrize `test_an_echo_from_another_build_is_not_adopted` over `NowAt` and `NowCovered(position=Before(), clip=<another clip>)`. Assert that the Presenter sends a `Cover` of this deck's clip.

### M4. A timeline click is not checked to show the beat as last seen. (presenter.py:448)
- Principle: tests must be falsifiable. The behaviour the audience sees must be pinned (§3.7: a click is a jump that shows the beat as last seen. The export player has the same rule and tests it).
- Mutant `timeline-click-plays` (`"show"` changed to `"play"`) SURVIVED (220 passed). Under the mutant, every click on the timeline replays the beat's animation on the shared screen.
- Fix: in `test_a_timeline_click_jumps_and_keeps_the_keys`, wait for the Audience's report and assert `state == "held"` (and never "playing") for a plain beat. Alternatively, record the messages with `sends()` and assert that a `Hold` was sent.

### M5. "`--from` wins once" has no test: a relaunch after a crash would jump back to the `--from` beat. (presenter.py:508-510)
- Principle: tests must be falsifiable. DECISIONS (STRATUM 8 r1) states the rule.
- Mutant `from-not-once` (`self.start = None` deleted) SURVIVED (220 passed). Under the mutant, every Hello re-applies `--from`. A crash relaunch mid-talk, or a "click to reopen", puts the talk back just before the `--from` beat.
- Fix: open with `start=` set. Wait for the first Hello and press Next twice. Then crash the Audience, as `test_a_crashed_audience_is_relaunched_on_the_same_beat` does, and assert that the position after the relaunch is the beat that was reached, not `p.before(start)`.

### M6. Hot-swap after `build/` is removed and made again has no test. (presenter.py:525-530)
- Principle: tests must be falsifiable. A silent failure must not look like success.
- Mutant `build-watch-not-readded` (the `addPath` line deleted) SURVIVED (220 passed). Under the mutant, the folder event for the new `build/` calls `build_changed` once, at a moment when no index has been committed yet. After that, nothing watches `build/`. When the commit lands, nothing reads it, the old deck stays up and the status line stays green. `rm -rf build` before a cold build is exactly what STRATUM 10 ran.
- Fix: an e2e test: present, `shutil.rmtree(build)` with a pin-safe copy of the clips (or move `build/` aside), commit a build into a new `build/`, and assert `settled()`. If the case is out of scope while presenting, delete lines 525-529 and record that removing build/ mid-talk is unsupported. Do not keep an untested branch.

## LOW

### L1. The layers contract does not place `export` (or `audience`), so nothing forbids `export → presenter` or `build → export`. (pyproject.toml:104-118)
- Principle: dependencies point one way.
- Probe (mac-personal): `from manim_presentations import presenter` appended to export.py: 11 kept, 0 broken. `from manim_presentations import export` appended to build.py: 11 kept, 0 broken. The export contract forbids `manim` but not `PySide6` or `manim_presentations.presenter`.
- Fix: put `manim_presentations.export` in the second layer (`build | presenter | export`), and add `PySide6` and `manim_presentations.presenter` to the export contract's forbidden list.

### L2. The chord rule is written twice: `protocol.CHORD` for Qt, and a literal list in player.html. (player.html:164; protocol.py:43)
- Principle: single source of truth. `KEYS` already ships to the page through the manifest. The modifier rule does not.
- Probe (mac-personal): `AltModifier` removed from `CHORD`. The export key test still passed (2 passed), and `grep -c CHORD export.py player.html` gives 0 and 0. The Presenter would now navigate on Alt+↓ while the page ignores it.
- Fix: ship the rule in the manifest. For example, in export.py add `"chord": [DOM_MODIFIER[m] for m in protocol.CHORD]` (with a `DOM_MODIFIER` table beside `DOM_KEY`, so a new Qt name is a KeyError). In the page, use `M.chord.some((m) => e[m])`.

### L3. `Present` waits without a bound for the readiness line. (tests/e2e/test_present.py:301)
- Principle: a test wait that a defect can turn into a hang must be bounded. This is r3's S9-2 again, in the helper that five tests use.
- Probe: mutant with the `present: Audience connected` print deleted. `test_sigterm_closes_presenter_and_audience` was still running at 55 s and was killed by `timeout` (exit 124). An unmutated run takes a few seconds.
- Fix: the same `threading.Timer(LAUNCH_MS / 1000, self.proc.kill)` as `test_a_sigterm_during_startup_closes_everything`, cancelled after the line.

### L4. The `AUDIENCE_CODE` docstring is stale. (protocol.py:36-37)
- It says a Presenter whose value differs "relaunches it". Since s8 r3, only an adopted Audience is relaunched. A launched one is quit and shown red (DECISIONS).
- Fix: "…a Presenter whose own value differs replaces an adopted Audience, and stops red if it launched that Audience (the engine changed on disk)."

### L5. AGENT-INSTRUCTIONS states a false place and a false lasting state. (AGENT-INSTRUCTIONS.md:15)
- "Setup has already built a copy of `examples/hello` in `/tmp`". setup.sh:86-89 builds the copy in `mktemp -d` (on macOS that is `$TMPDIR`, under /var/folders, not /tmp) and then deletes it. An agent that looks for it finds nothing.
- Fix: "Setup checks the engine by building a throwaway copy of `examples/hello`; no `build/` folder appears in the repo."

### L6. setup.sh's banner contradicts the measured duration that the README and AGENT-INSTRUCTIONS state. (setup.sh:6)
- The banner says "the first run takes several minutes". README:5 and AGENT-INSTRUCTIONS:13 say 65 s measured. This is one fact stated three times, two different ways.
- Fix: one wording, the measured one: "the first run takes about a minute or more (TinyTeX download)". Or drop the number from the banner.

### L7. The test helper `commit_from` copies a `stills/` folder that does not exist. (tests/e2e/test_present.py:106)
- Stills live under `clips/` (deck.py:142-145). `"stills"` is a stale part.
- Fix: `rel.parts[0] == "clips"`.

## Checked and sound (not findings)
- The wire: `to_audience` and `to_presenter` decode once at the edge. The code check reads one raw field before the union. `Told` routes every drop. The Audience's `expect` routing and the Presenter's `received` filter agree on (position, clip).
- Export against the build: `require_fresh` and `clips_shared` are held from `Deck.open` to the last encode. The manifest's beats come from the deck, and its chapter titles come from script.md. `require_fresh` makes those two agree. The position model in JS is pinned to `protocol.step` by `tests/position_table.json`.
- The CLI routes every refusal: present exits 2, 3 or 1, export exits 1 or 2. `talk_root` is the one boundary. `bin/mpres` and AGENT-INSTRUCTIONS' literal form match.
- conftest: the `TEST_COST["export"]` entry and the slot formula match DECISIONS.

## Mutation results

mac-work-2: `tests/unit tests/qt tests/e2e/test_present.py`, `-x -n 4`, runner `/tmp/rvp-work/mutants.py` (deleted after the run). 20 mutants, 14 killed, 6 survived.

| mutant | result |
|---|---|
| failed-not-cleared, save-red-no-guard, adopt-at-any-clip, overflow-never-amber, escape-ignored, editor-keys-navigate, end-of-talk-label, audience-chord-forwarded, no-remove-server, presenter-autorepeat, closed-relaunches, removed-goes-before, previous-plays | killed |
| structure-red-kept, stale-amber-kept | **survived** (M2) |
| adopt-covered-any-clip | **survived** (M3) |
| timeline-click-plays | **survived** (M4) |
| from-not-once | **survived** (M5) |
| build-watch-not-readded | **survived** (M6) |
| clock-starts-any (`if action == "next" and …` changed to `if …`) | survived: near-equivalent. Only a `--from` start can make Previous or Replay the first move. Not a finding. |
| no-connected-line (L3 probe) | hung (exit 124 at 55 s) |

mac-personal: `tests/export tests/e2e/test_cli_chain.py`, both engines, under `flock /tmp/mpres-heavy.lock`. 10 mutants, 9 killed: dom-key-no-shift-r, chapter-title-no-fallback, highlight-before-none, window-two, no-loop-attr, no-require-fresh, full-without-notes, fps-fixed, loop-shown-held. Survived: jump-not-reset-at-before (M1).

## Count

HIGH 1, MEDIUM 6, LOW 7.
