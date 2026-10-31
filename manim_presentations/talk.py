"""The authoring API. One Manim scene per chapter: `Talk` loads `chapters/<slug>.py` by path and calls its
`construct(talk)`. Inside, `talk.beat(slug)` / `talk.loop(slug)` mark where each beat starts; `talk.attach`,
`talk.transient` and `talk.bleed` mark intent at the object. These calls only record; every check runs after the
chapter, in the build. Pass 1 runs `Pass1Talk`, which also records what is on screen at each beat's end."""

import importlib.util
import sys
from pathlib import Path
from typing import Any

import numpy as np
from manim import (
    Axes,
    DecimalNumber,
    Dot,
    Group,
    ImageMobject,
    MarkupText,
    Mobject,
    NumberPlane,
    Paragraph,
    Scene,
    SingleStringMathTex,
    Text,
    VGroup,
    VMobject,
)

from manim_presentations import manim_hooks
from manim_presentations.clip import RecordContext
from manim_presentations.records import Animation, BeatKind, BeatRecord, Box, Unit

GLYPHS = (Text, MarkupText, SingleStringMathTex, DecimalNumber, Paragraph)  # every leaf under these is a glyph
BACKGROUND = (NumberPlane, Axes)  # their lines never count for overlap
SAMPLES_PER_CURVE = 8  # chords per cubic: a 45° arc in 8 chords strays 0.0012·r from the curve, under half a pixel
#                        up to r = 3 (vendored from Explainers' lesson.py)
_T = np.linspace(0, 1, SAMPLES_PER_CURVE + 1)
_BERNSTEIN = np.stack([(1 - _T) ** 3, 3 * (1 - _T) ** 2 * _T, 3 * (1 - _T) * _T**2, _T**3], axis=1)


class TalkError(Exception):
    """An authoring error found at the call, with the chapter line."""


class _Beat:
    def __init__(self, slug: str, kind: BeatKind, line: int, first_anim: int):
        self.slug, self.line, self.first_anim = slug, line, first_anim
        self.kind: BeatKind = kind
        self.animations: list[Animation] = []
        self.end: tuple[Unit, ...] = ()

    def record(self) -> BeatRecord:
        return BeatRecord(
            slug=self.slug,
            kind=self.kind,
            line=self.line,
            first_anim=self.first_anim,
            animations=tuple(self.animations),
            end=self.end,
        )


class Talk(Scene):
    """One chapter's scene. `recorder` digests every frame the chapter writes: pass 1's RecordContext (no pixels) or
    a worker's TeeContext (pixels too); the type is chosen once, by the process that builds the scene."""

    def __init__(self, chapter: Path, root: Path, title: str, recorder: type[RecordContext], **kwargs: Any):
        super().__init__(**kwargs)
        self.chapter, self.root, self.title = chapter, root, title
        self.recorder = recorder(self)
        self.beats: list[_Beat] = []
        self._anchors: list[Mobject] = []  # everything attached to stays alive, so its id is never reused

    def _line(self) -> int:
        here = manim_hooks.chapter_line(frozenset({str(self.chapter)}))
        assert here is not None, "talk methods are called from the chapter file"
        return here[1]

    def _where(self) -> str:
        return f"{manim_hooks.chapter_path(str(self.chapter), self.root)}:{self._line()}"

    def construct(self) -> None:
        if str(self.root) not in sys.path:
            sys.path.append(str(self.root))  # helpers.* imports work; installed packages still win a name clash
        spec = importlib.util.spec_from_file_location(f"mpres_chapter_{self.chapter.stem}", self.chapter)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        construct = getattr(module, "construct", None)
        if construct is None:
            raise TalkError(f"{manim_hooks.chapter_path(str(self.chapter), self.root)} defines no construct(talk)")
        construct(self)

    def beat(self, slug: str) -> None:
        self._start(slug, "beat")

    def loop(self, slug: str) -> None:
        """A looped beat: its animations are exactly one cycle, and it must end in the state it starts in."""
        self._start(slug, "loop")

    def _start(self, slug: str, kind: BeatKind) -> None:
        if any(b.slug == slug for b in self.beats):
            raise TalkError(f'{self._where()}: beat "{slug}" was already started in this chapter')
        if self.beats:
            self._close()
        self.beats.append(_Beat(slug, kind, self._line(), manim_hooks.play_index(self)))

    def play(self, *args: Any, **kwargs: Any) -> None:
        if not self.beats:
            raise TalkError(
                f"{self._where()}: play or wait before the chapter's first talk.beat()/talk.loop(); "
                "start a beat first (talk.add before it is fine)"
            )
        super().play(*args, **kwargs)
        digest, frames = self.recorder.play_digest()
        # self.duration: the play's exact run time (the scene clock accumulates float error)
        self.beats[-1].animations.append(Animation(run_time=self.duration, digest=digest, frames=frames))

    def tear_down(self) -> None:
        if not self.beats:
            raise TalkError(f"{manim_hooks.chapter_path(str(self.chapter), self.root)}: no talk.beat() in the chapter")
        self._close()
        super().tear_down()

    def _close(self) -> None:
        pass

    def attach(self, child: Mobject, to: Mobject) -> Mobject:
        """Mark child (or any group holding it) as meant to sit on `to` or any part of it: they may overlap."""
        self._anchors.append(to)
        setattr(child, "_mpres_attached_to", id(to))
        return child

    def transient(self, *mobs: Mobject) -> Any:
        """Mark mobjects (cursors, highlights) that must be gone by the end of the beat they were made in."""
        if not self.beats:
            raise TalkError(f"{self._where()}: transient() before the chapter's first talk.beat()")
        for m in mobs:
            setattr(m, "_mpres_transient_beat", len(self.beats) - 1)
        return mobs[0] if len(mobs) == 1 else mobs

    def bleed(self, *mobs: Mobject) -> Any:
        """Mark mobjects meant to extend past the frame edge."""
        for m in mobs:
            setattr(m, "_mpres_bleed", True)
        return mobs[0] if len(mobs) == 1 else mobs


class Pass1Talk(Talk):
    """Pass 1 also records what is on screen at each beat's end, where the camera draws it, with its chapter line."""

    def _close(self) -> None:
        self.beats[-1].end = self._end_state()

    def _end_state(self) -> tuple[Unit, ...]:
        units: list[Unit] = []

        def visit(
            m: Mobject,
            made: tuple[str, int] | None,
            groups: list[int],
            attached: int | None,
            transient: int | None,
            bleed: bool,
        ) -> None:
            made = manim_hooks.born(m) or made
            a = getattr(m, "_mpres_attached_to", None)
            attached = a if a is not None else attached
            t = getattr(m, "_mpres_transient_beat", None)
            transient = t if t is not None else transient
            bleed = bleed or getattr(m, "_mpres_bleed", False)
            if type(m) in (VGroup, Group):  # plain groups are opened: grouping never hides anything
                for s in m.submobjects:
                    visit(s, made, [*groups, id(m)], attached, transient, bleed)
                return
            g, d, s, f = _leaves(m, self.camera)
            if not (g or d or s or f):  # draws nothing (wait() adds such a placeholder): not on screen
                return
            assert made is not None, f"{type(m).__name__} has no creation line"  # all talk code runs from a chapter
            units.append(
                Unit(
                    kind=type(m).__name__,
                    file=manim_hooks.chapter_path(made[0], self.root),
                    line=made[1],
                    owners=(*groups, *(id(x) for x in m.get_family())),
                    attached_to=attached,
                    transient_beat=transient,
                    bleed=bleed,
                    glyphs=tuple(g),
                    markers=tuple(d),
                    strokes=tuple(s),
                    fills=tuple(f),
                )
            )

        for m in self.mobjects:
            visit(m, None, [], None, None, False)
        return tuple(units)


def _box(p: np.ndarray) -> Box:
    return float(p[:, 0].min()), float(p[:, 1].min()), float(p[:, 0].max()), float(p[:, 1].max())


def _polylines(m: VMobject) -> list[np.ndarray]:
    """Each subpath's cubic curves sampled at SAMPLES_PER_CURVE chords (subpaths are never joined)."""
    out: list[np.ndarray] = []
    for sub in m.get_subpaths():
        pts = np.einsum("sk,ckd->csd", _BERNSTEIN, sub.reshape(-1, 4, 3))
        out.append(np.concatenate([pts[:, :-1].reshape(-1, 3), pts[-1, -1:]]))
    return out


Leaves = tuple[list[Box], list[Box], list[tuple[tuple[float, float], ...]], list[Box]]


def _leaves(
    m: Mobject, camera: Any, glyph: bool = False, background: bool = False, out: Leaves | None = None
) -> Leaves:
    """Children first, then the mobject's own path (an Arrow's shaft is the parent; its tip is a child)."""
    out = out if out is not None else ([], [], [], [])
    glyph = glyph or isinstance(m, GLYPHS)
    background = background or isinstance(m, BACKGROUND)
    for s in m.submobjects:
        _leaves(s, camera, glyph, background, out)
    if isinstance(m, ImageMobject):
        out[3].append(_box(manim_hooks.screen(camera, m, m.points)))
    elif isinstance(m, VMobject) and len(m.points):
        if glyph:
            out[0].append(_box(manim_hooks.screen(camera, m, m.points)))
        elif isinstance(m, Dot):
            out[1].append(_box(manim_hooks.screen(camera, m, m.points)))
        elif m.get_stroke_width() > 0 and m.get_stroke_opacity() > 0:
            if not background:
                out[2].extend(
                    tuple((float(x), float(y)) for x, y in manim_hooks.screen(camera, m, p)) for p in _polylines(m)
                )
        elif m.get_fill_opacity() > 0:
            out[3].append(_box(manim_hooks.screen(camera, m, m.points)))
    return out
