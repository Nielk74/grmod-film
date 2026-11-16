"""Round 4: Portra's skin with Ektar-style richness in everything else, by hue-selective correction of Camera today (the real Portra fit).
Measured on Standard vs Camera today (measure4.py): Portra turns foliage from hue ~130 to ~108 (yellow) at ~0.65x chroma, sky from 258 to ~238 (cyan) at 0.75x chroma,
and bright neutrals to b = +1.2..+2.3 (yellow). The corrections below undo exactly those drifts, softly, and leave skin (hue 30-60) alone."""
import numpy as np
from engine import smooth, hue_w, skin_weight
from films2 import softlim, lw
from films3 import scurve


def pull(h, w, target, k):
    """hue pulled towards target (degrees) by factor k, weighted by w"""
    d = (target - np.degrees(h) + 180) % 360 - 180
    return h + np.radians(d) * k * w


def rich(L, C, h, s, P):
    s = 1 - (1 - s) ** 2
    ns = 1 - s
    L2 = scurve(L, P['contrast']) + P['black'] * (1 - smooth(L, 0.0, 0.25))
    # ---- vegetation: back to Standard's green hue, richer than Camera today, dark leaves included
    wg = hue_w(h, 112, 38) * smooth(C, 0.018, 0.04) * (1 - smooth(C, 0.09, 0.13)) * ns
    h2 = pull(h, wg, P['green_h'], P['green_k'])
    cm = np.exp(wg * np.log(P['green_cm']))
    L2 = L2 + P['green_dl'] * wg
    # ---- sky: pure blue, richer, soft chroma limit at the top, clouds (low chroma) untouched
    wb = hue_w(h, 238, 50) * smooth(C, 0.03, 0.055) * ns
    h2 = pull(h2, wb, P['sky_h'], P['sky_k'])
    cm = cm * np.exp(wb * np.log(P['sky_cm']))
    L2 = L2 - P['sky_dl'] * wb
    # ---- reds: rich, skin protected
    wr = hue_w(h, 27, 22) * smooth(C, 0.05, 0.1) * ns
    cm = cm * np.exp(wr * np.log(P['red_cm']))
    # ---- warm light kept golden (optional)
    ww = hue_w(h, 78, 28) * smooth(C, 0.05, 0.09) * smooth(L, 0.55, 0.75) * ns
    cm = cm * (1 + P['warm_cm'] * ww); h2 = h2 - np.radians(P['warm_dh']) * ww
    C2 = C * cm
    C2 = np.where(wb > 0, C2 + wb * (softlim(C2, P['sky_knee'], P['sky_max']) - C2), C2)
    C2 = np.where(wg > 0, C2 + wg * (softlim(C2, P['green_knee'], P['green_max']) - C2), C2)
    # ---- whites: bright, low-chroma pixels with a yellow/green cast go to clean white (slight warmth)
    a, b = C2 * np.cos(h2), C2 * np.sin(h2)
    wh = smooth(L, 0.78, 0.9) * (1 - smooth(C, 0.04, 0.07)) * np.maximum(hue_w(h, 112, 50), 1 - smooth(C, 0.012, 0.03)) * ns   # skin hues (<65) are outside this window
    a = a + P['white_mix'] * wh * (P['white_a'] - a); b = b + P['white_mix'] * wh * (P['white_b'] - b)
    return L2, np.hypot(a, b), np.arctan2(b, a)


BASE = dict(contrast=0.10, black=-0.006, green_h=141, green_k=0.95, green_cm=1.7, green_dl=0.0, green_knee=0.07, green_max=0.11,
            sky_h=256, sky_k=0.9, sky_cm=1.45, sky_dl=0.02, sky_knee=0.095, sky_max=0.15,
            red_cm=1.15, warm_cm=0.0, warm_dh=0, white_a=-0.004, white_b=0.003, white_mix=1.0)
RICH = dict(BASE)
RICHWARM = dict(BASE, white_a=-0.001, white_b=0.011, warm_cm=0.25, warm_dh=6, white_mix=0.85)
EKTAR = dict(BASE, contrast=0.22, black=-0.012, green_cm=2.0, green_dl=-0.01, green_knee=0.08, green_max=0.125,
             sky_cm=1.65, sky_dl=0.035, sky_knee=0.105, sky_max=0.17, red_cm=1.32, white_b=0.002)

LOOKS4 = {'rich': (lambda L, C, h, s: rich(L, C, h, s, RICH), True),
          'richwarm': (lambda L, C, h, s: rich(L, C, h, s, RICHWARM), True),
          'ektar': (lambda L, C, h, s: rich(L, C, h, s, EKTAR), True)}
