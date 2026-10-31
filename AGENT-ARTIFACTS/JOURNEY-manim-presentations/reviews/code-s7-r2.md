# Code review: STRATUM 7, round 2 (commit 2262e36)

Scope: `manim_presentations/audience.py`, `protocol.py` (`AUDIENCE_CODE`), `tests/qt/test_audience.py`, the import-linter contract for audience. Read against STRATA.md STRATUM 7, PLAN §3.7 (Audience parts), round 1 and the STRATUM 7 lines in DECISIONS.

Baseline: `tests/qt` is green (16 passed). The tree is restored (`git status` clean). All probes ran with scratch files, which are deleted.

## What I probed

Same-clip pairs (one message, then a second message for the clip already loaded):
- Play(mid-play), then Play. Play(mid-play), then Cover. Play(mid-play), then Loop. Loop, then Play. Hold, then Play. Hold, then Cover. Cover, then Play. All 7 work.
- Loop of the same clip after Play, Cover, Hold or Loop. Then Cover. All 4 work.
- **Hold of the same clip after Play (held), Play (mid-play), Cover, Loop or Hold. All 5 hang.** See HIGH 1.

## Mutation results (12 mutants, `tests/qt`)

Killed (3): `_error` does not restore `on_failure`, `_error` keeps `expect`, the invalid-frame skip removed.

Survived (9):
- `on_failure` overwritten even when `last_valid` is None (LOW 4).
- `expect` set before `setSource` (MEDIUM 2).
- `send` instead of `send_last` in `closeEvent`, in `died`, and on the backend-Fatal path (LOW 5).
- Unmapped keys consumed (LOW 6).
- `AUDIENCE_CODE` hashing `audience.py` alone (MEDIUM 3).
- Hold seeking on `BufferedMedia` as well as `LoadedMedia`. This one is harmless: `LoadedMedia` always comes first. It is not a finding.
- Window aspect 4:3 in place of 16:9. It is a stated decision, so it is not a finding.

## Findings

### HIGH 1. A Hold for the clip already loaded never reports and never seeks. The Presenter waits for a `Now` that never comes. (audience.py:134-136, 140-148, 151-155)
Principle: no failures that look like success / robustness at the edges. This is a regression from the r1 fix.
- With the same URL, `setSource` calls `stop()` and emits `LoadedMedia` synchronously. At that moment `expect` is still None (load sets it after `setSource` returns), so `_status` does nothing. After that only `BufferingMedia` and `BufferedMedia` arrive, and the seek trigger is `LoadedMedia` only.
- Measured trace, Cover(a) then Hold(a): `LoadedMedia expect=None`, then `BufferingMedia seek`, then `BufferedMedia seek`. No `Now`. The picture stays on frame 0. Nothing is sent: no `Now`, no `Failed`, no `Fatal`.
- It fails after every first message: Play (held), Play (mid-play), Cover, Loop and Hold of the same clip. Each probe timed out after 5 s.
- The path is reachable. Clips are content-addressed, so two beats with identical animations share one path. A Previous from At(k) sends Hold(clip of k−1). A Presenter that does not adopt `Hello` re-sends `show_for` for the clip already on screen, and that is a Hold for any At position of a play beat. Next during a Play also sends a Hold of the playing clip if STRATUM 8's `show_for` has that shape.
- Fix (measured): add `self._status(self.player.mediaStatus())` as the last line of `load`. It routes the status the player already has through the one router after the mark is set. With it, all 50 probe and suite tests pass. For Play, Loop and Cover the extra call does nothing, because their expectations act on frames and `EndOfMedia`, and a just-set source is never at `EndOfMedia`.
- Test: parametrise `test_hold_shows_only_the_last_frame_paused` over the first message ∈ {Play held, Play mid-play, Cover, Loop, Hold}, all of clip a, then Hold(a). Assert `held`, pts frame 29, sink `("a", 29)`, and exactly one new message. Today every case is red (mutant check done).

### MEDIUM 2. The DECISIONS reason for setting `expect` after `setSource` has no test. The mutant that sets it first survives. (audience.py:145-148, DECISIONS line 46)
Principle: tests are falsifiable. A decision that is measured must also be guarded.
- DECISIONS says that a Hold marked first seeked the old clip and reported its new frame 0 as held. I applied that mutant (`self.expect = expect` before `setSource`) and ran the suite 4 times. It stayed green each time, including `test_hold_shows_only_the_last_frame_paused`.
- So either the measured race happens only on a path no test covers, or it does not happen with today's code. In both cases the ordering that causes HIGH 1 is held up by an unguarded claim.
- Fix: write the sequence that showed the race into a test that goes red under the mutant. If you cannot reproduce it, correct the DECISIONS line. HIGH 1's fix is correct with either ordering.

### MEDIUM 3. `AUDIENCE_CODE`'s coverage is not checked. The import-linter contract is a denylist, so a new module slips through. (protocol.py:33-35, pyproject.toml:148-158)
Principle: exact, not exhaust / make illegal states unrepresentable.
- The hash claims to cover everything the Audience runs. The contract only forbids a list of modules that exist today. STRATUM 8 adds `presenter.py`, and later strata add more. None of them is forbidden, so `audience.py` could import one of them and lint stays green while the hash no longer covers what runs.
- The mutant that hashes `audience.py` alone also survives, so nothing checks that `protocol.py` changes the hash.
- Measured today: `python -P -c "import manim_presentations.audience"` loads exactly `{manim_presentations, manim_presentations.audience, manim_presentations.protocol}`.
- Fix: replace the contract with one subprocess test. It imports the audience and asserts that the set of `manim_presentations*` entries in `sys.modules` equals exactly those three, and that it contains no `manim`, `av` or `cairo`. That is an identity check on what loads, not a list of what must not load. In the same test, copy the package, change one byte of `protocol.py`, and assert that `AUDIENCE_CODE` differs, which kills the `audience.py`-only mutant.

### LOW 4. Two clips that fail back to back blank the window once a frame is lost, and a clip that fails mid-play shows the previous clip's frame. (audience.py:143-145, 183-184)
Principle: robustness. The intent in DECISIONS is that the shared window never goes black.
- The `if self.last_valid is not None` guard is what keeps `on_failure` through a second failure. Its mutant survives, because the test has only one failure.
- Also, `on_failure` is the previous clip's frame even when the failing clip had already presented frames. So a decode error mid-clip jumps the audience back to the earlier clip.
- Fix: in `_error`, restore `self.last_valid or self.on_failure`. Add a second `Play(gone2)` to the missing-clip test, and assert that the sink still shows `("b", 0)`.

### LOW 5. `waitForBytesWritten` in `send_last` is not load-bearing in any test. All three `send` mutants survive. (audience.py:110-114, 102, 188, 219)
Principle: minimality, or a falsifiable test.
- The `Fatal` subprocess tests still get their line without the wait. `flush()` already writes into the kernel socket buffer, and `os._exit` does not discard bytes that are already in that buffer.
- The `Closed` test runs in the test process, so it cannot see a process exit at all.
- Fix: delete `send_last` and use `send`, or show a case where it matters (for example, a Presenter that does not read while the Audience exits) and test it.

### LOW 6. Consuming every key press is indistinguishable from consuming only mapped ones. (audience.py:203-205, tests/qt/test_audience.py:285-298)
Principle: falsifiable tests.
- The mutant that returns True for unmapped keys survives. If it shipped, it would swallow shortcuts such as Cmd+W and Cmd+M on the Audience window.
- Fix: in the key test, send an unmapped key (for example `Key_A`) to a widget that records key presses, then assert that it arrives and that no `Key` message is sent.

HIGH: 1
MEDIUM: 2
LOW: 3
