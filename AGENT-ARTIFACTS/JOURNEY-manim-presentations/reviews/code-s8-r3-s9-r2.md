# Code review: STRATUM 8 round 3, STRATUM 9 round 2 (at 9a3763a)

Scope: `presenter.py`, `cli.py present`, `tests/qt/test_presenter.py`, `tests/presenting.py`, `tests/unit/test_show_for.py`, `tests/e2e/test_present.py`. Read against STRATA 8–9, PLAN §3.7 and §3.11, the STRATA 7–9 lines of DECISIONS, and DEBT's hot-swap re-check entry. I re-raise no fixed, decided or recorded item.

Baseline: `tests/qt` + `test_show_for.py` 81 passed (27 s). `tests/e2e/test_present.py` 13 passed (45 s). Load average was 10–32. Every probe ran in a scratch test file, now deleted. `git status` is clean. The final `pkill` found nothing of mine still running.

## Round 2 fixes: verified

All the fixes hold, and each has a mutant that the suite kills:
- S8-1 (older Audience's `Closed`): the early return in `_read` is killed by `test_an_older_audience…`, a real subprocess Audience, and by the fake one, which now answers Quit with Closed.
- S8-2 (stale observation): `tell` clears `now` (killed by the status-line test). `received` checks position and clip (killed by `test_a_report_about_another_clip…`). `audience_lost` clears `now` (killed by the crash test, which no longer clears `now` by hand).
- S8-3 (orphan before connect): `Link.close` SIGTERMs and reaps (killed by `test_closing_before_the_audience_listens…`).
- S8-4 (Failed): killed by `test_a_failed_clip_is_red…`.
- S8-5 (`idealWidth`): killed by `test_a_word_wider…`.
- S8-7: the closing test now polls against a deadline, and "close without Quit" fails red instead of hanging. The reap in `launch` is killed by the crash test's `ChildProcessError` check.
- S9-1 (no SIGHUP handler): done.
- S9-2: the lock retry is killed by `test_a_presenter_lock_held_briefly…`. The re-check after a swap is recorded in DEBT.
- S9-3: the e2e removal test now waits for the Audience's `title-card held`.

## Mutation results (17 mutants)

Killed (13): `_read` with no early return after our own Quit; `tell` keeps `now`; `received` compares position only; `audience_lost` keeps `now`; `close` with no kill; `close` with no Quit; lock with no retry; `fit` with no `idealWidth` check; `launch` with no reap; `Failed` not shown red; a raw compare in `hot_swap` (e2e); no parent watch (e2e); `adopt` ignores `--from`.

Survived (4): `set_red` does not reset `opening`; startup signals in `early` ignored; the excepthook sets no red; `hot_swap` keeps an old "removed" red. Each one is a finding below.

## STRATUM 8 (round 3)

### HIGH S8-1. Once the engine on disk differs from the running Presenter's code, every Audience it launches is quit and relaunched, without end. (presenter.py:209-213, 232-235; protocol.py:33-35)
- Principle: no failure that looks like success, and robustness to system edge cases. The plan states the rule itself in §3.7: a deterministic failure "would otherwise spawn windows without end".
- Mechanism: `AUDIENCE_CODE` is the hash of `audience.py` and `protocol.py`, read once when the Presenter imports. A launched Audience hashes the files on disk when it starts. Suppose the files change while a Presenter runs (a `git pull` or `./setup.sh` mid-talk, or an agent editing the engine). Then every Audience this Presenter launches says a different `protocol`. `_read` sets `told = "replace"` and sends Quit, and `_dropped` launches again. The next Audience hashes the same files, so the loop never ends.
- Any later launch starts the loop: a crash relaunch, a "click to reopen", or the first launch itself.
- Evidence (scratch qt test, clean source): a package copy of the engine with one comment added to `audience.py`, put on `PYTHONPATH` for the launched Audience, then `open_(talk)` and a 10 s wait. Result: `launches` was 38. The status read "Audience relaunched — re-share…". A first run that monkeypatched `p.AUDIENCE_CODE` gave 58 launches in 12 s. On a real screen, an Audience window opens and closes several times a second on the shared screen, until the Presenter is killed.
- Why the suite misses it: both mismatch tests start with an Audience that the Presenter did not launch. No test launches an Audience whose code differs from the Presenter's.
- Fix: route on what the Link already knows: did this Presenter launch the Audience? `self.pid is not None` at the Hello means this Presenter launched it.
  - An adopted Audience of other code gets `replace`, as now.
  - A launched Audience of other code is a deterministic failure. Mark it as `FatalSaid("the engine changed on disk since present started — restart mpres present")`, send Quit, and do not relaunch.
- Test: the scratch test above, made permanent. Assert `launches == [1]`, assert red with "restart", and assert that no Audience process is left.

### MEDIUM S8-2. A failure of the hot-swap thread other than the three caught types disables hot-swap for the rest of the talk, with no sign. Even the caught path has no test. (presenter.py:529-536, 320, 566-569)
- Principle: no failure that looks like success. Tests must be falsifiable. A name must say what the code does.
- Mechanism: `run` catches only `IncompatibleBuild`, `ValueError` and `OSError`.
  - Any other exception ends the thread. It goes to `threading.excepthook`, not to the `sys.excepthook` that `present` installs. `opened` and `open_failed` are never emitted, so `opening` stays `True`. From then on `build_changed` returns at once for every build.
  - Evidence (scratch qt test): `open_deck` raises `KeyError` once and then works. After a new `build_id`: `opening` was True, and the status was green ("Audience: waiting · beat 0/5"). After a second `build_id`: the deck was still the old one, and `open_deck` had been called once only.
  - The presenter keeps editing, runs `mpres build`, and sees the old deck all talk long, with a green line.
- Second problem: the caught path relies on `set_red` resetting `opening`. The mutant that removes this reset survived the qt and e2e suites. `set_red` has one caller, and its name hides that it is the open-failure handler.
- Fix:
  1. In `run`, use `except Exception as e: self.open_failed.emit(f"{type(e).__name__}: {e}")`. The failure then stays exact and red, and is never silent.
  2. Rename `set_red` to `open_failed_with(text)` (or inline it as the slot), so that the reset of `opening` is part of its stated job.
  3. Test: monkeypatch `open_deck` to raise once (a `KeyError`), then work. Commit a build and assert red with "could not be read". Commit another build and assert `window.deck.build_id` equals the new one.

### LOW S8-3. The Presenter's excepthook has no test. (presenter.py:774-781)
- Mutant: no `red["error"]`. It survived. This is r2's S8-8 fix, and it is not falsifiable now.
- Fix: one in-process test. Install the hook from `present`'s body (extract `failed` beside `route_signals`, so a test can install it on an `open_` window). Call `sys.excepthook(*sys.exc_info())` inside an `except`, or make a slot raise through `QTimer.singleShot`. Assert red with the exception's type name.

## STRATUM 9 (round 2)

### MEDIUM S9-1. Intent signals during startup have no test. (presenter.py:764-785)
- Principle: tests must be falsifiable. DECISIONS (STRATA 8–9 line) claims: "Intent signals arriving during startup are kept and acted on once the window exists."
- Mutant: the `if early:` block deleted. 52/52 qt and e2e passed. Without it, a Ctrl-C during the ~1 s start is swallowed: the Presenter comes up and stays up after the user asked it to stop.
- Fix: an e2e through `bin/mpres`. Make the start slow in a way the test controls, and do not guess a sleep. For example, hold `build/.clips.lock` exclusive in the test, so that `open_deck` blocks inside `open_presenter`. Then send SIGTERM, release the lock, and assert that the process exits 0 within `WAIT_MS` and that `audiences(talk) == []`.

### LOW S9-2. An intent signal between `windows.append` and `app.exec()` closes the window before the loop runs, and `exec` then never returns. (presenter.py:782-786)
- Qt 6 `quit()` (from `lastWindowClosed`) does nothing while no event loop runs. If the handler runs in that gap, `windows[0].close()` sends Quit to the Audience. Then `app.exec()` starts with no window and waits forever, holding the presenter lock, so the next `present` exits 3.
- The gap is a few bytecodes, so this is rare. I did not reproduce it.
- Fix: have `intent` always append to `early`, and check it once inside the loop with `QTimer.singleShot(0, …)` after `exec` starts. Or call `app.quit` through a queued call (`QTimer.singleShot(0, windows[0].close)`), which runs only when the loop runs.

### LOW S9-3. No test checks that a later rebuild clears the "removed" red. (presenter.py:545)
- Mutant: `red.pop("removed")` deleted. 13/13 e2e passed. §3.7 lists "a beat removed by a rebuild" as red, so the red stays until the next build, and only that build may clear it.
- Fix: in `test_a_rebuild_without_the_current_beat…`, commit one more build (any `rebuilt` change) after the assertions. Assert that "was removed" is gone and that the status is not red.

The pins, the presenter lock and its retry, the parent watch, `Link.close`'s Quit-or-kill, signal routing for SIGTERM, and the accident paths (SIGHUP default, SIGKILL to Python, SIGKILL to uv) look right. Each has a mutant killed by an e2e or qt test, or was verified in round 2. `show_for`/`held` is exhaustive over Position × kind × how.

## Count

STRATUM 8 (round 3): HIGH 1, MEDIUM 1, LOW 1.
STRATUM 9 (round 2): HIGH 0, MEDIUM 1, LOW 2.
