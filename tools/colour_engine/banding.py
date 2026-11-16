"""Step-size check on smooth areas: pixels whose camera-today neighbours differ by <=1 in every channel
(horizontal and vertical); how big are the engine's neighbour steps there? Full-size 6000x4000."""
import os, sys, json, numpy as np
from common import *
from engine import *
import films
from sheets import path_of

def cam_full(std, film):
    return np.concatenate([camera_today(std[r:r + 500], film) for r in range(0, std.shape[0], 500)], 0)

def steps(a, b):
    out = {}
    for name, ax in (('h', 1), ('v', 0)):
        da = np.abs(np.diff(a.astype(np.int16), axis=ax)).max(-1); db = np.abs(np.diff(b.astype(np.int16), axis=ax)).max(-1)
        sm = da <= 1
        out[name] = (db[sm], da[sm])
    d = np.concatenate([out['h'][0], out['v'][0]]); c = np.concatenate([out['h'][1], out['v'][1]])
    return dict(smooth_px=int(d.size), cam_max=int(c.max()), eng_max=int(d.max()), eng_frac_ge2=float((d >= 2).mean()),
                eng_frac_ge3=float((d >= 3).mean()), cam_frac_ge2=0.0)

res = {}
for key, scenes in {'cinestill': ['AK000164', 'R0000016'], 'gold': ['R0000022', 'R0000004'], 'kodachrome': ['R0000023', 'R0000022']}.items():
    film, tf, ne = films.FILMS[key]; lut = np.load(os.path.join(OUT, f'lut-{key}.npy'))
    for n in scenes:
        std = load_rgb8(path_of(n)); std = std[:, :std.shape[1] // 2 * 2]
        cam = cam_full(std, film); Y, Cb, Cr = to_422(cam)
        A = from_422(Y, Cb, Cr); B = from_422(*lut_apply_422(Y, Cb, Cr, lut))
        r = steps(A, B); res[f'{key}/{n}'] = r; print(key, n, r)
json.dump(res, open(os.path.join(OUT, 'banding.json'), 'w'), indent=1)
