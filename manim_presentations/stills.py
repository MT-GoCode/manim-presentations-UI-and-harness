"""The one decoder of stills: a clip's frame `index` as a PNG (first and last for the deck, middle for shots). This
file's hash names the stills, so a change here regenerates them from existing clips without re-rendering anything."""

from pathlib import Path

import av


def still_at(clip: Path, index: int, out: Path) -> None:
    """Write frame `index` (0-based, in presentation order) of `clip` to `out`, atomically."""
    with av.open(str(clip)) as f:
        for n, frame in enumerate(f.decode(video=0)):
            if n == index:
                tmp = out.with_name(f".tmp-{out.name}")
                frame.to_image().save(tmp, format="PNG")
                tmp.replace(out)
                return
    raise ValueError(f"{clip} has no frame {index}")
