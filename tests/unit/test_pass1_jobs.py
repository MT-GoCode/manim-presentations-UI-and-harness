"""Each pass-1 child gets its own copy of the warm cache. A shared cache races: Manim writes a fixed-name temp SVG
beside a cached entry even on a hit, and checks-then-writes on a miss. That race is timing-dependent at test scale
(two chapters did not collide reliably), so the property is checked where it is decided: the job plan."""

from pathlib import Path

from manim_presentations.build import pass1_jobs
from manim_presentations.deck import Layout
from manim_presentations.script import parse
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


def test_each_chapter_gets_a_private_copy_of_the_cache(tmp_path):
    layout = Layout(tmp_path / "t.manim-presentation")
    shared = layout.cache("id")
    (shared / "text").mkdir(parents=True)
    (shared / "text" / "entry.svg").write_text("<svg/>")
    script = parse("T\n\n# a\n\n## x\n\n# b\n\n## y\n")
    jobs = pass1_jobs(layout, list(script.chapters), SETTINGS, shared)
    caches = [Path(j.args[4]) for j in jobs]
    assert len(set(caches)) == 2
    for c in caches:
        assert c.is_relative_to(layout.media) and c != shared
        assert (c / "text" / "entry.svg").read_text() == "<svg/>"  # seeded, not empty
