"""Share of pixels changed (any RGB channel by >=3 levels) and skin chroma ratio, per option and scene (sheet size, 4:2:2 path)."""
import sys, os, json, numpy as np
from common import *
from engine import *
import films2
from sheets import path_of
from sheets2 import PORTRA_SCENES

SC = PORTRA_SCENES + ['R0000027', 'R0000022']


def stats(film, lut, scenes, width=900):
    out = {}
    for n in scenes:
        std = load_rgb8(path_of(n), width); std = std[:, :std.shape[1] // 2 * 2]
        cam = camera_today(std, film); Y, Cb, Cr = to_422(cam)
        A = from_422(Y, Cb, Cr); B = from_422(*lut_apply_422(Y, Cb, Cr, lut))
        ch3 = (np.abs(A.astype(int) - B).max(-1) >= 3).mean()
        l0 = srgb_to_oklab(A / 255.); l1 = srgb_to_oklab(B / 255.)
        C0 = np.hypot(l0[..., 1], l0[..., 2]); C1 = np.hypot(l1[..., 1], l1[..., 2]); h0 = np.arctan2(l0[..., 2], l0[..., 1])
        s = skin_weight(l0[..., 0], C0, h0); cs = films2.violet_cold_skin(l0[..., 0], C0, h0)
        r = {'changed_ge3': float(ch3), 'warm_skin_px': float((s > 0.5).mean()), 'cold_skin_px': float((cs > 0.5).mean())}
        if (s > 0.5).sum() > 50: r['skin_chroma_ratio'] = float(np.median(C1[s > 0.5] / C0[s > 0.5])); r['skin_dL'] = float(np.mean(l1[..., 0][s > 0.5] - l0[..., 0][s > 0.5]))
        if (cs > 0.5).sum() > 50: r['coldskin_chroma_ratio'] = float(np.median(C1[cs > 0.5] / C0[cs > 0.5]))
        out[n] = r
    return out


if __name__ == '__main__':
    res = {}
    for k in films2.PORTRA:
        lut = np.load(os.path.join(OUT, f'lut-portra-{k}.npy')); res[k] = stats('Portra 400', lut, SC)
        print(k)
        for n, r in res[k].items(): print('  ', n, {a: round(b, 3) for a, b in r.items()})
        print('   mean changed share %.3f' % np.mean([r['changed_ge3'] for r in res[k].values()]))
    json.dump(res, open(os.path.join(OUT, 'metrics-portra-options.json'), 'w'), indent=1)
