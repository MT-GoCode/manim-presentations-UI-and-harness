# Code review: STRATUM 7 round 5, STRATUM 8 round 2, STRATUM 9 round 1 (at 0da3dc8)

Scope: STRATUM 7 — `audience.py`, `protocol.py` (`AUDIENCE_CODE`, `KEYS`, `CHORD`), `tests/qt/test_audience.py`. STRATUM 8 — `presenter.py`, `cli.py present`, `tests/qt/test_presenter.py`, `tests/presenting.py`, `tests/unit/test_show_for.py` (after 8e66ff5, 0da3dc8). STRATUM 9 — 6ed0bfe and after: hot-swap, pins, presenter lock, signals, parent watch, `tests/e2e/test_present.py`, the `after-loop` overlay. Read against STRATA 7–9, PLAN §3.6–§3.7 and §3.11, and DECISIONS lines 43–59. I re-raise no settled item.

Baseline (load average 25–39 throughout): `tests/qt` + `test_show_for.py` 75 passed (37 s). `tests/e2e/test_present.py` 12 passed (41 s). I viewed `test-results/presenter.png`. Every probe ran in a scratch test file, now deleted. `git status` is clean. No Audience I started is still running.

## Mutation results (16 mutants, each against its stratum's test files)

Killed (9): no parent watch; `TEXT_EDIT_KEYS` emptied (↑, ↓ and R no longer type in the editor); adoption ignores the clip; status text drops red/amber; the Audience ignores frame time; no same-clip status reroute; Hold seeks to `duration` instead of `duration − 1`; `on_failure` not restored; no last frame at EndOfMedia.

Survived (6): no SIGHUP handler; no wakeup fd; no lock retry; no `build_changed("")` after a swap; `launch` does not reap; `fit` ignores `idealWidth`. One more is a survivor in substance: with `red.pop("failed")` removed, the only red test was `test_a_deleted_script_turns_red`, which does not touch that path. That test passed 16 of 16 at rest, so this was a load flake (LOW S8-6).

## STRATUM 7 (round 5)

No HIGH or MEDIUM. The r4 fix (`Awaiting(then, at_us)`) holds. Its mutant is killed, but only by `[play-play]`: 1 of the 4 cases.

### LOW S7-1. Only one of the four same-clip cases catches the frame-time mutant. (tests/qt/test_audience.py:237-258)
- Principle: tests must fail for the defect they claim to cover.
- Evidence: mutant `if True:` in place of the `startTime ≤ at < endTime` guard (audience.py:185). Only `[play-play]` went red. `[play-hold]`, `[loop-play]` and `[loop-hold]` stayed green in this run. The suite still catches the defect, but by one case in one run.
- Fix: nothing to change in the code. Note in DECISIONS that the guard's mutant is caught by `[play-play]`. If it ever survives a run, raise `SWITCHES` for that case.

I also probed a superseded failing clip: a Play or Cover of a missing file, then at once a good clip, 12 runs. Qt drops the stale error. The Audience reports only the good clip and never misattributes a `Failed`. No finding.

## STRATUM 8 (round 2)

### HIGH S8-1. A real Audience of other code is not relaunched. Its `Closed` overwrites the `replace` mark. (presenter.py:194-214, 216-231; audience.py:212-214)
- Principle: mark, then route (the mark must be single-origin and must not be overwritten). No failure that looks like success. Tests use the real thing.
- Mechanism: on a hash mismatch, `_read` sets `told = "replace"` and sends `Quit`. The real Audience handles `Quit` with `QApplication.quit()`. In Qt 6 that closes every window first, so `closeEvent` sends `Closed`. Measured with a subprocess Audience and a stdlib socket: after `{"type":"quit"}` the Audience writes `{"type":"closed"}`, then exits 0. The next `_read` sets `told = "closed"`, and `_dropped` routes to "Audience closed — click to reopen". There is no relaunch and no "re-share" line.
- Evidence (scratch qt test): a package copy of the engine with one changed comment in `audience.py`, started live on the talk's socket. Then `open_(talk)`. Result: status `Audience closed — click to reopen · Audience: waiting · beat 0/5`, and `launches == []`. Expected `[1]` and "re-share".
- This is the `git pull` path the hash exists for (§3.7). An older Audience also speaks a different union, so any later line it sends can raise in `to_presenter`.
- Why the suite misses it: `test_an_audience_of_other_code_is_quit_and_relaunched` uses `FakeAudience`, which never sends `Closed` on `Quit`. The real Audience does.
- Fix: route on the mark once it is set. In `_read`, return at the top when `self.told in ("replace", "quit")`: after our own `Quit`, nothing that connection says can change the cause. Test: the scratch test above as a permanent qt test, with a real subprocess Audience from a package copy (the pattern `test_a_fatal_audience…` already uses). Assert `launches == [1]`, "re-share" in the status, and the new Audience reports `Before`. Also make `FakeAudience` answer `Quit` with `Closed`, as the real one does.

### MEDIUM S8-2. `self.now` outlives the Audience and the message it described. A test hides this by clearing it by hand. (presenter.py:216-231, 522-548; tests/qt/test_presenter.py:304)
- Principle: single owner for mutable state; mark, then route. DECISIONS line 59 says the Presenter "shows only what the Audience reported about the current position".
- Three paths keep a stale observation:
  1. **Hot-swap removes the current beat.** `hot_swap` changes `self.position` but not `self.now`. Measured (FakeAudience, `NowAt(the-idea, held)`, then `hot_swap` with the-idea removed): `beat the-idea was removed by the rebuild; now at title-card · Audience: the-idea held · beat 1/4`. The Audience never said that about beat 1.
  2. **Hot-swap changes the current beat's clip.** `now` still holds the old clip's observation while the Audience loads the new one. `received` compares position only, so a late `Now` of the old clip at that position is also accepted.
  3. **A drop.** After a crash relaunch, a `Closed` or a `Fatal`, the status keeps the dead Audience's last state ("keeps-going looping") until a new report arrives, which may never happen.
- `test_a_crashed_audience_is_relaunched_on_the_same_beat` sets `window.now = None` before the SIGKILL (line 304). Without that line, `now_is(...)` is true at once from the stale value, so the test passes whether or not the relaunch resyncs. The test writes the state the code should own.
- Fix: tie the observation to what was sent. `received` accepts a `Now` only if `(position, clip)` equals `held(self.last_sent)`'s. Every assignment of `last_sent` (in `go`, `adopt` and `hot_swap`) sets `now = None` in the same statement, and so does the Link's drop (pass it up with `trouble`, or add a `dropped` callback). Delete line 304 of the test. Add a FakeAudience test for path 1 (assert "waiting" after the swap) and one for path 2 (send a `NowAt` with the old clip after the swap, and assert it is not shown).

### MEDIUM S8-3. Closing the Presenter before a launched Audience connects leaves an orphan Audience. (presenter.py:682-687, 152-166)
- Principle: robustness (system edge cases). §3.7 says intent closes both windows. No stale parts (leaked processes).
- `closeEvent` sends `Quit` only if the socket is connected. A launched Audience takes about 1 s to listen, so in that window `Quit` is dropped. The Audience then comes up with no Presenter. It is `setsid`, so nothing else stops it.
- Evidence (scratch test): `open_presenter(talk)`, then at once `window.close()`, then wait 4 s. Result: `pgrep -f <socket>` shows the launched pid alive (`orphan Audience ['90552'] (launched 90552)`).
- The same window exists in real use. Ctrl-C right after `mpres present` (signals are routed only after `open_presenter` returns, so SIGINT there is a `KeyboardInterrupt`, and SIGTERM is the default kill). It also exists during a crash relaunch, and after a "click to reopen".
- The `open_` fixture SIGKILLs `link.pid` on teardown, so the qt suite can never see this. It is a likely source of the orphan Audiences seen in earlier rounds (r4 LOW S8-9).
- Fix: in `closeEvent`, if `self.link.pid is not None` and the socket is not connected, `os.kill(pid, SIGTERM)` and `waitpid`. Better: give `Link` one `close()` that does Quit-or-kill by its own state, so the Presenter does not inspect the Link. Test: the scratch test above, with no fixture teardown kill.

### MEDIUM S8-4. No test sends `Failed` to the Presenter. The red "could not play" line and its clearing are untested. (presenter.py:475, 477-479)
- Principle: tests must be falsifiable, and every load-bearing path must run.
- `grep Failed tests/qt/test_presenter.py tests/e2e/test_present.py` finds nothing. Mutant: `red.pop("failed")` removed. No test that touches the path went red (see the mutation note). The STRATUM 8 list includes "socket drop red". `Failed` is the only runtime signal that a clip the Audience was told to play is missing.
- Fix: a FakeAudience test. Say `Failed(position=At(title-card), clip=…, reason="x")`. Assert red with "could not play" and the clip name. Then say a `NowAt` for the current position and assert the red line is gone.

### LOW S8-5. `fit` grows the editor text without limit: "That is all." renders one word per line at about 150 pt. (presenter.py:633-659; test-results/presenter.png)
- Principle: spec fidelity (§3.7 "auto-fits so the beat does not scroll, down to a floor"). The interface is the product.
- The search range ends at `viewport.height()` points. A short beat fills the column with three giant lines, and a presenter glancing mid-sentence reads a vertical list, not a phrase. The `idealWidth` clause that 0da3dc8 added is untested (mutant survived). Every test beat is long enough that no single word is wider than the column.
- Fix: this needs Minh's decision on a ceiling. A measured maximum, for example the P1(e) ladder's largest comfortable size, would keep a short beat on one or two lines. Test `idealWidth` with one long unbreakable word in a narrow window (resize to about 300 px): assert `document().idealWidth() <= viewport().width()` after `fit`.

### LOW S8-6. `test_a_deleted_script_turns_red` failed once under load. (tests/qt/test_presenter.py:421-425)
- Evidence: red once in the mutant-8 run (load average about 36, `Failed: ...`). It passed 16 of 16 at rest. Its 5 s wait for FSEvents is the same `WAIT_MS` the other watcher tests use. I did not find the cause.
- Fix: rerun it under load (`-n 16` beside a build) to tell whether FSEvents latency or teardown is the cause, before adding any margin.

### LOW S8-7. `launch`'s reap and the "closed" test's blocking wait are not falsifiable. (presenter.py:153-154; tests/qt/test_presenter.py:322-327)
- Mutant: `launch` without `waitpid`. All 33 passed. A zombie is invisible to every test.
- The mutant "closeEvent without Quit" (STRATA 9's own listed mutant) does not fail `test_closing_the_presenter_quits_the_audience`. It hangs it, because `os.waitpid(pid, 0)` never returns for an Audience that stays up by design. A hang is not a red.
- Fix: in the closing test, poll `waitpid(pid, WNOHANG)` against a deadline (`LAUNCH_MS`), then assert. For the reap: after a crash relaunch, assert `os.waitpid(first, os.WNOHANG)` raises `ChildProcessError` (already reaped).

### LOW S8-8. The Presenter has no excepthook. An exception in a slot is printed and the window goes on half-updated. (presenter.py:747-753)
- Principle: no failure that looks like success. The Audience got this treatment in r1, but the Presenter, the window Minh actually looks at, did not.
- Example: a malformed line in `Link._read` raises in `json.loads`. The rest of that batch is lost, and the status stays green.
- Fix: in `present`, set `sys.excepthook` to print the exception and set `red["error"]` to its one-line form. Do not exit: losing the Presenter mid-talk is worse than a red line.

## STRATUM 9 (round 1)

### MEDIUM S9-1. The SIGHUP handler does what the default action already does, and it overrides `nohup`. (presenter.py:739)
- Principle: absolute minimality; no inert code; tests must fail for the defect they claim to cover.
- CPython leaves SIGHUP at `SIG_DFL`, which terminates the process. The kernel then closes the lock and socket fds, without `Quit`, exactly as the handler's `os._exit(129)` does. Mutant: the line deleted. `test_an_accident_leaves_the_audience_up_and_a_rerun_reconnects` passed both cases.
- The handler also replaces an inherited `SIG_IGN`. So `nohup mpres present …` now dies on hangup, against the caller's explicit request.
- Fix: delete the line and its DECISIONS clause ("SIGHUP … exit with `os._exit`"). The SIGHUP test stays, as a test of the default.

### MEDIUM S9-2. Three S9 mechanisms have no test that can fail: the wakeup fd, the 1 s lock retry, and the re-check after a swap. (presenter.py:731-736, 717-725, 549)
- Principle: falsifiable tests. Every constant comes from a measurement. A claim in DECISIONS needs evidence.
- **Wakeup fd** (DECISIONS line 56: "Python handlers run at once, not on the next timer tick"). Mutant: no `set_wakeup_fd`. The SIGTERM test passed: the 1 s status clock runs the handler within 1 s, well inside `WAIT_MS`.
- **Lock retry** (`LOCK_RETRY_S`). Mutant: no retry. 45/45 passed.
- **`build_changed("")` at the end of `hot_swap`**. Mutant: removed. 12/12 e2e passed. Without it, a build committed while the previous one was opening is never adopted, because the folder event that announced it was dropped by the `opening` guard. The Presenter then sits on an old deck with no sign until the next unrelated change in `build/`.
- Fix:
  - Wakeup fd: assert latency. In-process, `route_signals(window)`, then `os.kill(os.getpid(), SIGTERM)`, `qtbot.waitUntil(lambda: not window.isVisible(), timeout=300)`. The clock period is 1000 ms, so the mutant fails. Restore the handlers after the test.
  - Lock retry: hold `presenter_lock` from a helper thread for 200 ms, call `open_presenter`, and assert it succeeds (mutant: Busy).
  - Re-check: monkeypatch `open_deck` to block on an event. Commit build B, then build C while B is opening, release, and assert `deck.build_id == C` with no further file change.

### LOW S9-3. The e2e rebuild test that removes a beat does not check what the Audience shows. (tests/e2e/test_present.py:152-168)
- It asserts the Presenter's position and red text only. It does not check that the Audience was told `Hold(title-card)` or that it reported it. With S8-2 path 1 present, the status line could still claim the removed beat.
- Fix: add `qtbot.waitUntil(now_is(window, p.At(slug="title-card"), "held"), timeout=WAIT_MS)`.

### LOW S9-4. Signals are routed only after startup, which takes about 1 s. (presenter.py:747-753)
- Between `QApplication()` and `route_signals`, SIGTERM is the default kill and SIGINT raises `KeyboardInterrupt` inside `open_presenter`. Both happen after `launch`, so both leave an orphan Audience (see S8-3).
- Fix: call `route_signals` before `open_presenter`, with the handlers closing whichever window exists (or exiting 130 if none), and let S8-3's Quit-or-kill cover the launched Audience.

The pins and the presenter lock look right. Pins are written under the shared clips lock before the GUI adopts the deck. GC keeps the previous index's clips, so an unswapped deck's clip survives one more build. The lock fd is not inherited by the spawned Audience (PEP 446; the "killed uv" e2e re-presents without exit 3). The `after-loop` overlay is minimal and does its one job.

## Count

STRATUM 7 (round 5): HIGH 0, MEDIUM 0, LOW 1.
STRATUM 8 (round 2): HIGH 1, MEDIUM 3, LOW 4.
STRATUM 9 (round 1): HIGH 0, MEDIUM 2, LOW 2.
