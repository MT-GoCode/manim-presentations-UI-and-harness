"""Peace-of-mind checks on pass-1 records (screen coordinates), at each beat's end: nothing overlaps unless attached,
nothing is off frame unless bled, and nothing made transient in the beat is still on screen. Pure functions over
records; vendored from Explainers' explainers/geometry.py.

Overlap is ink against ink, deeper than half a pixel: a glyph (letter, symbol) meets glyphs, dots and strokes; a dot
meets glyphs and dots (a dot on a line or curve is a marker placed there). Fill-only shapes never overlap anything."""

import math
from collections.abc import Sequence
from typing import Any, Literal, NamedTuple

import numpy as np

from manim_presentations.records import BeatRecord, Unit

Kind = Literal["pairing", "empty-beat", "overlap", "off-frame", "transient"]


class Finding(NamedTuple):
    """A check failure: its kind (marked where it is found, so counts per kind never parse text) and its message."""

    kind: Kind
    text: str


def _boxes(b: Any) -> np.ndarray:
    return np.asarray(b, float).reshape(-1, 4)


def _segments(strokes: Any) -> tuple[np.ndarray, np.ndarray]:
    """(starts, directions), n×2 each, of every chord of every polyline."""
    paths = [np.asarray(s, float) for s in strokes]
    if not paths:
        return np.zeros((0, 2)), np.zeros((0, 2))
    return np.concatenate([p[:-1] for p in paths]), np.concatenate([p[1:] - p[:-1] for p in paths])


def _box_hits(a: np.ndarray, b: np.ndarray, s: float) -> bool:
    """Some box of a overlaps some box of b by more than s along both axes."""
    A, B = a[:, None], b[None]
    return bool(
        (
            (A[..., 0] < B[..., 2] - s)
            & (B[..., 0] < A[..., 2] - s)
            & (A[..., 1] < B[..., 3] - s)
            & (B[..., 1] < A[..., 3] - s)
        ).any()
    )


def _segment_hits(boxes: np.ndarray, p: np.ndarray, d: np.ndarray, s: float) -> bool:
    """Some segment p + t·d (t in [0, 1]) passes through some box shrunk by s (Liang–Barsky clip)."""
    if not len(boxes) or not len(p):
        return False
    lo, hi = boxes[:, None, :2] + s, boxes[:, None, 2:] - s
    with np.errstate(divide="ignore", invalid="ignore"):
        t0, t1 = (lo - p) / d, (hi - p) / d
    flat, inside = d == 0, (lo < p) & (p < hi)  # a segment parallel to an axis is in or out along it everywhere
    enter = np.where(flat, np.where(inside, -np.inf, np.inf), np.minimum(t0, t1)).max(axis=2).clip(min=0)
    leave = np.where(flat, np.where(inside, np.inf, -np.inf), np.maximum(t0, t1)).min(axis=2).clip(max=1)
    return bool((enter < leave).any())


def _move(pairs: list[tuple[np.ndarray, np.ndarray]], s: float) -> tuple[float, float]:
    """The smallest shift, along one axis and on the 0.01 grid, after which no box of `mine` overlaps any of `theirs`
    by more than s, for every (mine, theirs) pair at once. Along x: the shifts that still overlap are open intervals,
    one per box pair that overlaps in y; the answer is the nearest grid point beside an interval end in none of them."""
    best = []
    for axis in (0, 1):
        o, lo, hi = 1 - axis, [], []
        for mine, theirs in pairs:
            A, B = mine[:, None], theirs[None]
            across = (A[..., o] < B[..., o + 2] - s) & (B[..., o] < A[..., o + 2] - s)
            lo.append((B[..., axis] + s - A[..., axis + 2])[across])
            hi.append((B[..., axis + 2] - s - A[..., axis])[across])
        lo, hi = np.concatenate(lo), np.concatenate(hi)
        ends = np.concatenate([lo, hi])
        grid = np.unique(np.concatenate([np.floor(ends * 100), np.ceil(ends * 100)]) / 100)
        free = grid[~((lo[None] < grid[:, None]) & (grid[:, None] < hi[None])).any(axis=1)]
        d = float(free[np.argmin(np.abs(free) + (free < 0) * 1e-9)])  # ties: the positive way
        best.append((abs(d), axis, d))
    _, axis, d = min(best)
    return (d, 0.0) if axis == 0 else (0.0, d)


def _overlap(x: Unit, y: Unit, s: float) -> tuple[float, float] | None:
    """How to move x clear of y, if x's ink meets y's."""
    g, m = _boxes(x.glyphs), _boxes(x.markers)
    solid = np.concatenate([_boxes(y.glyphs), _boxes(y.markers)])
    p, d = _segments(y.strokes)
    hit = _box_hits(np.concatenate([g, m]), solid, s) or _segment_hits(g, p, d, s)
    if not hit:
        return None
    # The move must clear every pair the rule checks, both ways (x's own strokes must not land on y's glyphs either).
    return _move(
        [(g, np.concatenate([solid, _chords(y.strokes)])), (m, solid), (_chords(x.strokes), _boxes(y.glyphs))], s
    )


def _chords(strokes: Any) -> np.ndarray:
    """Each chord's bounding box: never smaller than the chord, so a move that clears it clears the chord."""
    p, d = _segments(strokes)
    return np.column_stack([np.minimum(p, p + d), np.maximum(p, p + d)])


def _ink(u: Unit) -> np.ndarray:
    return np.concatenate(
        [_boxes(u.glyphs), _boxes(u.markers), _boxes(u.fills)] + [np.hstack([q, q]) for q in map(np.asarray, u.strokes)]
    )


def _named(u: Unit, ink: np.ndarray) -> str:
    x, y = (round((ink[:, i].min() + ink[:, i + 2].max()) / 2, 2) + 0.0 for i in (0, 1))  # + 0.0: no "-0.00"
    return f"{u.kind} at ({x:.2f}, {y:.2f})"


def check(beats: Sequence[BeatRecord], frame_width: float, frame_height: float, pixel_width: int) -> list[Finding]:
    """Every geometry error at every beat end, each naming `file:line` and the move that clears it."""
    errs: list[Finding] = []
    fx, fy = frame_width / 2, frame_height / 2
    s = frame_width / pixel_width / 2  # under half a pixel of ink is not drawn: neither overlap nor off frame
    for n, beat in enumerate(beats):
        units = beat.end
        inks = [_ink(u) for u in units]
        name = [_named(u, i) for u, i in zip(units, inks, strict=True)]
        for k, a in enumerate(units):
            for j in range(k + 1, len(units)):
                b = units[j]
                if a.attached_to in b.owners or b.attached_to in a.owners:
                    continue
                for (x, nx), (y, ny) in (((a, name[k]), (b, name[j])), ((b, name[j]), (a, name[k]))):
                    move = _overlap(x, y, s)
                    if move:
                        errs.append(
                            Finding(
                                "overlap",
                                f"{beat.slug} · {x.file}:{x.line} · {nx} × {ny} ({y.file}:{y.line}) · "
                                f"move {x.kind} by ({move[0]:+.2f}, {move[1]:+.2f})",
                            )
                        )
                        break
        for u, ink, nu in zip(units, inks, name, strict=True):
            over = {
                "right": ink[:, 2].max() - fx,
                "left": -fx - ink[:, 0].min(),
                "top": ink[:, 3].max() - fy,
                "bottom": -fy - ink[:, 1].min(),
            }
            edge = max(over, key=lambda e: over[e])
            if over[edge] > s and not u.bleed:
                errs.append(
                    Finding(
                        "off-frame",
                        f"{beat.slug} · {u.file}:{u.line} · {nu} is off frame by "  # moving in clears it
                        f"{math.ceil((over[edge] - s) * 100) / 100:.2f} ({edge}); move it in, or talk.bleed() it",
                    )
                )
            if u.transient_beat == n:
                errs.append(
                    Finding(
                        "transient",
                        f"{beat.slug} · {u.file}:{u.line} · {nu} was made transient in this beat and "
                        "is still on screen at its end",
                    )
                )
    return errs
