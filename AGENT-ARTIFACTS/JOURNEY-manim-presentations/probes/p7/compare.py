import json, sys
from pathlib import Path
import av, numpy as np
o = Path("out")
p1 = json.load(open(o/"pass1/pass1.json"))["digests"]
plain = json.load(open(o/"plain/plain.json"))["parts"]
def frames(path):
    with av.open(path) as c:
        return [f.to_ndarray(format="rgb24") for f in c.decode(video=0)]
ok = True
SUF = sys.argv[1] if len(sys.argv) > 1 else ""
for f in (0, 2, 7, 8, 10):
    t = json.load(open(o/f"tee/tee{f}{SUF}.json"))
    bad = [(n, d) for n, d in t["digests"] if d != p1[n]]
    pix = []
    for n, part in enumerate(t["parts"]):
        if part is None: continue
        a, b = frames(part), frames(plain[n])
        pix.append((n, len(a) == len(b) and all(np.array_equal(x, y) for x, y in zip(a, b)), len(a)))
    allpix = all(e for _, e, _ in pix)
    ok &= not bad and allpix
    print(f"from {f}: digests {len(t['digests'])} rendered, mismatches {bad}; pixels equal {allpix} {[(n,k) for n,e,k in pix if not e]}; parts {[n for n,_,_ in pix]}")
print("ALL OK" if ok else "FAIL")
