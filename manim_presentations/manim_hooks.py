"""Every touch of Manim internals outside clip.py. None of it is fingerprinted: it decides what pass 1 records and
checks, never a clip's pixels (tee verification catches any change that would).

Manim touches here (each tested one to one in tests/unit/test_hooks.py):
- creation lines: `Mobject.__init__` and `Mobject.copy` record the chapter line that made each object;
- end-state projection: `camera.transform_points_pre_display` and `camera.frame_center`;
- the animation counter: `renderer.num_plays`;
- exact fast-forward: `renderer.update_skipping_status` and, for plays before `from_animation_number` only, the IO
  calls `camera.capture_mobjects`, `camera.reset`, `camera.set_frame_to_background`, `renderer.get_frame`,
  `file_writer.add_partial_movie_file`, `begin_animation`, `end_animation` and `write_frame`;
- the partial-file mapping: `file_writer.partial_movie_files`, one entry per play (None for skipped ones)."""

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


def exact_fast_forward(scene: Any) -> None:
    """Plays before `from_animation_number` run Manim's own `play_internal` unmodified (per-frame `update_to_time`,
    time advanced where frames are added, `stop_condition`, the closing `update_mobjects(0)`, frozen-wait arithmetic)
    with every draw and write suppressed, so a chunk starts from exactly pass 1's scene state, call for call. Manim's
    skip mode would collapse each play to one `update_to_time(run_time)` and miss per-frame updater effects."""
    from manim import config

    r = scene.renderer
    cam, writer = r.camera, r.file_writer
    real = {
        "status": r.update_skipping_status,
        "capture": cam.capture_mobjects,
        "reset": cam.reset,
        "load": cam.set_frame_to_background,
        "get_frame": r.get_frame,
        "add": writer.add_partial_movie_file,
        "begin": writer.begin_animation,
        "end": writer.end_animation,
        "write": writer.write_frame,
    }
    forwarding = {"on": False}

    def update_skipping_status() -> None:
        forwarding["on"] = config.from_animation_number > 0 and r.num_plays < config.from_animation_number
        if forwarding["on"]:
            r.skip_animations = False
        else:
            real["status"]()

    def gated(name: str, null: Any) -> Any:
        return lambda *a, **k: null(*a, **k) if forwarding["on"] else real[name](*a, **k)

    r.update_skipping_status = update_skipping_status
    cam.capture_mobjects = gated("capture", lambda *a, **k: None)
    cam.reset = gated("reset", lambda *a, **k: cam)
    cam.set_frame_to_background = gated("load", lambda *a, **k: None)
    r.get_frame = gated("get_frame", lambda *a, **k: None)
    writer.add_partial_movie_file = gated("add", lambda *a, **k: real["add"](None))
    writer.begin_animation = gated("begin", lambda *a, **k: real["begin"](False, **k))
    writer.end_animation = gated("end", lambda *a, **k: real["end"](False))
    writer.write_frame = gated("write", lambda *a, **k: None)


def partial_files(scene: Any) -> dict[int, str]:
    """{play index: the partial file Manim wrote for it}, for the plays this process rendered."""
    return {i: p for i, p in enumerate(scene.renderer.file_writer.partial_movie_files) if p is not None}
