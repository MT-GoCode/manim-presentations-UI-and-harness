"""The export tests' own tools for the frames talk, whose every frame carries the code beat << 8 | frame index
(drawn by fixtures/frames.manim-presentation/helpers/code.py): its decoder and the exported page's parts."""

import base64
import io
import json
import re
import subprocess
import sys
from pathlib import Path

import av
from conftest import SUBPROCESS_TIMEOUT

FRAMES = Path(__file__).parent / "fixtures" / "frames.manim-presentation"
CELLS = 12
ROW = 0.056  # the cells' centre line, as a fraction of frame height (0.45 of 8 scene units)


def code(gray) -> int:
    """The frame code of one frame given as a 2-D luma array."""
    h, w = gray.shape
    return sum(1 << b for b in range(CELLS) if gray[int(ROW * h), int((b + 0.5) * w / CELLS)] > 128)


def run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """mpres with an environment (the engine-edit pattern); conftest.mpres for everything else."""
    return subprocess.run(
        [sys.executable, "-P", "-m", "manim_presentations.cli", *args],
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT,
        env=env,
    )


def manifest(html: str) -> dict:
    return json.loads(re.search(r'<script type="application/json" id="manifest">(.*?)</script>', html, re.S)[1])


def clips(html: str) -> list[bytes]:
    blocks = re.findall(r'<script type="application/octet-stream" id="clip-(\d+)">(.*?)</script>', html, re.S)
    assert [int(i) for i, _ in blocks] == list(range(len(blocks)))
    return [base64.b64decode(b) for _, b in blocks]


def decoded(clip: bytes) -> tuple[tuple[int, int, int], list[int]]:
    """The clip's (width, height, frame rate) and the code of every frame, in presentation order."""
    with av.open(io.BytesIO(clip)) as f:
        s = f.streams.video[0]
        return (s.width, s.height, s.average_rate), [code(fr.to_ndarray(format="gray")) for fr in f.decode(s)]
