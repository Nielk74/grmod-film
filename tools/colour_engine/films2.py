"""Round 2: refined Kodachrome 64 and CineStill 800T, and three optional Portra 400 looks. All OkLCh, soft weights.
band = dict(c=hue centre deg, w=half width, dh=hue shift deg, cm=chroma gain, dl=lightness shift,
            cg=(c0,c1) chroma gate, lg=(l0,l1,l2,l3) lightness window rising l0-l1, falling l2-l3, keep=skin share kept)"""
import numpy as np
from engine import smooth, hue_w, skin_weight


def lw(L, w):
    a, b, c, d = w
    return smooth(L, a, b) * (1 - smooth(L, c, d))


def bands2(L, C, h, s, bands, keep0=0.0):
    dh = np.zeros_like(L); lc = np.zeros_like(L); dL = np.zeros_like(L)
    for b in bands:
        g0, g1 = b.get('cg', (0.008, 0.05))
        w = hue_w(h, b['c'], b['w']) * smooth(C, g0, g1) * (1 - (1 - b.get('keep', keep0)) * s)
        if 'lg' in b:
            w = w * lw(L, b['lg'])
        dh += w * b.get('dh', 0); lc += w * np.log(b.get('cm', 1.0)); dL += w * b.get('dl', 0)
    return L + dL * (1 - smooth(L, 0.72, 0.9)), C * np.exp(lc), h + np.radians(dh)


def softlim(C, knee, cmax):
    """identity below knee; smoothly saturating towards cmax above it"""
    x = np.maximum(C - knee, 0); r = cmax - knee
    return np.where(C <= knee, C, knee + r * np.tanh(x / r))


# ---------------- Kodachrome 64 v2 ----------------
KC2 = dict(
    bands=[dict(c=27, w=24, dh=-2, cm=1.55, dl=-0.05),                                       # reds
           dict(c=250, w=50, dh=-2, cm=1.40, dl=-0.06, cg=(0.02, 0.06)),                     # blues / sky
           dict(c=100, w=30, dh=-5, cm=1.55, dl=-0.02, cg=(0.06, 0.12), lg=(0.5, 0.7, 1.1, 1.2)),   # bright saturated yellows only
           dict(c=68, w=22, dh=-3, cm=1.35, dl=-0.03, cg=(0.06, 0.12), lg=(0.5, 0.7, 1.1, 1.2)),    # bright saturated oranges only
           dict(c=140, w=40, dh=-4, cm=1.0, dl=-0.04, cg=(0.02, 0.06)),                      # greens: slightly olive, darker
           dict(c=335, w=35, dh=0, cm=1.15, dl=-0.02), dict(c=200, w=35, dh=0, cm=1.10, dl=-0.02)],
    sky_knee=0.105, sky_max=0.165, skin_cm=0.94)


def kodachrome2(L, C, h, s, P=KC2):
    s = 1 - (1 - s) ** 2
    L2, C2, h2 = bands2(L, C, h, s, P['bands'], 0.0)
    wb = hue_w(h2, 255, 55) * smooth(C, 0.03, 0.08)
    C2 = C2 + wb * (softlim(C2, P['sky_knee'], P['sky_max']) - C2)
    C2 = C2 * (1 - (1 - P['skin_cm']) * s)
    return L2, C2, h2


# ---------------- CineStill 800T v2 ----------------
def cold_skin(L, C, h):
    """faces the camera renders blue-grey: cold hue, low chroma, mid lightness"""
    return hue_w(h, 262, 40) * smooth(C, 0.006, 0.018) * (1 - smooth(C, 0.05, 0.075)) * smooth(L, 0.28, 0.42) * (1 - smooth(L, 0.78, 0.9))


CS2 = dict(
    bands=[dict(c=262, w=55, dh=-26, cm=1.25, dl=-0.01, cg=(0.035, 0.09)),
           dict(c=145, w=45, dh=24, cm=1.05, dl=-0.01),
           dict(c=205, w=40, cm=1.25),
           dict(c=330, w=40, dh=-20),
           dict(c=55, w=45, dh=-3, cm=1.22, cg=(0.006, 0.04), keep=1.0),
           dict(c=85, w=28, dh=-6, cm=1.15)],
    tint=0.034, tint_dir=205, tint_L=(0.06, 0.38), lift=0.016, cold_mix=0.65, cold_target=(0.030, 52))


def cinestill2(L, C, h, s, P=CS2):
    cs = cold_skin(L, C, h)
    # daylight blues: ease the teal shift on bright, high-chroma blues, keep it full for dusk/night blues
    ease = 1 - 0.75 * smooth(L, 0.58, 0.82) * smooth(C, 0.07, 0.13) - 0.25 * smooth(L, 0.7, 0.9)
    L2, C2, h2 = bands2(L, C, h, s, P['bands'], 0.0)
    bl = hue_w(h, 255, 70)
    k = (1 - bl * (1 - ease)) * (1 - cs)
    h2 = h + (h2 - h) * k; C2 = C * (C2 / np.maximum(C, 1e-6)) ** k; L2 = L + (L2 - L) * k
    a, b = C2 * np.cos(h2), C2 * np.sin(h2)
    warm = np.maximum(hue_w(h, 55, 85) * smooth(C, 0.004, 0.02), cs)    # warm colours and cold-rendered skin take no tint
    sh = 1 - smooth(L, *P['tint_L'])
    t = P['tint'] * sh * (1 - warm)
    a = a + t * np.cos(np.radians(P['tint_dir'])); b = b + t * np.sin(np.radians(P['tint_dir']))
    lift = P['lift'] * hue_w(h, 52, 55) * smooth(C, 0.005, 0.02) * (1 - smooth(C, 0.07, 0.13)) * smooth(L, 0.18, 0.4)
    a = a + lift * np.cos(np.radians(52)); b = b + lift * np.sin(np.radians(52))
    Ct, ht = P['cold_target']; m = P['cold_mix'] * cs   # cold skin: back towards natural warm skin (modest chroma, no orange)
    a = a + m * (Ct * np.cos(np.radians(ht)) - a); b = b + m * (Ct * np.sin(np.radians(ht)) - b)
    return L2, np.hypot(a, b), np.arctan2(b, a)


# ---------------- Portra 400 optional looks (no white-balance change, no global change) ----------------
def tight_skin(L, C, h):
    """narrower than skin_weight: peach hues, skin-level chroma (keeps pastry, stone, wood mostly out)"""
    return hue_w(h, 48, 24) * smooth(C, 0.015, 0.03) * (1 - smooth(C, 0.07, 0.10)) * lw(L, (0.3, 0.45, 0.85, 0.95))


def luminous_skin(L, C, h, s):
    s = tight_skin(L, C, h)
    d = (np.degrees(h) - 50 + 180) % 360 - 180
    h2 = h - np.radians(d) * 0.6 * s                  # hue towards peach
    C2 = np.minimum(C + 0.4 * s * (0.052 - C), 1.05 * C)   # chroma towards the skin's typical level, never above 1.05x
    L2 = L + 0.05 * s
    return L2, C2, h2


def violet_cold_skin(L, C, h):
    """cold-rendered skin that Portra leaves violet-grey (hue 255-325), skin-like lightness"""
    return hue_w(h, 290, 35) * smooth(C, 0.006, 0.016) * (1 - smooth(C, 0.035, 0.055)) * lw(L, (0.3, 0.42, 0.72, 0.85))


def shade_rescue(L, C, h, s):
    cs = violet_cold_skin(L, C, h)
    m = 0.7 * cs * (1 - s)
    a = C * np.cos(h); b = C * np.sin(h)
    a = a + m * (0.036 * np.cos(np.radians(48)) - a); b = b + m * (0.036 * np.sin(np.radians(48)) - b)
    return L + 0.02 * cs, np.hypot(a, b), np.arctan2(b, a)


def golden_light(L, C, h, s):
    w = hue_w(h, 82, 55) * smooth(C, 0.03, 0.06) * smooth(L, 0.55, 0.78) * (1 - s)         # bright, already-warm, not skin
    g = hue_w(h, 70, 50) * smooth(C, 0.008, 0.03) * smooth(L, 0.80, 0.93) * (1 - s)        # warm highlights
    C2 = C * (1 + 0.9 * w)
    h2 = h - np.radians(10) * w
    a = C2 * np.cos(h2) + 0.022 * g * np.cos(np.radians(85)); b = C2 * np.sin(h2) + 0.022 * g * np.sin(np.radians(85))
    return L + 0.03 * w, np.hypot(a, b), np.arctan2(b, a)


PORTRA = {'luminous': luminous_skin, 'shade': shade_rescue, 'golden': golden_light}
