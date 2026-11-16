# SPDX-License-Identifier: GPL-2.0-only
"""Check a "full look" LUT (tools/colourlut/make_lut.py) on real Standard photos, through the integer path of the camera.

For each film and photo: the Standard photo -> camera today (common.camera_today, the fitted matrix, curves and post matrix) -> YCbCr 4:2:2
(engine.to_422) -> the LUT (engine.lut_apply_422, the algorithm of the camera module) -> RGB, against the target: the film's cube applied
to the Standard photo. Mean OkLab distance x100, overall and in the sky, skin, grey and white areas (masks from the Standard photo, as
gap_report.py); "before" is the same pipeline without the LUT. Banding: neighbour steps in smooth areas and empty histogram bins in the sky,
before and after. Writes scratch/colour-engine/lut-check-<film>.jpg: Standard | camera today | with the LUT | target, for two photos.

    python tools/colourlut/check_lut.py [--no-banding] ["Classic Neg" ...]
"""
import json
import sys

import numpy as np
from PIL import Image, ImageDraw

import make_lut as m
from make_lut import SCRATCH, SLUG, common, engine

SCENES = ['R0000022', 'R0000023', 'R0000027', 'R0000030', 'R0000016']
BAND_SCENES = ['R0000023', 'R0000016']
WIDTH = 1200


def path_of(name):
    for d in common.DIRS:
        p = d + '\\' + name + '.JPG'
        if __import__('os').path.exists(p):
            return p
    sys.exit(f'{name}.JPG not found')


def ok(rgb8):
    return common.srgb_to_oklab(rgb8 / 255.0)


def run_lut(cam, lut):
    Y, Cb, Cr = engine.to_422(cam)
    before = engine.from_422(Y, Cb, Cr)
    after = engine.from_422(*engine.lut_apply_422(Y, Cb, Cr, lut))
    return before, after


def masks(std):
    lab = ok(std)
    L, C = lab[..., 0], np.hypot(lab[..., 1], lab[..., 2])
    h = np.degrees(np.arctan2(lab[..., 2], lab[..., 1])) % 360
    return dict(sky=(h > 225) & (h < 280) & (C > 0.035) & (L > 0.45),
                skin=(h > 30) & (h < 80) & (C > 0.02) & (C < 0.12) & (L > 0.35) & (L < 0.85),
                greys=(C < 0.02) & (L > 0.15) & (L < 0.86), whites=(L > 0.86) & (C < 0.03))


def steps(a, b):
    """Neighbour steps of b where a is smooth (every channel differs by <= 1 from its neighbour), horizontal and vertical."""
    d, c = [], []
    for ax in (1, 0):
        da = np.abs(np.diff(a.astype(np.int16), axis=ax)).max(-1)
        db = np.abs(np.diff(b.astype(np.int16), axis=ax)).max(-1)
        d.append(db[da <= 1])
        c.append(da[da <= 1])
    d, c = np.concatenate(d), np.concatenate(c)
    return dict(smooth_px=int(d.size), max=int(d.max()), frac_ge2=float((d >= 2).mean()), frac_ge3=float((d >= 3).mean()))


def gaps(rgb, mask):
    """Empty bins of the 8-bit histogram of each RGB channel between its 1st and 99th percentile, over the masked pixels."""
    n = 0
    tot = 0
    for ch in range(3):
        v = rgb[..., ch][mask]
        lo, hi = np.percentile(v, [1, 99]).astype(int)
        hist = np.bincount(v, minlength=256)[lo:hi + 1]
        n += int((hist == 0).sum())
        tot += int(hi - lo + 1)
    return n, tot


def label(img, text):
    im = Image.fromarray(img)
    ImageDraw.Draw(im).text((8, 6), text, fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
    return np.asarray(im)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    banding = '--no-banding' not in sys.argv
    coef = m.load_coef()
    results = {}
    for film in args or list(SLUG):
        lut = np.load(SCRATCH / f'lut-{SLUG[film]}-full.npy')
        cube = m.read_cube(m.CUBES / coef[film]['cube']).astype(np.float32)
        acc = {k: ([], []) for k in ('all', 'sky', 'skin', 'greys', 'whites')}
        sheet = []
        for name in SCENES:
            std = common.load_rgb8(path_of(name), WIDTH)
            std = std[:, :std.shape[1] // 2 * 2]
            cam = common.camera_today(std, film)
            target = np.clip(np.round(m.apply_cube_float(std.astype(np.float64), cube.astype(np.float64))), 0, 255).astype(np.uint8)
            before, after = run_lut(cam, lut)
            tl = ok(target)
            db = np.linalg.norm(ok(before) - tl, axis=-1) * 100
            da = np.linalg.norm(ok(after) - tl, axis=-1) * 100
            mk = masks(std)
            acc['all'][0].append(db.mean()); acc['all'][1].append(da.mean())
            for k, v in mk.items():
                if v.sum() > 2000:
                    acc[k][0].append(db[v].mean()); acc[k][1].append(da[v].mean())
            if name in ('R0000023', 'R0000016'):
                sc = 450 / std.shape[1]
                row = [Image.fromarray(x).resize((450, round(std.shape[0] * sc)), Image.LANCZOS) for x in (std, before, after, target)]
                sheet.append(np.concatenate([label(np.asarray(x), t) for x, t in zip(row, ('Standard', 'camera today', 'with LUT', 'target'))], 1))
        out = {k: (round(float(np.mean(b)), 2), round(float(np.mean(a)), 2)) for k, (b, a) in acc.items() if b}
        res = dict(gap_before_after=out)
        if banding:
            bs, gs = [], []
            for name in BAND_SCENES:
                std = common.load_rgb8(path_of(name))
                std = std[:, :std.shape[1] // 2 * 2]
                cam = np.concatenate([common.camera_today(std[r:r + 500], film) for r in range(0, std.shape[0], 500)], 0)
                Y, Cb, Cr = engine.to_422(cam)
                bef = engine.from_422(Y, Cb, Cr)
                aft = engine.from_422(*engine.lut_apply_422(Y, Cb, Cr, lut))
                sky = masks(std[::4, ::4])['sky']
                s = steps(cam, bef); s2 = steps(cam, aft)
                g0 = gaps(bef[::4, ::4], sky) if sky.sum() > 2000 else None
                g1 = gaps(aft[::4, ::4], sky) if sky.sum() > 2000 else None
                bs.append(dict(scene=name, steps_without_lut=s, steps_with_lut=s2, sky_hist_gaps_without=g0, sky_hist_gaps_with=g1))
            res['banding'] = bs
        results[film] = res
        Image.fromarray(np.concatenate(sheet, 0)).save(SCRATCH / f'lut-check-{SLUG[film]}.jpg', quality=90)
        print(film, json.dumps(res), flush=True)
    json.dump(results, open(SCRATCH / 'lut-check-full.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
