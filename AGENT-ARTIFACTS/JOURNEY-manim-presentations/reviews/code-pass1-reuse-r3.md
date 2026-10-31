# Code review: incremental pass 1 (pass1-reuse at 18db248), round 3

Scope: the round-2 fixes only (`git diff 8e9b4a2 18db248`), checked against the r2 findings and the DECISIONS line
"Incremental pass 1, review r2". I read pass1.py whole and the changed hunks of build.py.

Every probe and mutant ran on mac-personal, in a clone of 18db248 at /tmp/rvr3/repo. The probes are pytest cases in
`tests/build/test_rv3.py`, an untracked file that I deleted afterwards. They use the suite's own `prebuilt("edge")`,
`ran` and `GROWS` helpers.

Each staleness probe works the same way:
1. Edit `chapters/sizes.py` to branch on a value, and build once to prime it.
2. Change a talk file (the trigger) and build again. This is the incremental build.
3. Copy the talk without build/ and build the copy. This is the cold build.
4. Compare the `grows` beat's fingerprint from step 2 with the one from step 3.

## Round-2 fixes: verdict
- Every distribution's RECORD in the key (r2 H1): **fixed.** The sort is by name, a missing RECORD now raises an
  error, and the unused `identity` parameter is gone. I found no defect.
- Mode and mtime of opened or stat'ed files (r2 M1): **fixed for files.** For folders it causes a needless re-run on
  every build (M1 below).
- os.access wrapped (r2 M1): **fixed.**
- Children refused unless they are TinyTeX's (r2 M2): **incomplete.** Four routes still let a child read talk
  files without a record (H1 below). The TinyTeX test also uses a second source of truth for TeX's location (M2).
- Per-thread quiet flag (r2 M3, L3): **correct.** `threading.local` with a `getattr` default of False is right for
  threads the chapter starts. `own()` sets the flag back to False and does not restore the earlier value. That would
  be wrong if calls nested, but none do: the stat wrapper reads the flag before it calls `own`, and `realpath`
  raises none of the READ_EVENTS. The hook's own path stats (`.`, `chapters`, `chapters/__pycache__`) are no longer
  in the inputs. The probes' records show only `chapters/sizes.py` and its `.pyc`.
- Violation messages: **correct.** Each line is `error: <chapter> <what it did>`, and `dict.fromkeys` removes
  duplicate lines.

## HIGH

### H1. The spawn guard misses four ways to start a child, and each ships a stale clip
- Where: manim_presentations/pass1.py:24 (`SPAWN_EVENTS`) and :100-113 (`spawned`).
- Principle: no failure that looks like a success. The DECISIONS line says "a chapter may start only TinyTeX's
  programs (a child's reads are invisible)". That claim is false for each route below.
- Evidence: in every case below, the incremental build ran no chapter (`ran=set()`) and kept the old fingerprint.
  The cold build gave a different fingerprint. Each incremental record's inputs were only
  `['chapters/__pycache__/sizes.cpython-312.pyc', 'chapters/sizes.py']`.
  1. **TinyTeX's own programs read talk files.** Probe P2:
     `Tex(r"\input{assets/word.tex}")`. The trigger changes word.tex from `A` to `WWWWWWWWWW`. Incremental `grows` =
     `3a84abcab0`, cold `dba9f7f8ca`. The allowed latex child runs with the snapshot as its cwd, and it can read any
     talk file. This is a likely pattern for an author: a shared macros file loaded through `\input` in a
     TexTemplate preamble.
  2. **`os.fork()`** raises `os.fork`, which is not in SPAWN_EVENTS. The child inherits the guard, but its
     `note()` calls fill the child's copy of `inputs`. Probe P3 sends a child's `exists()` result back through a
     pipe. Incremental `21b843720f`, cold `3116267de4`.
  3. **`os.system`** always runs `/bin/sh`. The guard checks only the first word of the command string (:106). Probe
     P4 used `os.system(<TinyTeX kpsewhich> + " --version >/dev/null; test -e assets/flagS.txt")`. Incremental
     `21b843720f`, cold `3116267de4`. `subprocess` with `shell=True` is refused correctly, because the event's
     executable is `/bin/sh`.
  4. **multiprocessing (spawn, the macOS default)** starts the child through `_posixsubprocess.fork_exec`, which
     raises no event in SPAWN_EVENTS. I checked this directly: a hook that recorded os.system, subprocess.Popen,
     os.posix_spawn, os.exec, os.spawn and os.fork recorded nothing for `get_context("spawn").Process(...).start()`.
     The child is a new interpreter with no hook at all. Probe P5 used
     `Process(target=posix.stat, args=(assets/flagM.txt,))` and read its `exitcode`. Incremental `21b843720f`,
     cold `3116267de4`.
- Fix:
  - Routes 1 to 3: refuse the `os.fork` and `os.forkpty` events. Treat `os.system` as `/bin/sh` and refuse it, as
    `Popen(shell=True)` already is. Stop TeX from reading talk files. One way: put `openin_any=p` in `tex_env`
    (kpathsea's paranoid mode refuses absolute paths and `..`) and run Manim's TeX with its cwd in the TeX cache
    dir. Then `\input{assets/...}` fails loudly, and the author reads the file through `talk.root` and passes the
    text in, which the guard records. Another way: pass latex `-recorder` and record the files that its `.fls`
    names.
  - Route 4: no audit event exists for this route, so wrap `_posixsubprocess.fork_exec`, the same way
    os.stat is wrapped (pass1.py:147). Both `subprocess` and `multiprocessing` start children through that one
    function on POSIX. `subprocess` can also use `os.posix_spawn`, but the guard already catches that event. The
    wrapper's executable list holds the program paths after PATH lookup. If that is not wanted, state "multiprocessing
    children" as a limit beside system fonts.

## MEDIUM

### M1. A stat'ed folder makes its chapter run pass 1 again on every build, with nothing changed
- Where: manim_presentations/build.py:250-251 (`dir {st_mode} {st_mtime_ns}`). The snapshot makes its folders with
  `mkdir` (build.py:389) inside a scratch folder that every build wipes (deck.py:102). The pass1_key docstring says
  "the snapshot keeps both", but that is true for files only: `copy2` copies a file's stat, and `mkdir` gives each
  folder a new mtime and the default mode.
- Principle: lower latency (the no-change rebuild is the main path of incremental pass 1), and single source of
  truth (the key reads a value that the build itself makes, not a value from the talk).
- Evidence (probe P1): `if (talk.root / "assets").is_dir(): ...`. The first build ran `{"sizes"}`, as it should.
  A second build with no change ran `{'sizes'}` again. Every later build will do the same.
- Effect: any chapter that calls `exists()` or `is_dir()` on a folder, which is a common guard, never reuses its
  pass 1. Also, a `chmod` on a source folder is not seen, because the mode is mkdir's.
- Fix: for a stat'ed folder, key on "dir" alone, as round 1 did. A folder's mtime changes only when its entries
  change, and a listing is already keyed by its entry names. Or copy each folder's stat into the snapshot
  (`shutil.copystat`, applied after its files are copied). The first is simpler and keeps no value the build makes.
  Add the no-change rebuild assertion to `test_a_mode_change_is_an_input`, or a folder case to the existence test.

### M2. The guard finds TinyTeX in one place and PATH finds it in another, so a copied engine refuses Manim's own TeX
- Where: pass1.py:47 (`self.tinytex = realpath(tinytex)`, the engine's `.tinytex` folder) against build.py:436
  (PATH comes from `.tinytex/bin-path`, an absolute path that setup.sh:43 writes).
- Principle: single source of truth. Two values say where TeX is, and the guard compares one with the other.
- Evidence (probe P0): the clone made by this review's own setup (`cp -cR ~/work/.../.tinytex`, as the r2 and r3
  briefs say) keeps a bin-path that points into ~/work. A new Tex string failed:
  `error: chapters/text.py started /Users/minh/work/manim-presentations-UI-and-harness/.tinytex/TinyTeX/bin/universal-darwin/pdftex; a talk may not start other programs`.
  Before round 2, the same clone built. The error blames the talk for a fault in the engine's install.
- Fix: allow the realpath of the folder that bin-path names, which is the same value that goes into PATH. Pass that
  folder to pass 1 in place of `tinytex()`. Or make setup.sh write a bin-path relative to `.tinytex`.

## LOW

### L1. Dead and wrong argument parsing in `spawned`
- Where: pass1.py:104 and :107-108.
- Principle: no dead branches, and route on the exact mark.
- Evidence (CPython 3.12 source): on POSIX, `subprocess._execute_child` sets `executable = args[0]` before it raises
  `subprocess.Popen`, so `args[0] or (...)` never takes its right-hand side. `os.spawn` is raised only by the
  Windows C implementation, with arguments `(mode, path, argv, env)`. There `args[0]` is the int mode and
  `os.fsdecode` would raise TypeError. On macOS, `os.spawnv` is Python code (`<frozen os>`, checked) that forks and
  then raises `os.exec` in the child. The child is refused there and exits 127, so the parent records no violation
  and gets exit status 127 back.
- Fix: `command = args[0]` for Popen. Drop `os.spawn` from SPAWN_EVENTS. Refusing `os.fork` (H1) also turns the
  silent 127 from `os.spawnv` into a violation in the parent.

## Checked and found sound
- The spawn guard does not refuse anything that Manim needs when bin-path matches the repo. Once the clone's
  bin-path pointed at its own TinyTeX, every probe compiled Tex through pdftex (P2 included). Manim's only calls are
  `subprocess.run` of latex and dvisvgm (manim/utils/tex_file_writing.py:214, :254).
- The mtime of a file in the key: copy2 keeps it exactly, so a no-change rebuild reuses the record
  (`test_a_rebuild_runs_no_chapter`). A `touch` or a save with the same bytes now runs that chapter's pass 1 again.
  That is the stated cost of keying what a stat shows. The clips are still reused by their fingerprints.
- The RECORD key reads every distribution once per build, sorted by name.

## Mutants (the new tests can fail)
- M1: `os.access` left unwrapped. `test_an_access_check_is_an_input` failed.
- M2: `shown = ""` (no mode or mtime). `test_a_mode_change_is_an_input` failed.
- M3: `if False:` in place of the TinyTeX check. `test_a_chapter_may_not_start_other_programs` failed.
- I restored each mutant with `git checkout -- .`. Baseline: test_pass1_reuse.py gave `14 passed in 41.54s`.

## Count
HIGH 1 · MEDIUM 2 · LOW 1
