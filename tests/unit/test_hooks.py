"""One test per Manim touch (the lists in clip.py's and manim_hooks.py's docstrings). Each fails loudly if the hook
stops firing after a Manim upgrade."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from manim import BLUE, RED, Circle, FadeIn, ImageMobject, PointCloudDot, Scene, Square, config, tempconfig

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
    (cfg / "manim.cfg").write_text("[CLI]\nframe_rate = 7\npixel_width = 100\nbackground_color = #FF0000\n")
    code = (
        "from manim import config\nfrom manim_presentations import clip\nfrom manim_presentations.settings import "
        f"Settings\nclip.render_config(Settings.model_validate_json({SETTINGS.model_dump_json()!r}))\n"
        "print(config.frame_rate, config.pixel_width, config.background_color.to_hex())"
    )
    out = subprocess.run(
        [sys.executable, "-P", "-c", code],
        env={**os.environ, "HOME": str(tmp_path)},
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert out == ["30", "480", "#000000"]


def test_creation_lines_name_the_chapter_line_even_inside_a_helper(tmp_path):
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
    clip.render_config(SETTINGS)

    class S(Scene):
        pass

    s = S()
    c = Circle().shift([2, 1, 0])
    pts = manim_hooks.screen(s.camera, c, c.points)
    assert pts[:, 0].mean() == pytest.approx(2, abs=1e-6) and pts[:, 1].mean() == pytest.approx(1, abs=1e-6)


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
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert (out / "records.json").exists()
    assert not list(snap.rglob("__pycache__"))
    config.dry_run = False
