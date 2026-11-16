import os, json, numpy as np
from common import *
from engine import *
import films2
from sheets import path_of
from metrics2 import stats

def cam_full(std, film):
    return np.concatenate([camera_today(std[r:r + 500], film) for r in range(0, std.shape[0], 500)], 0)

res = {}
# full-size JPEG per Portra option
for k, scene in (('luminous', 'R0000005'), ('shade', 'R0000030'), ('golden', 'R0000027')):
    lut = np.load(os.path.join(OUT, f'lut-portra-{k}.npy'))
    std = load_rgb8(path_of(scene)); std = std[:, :std.shape[1] // 2 * 2]
    Y, Cb, Cr = to_422(cam_full(std, 'Portra 400'))
    eng = from_422(*lut_apply_422(Y, Cb, Cr, lut)); A = from_422(Y, Cb, Cr)
    Image.fromarray(eng).save(os.path.join(OUT, f'portra-{k}-{scene}.jpg'), quality=95, subsampling=1)
    res[f'portra_{k}_fullsize_{scene}'] = dict(changed_ge3=float((np.abs(A.astype(int) - eng).max(-1) >= 3).mean()), size=list(eng.shape[:2]))
    print(k, res[f'portra_{k}_fullsize_{scene}'], flush=True)
# skin ratios for the refined films
for key, film, f2, ne, scenes in (('kodachrome_v2', 'Kodachrome 64', films2.kodachrome2, True, ['R0000030', 'R0000005', 'R0000023']),
                                  ('cinestill_v2', 'CineStill 800T', films2.cinestill2, False, ['R0000030', 'AK000164', 'R0000016'])):
    lut = np.load(os.path.join(OUT, f'lut-{key.replace("_v2", "")}-v2.npy'))
    res[key] = stats(film, lut, scenes); print(key, {n: {a: round(b, 3) for a, b in r.items()} for n, r in res[key].items()}, flush=True)
# default Portra LUT still identity
ident = identity_lut()
std = load_rgb8(path_of('R0000022')); std = std[:, :std.shape[1] // 2 * 2]
Y, Cb, Cr = to_422(cam_full(std, 'Portra 400')); Y2, Cb2, Cr2 = lut_apply_422(Y, Cb, Cr, ident)
res['portra_default'] = dict(nonzero_lut_entries=int(np.count_nonzero(ident)),
                             max_abs_diff=int(max(np.abs(Y.astype(int) - Y2).max(), np.abs(Cb.astype(int) - Cb2).max(), np.abs(Cr.astype(int) - Cr2).max())), n_pixels=int(Y.size))
print(res['portra_default'])
json.dump(res, open(os.path.join(OUT, 'metrics-v2.json'), 'w'), indent=1)
print('DONE')
