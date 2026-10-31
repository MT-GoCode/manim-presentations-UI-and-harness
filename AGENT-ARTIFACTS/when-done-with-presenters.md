# When done with presenters

Minh's request (2026-10-31), to start only after the current irreproachable goal (deliver manim-cleanup-opus-plan.md
rev 30) is done and cleared. His words are kept as close to verbatim as possible.

## 0. First, close out this journey properly

- Make sure the strata and the plan are completely up to date: JOURNEY-manim-presentations/STRATA.md, DECISIONS,
  DEBT, and the plan, against what was actually built and decided.

## 1. Then register a second irreproachable goal: strata-explainers-upgrade

- Look at the `~/code/explainers` repo that originally motivated all this. Understand it. Then find all the ways to
  upgrade it, based on everything done here.
- Go straight to strata: make a `strata-explainers-upgrade` (a JOURNEY with STRATA.md; no blueprints needed first).
- **North star:** upgrade Explainers, especially on the Manim side and the robust-building side. Things done here
  that Explainers could do better at: rendering, the build, how much to chunk the build, the 75%-of-headroom width.
- **Keep in mind:** Explainers has a different structure, its animation scaffold is different, and it has other
  requirements, such as no overlapping.
- **Not wanted:** a utility to image-dump (no `mpres shots` equivalent).
- **GitHub:** make sure it is up on GitHub if it is not already, under a name like
  `manim-interactive-explainer-UI-and-harness`.
- **Do not commonize between repos.** Vendor the same code into each instead.
- **Do not worry about preserving the current lessons.**

## 2. One small utility to add (separate from the Manim upgrades)

- A word-count checker **bash script** for agents. It takes the number of words to compare against, and prints which
  cells (each `cells.md`) are over the limit.
- **Counting is code- and math-aware:** math terms and code count too.
- **Honest about failures:** any cell it could not process is reported as such, not skipped silently.
- **Try it** on the real cells.

## 3. Process

- Plan the strata, then review them adversarially to check they are good, principled strata and whether anything is
  missing. Repeat until only LOWs remain. Then execute.
