"""Facts the scene side records and the build side reads (pass 1's records.json). A leaf: imports nothing from the
engine. Coordinates are scene units as the camera draws them."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, TypeAdapter

BeatKind = Literal["beat", "loop"]
"""Marked at the call (`talk.beat` / `talk.loop`); a tag carried through the index, the Presenter and the export."""

Box = tuple[float, float, float, float]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Unit(_Frozen):
    """One thing drawn at a beat's end, as the geometry check sees it."""

    kind: str
    file: str  # the chapter file that made it, relative to the talk folder
    line: int  # its creation line there (an object made in a helper: the chapter line that called the helper)
    owners: tuple[int, ...]  # ids of its whole family and of the plain groups it was opened from
    attached_to: int | None  # id of what it was attached to (talk.attach)
    transient_beat: int | None  # index of the beat it was made transient in (talk.transient)
    bleed: bool  # meant to extend past the frame edge (talk.bleed)
    glyphs: tuple[Box, ...]  # letters and symbols
    markers: tuple[Box, ...]  # dots: placed on paths by intent, so they meet glyphs and dots only
    strokes: tuple[tuple[tuple[float, float], ...], ...]  # polylines, one per subpath
    fills: tuple[Box, ...]  # fill-only shapes and images (off frame only)


class Animation(_Frozen):
    """One play: its exact run time, the digest of the frames it writes, and how many it writes."""

    run_time: float
    digest: str
    frames: int


class BeatRecord(_Frozen):
    slug: str
    kind: BeatKind
    line: int  # the talk.beat/talk.loop call's line in the chapter file
    first_anim: int  # the chapter scene's play index of this beat's first animation
    animations: tuple[Animation, ...]
    end: tuple[Unit, ...]


class ChapterRecord(_Frozen):
    chapter: str
    file: str
    beats: tuple[BeatRecord, ...]
    cache_entries: tuple[str, ...]  # basenames of the TeX/text cache entries this chapter opened or created


CHAPTER_RECORD: TypeAdapter[ChapterRecord] = TypeAdapter(ChapterRecord)
