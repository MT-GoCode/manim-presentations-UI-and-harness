# Code review: STRATUM 7 round 4 and STRATUM 8 round 1 (commit 7271d83)

Scope: STRATUM 7 — `audience.py`, `AUDIENCE_CODE` in `protocol.py`, `tests/qt/test_audience.py` (after 2262e36, 2122550, c48f056). STRATUM 8 — commit 7271d83: `presenter.py`, `present` in `cli.py`, the `deck.py`/`script.py` changes, `tests/qt/test_presenter.py`, `tests/unit/test_show_for.py`, the import-linter contracts. Read against STRATA.md STRATUM 7/8, PLAN §3.6–§3.7 and the STRATUM 7/8 lines in DECISIONS.

Baseline (load average 21–28 on this machine during the whole review): `tests/qt` + `test_show_for.py` — 1 failed, 61 passed (the failure is HIGH 1 below); a rerun of `test_audience.py` passed 26/26. `lint-imports`: 10 contracts kept. pyright on presenter/audience/cli: 0 errors. Every probe ran in a scratch test file, now deleted; the tree is clean (`git status` empty). I started no Audience process that outlives its test (see LOW S8-9 for nine that I did not start).

## Mutation results (STRATUM 8, 8 mutants, full `test_presenter.py` + `test_show_for.py` each)

Killed (2): `_dropped` relaunches after `Fatal` (1 red); adoption ignores the clip (1 red).

Survived (6): Previous plays the beat (`act` always `"play"`), the `message.position == self.position` guard removed from `received`, the Next still shows `first_png`, the log opened `O_APPEND` instead of `O_TRUNC`, the fit floor ignored (`lo = 1`), elapsed always 0. See MEDIUM S8-1, S8-2, S8-3 and LOW S8-7.

## STRATUM 7 (round 4)

### HIGH S7-1. A message for the clip already playing reports a frame of the playback it replaced. (audience.py:149-156, 159-166; DECISIONS line 52)
Principle: exact, not exhaust / no failure that looks like success. The `Now` claims an observation that did not happen.
- Round 3's `Loading` mark waits for the new clip's `LoadedMedia`. For the same clip, Qt emits that `LoadedMedia` during `setSource` (DECISIONS line 50), so line 156 ends `Loading` at once, while the previous playback's in-flight frames still arrive. The first of them is reported.
- The suite already sees it: `test_hold_shows_only_the_last_frame_paused[play-same-mid]` failed in my baseline run. Rerun 48 times in one scratch file: 3 failed, `NowAt(state='held', pts=0.033333 / 0.133333 / 0.166667)` against the required last frame (29/30). So CI goes red at random.
- A broader probe (a Loop or Play of clip a running past frame 10, then Play, Loop, Cover or Hold of the same clip a, 5 switches per test, 32 tests): 4 tests failed. Play-after-Play reported `playing` at pts 0.3667 (frame 11, not 0); Hold-after-Loop and Hold-after-Play reported `held` at pts 0.3667. Cover-same and Loop-same did not fail in this sample.
- Play of the same clip mid-play is Replay (R) during an animation, and Hold of the same clip is a timeline click on the current beat. Both are normal stage actions.
- The tests do not cover the case except by chance: `test_a_switch_from_a_running_loop_reports_only_the_new_clip` switches a→b only, and `play-same-mid` sends its Hold right after the first `playing` report, which is why it fails only sometimes.
- Fix: the same-clip path needs its own end of `Loading`, because `LoadedMedia` is not a new-load signal there. Two candidates, measure before choosing: (a) in `load`, `setSource(QUrl())` before the real `setSource`, so every load, same clip or not, takes the asynchronous `LoadedMedia` path (check that it shows no black frame and keeps `on_failure` semantics); (b) carry the target frame in the mark — `Loading(then, at_ms)` with 0 for Play/Loop/Cover and `duration − 1` for Hold — and leave `Loading` only on the first frame with `startTime ≤ at_ms·1000 < endTime`. Within one clip, a frame's pts is its identity, so (b) checks the frame itself. Test: the scratch probe above as a permanent test — a running Play and a running Loop of clip a, then Play/Hold of clip a, 10 switches each, assert `pts == 0` (Play) and `round(pts·FPS) == FRAMES − 1` (Hold). It must be red on today's code (4 of 32 short runs failed here; 10 switches × 4 cases fail near-surely). Correct DECISIONS line 50/52 in the same change.

STRATUM 7 items from rounds 1–3 (CHORD, `Loading`, `flush`, the status route after `setSource`, `on_failure`) are fixed and I re-raise none.

## STRATUM 8 (round 1)

### MEDIUM S8-1. The green status line names the new beat with the old beat's observation. (presenter.py:384-387, 417-425, 466-477)
Principle: mark, then route; no failure that looks like success.
- `go` changes `self.position` but keeps `self.now`. `refresh_status` prints `beat.slug` of the new Position beside `self.now.state` of the old one.
- Measured (scratch Fake Audience): at Before with `NowCovered`, press ↓; before the Audience reports anything, the status line reads `Audience: title-card covered · beat 1/5 · 0:00`. The Audience never said that. If the Audience hangs (no `Failed`, no `Now`), the line stays green with that claim for the whole beat.
- The `message.position == self.position` guard in `received` is the only thing that keeps a late `Now` of the previous beat out of `self.now`, and no test can see it (mutant removed it: 36/36 green).
- Fix: in `go`, set `self.now = None` (the line then reads "waiting"/"connecting" until the Audience confirms), and print `self.now.position`'s slug, not the Position's, so the line shows only what the Audience reported. Test with the Fake Audience: press ↓, assert the line does not name the new beat until `NowAt` for it is said; then say a `NowAt` for the previous beat and assert it is not shown (kills the guard mutant).

### MEDIUM S8-2. Previous playing the beat again is not caught by any test. (presenter.py:377; tests/qt/test_presenter.py:200-201)
Principle: tests must fail for the defect they claim to cover.
- Mutant `self.go(position, "play")` for every action: 36/36 green. `test_each_press_moves_one_beat_and_the_audience_follows` waits for `held` after ↑, and a Play also ends `held`. On stage the mutant replays the previous beat's animation on every ↑.
- `test_show_for.py` covers `show_for`'s table, not `act`'s choice of `how`.
- Fix: after ↑, assert the first `NowAt` for the target is `held` at the last frame (`round(pts·fps) == frames − 1`), or use the Fake Audience and assert the sent message is `Hold`. Also add Previous to Before (assert `Cover`).

### MEDIUM S8-3. Auto-fit, its 16 pt floor, "beat text overflows" and the elapsed clock have no tests; `font_points` is written and never read. (presenter.py:476, 528-554)
Principle: falsifiable tests; no inert code.
- Mutants `lo = 1` (floor ignored) and `elapsed = 0`: both 36/36 green. The binary search, the floor (a P1-measured constant) and the overflow line are real logic shipped untested. Elapsed time is the field the plan keeps because Minh used it live (§3.7 status line).
- `self.font_points` (line 554) is set only in `fit` and read nowhere (grep over `manim_presentations` and `tests`), so it looks like a test hook that lost its test.
- Fix: a qt test that loads a short beat (assert the editor's point size is above 16 and the document fits the viewport) and a beat padded to overflow (assert size 16, the status text contains "beat text overflows", the editor scrolls). Read the point size from `editor.document().defaultFont()`, and delete `font_points`. For elapsed: press ↓, monkeypatch `time.monotonic` forward 75 s, call `refresh_status`, assert `1:15`.

### MEDIUM S8-4. The stratum's human-verifiable result has no command. (STRATA.md STRATUM 8 "human-verifiable results")
Principle: results reproducible from the fewest commands; strata rule — every stratum ends on a visible result.
- The stratum promises "an offscreen `QWidget.grab()` PNG of the Presenter at Mixing-Deluxe scale under `/tmp`, viewed in review". No code in the repo calls `grab` (grep over `manim_presentations`, `tests`), and no such PNG or STRATUM-8 blueprint is in the journey folder. I could not view it.
- Fix: a qt test (or one function in the suite's one entry point) that opens the Presenter offscreen on a deck with Mixing-Deluxe's beat count and resolution, `window.resize(…)`, and writes `window.grab()` to `/tmp/mpres-presenter-<hash>.png`, printing the path; then view it in the next round.

### MEDIUM S8-5. `Link` encodes "what this connection told us" as five booleans and an optional, routed by an if-ladder. (presenter.py:98-104, 159-199)
Principle: make illegal states unrepresentable; mark, then route.
- `hello`, `fatal`, `closed`, `quitting`, `replacing` are kept in sync by hand. `fatal` with `hello`, or `closed` with `replacing`, can be represented; `_dropped` resolves them by the order of its `if` arms, and `launch` must reset three of them (line 130) — forgetting one is a silent misroute.
- Fix: one tagged value, e.g. `self.told: Told` with `Told = NotYet | Greeted | FatalSaid(reason) | ClosedSaid | Replacing | Quitting`, set where each message is decoded (and by `quit`), reset to `NotYet` in `launch`; `_dropped` becomes one `match self.told`. Same behaviour, the existing cause tests unchanged.

### MEDIUM S8-6. `CHORD` is defined twice, in `audience.py:29` and `presenter.py:54`, with the same comment. (Single source of truth)
- The rule "a chord is never navigation" belongs to the one key map, which `protocol.py` already owns for the Presenter, the Audience and the exported player. The Presenter may not import `audience` (contract), so the copy is forced by placement, not by design.
- Fix: move `CHORD` beside `KEYS` in `protocol.py` as the Qt modifier names (`("Control", "Alt", "Meta")`, keeping `protocol` free of PySide) or as the Qt flags if `protocol` may import `QtCore`; both views read it. `AUDIENCE_CODE` changes with it, which is correct.

### LOW S8-7. The Now/Next stills, the Next label and the audience log truncation are untested; the Next label is never reset at Before. (presenter.py:399-410, 125)
- Mutants Next still = `first_png` and log `O_APPEND`: both green. At Before, line 403-405 leaves `next_label` as last set (stale "Next: end of talk" in a one-beat deck).
- Fix: assert `now_still.source`/`next_still.source` against the beat PNGs (`QPixmap(path).toImage() == still.source.toImage()`) at Before, at a middle beat and at the last beat; set the label in the Before arm too. Truncation: write junk to `audience_log`, open, assert the junk is gone.

### LOW S8-8. `--from` takes effect only at the first `Hello`. (presenter.py:269, 432-437)
- Until the Audience says `Hello` (~1 s, or never after a `Fatal`), the Presenter shows Before: the Now still, the editor (which autosaves) and the keys act on beat 0. Measured: `open_(talk, before("build-up"))` → `window.position == Before()`.
- Fix: `self.position = start or Before()` in `__init__`; on `Hello`, `--from` still wins (send `show_for(position, "show")` and skip adoption once).

### LOW S8-9. Reaping on disconnect can miss the exiting Audience; nine orphan Audiences from `work-s8` are running now.
- `_dropped` reaps only if `waitpid(WNOHANG)` already reports the exit (line 184); otherwise `launch` overwrites `self.pid` and the old process is never reaped. On macOS a process closes its fds before it becomes a zombie, so a fast disconnect read can lose the race. My one probe did not hit it.
- Observed: `pgrep -f manim_presentations.audience` shows nine Audiences from `work-s8/.venv`, parent 1, started 23:30–23:41 (before this review), each listening on a `$TMPDIR/mpres-*` socket. They are not mine and I left them; the implementer should kill them and check which test or manual run leaks them.
- Fix: in `launch`, if `self.pid` is still set, `waitpid(self.pid, 0)` (the old Audience has dropped its socket, so it is exiting); the plan's "reap before any relaunch" then holds exactly.

### LOW S8-10. Any red or amber hides the clock and the Audience state. (presenter.py:460-479)
- `refresh_status` shows red, else amber, else green. A long beat's "beat text overflows" (amber) or an unacknowledged "re-share" (red) removes the elapsed time and the `Audience: … held` field for as long as it lasts. §3.7 does not say the fields are exclusive.
- Fix: keep the green fields always and prefix the worst problem: `<red/amber text> · Audience: … · beat i/n · m:ss`, coloured by the worst source.

### LOW S8-11. A deleted `script.md` is silently ignored. (presenter.py:504-507)
- `FileNotFoundError` returns without a status change. That is right between an editor's unlink and rename, but a real deletion leaves the line green while every save then fails only on the next keystroke.
- Fix: on `FileNotFoundError`, set `red["structure"] = "script.md is missing"`; the next event that reads the file clears it.

## Count

STRATUM 7 (round 4): HIGH 1, MEDIUM 0, LOW 0.
STRATUM 8 (round 1): HIGH 0, MEDIUM 6, LOW 5.
