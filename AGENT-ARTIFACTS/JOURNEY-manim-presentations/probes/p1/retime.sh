#!/usr/bin/env bash
# Re-take the 3456x2168 real-time timings (switch, seek, start) per stack, each holding the heavy-work lock for ~1 min.
set -euo pipefail
cd "$(dirname "$0")"
export QT_QPA_PLATFORM=offscreen QT_SCALE_FACTOR=2
for s in widget sinkpaint; do
  flock /tmp/mpres-heavy.lock uv run python -u p5_qt.py --backend ffmpeg --stack $s --clips clips --res 3456x2168 \
    --reps 5 --checks b,seek,start --out results/retime_ffmpeg_$s.json 2>&1 | grep --line-buffered -E '^\[|Traceback|Error|wrote'
done
