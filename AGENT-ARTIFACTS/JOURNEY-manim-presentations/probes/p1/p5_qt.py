"""P1(a,b,c,d,f) + P5 Qt playback probe. One process = one QT_MEDIA_BACKEND x one widget stack.

Usage: QT_QPA_PLATFORM=offscreen uv run python p5_qt.py --backend <darwin|ffmpeg|any name> \
         --stack <widget|sinkpaint> --clips DIR --res 1920x1080 [--res ...] --reps 5 --out result.json \
         [--checks backend,a,b,c,f,k,seek,unlink]

"Presented" means: the frame the stack's QVideoSink holds (videoFrameChanged), read in the GUI thread.
Clip frames carry a 12-bit pixel code (make_clips.py): bits 0-7 frame index, bits 8-11 clip id.
"""

import argparse
import ctypes
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
    sys.exit("refusing to run: QT_QPA_PLATFORM must be offscreen")

from PySide6.QtCore import QEventLoop, QObject, QRect, QTimer, QUrl, Slot
from PySide6.QtGui import QPainter
from PySide6.QtMultimedia import QMediaPlayer, QVideoFrame, QVideoFrameFormat, QVideoSink
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QApplication, QWidget

FPS = 30
FRAME_US = 1_000_000 / FPS
COLS, ROWS = 4, 3
CLIP_IDS = {"A": 1, "B": 2, "L": 3, "S": 4}
PF = QVideoFrameFormat.PixelFormat
LUMA_PLANE = {PF.Format_NV12, PF.Format_NV21, PF.Format_YUV420P, PF.Format_YV12, PF.Format_IMC1,
              PF.Format_IMC2, PF.Format_IMC3, PF.Format_IMC4, PF.Format_YUV422P, PF.Format_Y8}
LUMA_PLANE16 = {PF.Format_P010, PF.Format_P016, PF.Format_Y16, PF.Format_YUV420P10}
RGB32 = {PF.Format_ARGB8888, PF.Format_ARGB8888_Premultiplied, PF.Format_XRGB8888, PF.Format_BGRA8888,
         PF.Format_BGRA8888_Premultiplied, PF.Format_BGRX8888, PF.Format_ABGR8888, PF.Format_XBGR8888,
         PF.Format_RGBA8888, PF.Format_RGBX8888}

now = time.perf_counter


# ---------- backend identity ----------
def loaded_media_plugins() -> list[str]:
    lib = ctypes.CDLL(None)
    lib._dyld_image_count.restype = ctypes.c_uint32
    lib._dyld_get_image_name.restype = ctypes.c_char_p
    lib._dyld_get_image_name.argtypes = [ctypes.c_uint32]
    names = (lib._dyld_get_image_name(i).decode() for i in range(lib._dyld_image_count()))
    return sorted({Path(n).name for n in names if "mediaplugin" in Path(n).name})


# ---------- frame decoding ----------
def sample_points(w: int, h: int):
    cw, ch = w // COLS, h // ROWS
    cells = [((b % COLS) * cw + cw // 2, (b // COLS) * ch + ch // 2) for b in range(COLS * ROWS)]
    # two points in cell 0's gray margin; make_clips' sweeping bar is narrower than their spacing, so it covers at most one
    bgs = [(cw // 10, ch // 10), (cw - cw // 10, ch // 10)]
    return cells, bgs


def decode(frame: QVideoFrame) -> dict:
    """Pixel identity of a presented frame: code, gray-background check, how it was read."""
    w, h = frame.width(), frame.height()
    cells, bgs = sample_points(w, h)
    fmt = frame.pixelFormat()
    if frame.map(QVideoFrame.MapMode.ReadOnly):
        try:
            bpl = frame.bytesPerLine(0)
            mv = frame.bits(0)
            if fmt in LUMA_PLANE:
                px = lambda x, y: mv[y * bpl + x]
            elif fmt in LUMA_PLANE16:
                px = lambda x, y: mv[y * bpl + 2 * x + 1]
            elif fmt in RGB32:
                px = lambda x, y: mv[y * bpl + 4 * x + 1]
            else:
                raise RuntimeError(f"unhandled pixel format {fmt}")
            vals = [px(x, y) for x, y in cells]
            bgv = [px(*b) for b in bgs]
            how = "map"
        finally:
            frame.unmap()
    else:
        img = frame.toImage()
        vals = [img.pixelColor(x, y).green() for x, y in cells]
        bgv = [img.pixelColor(*b).green() for b in bgs]
        how = "toImage"
    # mid-gray background is ~126 (limited-range Y) or ~128 (RGB); black is 16/0
    lo, hi = min(16, 0), 255
    thr = (lo + 235) / 2
    code = sum((1 << i) for i, v in enumerate(vals) if v > thr)
    return {"code": code, "bg": bgv, "real": any(abs(v - 127) < 30 for v in bgv), "how": how, "fmt": fmt.name, "w": w, "h": h}


# ---------- stacks ----------
class SinkPaint(QWidget):
    """QVideoSink frames painted in a plain QWidget."""

    def __init__(self):
        super().__init__()
        self._sink = QVideoSink(self)
        self._sink.videoFrameChanged.connect(self.update)
        self.paint_ms: list[float] = []

    def videoSink(self) -> QVideoSink:
        return self._sink

    def paintEvent(self, _):
        t = now()
        p = QPainter(self)
        p.fillRect(self.rect(), 0)
        f = self._sink.videoFrame()
        if f.isValid():
            fs = f.size().scaled(self.size(), __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.AspectRatioMode.KeepAspectRatio)
            r = QRect((self.width() - fs.width()) // 2, (self.height() - fs.height()) // 2, fs.width(), fs.height())
            f.paint(p, r, QVideoFrame.PaintOptions())
        p.end()
        self.paint_ms.append((now() - t) * 1000)


class Recorder(QObject):
    def __init__(self, sink: QVideoSink, player: QMediaPlayer | None = None):
        super().__init__()
        self.log: list[dict] = []
        self.last_valid: QVideoFrame | None = None
        self.sink = sink
        sink.videoFrameChanged.connect(self.on_frame)
        if player is not None:
            self.attach(player)

    def attach(self, player: QMediaPlayer):
        player.mediaStatusChanged.connect(lambda s: self.log.append({"t": now(), "ev": "status", "v": s.name}))
        player.playbackStateChanged.connect(lambda s: self.log.append({"t": now(), "ev": "state", "v": s.name}))
        player.errorOccurred.connect(lambda e, m: self.log.append({"t": now(), "ev": "error", "v": f"{e.name}: {m}"}))

    @Slot(QVideoFrame)
    def on_frame(self, f: QVideoFrame):
        e = {"t": now(), "ev": "frame", "valid": f.isValid(), "start": f.startTime() if f.isValid() else None}
        if f.isValid():
            e.update(decode(f))
            if e["real"]:
                self.last_valid = QVideoFrame(f)
        self.log.append(e)

    def frames(self, since: float = 0.0):
        return [e for e in self.log if e["ev"] == "frame" and e["t"] >= since]

    def mark(self, name: str):
        self.log.append({"t": now(), "ev": "mark", "v": name})


def wait(pred, timeout_s: float) -> bool:
    if pred():
        return True
    loop, timer, deadline = QEventLoop(), QTimer(), now() + timeout_s
    timer.setInterval(1)
    timer.timeout.connect(lambda: (pred() or now() > deadline) and loop.quit())
    timer.start()
    loop.exec()
    timer.stop()
    return pred()


def settle(s: float):
    wait(lambda: False, s)


class Rig:
    """One shown window with the chosen stack, one QMediaPlayer feeding it."""

    def __init__(self, stack: str):
        self.stack = stack
        self.view = QVideoWidget() if stack == "widget" else SinkPaint()
        self.view.resize(1728, 1084)
        self.view.show()
        self.new_player()

    def new_player(self):
        if getattr(self, "player", None) is not None:
            self.player.stop()
            self.player.setVideoOutput(None)
            self.player.deleteLater()
        self.player = QMediaPlayer()
        sink = self.view.videoSink()
        if self.stack == "widget":
            self.player.setVideoOutput(self.view)
        else:
            self.player.setVideoSink(sink)
        if getattr(self, "rec", None) is None:
            self.rec = Recorder(sink)
        self.rec.attach(self.player)
        self.hold_on_end = False
        self.player.mediaStatusChanged.connect(self._on_status)
        return self.player

    def _on_status(self, s):
        if s == QMediaPlayer.MediaStatus.EndOfMedia and self.hold_on_end and self.rec.last_valid is not None:
            self.view.videoSink().setVideoFrame(self.rec.last_valid)
            self.rec.mark("reset-sink-frame")

    def sink_now(self) -> dict:
        f = self.view.videoSink().videoFrame()
        return {"valid": f.isValid(), **(decode(f) if f.isValid() else {})}

    def eom(self) -> bool:
        return self.player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia


def code(clip: str, i: int) -> int:
    return (CLIP_IDS[clip] << 8) | i


def stats(xs):
    xs = [x for x in xs if x is not None]
    return {"n": len(xs), "median": statistics.median(xs) if xs else None, "max": max(xs) if xs else None,
            "min": min(xs) if xs else None}


def clip_url(p: Path) -> QUrl:
    return QUrl.fromLocalFile(str(p.resolve()))


# ---------- checks ----------
def check_a(rig: Rig, clips, reps, nframes=90):
    """Play to EndOfMedia; record what the sink holds afterwards without and with re-setting the sink frame."""
    out = {}
    for variant in ("raw", "reset"):
        runs = []
        for _ in range(reps):
            p = rig.new_player()
            rig.hold_on_end = variant == "reset"
            p.setSource(clip_url(clips["A"]))
            t0 = now()
            p.play()
            reached = wait(rig.eom, 10)
            t_end = now()
            settle(0.5)  # observation window after end-of-media
            fr = rig.rec.frames(t0)
            after = rig.rec.frames(t_end)
            valid = [e for e in fr if e["valid"] and e["real"] and e["code"] >> 8 == CLIP_IDS["A"]]
            runs.append({
                "missing_indices": sorted(set(range(nframes)) - {e["code"] & 0xFF for e in valid}),
                "reached_eom": reached,
                "last_presented_code": valid[-1]["code"] if valid else None,
                "last_start_us": valid[-1]["start"] if valid else None,
                "frames_presented": len(valid),
                "distinct_codes": len({e["code"] for e in valid}),
                "invalid_after_eom": sum(1 for e in after if not e["valid"]),
                "sink_after_500ms": rig.sink_now(),
                "state": rig.player.playbackState().name,
            })
        ok = [r["reached_eom"] and r["sink_after_500ms"].get("code") == code("A", nframes - 1) for r in runs]
        out[variant] = {"holds_last_frame": all(ok), "runs": runs}
    return out


def check_b(rig: Rig, clips, reps):
    """Single-buffered switch: A held at end, then setSource(B)+play(). Latency + any invalid/black frame between."""
    runs = []
    for _ in range(reps):
        p = rig.new_player()
        rig.hold_on_end = True
        p.setSource(clip_url(clips["A"]))
        p.play()
        wait(rig.eom, 10)
        settle(0.3)
        t0 = now()
        p.setSource(clip_url(clips["B"]))
        p.play()
        got_b = wait(lambda: any(e["valid"] and e["real"] and e["code"] >> 8 == 2 for e in rig.rec.frames(t0)), 5)
        between = []
        for e in rig.rec.frames(t0):
            if e["valid"] and e["real"] and e["code"] >> 8 == 2:
                first_b = e
                break
            between.append(e)
        wait(rig.eom, 10)
        runs.append({
            "got_b": got_b,
            "latency_ms": (first_b["t"] - t0) * 1000 if got_b else None,
            "first_b_index": first_b["code"] & 0xFF if got_b else None,
            "invalid_between": sum(1 for e in between if not e["valid"]),
            "black_between": sum(1 for e in between if e["valid"] and not e["real"]),
            "other_between": [e.get("code") for e in between if e["valid"] and e["real"]],
        })
    return {"runs": runs, "latency_ms": stats([r["latency_ms"] for r in runs]),
            "any_empty_or_black": any(r["invalid_between"] or r["black_between"] for r in runs),
            "all_first_b_is_frame0": all(r["first_b_index"] == 0 for r in runs)}


def loop_analysis(fr, nframes=90):
    """Intervals between presented frames; wrap = frame index decreasing. Frames before this run's first frame 0
    are the previous run's leftovers in the sink and are dropped."""
    i0 = next((i for i, e in enumerate(fr) if e["valid"] and e["real"] and e["code"] & 0xFF == 0), len(fr))
    fr = fr[i0:]
    v = [e for e in fr if e["valid"] and e["real"]]
    normal, wraps, drops, wrap_drops = [], [], 0, 0
    for a, b in zip(v, v[1:]):
        ia, ib = a["code"] & 0xFF, b["code"] & 0xFF
        dt = (b["t"] - a["t"]) * 1000
        if ib < ia:
            wraps.append({"dt_ms": dt, "from": ia, "to": ib, "start_from": a["start"], "start_to": b["start"]})
            wrap_drops += (nframes - 1 - ia) + ib
        else:
            normal.append(dt)
            drops += max(0, ib - ia - 1)
    return {"normal_dt_ms": stats(normal), "wraps": wraps, "drops_not_at_wrap": drops, "drops_at_wrap": wrap_drops,
            "invalid": sum(1 for e in fr if not e["valid"]), "black": sum(1 for e in fr if e["valid"] and not e["real"]),
            "seq": [(e["code"] & 0xFF if e["valid"] and e["real"] else -1, round((e["t"] - fr[0]["t"]) * 1000, 1)) for e in fr] if fr else []}


def check_c(rig: Rig, clips, reps, cycles=2.3):
    runs = []
    for _ in range(reps):
        p = rig.new_player()
        p.setLoops(QMediaPlayer.Loops.Infinite)
        p.setSource(clip_url(clips["L"]))
        t0 = now()
        p.play()
        settle(3.0 * cycles)
        runs.append(loop_analysis(rig.rec.frames(t0)))
        p.stop()
    wrap_dts = [w["dt_ms"] for r in runs for w in r["wraps"]]
    normal_max = max(r["normal_dt_ms"]["max"] for r in runs if r["normal_dt_ms"]["max"] is not None)
    return {"runs": runs, "wrap_dt_ms": stats(wrap_dts), "normal_dt_ms_max_over_runs": normal_max,
            "normal_dt_ms_median_over_runs": statistics.median(r["normal_dt_ms"]["median"] for r in runs),
            "wraps_seen": len(wrap_dts), "drops_at_wrap": sum(r["drops_at_wrap"] for r in runs),
            "invalid_or_black": sum(r["invalid"] + r["black"] for r in runs)}


def cover_once(rig: Rig, clip: Path):
    p = rig.new_player()
    t0 = now()
    p.setSource(clip_url(clip))
    p.pause()
    cid = CLIP_IDS[clip.name[0]]
    got = wait(lambda: any(e["valid"] and e["real"] and e["code"] >> 8 == cid for e in rig.rec.frames(t0)), 5)
    t1 = now()
    settle(0.3)  # confirm nothing else presents while paused
    fr = [e for e in rig.rec.frames(t0) if e["valid"] and e["real"] and e["code"] >> 8 == CLIP_IDS[clip.name[0]]]
    return {"got": got, "ms": (fr[0]["t"] - t0) * 1000 if fr else None,
            "first_index": fr[0]["code"] & 0xFF if fr else None, "first_start_us": fr[0]["start"] if fr else None,
            "frames_while_paused": len(fr), "invalid": sum(1 for e in rig.rec.frames(t0) if not e["valid"]),
            "state": p.playbackState().name, "status": p.mediaStatus().name, "_t1": t1}


LOADED = (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia)


def hold_once(rig: Rig, clip: Path, pos_ms: int, last_idx: int, order: str = "after_loaded"):
    """order=immediate: setSource; pause; setPosition. order=after_loaded: wait for Loaded/BufferedMedia before setPosition."""
    p = rig.new_player()
    t0 = now()
    p.setSource(clip_url(clip))
    p.pause()
    if order == "after_loaded":
        wait(lambda: p.mediaStatus() in LOADED, 5)
    t_loaded = now()
    p.setPosition(pos_ms)
    t_set = now()
    want = code(clip.name[0], last_idx)
    hit = lambda: any(e["valid"] and e["real"] and e["code"] == want for e in rig.rec.frames(t0))
    got = wait(hit, 5)
    settle(0.3)
    fr = [e for e in rig.rec.frames(t0) if e["valid"] and e["real"] and e["code"] >> 8 == want >> 8]
    first_hit = next((e for e in fr if e["code"] == want), None)
    return {"pos_ms": pos_ms, "order": order, "got_last": got, "ms_load": (t_loaded - t0) * 1000, "ms_from_setSource": (first_hit["t"] - t0) * 1000 if first_hit else None,
            "ms_from_setPosition": (first_hit["t"] - t_set) * 1000 if first_hit else None,
            "presented_sequence": [(e["code"] & 0xFF, e["start"]) for e in fr],
            "shown_before_last": [e["code"] & 0xFF for e in fr[: fr.index(first_hit)]] if first_hit else None,
            "final_index": fr[-1]["code"] & 0xFF if fr else None, "final_start_us": fr[-1]["start"] if fr else None,
            "invalid": sum(1 for e in rig.rec.frames(t0) if not e["valid"]), "state": p.playbackState().name}


def check_f(rig: Rig, clips, reps, nframes=90):
    cover = [cover_once(rig, clips["A"]) for _ in range(reps)]
    for c in cover:
        c.pop("_t1")
    last_us = (nframes - 1) * FRAME_US
    dur_ms = nframes * 1000 // FPS
    positions = sorted({int(last_us // 1000), -(-int(last_us) // 1000), dur_ms - 1})
    hold = {f"{o}@{pos}": [hold_once(rig, clips["A"], pos, nframes - 1, o) for _ in range(reps)]
            for o in ("immediate", "after_loaded") for pos in positions}
    hold_ok = {pos: all(r["got_last"] and r["final_index"] == nframes - 1 and r["final_start_us"] is not None
                        and abs(r["final_start_us"] - last_us) < FRAME_US / 2 for r in rs) for pos, rs in hold.items()}
    return {"cover": cover,
            "cover_ok": all(c["got"] and c["first_index"] == 0 and c["first_start_us"] == 0 and c["frames_while_paused"] == 1
                            for c in cover),
            "cover_ms": stats([c["ms"] for c in cover]),
            "last_pts_us": last_us, "hold": {str(k): v for k, v in hold.items()},
            "hold_ok": {str(k): v for k, v in hold_ok.items()},
            "hold_ms_from_setSource": {str(k): stats([r["ms_from_setSource"] for r in v]) for k, v in hold.items()}}


def check_k(rig: Rig, clips, reps, nframes=90, kmax=12):
    """Fallback for Hold: play muted from last_pts - k*frame; smallest k that reliably reaches EndOfMedia on the last frame."""
    last_ms = (nframes - 1) * 1000 / FPS
    table = {}
    for k in range(0, kmax + 1):
        runs = []
        for _ in range(reps):
            p = rig.new_player()
            rig.hold_on_end = True
            p.setSource(clip_url(clips["A"]))
            wait(lambda: p.mediaStatus() in LOADED, 5)
            p.setPosition(max(0, round(last_ms - k * 1000 / FPS)))
            t0 = now()
            p.play()
            reached = wait(rig.eom, 3)
            settle(0.3)
            runs.append({"reached_eom": reached, "ms": (now() - t0) * 1000, "sink": rig.sink_now().get("code")})
        table[k] = {"ok": sum(r["reached_eom"] and r["sink"] == code("A", nframes - 1) for r in runs), "n": reps}
    good = [k for k, v in table.items() if v["ok"] == v["n"]]
    return {"table": table, "smallest_reliable_k": min(good) if good else None}


def check_seek(rig: Rig, clips, reps):
    """Worst-case paused seek: Hold on the ~6 s, g=6 clip (180 frames)."""
    last_us = 179 * FRAME_US
    pos = -(-int(last_us) // 1000)
    runs = [hold_once(rig, clips["S"], pos, 179) for _ in range(reps)]
    for r in runs:
        r.pop("presented_sequence")
    return {"pos_ms": pos, "runs": runs, "ms_from_setSource": stats([r["ms_from_setSource"] for r in runs]),
            "ms_from_setPosition": stats([r["ms_from_setPosition"] for r in runs]),
            "all_hit": all(r["got_last"] and r["final_index"] == 179 for r in runs)}


def check_unlink(rig: Rig, clips):
    tmp = Path(tempfile.mkdtemp()) / "loop.mp4"
    shutil.copy2(clips["L"], tmp)
    p = rig.new_player()
    p.setLoops(QMediaPlayer.Loops.Infinite)
    p.setSource(clip_url(tmp))
    t0 = now()
    p.play()
    settle(1.5)
    lsof = subprocess.run(["lsof", "-p", str(os.getpid())], capture_output=True, text=True).stdout
    open_fd = any(str(tmp.resolve()) in l or str(tmp) in l for l in lsof.splitlines())
    tmp.unlink()
    t_un = now()
    settle(3.0 * 3)
    after = loop_analysis(rig.rec.frames(t_un))
    p.stop()
    return {"open_fd_before_unlink": open_fd, "wraps_after_unlink": len(after["wraps"]),
            "frames_after_unlink": sum(1 for e in rig.rec.frames(t_un) if e["valid"] and e["real"]),
            "errors": [e["v"] for e in rig.rec.log if e["ev"] == "error" and e["t"] >= t0],
            "invalid_after": after["invalid"], "state": p.playbackState().name}


def check_start(rig: Rig, clips, reps, nframes=90):
    """Which frames are skipped at playback start: direct setSource+play() vs paused Cover then play()."""
    out = {}
    for variant in ("direct", "cover_then_play"):
        runs = []
        for _ in range(reps):
            p = rig.new_player()
            t_src = now()
            p.setSource(clip_url(clips["A"]))
            if variant == "cover_then_play":
                p.pause()
                wait(lambda: any(e["valid"] and e["real"] and e["code"] == code("A", 0) for e in rig.rec.frames(t_src)), 5)
                settle(0.3)
            t0 = now()
            p.play()
            wait(rig.eom, 10)
            v = [e for e in rig.rec.frames(t0) if e["valid"] and e["real"] and e["code"] >> 8 == CLIP_IDS["A"]]
            seen = {e["code"] & 0xFF for e in v}
            if variant == "cover_then_play":
                seen.add(0)  # frame 0 was presented by the Cover before play()
            runs.append({"missing": sorted(set(range(nframes)) - seen),
                         "first_frames": [(e["code"] & 0xFF, round((e["t"] - t0) * 1000, 1)) for e in v[:6]]})
        out[variant] = runs
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", required=True, help="exported as QT_MEDIA_BACKEND before QApplication")
    ap.add_argument("--stack", choices=["widget", "sinkpaint"], required=True)
    ap.add_argument("--clips", type=Path, required=True)
    ap.add_argument("--res", action="append", required=True)
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--checks", default="backend,a,b,c,f,seek,unlink")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    checks = a.checks.split(",")
    os.environ["QT_MEDIA_BACKEND"] = a.backend
    app = QApplication([])
    result = {"requested_backend": os.environ.get("QT_MEDIA_BACKEND"), "stack": a.stack,
              "qt": __import__("PySide6").__version__, "platform": app.platformName(),
              "dpr": None, "by_res": {}}
    rig = Rig(a.stack)
    result["dpr"] = rig.view.devicePixelRatio()
    result["loaded_media_plugins"] = loaded_media_plugins()
    print(f"[{result['requested_backend']}/{a.stack}] loaded={result['loaded_media_plugins']}", flush=True)
    for res in a.res:
        clips = {n: a.clips / f"{n}_{res}.mp4" for n in CLIP_IDS}
        r = result["by_res"][res] = {}
        for c in checks:
            if c == "backend" or (c == "seek" and not clips["S"].exists()):
                continue
            t = now()
            fn = {"a": check_a, "b": check_b, "c": check_c, "f": check_f, "k": check_k, "seek": check_seek, "start": check_start}.get(c)
            la = os.getloadavg()
            r[c] = check_unlink(rig, clips) if c == "unlink" else fn(rig, clips, a.reps)
            r[c]["loadavg_1m_before_after"] = [la[0], os.getloadavg()[0]]
            print(f"[{result['requested_backend']}/{a.stack}/{res}] {c} done in {now() - t:.1f}s", flush=True)
            a.out.write_text(json.dumps(result, indent=1, default=str))
    if isinstance(rig.view, SinkPaint):
        result["paint_ms"] = stats(rig.view.paint_ms)
    result["loaded_media_plugins_end"] = loaded_media_plugins()
    a.out.write_text(json.dumps(result, indent=1, default=str))
    print(f"wrote {a.out}", flush=True)


if __name__ == "__main__":
    main()
