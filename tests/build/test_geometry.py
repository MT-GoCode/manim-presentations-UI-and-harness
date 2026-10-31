"""The geometry check through `mpres build`, on Explainers' vendored geometry fixture: every beat expects exactly
its messages (none for the cases that must pass; those are the beats not named below)."""

from conftest import TEST_WORKERS_WIDE, mpres

EXPECTED = [
    "dot-on-dot · chapters/geometry.py:44 · Dot at (0.00, 0.00) × Dot at (0.10, 0.00) (chapters/geometry.py:44) · move Dot by (-0.06, +0.00)",
    "text-on-text · chapters/geometry.py:46 · Text at (0.00, 0.00) × Text at (0.30, 0.00) (chapters/geometry.py:46) · move Text by (+0.00, +0.44)",
    "text-on-an-arrow · chapters/geometry.py:53 · Text at (0.00, 0.00) × Arrow at (0.00, 0.00) (chapters/geometry.py:53) · move Text by (+0.00, +0.11)",
    "hidden-in-a-group · chapters/geometry.py:55 · Dot at (0.00, 0.00) × Dot at (0.10, 0.00) (chapters/geometry.py:55) · move Dot by (-0.06, +0.00)",
    "off-frame-right · chapters/geometry.py:57 · Square at (8.00, 0.00) is off frame by 0.50 (right); move it in, or talk.bleed() it",
    "off-frame-left · chapters/geometry.py:58 · Square at (-8.00, 0.00) is off frame by 0.50 (left); move it in, or talk.bleed() it",
    "off-frame-top · chapters/geometry.py:59 · Square at (0.00, 4.00) is off frame by 0.50 (top); move it in, or talk.bleed() it",
    "off-frame-fill · chapters/geometry.py:60 · Square at (0.00, -4.00) is off frame by 0.50 (bottom); move it in, or talk.bleed() it",
    "off-frame-image · chapters/geometry.py:61 · ImageMobject at (8.00, 0.00) is off frame by 0.50 (right); move it in, or talk.bleed() it",
    "leftover-transient · chapters/geometry.py:65 · Circle at (0.00, 0.00) was made transient in this beat and is still on screen at its end",
    "leftover-transient-group · chapters/geometry.py:68 · Circle at (0.00, 0.00) was made transient in this beat and is still on screen at its end",
    "leftover-transient-group · chapters/geometry.py:68 · Square at (0.00, 0.00) was made transient in this beat and is still on screen at its end",
    "number-line-under-text · chapters/geometry.py:161 · NumberLine at (-0.14, -0.22) × Text at (1.00, -0.30) (chapters/geometry.py:162) · move NumberLine by (+0.00, +0.30)",
]


def test_every_case_gets_exactly_its_messages(talk):
    r = mpres("build", str(talk("geometry")), "--workers", str(TEST_WORKERS_WIDE))
    assert r.returncode == 1, r.stdout + r.stderr
    got = [line.removeprefix("error: ") for line in r.stderr.splitlines() if line.startswith("error: ")]
    assert got == EXPECTED
    assert r.stderr.splitlines()[-1] == "checks failed: off-frame 5 · overlap 5 · transient 3"
