"""`mpres shots <talk>`: the first, middle and last frame of every beat as PNGs, plus one contact sheet per chapter
(first | middle | last per beat), for an agent to look at the talk without playing it."""

import hashlib
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

from manim_presentations import headroom, stills
from manim_presentations.deck import BuiltBeat, Deck, Layout, require_fresh

MARKER = ".mpres-shots"  # only a folder holding this marker is ever emptied
# Contact-sheet thumbnails are this wide: three across is 1536 px, inside the 1568 px long edge a model reads an
# image at without downscaling, so an agent sees a chapter at full detail in one image.
THUMB_WIDTH = 512


class ShotsError(Exception):
    pass


def default_out(root: Path) -> Path:
    """Per talk, under /tmp: the folder name plus 8 hex of the path's sha256 keeps two same-named talks apart."""
    return Path("/tmp/mpres-shots") / f"{root.stem}-{hashlib.sha256(str(root).encode()).hexdigest()[:8]}"


def prepare(out: Path) -> None:
    """An empty output folder: a new one, or one this command made before (its marker), emptied."""
    if out.exists() and any(out.iterdir()):
        if not (out / MARKER).exists():
            raise ShotsError(f"{out} is not empty and was not made by mpres shots; pick another --out")
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / MARKER).touch()


def shots(root: Path, out: Path | None, workers: int | None) -> int:
    out = out or default_out(root)
    layout = Layout(root)
    with layout.clips_shared():  # no commit can collect the clips between opening the deck and reading them
        deck = Deck.open(root)
        require_fresh(deck)
        prepare(out)
        digits = len(str(len(deck.beats)))
        named = [(f"{n:0{digits}d}-{b.slug}", b) for n, b in enumerate(deck.beats, 1)]
        megapixels = deck.render.pixel_width * deck.render.pixel_height / 1e6
        width, _ = headroom.choose(
            "shots", workers, len(named), stills.DECODE_CORES, stills.decode_ram(megapixels), print
        )

        def frames(job: tuple[str, BuiltBeat]) -> None:
            name, b = job
            shutil.copyfile(b.first_png, out / f"{name}-first.png")
            shutil.copyfile(b.last_png, out / f"{name}-last.png")
            stills.still_at(b.clip, b.frames // 2, out / f"{name}-middle.png")

        with ThreadPoolExecutor(width) as pool:
            list(pool.map(frames, named))
    chapters = list(dict.fromkeys(b.chapter for b in deck.beats))
    for n, chapter in enumerate(chapters, 1):
        rows = [name for name, b in named if b.chapter == chapter]
        contact_sheet(
            [[out / f"{r}-{w}.png" for w in ("first", "middle", "last")] for r in rows],
            out / f"{n:0{len(str(len(chapters)))}d}-{chapter}.png",
        )
    count = sum(1 for p in out.iterdir() if p.suffix == ".png")
    print(f"shots: {count} images in {out}")
    return 0


def contact_sheet(rows: list[list[Path]], out: Path) -> None:
    images = [[Image.open(p) for p in row] for row in rows]
    w, h = images[0][0].size
    th = round(THUMB_WIDTH * h / w)
    sheet = Image.new("RGB", (3 * THUMB_WIDTH, th * len(rows)))
    for y, row in enumerate(images):
        for x, image in enumerate(row):
            sheet.paste(image.convert("RGB").resize((THUMB_WIDTH, th)), (x * THUMB_WIDTH, y * th))
    sheet.save(out)
