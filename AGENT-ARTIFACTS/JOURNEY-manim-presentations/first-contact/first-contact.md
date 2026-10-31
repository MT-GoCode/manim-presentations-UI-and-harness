# First contact (join)

Setup's example build succeeded: True. Answer: 181 words.

Setup worked: the example talk built in 6 s.

**What it is:** a tool for giving talks made of Manim animations.

**What you can ask:** "Make a 10-minute talk on X", "animate this algorithm", "change chapter 2", "export to HTML."

**How I'll build it:**
- Each talk is a folder in `~/manim-presentations/<name>.manim-presentation/`.
- `script.md` holds what you say, split into chapters and beats, with private `>` notes.
- `chapters/<slug>.py` holds one Manim function per chapter, with `talk.beat(...)` marking each beat.
- I sketch a storyboard first, then run `mpres build`. It checks for overlaps, things off-screen, text too small and loops that don't close. It re-renders only changed beats and checks every clip frame by frame.
- `mpres shots` gives me contact sheets so I can see the result and fix it.

**Other features:**
- `mpres present` opens a Presenter View (your script, notes, next slide, buttons) and an Audience View you share in Zoom. Arrow keys and clickers work, and you can edit the script while presenting.
- `mpres export` writes one HTML page that plays offline, with optional transcript.
