"""Lens characters, desktop prototype (no firmware, no film transforms, no grain, no halation).

Three looks, each with Medium and Strong:
  swirl   Helios-44 style swirly bokeh, only where the picture is already soft
  mist    neutral Pro-Mist bloom (glow in the highlight's own colour)
  corners old-lens corners: softness, radial colour fringing, tinted vignette

Written so that every step can become an ARM module: maps at <= 1024..1200 px wide built with box
blurs, the full-resolution pass is a per-strip blend of upsampled low-resolution maps.
Input is the real JPEG, taken through 8-bit YCbCr 4:2:2 planes (chroma halved horizontally) first.
"""
import sys, os, time, tracemalloc
import numpy as np
from PIL import Image, ImageOps, ImageDraw, ImageFont

STRIP = 192
_rng = np.random.default_rng(7)
DITHER = (_rng.random((256, 256, 1)) - _rng.random((256, 256, 1))).astype(np.float32) * 0.8   # triangular, +-0.8 LSB; a 256x256 table on ARM


def q8(x, r0=0):
    """Round to 8 bits with the dither tile (hides banding of smooth gradients)."""
    h, w = x.shape[:2]
    d = np.tile(DITHER, (h // 256 + 2, w // 256 + 1, 1))[r0 % 256:r0 % 256 + h, :w]
    return np.clip(x + 0.5 + d, 0, 255).astype(np.uint8)
G = 2.2


# ---------------------------------------------------------------- io
def load_422(path, maxw=None):
    """JPEG -> (Y, Cb, Cr) uint8 planes with 4:2:2 chroma (Cb/Cr half width)."""
    im = ImageOps.exif_transpose(Image.open(path)).convert('RGB')
    if maxw and im.width > maxw:
        im = im.resize((maxw, round(im.height * maxw / im.width)), Image.BOX)
    w = im.width & ~1
    im = im.crop((0, 0, w, im.height))
    y, cb, cr = [np.asarray(c) for c in im.convert('YCbCr').split()]
    # 4:2:2: average pairs of chroma samples
    cb = ((cb[:, 0::2].astype(np.uint16) + cb[:, 1::2] + 1) >> 1).astype(np.uint8)
    cr = ((cr[:, 0::2].astype(np.uint16) + cr[:, 1::2] + 1) >> 1).astype(np.uint8)
    return y, cb, cr


def planes_to_rgb(y, cb, cr, y0=0, y1=None):
    """4:2:2 planes -> RGB float32 (strip y0:y1), chroma upsampled linearly."""
    y1 = y.shape[0] if y1 is None else y1
    Y = y[y0:y1].astype(np.float32)
    def up(c):
        c = c[y0:y1].astype(np.float32)
        o = np.empty((c.shape[0], c.shape[1] * 2), np.float32)
        o[:, 0::2] = c
        o[:, 1::2] = c
        # simple linear interpolation of the odd samples
        o[:, 1:-1:2] = 0.5 * (c[:, :-1] + c[:, 1:]) if c.shape[1] > 1 else o[:, 1:-1:2]
        return o
    Cb = up(cb) - 128
    Cr = up(cr) - 128
    R = Y + 1.402 * Cr
    B = Y + 1.772 * Cb
    Gc = Y - 0.344136 * Cb - 0.714136 * Cr
    return np.stack([R, Gc, B], -1)


def rgb_small(y, cb, cr, sw):
    """Low-resolution RGB (float32, 0..255), box-averaged to width sw, from planes."""
    h, w = y.shape
    f = max(1, int(round(w / sw)))
    out = []
    # average strips of f rows
    hh = (h // f) * f
    rows = []
    for r0 in range(0, hh, f * 16):
        r1 = min(hh, r0 + f * 16)
        rgb = planes_to_rgb(y, cb, cr, r0, r1)
        rgb = rgb[:, : (w // f) * f].reshape((r1 - r0) // f, f, w // f, f, 3).mean((1, 3))
        rows.append(rgb)
    return np.clip(np.concatenate(rows, 0), 0, 255).astype(np.float32)


# ---------------------------------------------------------------- small-map tools
def box1d(a, r, axis):
    """Box blur of radius r along an axis, edge replicated (float64 running sum)."""
    if r < 1:
        return a
    a = np.moveaxis(a, axis, 0).astype(np.float64)
    pad = np.concatenate([np.repeat(a[:1], r + 1, 0), a, np.repeat(a[-1:], r, 0)], 0)
    c = np.cumsum(pad, 0)
    out = (c[2 * r + 1:] - c[:-2 * r - 1]) / (2 * r + 1)
    return np.moveaxis(out[: a.shape[0]], 0, axis).astype(np.float32)


def blur(a, r, passes=3):
    r = int(round(r))
    for _ in range(passes):
        a = box1d(box1d(a, r, 0), r, 1)
    return a


def maxfilt(a, r):
    from numpy.lib.stride_tricks import sliding_window_view as sw
    for ax in (0, 1):
        a = np.moveaxis(a, ax, 0)
        p = np.concatenate([np.repeat(a[:1], r, 0), a, np.repeat(a[-1:], r, 0)], 0)
        a = np.moveaxis(sw(p, 2 * r + 1, axis=0).max(-1), 0, ax) if False else \
            np.moveaxis(np.max(np.stack([p[i:i + a.shape[0]] for i in range(2 * r + 1)]), 0), 0, ax)
    return a


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def bil_rows(small, y0, y1, H, W):
    """Bilinear upsample of small (h,w[,c]) to full-res rows y0:y1 of an H x W picture."""
    h, w = small.shape[:2]
    ys = (np.arange(y0, y1) + 0.5) * h / H - 0.5
    xs = (np.arange(W) + 0.5) * w / W - 0.5
    ya = np.clip(np.floor(ys).astype(int), 0, h - 1); yb = np.clip(ya + 1, 0, h - 1)
    xa = np.clip(np.floor(xs).astype(int), 0, w - 1); xb = np.clip(xa + 1, 0, w - 1)
    fy = np.clip(ys - np.floor(ys), 0, 1).astype(np.float32); fx = np.clip(xs - np.floor(xs), 0, 1).astype(np.float32)
    if small.ndim == 3:
        fy = fy[:, None, None]; fx = fx[None, :, None]
    else:
        fy = fy[:, None]; fx = fx[None, :]
    top = small[ya][:, xa] * (1 - fx) + small[ya][:, xb] * fx
    bot = small[yb][:, xa] * (1 - fx) + small[yb][:, xb] * fx
    return top * (1 - fy) + bot * fy


LIN = ((np.arange(256) / 255.0) ** G).astype(np.float32)


def to_lin(v):
    return (np.clip(v, 0, 255) / 255.0) ** G


def to_gam(l):
    return 255.0 * np.clip(l, 0, 1) ** (1 / G)


def write_planes_rgb(strips, w, h):
    return np.concatenate(strips, 0).astype(np.uint8)


# ---------------------------------------------------------------- MIST (Pro-Mist bloom)
MIST = {
    # (gain tight, gain mid, gain wide, threshold start, threshold full)
    'medium': dict(g=(0.55, 0.60, 0.55), t=(0.35, 0.85)),
    'strong': dict(g=(1.00, 1.20, 1.10), t=(0.30, 0.80)),
}
MIST_R = (0.0035, 0.014, 0.045)       # box radius (3 passes) as a fraction of picture width


def mist_maps(small_rgb, P):
    """Glow in linear light, at the low resolution of small_rgb (<=1024 wide), own colour."""
    h, w, _ = small_rgb.shape
    lin = to_lin(small_rgb)
    m = lin.max(-1)
    b = smoothstep(P['t'][0], P['t'][1], m)
    # compactness: big bright areas (sky, walls) glow less than lamps and signs
    # compactness: share of bright pixels within ~4 % of the width. Lamps and signs are small and
    # surrounded by dark; sky, walls and plazas are not, and get no glow at all.
    area = blur(b, 0.035 * w, 2)
    comp = 1.0 - smoothstep(0.22, 0.60, area)
    # daylight guard: no glow where the wider neighbourhood (~10 % of the width) is itself bright
    comp = comp * (1.0 - smoothstep(0.07, 0.28, blur(m, 0.08 * w, 2)))
    src = lin * (b * comp)[..., None]
    glow = 0
    for g, r in zip(P['g'], MIST_R):
        # wider blurs spread the same energy over more pixels: gain scaled up so they still read
        glow = glow + g * blur(src, r * w, 3) * (1 + 6 * (r / MIST_R[0]) ** 0.5 * 0.1)
    return np.clip(glow, 0, 4).astype(np.float32)


def mist_apply(y, cb, cr, P, sw=1024):
    h, w = y.shape[0], y.shape[1]
    small = rgb_small(y, cb, cr, sw)
    glow = mist_maps(small, P)
    out = np.empty((h, w, 3), np.uint8)
    for r0 in range(0, h, STRIP):
        r1 = min(h, r0 + STRIP)
        rgb = planes_to_rgb(y, cb, cr, r0, r1)
        lin = to_lin(rgb)
        gl = bil_rows(glow, r0, r1, h, w)
        gl = gl / (1 + gl * 0.5)                    # soft roll-off
        lin = 1 - (1 - lin) * (1 - np.clip(gl, 0, 0.98))   # screen: bright stays defined, no clip
        out[r0:r1] = q8(to_gam(lin), r0)
    return out


# ---------------------------------------------------------------- CORNERS (old lens)
CORNERS = {
    'medium': dict(soft=0.75, ca=0.0020, vig=0.55, tint=0.18, r0=0.40, swirl=0.0),
    'strong': dict(soft=1.00, ca=0.0042, vig=0.85, tint=0.30, r0=0.30, swirl=0.0),
}


def corners_apply(y, cb, cr, P, sw=1200):
    h, w = y.shape
    small = rgb_small(y, cb, cr, sw)            # source for the soft layer (<=1200 wide)
    small2 = rgb_small(y, cb, cr, sw // 2)
    small3 = rgb_small(y, cb, cr, sw // 4)
    cx, cy = (w - 1) / 2, (h - 1) / 2
    rmax = float(np.hypot(cx, cy))
    out = np.empty((h, w, 3), np.uint8)
    xs = np.arange(w, dtype=np.float32) - cx
    x0r = (np.arange(w) - cx)
    for r0 in range(0, h, STRIP):
        r1 = min(h, r0 + STRIP)
        ys = (np.arange(r0, r1, dtype=np.float32) - cy)[:, None]
        rr = np.sqrt(xs[None, :] ** 2 + ys ** 2) / rmax           # 0 at the centre, 1 in the corners
        t = smoothstep(P['r0'], 1.0, rr)                           # 0 inside, 1 at the corners
        rgb = planes_to_rgb(y, cb, cr, r0, r1)
        if t.max() > 0:
            # --- radial colour fringing: red outward, blue inward (lateral CA), grows with r^2
            sh = P['ca'] * w * t * t                               # pixels
            ux = xs[None, :] / (rr * rmax + 1e-3); uy = ys / (rr * rmax + 1e-3)
            def samp(ch, sgn):
                sx = np.clip(np.arange(w)[None, :] + sgn * sh * ux, 0, w - 1.001)
                sy = np.clip(np.arange(r0, r1)[:, None] + sgn * sh * uy, 0, h - 1.001)
                ix = np.floor(sx).astype(int); iy = np.floor(sy).astype(int)
                fx = sx - ix; fy = sy - iy
                # rows outside the strip are fetched from the full RGB of the margin
                lo = max(0, int(np.floor(sy.min()))); hi = min(h, int(np.ceil(sy.max())) + 2)
                blk = planes_to_rgb(y, cb, cr, lo, hi)[..., ch]
                a = blk[iy - lo, ix]; b = blk[iy - lo, np.minimum(ix + 1, w - 1)]
                c = blk[np.minimum(iy + 1, hi - 1) - lo, ix]; d = blk[np.minimum(iy + 1, hi - 1) - lo, np.minimum(ix + 1, w - 1)]
                return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy
            rgb[..., 0] = samp(0, +1)
            rgb[..., 2] = samp(2, -1)
            # --- softness: blend towards the low-resolution copy (two blurs mixed)
            s1 = bil_rows(small, r0, r1, h, w); s2 = bil_rows(small2, r0, r1, h, w)
            s3 = bil_rows(small3, r0, r1, h, w)
            soft = 0.15 * s1 + 0.30 * s2 + 0.55 * s3
            m = (P['soft'] * smoothstep(0.0, 1.0, t) ** 0.9)[..., None]
            m = np.clip(m, 0, 0.95)
            rgb = rgb * (1 - m) + soft * m
            # --- vignette with a colour shift (warm, blue and a little green fall first)
            v = P['vig'] * t ** 1.6
            tint = P['tint']
            lin = to_lin(rgb)
            f = np.stack([1 - v * (1 - 0.30 * tint), 1 - v * (1 + 0.05 * tint), 1 - v * (1 + 0.55 * tint)], -1)
            lin = lin * np.clip(f, 0, 1)
            # old-lens veil: a little lift in the dark corners (low contrast), slightly warm
            lin = lin + (0.010 * t ** 2 * P['soft'])[..., None] * np.array([1.0, 0.85, 0.6], np.float32)
            rgb = to_gam(lin)
        out[r0:r1] = q8(rgb, r0)
    return out


# ---------------------------------------------------------------- SWIRL
SWIRL = {
    'medium': dict(L=0.085, p=1.5, boost=3.0, taps=33),
    'strong': dict(L=0.170, p=1.4, boost=5.5, taps=41),
}
SOFT_E = (0.9, 2.6)       # smoothed gradient energy (grey levels per low-res px): soft below, sharp above


def softness_map(small):
    """Low-res 'already soft' map (1 soft .. 0 sharp). Sharpness is the ratio of the gradient at a
    fine scale (+-1 px) to the gradient at a coarse scale (+-5 px): near 1 on a crisp edge, near 0.2
    on an edge that is already blurred wide, whatever its contrast (so out-of-focus lights and
    windows read as soft). Sharp evidence is dilated and feathered so the flat parts of an in-focus
    subject (skin, plates) stay protected."""
    h, w, _ = small.shape
    yl = small @ np.array([0.299, 0.587, 0.114], np.float32)
    yl = blur(yl, 1, 1)                                     # 3x3 box: keeps sensor noise out
    def grad(o):
        p = np.pad(yl, o, mode='edge')
        return np.abs(p[o:-o, 2 * o:] - p[o:-o, :-2 * o]) + np.abs(p[2 * o:, o:-o] - p[:-2 * o, o:-o])
    rs = 0.010 * w
    ef = blur(grad(1), rs, 2)
    ec = blur(grad(5), rs, 2)
    ratio = ef * 5 / (ec + 0.5)                             # (+-1 px gradient) / (+-5 px gradient) * 5 / ... see below
    ratio = ef / (ec + 0.5)
    evid = smoothstep(0.30, 0.48, ratio) * smoothstep(0.9, 3.0, ec)
    q = 4
    eq = evid[: (h // q) * q, : (w // q) * q].reshape(h // q, q, w // q, q).max((1, 3))
    eq = maxfilt(eq, max(1, int(round(0.036 * w / q))))
    eq = blur(eq, 0.014 * w / q, 2)
    e2 = bil_rows(eq, 0, h, h, w)
    return np.clip(1 - 3.0 * e2, 0, 1).astype(np.float32), e2


def swirl_render(small, M, P, strong_tail=True):
    """Tangential blur around the centre at low resolution, M-weighted so sharp pixels never
    leak into the background; near-clipped highlights lifted first (linear light)."""
    h, w, _ = small.shape
    lin = to_lin(small)
    hb = smoothstep(0.80, 0.97, small.max(-1) / 255.0)
    boosted = lin * (1 + P['boost'] * hb ** 2)[..., None]
    Pm = np.concatenate([boosted * M[..., None], M[..., None]], -1).astype(np.float32).reshape(-1, 4)
    cx, cy = (w - 1) / 2, (h - 1) / 2
    rmax = float(np.hypot(cx, cy))
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dx = xx - cx; dy = yy - cy
    r = np.sqrt(dx * dx + dy * dy)
    rn = r / rmax
    L = P['L'] * w * rn ** P['p']                       # arc length in pixels, ~ r^p
    sel = (M > 0.02) & (rn > 0.10)
    ii = np.nonzero(sel.ravel())[0]
    dxs, dys, rs, Ls = dx.ravel()[ii], dy.ravel()[ii], np.maximum(r.ravel()[ii], 1), L.ravel()[ii]
    num = np.zeros((ii.size, 4), np.float32)
    K = P['taps']
    for k in range(K):
        t = (k / (K - 1) - 0.5)
        th = t * Ls / rs
        c, s = np.cos(th), np.sin(th)
        sx = cx + dxs * c - dys * s; sy = cy + dxs * s + dys * c
        sx = np.clip(sx, 0, w - 1.001); sy = np.clip(sy, 0, h - 1.001)
        ix = sx.astype(int); iy = sy.astype(int); fx = (sx - ix)[:, None]; fy = (sy - iy)[:, None]
        i00 = iy * w + ix
        v = (Pm[i00] * (1 - fx) + Pm[i00 + 1] * fx) * (1 - fy) + (Pm[i00 + w] * (1 - fx) + Pm[i00 + w + 1] * fx) * fy
        num += v
    res = lin.copy()
    den = np.maximum(num[:, 3:4], 1e-3)
    sw_lin = num[:, :3] / den
    ok = (num[:, 3:4] > 0.05)[:, 0]
    flat = res.reshape(-1, 3)
    # soft knee on very bright results, then back to gamma
    cur = flat[ii]
    new = np.where(ok[:, None], sw_lin, cur)
    flat[ii] = new
    return to_gam(res / (1 + np.maximum(res - 1, 0) * 0.5)).astype(np.float32), small


def swirl_apply(y, cb, cr, P, sw=1200, return_mask=False):
    h, w = y.shape
    small = rgb_small(y, cb, cr, sw)
    M, _ = softness_map(small)
    sm, orig = swirl_render(small, M, P)
    # amount ramps with radius: nothing in the middle
    sh, sw_ = small.shape[:2]
    yy, xx = np.mgrid[0:sh, 0:sw_].astype(np.float32)
    rn = np.hypot(xx - (sw_ - 1) / 2, yy - (sh - 1) / 2) / np.hypot((sw_ - 1) / 2, (sh - 1) / 2)
    Mr = (M * smoothstep(0.10, 0.35, rn)).astype(np.float32)
    out = np.empty((h, w, 3), np.uint8)
    rho = 0.55   # keep this share of the full-resolution residual (grain / noise) inside the swirl
    for r0 in range(0, h, STRIP):
        r1 = min(h, r0 + STRIP)
        full = planes_to_rgb(y, cb, cr, r0, r1)
        m = bil_rows(Mr, r0, r1, h, w)[..., None]
        o_up = bil_rows(orig, r0, r1, h, w); s_up = bil_rows(sm, r0, r1, h, w)
        res = full + m * (s_up - o_up) - m * (1 - rho) * (full - o_up)
        out[r0:r1] = q8(res, r0)
    if return_mask:
        return out, Mr
    return out


# ---------------------------------------------------------------- sheets
def font(sz):
    for f in ('arial.ttf', 'segoeui.ttf', 'DejaVuSans.ttf'):
        try:
            return ImageFont.truetype(f, sz)
        except Exception:
            pass
    return ImageFont.load_default()


def panel(img, w=900, label=''):
    im = Image.fromarray(img) if isinstance(img, np.ndarray) else img
    im = im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    f = font(26)
    tw = d.textlength(label, font=f)
    d.rectangle((8, 8, 8 + tw + 16, 44), fill=(0, 0, 0))
    d.text((16, 10), label, fill=(255, 255, 255), font=f)
    return im


def make_sheet(rows, path, w=900):
    """rows: list of (name, [orig, medium, strong]) arrays"""
    ims = []
    for name, trio in rows:
        ims.append([panel(trio[0], w, name + '  Original'), panel(trio[1], w, 'Medium'), panel(trio[2], w, 'Strong')])
    gap = 6
    rh = [max(i.height for i in r) for r in ims]
    S = Image.new('RGB', (3 * w + 2 * gap, sum(rh) + gap * (len(rh) - 1)), (20, 20, 20))
    y = 0
    for r, hh in zip(ims, rh):
        for k, p in enumerate(r):
            S.paste(p, (k * (w + gap), y))
        y += hh + gap
    S.save(path)
    return S


FUNCS = {'swirl': (swirl_apply, SWIRL), 'mist': (mist_apply, MIST), 'corners': (corners_apply, CORNERS)}


def run(kind, path, level, maxw=None):
    f, tab = FUNCS[kind]
    y, cb, cr = load_422(path, maxw)
    return f(y, cb, cr, tab[level])


def orig_rgb(path, maxw=None):
    y, cb, cr = load_422(path, maxw)
    return np.clip(planes_to_rgb(y, cb, cr) + 0.5, 0, 255).astype(np.uint8)


def measure(kind, path, level):
    """Peak extra memory of one call (numpy, bytes) beyond the input planes and the output picture."""
    f, tab = FUNCS[kind]
    y, cb, cr = load_422(path)
    tracemalloc.start()
    base = tracemalloc.get_traced_memory()[0]
    t = time.time()
    o = f(y, cb, cr, tab[level])
    dt = time.time() - t
    cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return (peak - cur) / 1e6, dt, y.shape[1] * y.shape[0] / 1e6


if __name__ == '__main__':
    kind, path, level = sys.argv[1:4]
    out = run(kind, path, level, int(sys.argv[5]) if len(sys.argv) > 5 else None)
    Image.fromarray(out).save(sys.argv[4], quality=95)
