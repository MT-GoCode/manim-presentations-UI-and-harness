"""Print the P1 verdict tables from results/*.json."""

import json
import sys
from pathlib import Path

R = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "results"
f1 = lambda x: "-" if x is None else f"{x:.1f}"

for path in sorted(R.glob("*.json")):
    d = json.loads(path.read_text())
    print(f"\n## {path.stem}: requested={d['requested_backend']} stack={d['stack']} loaded={d['loaded_media_plugins']}"
          f" end={d.get('loaded_media_plugins_end')} dpr={d['dpr']} paint_ms={d.get('paint_ms')}")
    for res, r in d["by_res"].items():
        print(f"### {res}  loadavg_1m: " + str({c: [round(x, 1) for x in v["loadavg_1m_before_after"]] for c, v in r.items() if isinstance(v, dict) and "loadavg_1m_before_after" in v}))
        if "a" in r:
            for v, x in ((k, x) for k, x in r["a"].items() if isinstance(x, dict)):
                rs = x["runs"]
                print(f"(a) {v}: holds_last={x['holds_last_frame']} eom={sum(q['reached_eom'] for q in rs)}/{len(rs)}"
                      f" frames={[q['frames_presented'] for q in rs]} distinct={[q['distinct_codes'] for q in rs]}"
                      f" missing={[q.get('missing_indices') for q in rs]} sink_after={[q['sink_after_500ms'].get('code') for q in rs]} invalid_after_eom={[q['invalid_after_eom'] for q in rs]}")
        if "b" in r:
            b = r["b"]
            print(f"(b) latency_ms med={f1(b['latency_ms']['median'])} max={f1(b['latency_ms']['max'])} n={b['latency_ms']['n']}"
                  f" empty_or_black={b['any_empty_or_black']} first_b_frame0={b['all_first_b_is_frame0']}"
                  f" between={[(q['invalid_between'], q['black_between'], q['other_between']) for q in b['runs']]}")
        if "c" in r:
            c = r["c"]
            print(f"(c) wraps={c['wraps_seen']} wrap_dt med={f1(c['wrap_dt_ms']['median'])} max={f1(c['wrap_dt_ms']['max'])}"
                  f" | normal_dt med={f1(c['normal_dt_ms_median_over_runs'])} max={f1(c['normal_dt_ms_max_over_runs'])}"
                  f" drops_at_wrap={c['drops_at_wrap']} drops_elsewhere={sum(q['drops_not_at_wrap'] for q in c['runs'])}"
                  f" invalid_or_black={c['invalid_or_black']}")
        if "f" in r:
            f = r["f"]
            print(f"(f) cover_ok={f['cover_ok']} cover_ms med={f1(f['cover_ms']['median'])} max={f1(f['cover_ms']['max'])}"
                  f" cover_first={[(q['first_index'], q['first_start_us'], q['frames_while_paused']) for q in f['cover']]}")
            for k, ok in f["hold_ok"].items():
                rs = f["hold"][k]
                s = f["hold_ms_from_setSource"][k]
                print(f"    hold {k}: ok={ok} final={[(q['final_index'], q['final_start_us']) for q in rs]}"
                      f" before_last={[q.get('shown_before_last') for q in rs]} ms med={f1(s['median'])} max={f1(s['max'])}")
        if "k" in r:
            print(f"(k) smallest_reliable_k={r['k']['smallest_reliable_k']} table={ {k: f'{v['ok']}/{v['n']}' for k, v in r['k']['table'].items()} }")
        if "seek" in r:
            s = r["seek"]
            print(f"(seek) all_hit={s['all_hit']} from_setSource med={f1(s['ms_from_setSource']['median'])} max={f1(s['ms_from_setSource']['max'])}"
                  f" from_setPosition med={f1(s['ms_from_setPosition']['median'])} max={f1(s['ms_from_setPosition']['max'])}"
                  f" load_ms={[round(q['ms_load'], 1) for q in s['runs']]} before_last={[q['shown_before_last'] for q in s['runs']]}")
        if "unlink" in r:
            print(f"(unlink) {r['unlink']}")
        if "start" in r:
            for v, rs in ((k, x) for k, x in r["start"].items() if k != "loadavg_1m_before_after"):
                print(f"(start) {v}: missing={[q['missing'] for q in rs]} first={rs[0]['first_frames']}")
