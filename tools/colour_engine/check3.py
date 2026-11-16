"""Banding / noise check of the four Portra looks on full-size frames, from real 8-bit values."""
import os, json, numpy as np
from common import *
from engine import *
from sheets import path_of

LOOKS = ['frontier', 'noritsu', 'plus2', 'pushed']
res = {}
# LUT slope of luma along the neutral axis (noise gain for grey tones), from the LUT itself
g = np.arange(0, 256)
for k in LOOKS:
    lut = np.load(os.path.join(OUT, f'lut-portra-{k}.npy'))
    ax = np.array([lut_apply_422(np.full((1, 2), v, np.uint8), np.full((1, 1), 128, np.uint8), np.full((1, 1), 128, np.uint8), lut)[0][0, 0] for v in g], float)
    sl = np.diff(ax)
    res[k] = dict(luma_slope_max=float(sl.max()), luma_slope_min=float(sl.min()), luma_slope_shadows_10_60=float(sl[10:60].mean()),
                  grey_gaps=int(((np.bincount(ax.astype(int), minlength=256)[ax.min().astype(int):ax.max().astype(int) + 1]) == 0).sum()))


def cam_full(std, film):
    return np.concatenate([camera_today(std[r:r + 500], film) for r in range(0, std.shape[0], 500)], 0)


for scene, region in (('R0000027', (slice(0, 1200), slice(2800, 4000))), ('AK000164', (slice(0, 6000), slice(0, 4000)))):
    std = load_rgb8(path_of(scene)); std = std[:, :std.shape[1] // 2 * 2]
    Y, Cb, Cr = to_422(cam_full(std, 'Portra 400')); A = from_422(Y, Cb, Cr)
    for k in LOOKS:
        lut = np.load(os.path.join(OUT, f'lut-portra-{k}.npy')); B = from_422(*lut_apply_422(Y, Cb, Cr, lut))
        a = A[region]; b = B[region]
        da = np.abs(np.diff(a.astype(np.int16), axis=1)).max(-1); db = np.abs(np.diff(b.astype(np.int16), axis=1)).max(-1); sm = da <= 1
        h = np.bincount(b[..., 1].ravel(), minlength=256); lo, hi = np.percentile(b[..., 1], [1, 99]).astype(int)
        res[k][scene] = dict(smooth_px=int(sm.sum()), eng_frac_ge3=float((db[sm] >= 3).mean()), eng_max=int(db[sm].max()), green_hist_gaps=int((h[lo:hi + 1] == 0).sum()),
                             cam_green_hist_gaps=int((np.bincount(a[..., 1].ravel(), minlength=256)[np.percentile(a[..., 1], [1, 99]).astype(int)[0]:np.percentile(a[..., 1], [1, 99]).astype(int)[1] + 1] == 0).sum()))
        print(k, scene, res[k][scene], flush=True)
    del Y, Cb, Cr, A
json.dump(res, open(os.path.join(OUT, 'check-portra-v3.json'), 'w'), indent=1)
for k in LOOKS: print(k, {a: round(b, 2) for a, b in res[k].items() if not isinstance(b, dict)})
print('DONE')
