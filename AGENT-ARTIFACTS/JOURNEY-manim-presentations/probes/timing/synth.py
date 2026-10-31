"""Throwaway timing probe (P0/P2/P3/P7c): one synthetic Mixing-Deluxe-scale chapter (6 beats, ~60 s of video).

usage: python synth.py MODE CHAPTER OUTDIR [FROM [UPTO]]
  MODE pass1  dry run under RecordContext (pass-1 cost, digests)
       plain  full render, no recorder
       tee    render plays FROM..UPTO through TeeContext with exact fast-forward
env: P_W, P_H pixel size (default 3456x2168); prints one JSON line.
"""
import json
import os
import resource
import sys
import time
from pathlib import Path

MODE, CH, OUTDIR = sys.argv[1], int(sys.argv[2]), Path(sys.argv[3]).resolve()
FROM = int(sys.argv[4]) if len(sys.argv) > 4 else 0
UPTO = int(sys.argv[5]) if len(sys.argv) > 5 else -1
W, H = int(os.environ.get("P_W", 3456)), int(os.environ.get("P_H", 2168))
TEX = os.environ.get("P_TEX") or Path("/Users/minhtrinh/code/explainers/.tinytex/bin-path").read_text().strip()
os.environ["PATH"] = TEX + os.pathsep + os.environ["PATH"]
t_import = time.monotonic()
from manim import *  # noqa: E402,F403
from manim import tempconfig  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from rec import RecordContext, TeeContext, exact_fast_forward  # noqa: E402

import_s = time.monotonic() - t_import


class Chapter(Scene):
    def construct(self):
        title = Text(f"Chapter {CH}: synthetic", font_size=40).to_edge(UP)
        self.add(title)
        eq = MathTex(r"\sum_{i=1}^{n} w_i x_i = " + str(CH), font_size=44).to_corner(DR)
        for b in range(6):
            grid = VGroup(*[Square(0.5, color=BLUE, fill_opacity=0.3) for _ in range(24)]).arrange_in_grid(4, 6, buff=0.25)
            self.play(LaggedStart(*[Create(s) for s in grid], lag_ratio=0.05), run_time=2)
            labels = VGroup(*[Text(f"item {CH}.{b}.{i}", font_size=24) for i in range(6)]).arrange(DOWN).to_edge(LEFT)
            self.play(FadeIn(labels, shift=RIGHT), run_time=1)
            self.play(grid.animate.scale(0.7).shift(RIGHT * 2), run_time=2)
            dot = Dot(color=YELLOW)
            dot.add_updater(lambda m, dt: m.rotate(dt, about_point=ORIGIN).shift(RIGHT * 0 + 0.0))
            dot.move_to(RIGHT * 1.5)
            self.add(dot)
            self.wait(2)
            dot.clear_updaters()
            target = VGroup(*[Circle(0.25, color=GREEN, fill_opacity=0.5) for _ in range(24)]).arrange_in_grid(4, 6, buff=0.3).shift(RIGHT * 2)
            self.play(Transform(grid, target), Write(eq) if b == 0 else Indicate(eq), run_time=2)
            self.wait(1)
            self.play(FadeOut(grid, labels, dot), run_time=0.5)


def private_cache(kind):
    """Each process gets its own copy of the warm cache (Manim writes into its cache even on a hit)."""
    import shutil
    warm, mine = OUTDIR / f"{kind}-{CH}", OUTDIR / f"{kind}-{CH}-{MODE}-{FROM}-{UPTO}-{os.getpid()}"
    if MODE == "tee" and warm.exists():
        shutil.copytree(warm, mine)
        return str(mine)
    return str(warm)


def cfg(**extra):
    return {"pixel_width": W, "pixel_height": H, "frame_width": 8.0 * W / H, "frame_rate": 30, "seed": 0,
            "disable_caching": True, "max_files_cached": -1, "verbosity": "ERROR", "progress_bar": "none",
            "media_dir": str(OUTDIR / f"media-{MODE}-{CH}-{FROM}-{UPTO}"), "tex_dir": private_cache("tex"),
            "text_dir": private_cache("text"), "format": "mp4", "transparent": False, "video_codec": "libx264",
            "pixel_format": "yuv420p",
            "video_encoder_options": {"threads": "1", "g": "6", "crf": "18", "preset": "veryfast"}, **extra}


t0 = time.monotonic()
out = {"mode": MODE, "chapter": CH, "from": FROM, "upto": UPTO, "w": W, "h": H, "import_s": import_s}
if MODE == "pass1":
    with tempconfig(cfg(dry_run=True)):
        scene = Chapter()
        rec = RecordContext(scene)
        play, digests, durations = scene.play, [], []

        def recorded(*a, **k):
            play(*a, **k)
            digests.append(rec.play_digest())
            durations.append(scene.duration)
        scene.play = recorded
        scene.render()
    out |= {"plays": len(digests), "video_s": sum(durations), "durations": durations}
elif MODE == "plain":
    with tempconfig(cfg()):
        scene = Chapter()
        scene.render()
else:
    with tempconfig(cfg(from_animation_number=FROM, upto_animation_number=UPTO)):
        scene = Chapter()
        TeeContext(scene)
        exact_fast_forward(scene)
        scene.render()
out["seconds"] = time.monotonic() - t0
ru = resource.getrusage(resource.RUSAGE_SELF)
out["maxrss"] = ru.ru_maxrss
out["cpu_s"] = ru.ru_utime + ru.ru_stime
print(json.dumps(out))
