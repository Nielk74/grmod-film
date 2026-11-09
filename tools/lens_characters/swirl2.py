"""Swirly bokeh, second attempt (desktop prototype, numpy and Pillow only).

EXPERIMENT, not part of any firmware or app build. Judged fun but not good enough to ship (2026-11-09).

The first version dragged pixels along arcs, wherever the picture looked "soft". It failed two ways:
crisp-edged bokeh discs looked sharp and were protected, and dark in-focus areas looked soft and
were smeared. Real swirl (Biotar, Helios 44 / 40) is not motion: off axis, the barrel clips each
out-of-focus disc into a cat's eye whose long axis runs along a circle around the frame centre.

So this version:
  1. finds the actual bokeh discs (circular Hough on bright-side edges, filled, of a consistent size);
  2. erases them to a local base and redraws each as a clipped cat's eye, curved along its circle;
  3. moves extended blurred lights only by a small arc tied to the size of the blur;
  4. changes nothing without positive evidence of defocus: unknown stays untouched.

Everything is computed at half resolution and added to the full picture as a difference.
"""
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
from lens_characters import STRIP, bil_rows, blur, load_422, maxfilt, planes_to_rgb, q8, rgb_small, smoothstep, to_gam, to_lin

LENSES = {
    # size: disc scale. f0, p: where the clip starts and how fast it grows (0 centre, 1 corner).
    # clip_in / clip_out: share of the radius removed on the side facing / away from the centre.
    # stretch: added tangential length at the corner. rb: radius of the clipping circles.
    # rim: bright edge. arc: tangential blur of extended lights, in disc radii, at the corner.
    # bg: arc length of the background swirl at the corner, as a share of the half-resolution width.
    'helios44': dict(size=1.05, f0=0.16, p=1.15, clip_in=0.62, clip_out=0.18, stretch=0.30, rb=1.6, rim=0.18, arc=1.4, bg=0.022),
    'helios40': dict(size=1.30, f0=0.08, p=0.95, clip_in=0.74, clip_out=0.30, stretch=0.70, rb=1.5, rim=0.28, arc=2.6, bg=0.045),
    'petzval': dict(size=1.15, f0=0.30, p=0.80, clip_in=0.60, clip_out=0.60, stretch=1.10, rb=2.2, rim=0.0, arc=4.0, bg=0.070),
}
RADII = np.geomspace(9.0, 48.0, 18)      # half-resolution disc radii; smaller ones are mostly glints on food and texture


def luma(rgb):
    return rgb @ np.array([0.299, 0.587, 0.114], np.float32)


def gradients(y):
    gx = np.zeros_like(y); gy = np.zeros_like(y)
    gx[:, 1:-1] = (y[:, 2:] - y[:, :-2]) * 0.5
    gy[1:-1, :] = (y[2:, :] - y[:-2, :]) * 0.5
    return gx, gy


def stamp(canvas, x, y, r, value=1.0):
    """Paint a filled disc into a 2-D array, keeping the maximum."""
    h, w = canvas.shape
    x0, x1 = max(0, int(x - r - 1)), min(w, int(x + r + 2))
    y0, y1 = max(0, int(y - r - 1)), min(h, int(y + r + 2))
    if x0 >= x1 or y0 >= y1:
        return
    yy, xx = np.ogrid[y0:y1, x0:x1]
    inside = (xx - x) ** 2 + (yy - y) ** 2 <= r * r
    canvas[y0:y1, x0:x1][inside] = value


def find_discs(rgb, edges, min_score=0.18, scale=1.0):
    """Bokeh discs as an array of (x, y, radius, score). Fills `edges` with arc-support maps."""
    h, w, _ = rgb.shape
    y = blur(luma(rgb), 1, 1)
    gx, gy = gradients(y)
    mag = np.hypot(gx, gy)
    py, px = np.nonzero(mag >= 5.0)
    nx = gx[py, px] / mag[py, px]; ny = gy[py, px] / mag[py, px]
    # the brighter side of the edge must be a light, not a mid-tone
    ix = np.clip((px + 3 * nx).astype(int), 0, w - 1); iy = np.clip((py + 3 * ny).astype(int), 0, h - 1)
    keep = y[iy, ix] >= 50
    px, py, nx, ny = px[keep], py[keep], nx[keep], ny[keep]
    def score_map(r):
        cx = np.rint(px + r * nx).astype(np.int64); cy = np.rint(py + r * ny).astype(np.int64)
        ok = (cx >= 0) & (cx < w) & (cy >= 0) & (cy < h)
        votes = np.bincount(cy[ok] * w + cx[ok], minlength=h * w).reshape(h, w).astype(np.float32)
        votes = blur(votes, 1, 1) * 9                         # 3x3 sum: the circle need not be perfect
        return votes / (2 * np.pi * r * 2.6)
    # Small radii fire on any edge, so a per-pixel "best radius" is wrong. Discs at one depth share one
    # size: count strong circles at each radius, keep the dominant sizes, and search only those.
    radii = RADII * scale
    maps = [score_map(r) for r in radii]
    counts = np.array([((m[1:-1, 1:-1] >= 0.42) & (m[1:-1, 1:-1] >= m[:-2, 1:-1]) & (m[1:-1, 1:-1] >= m[2:, 1:-1]) &
                        (m[1:-1, 1:-1] >= m[1:-1, :-2]) & (m[1:-1, 1:-1] >= m[1:-1, 2:])).sum() for m in maps], np.float32)
    weighted = np.convolve(counts * radii, np.ones(3) / 3, mode='same')
    best = np.zeros((h, w), np.float32)
    best_r = np.zeros((h, w), np.float32)
    chosen = np.zeros(len(radii), bool)
    if counts.max() >= 8:
        top = int(np.argmax(weighted))
        chosen |= np.abs(np.log(radii / radii[top])) < 0.16
        rest = weighted.copy(); rest[np.abs(np.log(radii / radii[top])) < 0.45] = 0
        if rest.max() >= 0.3 * weighted[top]:
            second = int(np.argmax(rest))
            chosen |= np.abs(np.log(radii / radii[second])) < 0.16
    supported = np.zeros(len(px), bool)
    for r, m, use in zip(radii, maps, chosen):
        if use:
            better = m > best
            best[better] = m[better]; best_r[better] = r
            # an edge is an arc of a bokeh disc if the circle it votes for has real support
            cx = np.clip(np.rint(px + r * nx).astype(np.int64), 0, w - 1); cy = np.clip(np.rint(py + r * ny).astype(np.int64), 0, h - 1)
            supported |= m[cy, cx] >= 0.16
    del maps
    sup = np.zeros((h, w), np.float32); unsup = np.zeros((h, w), np.float32)
    sup[py[supported], px[supported]] = 1; unsup[py[~supported], px[~supported]] = 1
    edges.update(sup=sup, unsup=unsup)
    peak = (best >= min_score)
    peak[1:-1, 1:-1] &= (best[1:-1, 1:-1] >= best[:-2, 1:-1]) & (best[1:-1, 1:-1] >= best[2:, 1:-1]) & \
                        (best[1:-1, 1:-1] >= best[1:-1, :-2]) & (best[1:-1, 1:-1] >= best[1:-1, 2:])
    cy, cx = np.nonzero(peak)
    order = np.argsort(-best[cy, cx])
    taken = np.zeros((h, w), bool)
    found = []
    for i in order:
        x, yc = int(cx[i]), int(cy[i]); r = float(best_r[yc, x])
        if taken[yc, x]:
            continue
        x0, x1 = max(0, int(x - r)), min(w, int(x + r + 1)); y0, y1 = max(0, int(yc - r)), min(h, int(yc + r + 1))
        patch = y[y0:y1, x0:x1]
        yy, xx = np.ogrid[y0:y1, x0:x1]
        d2 = (xx - x) ** 2 + (yy - yc) ** 2
        core = patch[d2 <= (0.72 * r) ** 2]
        if core.size < 8:
            continue
        level = np.median(core)
        # filled and flat-topped: rejects rings (glasses, snaps) and textured objects
        if level < 55 or (core >= 0.62 * level).mean() < 0.88 or core.std() > 0.28 * level:
            continue
        stamp_taken(taken, x, yc, 0.62 * r)
        found.append((x, yc, r, float(best[yc, x])))
    if not found:
        return np.zeros((0, 4), np.float32)
    d = np.array(found, np.float32)
    # one depth gives one size: keep sizes that many discs share
    lr = np.log(d[:, 2])
    support = np.array([(np.abs(lr - v) < 0.26).sum() for v in lr])
    d = d[support >= max(5, 0.04 * len(d))]
    # Letters and curved objects give many weak circles; real bokeh gives a good share of strong ones.
    # Measured: Christmas lights 21% strong, every photo with false matches 4% or less.
    strong = (d[:, 3] >= 0.42).sum() if len(d) else 0
    edges.update(strong=int(strong), total=len(d), radius=float(np.median(d[:, 2])) if len(d) else 0.0)
    # Glints on food and texture pile up at the smallest size searched; real bokeh is clearly larger.
    if strong < 12 or strong < 0.10 * len(d) or float(np.median(d[:, 2])) < 10.5:
        edges.update(sup=np.zeros((h, w), np.float32), unsup=np.zeros((h, w), np.float32))
        return np.zeros((0, 4), np.float32)
    return d


def stamp_taken(taken, x, y, r):
    stamp(taken, x, y, r, True)


def arc_field(edges, ref, h, w):
    """Where the bright edges are mostly arcs of the bokeh disc size: garlands and shapes made of discs.
    Straight or fine in-focus outlines (a hood, a face, a cable) do not fit such circles."""
    q = 4
    def down(a):
        return a[: (h // q) * q, : (w // q) * q].reshape(h // q, q, w // q, q).mean((1, 3))
    r = max(2.0, 1.6 * ref / q)
    s, u = blur(down(edges['sup']), r, 2), blur(down(edges['unsup']), r, 2)
    p = s / (s + 0.65 * u + 0.004)
    p = smoothstep(0.36, 0.58, p) * smoothstep(0.003, 0.014, s)
    return bil_rows(blur(p, 1.5, 1).astype(np.float32), 0, h, h, w)


def wide_lights(y, ref):
    """Bright areas far wider than a disc: shapes, not dots. 1 inside them and around their outline."""
    h, w = y.shape
    q = 2
    m = (y[: (h // q) * q, : (w // q) * q].reshape(h // q, q, w // q, q).mean((1, 3)) >= 215).astype(np.float32)
    core = erode(m, max(1, int(round(2.0 * ref / q))))
    area = maxfilt(core, max(1, int(round(3.2 * ref / q))))
    return bil_rows(area.astype(np.float32), 0, h, h, w)


def grow_field(near, sharp, rgb, ref):
    """Extend the bokeh field along connected, very bright light, so that a flower or garland changes
    as a whole and not in patches. Crisp edges of very bright shapes do not stop it (bokeh is crisp);
    crisp edges of anything dimmer do, which keeps a pale hood or a face out."""
    h, w, _ = rgb.shape
    y = blur(luma(rgb), 1, 1)
    glare = maxfilt(y, 3)
    stop = sharp * (1 - smoothstep(190, 215, glare))
    q = 4
    def down(a, how):
        return getattr(a[: (h // q) * q, : (w // q) * q].reshape(h // q, q, w // q, q), how)((1, 3))
    wall = blur(maxfilt(down(stop, 'max'), 1), 1, 1) > 0.25
    seed0 = down(near, 'mean') > 0.5
    allowed = (down(y, 'mean') >= 165) & ~wall
    seed = seed0.copy()
    for _ in range(max(4, int(round(8 * ref / q)))):
        grown = (maxfilt(seed.astype(np.float32), 1) > 0.5) & (allowed | seed0)
        if (grown == seed).all():
            break
        seed = grown
    extra = bil_rows(blur(seed.astype(np.float32), 1.5, 1).astype(np.float32), 0, h, h, w)
    return np.maximum(near, smoothstep(0.25, 0.65, extra))


def evidence(rgb, discs, edges):
    """Soft and sharp edge evidence (0..1 maps at full half-res size), both ignoring bokeh edges."""
    h, w, _ = rgb.shape
    y = blur(luma(rgb), 1, 1)
    def d(o):
        p = np.pad(y, o, mode='edge')
        return (np.abs(p[o:-o, 2 * o:] - p[o:-o, :-2 * o]) + np.abs(p[2 * o:, o:-o] - p[:-2 * o, o:-o])) / (2 * o)
    fine = d(1); coarse = d(6)
    contrast = coarse * 12
    ratio = fine / (coarse + 0.4)
    sharp = smoothstep(2.0, 3.2, ratio) * smoothstep(14, 34, contrast)
    soft = (1 - smoothstep(1.3, 2.0, ratio)) * smoothstep(12, 30, contrast)
    near = bokeh_field(discs, h, w)
    if len(discs):
        near = np.maximum(near, arc_field(edges, float(np.median(discs[:, 2])), h, w))
    return soft * (1 - near), sharp * (1 - near), near


def bokeh_field(discs, h, w):
    """The whole area a group of discs covers, gaps included: dots the detector missed are inside it."""
    field_map = np.zeros((h, w), np.float32)
    for x, yc, r, _ in discs:
        stamp(field_map, x, yc, 1.3 * r)
    if len(discs):
        q = 4
        small = field_map[: (h // q) * q, : (w // q) * q].reshape(h // q, q, w // q, q).mean((1, 3))
        ref = max(2, float(np.median(discs[:, 2])) / q)
        small = smoothstep(0.30, 0.55, blur(small, 1.4 * ref, 2))
        field_map = np.maximum(field_map, bil_rows(small.astype(np.float32), 0, h, h, w))
    return field_map


def defocus_mask(soft, sharp, near, w):
    """1 where there is positive evidence of defocus. No evidence means 0, so flat dark areas stay put."""
    h, _ = soft.shape
    q = 8
    def down(a, f):
        return a[: (h // q) * q, : (w // q) * q].reshape(h // q, q, w // q, q).__getattribute__(f)((1, 3))
    so, sh, ne = down(soft, 'mean'), down(sharp, 'max'), down(near, 'mean')
    W = so.shape[1]
    sh = blur(maxfilt(sh, max(1, round(0.010 * W))), 0.008 * W, 2)    # an in-focus edge protects its surroundings
    so = blur(so, 0.012 * W, 2)
    m = smoothstep(0.012, 0.05, so) * (1 - smoothstep(0.03, 0.22, sh))
    m = np.maximum(m, ne * (1 - smoothstep(0.10, 0.40, sh)))
    m = blur(m, 0.006 * W, 2)
    return bil_rows(m.astype(np.float32), 0, h, h, w).astype(np.float32), bil_rows(sh.astype(np.float32), 0, h, h, w)


def base_layer(lin, near, lights, ref, w):
    """The picture with its round dots replaced by a soft glow of their own light. A dark envelope
    here left black gaps: dense bokeh has a layer of dim lights behind the bright ones."""
    h, _, _ = lin.shape
    q = 4
    small = lin[: (h // q) * q, : (w // q) * q].reshape(h // q, q, w // q, q, 3).mean((1, 3))
    glow = blur(small, max(1.5, 1.6 * ref / q), 2) * 0.62
    up = bil_rows(glow.astype(np.float32), 0, h, h, w)
    a = blur(np.maximum(near * lights, 0).astype(np.float32), 0.45 * ref, 1)
    a = (smoothstep(0.08, 0.40, a) * near)[..., None].astype(np.float32)
    return lin * (1 - a) + np.minimum(up, lin) * a


def erode(a, r):
    return -maxfilt(-a, r)


def chunks(lights, near, discs, ref):
    """Bright masses far wider than a disc that no detected disc explains: flowers, signs. Followed
    along their own connected outline, so the boundary with the redrawn dots is never a square."""
    h, w = lights.shape
    covered = np.zeros((h, w), bool)
    for x, yc, r, _ in discs:
        stamp(covered, x, yc, 1.15 * r, True)
    q = 4
    mask = (lights > 0.5) & (near > 0.5) & ~covered
    m = mask[: (h // q) * q, : (w // q) * q].reshape(h // q, q, w // q, q).mean((1, 3)) > 0.5
    seed = erode(m.astype(np.float32), max(1, int(round(1.9 * ref / q)))) > 0.5
    for _ in range(max(10, int(round(16 * ref / q)))):
        grown = (maxfilt(seed.astype(np.float32), 1) > 0.5) & m
        if (grown == seed).all():
            break
        seed = grown
    area = maxfilt(seed.astype(np.float32), 1)
    return smoothstep(0.2, 0.7, bil_rows(blur(area, 1, 1).astype(np.float32), 0, h, h, w))


def sources(lights, near, discs, ref, level):
    """Dots the detector missed: one light per spot, spaced like real discs. A bright shape is its
    sources spread by the disc, so eroding it by the disc gives the sources back."""
    h, w = lights.shape
    covered = np.zeros((h, w), bool)
    for x, yc, r, _ in discs:
        stamp(covered, x, yc, 1.0 * r, True)
    q = 2
    mask = (lights > 0.5) & (near > 0.5)
    m = mask[: (h // q) * q, : (w // q) * q].reshape(h // q, q, w // q, q).all((1, 3))
    core = erode(m.astype(np.float32), max(1, int(round(0.72 * ref / q)))) > 0.5
    ys, xs = np.nonzero(core)
    xs, ys = (xs + 0.5) * q, (ys + 0.5) * q
    order = np.argsort(-level[ys.astype(int), xs.astype(int)])
    out = []
    for i in order:
        x, y = float(xs[i]), float(ys[i])
        if covered[min(h - 1, int(y)), min(w - 1, int(x))]:
            continue
        stamp(covered, x, y, 1.3 * ref, True)
        out.append((x, y))
    return out


def field(x, y, cx, cy, rmax):
    return float(np.hypot(x - cx, y - cy) / rmax)


def draw_cats_eye(sum_buf, max_buf, x, y, R, colour, L, cx, cy, rmax):
    """One clipped disc in polar-local coordinates, so that it curves around the frame centre."""
    h, w, _ = max_buf.shape
    r0 = float(np.hypot(x - cx, y - cy))
    t = smoothstep(L['f0'], 1.0, r0 / rmax) ** L['p']
    s = 1 + L['stretch'] * t
    ext = R * s * 1.25 + 3
    x0, x1 = max(0, int(x - ext)), min(w, int(x + ext + 2)); y0, y1 = max(0, int(y - ext)), min(h, int(y + ext + 2))
    if x0 >= x1 or y0 >= y1:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    dx, dy = xx - cx, yy - cy
    rad = np.hypot(dx, dy)
    th0 = np.arctan2(y - cy, x - cx)
    dth = (np.arctan2(dy, dx) - th0 + np.pi) % (2 * np.pi) - np.pi
    u = rad - r0                                 # outward
    v = r0 * dth / s                             # along the circle, undoing the stretch
    if r0 < 2 * R:                               # near the axis polar coordinates are meaningless: a plain disc
        u, v = xx - x, yy - y
    d = R - np.hypot(u, v)
    if t > 0:
        Rb = L['rb'] * R
        uin = Rb - R * (1 - L['clip_in'] * t)    # circle whose edge cuts the inner side
        uout = Rb - R * (1 - L['clip_out'] * t)
        d = np.minimum(d, Rb - np.hypot(u - uin, v))
        d = np.minimum(d, Rb - np.hypot(u + uout, v))
    edge = 1.6 + 0.11 * R
    alpha = np.clip(d / edge + 0.5, 0, 1).astype(np.float32)
    if L['rim'] > 0:
        # brighter toward the edge, a little dimmer inside: a real bubble is not a flat sticker
        body = 0.80 + 0.20 * (1 - smoothstep(0.0, 0.75 * R, d)).astype(np.float32)
        alpha = alpha * body * (1 + L['rim'] * (1 - smoothstep(0, 0.30 * R, d)).astype(np.float32))
    patch = alpha[..., None] * colour
    if sum_buf is not None:
        sum_buf[y0:y1, x0:x1] += patch
    max_buf[y0:y1, x0:x1] = np.maximum(max_buf[y0:y1, x0:x1], patch)


def arc_blur(lin, M, Lpx, cx, cy, taps=21):
    """Tangential blur with a length per pixel. Weighted by M, so sharp pixels never leak in."""
    h, w, _ = lin.shape
    Pm = np.concatenate([lin * M[..., None], M[..., None]], -1).astype(np.float32).reshape(-1, 4)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dx, dy = xx - cx, yy - cy
    r = np.maximum(np.hypot(dx, dy), 1)
    ii = np.nonzero(((M > 0.02) & (Lpx > 1.5)).ravel())[0]
    if ii.size == 0:
        return lin
    dxs, dys, rs, ls = dx.ravel()[ii], dy.ravel()[ii], r.ravel()[ii], Lpx.ravel()[ii]
    num = np.zeros((ii.size, 4), np.float32)
    for k in range(taps):
        a = (k / (taps - 1) - 0.5) * ls / rs
        c, s = np.cos(a), np.sin(a)
        sx = np.clip(cx + dxs * c - dys * s, 0, w - 1.001); sy = np.clip(cy + dxs * s + dys * c, 0, h - 1.001)
        ix = sx.astype(np.int64); iy = sy.astype(np.int64)
        fx = (sx - ix)[:, None]; fy = (sy - iy)[:, None]
        i0 = iy * w + ix
        num += (Pm[i0] * (1 - fx) + Pm[i0 + 1] * fx) * (1 - fy) + (Pm[i0 + w] * (1 - fx) + Pm[i0 + w + 1] * fx) * fy
    out = lin.copy().reshape(-1, 3)
    good = num[:, 3] > 0.05 * taps * 0.2
    moved = num[good, :3] / num[good, 3:4]
    keep = M.ravel()[ii][good][:, None]
    target = ii[good]
    out[target] = out[target] * (1 - keep) + moved * keep
    return out.reshape(h, w, 3)


def background_swirl(y, cb, cr, half, M, veto, L, debug):
    """Daylight and any frame without dots: a Helios swirls the blurred background itself. Only where
    there is positive evidence of defocus, and not at all when too little of the frame is out of focus."""
    H, W = y.shape
    h, w, _ = half.shape
    cx, cy = (w - 1) / 2, (h - 1) / 2
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    rn = np.hypot(xx - cx, yy - cy) / float(np.hypot(cx, cy))
    tt = smoothstep(L['f0'], 1.0, rn) ** L['p']
    amount = M * smoothstep(0.02, 0.2, tt)
    share = float((M > 0.5).mean())
    info = dict(discs=np.zeros((0, 4), np.float32), sources=0, mask=M, veto=veto, half=half, near=M, soft_share=share)
    if share < 0.08:                                    # nothing convincing to swirl: leave the picture alone
        out = np.clip(np.concatenate([planes_to_rgb(y, cb, cr, r0, min(H, r0 + STRIP)) for r0 in range(0, H, STRIP)], 0) + 0.5, 0, 255).astype(np.uint8)
        return out, info
    lin = to_lin(half)
    moved = arc_blur(lin, amount, L['bg'] * w * tt, cx, cy, taps=31)
    delta = to_gam(np.clip(moved, 0, 1)) - to_gam(lin)
    out = np.empty((H, W, 3), np.uint8)
    for r0 in range(0, H, STRIP):
        r1 = min(H, r0 + STRIP)
        full = planes_to_rgb(y, cb, cr, r0, r1)
        out[r0:r1] = q8(full + bil_rows(delta.astype(np.float32), r0, r1, H, W), r0)
    return out, info


def swirl(y, cb, cr, L, debug=False):
    H, W = y.shape
    half = rgb_small(y, cb, cr, W // 2)
    h, w, _ = half.shape
    edges = {}
    discs = find_discs(half, edges)                     # crops keep the sensor's scale, so radii are absolute
    soft, sharp, near = evidence(half, discs, edges)
    M, veto = defocus_mask(soft, sharp, near, w)
    if not len(discs):
        return background_swirl(y, cb, cr, half, M, veto, L, debug)
    if len(discs):
        # rejected discs must leave every map, or they get erased and never redrawn (black holes)
        discs = discs[np.array([veto[int(b), int(a)] < 0.6 for a, b, _, _ in discs])]
        soft, sharp, near = evidence(half, discs, edges)
        near = grow_field(near, sharp, half, float(np.median(discs[:, 2])) if len(discs) else 0.006 * w)
        soft, sharp = soft * (1 - near), sharp * (1 - near)
        M, veto = defocus_mask(soft, sharp, near, w)
    lin = to_lin(half)
    cx, cy = (w - 1) / 2, (h - 1) / 2
    rmax = float(np.hypot(cx, cy))
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    rn = np.hypot(xx - cx, yy - cy) / rmax
    tt = smoothstep(L['f0'], 1.0, rn) ** L['p']
    # a disc's own colour above its surroundings; dots on protected, in-focus ground are dropped
    new = lin
    ref = float(np.median(discs[:, 2])) if len(discs) else 0.006 * w
    yl = blur(luma(half), 1, 1)
    # a light is brighter than its surroundings, so a bright daytime wall or sky does not count
    bright = smoothstep(45, 80, yl) * smoothstep(10, 30, yl - blur(yl, 4 * ref, 2))
    nsrc = 0
    if len(discs):
        # wide lights (flowers, signs) keep their structure and only curve; dots are what gets redrawn
        wide = chunks(bright, near, discs, ref)
        discs = discs[wide[discs[:, 1].astype(int), discs[:, 0].astype(int)] < 0.5]
        wide = chunks(bright, near, discs, ref)              # again, without the discs found on those shapes
        bright = bright * (1 - wide)
    if len(discs):
        base = base_layer(lin, near, bright, ref, w)
    else:
        base = lin
    moved = arc_blur(base, M * smoothstep(0.02, 0.2, tt), L['arc'] * ref * tt * 2, cx, cy)
    if len(discs):
        S = np.zeros((h, w, 3), np.float32); X = np.zeros((h, w, 3), np.float32)
        soft_lin = blur(lin, 2, 1)
        ring = np.linspace(0, 2 * np.pi, 8, endpoint=False)
        for x, yc, r, _ in discs:
            x0, x1 = max(0, int(x - .6 * r)), min(w, int(x + .6 * r) + 1)
            y0, y1 = max(0, int(yc - .6 * r)), min(h, int(yc + .6 * r) + 1)
            centre = np.median(lin[y0:y1, x0:x1].reshape(-1, 3), 0)
            # a clipped core has lost its colour; the disc's outer part still has it
            rx = np.clip((x + 0.8 * r * np.cos(ring)).astype(int), 0, w - 1); ry = np.clip((yc + 0.8 * r * np.sin(ring)).astype(int), 0, h - 1)
            tint = soft_lin[ry, rx].mean(0)
            colour = np.maximum(0.55 * centre + 0.45 * tint - base[int(yc), int(x)], 0)
            draw_cats_eye(S, X, float(x), float(yc), r * L['size'], colour.astype(np.float32), L, cx, cy, rmax)
        # dots the detector missed, garlands and flowers: redrawn from where their light came from
        extra = sources(bright, near, discs, ref, soft_lin.sum(-1))
        nsrc = len(extra)
        for x, yc in extra:
            ix, iy = min(w - 1, int(x)), min(h - 1, int(yc))
            colour = np.maximum(soft_lin[iy, ix] - base[iy, ix], 0).astype(np.float32)
            draw_cats_eye(S, X, x, yc, ref * L['size'], colour, L, cx, cy, rmax)
        spots = 0.5 * X + 0.5 * S                            # overlapping discs add up, but stay readable
        new = moved + spots / (1 + np.maximum(spots - 0.55, 0))
    else:
        new = moved
    delta = to_gam(np.clip(new, 0, 1)) - to_gam(lin)
    out = np.empty((H, W, 3), np.uint8)
    for r0 in range(0, H, STRIP):
        r1 = min(H, r0 + STRIP)
        full = planes_to_rgb(y, cb, cr, r0, r1)
        out[r0:r1] = q8(full + bil_rows(delta.astype(np.float32), r0, r1, H, W), r0)
    if debug:
        return out, dict(discs=discs, mask=M, veto=veto, half=half, near=near, sources=nsrc)
    return out, dict(discs=discs, sources=nsrc)


def overlay(info):
    """Detected discs on the half-resolution picture, the defocus mask in the green channel."""
    img = np.clip(info['half'], 0, 255).astype(np.float32)
    img = img * 0.55
    img[..., 1] += info['mask'] * 120
    img[..., 0] += info['veto'] * 90
    canvas = np.clip(img, 0, 255).astype(np.uint8)
    t = np.linspace(0, 2 * np.pi, 40)
    for x, y, r, _ in info['discs']:
        a = np.clip((x + r * np.cos(t)).astype(int), 0, canvas.shape[1] - 1)
        b = np.clip((y + r * np.sin(t)).astype(int), 0, canvas.shape[0] - 1)
        canvas[b, a] = (255, 255, 0)
    return canvas


if __name__ == '__main__':
    path, lens, out_path = sys.argv[1:4]
    y, cb, cr = load_422(path)
    img, info = swirl(y, cb, cr, LENSES[lens], debug=True)
    Image.fromarray(img).save(out_path, quality=95)
    Image.fromarray(overlay(info)).save(out_path.rsplit('.', 1)[0] + '-debug.png')
    print(os.path.basename(path), lens, 'discs', len(info['discs']), 'recovered sources', info['sources'],
          'median radius', round(float(np.median(info['discs'][:, 2])), 1) if len(info['discs']) else None)
