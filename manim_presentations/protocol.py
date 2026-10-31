"""The Presenter⇄Audience wire: newline-delimited JSON, one frozen model per message in a closed tagged union, decoded
once at the socket edge. Also the Position model (the Presenter owns position; the Audience only echoes it) and the
one key map the Presenter, the Audience and the exported player share. Imports nothing from the engine."""

import hashlib
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Before(_Frozen):
    """Beat 0's first frame is on screen and no animation has played."""

    kind: Literal["before"] = "before"


class At(_Frozen):
    """That beat's animation has played."""

    kind: Literal["at"] = "at"
    slug: str


Position = Annotated[Before | At, Field(discriminator="kind")]

Action = Literal["next", "previous", "replay"]

AUDIENCE_CODE = hashlib.sha256(
    Path(__file__).with_name("audience.py").read_bytes() + Path(__file__).read_bytes()
).hexdigest()
"""What an Audience does with each message. `Hello.protocol` carries the running Audience's value. When it differs
from the Presenter's own, an Audience the Presenter adopted (one that survived a `git pull`) is quit and relaunched;
one the Presenter launched itself means the engine on disk changed under it, which stops red ("restart mpres
present")."""

KEYS: dict[str, Action] = {"Up": "previous", "PageUp": "previous", "Down": "next", "PageDown": "next", "R": "replay"}
"""Qt key names (`Qt.Key.Key_<name>`) to actions. PageUp/PageDown are what presentation clickers send."""

CHORD = ("ControlModifier", "AltModifier", "MetaModifier")
"""Qt modifier names (`Qt.KeyboardModifier.<name>`): a key held with any of them is a shortcut (Cmd+R, Cmd+W), never
navigation, in the Presenter, the Audience and the exported player. Shift and the keypad flag (arrows on macOS) do not
count."""


class Moved(_Frozen):
    kind: Literal["moved"] = "moved"
    position: Position


class Boundary(_Frozen):
    """The action has nowhere to go (Next at the last beat, Previous or Replay at Before): flash red, stay."""

    kind: Literal["boundary"] = "boundary"


def step(position: Before | At, action: Action, slugs: tuple[str, ...]) -> Moved | Boundary:
    """Where an action takes the Position in a deck whose beats are `slugs` (in order)."""
    match position, action:
        case Before(), "next":
            return Moved(position=At(slug=slugs[0]))
        case Before(), "previous" | "replay":
            return Boundary()
        case At(slug=s), "next":
            i = slugs.index(s)
            return Moved(position=At(slug=slugs[i + 1])) if i + 1 < len(slugs) else Boundary()
        case At(slug=s), "previous":
            i = slugs.index(s)
            return Moved(position=At(slug=slugs[i - 1]) if i else Before())
        case At(), "replay":
            return Moved(position=position)


def before(slug: str, slugs: tuple[str, ...]) -> Before | At:
    """The Position just before beat `slug` (`--from`): the first Next then plays `slug` itself."""
    i = slugs.index(slug)
    return At(slug=slugs[i - 1]) if i else Before()


# Presenter → Audience. The position's type fixes which frame is shown, so no message stores that fact twice.
class Play(_Frozen):
    """Play once, then hold the last frame."""

    type: Literal["play"] = "play"
    position: At
    clip: str


class Loop(_Frozen):
    type: Literal["loop"] = "loop"
    position: At
    clip: str


class Cover(_Frozen):
    """Show frame 0, paused."""

    type: Literal["cover"] = "cover"
    position: Before
    clip: str


class Hold(_Frozen):
    """Show the last frame, paused."""

    type: Literal["hold"] = "hold"
    position: At
    clip: str


class Quit(_Frozen):
    type: Literal["quit"] = "quit"


ToAudience = Annotated[Play | Loop | Cover | Hold | Quit, Field(discriminator="type")]


# Audience → Presenter. `state` and `pts` are observations of what the player does; `clip` is what the Audience set.
class NowCovered(_Frozen):
    type: Literal["now-covered"] = "now-covered"
    position: Before
    clip: str


class NowAt(_Frozen):
    type: Literal["now-at"] = "now-at"
    position: At
    clip: str
    state: Literal["playing", "held", "looping"]
    pts: float


Now = Annotated[NowCovered | NowAt, Field(discriminator="type")]


class Hello(_Frozen):
    """Sent once on connect. `last` is None for a freshly launched Audience; `protocol` hashes the Audience's code."""

    type: Literal["hello"] = "hello"
    last: Now | None
    protocol: str


class Failed(_Frozen):
    type: Literal["failed"] = "failed"
    position: Position
    clip: str
    reason: str


class Fatal(_Frozen):
    """A failure not tied to a clip (for example the wrong media backend); the Audience exits after sending it."""

    type: Literal["fatal"] = "fatal"
    reason: str


class Closed(_Frozen):
    type: Literal["closed"] = "closed"


class Key(_Frozen):
    type: Literal["key"] = "key"
    action: Action


ToPresenter = Annotated[NowCovered | NowAt | Hello | Failed | Fatal | Closed | Key, Field(discriminator="type")]

_TO_AUDIENCE: TypeAdapter[Play | Loop | Cover | Hold | Quit] = TypeAdapter(ToAudience)
_TO_PRESENTER: TypeAdapter[NowCovered | NowAt | Hello | Failed | Fatal | Closed | Key] = TypeAdapter(ToPresenter)


def encode(message: _Frozen) -> bytes:
    return message.model_dump_json().encode() + b"\n"


def to_audience(line: bytes) -> Play | Loop | Cover | Hold | Quit:
    return _TO_AUDIENCE.validate_json(line)


def to_presenter(line: bytes) -> NowCovered | NowAt | Hello | Failed | Fatal | Closed | Key:
    return _TO_PRESENTER.validate_json(line)
