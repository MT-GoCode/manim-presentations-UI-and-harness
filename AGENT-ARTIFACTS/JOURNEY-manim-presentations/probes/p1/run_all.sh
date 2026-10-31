#!/usr/bin/env bash
# Full P1 matrix. Headless only. Runs serially so no run contends with another for the decoder.
set -euo pipefail
cd "$(dirname "$0")"
export QT_QPA_PLATFORM=offscreen QT_SCALE_FACTOR=2  # scale 2 = Retina device pixel ratio, as on stage
mkdir -p results
[ -f clips/S_3456x2168.mp4 ] || uv run python -u make_clips.py clips
run() { uv run python -u p5_qt.py --backend "$1" --stack "$2" --clips clips --res 3456x2168 --res 1920x1080 \
          --reps "$3" --checks "$4" --out "results/$1_$2.json" 2>&1 | grep --line-buffered -E '^\[|Traceback|Error|wrote'; }
# darwin cannot load media under offscreen (see P1.md); one rep documents the failure per stack x resolution
for s in widget sinkpaint; do [ -f results/darwin_$s.json ] || run darwin $s 1 backend,a,f; done
# timing runs hold the machine-wide heavy-work lock so no other probe skews real-time playback
for s in widget sinkpaint; do flock /tmp/mpres-heavy.lock bash -c "$(declare -f run); run ffmpeg $s 5 backend,a,b,c,f,k,seek,unlink,start"; done
# requested backend that cannot load
for b in bogus windows; do
  uv run python -u p5_qt.py --backend $b --stack widget --clips clips --res 480x270 --reps 1 --checks a \
    --out "results/missing_$b.json" 2>&1 | grep --line-buffered -E '^\[|Traceback|Error|wrote|plugin|backend' || true
done
uv run python -u fonts.py
