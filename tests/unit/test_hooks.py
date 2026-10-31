"""One test per Manim touch (the lists in clip.py's and manim_hooks.py's docstrings). Each fails loudly if the hook
stops firing after a Manim upgrade."""

import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from manim import BLUE, RED, Circle, FadeIn, FadeOut, ImageMobject, PointCloudDot, Scene, Square, tempconfig

from manim_presentations import clip, manim_hooks
from manim_presentations.settings import Settings

SETTINGS = Settings(
    pixel_width=480,
    pixel_height=270,
    frame_width=8 * 480 / 270,
    frame_rate=30,
    background="#000000",
    min_text=0.0,
    min_tex=0.0,
)


@pytest.fixture(autouse=True)
def in_tmp_path(tmp_path, monkeypatch):
    """Manim's default media, text and TeX folders are relative to the cwd (render_config restores them)."""
    monkeypatch.chdir(tmp_path)


def digests(build_scene) -> list[tuple[str, int]]:
    """Pass-1 digests of a scene whose construct is `build_scene(scene)`, dry-run under RecordContext."""
    clip.render_config(SETTINGS)
    out: list[tuple[str, int]] = []
    with tempconfig({"dry_run": True}):

        class S(Scene):
            def construct(self):
                build_scene(self)

        s = S()
        rec = clip.RecordContext(s)
        play = s.play

        def recorded(*a, **k):
            play(*a, **k)
            out.append(rec.play_digest())

        s.play = recorded
        s.render()
    return out


def test_recorder_digests_identify_what_is_drawn():
    same = digests(lambda s: s.play(FadeIn(Square(color=BLUE))))
    assert same == digests(lambda s: s.play(FadeIn(Square(color=BLUE))))
    assert same != digests(lambda s: s.play(FadeIn(Square(color=RED))))
    assert same[0][1] == 30  # FadeIn's default 1 s at 30 fps


def test_recorder_sees_the_non_cairo_paths(tmp_path):
    from PIL import Image

    png = tmp_path / "p.png"
    Image.new("RGB", (8, 8), (255, 0, 0)).save(png)
    Image.new("RGB", (8, 8), (0, 255, 0)).save(tmp_path / "q.png")
    img = digests(lambda s: s.play(FadeIn(ImageMobject(str(png)))))
    assert img != digests(lambda s: s.play(FadeIn(ImageMobject(str(tmp_path / "q.png")))))
    cloud = digests(lambda s: s.play(FadeIn(PointCloudDot(color=BLUE))))
    assert cloud != digests(lambda s: s.play(FadeIn(PointCloudDot(color=RED))))


def test_render_config_ignores_a_user_manim_cfg(tmp_path):
    """A hostile user config, merged in at `import manim`, never reaches the render settings."""
    cfg = tmp_path / ".config" / "manim"
    cfg.mkdir(parents=True)
    (cfg / "manim.cfg").write_text("[CLI]\nframe_rate = 7\nzero_pad = 9\nwrite_all = True\nsave_last_frame = True\n")
    code = (
        "from manim import config\nfrom manim_presentations import clip\nfrom manim_presentations.settings import "
        f"Settings\nclip.render_config(Settings.model_validate_json({SETTINGS.model_dump_json()!r}))\n"
        "print(config.frame_rate, config.zero_pad, config.write_all, config.save_last_frame)"
    )
    out = subprocess.run(
        [sys.executable, "-P", "-c", code],
        env={**os.environ, "HOME": str(tmp_path)},
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert out == ["30", "4", "False", "False"]  # keys render_config does not set are still Manim's defaults


def test_creation_lines_name_the_chapter_line_even_inside_a_helper(tmp_path, monkeypatch):
    from manim import Mobject

    monkeypatch.setattr(Mobject, "__init__", Mobject.__init__)  # restored after the test: the hook patches the class
    monkeypatch.setattr(Mobject, "copy", Mobject.copy)
    chapter = tmp_path / "ch.py"
    helper_src = "from manim import Circle\ndef make():\n    return Circle()\n"
    helper = {}
    exec(compile(helper_src, str(tmp_path / "helper.py"), "exec"), helper)
    manim_hooks.record_creation_lines(frozenset({str(chapter)}))
    ns = {"make": helper["make"], "Square": Square}
    exec(compile("a = Square()\n\nb = make()\nc = a.copy()\n", str(chapter), "exec"), ns)
    assert manim_hooks.born(ns["a"]) == (str(chapter), 1)
    assert manim_hooks.born(ns["b"]) == (str(chapter), 3)
    assert manim_hooks.born(ns["c"]) == (str(chapter), 4)


def test_projection_is_where_the_camera_draws():
    """A moved camera: the object's drawn position is its position minus the frame centre."""
    clip.render_config(SETTINGS)

    class S(Scene):
        pass

    s = S()
    s.camera.frame_center = np.array([0.5, -0.25, 0.0])
    c = Circle().shift([2, 1, 0])
    pts = manim_hooks.screen(s.camera, c, c.points)
    assert pts[:, 0].mean() == pytest.approx(1.5, abs=1e-6) and pts[:, 1].mean() == pytest.approx(1.25, abs=1e-6)


def test_recorder_digest_includes_the_frame_centre():
    def centred(x):
        def build(s):
            s.camera.frame_center = np.array([x, 0.0, 0.0])
            s.play(FadeIn(Square()))

        return build

    assert digests(centred(0.0)) != digests(centred(0.5))


def test_recorder_chains_frames_drawn_on_the_static_image():
    """A still object is drawn once into the static frame; every animated frame starts from it."""

    def still(color):
        def build(s):
            s.add(Square(color=color).shift([-2, 0, 0]))
            s.play(FadeIn(Circle()))

        return build

    assert digests(still(BLUE)) != digests(still(RED))


def test_recorder_sees_background_image_vmobjects(tmp_path):
    from PIL import Image

    def image(rgb, name):
        Image.new("RGB", (8, 8), rgb).save(tmp_path / name)

        def build(s):
            s.play(FadeIn(Circle().set_fill(opacity=1).color_using_background_image(str(tmp_path / name))))

        return build

    assert digests(image((255, 0, 0), "r.png")) != digests(image((0, 255, 0), "g.png"))


def test_play_index_counts_plays():
    seen = []
    digests(
        lambda s: [
            seen.append(manim_hooks.play_index(s)),
            s.play(FadeIn(Square())),
            seen.append(manim_hooks.play_index(s)),
            s.wait(0.5),
            seen.append(manim_hooks.play_index(s)),
        ]
    )
    assert seen == [0, 1, 2]


def test_pass1_writes_no_bytecode(tmp_path):
    """Pass 1 imports talk helpers from the snapshot; none may leave a __pycache__ behind."""
    snap = tmp_path / "snap"
    (snap / "chapters").mkdir(parents=True)
    (snap / "helpers").mkdir()
    (snap / "helpers" / "__init__.py").write_text("")
    (snap / "helpers" / "h.py").write_text("X = 1\n")
    (snap / "chapters" / "c.py").write_text(
        "from manim import FadeIn, Square\nfrom helpers.h import X\n\ndef construct(talk):\n    talk.beat('b')\n"
        "    talk.play(FadeIn(Square(X)))\n"
    )
    out = tmp_path / "out"
    out.mkdir()
    cache = tmp_path / "cache"
    cache.mkdir()
    tinytex = Path(clip.__file__).parents[1] / ".tinytex"
    r = subprocess.run(
        [
            sys.executable,
            "-P",
            "-m",
            "manim_presentations.pass1",
            str(snap),
            "c",
            "C",
            SETTINGS.to_argv(),
            str(cache),
            str(tinytex),
            str(out),
        ],
        env={**os.environ, "MPRES_BUILD_PID": str(os.getpid())},
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert (out / "records.json").exists()
    assert not list(snap.rglob("__pycache__"))


def tee_run(build_scene, first: int) -> tuple[list[str], float, dict[int, str], list[str]]:
    """Render plays from `first` on through TeeContext after exact fast-forward: (digests of the rendered plays, the
    renderer's clock at the end, the partial-file mapping, pass 1's digests of the same plays)."""
    clip.render_config(SETTINGS)
    pass1 = [d for d, _ in digests(build_scene)]
    out: list[str] = []
    with tempconfig({"from_animation_number": first}):

        class S(Scene):
            def construct(self):
                build_scene(self)

        s = S()
        tee = clip.TeeContext(s)
        manim_hooks.exact_fast_forward(s)
        play = s.play

        def recorded(*a, **k):
            n = s.renderer.num_plays
            play(*a, **k)
            if n >= first:
                out.append(tee.play_digest()[0])
            else:
                tee.play_digest()

        s.play = recorded
        s.render()
        return out, s.renderer.time, manim_hooks.partial_files(s), pass1[first:]


def stateful(s):
    sq = Square()
    sq.add_updater(lambda m, dt: m.rotate(dt))  # per-frame state a one-step skip would not reproduce
    s.add(sq)
    s.play(FadeIn(Circle()))
    s.wait(0.5)
    ticks = {"n": 0}

    def stop():
        ticks["n"] += 1
        return ticks["n"] > 7  # wait_until stops mid-wait, after a frame-dependent count

    s.wait_until(stop, max_time=2)
    s.play(sq.animate.shift([1, 0, 0]))


def test_exact_fast_forward_reproduces_pass1_and_its_clock():
    got, clock, partials, want = tee_run(stateful, 3)
    assert got == want
    full_clock = tee_run(stateful, 0)[1]
    assert clock == full_clock  # time-keeping: the fast-forwarded plays advanced the clock exactly as rendered ones
    assert sorted(partials) == [3]  # the partial-file mapping holds only the rendered play, at its play index


def test_skip_mode_fast_forward_would_diverge(monkeypatch):
    """The mutant: Manim's own skip mode for the plays before the chunk. Its digests differ, so the tee comparison
    in the build can catch it."""
    monkeypatch.setattr(manim_hooks, "exact_fast_forward", lambda scene: None)
    got, _, _, want = tee_run(stateful, 3)
    assert got != want


def first_frame_vs_raster(build_scene) -> tuple[np.ndarray, np.ndarray]:
    """(the canonical raster at the first play's capture point, the pixels Manim actually drew for that frame)."""
    clip.render_config(SETTINGS)
    captured: dict[str, np.ndarray] = {}
    with tempconfig({}):

        class S(Scene):
            def construct(self):
                build_scene(self)

        s = S()
        manim_hooks.on_first_frame(s, lambda: captured.setdefault("raster", manim_hooks.canonical_raster(s)))
        write = s.renderer.file_writer.write_frame

        def first_written(frame, **k):
            captured.setdefault("drawn", np.asarray(frame).copy())
            return write(frame, **k)

        s.renderer.file_writer.write_frame = first_written
        s.render()
    return captured["raster"], captured["drawn"]


@pytest.mark.parametrize(
    "build_scene",
    [
        lambda s: (s.add(Square(color=BLUE)), s.play(FadeIn(Circle(color=RED)))),  # a moving play's frame 0
        lambda s: (s.add(Square(color=BLUE)), s.wait(0.2)),  # a frozen wait's frame
    ],
    ids=["play", "frozen-wait"],
)
def test_the_start_capture_point_is_exactly_frame_0(build_scene):
    raster, drawn = first_frame_vs_raster(build_scene)
    assert np.array_equal(raster[..., :3], drawn[..., :3])


def test_the_end_raster_leaves_out_what_a_play_removed():
    """FadeOut's clean-up takes its mobject out of the scene but not out of the play's moving list."""
    clip.render_config(SETTINGS)
    with tempconfig({"dry_run": True}):
        s = Scene()
        gone = Circle(color=RED)
        s.add(gone)
        s.play(FadeOut(gone))
        after = manim_hooks.canonical_raster(s)
        empty = Scene()
        empty.play(FadeIn(Square().set_opacity(0)))
        blank = manim_hooks.canonical_raster(empty)
    assert np.array_equal(after, blank)


@pytest.fixture
def size_hooks(monkeypatch):
    """The pass-1 size hooks, restored after the test (they patch Manim classes)."""
    from manim import Mobject, Paragraph, Transform

    for cls, name in ((Paragraph, "__init__"), (Transform, "clean_up_from_scene"), (Mobject, "become")):
        monkeypatch.setattr(cls, name, getattr(cls, name))
    manim_hooks.install_size_references()


def played(build_scene):
    clip.render_config(SETTINGS)
    with tempconfig({"dry_run": True}):
        s = Scene()
        return build_scene(s)


def test_a_transformed_text_is_sized_as_its_target(size_hooks):
    from manim import Text, Transform

    def run(s):
        t = Text("go", font_size=16)
        s.add(t)
        s.play(Transform(t, Text("gone", font_size=48)))  # a different glyph set: height alone would mislead
        return t

    t = played(run)
    assert manim_hooks.font_size(t) == pytest.approx(48)
    assert t.font_size != pytest.approx(48)  # Manim's own reading is stale: the shadow is what makes this right


def test_a_later_scale_stays_reflected(size_hooks):
    from manim import Text, Transform

    def run(s):
        t = Text("go", font_size=16)
        s.add(t)
        s.play(Transform(t, Text("gone", font_size=50)))
        s.play(t.animate.scale(0.5))
        return t

    assert manim_hooks.font_size(played(run)) == pytest.approx(25)


def test_become_takes_the_targets_reference(size_hooks):
    from manim import Text

    def run(s):
        t = Text("a", font_size=12)
        t.become(Text("tall glyphs", font_size=44))
        return t

    assert manim_hooks.font_size(played(run)) == pytest.approx(44)


def test_a_paragraph_is_sized_from_its_text(size_hooks):
    from manim import Paragraph

    p = Paragraph("one", "two lines", font_size=30)
    assert manim_hooks.font_size(p) == pytest.approx(30)
    p.scale(0.5)
    assert manim_hooks.font_size(p) == pytest.approx(15)


def test_text_transformed_into_a_non_text_slot_is_marked(size_hooks):
    from manim import Text, Transform, VGroup

    def run(s):
        two = VGroup(Text("a", font_size=40), Text("b", font_size=40))
        s.add(two)
        s.play(Transform(two, VGroup(Text("x", font_size=40), Square(0.3))))  # text where the target has none
        return two

    a, b = played(run)
    assert getattr(a, "_mpres_size_mismatch", False) and getattr(b, "_mpres_size_mismatch", False)


def test_a_source_that_leaves_the_screen_takes_no_shadow(size_hooks):
    """FadeTransform restores its source and takes it off screen (its mobject is a group of the source and a target
    copy, two texts against one). Shown again later, the source is its own 16 and is not marked mismatched."""
    from manim import FadeTransform, Text

    def run(s):
        a, b = Text("a", font_size=16), Text("b", font_size=48)
        s.add(a)
        s.play(FadeTransform(a, b))
        s.add(a)
        return a, b

    a, b = played(run)
    assert not getattr(a, "_mpres_size_mismatch", False)
    assert manim_hooks.font_size(a) == pytest.approx(16) and manim_hooks.font_size(b) == pytest.approx(48)


def test_the_shadow_changes_no_frame(monkeypatch):
    """Observation only: a chapter that sets font_size after a Transform draws the same frames with the hook."""
    from manim import Text, Transform

    def scene(s):
        t = Text("go", font_size=16)
        s.add(t)
        s.play(Transform(t, Text("gone", font_size=48)))
        t.font_size = 36
        s.play(t.animate.shift([1, 0, 0]))

    without = digests(scene)
    from manim import Mobject, Paragraph

    for cls, name in ((Paragraph, "__init__"), (Transform, "clean_up_from_scene"), (Mobject, "become")):
        monkeypatch.setattr(cls, name, getattr(cls, name))
    manim_hooks.install_size_references()
    assert digests(scene) == without
