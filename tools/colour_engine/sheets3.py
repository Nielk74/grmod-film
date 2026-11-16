import sys, os, json, numpy as np
from common import *
from engine import *
import films3
from sheets import path_of
from sheets2 import sheet, PORTRA_SCENES

LABELS = {'frontier': 'Frontier', 'noritsu': 'Noritsu', 'plus2': '+2', 'pushed': 'Pushed'}


def build_all():
    ls = {}
    for k, (f, ne) in films3.LOOKS3.items():
        ls[k] = build_lut(f, ne); np.save(os.path.join(OUT, f'lut-portra-{k}.npy'), ls[k])
    return ls


def delta_e(film, lut, scenes, width=900):
    out = {}
    for n in scenes:
        std = load_rgb8(path_of(n), width); std = std[:, :std.shape[1] // 2 * 2]
        Y, Cb, Cr = to_422(camera_today(std, film))
        A = from_422(Y, Cb, Cr); B = from_422(*lut_apply_422(Y, Cb, Cr, lut))
        d = srgb_to_oklab(A / 255.) - srgb_to_oklab(B / 255.)
        l0 = srgb_to_oklab(A / 255.); l1 = srgb_to_oklab(B / 255.)
        C0 = np.hypot(l0[..., 1], l0[..., 2]); C1 = np.hypot(l1[..., 1], l1[..., 2]); h0 = np.arctan2(l0[..., 2], l0[..., 1])
        s = skin_weight(l0[..., 0], C0, h0)
        r = {'dE100': float(np.sqrt((d ** 2).sum(-1)).mean() * 100), 'dL100': float((l1[..., 0] - l0[..., 0]).mean() * 100)}
        if (s > 0.5).sum() > 50:
            r['skin_C_ratio'] = float(np.median(C1[s > 0.5] / C0[s > 0.5])); r['skin_hue_shift'] = float(np.degrees(np.median((np.arctan2(l1[..., 2], l1[..., 1]) - h0)[s > 0.5])))
        out[n] = r
    return out


if __name__ == '__main__':
    ls = build_all()
    cols = [('Camera today', None)] + [(LABELS[k], ls[k]) for k in films3.LOOKS3]
    sheet('Portra 400', PORTRA_SCENES, cols, wp=420, wl=620, name='sheet-portra-v3')
    res = {k: delta_e('Portra 400', ls[k], PORTRA_SCENES) for k in ls}
    json.dump(res, open(os.path.join(OUT, 'metrics-portra-v3.json'), 'w'), indent=1)
    print('scene     ' + '  '.join(f'{LABELS[k]:>9}' for k in ls))
    for n in PORTRA_SCENES:
        print(f'{n}  ' + '  '.join(f"{res[k][n]['dE100']:9.1f}" for k in ls))
    for k in ls:
        sk = [r['skin_C_ratio'] for r in res[k].values() if 'skin_C_ratio' in r]
        print(k, 'skin C ratio %.2f-%.2f' % (min(sk), max(sk)))
