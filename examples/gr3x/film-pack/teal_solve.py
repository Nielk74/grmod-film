# SPDX-License-Identifier: GPL-2.0-only
"""Solve, per film, the linear-light 3x3 channel mix (rows summing to 1: neutrals stay neutral) that
turns blue skies toward a target hue while keeping skin and yellows where they are as far as a linear
mix allows, foliage steered to a target shift. The result goes into core/src/filmpack/looks.ts as a
`mixer` (the camera's film format carries a linear mix exactly; a hue-selective twist it cannot).

    python teal_solve.py            # prints the matrix and the hue shifts for each film

Colours: sky samples as GR III Standard renders them (hue ~235..262), light / dark skin, yellow,
foliage, a saturated red, and a purple (which must not run into the sky's way). Hues in OkLCh degrees.
"""
import numpy as np

def lin(c): c = np.asarray(c, float) / 255; return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
M1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929], [0.2119034982, 0.6806995451, 0.1073969566], [0.0883024619, 0.2817188376, 0.6299787005]])
M2 = np.array([[0.2104542553, 0.793617785, -0.0040720468], [1.9779984951, -2.428592205, 0.4505937099], [0.0259040371, 0.7827717662, -0.808675766]])
def lch(l):
    l = np.clip(l, 1e-6, None); lab = np.cbrt(l @ M1.T) @ M2.T
    return lab[:, 0], np.hypot(lab[:, 1], lab[:, 2]), np.degrees(np.arctan2(lab[:, 2], lab[:, 1])) % 360

SKY = lin([[95, 140, 200], [120, 160, 215], [70, 110, 175], [140, 175, 220], [100, 150, 205], [160, 190, 225], [60, 95, 160], [110, 135, 190]])
PROTECT = {'skin': lin([[194, 150, 130], [220, 175, 150], [205, 160, 135]]), 'dark skin': lin([[115, 82, 68], [140, 100, 80]]),
           'yellow': lin([[224, 163, 46], [231, 199, 31], [240, 210, 120]]), 'red': lin([[175, 54, 60], [200, 60, 50]]), 'purple': lin([[94, 60, 108], [133, 128, 177]])}
FOLIAGE = lin([[87, 108, 67], [70, 110, 60], [110, 140, 70], [50, 80, 45]])

def dh(a, b): return (a - b + 540) % 360 - 180

def shifts(m):
    out = {}
    for name, x in [('sky', SKY), ('foliage', FOLIAGE), *PROTECT.items()]:
        y = np.clip(x @ m.T, 0, 1)
        _, c0, h0 = lch(x); _, c1, h1 = lch(y)
        out[name] = (dh(h1, h0).mean(), (c1 / np.maximum(c0, 1e-6)).mean())
    return out

def matrix(p):
    # p: six off-diagonal entries; the diagonal makes each row sum to 1
    m = np.array([[0, p[0], p[1]], [p[2], 0, p[3]], [p[4], p[5], 0]], float)
    m[np.diag_indices(3)] = 1 - m.sum(1)
    return m

def cost(p, sky, foliage, w_foliage):
    s = shifts(matrix(p))
    c = 4 * (s['sky'][0] - sky) ** 2 + w_foliage * (s['foliage'][0] - foliage) ** 2
    c += 3 * s['skin'][0] ** 2 + 2 * s['dark skin'][0] ** 2 + 1.5 * s['yellow'][0] ** 2 + 0.5 * s['red'][0] ** 2 + 0.3 * s['purple'][0] ** 2
    # Chroma kept (saturation is the look's business): strictly on skin and yellows, loosely elsewhere.
    c += 900 * (s['skin'][1] - 1) ** 2 + 900 * (s['dark skin'][1] - 1) ** 2 + 400 * (s['yellow'][1] - 1) ** 2
    c += 150 * (s['sky'][1] - 1) ** 2 + 150 * (s['foliage'][1] - 1) ** 2 + 60 * (s['red'][1] - 1) ** 2
    c += 2 * float(np.sum(np.asarray(p) ** 2))                                            # no wild mixes
    return c

def solve(sky, foliage, w_foliage=1.0):
    p = np.zeros(6); step = 0.08; best = cost(p, sky, foliage, w_foliage)
    while step > 1e-4:
        improved = False
        for i in range(6):
            for d in (step, -step):
                q = p.copy(); q[i] += d
                c = cost(q, sky, foliage, w_foliage)
                if c < best: p, best, improved = q, c, True
        if not improved: step /= 2
    return matrix(p)

# Film: sky hue shift wanted (degrees; Standard skies ~259, teal ~215..230), foliage shift, weight.
FILMS = {
    'Classic Chrome': (-30, -10, 0.6), 'Classic Neg': (-38, +12, 1.0), 'Eterna': (-30, +6, 0.6), 'Blockbuster': (-45, +20, 0.8),
    'Instant': (-30, +6, 0.6), 'Portra 400': (-18, -8, 0.6), 'Pro Neg Std': (-10, +4, 0.5), 'Nostalgic Neg': (-10, -8, 0.5),
    'Kodachrome 64': (-10, -6, 0.5), 'Gold 200': (-10, -6, 0.5), 'Primrose': (-14, -4, 0.5), 'CineStill 800T': (-22, +14, 0.8),
}
def display_space():
    """The camera's Hue stage (YCbCr conversion) works on display RGB: solve there, colours as 0..1 display values."""
    global SKY, PROTECT, FOLIAGE
    disp = lambda c: np.asarray(c, float) / 255
    raw = {'sky': [[95, 140, 200], [120, 160, 215], [70, 110, 175], [140, 175, 220], [100, 150, 205], [160, 190, 225], [60, 95, 160], [110, 135, 190]]}
    SKY = disp(raw['sky'])
    PROTECT = {'skin': disp([[194, 150, 130], [220, 175, 150], [205, 160, 135]]), 'dark skin': disp([[115, 82, 68], [140, 100, 80]]),
               'yellow': disp([[224, 163, 46], [231, 199, 31], [240, 210, 120]]), 'red': disp([[175, 54, 60], [200, 60, 50]]), 'purple': disp([[94, 60, 108], [133, 128, 177]])}
    FOLIAGE = disp([[87, 108, 67], [70, 110, 60], [110, 140, 70], [50, 80, 45]])


_lch_linear = lch


def lch_display(x):
    return _lch_linear(np.where(x <= 0.04045, x / 12.92, ((np.clip(x, 0, None) + 0.055) / 1.055) ** 2.4))


if __name__ == '__main__':
    import sys
    if sys.argv[1:] == ['display']:
        # The mix of the camera's Hue +4 for films: sky about 24 degrees toward teal, foliage kept.
        display_space()
        globals()['lch'] = lch_display
        m = solve(-24, 0, 0.6)
        print('display mix', '[' + ', '.join('[' + ', '.join(f'{v:.4f}' for v in r) + ']' for r in m) + ']')
        print('  ', '  '.join(f"{k} {v[0]:+.0f}/{v[1]:.2f}" for k, v in shifts(m).items()))
        raise SystemExit
    for film, (sky, fol, w) in FILMS.items():
        m = solve(sky, fol, w)
        s = shifts(m)
        rows = ', '.join('[' + ', '.join(f'{v:.3f}' for v in r) + ']' for r in m)
        print(f"{film:15s} mixer([{rows}])  " + '  '.join(f"{k} {v[0]:+.0f}/{v[1]:.2f}" for k, v in s.items()))
