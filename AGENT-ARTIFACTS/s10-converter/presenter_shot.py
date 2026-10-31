"""STRATUM 8's human-verifiable result at Mixing-Deluxe scale: a Presenter View screenshot, offscreen only."""

import os
import sys
from pathlib import Path

assert os.environ.get("QT_QPA_PLATFORM") == "offscreen", "never open a window on the real screen"

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from manim_presentations.presenter import open_presenter

app = QApplication(sys.argv)
window = open_presenter(Path(sys.argv[1]).expanduser(), None)


def shoot() -> None:
    window.showNormal()  # open_presenter maximizes, and the offscreen screen is ~800 px
    window.resize(1728, 1117)
    print("size", window.size().width(), window.size().height(), flush=True)
    print("saved", window.grab().save("/tmp/mpres-presenter-mixing-deluxe.png"), flush=True)
    window.close()
    QTimer.singleShot(2000, app.quit)


QTimer.singleShot(8000, shoot)  # the Audience connects within a few seconds; the status line then shows it
app.exec()
