# Code review: STRATUM 7, round 1 (commit 8ba9ca6)

Scope: `manim_presentations/audience.py`, `tests/qt/test_audience.py`, the import-linter contract, the `qt` TEST_COST entry. Read against STRATA.md STRATUM 7, PLAN §3.7, DECISIONS (P1, P5, the three STRATUM 7 entries) and probes/P1.md.

Baseline: `tests/qt` 11 passed in 7.2 s. pyright on audience.py: 0 errors. The tree is restored (`git status` clean).

## What I probed

I added scratch tests (deleted after) for the races in the brief. All of them behave correctly today:
- Replay: Play(a), held, then Play(a) again gives `playing pts=0`, then `held pts=0.9667`, 31 frames.
- Previous from At(0): Play(a), held, then Cover(a) gives one presented frame 0 and `NowCovered`.
- Play(a), then Hold(a). Cover(a), then Hold(a). Loop(a), then Hold(a). Each gives one frame 29 and `held`.
- Play(a), then Play(b) mid-play: `playing pts=0`, then `held`, both for b with b's position.
- Hold(a) and Cover(b) back to back, before LoadedMedia: one `NowCovered(b)`, frame 0.
- A missing clip after Cover: `Failed` with the new clip and position.

So same-URL `setSource` does not hang. Qt's same-URL path calls `stop()` and then returns early. None of these paths has a test (see M2, M4).

## Mutation results (24 mutants, `tests/qt`)

Killed (16): no EndOfMedia re-set, Hold seek to frame 28, Hold seek before LoadedMedia, Loop played once, Cover plays, no Fatal check, auto-repeat forwarded, key not consumed, old client kept, Hello `last=None`, no `Closed`, invalid frames kept, pts in ms, no `expect` reset in `report`, `Failed` not sent. Also killed: no `waitForBytesWritten` (the Fatal test catches it).

Survived (8): `last_valid` not reset on a new message (M13), `BufferedMedia` dropped from the Hold trigger (M15), **Play does not reset `setLoops(1)` (M16)**, `place()` a no-op (M18), no `setMinimumSize(0, 0)` (M19), `IgnoreAspectRatio` (M20), old client's `readyRead.disconnect()` removed (M23), title without " — Audience View" (M24).

## Findings

### MEDIUM 1. An exception in any slot is printed, and the Audience keeps running. It exits 0. (audience.py:113-118, 144-150, 160-170, 172-175)
Principle: no fallbacks / failures that look like success.
- I checked this against a real `python -m manim_presentations.audience` process. I sent `{"type":"nope"}\n`. PySide printed the ValidationError, the process stayed alive, and a later `Quit` exited 0.
- Every `assert` in `_status`, `report` and `_error` is therefore a soft guard. So is the `raise AssertionError` in `report`. The Presenter then waits for a `Now` that never comes, and the Audience shows a stale frame.
- A bad line also drops every later line in the same `readAll()` chunk. `_read` raises in the middle of the loop, and `self.buffer` already holds only the tail.
- Under pytest-qt this is invisible: qtbot turns slot exceptions into test failures. So the suite cannot show the production behaviour.
- Fix: in `main`, before `app.exec()`, install `sys.excepthook` to print the traceback, `send(p.Fatal(reason=...))`, and `os._exit(1)`. Test: in the package-copy subprocess style, send a malformed line. Assert that `Fatal` arrives and the exit code is 1.

### MEDIUM 2. A Play after a Loop is untested. Mutant M16 survives. (audience.py:124-126, tests/qt/test_audience.py)
Principle: tests are falsifiable for real paths (hierarchical tests that mimic real use).
- Next from a loop beat to a normal beat is an ordinary talk path. If `setLoops(1)` is removed, a Play after a Loop loops forever and never reports `held`. The suite stays green.
- Fix: add a test that sends Loop(a), waits for `looping`, then sends Play(b). Assert `playing`, then `held` at frame 29, and assert `EndOfMedia`.

### MEDIUM 3. Clips a and b are pixel-identical, so no test can tell which clip is on screen. (tests/qt/test_audience.py:38-51, 59-61)
Principle: exact, not exhaust. The check must look at the thing itself.
- `index_of` decodes only the frame index (gray 8·i). Both clips encode the same frames. A stale frame of the outgoing clip is therefore indistinguishable from the incoming clip's frame.
- `test_hold_shows_only_the_last_frame_paused` plays b and then holds a. Its `[FRAMES - 1]` assertion passes whether frame 29 came from a or b. The same applies to every future switch test.
- Fix: give each clip its own mark, for example blue = 64·clip_id with red = 8·i. Make `index_of` return `(clip, i)`. Assert the clip identity in the Hold, switch and Cover tests.

### MEDIUM 4. Replay, and Previous from At(0) to Before, have no tests. (tests/qt/test_audience.py)
Principle: tests mimic real use cases. Regression guards on load-bearing paths.
- R (Replay) and Previous at At(0) are first-class actions. Both send a message for the clip already loaded. In Qt they take a different path: same-URL `setSource` stops and then returns early, with no new load.
- My probe shows that both paths work today. Nothing guards them against a refactor, for example a no-op skip when `message.clip` equals the current source, or a Qt upgrade.
- Fix: add one test parametrised over (Play, then Play same clip: `playing`, `held` and all frames again) and (Play, then Cover same clip: `NowCovered` and frame 0 paused).

### MEDIUM 5. The Fatal test can hang the suite forever. (tests/qt/test_audience.py:121-126)
Principle: robustness / no arbitrary limits, with a bound stated where one is needed.
- The `while s.connect_ex(name) != 0` loop only exits if the process dies. An Audience that stays alive and never listens spins forever.
- `s.makefile("rb").readline()` blocks without a timeout if no line comes. pytest-timeout is not installed.
- Fix: `s.settimeout(WAIT_MS / 1000)`, and bound the connect loop with a deadline of `time.monotonic() + WAIT_MS / 1000` that fails the test with the reason.

### LOW 6. `send` blocks the GUI thread in `waitForBytesWritten()` on every message. (audience.py:107-111)
Principle: latency / no arbitrary limits.
- The wait matters only when the next line may be the process's last: `Fatal` and `Closed`. The default 30 000 ms is an implicit, unstated timeout.
- If the Presenter stalls and stops reading, playback-side sends (every `Now`) can freeze the Audience's event loop for up to 30 s.
- Fix: call `waitForBytesWritten()` only on the `Fatal` and `Closed` paths, the two callers that need it.

### LOW 7. `handle` sets `expect` after `setSource`. (audience.py:121-136)
Principle: mark, then route.
- Signals that `setSource` emits synchronously see the previous message's `expect`. Examples: `stop()` on the same URL changes status and sends an empty frame.
- I probed this as harmless today. Only `"seek"` acts on a status, and a stale "seek" seeks a source that is about to be replaced.
- Fix: set `self.shown` and `self.expect` before `setSource`. Use the match to set `expect` and loops first, then call `setSource`, then call `play()` or `pause()`.

### LOW 8. `Quit` is routed outside the match. (audience.py:120-123)
Principle: route on the tag in one place.
- Fix: make it a `case p.Quit():` arm of the one exhaustive match. Move `self.shown, self.last_valid = ...` and `setSource` into a helper, or into the four media arms.

### LOW 9. `state` comes from the Audience's expectation, not from observed `playbackState`. (audience.py:147-157)
Principle: no spec drift.
- PLAN §3.7 says `playing` and `held` come from `playbackState`, and `looping` is the observed `PlayingState` with `loops() == Infinite`.
- The code reports `playing` or `looping` on the first valid frame after `play()`, and `held` on EndOfMedia. That is close to an observation: a presented frame is stronger evidence than a state flag. But it differs from the PLAN's wording.
- Fix: keep it, and add a DECISIONS line that `state` is the presented-frame event per message type. Or assert `playbackState()` inside `report`.

### LOW 10. The window properties have no tests. M18, M19, M20 and M24 survive. (audience.py:48-58, 82-92)
Principle: falsifiable tests for spec'd behaviour.
- The title is what Minh picks in Zoom's share list. Letterboxing, minimum size 0 and the 55% placement are §3.7 requirements. None of them is in STRATUM 7's test list, so this is not a spec gap.
- Fix: one test asserting `windowTitle() == "Test talk — Audience View"`, `video.aspectRatioMode() == KeepAspectRatio`, `minimumSize() == QSize(0, 0)`, and `width() == round(0.55 * screen.availableGeometry().width())` under offscreen's single screen.

### LOW 11. The `9 / 16` window aspect has no stated origin. (audience.py:91)
Principle: no arbitrary constants.
- The clips in this project are 3456×2168 (16:10), so a 16:9 window pillarboxes by default.
- Fix: write down why 16:9 was chosen beside it, or derive the height from the first clip's size (`QMediaMetaData.Resolution`). The simpler way is a stated decision.

### LOW 12. `self.client.readyRead.disconnect()` before `abort()` is not load-bearing. M23 survives. (audience.py:96-98)
Principle: minimality.
- `abort()` discards pending data and closes the socket, so the old client cannot emit `readyRead` into `_read` after that.
- Fix: delete the line, or show a case where it matters.

### LOW 13. Resetting `last_valid` per message is guarded only by a swallowed `assert`. M13 survives. (audience.py:123, 153)
Principle: no soft guards.
- Without the reset, a Play whose clip presents no valid frame before EndOfMedia would hold the previous clip's frame and report `held`. With the reset, the `assert` fires, but MEDIUM 1 shows that the assert is swallowed.
- Fix: this resolves with MEDIUM 1. No separate test is needed.

### LOW 14. A `Failed` clip blanks the Audience. (audience.py:172-175)
Principle: robustness on stage.
- After Cover(a) and then Play(missing), the sink frame is invalid, so the shared window goes black. PLAN §3.7 does not say what the audience should see on `Failed`. The Presenter shows red.
- Fix: decide it in DECISIONS (black, or keep the last valid frame). If the choice is to keep the frame, re-set `last_valid` in `_error` from the previous clip, and capture that frame before `setSource` clears it.

HIGH: 0
MEDIUM: 5
LOW: 9
