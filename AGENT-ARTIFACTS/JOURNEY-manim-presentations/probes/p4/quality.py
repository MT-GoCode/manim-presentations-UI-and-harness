"""Quality of each export variant as an audience sees it on a 1080p display.

Reference = the 3456x2168 source scaled to 1722x1080; distorted = the export scaled to 1722x1080. So the score
counts both the resolution loss and the crf loss. VMAF (and its PSNR feature) per clip; text crops as PNGs.
Grids in crops/<name>_grid.png: columns = reference, h1080, h720, h540; rows = crf 20, 23, 28 (reference repeats).
Usage: uv run quality.py
"""

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
HEIGHTS, CRFS = (1080, 720, 540), (20, 23, 28)
CLIPS = ("clip001", "clip011", "clip015", "clip027")
# (clip, frame, crop as fractions x0, y0, x1, y1): the smallest text in the talk.
CROPS = {"onejob_text": ("clip001", 200, 0.0, 0.33, 0.5, 0.60), "eval_digits": ("clip015", 200, 0.48, 0.22, 0.98, 0.48)}
DW, DH = 1722, 1080
VF = f"scale={DW}:{DH}:flags=bicubic,format=yuv420p"


def ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def vmaf(clip: str, h: int, crf: int) -> dict:
    log = HERE / "results" / "vmaf" / f"{clip}_h{h}_crf{crf}.json"
    ff("-i", str(HERE / "out" / f"h{h}_crf{crf}" / f"{clip}.mp4"), "-i", str(HERE / "src" / f"{clip}.mp4"),
       "-lavfi", f"[0]{VF}[d];[1]{VF}[r];[d][r]libvmaf=n_threads=2:feature=name=psnr:log_fmt=json:log_path={log}",
       "-f", "null", "-")
    pooled = json.loads(log.read_text())["pooled_metrics"]
    return {"clip": clip, "height": h, "crf": crf, "vmaf_mean": pooled["vmaf"]["mean"], "vmaf_min": pooled["vmaf"]["min"],
            "psnr_y": pooled["psnr_y"]["mean"]}


def crop(name: str, src: Path, frame: int, box: tuple, out: Path) -> None:
    x0, y0, x1, y1 = box
    ff("-i", str(src), "-vf", f"select=eq(n\\,{frame}),{VF},crop={round((x1 - x0) * DW)}:{round((y1 - y0) * DH)}:{round(x0 * DW)}:{round(y0 * DH)}",
       "-frames:v", "1", str(out))


def crops() -> None:
    d = HERE / "crops"
    d.mkdir(exist_ok=True)
    for name, (clip, frame, *box) in CROPS.items():
        crop(name, HERE / "src" / f"{clip}.mp4", frame, box, d / f"{name}_reference.png")
        rows = []
        for crf in CRFS:
            cells = [d / f"{name}_reference.png"]
            for h in HEIGHTS:
                p = d / f"{name}_h{h}_crf{crf}.png"
                crop(name, HERE / "out" / f"h{h}_crf{crf}" / f"{clip}.mp4", frame, box, p)
                cells.append(p)
            row = d / f"{name}_row_crf{crf}.png"
            ff(*sum([["-i", str(c)] for c in cells], []), "-filter_complex", f"hstack=inputs={len(cells)}", str(row))
            rows.append(row)
        ff(*sum([["-i", str(r)] for r in rows], []), "-filter_complex", f"vstack=inputs={len(rows)}", str(d / f"{name}_grid.png"))
        for r in rows:
            r.unlink()


if __name__ == "__main__":
    (HERE / "results" / "vmaf").mkdir(parents=True, exist_ok=True)
    grid = [(c, h, crf) for c in CLIPS for h in HEIGHTS for crf in CRFS]
    with ThreadPoolExecutor(4) as ex:  # 4 x libvmaf n_threads=2 = 8 cores, the same cap as the encode sweep
        rows = list(ex.map(lambda a: vmaf(*a), grid))
    crops()
    (HERE / "results" / "quality.json").write_text(json.dumps(rows, indent=1))
    for h in HEIGHTS:
        for crf in CRFS:
            sel = [r for r in rows if r["height"] == h and r["crf"] == crf]
            print(f"h{h} crf{crf}: vmaf mean {sum(r['vmaf_mean'] for r in sel) / len(sel):.2f}, "
                  f"worst-frame {min(r['vmaf_min'] for r in sel):.2f}, psnr_y {sum(r['psnr_y'] for r in sel) / len(sel):.2f}", flush=True)
