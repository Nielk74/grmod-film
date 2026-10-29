# SPDX-License-Identifier: GPL-2.0-only
"""The teal-sky mix for the camera's Hue stage: GR III applies Hue as a 3x3 matrix on the finished
(display, gamma-encoded) RGB, inside its RGB -> YCbCr conversion. The skin-protecting teal mix was
solved in linear light (TEAL_SKY_MIX, core/src/color/sky.ts); this finds the display-space 3x3 matrix
(rows summing to 1: neutrals stay neutral) that reproduces it best, by least squares over a broad set
of colours weighted toward skies, skin and foliage, and reports what it does to them.

    python teal_display.py
"""
import numpy as np

LIN = np.array([[1.267, -0.155, -0.112], [0.076, 0.682, 0.242], [-0.075, 0.081, 0.994]])
enc = lambda l: np.where(l <= 0.0031308, l * 12.92, 1.055 * np.clip(l, 0, None) ** (1 / 2.4) - 0.055)
dec = lambda d: np.where(d <= 0.04045, d / 12.92, ((d + 0.055) / 1.055) ** 2.4)

g = np.linspace(0, 1, 13)
grid = np.array(np.meshgrid(g, g, g)).reshape(3, -1).T
focus = np.array([[95, 140, 200], [120, 160, 215], [70, 110, 175], [140, 175, 220], [160, 190, 225], [60, 95, 160],
                  [194, 150, 130], [220, 175, 150], [115, 82, 68], [87, 108, 67], [70, 110, 60], [110, 140, 70],
                  [224, 163, 46], [231, 199, 31], [175, 54, 60]], float) / 255
X = np.vstack([grid, np.repeat(focus, 40, axis=0)])
Y = np.clip(enc(np.clip(dec(X) @ LIN.T, 0, 1)), 0, 1)

M = np.zeros((3, 3))
for r in range(3):
    # y_r = a x0 + b x1 + (1 - a - b) x2  ->  y_r - x2 = a (x0 - x2) + b (x1 - x2)
    A = np.stack([X[:, 0] - X[:, 2], X[:, 1] - X[:, 2]], 1)
    a, b = np.linalg.lstsq(A, Y[:, r] - X[:, 2], rcond=None)[0]
    M[r] = [a, b, 1 - a - b]

M1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929], [0.2119034982, 0.6806995451, 0.1073969566], [0.0883024619, 0.2817188376, 0.6299787005]])
M2 = np.array([[0.2104542553, 0.793617785, -0.0040720468], [1.9779984951, -2.428592205, 0.4505937099], [0.0259040371, 0.7827717662, -0.808675766]])
def lch(d):
    lab = np.cbrt(np.clip(dec(d), 1e-7, None) @ M1.T) @ M2.T
    return np.hypot(lab[:, 1], lab[:, 2]), np.degrees(np.arctan2(lab[:, 2], lab[:, 1])) % 360
def report(m, label):
    out = []
    for name, rgb in [('sky', [[95, 140, 200], [120, 160, 215], [70, 110, 175]]), ('skin', [[194, 150, 130], [220, 175, 150]]), ('dark skin', [[115, 82, 68]]),
                      ('foliage', [[87, 108, 67], [110, 140, 70]]), ('yellow', [[224, 163, 46], [231, 199, 31]]), ('red', [[175, 54, 60]])]:
        x = np.array(rgb, float) / 255
        y = np.clip(x @ m.T, 0, 1) if m is not None else np.clip(enc(np.clip(dec(x) @ LIN.T, 0, 1)), 0, 1)
        c0, h0 = lch(x); c1, h1 = lch(y)
        out.append(f"{name} {((h1 - h0 + 540) % 360 - 180).mean():+.0f}°×{(c1 / c0).mean():.2f}")
    print(f'{label:24s}', '  '.join(out))
report(None, 'linear-light mix')
report(M, 'display mix (fitted)')
print('display mix', '[' + ', '.join('[' + ', '.join(f'{v:.4f}' for v in r) + ']' for r in M) + ']')


# Refined directly in display space: sky to the target hue, the other colours' hue and saturation held.
SETS = {k: np.array(v, float) / 255 for k, v in {
    'sky': [[95, 140, 200], [120, 160, 215], [70, 110, 175], [140, 175, 220], [160, 190, 225], [60, 95, 160]],
    'skin': [[194, 150, 130], [220, 175, 150], [205, 160, 135]], 'dark skin': [[115, 82, 68], [140, 100, 80]],
    'foliage': [[87, 108, 67], [70, 110, 60], [110, 140, 70], [50, 80, 45]], 'yellow': [[224, 163, 46], [231, 199, 31], [240, 210, 120]],
    'red': [[175, 54, 60], [200, 60, 50]], 'purple': [[94, 60, 108], [133, 128, 177]]}.items()}
def stats(m):
    out = {}
    for k, x in SETS.items():
        c0, h0 = lch(x); c1, h1 = lch(np.clip(x @ m.T, 0, 1))
        out[k] = (((h1 - h0 + 540) % 360 - 180).mean(), (c1 / np.maximum(c0, 1e-6)).mean())
    return out
def cost(m, target):
    s = stats(m)
    c = 6 * (s['sky'][0] - target) ** 2 + 4 * s['skin'][0] ** 2 + 3 * s['dark skin'][0] ** 2 + 2 * s['yellow'][0] ** 2 + s['foliage'][0] ** 2
    c += 0.5 * s['red'][0] ** 2 + 0.3 * s['purple'][0] ** 2
    c += 2500 * ((s['skin'][1] - 1) ** 2 + (s['dark skin'][1] - 1) ** 2) + 1500 * (s['yellow'][1] - 1) ** 2 + 900 * (s['foliage'][1] - 1) ** 2
    c += 500 * (s['sky'][1] - 1) ** 2 + 200 * (s['red'][1] - 1) ** 2
    return c
def refine(m0, target):
    p = np.array([m0[0, 1], m0[0, 2], m0[1, 0], m0[1, 2], m0[2, 0], m0[2, 1]])
    mk = lambda p: (lambda m: (m.__setitem__(np.diag_indices(3), 1 - m.sum(1)), m)[1])(np.array([[0, p[0], p[1]], [p[2], 0, p[3]], [p[4], p[5], 0]], float))
    best, step = cost(mk(p), target), 0.02
    while step > 2e-5:
        better = False
        for i in range(6):
            for d in (step, -step):
                q = p.copy(); q[i] += d
                c = cost(mk(q), target)
                if c < best: p, best, better = q, c, True
        if not better: step /= 2
    return mk(p)
R = refine(M, -24)
report(R, 'display mix (refined)')
print('refined mix', '[' + ', '.join('[' + ', '.join(f'{v:.4f}' for v in r) + ']' for r in R) + ']')
