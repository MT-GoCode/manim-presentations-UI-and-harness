"""Pair each beat's new last frame with the old build's end frame; print mean abs pixel diff; write side-by-side sheets."""
import json, sys
from pathlib import Path
from PIL import Image, ImageChops, ImageStat
old = Path(sys.argv[1]); new = Path(sys.argv[2]); out = Path(sys.argv[3]); out.mkdir(exist_ok=True)
ids = json.loads((Path(__file__).parent / "id_to_slug.json").read_text())
beats = [(i, s) for i, s in ids.items() if "." in i]
n_by_slug = {p.name.rsplit("-last.png", 1)[0].split("-", 1)[1]: p for p in new.glob("*-last.png")}
W = 576
rows = {}
for i, slug in beats:
    a = Image.open(old / i.split(".")[0] / f"{i}-end.png").convert("RGB")
    b = Image.open(n_by_slug[slug]).convert("RGB")
    assert a.size == b.size, (i, a.size, b.size)
    d = ImageStat.Stat(ImageChops.difference(a, b)).mean
    diff = sum(d) / 3
    print(f"{i:6} {slug:40} mean|Δ|={diff:6.2f}")
    h = int(a.height * W / a.width)
    rows.setdefault(i.split(".")[0], []).append((a.resize((W, h)), b.resize((W, h))))
for ch, pairs in rows.items():
    h = pairs[0][0].height
    sheet = Image.new("RGB", (2 * W + 8, len(pairs) * (h + 8)), "gray")
    for k, (a, b) in enumerate(pairs):
        sheet.paste(a, (0, k * (h + 8))); sheet.paste(b, (W + 8, k * (h + 8)))
    sheet.save(out / f"{ch}.png")
