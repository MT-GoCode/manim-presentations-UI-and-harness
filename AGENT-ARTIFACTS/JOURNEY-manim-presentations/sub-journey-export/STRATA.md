# STRATA — sub-journey export (branch `sj/export`)

Brief: NORTH-STAR.md here. Sanctioned deviations: the parent DECISIONS (P4, P5) and DECISIONS.md here (fresh-element route, frame codes, key table, ENCODE_RAM). Clone: `conversation-contexts/manim-presentations-harness/export-clone`. Host: mac-work-2; every `uv run pytest` selecting `build`/`qt`/`export`/`e2e` and every heavy encode holds `flock /tmp/mpres-heavy.lock`. Local WebKit dies during demonlock's LOCKED hours, so locally the export tests run `-k chrome`; CI (macos-latest) is authoritative for WebKit. Each stratum ends with looped FRESH Claude reviews until only LOWs, then green CI. Owned files only: `manim_presentations/export.py`, `manim_presentations/player.html`, the `export` block in `cli.py`, one `[[tool.importlinter.contracts]]` block, `tests/export/**`, the export step in `tests/e2e/test_cli_chain.py`.

Shared test spine (built in E1, grown by E2–E3): `tests/export/frames_plugin.py` (fixtures, loaded by `pytest_plugins`; a second `conftest.py` would replace `sys.modules['conftest']`, which other tests import from) builds `tests/export/fixtures/frames.manim-presentation` once per session (the warm-cache recipe: one writer under `fcntl.flock`, the others read) and exports it per variant once; `tests/export/frames.py` holds the tests' own frame-code decoder (Python for decoded files; a JS string for the page, E2); the browser fixtures (E2, in frames_plugin.py: one headless browser per engine per worker, `webkit` and `chrome` via `channel="chrome"`, network routed to abort anything not `file:`/`blob:`/`data:`).

---

## STRATUM E1: `mpres export` writes one self-contained HTML whose every frame is the right one
description: The command and the file, before the player has logic. Files:
- `export.py`: `H0 = 1080`, `C0 = 28`, `ENCODE_CORES = 1.35`, `encode_ram(source_mp, out_mp)` (DECISIONS here), each cited; `DOM_KEY` (Qt key name → `KeyboardEvent.key` values); `export(root, out, height, crf, workers) -> int` (E3 adds `transcript`): under `Layout.clips_shared()`: `Deck.open`, `require_fresh`, height = `height or min(H0, render.pixel_height)` (an explicit height above the source refuses, naming the source height), width `2·round(H·w/h/2)`, prints the chosen height and width; `headroom.choose("export", workers, n, ENCODE_CORES, encode_ram(...), say)`; parallel re-encodes (`ProcessPoolExecutor(width)`, spawn) of P4's job verbatim at the deck's fps into a private `mkdtemp` under `Layout.export_tmp`, removed after; then the page: `player.html` with the manifest (`<script type="application/json">`: title, fps, key table, beats with chapter, slug, title, kind, frames; transcript fields per E3 — none yet) and one base64 `<script type="application/octet-stream">` block per beat, written atomically to `--out`. `say` flushes, so tests can block on phase lines.
- `player.html` (scaffold): parses the manifest and shows beat 0's frame 0 from its Blob URL; E2 replaces the script wholesale.
- `cli.py`: `export` subparser (`--out` required, `--height` even positive int, `--crf` 0–51, `--workers`; `--out` must name a file in an existing folder; `--transcript` arrives in E3 with its effect, so no flag is ever inert); `run_export` routes `IncompatibleBuild`, `Stale`, `TooBig`, `ExportError` to exit 1.
- `pyproject.toml`: contract "export reads the deck and re-encodes; it never builds or imports settings" (forbidden: build, clip, talk, pass1, worker, manim_hooks, settings, manim).
- `tests/export/fixtures/frames.manim-presentation` (frame codes, two chapters, a loop, notes, an untitled beat), `tests/export/frames_plugin.py`, `tests/export/frames.py`, `tests/export/test_file.py`:
  - every embedded clip, base64-decoded and decoded with av, has the printed width × height, the deck's fps, `BuiltBeat.frames` frames, and frame k reads `i<<8|k` (mutants: drop the last flush → frame count short; `rate=` from a constant → fps wrong; a re-render path is impossible by the contract);
  - default height = min(1080, 270) = 270 printed; `--height 180` gives 320×180; `--height 272` refuses naming 270; `--height 181` and `--crf 52` refuse at argparse (mutants: each bound off by one);
  - higher `--crf` gives a smaller file at equal height (mutant: crf not passed);
  - a stale talk refuses naming the file; an unbuilt talk refuses (`IncompatibleBuild`);
  - `export` width line: `--workers 3` prints `export width: 3 (--workers)`; without it the machine line's width equals the restated 75% formula (mutant: `jobs` not passed);
  - `RamExceeded`: engine-edit copy with `encode_ram` ×10⁶ exits 1 with "pass --workers 1" and writes no file; with `--workers 1` it exports;
  - a build during export renders, waits at commit, then commits: export SIGSTOPped after its width line (inside the lock), a beat edited, `mpres build` blocks on `commit: waiting for shots/export to finish`, the index is unchanged until SIGCONT, then both exit 0 and the new index lands (mutant: export without `clips_shared()` → the waiting line never comes);
  - no temporary files left under `build/.export` after success or after a failed encode (mutant: no cleanup).
verifiable execution: `uv run pytest tests/export tests/unit` green (locally `-k "not webkit"`), lint-imports, pyright, ruff; CI green.
human-verifiable results: `mpres export frames.manim-presentation --out /tmp/f.html` prints `export: height 270 · width 480 · crf 28`, the width line, `exported /tmp/f.html · N KiB · 4 beats`; the file opens offline on beat 0.

## STRATUM E2: The player — Next/Previous/Replay, no black frame, loops loop, in WebKit and Chrome
description: `player.html`'s script, replacing E1's scaffold whole:
- `step(position, action, slugs)` and `showFor(position, kind, action)` mirroring `protocol.step` and the Presenter's show_for (Before → cover beat 0; Next/Replay → play, loop if a loop; Previous/jump → hold, loop if a loop); boundaries flash red.
- Blob window: URLs for beats within ±1 of the current one, created on entering, revoked after the swap that leaves.
- `show(beat, frame, play)`: the fresh-element route (DECISIONS here) with a generation counter, so a fast key press abandons the stale show (its element removed, never raised).
- Buttons Previous / Next / Replay, the manifest's key table (`event.key`, `event.repeat` dropped), a jump list of titles grouped by chapter (a jump = At(X) shown as for Previous).
- Tests (`tests/export/test_player.py`, parametrized over `webkit` and `chrome`):
  - position table: every row of `tests/position_table.json` through the page's `step` (mutant: Previous at At(first) stays);
  - click-through by keys over all beats, then back with Previous to Before: after each action the front video (`elementFromPoint` at the stage centre) reads the expected beat and frame — Next: frame 0 at the swap, then advancing; Previous: the last frame `frames−1`; Before: frame 0 (mutants: seek to k/fps → Chrome reads k−1; reuse the element → WebKit reads the stale frame);
  - no black and no wrong frame on any transition: a MutationObserver logs the front video's code at every DOM change; every logged code is either the outgoing beat's or the target's expected frame, and never 0 (an unready element) (mutant: raise on insert);
  - Replay, a jump to the current beat, a jump far ahead, and three Nexts pressed in one task land on the right frame with one video left in the DOM (mutant: no generation check);
  - non-loop beats reach `ended` and keep showing `frames−1`; the loop beat after 2× its duration is not paused, its codes wrapped at least once and are all its own (mutant: no `loop`);
  - Blob window: after every action the beats with live URLs are exactly current ±1, and created − revoked = window size (mutant: no revoke);
  - buttons, PageDown/PageUp and R act like the keys; an auto-repeat keydown does nothing (mutant: repeat not dropped);
  - offline: zero aborted requests across the whole run (mutant: an external script tag).
- Measure the export test process-tree peak (browser + harness) and CI time; if the `export` cost exceeds conftest's heaviest TEST_COST or CI > 30 min, report to the parent with the numbers.
verifiable execution: `uv run pytest tests/export` green on CI for both engines.
human-verifiable results: a headless screenshot strip of the frames talk at each transition (CI artifact under `test-results/`), and the e2e-style click-through log.

## STRATUM E3: Transcript panel, privacy, and the CLI chain — End of export Period
description:
- `export.py`: transcript `none` → no transcript fields; `narration` → each beat's `script.parse(...)` narration; `full` → plus notes. `player.html`: the panel (only when the manifest has a transcript): one entry per beat (title, narration, notes styled apart in `full`), the current beat highlighted and `scrollIntoView({block: "nearest"})`, a click jumps (At(X) shown as for Previous), a toggle button hides the panel; `@media (min-aspect-ratio: 1/1)` puts it beside the video, otherwise below.
- Tests (`tests/export/test_transcript.py`): `none`: no narration line and no note line in the HTML or any base64-decoded block, and no panel element; `narration`: every narration line present, no note line anywhere (mutant: notes included); `full`: notes present; highlight follows Next/Previous and the highlighted entry is inside the panel's visible box after moving to the last beat (mutant: no scroll); clicking an entry shows that beat's last frame (code); toggle hides the panel and the video box grows; 1600×900 → panel right of the video, 600×1000 → below (mutant: the media query inverted). Both engines.
- `tests/e2e/test_cli_chain.py`: append the export step: `mpres build` → `mpres shots` → `mpres export examples/hello` at `--transcript full`; the manifest's slugs equal the index's, and in Chrome the page clicks through every beat to the end with no media error.
- End-of-period review: FRESH reviewers over the whole sub-journey diff (`git diff a6bd216..sj/export`), then report to the parent.
verifiable execution: full `uv run pytest` green on CI (≤ 30 min), branch pushed.
human-verifiable results: the exported Hello talk with the transcript panel beside the video; the privacy tests' three variants.
