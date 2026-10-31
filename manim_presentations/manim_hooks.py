"""Every touch of Manim internals outside clip.py. None of it is fingerprinted: it decides what pass 1 records and
checks, never a clip's pixels (tee verification catches any change that would).

Manim touches here (each tested one to one in tests/unit/test_hooks.py):
- creation lines: `Mobject.__init__` and `Mobject.copy` record the chapter line that made each object;
- end-state projection: `camera.transform_points_pre_display` and `camera.frame_center`;
- the animation counter: `renderer.num_plays`."""

import sys
from pathlib import Path
from typing import Any

import numpy as np
from manim import Mobject


def chapter_line(chapter_files: frozenset[str]) -> tuple[str, int] | None:
    """(file, line) of the innermost stack frame in a chapter file: an object made inside a helper reports the
    chapter line that called the helper."""
    f = sys._getframe(1)
    while f is not None and f.f_code.co_filename not in chapter_files:
        f = f.f_back
    return (f.f_code.co_filename, f.f_lineno) if f is not None else None


def record_creation_lines(chapter_files: frozenset[str]) -> None:
    """Every mobject made while a chapter runs remembers the chapter line that made it; a copy, the line that
    copied it."""
    init, copy = Mobject.__init__, Mobject.copy

    def recording_init(m: Mobject, *a: Any, **k: Any) -> None:
        init(m, *a, **k)
        setattr(m, "_mpres_born", chapter_line(chapter_files))

    def recording_copy(m: Mobject, *a: Any, **k: Any) -> Mobject:
        c = copy(m, *a, **k)
        line = chapter_line(chapter_files)
        for x in c.get_family():
            setattr(x, "_mpres_born", line)
        return c

    setattr(Mobject, "__init__", recording_init)
    setattr(Mobject, "copy", recording_copy)


def screen(camera: Any, m: Mobject, points: np.ndarray) -> np.ndarray:
    """Points as the camera draws them, in scene units (Camera.points_to_subpixel_coords' own mapping)."""
    return (camera.transform_points_pre_display(m, points) - camera.frame_center)[:, :2]


def play_index(scene: Any) -> int:
    """The index of the next play in this scene (Manim's own counter, the one from/upto_animation_number use)."""
    return int(scene.renderer.num_plays)


def born(m: Mobject) -> tuple[str, int] | None:
    return getattr(m, "_mpres_born", None)


def chapter_path(file: str, snapshot: Path) -> str:
    """A snapshot path as the author knows it: relative to the talk folder."""
    return str(Path(file).relative_to(snapshot))
