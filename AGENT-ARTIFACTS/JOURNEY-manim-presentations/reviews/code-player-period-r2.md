# Code review: End of Player Period, round 2 (join at 1136c2f)

Reviewer: FRESH adversarial subagent. Scope:
- Did round 1's fixes work? The commits are `cb69400..1136c2f`.
- A pass over the whole codebase for HIGH or MEDIUM findings that round 1 missed. This includes the export code merged after round 1.

I read these files in full: presenter.py, export.py, player.html, tests/presenting.py, tests/e2e/test_present.py, and the new qt tests. I also read the whole diff `cb69400..1136c2f`. I checked them against STRATA, DECISIONS, DEBT, sub-journey-export DECISIONS and DEBT, and every earlier review. I re-raise nothing that is fixed, decided, or recorded as debt.

Baseline:
- mac-work-2: `tests/unit tests/qt tests/e2e/test_present.py`, `-n 4`: 226 passed (63 s).
- mac-personal, clone at 1136c2f: `lint-imports`: 11 kept, 0 broken. Full suite (`-n auto`): 367 passed in 9 min 2 s, WebKit included.
- CI on 1136c2f (run 41191602968): success.

## Round 1 resolutions

| r1 | status | evidence |
|---|---|---|
| H1 | recorded, as stated | DECISIONS (End of Player Period R1) and sub-journey DEBT. Not re-raised. |
| M1 | resolved | `git merge-base --is-ancestor origin/sj/export 1136c2f` is true. The test `test_the_jump_list_clears_at_before…` is present. |
| M2 | resolved | Mutants `structure-red-kept` and `stale-amber-kept` are both killed by `test_a_clean_rebuild_clears_the_stale_amber_and_the_headings_red`. |
| M3 | resolved | Mutant `adopt-covered-any-clip` is killed by `test_a_reconnect_to_another_builds_cover_is_not_adopted`. |
| M4 | resolved | Mutant `timeline-click-plays` is killed by `test_a_timeline_click_shows_the_beat_as_last_seen`. |
| M5 | resolved, as stated | The once-guard was equivalent, and I agree with that reasoning. Every later Hello comes from a `launch()`, either `_dropped` ("replace" or "hello") or `_reopen`. A launched Audience has no `last`, so `adopt` shows the current Position on either branch. The `from_given` branch is still load-bearing: mutant `from-ignored-on-reconnect` (`if False:`) is killed by `test_from_wins_over_what_the_audience_shows`. |
| M6 | **not resolved**, see M1 below | The new test passes, but the branch it tests can never run. |
| L1 | half resolved, see L2 | export → presenter is now forbidden. Probe: the import added, 10 kept, 1 broken. export → PySide6 still passes, 11 kept. |
| L2 | resolved | The manifest ships `chord` from `protocol.CHORD` through `DOM_MODIFIER`. A new Qt name gives a KeyError. |
| L3 | half resolved, see L1 | The bound covers a Presenter whose event loop runs. It does not cover one that blocks before its loop. |
| L4–L7 | resolved | Docstring, AGENT-INSTRUCTIONS, setup banner and `commit_from` match the code. |
| 08e49ff | sound | Mutant `missing-script-not-red` is killed by `test_moving_while_the_script_is_missing_shows_red`. `script_changed` clears the red when the file comes back. |

## HIGH

None.

## MEDIUM

### M1. The "build/ removed and made again" branch is inert on macOS, and its new test passes without it. (manim_presentations/presenter.py:537-542; tests/e2e/test_present.py:256)
- Principle: no stale parts (inert code goes). Tests must be falsifiable and must observe the line they claim. Round 1's M6 named this exact alternative: "Do not keep an untested branch."
- Evidence:
  - Mutant `build-watch-not-readded` (the `addPath` line deleted): SURVIVED, 226 passed.
  - Mutant `no-immediate-build-check` (the `build_changed(str(build))` call in `folder_changed` replaced by `pass`): SURVIVED, 226 passed.
  - Mechanism, from probe `watchprobe.py` (a bare QFileSystemWatcher on `build/`, 3 of 3 runs): after `shutil.rmtree(build)`, `directories()` still lists `build/`. After `mkdir` and a file write, `directoryChanged` fires again. On macOS's FSEvents backend a watch on a path survives the removal of the folder. So `str(build) not in self.build_watcher.directories()` is never true, and both lines of the branch never run. The new test is adopted through the original watch.
  - This is the same backend fact that DECISIONS (STRATUM 8) records for the talk-folder watch.
- Fix: delete lines 539-541, so `folder_changed` is `self.script_changed(path)` and can be removed. Connect `directoryChanged` straight to `script_changed`. Add the measurement to DECISIONS: "The FSEvents watch on build/ survives the folder's removal and fires again when the folder is made again (probe: 3/3)." Keep `test_a_build_folder_removed_and_made_again_is_still_watched` as the behaviour pin. Its name and setup already state the behaviour, not the line.

## LOW

### L1. Present's startup bound does not cover a Presenter that blocks before its event loop. (tests/e2e/test_present.py:328-332)
- Principle: a test wait that a defect can turn into a hang must be bounded. This is r1 L3, still half open.
- Probe `l3probe.sh`: mutant with `time.sleep(10**6)` before `open_presenter` in `present`. `test_sigterm_closes_presenter_and_audience` ran until the outer `timeout 75` (exit 124), against a 20 s bound.
- Mechanism: the timer kills `uv` only. The orphaned Python Presenter holds the stdout pipe open, so `any(… for line in self.proc.stdout)` keeps blocking. Its parent-death watch is a QTimer, and it never runs before `app.exec()`. A startup stuck on a held `.clips.lock` is the realistic case of this defect.
- Fix: start the process with `start_new_session=True` and kill its group: `threading.Timer(LAUNCH_MS / 1000, os.killpg, (self.proc.pid, signal.SIGKILL))`. Do the same in `test_a_sigterm_during_startup_closes_everything`. The `presented` teardown already kills `run.python`, so it needs no change.

### L2. The export contract still allows PySide6. (pyproject.toml:160)
- Principle: dependencies point one way. Round 1's L1 fix named both halves. The layer half is done.
- Probe (mac-personal): `import PySide6` appended to export.py: 11 kept, 0 broken.
- Fix: add `PySide6` to the export contract's forbidden list, beside `manim`.

### L3. Alt as a chord has no test at any level. (manim_presentations/protocol.py:44; tests/qt/test_presenter.py:109; tests/qt/test_audience.py:402; tests/export/test_player.py:170)
- Principle: tests must be falsifiable. With L2 of round 1 fixed, `CHORD` is the one source for three consumers, but only Control/Cmd (and the DOM's metaKey and ctrlKey) are pinned.
- Mutant `alt-not-chord` (`"AltModifier"` removed from `CHORD`): SURVIVED in `tests/unit tests/qt tests/e2e/test_present.py` (226 passed). It also SURVIVED in tests/export on mac-personal (46 passed). Under the mutant, Option+↓ advances the Presenter and the Audience. On macOS, Option+arrow is a common text-editing chord.
- Fix: in `test_a_chord_is_not_navigation`, add Alt+↓ (`Qt.KeyboardModifier.AltModifier`) beside Cmd+↓. In the export key test, add `"{key: 'ArrowDown', altKey: true}"`.

### L4. `test_from_wins_only_once` names a rule that no longer exists. (tests/qt/test_presenter.py:589)
- Principle: test names describe behaviour. The once-guard is gone, so "only once" names a mechanism that no longer exists. The behaviour is: "a relaunched Audience gets the current position."
- Fix: rename it to `test_a_relaunched_audience_gets_the_current_position_not_the_from_one`, and drop the docstring that the name then repeats.

## Mutation results

mac-work-2: `tests/unit tests/qt tests/e2e/test_present.py`, `-x -n 4`, runner `/tmp/rvp2-work/mutants.py` (deleted after the run). Each mutant was restored with `git checkout`.

| mutant | result |
|---|---|
| structure-red-kept, stale-amber-kept | killed (test_a_clean_rebuild_clears_…) |
| adopt-covered-any-clip | killed (test_a_reconnect_to_another_builds_cover_is_not_adopted) |
| timeline-click-plays | killed (test_a_timeline_click_shows_the_beat_as_last_seen) |
| missing-script-not-red | killed (test_moving_while_the_script_is_missing_shows_red) |
| from-ignored-on-reconnect | killed (test_from_wins_over_what_the_audience_shows) |
| build-watch-not-readded | **survived** (M1) |
| no-immediate-build-check | **survived** (M1) |
| alt-not-chord | **survived** (L3) |

Probes: `watchprobe.py` (M1, 3/3 runs). `l3probe.sh` (L1, hung to exit 124 at 75 s). lint-imports export → presenter (broken, as intended) and export → PySide6 (kept: L2).

Clean-up: every mutant was restored, and `git status` is clean in the worktree and in the mac-personal clone. Both mac-personal clones (`/tmp/rvp2`) and `/tmp/rvp2-work` are deleted. No process of mine is still running.

## Count

HIGH 0, MEDIUM 1, LOW 4.
