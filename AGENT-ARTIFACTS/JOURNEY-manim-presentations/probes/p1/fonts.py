"""P1(e): QPlainTextEdit font ladder 10-28 pt, grabbed at devicePixelRatio 2, with measured cap height in pixels."""

import os
import sys
from pathlib import Path

if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
    sys.exit("refusing to run: QT_QPA_PLATFORM must be offscreen")

import numpy as np
from PySide6.QtGui import QFont, QFontMetricsF, QImage
from PySide6.QtWidgets import QApplication, QPlainTextEdit

TEXT = """## what-a-swarm-does: What a swarm does

Each agent owns one file. The merge step reads every file once and writes one summary.
> note: pause here, point at the left column, then click.
Next: the latency chart. 12 agents finish in 41 s, not 8 min.
"""

app = QApplication([])
out = Path(__file__).parent / "fonts"
out.mkdir(exist_ok=True)
rows = []
for pt in range(10, 29):
    ed = QPlainTextEdit()
    f = QFont(ed.font())
    f.setPointSize(pt)
    ed.setFont(f)
    ed.setPlainText(TEXT)
    ed.resize(1100, 520)
    ed.show()
    app.processEvents()
    img = ed.grab().toImage().convertToFormat(QImage.Format.Format_Grayscale8)
    # measured cap height: dark rows of a lone "H" rendered in the same font at the same DPR
    probe = QPlainTextEdit()
    probe.setFont(f)
    probe.setPlainText("H")
    probe.setCursorWidth(0)
    probe.resize(300, 200)
    probe.show()
    app.processEvents()
    h = probe.grab().toImage().convertToFormat(QImage.Format.Format_Grayscale8)
    a = np.frombuffer(h.constBits(), np.uint8).reshape(h.height(), h.bytesPerLine())[:, : h.width()]
    dark = np.where((a < 128).any(axis=1))[0]
    cap_px = int(dark.max() - dark.min() + 1)
    img.save(str(out / f"editor_{pt:02d}pt.png"))
    rows.append((pt, ed.devicePixelRatio(), img.width(), img.height(), cap_px, QFontMetricsF(f).capHeight(), f.family()))
    ed.close()
    probe.close()
with open(out / "ladder.tsv", "w") as fh:
    fh.write("pt\tdpr\tpng_w\tpng_h\tcap_px_measured\tcap_height_logical\tfamily\n")
    for r in rows:
        fh.write("\t".join(map(str, r)) + "\n")
        print(*r, sep="\t", flush=True)
