"""Round 3: four whole-frame Portra 400 characters (Frontier scan, Noritsu scan, overexposed +2, pushed +1), OkLCh, soft weights.
Camera today = the real Portra fit. All transforms are smooth functions of L, C, h; skin is weighted softly and capped."""
import numpy as np
from engine import smooth, hue_w, skin_weight


def scurve(L, a):
    """mix of identity and smoothstep: a>0 adds contrast around L=0.5 (slope 1+0.5a mid, 1-a at the ends), a<0 flattens"""
    S = L * L * (3 - 2 * L)
    return (1 - a) * L + a * S


def prep(L, C, h, s):
    return 1 - (1 - s) ** 2


def tint(a, b, amt, deg):
    return a + amt * np.cos(np.radians(deg)), b + amt * np.sin(np.radians(deg))


def hshift(h, w, deg):
    return h + np.radians(deg) * w


# ---------------- Frontier: bold, bright, golden skin, shadow density, highlights near clipping ----------------
FR = dict(contrast=0.58, toe=-0.015, hi=0.05, chroma=1.22, skin_hue=+12, skin_cm=1.07, green=(-26, 1.25), sky=(-18, 1.25))


def frontier(L, C, h, s, P=FR):
    s = prep(L, C, h, s)
    L2 = scurve(L, P['contrast']) + P['toe'] * (1 - smooth(L, 0.0, 0.25)) + P['hi'] * smooth(L, 0.55, 0.95) + 0.015 * smooth(L, 0.2, 0.6) * (1 - smooth(L, 0.6, 0.9))
    gate = smooth(C, 0.008, 0.05)
    wg = hue_w(h, 140, 45) * gate; wb = hue_w(h, 245, 45) * gate
    h2 = h + np.radians(P['green'][0]) * wg + np.radians(P['sky'][0]) * wb + np.radians(P['skin_hue']) * s * gate
    cm = np.exp(np.log(P['chroma']) + wg * np.log(P['green'][1]) + wb * np.log(P['sky'][1]) + s * (np.log(P['skin_cm']) - np.log(P['chroma'])))
    return L2, C * cm, h2


# ---------------- Noritsu: lower contrast, open shadows, soft highlights, rosy skin, rich colour ----------------
NO = dict(contrast=-0.26, lift=0.022, shoulder=0.07, chroma=1.30, skin_hue=-11, skin_cm=1.10)


def noritsu(L, C, h, s, P=NO):
    s = prep(L, C, h, s)
    L2 = scurve(L, P['contrast']) + P['lift'] * (1 - smooth(L, 0.0, 0.45)) - P['shoulder'] * smooth(L, 0.72, 1.0) + 0.025 * smooth(L, 0.3, 0.6) * (1 - smooth(L, 0.6, 0.9))
    gate = smooth(C, 0.008, 0.05)
    h2 = h + np.radians(P['skin_hue']) * s * gate
    cm = np.exp(np.log(P['chroma']) + s * (np.log(P['skin_cm']) - np.log(P['chroma'])))
    return L2, C * cm, h2


# ---------------- Overexposed +2: bright, luminous warm-pink skin and highlights, lifted cyan-leaning shadows ----------------
P2 = dict(gamma=1.38, floor=0.035, chroma=1.10, skin_hue=-7, skin_cm=1.06, pink=0.016, cyan=0.013)


def plus2(L, C, h, s, P=P2):
    s = prep(L, C, h, s)
    L2 = P['floor'] + (1 - P['floor']) * (1 - (1 - L) ** P['gamma'])
    gate = smooth(C, 0.008, 0.05)
    h2 = h + np.radians(P['skin_hue']) * s * gate
    cm = np.exp(np.log(P['chroma']) + s * (np.log(P['skin_cm']) - np.log(P['chroma'])))
    C2 = C * cm
    a, b = C2 * np.cos(h2), C2 * np.sin(h2)
    hi = smooth(L, 0.62, 0.95); lo = 1 - smooth(L, 0.0, 0.4)
    a, b = tint(a, b, P['pink'] * hi * (1 - 0.0 * s), 28)          # pink highlights
    a, b = tint(a, b, P['cyan'] * lo * (1 - s), 215)               # cyan lean in the lifted shadows
    return L2, np.hypot(a, b), np.arctan2(b, a)


# ---------------- Pushed +1: punchy contrast and colour, neutral, rich blacks ----------------
PU = dict(contrast=0.70, black=-0.015, mid=0.025, chroma=1.30, skin_cm=1.06)


def pushed(L, C, h, s, P=PU):
    s = prep(L, C, h, s)
    L2 = scurve(L, P['contrast']) + P['black'] * (1 - smooth(L, 0.0, 0.3)) + P['mid'] * smooth(L, 0.2, 0.55) * (1 - smooth(L, 0.55, 0.9))
    cm = np.exp(np.log(P['chroma']) + s * (np.log(P['skin_cm']) - np.log(P['chroma'])))
    return L2, C * cm, h


LOOKS3 = {'frontier': (frontier, True), 'noritsu': (noritsu, True), 'plus2': (plus2, False), 'pushed': (pushed, True)}
