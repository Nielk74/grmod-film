import sys, os, json, numpy as np
from common import *
from engine import *
import films
from sheets import path_of, make_sheet, SCENES

BEST = {'cinestill': 'AK000164', 'gold': 'R0000022', 'kodachrome': 'R0000023'}
res = {}
def cam_full(std, film):
    parts = [camera_today(std[r:r + 500], film) for r in range(0, std.shape[0], 500)]
    return np.concatenate(parts, 0)

def gaps(a):
    out = []
    for c in range(3):
        v = a[..., c].ravel(); lo, hi = np.percentile(v, [1, 99]).astype(int)
        h = np.bincount(v, minlength=256)[lo:hi + 1]; out.append(int((h == 0).sum()))
    return out

for key, (film, tf, ne) in films.FILMS.items():
    lut = build_lut(tf, ne)
    np.save(os.path.join(OUT, f'lut-{key}.npy'), lut)
    std = load_rgb8(path_of(BEST[key])); std = std[:, :std.shape[1] // 2 * 2]
    cam = cam_full(std, film)
    Y, Cb, Cr = to_422(cam)
    Y2, Cb2, Cr2 = lut_apply_422(Y, Cb, Cr, lut)
    eng = from_422(Y2, Cb2, Cr2); camd = from_422(Y, Cb, Cr)
    Image.fromarray(eng).save(os.path.join(OUT, f'{key}-{BEST[key]}-engine.jpg'), quality=95, subsampling=1)
    d = np.abs(np.diff(lut.astype(np.float64) / 16, axis=0)); 
    gain = max(np.abs(np.diff(lut.astype(np.float64) / 16, axis=a)).max() / 8 for a in range(3))
    g99 = np.percentile(np.concatenate([np.abs(np.diff(lut.astype(np.float64) / 16, axis=a)).ravel() for a in range(3)]) / 8, 99.9)
    sky = slice(0, 600)  # top rows: sky in R0000022 / R0000023 / AK000164 (dark bg)
    res[key] = dict(scene=BEST[key], lut_bytes=int(lut.size * 2), max_slope_extra=float(gain), p999_slope_extra=float(g99),
                    gaps_cam=gaps(camd[sky]), gaps_eng=gaps(eng[sky]), size=list(eng.shape[:2]))
    print(key, res[key])
# Portra identity
std = load_rgb8(path_of('R0000022')); std = std[:, :std.shape[1] // 2 * 2]
cam = cam_full(std, 'Portra 400'); Y, Cb, Cr = to_422(cam)
lut = identity_lut(); Y2, Cb2, Cr2 = lut_apply_422(Y, Cb, Cr, lut)
res['portra'] = dict(nonzero_lut_entries=int(np.count_nonzero(lut)), max_abs_diff=int(max(np.abs(Y.astype(int) - Y2).max(), np.abs(Cb.astype(int) - Cb2).max(), np.abs(Cr.astype(int) - Cr2).max())),
                     n_pixels=int(Y.size))
print(res['portra'])
json.dump(res, open(os.path.join(OUT, 'metrics.json'), 'w'), indent=1)
