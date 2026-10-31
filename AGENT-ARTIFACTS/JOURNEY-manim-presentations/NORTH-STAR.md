# NORTH STAR — manim-presentations-UI-and-harness

Plan of record: `conversation-contexts/mixing-deluxe-presentation/manim-cleanup-opus-plan.md` rev 30-o (the PLAN).
Goal (Minh, verbatim in irreproachable): deliver the PLAN completely, no omissions except where reasonable from discoveries.

★ = SHINY; these decide done.

- ★ N1 Shareable, principled, not slop: code-principles.md is law; CI green (ruff, format, pyright, whole suite) on every push; player reaches into no library; every Manim touch listed and tested one to one.
- ★ N2 Parallel, incremental, verified build ("EXTREMELY STRONG CODE"): 75% of free CPU+RAM by default, `--workers N` override; only changed frames re-render; every committed clip verified digest-for-digest against pass 1 and stream-checked; build-time checks (overlap, off-frame, min text, loop closure, pairing).
- ★ N3 Presenter View + Audience View: two windows; big ↑ Previous / ↓ Next / R Replay buttons that pop; description boxes gone; transcript editable live, saved to script.md.
- ★ N4 Agent-first: AGENT-INSTRUCTIONS.md (Setup / How to use / How to make good slides); talks in the plain local folder ~/manim-presentations (never in the engine repo; not a git repo); path-based CLI; `mpres shots` dumps first/middle/last of every click to /tmp; the clone + `claude "…"` first-contact prompt answers correctly in <150 words.
- N5 `mpres export` → one self-contained offline HTML; loops loop; transcript optional.
- Non-goal: Mixing Deluxe is DONE — migrate in one agent-hour, never polish.
