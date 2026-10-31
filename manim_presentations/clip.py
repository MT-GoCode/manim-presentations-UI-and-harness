"""What a clip is: what a frame digest means, the Manim config every scene process renders under, and how frames are
encoded. This file's hash is the only engine code in a beat's fingerprint, so everything that shapes a clip's bytes
lives here and nowhere else.

Manim touches here (each tested one to one in tests/unit/test_hooks.py):
- the Recorder: the camera's drawing calls, `renderer.get_frame`, `file_writer.write_frame`;
- the tee's static-frame map: `renderer.save_static_frame_data` (the one frame that becomes `static_image`);
- `render_config`: the global `config`, rebuilt from Manim's packaged default.cfg only.

In pass 1 the camera runs its own drawing code, but every call it would make to Cairo (paths, colours, gradients,
line widths, joins, caps) and every point cloud and image it would paint is recorded instead of rasterized. A frame
is the digest of what its canvas started from (the background, or a saved frame) and everything drawn on it since;
equal digests draw equal pixels. Vendored from Explainers' explainers/fingerprint.py."""

import configparser
import hashlib
from pathlib import Path
from typing import Any

import cairo
import manim
import numpy as np
from manim import config
from manim._config.utils import ManimConfig

from manim_presentations.settings import Settings

# Vendored from Explainers' render.py ENCODER. threads=1: x264 output depends on its thread count. g=6: a paused seek
# to any frame lands in ≈50 ms at 3456×2168 (P1). What Manim's "auto" picks for an opaque mp4, pinned, so no
# manim.cfg can change a clip's bytes.
ENCODE = {"threads": "1", "g": "6", "crf": "18", "preset": "veryfast"}
OUTPUT = {"format": "mp4", "transparent": False, "video_codec": "libx264", "pixel_format": "yuv420p"}
SEED = 0  # every process draws the same random numbers, so chunks and pass 1 agree
_applied: dict[str, Any] = {}  # what render_config last set, as Manim stores it


def render_config(settings: Settings) -> None:
    """Make the global Manim `config` exactly Manim's packaged defaults plus this talk's render settings, in place
    (modules hold references to it). A user ~/.config/manim/manim.cfg, merged in at `import manim`, never leaks."""
    parser = configparser.ConfigParser()
    parser.read(Path(manim.__file__).parent / "_config" / "default.cfg")
    fresh = ManimConfig().digest_parser(parser)
    fresh.update(render_keys(settings))
    config.update(fresh)
    _applied.clear()
    _applied.update({k: config[k] for k in render_keys(settings)})


def render_keys(settings: Settings) -> dict[str, Any]:
    return {
        "pixel_width": settings.pixel_width,
        "pixel_height": settings.pixel_height,
        "frame_width": settings.frame_width,
        "frame_height": settings.frame_height,
        "frame_rate": settings.frame_rate,
        "background_color": settings.background,
        "renderer": "cairo",
        "seed": SEED,
        "disable_caching": True,
        "max_files_cached": -1,
        "verbosity": "ERROR",
        "progress_bar": "none",
        "video_encoder_options": ENCODE,
        **OUTPUT,
    }


def check_render_config(settings: Settings) -> None:
    """The live config still holds exactly what `render_config` set: no code outside this file changed how frames are
    drawn or encoded while the scene ran. Compared as Manim stores the values (colours and enums converted)."""
    keys = render_keys(settings)
    drift = {k: (config[k], _applied[k]) for k in keys if repr(config[k]) != repr(_applied[k])}
    assert not drift, f"render config changed outside clip.py: {drift}"


def _sha(*parts: bytes) -> bytes:
    return hashlib.sha256(b"".join(parts)).digest()


class Frame:
    """Stands in for a pixel array wherever the renderer passes frames around (the static frame, written frames)."""

    __slots__ = ("digest",)

    def __init__(self, digest: bytes):
        self.digest = digest


DRAWING = frozenset(
    {
        "new_path",
        "new_sub_path",
        "move_to",
        "curve_to",
        "close_path",
        "set_source_rgba",
        "set_source",
        "set_line_width",
        "set_line_join",
        "set_line_cap",
        "fill_preserve",
        "stroke_preserve",
    }
)


def _op(name: str, args: tuple[Any, ...]) -> tuple[Any, ...]:
    return (
        name,
        *(
            ("gradient", a.get_linear_points(), a.get_color_stops_rgba())
            if isinstance(a, cairo.LinearGradient)
            else float(a)
            for a in args
        ),
    )


class _Context:
    """A cairo.Context that records each drawing call this Manim makes. Any other attribute raises: a query
    (get_matrix, fill_extents) answered with None would draw wrong."""

    def __init__(self, ops: list[tuple[Any, ...]]):
        self._ops = ops

    def __getattr__(self, name: str) -> Any:
        if name not in DRAWING:
            raise AttributeError(f"the recorder does not record cairo.Context.{name}")

        def record(*args: Any) -> None:
            self._ops.append(_op(name, args))

        return record


class RecordContext:
    """Installed on one scene's camera and renderer for pass 1: digest-only frames. `play_digest()` closes one
    animation: the digests of the frames it wrote, each with its repeat count, in order."""

    def __init__(self, scene: Any):
        cam = self._cam = scene.camera
        self._ops: list[tuple[Any, ...]] = []
        self._canvas = b""
        self._written: list[tuple[bytes, int]] = []
        self._arrays: dict[int, tuple[np.ndarray, bytes]] = {}
        names = (
            "get_cairo_context",
            "display_point_cloud",
            "display_image_mobject",
            "display_multiple_background_colored_vmobjects",
            "reset",
            "set_frame_to_background",
        )
        self._orig: dict[str, Any] = {n: getattr(cam, n) for n in names}
        self._orig_get_frame = scene.renderer.get_frame
        self._orig_write = scene.renderer.file_writer.write_frame
        cam.get_cairo_context = self._context
        cam.display_point_cloud = self._points
        cam.display_image_mobject = self._image
        cam.display_multiple_background_colored_vmobjects = self._backgrounds
        cam.reset = self._reset
        cam.set_frame_to_background = self._load
        scene.renderer.get_frame = self._snapshot
        scene.renderer.file_writer.write_frame = self._write

    def _array(self, a: np.ndarray) -> bytes:
        """Digest of an array that stays the same object while in use (the background, a background image). The
        entry holds the array, so its id is never reused while the entry exists."""
        hit = self._arrays.get(id(a))
        if hit is None:
            hit = self._arrays[id(a)] = (a, _sha(repr((a.shape, a.dtype.str)).encode(), a.tobytes()))
        return hit[1]

    def _matrix(self) -> None:
        """Paths are recorded in scene units: the world-to-pixel matrix Camera.get_cairo_context sets is part of what
        is drawn."""
        c = self._cam
        sx, sy = c.pixel_width / c.frame_width, c.pixel_height / c.frame_height
        tx, ty = c.pixel_width / 2 - c.frame_center[0] * sx, c.pixel_height / 2 + c.frame_center[1] * sy
        self._ops.append(("matrix", float(sx), float(-sy), float(tx), float(ty)))

    def _context(self, pixel_array: np.ndarray) -> Any:
        self._matrix()
        return _Context(self._ops)

    def _backgrounds(self, vmobjects: Any, pixel_array: np.ndarray) -> Any:
        vmobjects = list(vmobjects)
        displayer = self._cam.get_background_colored_vmobject_displayer()
        self._ops += [
            ("background-image", self._array(displayer.get_background_array(v.get_background_image())))
            for v in vmobjects
        ]
        return self._orig["display_multiple_background_colored_vmobjects"](vmobjects, pixel_array)

    def _points(self, pmobject: Any, points: np.ndarray, rgbas: np.ndarray, thickness: float, pixel_array: Any) -> Any:
        coords = self._cam.points_to_pixel_coords(pmobject, points)
        self._ops.append(("points", _sha(coords.tobytes(), np.asarray(rgbas, float).tobytes()), float(thickness)))

    def _image(self, image_mobject: Any, pixel_array: np.ndarray) -> Any:
        pixels = np.ascontiguousarray(image_mobject.get_pixel_array())
        corners = self._cam.points_to_subpixel_coords(image_mobject, image_mobject.points)
        self._ops.append(
            (
                "image",
                _sha(repr(pixels.shape).encode(), pixels.tobytes(), corners.tobytes()),
                int(image_mobject.resampling_algorithm),
            )
        )

    def _reset(self) -> Any:
        self._ops.clear()
        self._canvas = self._array(self._cam.background)
        return self._cam

    def _load(self, frame: Frame) -> None:
        self._ops.clear()
        self._canvas = frame.digest

    def _snapshot(self) -> Frame:
        self._canvas = _sha(self._canvas, repr(self._ops).encode())
        self._ops.clear()
        return Frame(self._canvas)

    def _write(self, frame: Frame, *, repeat: int = 1) -> None:
        self._written.append((frame.digest, repeat))

    def play_digest(self) -> tuple[str, int]:
        """(digest of the frames the play wrote, how many frames it wrote)."""
        d = _sha(repr(self._written).encode()).hex()
        n = sum(r for _, r in self._written)
        self._written.clear()
        return d, n


class _TeeCtx:
    """Records exactly the op pass 1 records, then forwards it to the real Cairo context."""

    def __init__(self, ops: list[tuple[Any, ...]], real: Any):
        self._ops, self._real = ops, real

    def __getattr__(self, name: str) -> Any:
        if name not in DRAWING:
            raise AttributeError(f"the tee does not forward cairo.Context.{name}")
        forward = getattr(self._real, name)

        def tee(*args: Any) -> Any:
            self._ops.append(_op(name, args))
            return forward(*args)

        return tee


class TeeContext(RecordContext):
    """A worker's recorder: every call pass 1 records is both digested (with the same op encoder) and forwarded, so
    its frames carry real pixels and a digest the parent compares with pass 1's. It demands nothing more of the camera
    than pass 1 does and guarantees more (Liskov)."""

    def __init__(self, scene: Any):
        super().__init__(scene)
        self._static: tuple[np.ndarray, bytes] | None = None  # the current static_image and its digest
        self._last: tuple[np.ndarray, bytes] | None = None
        renderer = scene.renderer
        save = renderer.save_static_frame_data

        def save_static(sc: Any, static_mobjects: Any) -> Any:
            out = save(sc, static_mobjects)
            self._static = self._last if renderer.static_image is not None else None
            return out

        renderer.save_static_frame_data = save_static

    def _context(self, pixel_array: np.ndarray) -> Any:
        self._matrix()
        return _TeeCtx(self._ops, self._orig["get_cairo_context"](pixel_array))

    def _points(self, pmobject: Any, points: np.ndarray, rgbas: np.ndarray, thickness: float, pixel_array: Any) -> Any:
        super()._points(pmobject, points, rgbas, thickness, pixel_array)
        return self._orig["display_point_cloud"](pmobject, points, rgbas, thickness, pixel_array)

    def _image(self, image_mobject: Any, pixel_array: np.ndarray) -> Any:
        super()._image(image_mobject, pixel_array)
        return self._orig["display_image_mobject"](image_mobject, pixel_array)

    def _reset(self) -> Any:
        super()._reset()
        return self._orig["reset"]()

    def _load(self, frame: Any) -> None:
        assert self._static is not None and self._static[0] is frame, "a background frame the tee did not snapshot"
        self._ops.clear()
        self._canvas = self._static[1]
        self._orig["set_frame_to_background"](frame)

    def _snapshot(self) -> Any:
        super()._snapshot()
        real = self._orig_get_frame()
        self._last = (real, self._canvas)
        return real

    def _write(self, frame: Any, *, repeat: int = 1) -> None:
        self._written.append((self._canvas, repeat))
        self._orig_write(frame, repeat=repeat)


def join(parts: list[Path], out: Path) -> int:
    """Concatenate one beat's partial files without re-encoding (Manim's own combine pattern, vendored from Explainers'
    render.py); returns the number of frames."""
    import io

    import av

    manifest = "".join(f"file 'file:{p}'\n" for p in parts).encode()
    src = av.open(io.BytesIO(manifest), mode="r", options={"safe": "0", "an": "1"}, format="concat")
    dst = av.open(str(out), mode="w")
    stream = dst.add_stream_from_template(src.streams.video[0])
    frames = 0
    for packet in src.demux(src.streams.video[0]):
        if packet.dts is None:
            continue
        packet.dts = None
        packet.stream = stream
        dst.mux(packet)
        frames += 1
    dst.close()
    src.close()
    return frames


def stream_check(path: Path, settings: Settings) -> list[str]:
    """What the clip's stream declares against what ENCODE and the render settings require: codec, pixel format,
    size and frame rate. Drawing is covered by tee verification; encoding is covered here."""
    import av

    with av.open(str(path)) as f:
        v = f.streams.video[0]
        got = {
            "codec": v.codec_context.name,
            "pix_fmt": v.codec_context.pix_fmt,
            "size": (v.width, v.height),
            "fps": v.average_rate,
        }
    want = {
        "codec": "h264",
        "pix_fmt": OUTPUT["pixel_format"],
        "size": (settings.pixel_width, settings.pixel_height),
        "fps": settings.frame_rate,
    }
    return [f"{k} {got[k]} ≠ {want[k]}" for k in want if got[k] != want[k]]


def identity() -> dict[str, str]:
    """Everything after the frames that shapes a clip's bytes, besides the render settings: this file (the Recorder,
    ENCODE, join) and the drawing and encoding libraries. pixman is read from its pkg-config record: it can change
    antialiased pixels for identical draw calls."""
    import subprocess
    import sys
    from importlib.metadata import version

    pixman = subprocess.run(["pkg-config", "--modversion", "pixman-1"], capture_output=True, text=True, check=True)
    return {
        "clip.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "python": sys.version,
        **{d: version(d) for d in ("manim", "pycairo", "av", "numpy", "pillow")},
        "cairo": cairo.cairo_version_string(),
        "pixman": pixman.stdout.strip(),
    }
