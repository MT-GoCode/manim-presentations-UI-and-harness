# STRATUM 10 results: Mixing Deluxe migrated

Host: mac-work-2. Engine: work-s10 at 9a3763a, unedited. Builds ran at the default width; other agents kept the load
average between 16 and 41 for the whole run.

## Times

- Start: 2026-10-31 01:39 PDT. Build green: 01:52 (13 minutes into the one-hour box). End of all STRATUM 10 work: 02:03.
- Talk: `~/manim-presentations/mixing-deluxe.manim-presentation/` (10 chapters, 57 beats, 278 animations, 3 loops).
- `ls` shows a lowercase `script.md` and none of the deleted files (SCRIPT.md, NARRATION.md, export-script.mjs,
  deck.py, render.json, `__pycache__/`, transcript.json, the seven old class modules). The old engine's zero-byte
  `.build.lock` and `.transcript.json.lock` were also deleted from the copy. The source checkout is untouched.
- Converter (throwaway): `conversation-contexts/manim-presentations-harness/s10-converter/` — `convert.py`
  (transcript.json → script.md + helpers/content.py + id_to_slug.json; rewrite of quoted beat IDs), `move.py`
  (mechanical class → `chapters/<slug>.py` move, then hand-edited: ZephonSingle's `self.speed` state became a local
  passed to `hold(talk, speed, …)`), `compare.py`, `presenter_shot.py`.
- Slug renames printed by the converter: beat 09.3 → `live-tokenization-2`, beat 10.1 → `questions-2`.

## First build: failures per kind

| kind | count |
|---|---|
| min-text | 791 |
| overlap | 3 |
| off frame, loop closure, tee, shadow mismatch, pairing, no-animation beat | 0 |

## Exits taken (all listed in the talk README)

- min-text: `talk.toml [checks] min_text = 0.001027` — the talk's smallest Pango text, 9.9 pt effective
  (ContextView's GpuTimeline phase labels, 18 pt scaled 0.55) at frame height 10.037. Origin "presented live
  2026-10". No TeX in the talk, so `min_tex` keeps its default.
- attach: `chapters/optimization-3-make-zephon-live-tokenization-go-brrr.py:271` `talk.attach(waiting, queue_focus)`
  (two overlap errors, beats starved-models and the-measured-gap).
- attach: `chapters/in-progress-a-well-oiled-swarm-machine.py:245` `talk.attach(hit, main)`.
- No bleed, loop→beat or talk.wait exits. All three loops close at tolerance 0.

Second build green (exit 0, digests verified, 57 clips stream-checked).

## Cold build (STRATUM 11 documents this)

`rm -rf build` then `mpres build`: **397.6 s wall** (6 min 38 s), at load average 41 rising to 42.
Phases: pass 1 137.6 s (width 5, 335 new cache entries) · render 226.4 s (11 chunks, 5 workers, 1.26 GB peak per
worker) · join 27.0 s · commit 0.8 s. Inside D14's 10-minute budget. The earlier warm-cache build (build 2) took
452.7 s at load 34 (pass 1 176.3 s, render 227.3 s, join 35.4 s), so load from other agents dominates the spread.

## D12 (last-beat edit) — MISSES 20 s; Minh's call

Edit: `chapters/questions.py` `FadeIn(mark, scale=0.8)` → `0.7`, rebuild; then reverted and rebuilt (second sample).

| sample | wall | pass 1 | render | join | commit | load |
|---|---|---|---|---|---|---|
| edit | **71.1 s** | 63.5 s (10 chapters, width 8) | 1.75 s (1 beat, 56 reused) | 0.15 s | 0.20 s | 33 → 26 |
| revert | **59.7 s** | 55.0 s (10 chapters, width 9) | 1.66 s (1 beat, 56 reused) | 0.03 s | 0.22 s | 24 → 16 |

Pass 1 is ~90% of the time: every edit re-runs pass 1 for all 10 chapters, and Mixing Deluxe's heaviest chapter
bounds it. The real render is under 2 s. The D12 PASS in DECISIONS (18.4 s) was on the synthetic 57-beat-scale
talk, whose pass-1 chapters cost ~7.9 s each; this talk's chapters are far heavier in pass 1 under this load.
Reported to Minh through the main agent with this breakdown.

## Contact sheets vs the old build's end frames

`mpres shots` → `/tmp/mpres-shots-mixing-deluxe/` (181 images, 10 contact sheets, 13.9 s). Every beat's new last
frame was paired with the old `build/<ch>/<id>-end.png` (same 3456×2168): mean absolute pixel difference per beat
0.01–0.59 out of 255 (worst: the-swarm-api 0.59, live-tokenization-2 0.42, live-catches-up 0.51). Side-by-side
sheets in `/tmp/s10-compare/<chapter>.png`. Eyeballed: chapter 09 side by side, contact sheets 06 and 08 — no
visible drift in layout, color or text; the residue is antialiasing-level (consistent with Manim 0.21 → 0.22).

## Presenter screenshot (STRATUM 8's human-verifiable result at Mixing-Deluxe scale)

`/tmp/mpres-presenter-mixing-deluxe.png`, 1728×1117, QT_QPA_PLATFORM=offscreen, Audience launched offscreen and
closed with the window (no process left). Status: "Audience: title covered · beat 0/57 · 0:00". `open_presenter`
maximizes the window, and the offscreen screen is ~800 px, so the script calls `showNormal()` before `resize`.
Observed: the editor's very short first beat renders at a size where "production" clips under a horizontal
scrollbar — the known no-font-ceiling item deferred to the P6 ladder at FINAL.

## Engine observation (not blocking)

On the first screenshot run (window closed, event loop kept 2 s), the Presenter printed a traceback after close:
`Link._dropped → audience_lost → refresh_status → self.status.setText` raised `RuntimeError: libshiboken: Internal
C++ object (Status) already deleted`. The second run did not reproduce it. It is teardown-only (the Audience still
exited), but a Link signal can reach a Presenter whose widgets are gone.
