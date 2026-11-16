import sys, os, time, glob
sys.path.insert(0, os.path.dirname(__file__))
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from common import *
from engine import *
import films

SCENES = {
    'cinestill': ['AK000164', 'AK000167', 'R0000016', 'R0000030', 'R0000032', 'R0000027'],
    'gold': ['R0000030', 'R0000022', 'R0000004', 'R0000005', 'R0000023'],
    'kodachrome': ['R0000022', 'R0000027', 'R0000030', 'R0000004', 'R0000023'],
}
def path_of(n):
    for d in DIRS:
        p = d + "\\" + n + ".JPG"
        if os.path.exists(p): return p

def panel(rgb8, label, w):
    im = Image.fromarray(rgb8)
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype("arial.ttf", max(18, w // 28))
    d.rectangle([0, 0, w // 2.4, f.size + 10], fill=(0, 0, 0)); d.text((8, 4), label, fill=(255, 255, 255), font=f)
    return im

def make_sheet(key, lut, scenes=None, tag=''):
    film, tf, _ = films.FILMS[key]
    rows = []
    for n in (scenes or SCENES[key]):
        p = path_of(n); assert image_tone(p) == 0x100, n
        probe = Image.open(p); portrait = ImageOps.exif_transpose(probe).height > ImageOps.exif_transpose(probe).width
        w = 600 if portrait else 900
        std = load_rgb8(p, w); std = std[:, :std.shape[1] // 2 * 2]
        cam = camera_today(std, film)
        (Y, Cb, Cr), (Y2, Cb2, Cr2) = process_full(cam, lut)
        camd, eng = from_422(Y, Cb, Cr), from_422(Y2, Cb2, Cr2)
        row = Image.new('RGB', (3 * std.shape[1] + 20, std.shape[0]), (20, 20, 20))
        for i, (a, lab) in enumerate([(std, f'{n}  Standard'), (camd, 'Camera today'), (eng, 'Colour engine')]):
            row.paste(panel(a, lab, std.shape[1]), (i * (std.shape[1] + 10), 0))
        rows.append(row)
    Wd = max(r.width for r in rows)
    sheet = Image.new('RGB', (Wd, sum(r.height for r in rows) + 10 * len(rows)), (20, 20, 20))
    y = 0
    for r in rows: sheet.paste(r, (0, y)); y += r.height + 10
    return sheet

if __name__ == '__main__':
    key = sys.argv[1]; film, tf, ne = films.FILMS[key]
    t = time.time(); lut = build_lut(tf, ne); print('lut', time.time() - t)
    sh = make_sheet(key, lut); sh.save(os.path.join(OUT, f"sheet-{key}.png")); print(sh.size, time.time() - t)
    # also a half-size version for viewing
    sh.resize((sh.width // 2, sh.height // 2), Image.LANCZOS).save(os.path.join(OUT, f"view-{key}.jpg"), quality=88)
    H = sh.height; n = 3; step = -(-H // n)
    for i in range(n):
        sh.crop((0, i * step, sh.width, min(H, (i + 1) * step))).save(os.path.join(OUT, f"view-{key}-{i}.jpg"), quality=90)
