import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from manim_presentations import protocol as p

TABLE = json.loads((Path(__file__).parents[1] / "position_table.json").read_text())
SLUGS = tuple(TABLE["slugs"])


def _position(raw: dict) -> p.Before | p.At:
    return p.Before() if raw["kind"] == "before" else p.At(slug=raw["slug"])


@pytest.mark.parametrize("case", TABLE["steps"], ids=lambda c: f"{c['from']}-{c['action']}")
def test_step_table(case):
    got = p.step(_position(case["from"]), case["action"], SLUGS)
    want = p.Boundary() if case["to"] == "boundary" else p.Moved(position=_position(case["to"]))
    assert got == want


@pytest.mark.parametrize("case", TABLE["from_flag"], ids=lambda c: c["slug"])
def test_from_flag_lands_just_before(case):
    assert p.before(case["slug"], SLUGS) == _position(case["to"])


TO_AUDIENCE = [
    p.Play(position=p.At(slug="a"), clip="clips/1.mp4"),
    p.Loop(position=p.At(slug="a"), clip="clips/1.mp4"),
    p.Cover(position=p.Before(), clip="clips/0.mp4"),
    p.Hold(position=p.At(slug="b"), clip="clips/2.mp4"),
    p.Quit(),
]
TO_PRESENTER = [
    p.Hello(last=None, protocol="abc"),
    p.Hello(last=p.NowAt(position=p.At(slug="a"), clip="c", state="held", pts=2.5), protocol="abc"),
    p.Hello(last=p.NowCovered(position=p.Before(), clip="c"), protocol="abc"),
    p.NowAt(position=p.At(slug="a"), clip="c", state="looping", pts=0.0),
    p.Failed(position=p.Before(), clip="c", reason="no such file"),
    p.Fatal(reason="media backend ffmpeg loaded, darwin required"),
    p.Closed(),
    p.Key(action="replay"),
]


@pytest.mark.parametrize("message", TO_AUDIENCE, ids=lambda m: type(m).__name__)
def test_to_audience_round_trip(message):
    line = p.encode(message)
    assert line.endswith(b"\n") and line.count(b"\n") == 1
    assert p.to_audience(line) == message


@pytest.mark.parametrize("message", TO_PRESENTER, ids=lambda m: type(m).__name__)
def test_to_presenter_round_trip(message):
    assert p.to_presenter(p.encode(message)) == message


def test_position_is_tagged_json():
    assert json.loads(p.encode(p.Hold(position=p.At(slug="x"), clip="c"))) == {
        "type": "hold",
        "position": {"kind": "at", "slug": "x"},
        "clip": "c",
    }


@pytest.mark.parametrize(
    "line",
    [
        b'{"type": "seek", "clip": "c"}\n',  # unknown tag
        b'{"type": "play", "position": {"kind": "before"}, "clip": "c"}\n',  # Play needs At
        b'{"type": "quit", "extra": 1}\n',  # extra field
    ],
)
def test_bad_lines_are_rejected_at_the_edge(line):
    with pytest.raises(ValidationError):
        p.to_audience(line)


def test_messages_from_one_direction_do_not_decode_in_the_other():
    with pytest.raises(ValidationError):
        p.to_presenter(p.encode(p.Quit()))
    with pytest.raises(ValidationError):
        p.to_audience(p.encode(p.Closed()))
