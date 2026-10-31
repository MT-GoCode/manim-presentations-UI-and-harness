"""Every touch of Manim internals outside clip.py. None of it is fingerprinted: it decides what pass 1 records and
checks, never a clip's pixels (tee verification catches any change that would).

Manim touches here (each tested one to one in tests/unit/test_hooks.py):
- creation lines: `Mobject.__init__` and `Mobject.copy` record the chapter line that made each object;
- end-state projection: `camera.transform_points_pre_display` and `camera.frame_center`;
- the animation counter: `renderer.num_plays`;
- exact fast-forward: `renderer.update_skipping_status` and, for plays before `from_animation_number` only, the IO
  calls `camera.capture_mobjects`, `camera.reset`, `camera.set_frame_to_background`, `renderer.get_frame`,
  `file_writer.add_partial_movie_file`, `begin_animation`, `end_animation` and `write_frame`;
- the partial-file mapping: `file_writer.partial_movie_files`, one entry per play (None for skipped ones);
- the loop-closure capture points: `renderer.render` (a play's first frame, after `update_to_time(0)`) and
  `renderer.freeze_current_frame` (a frozen wait's frame); the canonical raster draws the scene's mobjects and
  foreground on a fresh, unpatched `Camera` in one `capture_mobjects` call;
- the size references: `Paragraph.__init__` (its Text lives off the scene family, in `lines_text`), and the
  observation-only shadow on `Transform.clean_up_from_scene` (FadeTransform overrides it and restores its source)
  and `Mobject.become`: the text classes' own `initial_height`, `font_size`, `height` and `submobjects` are read,
  never written."""

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


def on_first_frame(scene: Any, callback: Any) -> None:
    """Call `callback()` once per play, at exactly what the play's frame 0 shows: before the first
    `renderer.render(scene, t=0, …)` (after `update_to_time(0)` ran animation and scene updaters), or, in a frozen
    wait, at `freeze_current_frame` (its `update_frame` before it only draws)."""
    r = scene.renderer
    render, freeze = r.render, r.freeze_current_frame
    seen = {"play": -1}

    def first() -> None:
        if seen["play"] != r.num_plays:
            seen["play"] = r.num_plays
            callback()

    def render_first(sc: Any, t: float, moving: Any = None) -> None:
        first()
        render(sc, t, moving)

    def freeze_first(duration: float) -> None:
        first()
        freeze(duration)

    r.render = render_first
    r.freeze_current_frame = freeze_first


def canonical_raster(scene: Any) -> np.ndarray:
    """The scene's current state drawn whole on a fresh camera (the Recorder never involved). One call draws in
    Manim's frame order: a play's static/moving split is a prefix/suffix of the z-sorted family list, and
    capture_mobjects z-sorts each call. Only mobjects in the scene are drawn: a remover's clean-up takes its mobject
    out of the scene but not out of the play's lists."""
    from manim.camera.camera import Camera

    camera = Camera()
    camera.reset()
    camera.capture_mobjects([*scene.mobjects, *(m for m in scene.foreground_mobjects if m not in scene.mobjects)])
    return camera.pixel_array.copy()


SIZED = ("Text", "MarkupText", "Paragraph", "SingleStringMathTex", "DecimalNumber", "Typst")


def sized(m: Mobject) -> bool:
    """A mobject whose declared size the min-text check reads: Manim derives its font_size from its height."""
    return any(c.__name__ in SIZED for c in type(m).__mro__)


class Mismatch:
    """A node's size reference after a Transform or become paired it with a node of the other kind (size-checked or
    not): unknown."""


Ref = tuple[float, float] | Mismatch


def size_ref(m: Mobject) -> Ref:
    """(reference height, the font size at that height). Manim's own: (initial_height, font_size · initial_height /
    height), the size it was created at; or what the latest Transform or become left on it."""
    for ref in (getattr(m, "_mpres_ref", None), getattr(m, "_mpres_paragraph_ref", None)):
        if ref is not None:
            return ref
    initial, size = getattr(m, "initial_height"), getattr(m, "font_size")  # noqa: B009 — text-class attributes
    return initial, size * initial / m.height


def mismatched(m: Mobject) -> bool:
    return isinstance(getattr(m, "_mpres_ref", None), Mismatch)  # isinstance: Mobject.copy deep-copies the marker


def font_size(m: Mobject) -> float:
    """The declared size now: the reference size scaled by how much the mobject grew since (later scale() calls stay
    reflected)."""
    ref = size_ref(m)
    assert not isinstance(ref, Mismatch), "a mismatched node has no declared size"
    height, size = ref
    return size * m.height / height


def install_size_references() -> None:
    """Pass 1 only. Record Paragraph's reference at creation; after a Transform, whose source ends holding the
    target's points (Transform, .animate, ClockwiseTransform, CyclicReplace, ApplyFunction, ReplacementTransform), and
    after become, give each node of the source the reference of the target node whose points it took: Manim's own
    pairing, by index over the two aligned families. A size-checked node paired with one that is not (a Text that now
    draws a square, a Square that now draws glyphs) is marked for the check to report."""
    from manim import Paragraph, Transform

    paragraph_init = Paragraph.__init__

    def recording_paragraph(self: Any, *a: Any, **k: Any) -> None:
        paragraph_init(self, *a, **k)
        setattr(self, "_mpres_paragraph_ref", (self.height, self.lines_text.font_size))

    def ref(x: Mobject, t: Mobject) -> Ref | None:
        return Mismatch() if sized(x) != sized(t) else size_ref(t) if sized(t) else None

    def take(source: Mobject, aligned_target: Mobject) -> None:
        """Every node's one fact is rewritten, so the latest take wins."""
        pairs = list(zip(source.get_family(), aligned_target.get_family(), strict=True))
        refs = [ref(x, t) for x, t in pairs]  # read first: source and target may share nodes
        for (x, _), r in zip(pairs, refs, strict=True):
            setattr(x, "_mpres_ref", r)

    clean_up = Transform.clean_up_from_scene

    def shadowing_clean_up(self: Any, scene: Any) -> None:
        clean_up(self, scene)
        take(self.mobject, self.target_copy)  # off screen too: a replaced source shown again holds the target

    def align_structure(a: Mobject, b: Mobject) -> None:
        """align_data's family alignment without its point alignment, which would rewrite a's points."""
        a.null_point_align(b)
        a.align_submobjects(b)
        for x, y in zip(a.submobjects, b.submobjects, strict=True):
            align_structure(x, y)

    become = Mobject.become

    def shadowing_become(self: Mobject, mobject: Mobject, *a: Any, **k: Any) -> Mobject:
        # With no keyword, become aligns `mobject` itself, so it already pairs with self. With one, become aligns a
        # private copy: align our own copy the same way (keywords only move points, never the family structure).
        # The copy costs ~35× a bare become (6 ms for a line of Text), so it is made only when needed.
        target = mobject.copy() if a or k else mobject
        out = become(self, mobject, *a, **k)
        align_structure(self, target)
        take(self, target)
        return out

    setattr(Paragraph, "__init__", recording_paragraph)
    setattr(Transform, "clean_up_from_scene", shadowing_clean_up)
    setattr(Mobject, "become", shadowing_become)
