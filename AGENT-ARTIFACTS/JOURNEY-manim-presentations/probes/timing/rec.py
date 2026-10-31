"""Throwaway: P7's RecordContext / TeeContext / exact_fast_forward, shared by the timing probes."""
import hashlib
import cairo
import numpy as np
from manim import config

def _sha(*parts: bytes) -> bytes:
    return hashlib.sha256(b"".join(parts)).digest()


class _Frame:
    __slots__ = ("digest",)

    def __init__(self, digest):
        self.digest = digest


DRAWING = frozenset({"new_path", "new_sub_path", "move_to", "curve_to", "close_path", "set_source_rgba",
                     "set_source", "set_line_width", "set_line_join", "set_line_cap", "fill_preserve",
                     "stroke_preserve"})


def _encode(name, args):
    return (name, *(("gradient", a.get_linear_points(), a.get_color_stops_rgba())
                    if isinstance(a, cairo.LinearGradient) else float(a) for a in args))


class _Context:
    def __init__(self, ops):
        self._ops = ops

    def __getattr__(self, name):
        if name not in DRAWING:
            raise AttributeError(f"pass 1 does not record cairo.Context.{name}")

        def record(*args):
            self._ops.append(_encode(name, args))
        return record


class _TeeCtx:
    """Records exactly the op pass 1 records, then forwards to the real context."""

    def __init__(self, ops, real):
        self._ops, self._real = ops, real

    def __getattr__(self, name):
        if name not in DRAWING:
            raise AttributeError(f"tee does not forward cairo.Context.{name}")
        fn = getattr(self._real, name)

        def tee(*args):
            self._ops.append(_encode(name, args))
            return fn(*args)
        return tee


class RecordContext:
    """Explainers' Recorder, vendored (pass 1: digest-only frames)."""

    def __init__(self, scene):
        cam = self._cam = scene.camera
        self._ops: list = []
        self._canvas = b""
        self._written: list = []
        self._arrays: dict = {}
        self._orig = {n: getattr(cam, n) for n in ("get_cairo_context", "display_point_cloud", "display_image_mobject",
                                                     "display_multiple_background_colored_vmobjects", "reset",
                                                     "set_frame_to_background")}
        self._orig_get_frame = scene.renderer.get_frame
        self._orig_write = scene.renderer.file_writer.write_frame
        cam.get_cairo_context = self._context
        cam.display_point_cloud = self._points
        cam.display_image_mobject = self._image
        cam.display_multiple_background_colored_vmobjects = self._bg
        cam.reset = self._reset
        cam.set_frame_to_background = self._load
        scene.renderer.get_frame = self._snapshot
        scene.renderer.file_writer.write_frame = self._write

    def _array(self, a):
        hit = self._arrays.get(id(a))
        if hit is None:
            hit = self._arrays[id(a)] = (a, _sha(repr((a.shape, a.dtype.str)).encode(), a.tobytes()))
        return hit[1]

    def _matrix(self):
        c = self._cam
        sx, sy = c.pixel_width / c.frame_width, c.pixel_height / c.frame_height
        self._ops.append(("matrix", *map(float, (sx, -sy, c.pixel_width / 2 - c.frame_center[0] * sx,
                                                 c.pixel_height / 2 + c.frame_center[1] * sy))))

    def _context(self, pixel_array):
        self._matrix()
        return _Context(self._ops)

    def _bg(self, vmobjects, pixel_array):
        vmobjects = list(vmobjects)
        displayer = self._cam.get_background_colored_vmobject_displayer()
        self._ops += [("background-image", self._array(displayer.get_background_array(v.get_background_image())))
                      for v in vmobjects]
        return self._orig["display_multiple_background_colored_vmobjects"](vmobjects, pixel_array)

    def _points(self, pmobject, points, rgbas, thickness, pixel_array):
        coords = self._cam.points_to_pixel_coords(pmobject, points)
        self._ops.append(("points", _sha(coords.tobytes(), np.asarray(rgbas, float).tobytes()), float(thickness)))

    def _image(self, image_mobject, pixel_array):
        pixels = np.ascontiguousarray(image_mobject.get_pixel_array())
        corners = self._cam.points_to_subpixel_coords(image_mobject, image_mobject.points)
        self._ops.append(("image", _sha(repr(pixels.shape).encode(), pixels.tobytes(), corners.tobytes()),
                          int(image_mobject.resampling_algorithm)))

    def _reset(self):
        self._ops.clear()
        self._canvas = self._array(self._cam.background)
        return self._cam

    def _load(self, frame):
        self._ops.clear()
        self._canvas = frame.digest

    def _snapshot(self):
        self._canvas = _sha(self._canvas, repr(self._ops).encode())
        self._ops.clear()
        return _Frame(self._canvas)

    def _write(self, frame, *, repeat=1):
        self._written.append((frame.digest, repeat))

    def play_digest(self):
        d = _sha(repr(self._written).encode()).hex()
        self._written.clear()
        return d


class TeeContext(RecordContext):
    """Same ops as pass 1, and every call forwarded: frames carry real pixels."""

    def __init__(self, scene):
        super().__init__(scene)
        self._static = None  # (pixel array, digest) of the current static_image
        self._last = None
        r = scene.renderer
        save = r.save_static_frame_data

        def save_static(sc, static_mobjects):
            out = save(sc, static_mobjects)
            self._static = self._last if r.static_image is not None else None
            return out
        r.save_static_frame_data = save_static

    def _context(self, pixel_array):
        self._matrix()
        return _TeeCtx(self._ops, self._orig["get_cairo_context"](pixel_array))

    def _points(self, pmobject, points, rgbas, thickness, pixel_array):
        super()._points(pmobject, points, rgbas, thickness, pixel_array)
        return self._orig["display_point_cloud"](pmobject, points, rgbas, thickness, pixel_array)

    def _image(self, image_mobject, pixel_array):
        super()._image(image_mobject, pixel_array)
        return self._orig["display_image_mobject"](image_mobject, pixel_array)

    def _reset(self):
        super()._reset()
        return self._orig["reset"]()

    def _load(self, frame):
        assert self._static is not None and self._static[0] is frame, "set_frame_to_background with an unknown frame"
        self._ops.clear()
        self._canvas = self._static[1]
        return self._orig["set_frame_to_background"](frame)

    def _snapshot(self):
        super()._snapshot()
        real = self._orig_get_frame()
        self._last = (real, self._canvas)
        return real

    def _write(self, frame, *, repeat=1):
        self._written.append((self._canvas, repeat))
        return self._orig_write(frame, repeat=repeat)


def exact_fast_forward(scene):
    """Plays before from_animation_number replay play_internal exactly (time-keeping, updaters, stop_condition,
    the closing update_mobjects(0)) with all drawing and writing suppressed."""
    r = scene.renderer
    cam, fw = r.camera, r.file_writer
    real = {"update_skipping_status": r.update_skipping_status, "capture": cam.capture_mobjects,
            "get_frame": r.get_frame, "add_partial": fw.add_partial_movie_file, "begin": fw.begin_animation,
            "end": fw.end_animation, "write": fw.write_frame, "reset": cam.reset, "load": cam.set_frame_to_background}
    state = {"ff": False}

    def update_skipping_status():
        if config.from_animation_number > 0 and r.num_plays < config.from_animation_number:
            state["ff"] = True
            r.skip_animations = False
            return
        state["ff"] = False
        real["update_skipping_status"]()

    def gate(name, null):
        def f(*a, **k):
            return null(*a, **k) if state["ff"] else real[name](*a, **k)
        return f

    r.update_skipping_status = update_skipping_status
    cam.capture_mobjects = gate("capture", lambda *a, **k: None)
    cam.reset = gate("reset", lambda *a, **k: cam)
    cam.set_frame_to_background = gate("load", lambda *a, **k: None)
    r.get_frame = gate("get_frame", lambda *a, **k: None)
    fw.add_partial_movie_file = gate("add_partial", lambda h: real["add_partial"](None))
    fw.begin_animation = gate("begin", lambda *a, **k: real["begin"](False, **{x: y for x, y in k.items()}))
    fw.end_animation = gate("end", lambda *a, **k: real["end"](False))
    fw.write_frame = gate("write", lambda *a, **k: None)


