"""P5: MIN_SAMPLE_WINDOW = the shortest window whose idle_cores spread on an idle machine stays under 0.5 cores.
idle_cores = cpu_count − busy, busy = Σ over CPUs of (1 − idle fraction) in the window (psutil cpu_times_percent)."""
import json
import os
import statistics
import sys

import psutil

N = os.cpu_count()
out = {"cpu_count": N, "ram_total": psutil.virtual_memory().total, "ram_available": psutil.virtual_memory().available,
       "windows": {}}
for w in (0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0):
    vals = []
    for _ in range(int(sys.argv[1]) if len(sys.argv) > 1 else 12):
        per = psutil.cpu_times_percent(interval=w, percpu=True)
        busy = sum(100 - p.idle for p in per) / 100
        vals.append(N - busy)
    out["windows"][w] = {"min": min(vals), "max": max(vals), "spread": max(vals) - min(vals),
                         "median": statistics.median(vals)}
    print(f"window {w:>5}s idle_cores min {min(vals):.2f} max {max(vals):.2f} spread {max(vals)-min(vals):.2f}", flush=True)
print(json.dumps(out))
