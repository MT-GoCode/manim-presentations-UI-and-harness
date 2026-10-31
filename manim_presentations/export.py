"""`mpres export <talk> --out FILE.html`: the built talk as one self-contained, offline HTML file. Clips are re-encoded
(never re-rendered) at a web height with export's own encoder settings, which hide a delivery decision and never touch
a clip's fingerprint, and embedded as base64 blocks the player turns into Blob URLs."""

import base64
import functools
import html
import json
import multiprocessing
import os
import shutil
import tempfile
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import av

from manim_presentations import headroom, protocol, script
from manim_presentations.deck import Deck, Layout, require_fresh

# P4: on a 1080p display, height decides quality and crf barely does (VMAF 96.4 at 1080/crf 28, 163 MiB for a 10-min
# talk; 720/crf 23 scores 89.7 and softens small text).
H0 = 1080
C0 = 28
ENCODE_CORES = 1.35  # P4: the largest CPU/wall of 1,539 threads=1 jobs (median 1.1)
MiB = 2**20
PLAYER = Path(__file__).with_name("player.html")
MANIFEST = "<!--manifest-->"  # where the page's data goes in player.html
TITLE = "<!--title-->"
# protocol.KEYS names Qt keys, which are logical (layout-mapped) keys; so are KeyboardEvent.key values. Qt's Key_R is
# R with or without Shift.
DOM_KEY = {
    "Up": ("ArrowUp",),
    "Down": ("ArrowDown",),
    "PageUp": ("PageUp",),
    "PageDown": ("PageDown",),
    "R": ("r", "R"),
}

# What each --transcript mode puts in a beat's manifest entry: nothing, the spoken text, or that and the private notes.
TRANSCRIPT: dict[str, Callable[[script.Beat], dict[str, str]]] = {
    "none": lambda b: {},
    "narration": lambda b: {"narration": b.narration},
    "full": lambda b: {"narration": b.narration, "notes": b.notes},
}

say = functools.partial(print, flush=True)  # tests block on these lines from a pipe


class ExportError(Exception):
    pass


def encode_ram(source_mp: float, out_mp: float) -> int:
    """One encode job's peak RSS: the line through P4's 1080 and 720 maxima from 3456×2168 sources (457 and 302 MiB),
    above its 540 point (246 vs 237), with 22 MiB per source megapixel, P4's decode slope (stills.decode_ram)."""
    return int((12 + 22 * source_mp + 151 * out_mp) * MiB)


def encode(src: Path, dst: Path, width: int, height: int, crf: int, fps: int) -> None:
    """P4's measured job: decode at one thread, bicubic scale, libx264 yuv420p at one thread, the source frame rate."""
    with av.open(str(src)) as inp, av.open(str(dst), "w", options={"movflags": "faststart"}) as out:
        vin = inp.streams.video[0]
        vin.codec_context.thread_count = 1
        vin.codec_context.thread_type = "NONE"
        vout = out.add_stream("libx264", rate=fps)
        vout.width, vout.height, vout.pix_fmt = width, height, "yuv420p"
        vout.codec_context.options = {"crf": str(crf), "threads": "1"}
        for f in inp.decode(vin):
            g = f.reformat(width=width, height=height, format="yuv420p", interpolation="BICUBIC")
            out.mux(vout.encode(g))
        out.mux(vout.encode())


def export(root: Path, out: Path, height: int | None, crf: int | None, transcript: str, workers: int | None) -> int:
    layout = Layout(root)
    layout.export_tmp.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir=layout.export_tmp))
    partial = out.with_name(f".{out.name}.tmp")  # beside --out: os.replace needs one filesystem
    try:
        with layout.clips_shared():  # no commit can collect the clips between opening the deck and reading them
            deck = Deck.open(root)
            require_fresh(deck)
            talk = script.load(root / "script.md")  # the structure require_fresh just compared
            r = deck.render
            if height is not None and height > r.pixel_height:
                raise ExportError(f"--height {height} is above the source height {r.pixel_height}")
            h = height or min(H0, r.pixel_height)
            w = 2 * round(h * r.pixel_width / r.pixel_height / 2)
            crf = C0 if crf is None else crf
            say(f"export: height {h} · width {w} · crf {crf}")
            ram = encode_ram(r.pixel_width * r.pixel_height / 1e6, w * h / 1e6)
            n = headroom.choose("export", workers, len(deck.beats), ENCODE_CORES, ram, say)
            clips = [tmp / f"{i}.mp4" for i in range(len(deck.beats))]
            with ProcessPoolExecutor(n, mp_context=multiprocessing.get_context("spawn")) as pool:  # no forked locks
                job = functools.partial(encode, width=w, height=h, crf=crf, fps=r.fps)
                for k, _ in enumerate(pool.map(job, [b.clip for b in deck.beats], clips), 1):
                    say(f"encoded {k}/{len(clips)}")
        manifest = {
            "title": talk.title,
            "fps": r.fps,
            "chapters": [
                [c.slug, c.title or c.slug] for c in talk.chapters
            ],  # a list: JS orders integer-like keys first
            "keys": {key: a for q, a in protocol.KEYS.items() for key in DOM_KEY[q]},
            "transcript": transcript,
            "beats": [
                {
                    "chapter": b.chapter,
                    "slug": b.slug,
                    "title": b.title or b.slug,
                    "kind": b.kind,
                    "frames": b.frames,
                    **TRANSCRIPT[transcript](talk.beat(b.slug)),
                }
                for b in deck.beats
            ],
        }
        safe = json.dumps(manifest).replace("</", "<\\/")  # no string in it can close the script element
        page_html = PLAYER.read_text(encoding="utf-8").replace(TITLE, html.escape(talk.title))
        head, tail = page_html.split(MANIFEST)
        with partial.open("w", encoding="utf-8") as page:  # streamed: a long talk's clips never sit in memory at once
            page.write(f'{head}<script type="application/json" id="manifest">{safe}</script>\n')
            for i, c in enumerate(clips):
                b64 = base64.b64encode(c.read_bytes()).decode()
                page.write(f'<script type="application/octet-stream" id="clip-{i}">{b64}</script>\n')
            page.write(tail)
        os.replace(partial, out)
    finally:
        shutil.rmtree(tmp)
        partial.unlink(missing_ok=True)
    say(f"exported {out} · {out.stat().st_size // 1024} KiB · {len(deck.beats)} beats")
    return 0
