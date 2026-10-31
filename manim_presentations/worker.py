"""One render chunk, in its own process: plays [first, last] of one chapter's scene, fast-forwarded exactly to `first`,
rendered through the tee, reported to <out>/report.json with each play's digest, frame count and partial file.

    python -P -m manim_presentations.worker <snapshot> <chapter> <title> <settings-json> <cache> <out> <first> <last>

The first statement changes into the snapshot, before anything imports manim (Manim reads ./manim.cfg at import)."""

import os
import sys

if __name__ == "__main__":
    os.chdir(sys.argv[1])

import json
from pathlib import Path


def main(argv: list[str]) -> int:
    snapshot, slug, title, settings_json, cache, out, first, last = argv
    snapshot_path, cache_path, out_path = Path(snapshot), Path(cache), Path(out)
    from manim_presentations.pass1 import watch_parent

    watch_parent()
    os.nice(10)
    import manim  # noqa: F401  — Manim's own bytecode is still used; ours is never written

    sys.dont_write_bytecode = True
    from manim import config

    from manim_presentations import clip, manim_hooks
    from manim_presentations.settings import Settings
    from manim_presentations.talk import Talk

    settings = Settings.from_argv(settings_json)
    clip.render_config(settings)
    merged = {
        "from_animation_number": int(first),
        "upto_animation_number": int(last),
        "media_dir": str(out_path / "media"),
        "tex_dir": str(cache_path / "tex"),
        "text_dir": str(cache_path / "text"),
    }
    assert not merged.keys() & clip.render_keys(settings).keys(), "a worker may only set paths and the play range"
    config.update(merged)
    scene = Talk(snapshot_path / "chapters" / f"{slug}.py", snapshot_path, title, clip.TeeContext)
    manim_hooks.exact_fast_forward(scene)
    scene.render()
    clip.check_render_config(settings)  # nothing outside clip.py changed what frames are drawn with
    partials = manim_hooks.partial_files(scene)
    report = [
        {"anim": b.first_anim + j, "digest": a.digest, "frames": a.frames, "partial": partials[b.first_anim + j]}
        for b in scene.beats
        for j, a in enumerate(b.animations)
        if int(first) <= b.first_anim + j <= int(last)
    ]
    (out_path / "report.json").write_text(json.dumps(report))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
