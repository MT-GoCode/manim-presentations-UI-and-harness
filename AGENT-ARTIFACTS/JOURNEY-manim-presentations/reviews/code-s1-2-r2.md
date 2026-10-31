# Code review S1–2, round 2

Commit `4cddf8a` (branch `wip`). Fresh reviewer: did not read earlier reviews. Every file listed in the brief was read in full. Spec: STRATA S1–S2 + rules, PLAN rev 30-o §0–§3.5, §3.11 (and §8 for `save_beat`), DECISIONS. Mutants ran on mac-personal (load ≈1, same commit); the repo there was restored after each one (`git status` clean). CI on this commit is green: 93 passed, about 2 min wall time, under the 30-min bound.

Counts: **HIGH 1 · MEDIUM 8 · LOW 10**.

---

## HIGH

### H1. Import contracts for the modules this stratum created are missing; `clip` (the only fingerprinted file) may import unfingerprinted engine code
- **Where:** `pyproject.toml:69-101`.
- **Problem:** the STRATA rule says "each stratum adds the `[tool.importlinter]` contracts (§3.1 arrows) for the modules it creates". STRATUM 2 created `clip`, `manim_hooks`, `talk`, `geometry`, `pass1`, `deck` and `build`. The only contracts added are the scene-side ban (talk/pass1 must not import deck/script/protocol/build/cli), the build ban (build must not import pass1/talk/manim_hooks), and "no rendering library" for deck/geometry. These §3.1 arrows are not stated anywhere:
  - `clip → settings` only;
  - `manim_hooks → settings`;
  - `talk → {manim_hooks, clip, records}`;
  - `geometry → records`;
  - `deck → {script, settings, records}`.
- **Why it matters:** the arrow from `clip` carries weight. §3.1 rests pixel exactness on "the pixel path lives only in `clip.py`, whose hash alone is fingerprinted". If `clip` imports `manim_hooks` or `talk`, an unfingerprinted edit can change clip bytes, and nothing stops that import. Nothing stops a `deck → build` or `geometry → deck` cycle either.
- **Principles:** dependencies point one way; insane decoupling; this stratum's own rule.
- **Evidence:** mutant M8b added `from manim_presentations import manim_hooks` to `clip.py`. `test_import_contracts_hold` stayed **green**. M8a (`import deck` in `talk.py`) goes red, so the one contract that exists works.
- **Fix:** state the arrows as data.
  - One `layers` contract: `cli | build | pass1 | talk | manim_hooks | clip | (geometry, deck) | (settings, script, headroom) | (records, protocol)`, or the §3.1 equivalent.
  - Or explicit `forbidden` contracts. At minimum: `clip` must not import any `manim_presentations.*` except `settings`; `manim_hooks` only `settings`; `geometry` only `records`; `deck` must not import `build`, `clip`, `talk`, `pass1` or `manim_hooks`.
  - Re-run M8b to red.

---

## MEDIUM

### M1. The hostile-`manim.cfg` test cannot fail for the defect it names
- **Where:** `tests/unit/test_hooks.py:69-86`; code at `manim_presentations/clip.py:35-42`.
- **Problem:** the hostile config sets only `frame_rate`, `pixel_width` and `background_color`. `_render_keys` overrides all three anyway. So the test passes whether or not `render_config` rebuilds from the packaged `default.cfg`, which is the property in its docstring.
- **Principles:** non-vacuous tests (the gate); every test names a mutant that turns it red.
- **Evidence:**
  - Mutant M1 (`fresh = ManimConfig().digest_parser(parser)` → `fresh = config.copy()`): the test stays **green**.
  - Direct probe with a user cfg of `zero_pad = 9`, `write_all = True`, `save_last_frame = True`: the original code prints `4 False False` (clean). M1 prints `9 False True`, so the user's keys leak through. (`background_opacity` did not leak even under M1, so it is not a usable probe key.)
- **Fix:** the hostile cfg must set keys that `_render_keys` does not override, for example `zero_pad = 9` and `write_all = True`, and the test asserts their default values. Better still, assert that every key of `config` equals a fresh `default.cfg` digest plus `_render_keys`. Re-run M1 to red. The §3.11 "identical clips" form becomes possible in STRATUM 3.

### M2. The build lock is released before `.media` is removed
- **Where:** `manim_presentations/build.py:249-250` (`os.close(lock)`, then `shutil.rmtree(layout.media)`).
- **Problem:** once the fd closes (all children are reaped by then), a second build can take the lock, wipe `.media`, and start its snapshot. This build's `rmtree` then deletes the second build's snapshot and process directories while it runs. The window is small (one `rmtree` of the snapshot) but real. The comment at line 187 claims the wipe is safe because "holding the lock proves no earlier build process lives", and this order breaks that claim.
- **Principles:** robustness (concurrency prevented, not assumed absent); single owner for mutable state.
- **Fix:** swap the two lines (rmtree under the lock, then close), or drop the explicit close and let the process exit release it. A test is not practical for this window. The fix is ordering by construction.

### M3. The parent's cache merge and the cache-entry record are unverified
- **Where:** `manim_presentations/build.py:284-301` (`merge_caches`); `manim_presentations/pass1.py:71-72` (`cache_entries`).
- **Problem:** both are named STRATUM 2 deliverables ("cache-id + private copies + parent merge"; "audit-hook allow-list + cache-entry record"). No test observes either one. If the merge does nothing, the warm cache stays empty, every build runs cold, and every build still passes.
- **Principles:** non-vacuous tests; a code path nobody has seen execute.
- **Evidence:**
  - M14 (merge skips every entry): `tests/build tests/unit` gave **111 passed**.
  - M18 (`cache_entries` never recorded): the full suite gave **93 passed**.
- **Fix:** one build test on a cold copy with a new `Text`:
  - assert the entry's basename appears under `build/.cache/<id>/text` after the build;
  - assert a second build prints `0 new cache entries`;
  - assert `records.json`'s `cache_entries` names that basename. (`.media` is removed on success, so either keep the test on a failing-check overlay, where `.media` survives, or read it before cleanup.)
  - Also note that `cache_entries` currently picks up directory basenames (`tex`, `text`) from listings. See L5.

### M4. The read allow-list's exactness is mostly untested: three holes survive
- **Where:** `manim_presentations/pass1.py:73-80`, `38-41`.
- **Problem:** only one exactness case is tested: a read of `/tmp/x`. These mutants all survive:
  - **M12:** the tempdir is allowed for *read* opens too (`elif cannot_read(...)` → `else`). §3.5 says reads in the tempdir "fail like any other read outside the snapshot". The `/tmp/x` fixture cannot catch this, because macOS's `gettempdir()` is `/var/folders/…`, not `/tmp`.
  - **M19:** the listing-only roots also apply to `open`. `sys.path` holds the repo root (via the editable `.pth`), so a chapter could read the engine repo's files.
  - **M17:** the `O_CREAT|O_EXCL` allowance in `cannot_read` is removed. Even cold TeX builds pass, so no test ever runs that branch. Its comment describes a `tempfile` probe that no test triggers.
- **Principles:** exact, not exhaust-based; every guard is exact; no branch nobody has seen execute.
- **Evidence:** M12 gave 31 passed; M19 gave 21 passed; M17 gave 3 passed (the twins, imports and edge+hello cold builds).
- **Fix:** add overlays (one failure each), as parametrize rows of `test_each_authoring_error_is_named_at_its_line`:
  - a chapter that writes then reads `tempfile.gettempdir()/x` must fail (kills M12);
  - a chapter that opens `Path(manim_presentations.__file__).parents[1] / "pyproject.toml"`, or any file in a `sys.path` root outside the roots, must fail (kills M19);
  - a must-pass chapter that calls `tempfile.NamedTemporaryFile()` must build (kills M17). If that probe never fires in practice, delete the O_EXCL arm instead.

### M5. The parent-death watch and "the first failure kills the rest" are unverified
- **Where:** `manim_presentations/pass1.py:25-35, 86`; `manim_presentations/build.py:114-121`.
- **Problem 1 (the watch):** the lock test's `slow` chapter sleeps only 6 s, then finishes on its own. Without the watch, the orphan still exits, the lock is released, and the retry loop succeeds.
- **Problem 2 (the kill):** no test has a failing chapter beside a long-running one. If `killpg` is removed, the parent just waits.
- **Principles:** non-vacuous tests. Both behaviours are named in §3.5 and STRATUM 2.
- **Evidence:** M16 (no `watch_parent()`): the lock test stays **green**. M13 (no `killpg`): `tests/build` gave 21 passed.
- **Fix:**
  - Make `slow` sleep for a long time (e.g. `time.sleep(600)`, cut off by the test), and bound the retry loop by the watch's 1 s poll plus spawn time rather than `SUBPROCESS_TIMEOUT`. That makes the watch load-bearing.
  - For the kill: build `edge` with the `slow` and `early-play` overlays together (or a combined overlay), then assert the build fails with the early-play message and that the slow chapter's process is gone (no pid whose argv contains `pass1-slow`/`slow`) right after the CLI returns. The overlay helper takes one overlay, so add a combined `slow-and-early-play` overlay.

### M6. The pairing "same order" rule is untested
- **Where:** `manim_presentations/build.py:168-176`.
- **Problem:** §3.5 step 4 requires "same slugs, same order". No overlay has the same beats in a different order.
- **Evidence:** M15 (order block disabled): `tests/build` gave 21 passed.
- **Principles:** non-vacuous tests; spec coverage.
- **Fix:** add an overlay `swapped` whose `script.md` lists `## b`, `## a` while the chapter calls `a` then `b`. Assert the exact message `chapters/swapped.py:N order differs at beat 1 of "swapped": script.md "## b", chapter "a"`.

### M7. `save_beat`'s re-splice on concurrent change (§8, a STRATUM 1 item) is not built, and the "concurrent" test is not concurrent
- **Where:** `manim_presentations/script.py:132-140`; `tests/unit/test_script.py:86-91`.
- **Problem:** STRATUM 1 lists "`save_beat` … re-splicing on concurrent change, §8" and a "concurrent re-splice" test. §8 says `save_beat` re-reads the file just before `os.replace` and re-splices if the bytes changed. The code reads once and replaces. The docstring argues the window is microseconds, which is a fair minimality argument, but DECISIONS does not record it. The test writes the "external" edit *before* calling `save_beat`, so any implementation that reads at call time passes it.
- **Principles:** no spec drift (a sanctioned deviation goes in DECISIONS); non-vacuous tests.
- **Fix:** choose one.
  - (a) Add a DECISIONS entry: "save_beat reads at call time; §8's re-read narrows a window of the same order and is dropped". Rename the test to say what it checks.
  - (b) Implement the re-read compare, with a test that changes the file between the read and the replace (for example, monkeypatch `tempfile.mkstemp` to write another beat's edit first) and asserts both edits survive.
  - (a) is the minimal choice.

### M8. `BeatRecord` encodes one animation as three parallel tuples
- **Where:** `manim_presentations/records.py:39-41` (`run_times`, `drawn`, `frames`); mirrored in `talk.py:49-51, 121-123`.
- **Problem:** the record can hold different counts of run times, digests and frame counts, which is an illegal state. This is the data spine that STRATUM 3 (verification, chunking, join frame counts) and STRATUM 4 index into by animation number.
- **Principles:** make illegal states unrepresentable; boundary types later strata extend.
- **Fix:** `class Animation(_Frozen): run_time: float; digest: str; frames: int`, with `BeatRecord.animations: tuple[Animation, ...]`. `Talk.play` appends one `Animation`. The empty-beat check becomes `not b.animations`. Doing this now costs a few lines. Doing it after STRATUM 3 means surgery.

---

## LOW

- **L1** `settings.py:40-45`. `pixel_width = 0` (or `-2`) passes the even check, and `frame_rate = 0` is accepted. Bad values enter at the boundary and fail deep inside Manim. Fix: `PositiveInt` for the pixel sizes and frame rate, and `PositiveFloat` for `frame_width`.
- **L2** `setup.sh:40-42`. `tlmgr install` contacts the package repository on every run (measured: `tlmgr: package repository https://tlnet.yihui.org (verified)`, 1.05 s, even with every package present). So the `setup.sh` re-run needs the network, and the e2e docstring ("nothing is downloaded", `tests/e2e/test_setup.py:1-3`) overstates it. Packages also come from a floating repository, so STRATA's "pinned TinyTeX" pins only the installer bundle. `cache_id` keeps correctness intact, but this is not recorded in DECISIONS. Fix: skip `tlmgr install` when `tlmgr info --only-installed --list` already covers the list, and record the floating-package decision in DECISIONS (or point `tlmgr option repository` at a dated historic mirror).
- **L3** `pass1.py:27`. `watch_parent` reads `getppid()` in the child. If the build parent died before that line ran, the child records launchd (pid 1) as its parent and never notices. Fix: pass `os.getpid()` of the parent on argv/env and compare against it.
- **L4** `pass1.py:78-80, 124-126`. A write-only open outside the roots (and outside the tempdir) is recorded and reported as "read … outside the talk folder". §3.5 says the hook "checks reads only". Either let write opens through (writes are confined by `dry_run` and `media_dir`), or word the message for writes.
- **L5** `pass1.py:71-72`. `cache_entries` records the basename of any path under the cache, including listed directories (`tex`, `text`). STRATUM 3's prune keys on these, so record `open` events only.
- **L6** `build.py:131, 227, 289`. The process name `f"pass1-{c}"` is built in three places, and `spawn`/`run_all` both spell `"stdout"`/`"stderr"` (`build.py:89-90, 110`). Single source of truth: one `pass1_name(slug)` helper, and the log path returned by or owned in one place (ideally `Layout`).
- **L7** `geometry.py:16`. `Kind` includes `"pairing"` and `"empty-beat"`, which are build checks. So the build's vocabulary of check kinds lives in the geometry module, and STRATUM 4–5 will add more kinds there. Move `Finding`/`Kind` to the build side, or to `records` if both sides need it.
- **L8** `clip.py:39`. `Path(...).open()` is never closed. Use `parser.read(path)`.
- **L9** `talk.py:93-96, 126-127`. The "defines no construct(talk)" and "no talk.beat() in the chapter" TalkError paths are never run by a test. Add two one-line overlays as parametrize rows.
- **L10** `tests/unit/test_headroom.py:28-35`. The `sample` test checks only bounds (`0 ≤ idle ≤ cpu_count`). A mutant returning `len(per_cpu)` (ignoring busy) passes it. This is acceptable given that §3.11's default-width test (STRATUM 3) owns the one-sided bound. Note it there.

Not raised (checked and fine):
- spawn/reap: `posix_spawn` + `wait4(-1)`, `setsid` group kill, EPERM on zombie leaders;
- lock inheritance (M3 kills it);
- `/dev/null` root (M2 kills it);
- `dont_write_bytecode` placement and its test (M6);
- the job plan's private copies (M7);
- the transient per-chapter index (M11);
- the warm-cache seeding mutant (M10);
- `--help` without manim (M9);
- `RamExceeded` routing;
- the snapshot copy route;
- comment quality (crisp, rationale only);
- CI steps and caches against §3.11.

---

## Mutants run (mac-personal, `uv run pytest -n 8 -p no:cacheprovider`, restored after each)

| # | Mutant | Target tests | Result |
|---|---|---|---|
| M0 | baseline (none) | `tests` | 93 passed |
| M1 | `render_config` copies live `config` instead of rebuilding from `default.cfg` | `test_render_config_ignores_a_user_manim_cfg` | **survived** (MEDIUM M1); direct probe shows leaked `zero_pad=9`, `write_all=True` |
| M2 | `/dev/null` removed from roots | twins (cold) | killed (warm-cache and cold twins builds fail) |
| M3 | build-lock fd not inheritable | lock-outlives test | killed |
| M4 | `guard.violations` ignored | reads-outside | killed |
| M5 | spawn up to `width + 1` | `--workers 1` peak | killed |
| M6 | `dont_write_bytecode` not set | `test_pass1_writes_no_bytecode` | killed |
| M7 | pass 1 given the shared cache | `test_pass1_jobs` | killed |
| M8a | `talk` imports `deck` | `test_import_contracts_hold` | killed |
| M8b | `clip` imports `manim_hooks` | `test_import_contracts_hold` | **survived** (HIGH H1) |
| M9 | top-level `import manim` in `cli` | `test_help_imports_no_manim` | killed |
| M10 | warm cache symlinked, not copied | overlap build | killed (teardown digest) |
| M11 | transient index taken across all chapters | late-transient | killed |
| M12 | tempdir allowed for read opens | `tests/build` + hooks | **survived** (M4) |
| M13 | no `killpg` on first failure | `tests/build` | **survived** (M5) |
| M14 | cache merge copies nothing | `tests/build tests/unit` | **survived** (M3) |
| M15 | pairing order check disabled | `tests/build` | **survived** (M6) |
| M16 | no parent-death watch | lock-outlives test | **survived** (M5) |
| M17 | O_EXCL allowance removed from `cannot_read` | twins / imports / edge+hello (cold) | **survived** (M4: branch never exercised) |
| M18 | cache entries never recorded | `tests` | **survived** (M3) |
| M19 | listing roots also allowed for `open` | `tests/build` | **survived** (M4) |
