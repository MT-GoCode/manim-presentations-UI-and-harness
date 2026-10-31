"""P1(a) detail: event order around EndOfMedia (does an empty frame reach the sink before the hold re-set?)."""
import os, sys
sys.argv = [sys.argv[0]]
os.environ["QT_MEDIA_BACKEND"] = "ffmpeg"
import p5_qt as P
from PySide6.QtWidgets import QApplication

app = QApplication([])
for stack in ("widget", "sinkpaint"):
  for res in ("1920x1080", "3456x2168"):
    for hold in (True,) * 3:
        rig = P.Rig(stack)
        p = rig.new_player()
        rig.hold_on_end = hold
        t0 = P.now()
        p.setSource(P.clip_url(P.Path(f"clips/A_{res}.mp4")))
        p.play()
        P.wait(rig.eom, 10)
        P.settle(0.5)
        tail = [e for e in rig.rec.log if e["t"] >= t0][-6:]
        print(stack, res, "hold" if hold else "raw",
              [(e["ev"], e.get("v", e.get("code") if e.get("valid") else "INVALID"), round((e["t"] - tail[0]["t"]) * 1000, 2)) for e in tail])
