"""For every film: how far is the camera's matrix-and-curves result from the film's authored look, on real photos?
Mean OkLab distance x100, overall and for skin, plants, sky and whites. A big gap is what a colour LUT could recover."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

import common
from common import OUT, load_rgb8, srgb_to_oklab
from sheets import path_of

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CUBES = os.path.join(ROOT, 'examples', 'gr3x', 'film-pack-v3', 'out', 'cube')
SCENES = ['R0000022', 'R0000023', 'R0000027', 'R0000020', 'R0000030', 'R0000005', 'AK000164', 'R0000016', 'R0000004', 'R0000032']
WIDTH = 1200


def read_cube(path):
    with open(path, encoding='utf-8') as fh:
        rows = [ln.split() for ln in fh if ln.strip() and (ln[0].isdigit() or ln[0] == '-')]
    n = round(len(rows) ** (1 / 3))
    return np.array(rows, np.float32).reshape(n, n, n, 3)  # indexed [b][g][r], the .cube order


def apply_cube(rgb8, cube):
    n = cube.shape[0]
    p = rgb8.astype(np.float32) / 255 * (n - 1)
    i = np.clip(p.astype(np.int32), 0, n - 2)
    f = p - i
    out = 0.0
    for db in (0, 1):
        for dg in (0, 1):
            for dr in (0, 1):
                w = (f[..., 2] if db else 1 - f[..., 2]) * (f[..., 1] if dg else 1 - f[..., 1]) * (f[..., 0] if dr else 1 - f[..., 0])
                out = out + w[..., None] * cube[i[..., 2] + db, i[..., 1] + dg, i[..., 0] + dr]
    return np.clip(np.round(out * 255), 0, 255).astype(np.uint8)


def main():
    coef = json.load(open(os.path.join(OUT, 'coef-all.json'), encoding='utf8'))
    common._coef = coef
    films = [k for k in coef if k not in ('S', 'Sinv', 'standardQ13')]
    photos = []
    for s in SCENES:
        std = load_rgb8(path_of(s), WIDTH)
        lab = srgb_to_oklab(std / 255.0)
        L, C = lab[..., 0], np.hypot(lab[..., 1], lab[..., 2])
        h = np.degrees(np.arctan2(lab[..., 2], lab[..., 1])) % 360
        masks = dict(skin=(h > 30) & (h < 80) & (C > 0.02) & (C < 0.12) & (L > 0.35) & (L < 0.85),
                     plants=(h > 100) & (h < 165) & (C > 0.025) & (L > 0.15),
                     sky=(h > 225) & (h < 280) & (C > 0.035) & (L > 0.45),
                     whites=(L > 0.86) & (C < 0.03))
        photos.append((s, std, masks))
    rows = []
    for film in films:
        cube = read_cube(os.path.join(CUBES, coef[film]['cube']))
        de_all, parts = [], {k: [] for k in ('skin', 'plants', 'sky', 'whites')}
        big = []
        for s, std, masks in photos:
            today = common.camera_today(std, film)
            target = apply_cube(std, cube)
            de = np.linalg.norm(srgb_to_oklab(today / 255.0) - srgb_to_oklab(target / 255.0), axis=-1) * 100
            de_all.append(de.mean()); big.append(float((de > 6).mean()) * 100)
            for k, m in masks.items():
                if m.sum() > 2000:
                    parts[k].append(float(de[m].mean()))
        fit = coef[film]['meanDE']
        row = dict(film=film, fitDE2000=round(fit, 2), mean=round(float(np.mean(de_all)), 2), worst_photo=round(float(np.max(de_all)), 2),
                   pct_big=round(float(np.mean(big)), 1), **{k: round(float(np.mean(v)), 2) if v else None for k, v in parts.items()})
        rows.append(row)
        print(row, flush=True)
    rows.sort(key=lambda r: -r['mean'])
    with open(os.path.join(OUT, 'gap-report.json'), 'w', encoding='utf-8') as fh:
        json.dump(rows, fh, indent=1)
    print('\nfilm | gap mean | worst photo | % pixels gap>6 | skin | plants | sky | whites')
    for r in rows:
        print(f"{r['film']:<18} {r['mean']:>5} {r['worst_photo']:>6} {r['pct_big']:>6} {r['skin']!s:>6} {r['plants']!s:>6} {r['sky']!s:>6} {r['whites']!s:>6}")


if __name__ == '__main__':
    main()
