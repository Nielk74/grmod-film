"""Per-film colour transforms in OkLCh: smooth functions of hue, chroma, lightness, soft skin weighting.
band = (hue centre deg, half width deg, hue shift deg, chroma multiplier, lightness shift [OkLab L])."""
import numpy as np
from engine import smooth, hue_w, skin_weight, build_lut

def bands_apply(L, C, h, skin, bands, skin_keep):
    """skin_keep: share of each band's effect that skin colours keep (0 = skin untouched).
    A band may carry a chroma gate (c0, c1) and its own skin_keep: (hue, width, dh, cm, dL, gate, keep)."""
    dh = np.zeros_like(L); lc = np.zeros_like(L); dL = np.zeros_like(L)
    for b in bands:
        c, wd, sh, cm, dl = b[:5]
        g0, g1 = b[5] if len(b) > 5 and b[5] else (0.008, 0.05)
        keep = b[6] if len(b) > 6 and b[6] is not None else skin_keep
        w = hue_w(h, c, wd) * smooth(C, g0, g1) * (1 - (1 - keep) * skin)
        dh += w * sh; lc += w * np.log(cm); dL += w * dl
    return L + dL * (1 - smooth(L, 0.72, 0.9)), C * np.exp(lc), h + np.radians(dh)

# ---------------- CineStill 800T ----------------
CS = dict(
    bands=[(262, 55, -26, 1.25, -0.01, (0.035, 0.09)), (145, 45, +24, 1.05, -0.01), (205, 40, 0, 1.25, 0),
           (330, 40, -20, 1.0, 0), (55, 45, -3, 1.22, 0.0, (0.006, 0.04), 1.0), (85, 28, -6, 1.15, 0.0)],
    tint=0.034, tint_dir=205, tint_L=(0.06, 0.38), lift=0.016)

def cinestill(L, C, h, s, P=CS):
    L2, C2, h2 = bands_apply(L, C, h, s, P['bands'], skin_keep=0.0)
    a, b = C2 * np.cos(h2), C2 * np.sin(h2)
    warm = hue_w(h, 55, 85) * smooth(C, 0.004, 0.02)          # warm colours (and skin) do not take the tint
    sh = 1 - smooth(L, *P['tint_L'])
    t = P['tint'] * sh * (1 - warm)
    a = a + t * np.cos(np.radians(P['tint_dir'])); b = b + t * np.sin(np.radians(P['tint_dir']))
    # the orange half of the split: warm colours that came out dull (the film cools skin) get a bounded warm lift
    lift = P['lift'] * hue_w(h, 52, 55) * smooth(C, 0.005, 0.02) * (1 - smooth(C, 0.07, 0.13)) * smooth(L, 0.18, 0.4)
    a = a + lift * np.cos(np.radians(52)); b = b + lift * np.sin(np.radians(52))
    return L2, np.hypot(a, b), np.arctan2(b, a)

# ---------------- Gold 200 ----------------
GD = dict(
    bands=[(135, 50, -19, 1.40, +0.06), (108, 30, -8, 1.65, +0.04), (75, 32, -5, 1.38, +0.02), (20, 25, 4, 1.15, 0),
           (262, 45, 0, 1.12, +0.0), (200, 40, 0, 1.08, 0), (330, 40, 8, 1.1, 0.0)],
    honey=0.55, skin_keep=0.0)

def gold(L, C, h, s, P=GD):
    s = 1 - (1 - s) ** 2   # wider skin protection: partly-skin colours are protected too
    L2, C2, h2 = bands_apply(L, C, h, s, P['bands'], P['skin_keep'])
    honey = hue_w(h, 80, 60) * smooth(L, 0.45, 0.85) * smooth(C, 0.02, 0.06) * (1 - 0.9 * s)
    C2 = C2 * (1 + P['honey'] * honey) * (1 - 0.06 * s)
    h2 = h2 - np.radians(7) * honey
    return L2, C2, h2

# ---------------- Kodachrome 64 ----------------
KC = dict(
    bands=[(27, 24, -2, 1.55, -0.05), (250, 50, -2, 1.55, -0.06, (0.02, 0.06)), (100, 30, -5, 1.55, -0.02), (68, 22, -4, 1.4, -0.03), (140, 40, -14, 1.0, -0.04),
           (335, 35, 0, 1.15, -0.02), (200, 35, 0, 1.10, -0.02)],
    skin_keep=0.0, skin_cm=0.97)

def kodachrome(L, C, h, s, P=KC):
    s = 1 - (1 - s) ** 2
    L2, C2, h2 = bands_apply(L, C, h, s, P['bands'], P['skin_keep'])
    C2 = C2 * (1 - (1 - P['skin_cm']) * s)
    return L2, C2, h2

FILMS = {  # sheet name -> (camera film, transform, neutral_exact)
    'cinestill': ('CineStill 800T', cinestill, False),
    'gold': ('Gold 200', gold, True),
    'kodachrome': ('Kodachrome 64', kodachrome, True),
}
