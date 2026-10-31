# Code review: STRATUM 8 round 4, STRATUM 9 round 3 (at f3e428e)

Scope: `git diff 9a3763a f3e428e`, and the code it touches in `presenter.py`: the code check in `Link._read`, `build_changed`/`open_failed_with`, `report_errors` and `present`. I also read the new tests. I re-raise no decided item.

Baseline: `tests/qt` 71 passed (28 s). `tests/e2e/test_present.py` 15 passed (40 s). `git status` is clean after the run. The final `pkill` matched processes. These were Audience processes that the mutant runs left behind (most likely from `fatal_no_guard`, whose failing test leaves a relaunch loop). No unmutated run leaked a process.

## Round 3 fixes: verified

| Finding | Fix | Mutant | Result |
|---|---|---|---|
| S8-1 launched Audience of other code relaunched without end | `told = FatalSaid(...)` when `self.pid is not None` | always `"replace"` | killed by `test_an_audience_it_launched_with_other_code…` |
| S8-1 (guard) | `_read` ignores lines once `told` is a `FatalSaid` | guard removed | killed by the same test: `Closed` turns the drop into "click to reopen" |
| S8-2 hot-swap thread dies silently | `except Exception` | the old three-type `except` | killed by `test_a_build_that_cannot_be_opened…` |
| S8-2 `opening` reset | `open_failed_with` | no `opening = False` | killed by the same test |
| S8-3 excepthook untested | `report_errors` extracted, qt test | no `red["error"]` | killed by `test_an_exception_in_a_slot_is_shown_red` |
| S9-1 startup signal untested | e2e that holds `.clips.lock` | `if stop:` block deleted | killed by `test_a_sigterm_during_startup…`: it fails at the 20 s `proc.wait` and does not hang |
| S9-2 close before `exec` | every close is queued with `QTimer.singleShot(0, …)` | — | correct by reading (see below) |
| S9-3 "removed" red kept | test commits one more build | `red.pop("removed")` deleted | killed by `test_a_rebuild_without_the_current_beat…` |

Ordering in `present`, checked by reading:
- A signal before `route_signals` gets the default action, and the process ends before anything exists.
- A signal during `open_presenter` (blocked in `flock`, which PEP 475 retries after the handler) appends to `stop`. `if stop:` then queues the close.
- A signal between `windows.append` and `if stop:` queues two closes. The second `closeEvent` repeats `Link.close`. If the socket is still connected, that sends Quit again (harmless). If the socket is gone, it SIGTERMs and reaps the exiting launched Audience. `lock_fd` is guarded. So the double close is harmless.
- A signal after `if stop:` sees `windows` and queues one close. Every close now runs inside the loop, so `lastWindowClosed` always ends `exec`. The r3 S9-2 gap is closed.

Launched vs adopted, checked across relaunches: `pid` is `None` only for an Audience adopted by `connect_live`. `pid` is also `None` after `_try_connect` sees an exit (then no socket exists) and after `close` (then `told` is `"quit"`). An adopted Audience of other code gets `replace`. Its relaunch is a launched Audience. If that one also differs (the disk changed as well), it gets `FatalSaid` and nothing launches again. The loop is bounded on every path.

## STRATUM 8 (round 4)

### LOW S8-1. The `Told` contract and the `_read` guard comment are now stale. (presenter.py:116-117, 207, 211-216)
- Principle: no stale parts, and mark then route (a mark says where it came from).
- Evidence: the `Told` comment says it is "what this connection has told the Presenter", and that `"quit"` and `"replace"` are "the Presenter's own Quit". The fix adds a third own-Quit case and encodes it as `FatalSaid`, a variant named for something the Audience said. The guard comment at :207 says "after our own Quit". The guard now also covers an Audience's own `Fatal`, which is not our Quit. Behavior is correct: an Audience sends `Fatal` and then exits, so ignoring what follows changes nothing.
- Fix: change the comments to state the property. For example, at :116: "`quit`, `replace`, and a `FatalSaid` set at the code check are the Presenter's own Quit". At :207: "once the end is decided (our Quit, or the Audience's Fatal), nothing more on this connection changes it". Or rename `FatalSaid` to a name that does not claim the Audience as its source (for example `Failed(reason)`).

### LOW S8-2. The new qt test writes `Link.pid` to stay safe at teardown. (tests/qt/test_presenter.py:517-521)
- Principle: decoupling (a test must not change internal state of the unit under test).
- Evidence: the test reaps the Audience with `os.waitpid` and then sets `window.link.pid = None`. Without that line, teardown's `Link.close` would SIGTERM a pid that is already reaped and could be reused. The Link holds the quit Audience as a zombie until `close`. That design is correct in production, and the existing test at :337 uses the same pattern.
- Fix: check "it quit" without reaping, so `Link.close` still owns the reap. For example, poll `os.kill(pid, 0)` together with the zombie state from `ps -o stat= -p pid`. Or reap in `_dropped` for the drop routes that never relaunch (`FatalSaid`, `"nothing"`, `"closed"`). The test can then assert `window.link.pid is None` instead of setting it.

## STRATUM 9 (round 3)

### LOW S9-1. Nothing checks that `present` installs `report_errors`. (presenter.py:791)
- Principle: tests must be falsifiable.
- Mutant: `report_errors(windows[0])` deleted from `present`. `tests/qt` + `tests/e2e/test_present.py`: 86/86 passed. The qt test installs the hook itself, so it proves `failed` works, but it does not prove that the Presenter uses it.
- Fix: install the hook where the window is made, so the qt test's `open_` gets it through the real path. For example, call `report_errors(window)` at the end of `open_presenter`. Then make the qt test drop its own `report_errors` call. Or keep it as is and record the one untested wiring line in DECISIONS. This is LOW because the call is one line, next to code that is tested.

### LOW S9-2. The SIGTERM test's wait for `present: opening` has no bound. (tests/e2e/test_present.py:410-412)
- Principle: a test wait that a defect can turn into a hang must be bounded.
- Evidence: `for line in proc.stdout` blocks until the line arrives or until EOF. The test holds `.clips.lock` exclusive, so any regression that drops or renames the print, or blocks before it while still alive, makes the process wait forever and the test hang forever. The lock is released only in the `finally` below the loop. The `proc.wait(LAUNCH_MS/1000)` bound comes only after the loop.
- Fix: read the line with a deadline. For example, use `threading.Timer(LAUNCH_MS / 1000, proc.kill)` around the loop, or `select` on `proc.stdout` against a deadline, and then assert that the line was seen.

## Count

STRATUM 8 (round 4): HIGH 0, MEDIUM 0, LOW 2.
STRATUM 9 (round 3): HIGH 0, MEDIUM 0, LOW 2.
