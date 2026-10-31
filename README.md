# manim-presentations

[![CI](https://github.com/MT-GoCode/manim-presentations-UI-and-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/MT-GoCode/manim-presentations-UI-and-harness/actions/workflows/ci.yml)

The first `./setup.sh` takes a minute or more (65 s measured, plus Homebrew's time if it must install cairo; it installs TeX and builds an example). Run it detached or with a long
timeout; an agent's default command timeout is too short.

Give talks made of Manim animations. You write a `script.md` (what you say, beat by beat) and one Python file per
chapter; the engine renders every beat into a verified clip and presents them in two windows: a private **Presenter
View** (your script, notes, the next slide, big Previous / Next / Replay buttons) and an **Audience View** to share in
Zoom. Builds are incremental and parallel: change one beat and only that beat renders again.

## Quick start

```
git clone https://github.com/MT-GoCode/manim-presentations-UI-and-harness
claude "Explore ./manim-presentations-UI-and-harness, run setup, read AGENT-INSTRUCTIONS.md, and tell me what this is and how to use it. Then introduce me to the product. What I can ask, how you'll execute (write manim code, put it where, how you'll build animations, etc.), and what other features there are (HTML exports, presentation/audience view, editable script, etc.). Less than 150 words."
```

The repo is written to be driven by an agent: [AGENT-INSTRUCTIONS.md](AGENT-INSTRUCTIONS.md) is what it reads. By hand:

```
./setup.sh
cp -R examples/hello.manim-presentation ~/manim-presentations/my-talk.manim-presentation
mpres build   ~/manim-presentations/my-talk.manim-presentation
mpres shots   ~/manim-presentations/my-talk.manim-presentation
mpres present ~/manim-presentations/my-talk.manim-presentation
mpres export  ~/manim-presentations/my-talk.manim-presentation --out ~/Desktop/my-talk.html
```

## The worked example

[`examples/hello.manim-presentation`](examples/hello.manim-presentation) is a complete two-chapter talk: chapter
cards, a fixed title, a process told by motion, and a loop. Copy it to start a talk.

## What it does

- **`mpres build`** checks the talk first (overlaps, things off the frame, text too small, loops that do not close,
  `script.md` out of step with the chapters) and names the file and line of each problem, then renders only what
  changed, in parallel, and verifies every clip frame by frame. Measured cold builds: `examples/hello`
  about 7 s (5 beats at 1920×1080, an 18-core Apple M5 Pro); a 57-beat talk at 3456×2168 about 7 min (a 16-core Apple M4 Max shared with other heavy work).
- **`mpres present`** opens the Presenter View and the Audience View. Keys: ↓ ↑ R, and a clicker's PageDown/PageUp.
  You can edit the script and rebuild while presenting.
- **`mpres shots`** writes the first, middle and last frame of every beat and a contact sheet per chapter.
- **`mpres export`** writes the talk as one self-contained HTML page that plays offline. Supported browsers: Safari
  and Chrome. Firefox is untested.

macOS only. MIT licensed.
