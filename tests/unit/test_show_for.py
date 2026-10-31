"""What the Presenter sends for each Position, beat kind and way of arriving, and what each message settles to."""

from pathlib import Path

import pytest

from manim_presentations import protocol as p
from manim_presentations.deck import BuiltBeat
from manim_presentations.presenter import held, show_for


def beat(kind):
    return BuiltBeat("c", "s", None, kind, Path("/c.mp4"), Path("/f.png"), Path("/l.png"), 30)


AT, BEFORE, CLIP = p.At(slug="s"), p.Before(), "/c.mp4"


@pytest.mark.parametrize(
    "position,kind,how,sent",
    [
        (BEFORE, "beat", "show", p.Cover(position=BEFORE, clip=CLIP)),
        (BEFORE, "loop", "show", p.Cover(position=BEFORE, clip=CLIP)),  # Before is beat 0's first frame, either kind
        (BEFORE, "beat", "play", p.Cover(position=BEFORE, clip=CLIP)),
        (BEFORE, "loop", "play", p.Cover(position=BEFORE, clip=CLIP)),
        (AT, "beat", "play", p.Play(position=AT, clip=CLIP)),
        (AT, "beat", "show", p.Hold(position=AT, clip=CLIP)),
        (AT, "loop", "play", p.Loop(position=AT, clip=CLIP)),
        (AT, "loop", "show", p.Loop(position=AT, clip=CLIP)),  # a loop beat seen again is running, never frozen
    ],
)
def test_show_for(position, kind, how, sent):
    assert show_for(position, beat(kind), how) == sent


@pytest.mark.parametrize(
    "sent,settled",
    [
        (p.Play(position=AT, clip=CLIP), p.Hold(position=AT, clip=CLIP)),
        (p.Hold(position=AT, clip=CLIP), p.Hold(position=AT, clip=CLIP)),
        (p.Loop(position=AT, clip=CLIP), p.Loop(position=AT, clip=CLIP)),
        (p.Cover(position=BEFORE, clip=CLIP), p.Cover(position=BEFORE, clip=CLIP)),
    ],
)
def test_held(sent, settled):
    assert held(sent) == settled
