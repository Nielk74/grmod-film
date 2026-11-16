"""Measure foliage, sky and whites in OkLCh: Standard vs Camera today (Portra) vs a LUT. Masks come from the Standard picture."""
import sys, os, json, numpy as np
from common import *
from engine import *
from sheets import path_of

PLANTS = ['R0000022', 'R0000023', 'R0000027', 'R0000020', 'R0000021', 'R0000019']


def lch(rgb8):
    o = srgb_to_oklab(rgb8 / 255.)
    return o[..., 0], np.hypot(o[..., 1], o[..., 2]), (np.degrees(np.arctan2(o[..., 2], o[..., 1])) % 360), o[..., 1], o[..., 2]


def circ_median(h):
    return float((np.degrees(np.angle(np.median(np.cos(np.radians(h))) + 1j * np.median(np.sin(np.radians(h))))) % 360))


def regions(std):
    L, C, h, a, b = lch(std)
    green = (h > 105) & (h < 170) & (C > 0.035) & (L < 0.85)
    sky = (h > 225) & (h < 285) & (C > 0.03) & (L > 0.5)
    white = (L > 0.82) & (C < 0.05)
    return green, sky, white


def measure(film, lut, scenes, width=900):
    out = {}
    for n in scenes:
        std = load_rgb8(path_of(n), width); std = std[:, :std.shape[1] // 2 * 2]
        Y, Cb, Cr = to_422(camera_today(std, film))
        views = {'std': std, 'cam': from_422(Y, Cb, Cr)}
        if lut is not None: views['new'] = from_422(*lut_apply_422(Y, Cb, Cr, lut))
        g, s, w = regions(std)
        r = {}
        for nm, v in views.items():
            L, C, h, a, b = lch(v); d = {}
            if g.sum() > 200:
                d['green_h'] = circ_median(h[g]); d['green_C'] = float(np.median(C[g]))
                dk = g & (L < 0.35)
                if dk.sum() > 200: d['darkgreen_h'] = circ_median(h[dk]); d['darkgreen_C'] = float(np.median(C[dk]))
                lt = g & (L >= 0.35)
                if lt.sum() > 200: d['litgreen_h'] = circ_median(h[lt]); d['litgreen_C'] = float(np.median(C[lt]))
            if s.sum() > 200: d['sky_h'] = circ_median(h[s]); d['sky_C'] = float(np.median(C[s]))
            if w.sum() > 200: d['white_a'] = float(np.mean(a[w]) * 100); d['white_b'] = float(np.mean(b[w]) * 100)
            r[nm] = d
        if lut is not None:
            Lc, Cc, hc, _, _ = lch(views['cam']); Ln, Cn, hn, an, bn = lch(views['new'])
            sk = skin_weight(Lc, Cc, hc) > 0.5
            if sk.sum() > 50:
                dh = (hn - hc + 180) % 360 - 180
                r['skin_hue_shift'] = float(np.median(dh[sk])); r['skin_C_ratio'] = float(np.median(Cn[sk] / Cc[sk]))
            A = views['cam']; B = views['new']
            d = srgb_to_oklab(A / 255.) - srgb_to_oklab(B / 255.); r['dE100'] = float(np.sqrt((d ** 2).sum(-1)).mean() * 100)
            r['dContrast'] = float(np.std(Ln) / np.std(Lc))
        out[n] = r
    return out


if __name__ == '__main__':
    res = measure('Portra 400', None, PLANTS)
    for n, r in res.items(): print(n, {k: {a: round(b, 3) for a, b in v.items()} for k, v in r.items()})
