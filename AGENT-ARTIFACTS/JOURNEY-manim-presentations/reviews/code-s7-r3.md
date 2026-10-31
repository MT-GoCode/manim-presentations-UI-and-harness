# Code review: STRATUM 7, round 3 (commit 2122550)

Scope: `manim_presentations/audience.py`, `protocol.py` (`AUDIENCE_CODE`), `tests/qt/test_audience.py`. Read against STRATA.md STRATUM 7, PLAN §3.7 (Audience parts), rounds 1 and 2, and the STRATUM 7 lines in DECISIONS.

Baseline: `tests/qt/test_audience.py` 23 passed in 7 s. pyright on both modules: 0 errors. The tree is restored (`git status` clean). Every probe ran in a scratch test file, which is deleted.

## What I probed

- A switch away from a clip that is still running: Loop(a) running for 100–507 ms, then Cover(b), Play(b), Loop(b) or Hold(b). Also Play(a) mid-play, then Cover(b). I wrapped `view.report` to record the frame each report is made from, decoded with `shows`. 12 delays per case.
- The key forwarder with modifiers: R with Control (Cmd on macOS), Shift and Alt.
- `Qt.Key(0)` and other unknown key codes: PySide returns a numeric name and does not raise. No crash path there.

## Mutation results (6 mutants)

Killed (5): the status route after `setSource` removed (5 red), `flush()` removed (2 red), auto-repeat forwarded (1 red), reports made while the expectation is `seek` (14 red), `on_failure` kept across loads (1 red).

Survived (1): `last_valid` kept only while something is expected. See HIGH 1: the outgoing clip's late frames land in `last_valid`, and no test can see it.

## Findings

### HIGH 1. Next during a loop, or any switch from a clip that is still playing, can report the outgoing clip's frame as the new message's first frame. (audience.py:134-141, 154-159; DECISIONS line 46)
Principle: exact, not exhaust / no failures that look like success. The report claims an observation that did not happen.
- The outgoing clip's frames do not all arrive during `setSource`. Some arrive after `load` returns, when `expect` is already `playing`, `looping` or `covered`. `_presented` then reports that stale frame for the new message.
- Measured, baseline: 10 of 36 runs of a switch from a running Loop(a) to Cover(b), Play(b) or Loop(b) report a frame of clip a. Examples from the recorded reports: `('covered', ('a', 16), 'Cover')`, `('playing', ('a', 14), 'Play')`, `('looping', ('a', 4), 'Loop')`. A Play(a) mid-play, then Cover(b), fails the same way. Hold(b) never fails, because its frames route only after `LoadedMedia`.
- What the Presenter sees: `NowAt(state="playing", pts=0.47)` for a clip that starts at 0, or `NowCovered` sent before frame 0 of b is on screen. Next during a loop is D7, the normal stage path. The STRATUM's claim that `Now` carries observations of the player does not hold on this path.
- DECISIONS line 46 says that `setSource` emits the outgoing frames synchronously, and that the mark set after `setSource` therefore makes them inert. The probe shows the claim is incomplete: the outgoing frames also arrive after `setSource` returns.
- The tests cannot see it. `test_a_play_after_a_loop_plays_once_and_holds` checks only `state == "playing"`. No test switches away from a clip that is still running and checks the first report.
- Fix (measured): arm Play, Loop and Cover the way Hold is armed already. Frames route only after the new source's `LoadedMedia`. In `load`, keep the target state aside and set `expect = "load"` (Hold keeps `"seek"`). In `_status`, add the arm `expect == "load" and status == LoadedMedia: expect = <target state>`. The existing `self._status(self.player.mediaStatus())` line covers the same-clip path. I applied this fix as a scratch diff (5 changed lines): 83 of 83 passed, twice, including the 60 probe cases and the full suite. Under the fix, set `last_valid` only once the frame is routed, so that `last_valid` holds only the new clip's frames. That kills the surviving mutant. Make the fix as one tagged value, not two fields kept in sync. For example, the Expect union gets a `("load", target)` variant, or the target travels in `self.shown`'s type.
- Test: in one test, switch from a running Loop of one clip to another clip at least 10 times, and wait for the loop to pass frame 10 (in the `presented` list) before each switch. Assert `NowAt.pts == 0` for Play and Loop each time. For Cover, the message has no pts, so assert from the presented frames: no frame of the outgoing clip comes after the first `("b", 0)`, and the sink shows `("b", 0)` when `NowCovered` arrives. Check that the test is red on today's code (the probe failed about 1 run in 4, so 10 switches in one test fail with near-certainty). Correct DECISIONS line 46 in the same change.

### LOW 2. A key with a modifier is forwarded as its bare action. Cmd+R on the Audience is a Replay. (audience.py:193-201)
Principle: exact, not exhaust. The filter matches the key code alone, which is a property, not the whole key press.
- Measured: R with Control (Cmd), Shift or Alt each sends `Key(action="replay")`. So does Cmd+↓ and so on.
- The r2 docstring of the unmapped-key test ("Cmd+W and the like still reach the window") is true only because W has no mapping.
- Fix: forward only when `event.modifiers()` has no Control, Alt or Meta bit (`KeypadModifier` must stay allowed, because arrow keys carry it on macOS). Pass everything else through. Write the same rule down once for STRATUM 8's Presenter filter. Test: add Cmd+R to `test_unmapped_keys_pass_through_the_forwarder` and assert that it reaches the recorder and sends no `Key`.

HIGH: 1
MEDIUM: 0
LOW: 1
