"""Colour engine prototype: per-film 3D LUT (33^3) on the finished 8-bit YCbCr 4:2:2 picture.
LUT index: (Y of the chroma pair = mean of its two lumas, Cb, Cr). LUT output: deltas (dY, dCb, dCr) in Q4.
Per pair: one integer tetrahedral lookup. Per pixel: Y += dY (the pair's luma correction), clip."""
import numpy as np
from common import *

N = 33
SMOOTH_PASSES = 0  # smoothing was tried: it did not reduce step sizes and leaked colour pushes into skin nodes
STEP = 8  # 256/32: index = v >> 3, fraction = v & 7 (exact, no division)

# ---------- YCbCr (JPEG, BT.601 full range) ----------
def rgb_to_ycc(rgb):  # float 0..255 in/out
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    y = 0.299 * r + 0.587 * g + 0.114 * b
    return np.stack([y, 128 + (b - y) * 0.564, 128 + (r - y) * 0.713], -1)

def ycc_to_rgb(ycc):
    y, cb, cr = ycc[..., 0], ycc[..., 1] - 128, ycc[..., 2] - 128
    return np.stack([y + 1.402 * cr, y - 0.344136 * cb - 0.714136 * cr, y + 1.772 * cb], -1)

def to_422(rgb8):
    """RGB8 -> (Y uint8 HxW, Cb uint8 Hx(W/2), Cr uint8): chroma averaged over horizontal pairs."""
    h, w = rgb8.shape[:2]
    w -= w % 2
    ycc = rgb_to_ycc(rgb8[:, :w].astype(np.float32))
    Y = np.round(ycc[..., 0])
    c = ycc[..., 1:].reshape(h, w // 2, 2, 2).mean(2)
    return np.clip(Y, 0, 255).astype(np.uint8), np.clip(np.round(c[..., 0]), 0, 255).astype(np.uint8), np.clip(np.round(c[..., 1]), 0, 255).astype(np.uint8)

def from_422(Y, Cb, Cr):
    cb = np.repeat(Cb, 2, 1).astype(np.float32); cr = np.repeat(Cr, 2, 1).astype(np.float32)
    rgb = ycc_to_rgb(np.stack([Y.astype(np.float32), cb, cr], -1))
    return np.clip(np.round(rgb), 0, 255).astype(np.uint8)

# ---------- LUT apply: integer tetrahedral, vectorised ----------
def lut_apply_422(Y, Cb, Cr, lut):
    """lut: int16 (33,33,33,3) in Q4 deltas. Returns new (Y, Cb, Cr) uint8."""
    h, w2 = Cb.shape
    Y = Y[:, :w2 * 2]
    Ym = ((Y[:, 0::2].astype(np.int32) + Y[:, 1::2] + 1) >> 1)
    out = np.empty((h, w2, 3), np.int32)
    for r0 in range(0, h, 256):
        sl = slice(r0, min(h, r0 + 256))
        v = np.stack([Ym[sl], Cb[sl].astype(np.int32), Cr[sl].astype(np.int32)], -1)
        out[sl] = _tetra(v, lut)
    dY = out[..., 0]; dCb = out[..., 1]; dCr = out[..., 2]
    Yn = np.clip(Y.astype(np.int32) + np.repeat(dY, 2, 1), 0, 255).astype(np.uint8)
    return Yn, np.clip(Cb.astype(np.int32) + dCb, 0, 255).astype(np.uint8), np.clip(Cr.astype(np.int32) + dCr, 0, 255).astype(np.uint8)

def _tetra(v, lut):
    idx = v >> 3; f = v & 7
    L = lut.astype(np.int32)
    def at(o):
        return L[idx[..., 0] + o[0], idx[..., 1] + o[1], idx[..., 2] + o[2]]
    order = np.argsort(-f, axis=-1, kind="stable")  # axes by descending fraction
    fs = np.take_along_axis(f, order, -1)
    base = at((0, 0, 0)).copy()
    acc = base * 8
    cur = [np.zeros_like(idx[..., 0]) for _ in range(3)]
    prev = base
    for k in range(3):
        for ax in range(3):
            cur[ax] = cur[ax] + (order[..., k] == ax)
        nxt = at(cur)
        acc += (nxt - prev) * fs[..., k:k + 1]
        prev = nxt
    return (acc + 64) >> 7   # Q4 values * 8 (fraction denominator) -> /128, rounded

# ---------- LUT build from a colour transform in OkLCh ----------
def smooth(x, a, b):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)

def hue_w(h, c, wd):
    """Raised-cosine window over hue (radians in, degrees for c/wd): 1 at c, 0 at +-wd."""
    d = (np.degrees(h) - c + 180) % 360 - 180
    return 0.5 * (1 + np.cos(np.pi * np.clip(d / wd, -1, 1)))

def skin_weight(L, C, h):
    return hue_w(h, 50, 34) * smooth(C, 0.012, 0.045) * (1 - smooth(C, 0.15, 0.22)) * smooth(L, 0.28, 0.5) * (1 - smooth(L, 0.93, 0.99))

def build_lut(transform, neutral_exact=True):
    """transform(L, C, h, skin) -> (L2, C2, h2) arrays. Returns int16 LUT (33,33,33,3), Q4 deltas."""
    g = np.minimum(np.arange(N) * STEP, 255).astype(np.float64)
    Yg, Cbg, Crg = np.meshgrid(g, g, g, indexing="ij")
    ycc = np.stack([Yg, Cbg, Crg], -1).reshape(-1, 3)
    rgb = np.clip(ycc_to_rgb(ycc), 0, 255)
    ycc0 = rgb_to_ycc(rgb)  # node as if clipped into gamut: out-of-gamut nodes behave as their clipped colour
    lab = srgb_to_oklab(rgb / 255)
    L, a, b = lab[:, 0], lab[:, 1], lab[:, 2]
    C = np.hypot(a, b); h = np.arctan2(b, a)
    skin = skin_weight(L, C, h)
    L2, C2, h2 = transform(L, C, h, skin)
    out = gamut_map(L2, np.maximum(C2, 0), h2) * 255
    d = rgb_to_ycc(out) - ycc0
    if neutral_exact:  # a film without a tint keeps the grey axis exactly grey (no white-balance change)
        d[:, 1:] = np.where(C[:, None] < 0.004, 0, d[:, 1:])
    d = d.reshape(N, N, N, 3)
    for _ in range(SMOOTH_PASSES):   # [1 2 1]/4 along each axis: limits the LUT's gain so 8-bit noise is not amplified
        for ax in range(3):
            p = np.pad(d, [(1, 1) if a == ax else (0, 0) for a in range(4)], mode="edge")
            sl = lambda o: tuple(slice(o, o + N) if a == ax else slice(None) for a in range(4))
            d = (p[sl(0)] + 2 * p[sl(1)] + p[sl(2)]) / 4
    if neutral_exact:
        d[16, 16, :, :] = d[16, 16, :, :]  # (grey axis handled below)
        d[:, 16, 16, 1:] = 0
    return np.round(d * 16).astype(np.int16)

def identity_lut():
    return np.zeros((N, N, N, 3), np.int16)

def process_full(rgb8_cam, lut):
    Y, Cb, Cr = to_422(rgb8_cam)
    return (Y, Cb, Cr), lut_apply_422(Y, Cb, Cr, lut)
