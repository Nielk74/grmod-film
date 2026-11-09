"""Builds the sheets, 100% crops, full-size JPEGs and memory/time numbers into scratch/lens-characters/."""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from lens_characters import *

OUT = os.path.join(os.path.dirname(__file__), '..', '..', 'scratch', 'lens-characters')
OUT = os.path.abspath(OUT)
def P(n):
    for d in ('Ricoh2', 'Ricoh'):
        p = 'C:/Users/Antoine/Pictures/%s/%s.JPG' % (d, n)
        if os.path.exists(p):
            return p
SCENES = {
    'swirl': ['AK000137', 'AK000002', 'AK000104', 'R0000030', 'AK000129'],
    'mist': ['AK000106', 'R0000047', 'AK000137', 'AK000129', 'R0000028'],
    'corners': ['AK000129', 'R0000047', 'R0000024', 'AK000063'],
}
FULL = {'swirl': 'AK000137', 'mist': 'R0000047', 'corners': 'AK000129'}
CROP = {'swirl': (3300, 0, 900, 700), 'mist': (1500, 1200, 900, 700), 'corners': (5100, 0, 900, 700)}  # x, y, w, h in the full picture

which = sys.argv[1:] or ['swirl', 'mist', 'corners']
meas = {}
for kind in which:
    rows = []
    for n in SCENES[kind]:
        rows.append((n, [orig_rgb(P(n), 3000), run(kind, P(n), 'medium', 3000), run(kind, P(n), 'strong', 3000)]))
    make_sheet(rows, os.path.join(OUT, 'sheet-%s.png' % kind))
    # full size, Strong
    n = FULL[kind]
    y, cb, cr = load_422(P(n))
    f, tab = FUNCS[kind]
    tracemalloc.start()
    t = time.time()
    o = f(y, cb, cr, tab['strong'])
    dt = time.time() - t
    cur, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
    meas[kind] = dict(peak_mb=round((peak - cur) / 1e6 + 0, 1), out_mb=round(o.nbytes / 1e6, 1), sec=round(dt, 1), mp=round(y.size / 1e6, 1))
    Image.fromarray(o).save(os.path.join(OUT, 'full-%s-strong-%s.jpg' % (kind, n)), quality=95)
    a = np.clip(planes_to_rgb(y, cb, cr) + .5, 0, 255).astype(np.uint8)
    x0, y0, cw, ch = CROP[kind]
    c = np.concatenate([a[y0:y0 + ch, x0:x0 + cw], o[y0:y0 + ch, x0:x0 + cw]], 1)
    Image.fromarray(c).save(os.path.join(OUT, '_crop_%s.png' % kind))
    print(kind, meas[kind], flush=True)
json.dump(meas, open(os.path.join(OUT, '_meas_%s.json' % '_'.join(which)), 'w'))
