import sys, os, json, numpy as np
from PIL import Image, ImageDraw, ImageFont
from common import *
from engine import *
import films, films2
from sheets import path_of

PORTRA_SCENES = ['R0000030', 'R0000032', 'R0000005', 'AK000164', 'R0000004', 'R0000027', 'R0000023']


def luts():
    return {'cinestill_v1': np.load(os.path.join(OUT, 'lut-cinestill.npy')), 'kodachrome_v1': np.load(os.path.join(OUT, 'lut-kodachrome.npy'))}


def label(rgb8, text, w):
    im = Image.fromarray(rgb8); d = ImageDraw.Draw(im); f = ImageFont.truetype("arial.ttf", max(16, w // 26))
    d.rectangle([0, 0, w // 1.8, f.size + 10], fill=(0, 0, 0)); d.text((8, 4), text, fill=(255, 255, 255), font=f)
    return im


def sheet(film, scenes, cols, wp=470, wl=700, name=None):
    """cols: list of (label, None for camera-today | 'std' | lut)"""
    rows = []
    for n in scenes:
        p = path_of(n); assert image_tone(p) == 0x100, n
        im0 = ImageOps.exif_transpose(Image.open(p)); w = wp if im0.height > im0.width else wl
        std = load_rgb8(p, w); std = std[:, :std.shape[1] // 2 * 2]
        cam = camera_today(std, film); Y, Cb, Cr = to_422(cam); pics = []
        for lab, l in cols:
            if isinstance(l, str): a = std
            elif l is None: a = from_422(Y, Cb, Cr)
            else: a = from_422(*lut_apply_422(Y, Cb, Cr, l))
            pics.append(label(a, (n + '  ' if lab == 'Standard' else '') + lab, std.shape[1]))
        row = Image.new('RGB', (len(cols) * (std.shape[1] + 8), std.shape[0]), (20, 20, 20))
        for i, pnl in enumerate(pics): row.paste(pnl, (i * (std.shape[1] + 8), 0))
        rows.append(row)
    Wd = max(r.width for r in rows); sh = Image.new('RGB', (Wd, sum(r.height + 8 for r in rows)), (20, 20, 20)); y = 0
    for r in rows: sh.paste(r, (0, y)); y += r.height + 8
    sh.save(os.path.join(OUT, name + '.png'))
    H = sh.height; n = 3; st = -(-H // n)
    for i in range(n): sh.crop((0, i * st, sh.width, min(H, (i + 1) * st))).save(os.path.join(OUT, f'view-{name}-{i}.jpg'), quality=90)
    return sh


def run(what):
    L1 = luts()
    if what == 'kodachrome':
        lut2 = build_lut(films2.kodachrome2, True); np.save(os.path.join(OUT, 'lut-kodachrome-v2.npy'), lut2)
        sheet('Kodachrome 64', ['R0000022', 'R0000023', 'R0000027', 'R0000030', 'R0000004', 'R0000005'],
              [('Standard', 'std'), ('Camera today', None), ('First engine', L1['kodachrome_v1']), ('Refined', lut2)], name='sheet-kodachrome-v2')
    if what == 'cinestill':
        lut2 = build_lut(films2.cinestill2, False); np.save(os.path.join(OUT, 'lut-cinestill-v2.npy'), lut2)
        sheet('CineStill 800T', ['R0000016', 'AK000164', 'R0000030', 'R0000032', 'R0000027', 'R0000005'],
              [('Standard', 'std'), ('Camera today', None), ('First engine', L1['cinestill_v1']), ('Refined', lut2)], name='sheet-cinestill-v2')
    if what == 'portra':
        ls = {k: build_lut(f, True) for k, f in films2.PORTRA.items()}
        for k, l in ls.items(): np.save(os.path.join(OUT, f'lut-portra-{k}.npy'), l)
        sheet('Portra 400', PORTRA_SCENES,
              [('Camera today', None), ('Luminous skin', ls['luminous']), ('Shade rescue', ls['shade']), ('Golden light', ls['golden'])], name='sheet-portra-options')


if __name__ == '__main__':
    run(sys.argv[1])
