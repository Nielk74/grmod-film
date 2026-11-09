"""Comparison sheet for swirl2: original and the three lens types, on real photographs."""
import glob
import os
import sys
import time

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
from lens_characters import load_422, panel, planes_to_rgb
from swirl2 import LENSES, swirl

ROOTS = [r"C:\Users\Antoine\Pictures\Ricoh", r"C:\Users\Antoine\Pictures\Ricoh2", r"C:\Users\Antoine\Pictures\Recover"]
# bokeh dots at night, blurred daylight backgrounds, then frames that should stay untouched
SCENES = ['AK000137', 'R0000030', 'AK000076', 'R0000029', '$MG_1025', '$MG_1080', 'AK000145', 'AK000106', 'AK000129']
OUT = os.path.join(os.path.dirname(__file__), '..', '..', 'scratch', 'lens-characters', 'v2')


def find(name):
    for root in ROOTS:
        hits = glob.glob(os.path.join(root, '**', glob.escape(name) + '.[jJ][pP][gG]'), recursive=True)
        if hits:
            return hits[0]
    return None


rows = []
for name in SCENES:
    path = find(name)
    if path is None:
        print('missing', name, flush=True)
        continue
    y, cb, cr = load_422(path)
    cells = [panel(np.clip(planes_to_rgb(y, cb, cr) + 0.5, 0, 255).astype(np.uint8), 900, name + '  Original')]
    for lens, params in LENSES.items():
        start = time.time()
        img, info = swirl(y, cb, cr, params)
        print(name, lens, 'discs', len(info['discs']), 'recovered', info['sources'], round(time.time() - start, 1), 's', flush=True)
        cells.append(panel(img, 900, lens))
        if name == 'AK000137':
            Image.fromarray(img).save(os.path.join(OUT, 'full-' + lens + '-' + name + '.jpg'), quality=95)
    rows.append(cells)

gap = 6
heights = [max(c.height for c in r) for r in rows]
sheet = Image.new('RGB', (4 * 900 + 3 * gap, sum(heights) + gap * (len(rows) - 1)), (20, 20, 20))
top = 0
for r, height in zip(rows, heights):
    for k, c in enumerate(r):
        sheet.paste(c, (k * (900 + gap), top))
    top += height + gap
sheet.save(os.path.join(OUT, 'sheet-swirl-v2.png'))
print('done', flush=True)
