# Code review: STRATUM 1–2, round 1

Repo: `manim-presentations-UI-and-harness` @ `7555584` (branch `wip`) plus the uncommitted `pyproject.toml` filterwarnings line.

Mutants and probes ran on mac-personal (`~/work/...`, same commit). Baseline: 88 passed in 25.7 s. Scripts: `/tmp/rv-s12/{run.sh,probes.sh}` on mac-work-2. Every mutant was restored with `git checkout -- .`.

Counts: **HIGH 6 · MEDIUM 11 · LOW 10**

---

## HIGH

### H1. The import-linter test is vacuous: it can never fail
`tests/unit/test_cli.py:50-52`
- **Problem.** The test runs `python -m importlinter.cli lint`. `importlinter/cli.py` defines click commands but has no `if __name__ == "__main__"` block. So the command imports the module, does nothing, and exits 0.
- **Principle.** Test design (non-vacuous, falsifiable). This is also the failure-mode list's "test subversion".
- **Evidence.**
  - Mutant: add `import deck` to `talk.py` (the mutant named in PLAN §3.1). The test stayed green (7 passed).
  - With that same mutant, `uv run lint-imports` exits 1 and names `manim_presentations.talk -> manim_presentations.deck (l.29)`.
  - The module form still exits 0.
  - So no import contract in this stratum has been proven by the one suite. The rule "each stratum mutation-tests its contracts" is unmet.
- **Fix.** Run `[sys.executable, "-m", "importlinter", "lint"]` (the package has a `__main__`; check it), or `[Path(sys.executable).parent / "lint-imports"]`. Then re-run the `talk → deck` mutant and see red.

### H2. The transient check is wrong in every chapter after the first
`manim_presentations/talk.py:143` (marks the chapter-local beat index) and `manim_presentations/geometry.py:120,156` (compares it with a talk-wide index).
- **Problem.** `talk.transient` stores `len(self.beats) - 1`, which is the beat's index inside its chapter. `build.py:236-237` passes `geometry.check` the beats of all chapters joined into one list, and `check` compares `u.transient_beat == n` with `n` as the talk-wide index. Explainers had one scene, so the two indexes were the same there. Per-chapter scenes (D13) broke that.
- **Principle.** Correctness: a peace-of-mind check silently passes broken talks (no fallbacks; a failure that looks like a success). Mark, then route: the beat identity was marked in one coordinate system and routed in another.
- **Evidence.** Probe P1 on mac-personal:
  - A chapter `late` has beat `two` with `talk.transient(Dot)` and no FadeOut.
  - Appended as the 4th chapter of the edge fixture, the build exits 0 with `checks passed`.
  - Built as the only chapter, it exits 1 with `transient 1`.
  - The suite stays green because both fixtures that exercise transient (`edge`'s `marks`, `geometry`) are chapter 0.
- **Fix.** Pass `geometry.check` one chapter's beats at a time, or make the mark chapter-relative on both sides. Prefer per-chapter calls: `check(r.beats, …)` for each `r`, so the beat index is local by construction. Add a must-fail overlay where a second chapter leaves a transient on screen.

### H3. A `frame_width` override renders with non-square units (distorted picture)
`manim_presentations/settings.py:72-74`, `manim_presentations/clip.py:49-50`
- **Problem.** `Settings.frame_height` is always 8. A talk that sets `render.frame_width` (PLAN §3.2's table: "Mixing Deluxe sets 16") at a non-2:1 pixel shape gets a different pixels-per-unit on each axis. Circles become ellipses, and the geometry, off-frame and min-text checks use the wrong frame.
- **Principle.** Correctness. It also breaks the as-built engine's invariant: `manim-presenters/manim_presenters/build.py:158` derives `frame_height = frame_width · H / W`.
- **Evidence.** Probe P2: `Settings(3456×2168, frame_width=16)` → `config.frame_width=16, frame_height=8`. That gives 216 px per unit on x and 271 px per unit on y. Mixing Deluxe (STRATUM 10) is exactly this case.
- **Fix.** Make `frame_height` a derived property, `frame_width · pixel_height / pixel_width`. Keep `FRAME_HEIGHT_UNITS` only as the source of the default `frame_width`. Then the DECISIONS min-text unit ("/ settings frame_height") stays correct. Add a unit test with the 3456×2168, frame_width 16 settings: a circle's projected width must equal its projected height.

### H4. The "twins" test does not catch the shared-cache mutant it names
`tests/build/test_checks.py:52-57` and its docstring
- **Problem.** STRATA asks for "two chapters' identical Text/MathTex on a cold cache pass (mutant: shared cache)". PLAN §3.11 says a shared cache would collide "deterministically". This test does not catch that mutant.
- **Principle.** Test design: every test names its mutant, and that mutant must turn it red.
- **Evidence.** Mutant: in `build.py:210`, pass `str(shared)` instead of `str(private)` to every pass-1 child. `-k twins` stayed green (1 passed in 4.5 s). The test's claim "a shared cache would collide … every run" is false at 480×270 on this Manim.
- **Fix.** Find the real race first. Either the collision needs more than two writers or a different object (probe it), or the claim is wrong. Then:
  - make the test observe it, for example by asserting each private copy holds only its own chapter's new entries plus the seed, so the private-copy property itself is checked; or
  - rewrite the docstring and record in DECISIONS that the race is not reproducible, so the property gets a different guard.

  Do not keep a docstring that claims a kill that does not happen.

### H5. Lock inheritance (a STRATUM 2 deliverable) has no test; the mutant survives
`manim_presentations/deck.py:63`
- **Problem.** `os.set_inheritable(fd, True)` is what makes the wipe at `build.py:164` safe against orphans (PLAN §3.5 step 2). Nothing in the suite observes it.
- **Principle.** Test design (each load-bearing property has a falsifiable test). Robustness (system edge cases: a SIGKILLed parent).
- **Evidence.** Mutant `set_inheritable(fd, False)`: all of `tests/build/test_checks.py` stayed green (14 passed). The only lock test (`test_a_concurrent_build_exits_3`) takes the lock from the test process, so it never exercises inheritance.
- **Fix.** Add the PLAN §3.11 test now, since the lock and pass 1 both exist:
  1. Start `mpres build` on a fixture with one slow chapter (`talk.wait` long enough, or a chapter that blocks on a FIFO it then reads).
  2. Block on the `snapshot:` phase line.
  3. SIGKILL the parent pid only.
  4. Assert an immediate second build exits 3 with "a build is running".
  5. After the orphan's parent-death watch fires, assert the build succeeds.

  The mutant then goes red.

### H6. Missing STRATUM 2 deliverable: the child-output reader thread
`manim_presentations/build.py:81-120`
- **Problem.** STRATA STRATUM 2 lists "child stdout/stderr files + reader thread" for `build.py`. The files exist. No reader thread does: child output is read only after a failure (`build.py:110`). The scaffolding list does not defer it to STRATUM 3.
- **Principle.** Spec coverage. Deliver the planned interface in the stratum that owns it, so STRATUM 3 only adds to it.
- **Evidence.** `grep -n Thread manim_presentations/build.py` matches nothing. `threading` is imported only to build a temp file name (L3 below).
- **Fix.** Add the tail-into-one-progress-line reader that PLAN §3.5 step 7 describes, used by `run_all`. Or, if it has no consumer until workers exist, record that deferral in DECISIONS and in STRATA's scaffold line. Either way the plan and the code must agree.

---

## MEDIUM

### M1. Bad input reaches the user as Python tracebacks
`manim_presentations/build.py:146,172`, `manim_presentations/cli.py:37`
- **Problem.** Three authoring mistakes crash the CLI with a traceback instead of a one-line error:
  - **P4:** a bad slug in `script.md` raises a `ValueError` from `script._heading`. `build.py:172` does not catch it. Every `script.parse` error behaves the same way.
  - **P5:** a chapter that calls `talk.beat("a")` twice, against one `## a`, crashes in `pairing`: `ValueError: zip() argument 2 is longer than argument 1` from `zip(..., strict=True)` at `build.py:146`.
  - **P3:** `--workers 0` (or a negative value) crashes with `ChildProcessError: [Errno 10] No child processes`. `run_all` never spawns, then calls `wait4`.
- **Principle.** Robustness: validate exactly once, at the boundary. No silent garbage, and no unhelpful crash either.
- **Fix.**
  - Wrap the script load as `ScriptError`, then route it to `BuildError(1, …)`, or validate `script.md` in `cli`'s boundary.
  - Make `talk.beat` raise `TalkError` on a repeated slug in its chapter. Then `pairing` never sees duplicates. Or compute the order message without a strict zip.
  - Give argparse a `type=` that refuses N < 1.

### M2. An outside read that talk code does not catch prints a traceback, not the guard's message
`manim_presentations/pass1.py:106-122`
- **Problem.** The nicely worded `chapters/x.py read …` message prints only when talk code swallowed the `PermissionError`. In the common case (no try), the `PermissionError` is not a `TalkError`. It propagates out of `main` as a full traceback (probe P6). The parent then shows only its last 40 lines (M3).
- **Principle.** Simplest internal logic: one route for one failure. Mark, then route: the guard already marked the violation, so route on that mark, not on whether talk code caught it.
- **Fix.** Catch the exception around `scene.render()` and check `guard.violations` first, for both paths. Then the uncaught and the swallowed cases print the same message. Delete the redundant `guard.active = False` at L110, which the `finally` already does.

### M3. The failing child's stderr is cut to 40 lines (an arbitrary limit)
`manim_presentations/build.py:111`
- **Problem.** `err[-40:]` is a new cap. Explainers' `render.py:135` prints the whole log. The message also does not name the log file, so anything cut is invisible.
- **Principle.** No arbitrary limits or constants. PLAN §3.5: "prints the failing child's stderr".
- **Fix.** Print the whole stderr. If a cap is ever wanted, it needs a stated origin and the log path printed beside it.

### M4. The read guard lets talk code read TMPDIR through `r+`/`a+`
`manim_presentations/pass1.py:62,68`
- **Problem.** TMPDIR is allowed for "write-mode" opens, and `writing` is true for any `+` mode or `O_RDWR`. So `open(tmp/x, "r+").read()` passes. PLAN §3.5: "reads there fail like any other read outside the snapshot."
- **Evidence.** Probe P7: a chapter that reads a TMPDIR file through `"r+"` builds with `checks passed`.
- **Principle.** Exact guards, not exhaust-based. The mode letter stands in for "does not read".
- **Fix.** Allow TMPDIR only for opens that cannot read: `O_WRONLY`, or mode `w`/`a`/`x` without `+`. If `tempfile`'s probe needs `O_RDWR|O_CREAT|O_EXCL`, allow exactly that flag set (it creates a file, so nothing old is read), and cite it.

### M5. The projection hook test cannot fail for either hook it covers
`tests/unit/test_hooks.py:101-110`
- **Problem.** The test uses a default 2D camera: `frame_center = 0`, and `transform_points_pre_display` is the identity for finite points. Dropping both terms gives the same numbers.
- **Evidence.**
  - Mutant: `screen` returns `points[:, :2]`. `test_hooks.py` and `test_geometry.py` both stayed green (8 passed).
  - Mutant: drop `frame_center` from `RecordContext._matrix`. `test_hooks.py` stayed green.
- **Principle.** The gate: "would this test still pass if the function returned its input?" Yes, so it observes nothing. PLAN §3.11: one test per touchpoint that "fails loudly if the hook stops firing".
- **Fix.** Use a camera whose `frame_center` is moved (a `MovingCamera` frame shifted, or `camera.frame_center` set). Assert the projected mean equals the object position minus the offset. Add a recorder case where two scenes differ only in `frame_center` and must get different digests.

### M6. Two Recorder touchpoints have no test: the static-frame chain and background-coloured vmobjects
`manim_presentations/clip.py:164-171,193-195`; `tests/unit/test_hooks.py`
- **Problem.** The `clip.py` docstring says every touch is "tested one to one". `set_frame_to_background` (`_load`) and `display_multiple_background_colored_vmobjects` (`_backgrounds`) are not.
- **Evidence.**
  - Mutant: `_load` sets `self._canvas = b""`. `test_hooks.py` stayed green (7 passed).
  - Mutant: `_backgrounds` records nothing. Also green.
- **Principle.** Test design: one test per touchpoint, falsifiable.
- **Fix.** Add two digest tests:
  - (a) A static object whose colour differs between two scenes, while a second object animates. Manim draws the first from the static frame. The digests must differ.
  - (b) Two background-image VMobjects (`color_using_background_image`) with different images. The digests must differ.

### M7. `TEST_WORKERS` / `TEST_WORKERS_WIDE` are not conftest constants
`tests/build/test_checks.py:8`, `tests/build/test_geometry.py:24`, `tests/conftest.py:60`
- **Problem.** STRATUM 1 and PLAN §3.11 put the two constants in `conftest.py`. Today the value is `W = "2"` in one file, with a comment calling it TEST_WORKERS, and the literal `"4"` in two others.
- **Principle.** Single source of truth: one number in one place.
- **Fix.** Define `TEST_WORKERS = 2` and `TEST_WORKERS_WIDE = 4` in `conftest.py` and import them. These are not part of the known-pending width hook.

### M8. The fourth link-routing case is unasserted
`tests/e2e/test_setup.py:49-56`
- **Problem.** STRATUM 1 lists four cases. The fourth is "already on PATH, as CI arranges → no rc line". The relink test runs with `~/.local/bin` on PATH but never asserts that the rc file was left alone.
- **Principle.** Spec coverage, with a falsifiable test.
- **Evidence.** A mutant setup.sh that always appends the line (dropping the `case ":$PATH:"` guard) would pass all three tests. This was read, not run.
- **Fix.** In that test, or a separate one, assert `not (home / "zdot" / ".zshrc").exists()`.

### M9. setup.sh's TinyTeX gate checks something other than completion, and the "pin" does not hold
`setup.sh:24-36`
- **Problem.** Two flaws:
  - The install block is skipped whenever `tlmgr` exists. If `tlmgr install` fails partway (network, mirror), every re-run skips the packages and leaves a broken TeX. The CI cache keyed on `setup.sh` can then save that broken tree.
  - `tlmgr update --self` plus `tlmgr install` pull current packages from CTAN. The comment says "pinned". After the next TeX Live annual release, `tlmgr update --self` on a 2026 install refuses the cross-release update, so fresh setups and CI break around April 2027.
- **Principle.** Robustness: retries must be idempotent. Exact, not exhaust-based: `tlmgr`'s presence stands in for "installed". Comments must state true properties.
- **Fix.**
  - Run `tlmgr install …` unconditionally. It is a fast no-op when the packages are present. Or gate on a marker written last.
  - Point `tlmgr` at the pinned year's frozen repository (`tlmgr option repository <historic>/2026/tlnet-final` once it exists), or record in DEBT that the pin covers only the bundle.
  - Reword the comment either way. The cache-id hashes `texlive.tlpdb`, so correctness holds, but the comment overstates the pin.

### M10. The STRATUM 2 `import build` mutant cannot be caught yet, and STRATA says it is
`tests/unit/test_cli.py:40-47`
- **Problem.** STRATUM 1 says "STRATUM 2 adds the `import build` mutant". `build.py` does not import Manim yet (it never imports `clip`), so a top-level `import manim_presentations.build` in `cli.py` leaves `--help` free of Manim.
- **Evidence.** That mutant stayed green (7 passed).
- **Principle.** Test design (a named mutant must go red). No spec drift.
- **Fix.** Record in STRATA/DECISIONS that the mutant becomes live in STRATUM 3, when `build → clip`, and run it then. Do not claim it for STRATUM 2.

### M11. The warm-cache mutant named in STRATA survives
`tests/conftest.py:73-75`
- **Problem.** STRATA STRATUM 2 says: "mutant: seed from the shared cache without copying". No test observes it.
- **Evidence.** Mutant: replace the copy with a symlink of `build/.cache` to the session cache. All of `test_checks.py` stayed green (14 passed). Builds then merge into the session-wide cache, so tests share mutable state.
- **Principle.** Test design. Parallel correctness ("never let your own parallel work contend with the thing under test").
- **Fix.** Add an assertion that a test's build leaves the session cache unchanged (hash or listing before and after), or that `build/.cache` is a real directory. Or drop the mutant claim from STRATA with a reason.

---

## LOW

- **L1.** `pyproject.toml:8`: the comment says "README: Manim touches". The README has no such section. Per STRATA the list lives in the `clip.py`/`manim_hooks.py` docstrings. Point the comment there. (No stale parts.)
- **L2.** `pyproject.toml:44-53`: PLAN/STRATA say "pyright strict on the package". The config is strict on 7 files and standard on the rest, with a reason given. That is honest, but it is an unrecorded deviation. Add it to DECISIONS.
- **L3.** `build.py:289`: the temp name includes `threading.get_ident()` in a single-threaded parent. That is the only reason `threading` is imported. Use `os.getpid()` alone. (Minimality.)
- **L4.** `headroom.py:36`: `os.cpu_count() or 1` defends a value that must exist. Use `len(per_cpu)`, which is the same measurement that produced `busy`. (No pointless defensive code; one source.)
- **L5.** `pass1.py:44`: `real = lambda p: os.path.realpath(p)  # noqa: E731` wraps a function in a lambda and needs a noqa for it. Use `os.path.realpath` directly. The same pattern appears at `talk.py:161`.
- **L6.** `geometry.py:17-21`, `records.py:21`: `Finding.kind` is a free `str` (`"overlap"`, `"pairing"`, …). Make it a `Literal[...]` so a typo is a type error. Also, pairing and empty-beat findings in `build.py` import `Finding` from `geometry`, so a build-wide concept lives in one check's module. (Tagged unions; cohesion.)
- **L7.** `build.py:247-250`: `--workers` prints `pass-1 width: N (--workers)` without the RAM estimate PLAN §3.5 step 6 asks for. The one-job path prints no width line at all ("width: 1 (1 job)").
- **L8.** `tests/unit/test_hooks.py:93`: `record_creation_lines` patches `Mobject.__init__`/`copy` globally in the xdist worker and never restores them. Later tests in that worker run with wrapped (and possibly double-wrapped) constructors. Use `monkeypatch.setattr` on `Mobject`. At L163, `config.dry_run = False` resets nothing the test changed (the work ran in a subprocess). Delete it.
- **L9.** `tests/conftest.py:35-37`: `copy_talk` tries `examples/` and then falls back to `tests/fixtures/` by existence. Pass the source path explicitly, or keep a table of the two names. (No fallbacks.) `setup.sh:11` ignores unknown arguments silently, so `./setup.sh --devv` installs without dev deps. Refuse unknown arguments.
- **L10.** `tests/build/test_checks.py:38`: the outside-read case uses `/etc/hosts`. STRATA and PLAN say `/tmp/x`, and PLAN expects probes may add `/private/etc` as a root (for `mimetypes`), which would turn this test into a false failure. Use `/tmp/x` as specified. Separately, `test_a_concurrent_build_exits_3` runs with no timeout, so a blocking-lock mutant hangs the suite instead of failing. Give `mpres()` a timeout.

---

## Mutants run (mac-personal)

| Mutant | Target test | Result |
|---|---|---|
| `screen` returns `points[:, :2]` | test_hooks, test_geometry | **survived** (M5) |
| `_load` ignores the saved frame | test_hooks | **survived** (M6) |
| `_backgrounds` records nothing | test_hooks | **survived** (M6) |
| `_matrix` drops `frame_center` | test_hooks | **survived** (M5) |
| top-level `import build` in cli | test_cli | **survived** (M10) |
| `import deck` in talk.py | test_cli (lint-imports) | **survived**: vacuous test (H1) |
| pass 1 on the shared cache | test_checks -k twins | **survived** (H4) |
| lock fd not inheritable | test_checks | **survived** (H5) |
| warm cache symlinked, not copied | test_checks | **survived** (M11) |
| `dont_write_bytecode` removed | test_hooks -k bytecode | killed |
| guard keeps no violation list | test_checks -k reads | killed |
| run_all ignores width | test_checks -k workers_1 | killed |
| transient check disabled | test_geometry | killed |
| empty-beat check disabled | test_checks -k empty | killed |
| play-before-beat guard disabled | test_checks -k early | killed |

Probes P1–P7 (`/tmp/rv-s12/probes.sh`) give the evidence for H2, H3, M1, M2 and M4.

## Fine as is (checked, not reported)
- `run_all`: spawn, reap and kill logic, including KeyboardInterrupt.
- `posix_spawn` with `-P`.
- The audit-hook allow-list against PLAN §3.5, apart from M4.
- The cache merge (temp file then `os.replace`, skipping existing entries).
- `cli` boundary refusals.
- The settings origin validator.
- The protocol union and the Position table.
- The `script.py` vendoring (all 9 refactor tests carried, plus additions).
- The exactness of the geometry fixture test.
- `examples/hello` against §3.11.
