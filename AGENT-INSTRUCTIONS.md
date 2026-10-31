# AGENT-INSTRUCTIONS

You are an agent helping someone make and present talks with this engine. A talk is a folder of Manim chapters plus a
`script.md`; the engine renders it into verified video clips, presents it in two windows, screenshots it, and exports
it as one HTML page.

# Setup

- You need macOS and Homebrew.
- Run `./setup.sh` from this repo. It installs uv if it is missing, then cairo and pkg-config, a repo-local TinyTeX
  and the Python environment, and links `mpres` into `~/.local/bin`. It is safe to run again. `./setup.sh --dev` also
  checks the browsers the export tests use.
  - The first run took 65 s on an 18-core Apple M5 Pro whose Homebrew already had cairo and pkg-config; installing those adds Homebrew's own time. It prints a line per phase. **Run it detached or with a long timeout**:
    it outlasts an agent shell's default command timeout.
- Check the install with `mpres --help`. Setup checks the engine by building a throwaway copy of `examples/hello`, so
  no `build/` folder appears in the repo.
- `mpres` is exactly `uv run -q --project <repo> mpres`. When `~/.local/bin` is not on your shell's `PATH` (a shell
  that has not reloaded its rc file), use the literal form; `uv` itself is in `/opt/homebrew/bin`:

  ```
  uv run -q --project <repo> mpres build   <talk>
  uv run -q --project <repo> mpres present <talk>
  uv run -q --project <repo> mpres shots   <talk>
  uv run -q --project <repo> mpres export  <talk> --out <file>.html
  ```

  Every example below uses `mpres`.

# How to use this

## Where talks live

- Talks live in `~/manim-presentations/`. Create it if it is missing. Each `<name>.manim-presentation` folder inside
  is one talk.
- Do not put talks under `~/Documents`: iCloud may sync that folder and evict a talk's clips to the cloud. If the user
  asks for Documents, tell them why first.
- Start a talk from the worked example:
  `cp -R <repo>/examples/hello.manim-presentation ~/manim-presentations/<name>.manim-presentation`.

## What is inside a talk

```
<name>.manim-presentation/
  script.md        the talk: title, chapters, beats, and what is said
  chapters/        one <chapter-slug>.py per chapter
  helpers/         code shared by chapters (optional)
  assets/          images and data the chapters read (optional)
  talk.toml        render size and check minimums (optional)
  build/           made by `mpres build`; never edit it, never copy it
```

**`script.md`.** Line 1 is the talk's title. Then:

```
# chapter-slug: Chapter title

## beat-slug: Beat title

What you say during this beat.

> A private note: shown to you in the Presenter View, never spoken, never exported unless asked.
```

- A slug is `a-z`, `0-9` and `-`. It is the beat's identity; the title after `: ` is what people see (optional).
- Chapters and beats in `script.md` pair one to one with `chapters/<chapter-slug>.py` and the `talk.beat` calls in it.
- Editing what is said (or the notes) never triggers a render. Changing a heading does: run `mpres build`.

**A chapter** is a function, not a class:

```python
from manim import Circle, FadeIn


def construct(talk):
    talk.beat("the-idea")  # every play after this, until the next beat, is this beat
    talk.play(FadeIn(Circle()))

    talk.loop("keeps-going")  # a looped beat: exactly one cycle (see Loops)
    ...
```

- `talk` is a Manim `Scene`: use `talk.play`, `talk.add`, `talk.wait` and the rest as usual.
- Each chapter starts on an empty stage.
- The authoring calls:
  - `talk.beat(slug)` starts a beat; `talk.loop(slug)` starts a looped beat.
  - `talk.attach(child, to=parent)` marks something meant to sit on top of something else (no overlap error).
  - `talk.bleed(*mobjects)` marks things meant to extend past the frame edge.
  - `talk.transient(*mobjects)` marks things (cursors, highlights) that must be gone by the end of their beat.
  - `talk.root` is the talk folder: read assets as `talk.root / "assets" / "x.png"`. A talk never reads, lists or
    `stat`s anything outside its own folder; the build refuses it.
  - `talk.title` is the talk's title from `script.md`.
- `helpers/` is importable from chapters as `from helpers.<module> import ...`.

**`talk.toml`** is optional. Every value has a default with a stated origin. If you override a key in a table, that
table needs an `origin` saying where your numbers came from:

```toml
[render]
pixel_width = 3456
pixel_height = 2168
origin = "the presenter's Audience window, measured at 2x"
```

## Long-running commands, for agents

- `mpres build` can take minutes on a cold or large talk. Run it detached or with a long timeout, and read its phase
  lines as they come. Measured cold builds: `examples/hello` about 7 s (5 beats at 1920×1080, an 18-core Apple M5 Pro); a 57-beat talk at 3456×2168 about 7 min (a 16-core Apple M4 Max shared with other heavy work).
- `mpres present` opens two windows for a human and does not return. Launch it in the background, or ask the user to
  run it; never run it in the foreground. It prints `present: Audience connected, showing <position>` when it is up.
  Stop it with Ctrl-C or `kill <pid>`: both close both windows.

## Build

- `mpres build <talk>` is incremental: only beats whose frames changed are rendered. Editing narration never renders.
  Editing the engine re-renders only the beats whose frames change, except `clip.py`, which re-renders everything.
  After updating the engine or its dependencies, run `mpres build`: `present` keeps serving the old, verified clips
  until you do.
- Every clip is verified frame-digest for frame-digest against what was planned. A verification failure means
  nondeterminism at the line it names; see the landmines (no sets of mobjects, no clock reads).
- When a check fails, the build names the file and line, and usually the move that fixes it. The checks: overlap,
  off-frame, a transient left on screen, a beat with no animation, a loop that does not close, text below the minimum
  size, a text-size mismatch in a group transform, and `script.md` / chapter pairing. Fix the line, or use `attach`,
  `bleed` or `transient` when the thing is meant.
- By default the build uses 75% of the machine's free headroom. `--workers 2` conserves CPU (during a call, for
  example). That is the whole of "optimized": incremental and parallel by default; there is no draft mode.
- If you move this repo, `~/.local/bin/mpres` becomes a dangling link ("no such file or directory"). Run `./setup.sh`
  again from the new location.

## Loops

- `talk.loop(slug)` makes exactly one cycle, and it must end exactly in the state it starts in. The build checks it
  pixel for pixel.
- Keep cycles short: Next jumps out of a loop immediately.

## Look at your work

- `mpres shots <talk>` writes the first, middle and last frame of every beat, plus one contact sheet per chapter, to a
  folder it prints. Read the contact sheets.

## Present

- `mpres present <talk>` opens the Presenter View and the Audience View. `--from <beat-slug>` starts just before that
  beat.
- Keys: ↓ Next, ↑ Previous, R Replay. A presentation clicker's PageDown/PageUp work too.
- In Zoom, share the **Audience View** window. If that is not possible, share a portion of the screen.
- The user can edit the script in the Presenter View while presenting, and you can run `mpres build` while they
  present: both windows pick up the new build without restarting.
- If `present` refuses because the talk changed since its build, run `mpres build` first.

## Export

- `mpres export <talk> --out ~/Desktop/<name>.html` writes one self-contained page that plays offline in Safari and
  Chrome (Firefox is untested).
- `--transcript none` (the default) shows titles only; `narration` adds what is said; `full` also adds the private
  `>` notes. Ask the user before exporting notes.
- `--height` and `--crf` override the measured video size and quality, which the command prints.

## Agent workflow

1. Write a storyboard in `/tmp/`: the chapters, the beats, what moves in each.
2. Write `script.md` and the chapters.
3. Run `mpres build`, and fix each error at the line it names.
4. Run `mpres shots` and look at the contact sheets.
5. Iterate.

Optionally, ask a fresh subagent to critique the storyboard against the heuristics below.

If the engine misbehaves, stop and tell the user. Never patch the engine from inside a talk.

# How to make good slides

- **Motion carries information.** Things move, split, merge and transform to show a process. Never animate the
  drawing of a flowchart.
- **Fixed titles.** A title stays in one place and does not change through a chapter. The audience is half
  attending; a fixed title grounds them.
- **Chapter boundaries.** Each chapter opens on a black card with its title. Something that recurs (a counter, a
  badge) is re-created at the start of the next chapter, from a shared helper, in the same place, so it reads as
  surviving the cut.
- **Continuity within a chapter.** Every beat starts from the last frame; nothing pops in from nowhere.
- **One change at a time.** The eye goes to what just moved. Fade out what is finished.
- **Use the stage.** Big geometry, the whole 16:9 stage, a grid, even spacing.
- **Words go in `script.md`.** On screen, only labels, numbers and short phrases.
- **Quiet visuals.** One accent colour means "look here", and each colour keeps one meaning for the whole talk.
- **Loops** show "keeps happening". A change of state is its own beat, placed before the loop.
- **Threads.** A counter or badge that recurs across chapters ties them together.

## Manim landmines

- **Transform padding.** Transforming between mobjects with different numbers of parts pads the smaller one; the
  extra parts appear from nowhere. Match the parts, or use `ReplacementTransform`.
- **`from manim import *` shadows names** (`Line`, `Text`, `config`, ...). Import what you use.
- **TeX parts.** Split `MathTex` into the parts you will transform: `MathTex("a", "+", "b")`.
- **Size text at creation.** Use `font_size=`, not `.scale()` afterwards; the minimum-size check reads the declared
  size.
- **f-string braces.** In `MathTex(f"...")`, TeX braces must be doubled: `{{` and `}}`.
- **No per-frame Text.** Creating `Text` inside an updater re-renders text every frame. Use `DecimalNumber` or a
  prebuilt set.
- **Deep copies.** `.copy()` copies updaters and submobjects; clear what you do not want.
- **`self.mobjects`** lists only top-level mobjects, not their parts.
- **Write vs Create.** `Write` for text, `Create` for shapes.
- **`Group` for images.** `VGroup` cannot hold an `ImageMobject`.
- **Leave `config` alone.** `talk.toml` owns the render settings.
- **Fonts** must be installed on the system; font files inside a talk are not supported.
- **No sets of mobjects and no clock reads.** Sets are ordered by `id`, which changes between processes, and clock
  reads change every run; both break verification.
- **Group transforms between text and shapes.** When a `Transform` between two groups pairs a text object with a
  shape, the build cannot know the text's size and says so: use `ReplacementTransform`.
- **Files outside the talk.** A talk reads only files inside its own folder; copy anything else into `assets/` first.
- **Large inputs** to a generator script stay outside the talk; only its small output goes into `assets/`, because
  every file in a talk is snapshotted and hashed on every build.
- **Dependencies.** Talks use only the engine's Python dependencies.
