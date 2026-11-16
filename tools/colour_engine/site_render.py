"""Full-size renders of every colour-engine comparison, for the local viewer in scratch/colour-engine/site."""
import json
import multiprocessing as mp
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image

import common
from common import OUT, camera_today, load_rgb8
from engine import from_422, lut_apply_422, to_422
from gap_report import CUBES, apply_cube, read_cube
from sheets import path_of

SITE = os.path.join(OUT, 'site')
FILMS = [
    dict(id='cinestill', name='CineStill 800T', film='CineStill 800T',
         scenes=['R0000016', 'AK000164', 'R0000030', 'R0000032', 'R0000027', 'R0000005'],
         versions=[('standard', 'Standard', 'std'), ('today', 'Camera today', None),
                   ('first', 'First engine', 'lut-cinestill.npy'), ('refined', 'Refined', 'lut-cinestill-v2.npy')],
         a='today', b='refined'),
    dict(id='kodachrome', name='Kodachrome 64', film='Kodachrome 64',
         scenes=['R0000022', 'R0000023', 'R0000027', 'R0000030', 'R0000004', 'R0000005'],
         versions=[('standard', 'Standard', 'std'), ('today', 'Camera today', None),
                   ('first', 'First engine', 'lut-kodachrome.npy'), ('refined', 'Refined', 'lut-kodachrome-v2.npy')],
         a='today', b='refined'),
    dict(id='portra', name='Portra 400 options', film='Portra 400',
         scenes=['R0000022', 'R0000023', 'R0000027', 'R0000020', 'R0000018', 'R0000030', 'R0000005', 'AK000164', 'R0000032', 'R0000004'],
         versions=[('standard', 'Standard', 'std'), ('today', 'Camera today', None), ('rich', 'Rich Portra', 'lut-portra-rich.npy'),
                   ('richwarm', 'Rich Portra warm', 'lut-portra-richwarm.npy'), ('ektar', 'Portra x Ektar', 'lut-portra-ektar.npy'),
                   ('plus2', 'Overexposed +2', 'lut-portra-plus2.npy'),
                   ('frontier', 'Frontier scan', 'lut-portra-frontier.npy'), ('pushed', 'Pushed +1', 'lut-portra-pushed.npy'),
                   ('noritsu', 'Noritsu scan', 'lut-portra-noritsu.npy')],
         a='today', b='rich'),
    # Films that might use the colour engine: what the camera does today against the full authored look (the ceiling of a LUT).
    *[dict(id=i, name=n, film=n,
           scenes=['R0000022', 'R0000023', 'R0000027', 'R0000016', 'R0000030', 'R0000005', 'R0000020'],
           versions=[('standard', 'Standard', 'std'), ('today', 'Camera today', None), ('lut', 'Camera build (LUT)', t), ('full', 'Full look (LUT ceiling)', 'cube:' + c)],
           a='today', b='lut')
      for i, n, c, t in (('classicneg', 'Classic Neg', '04-Classic-Neg.cube', 'lut-classic-neg-full.npy'),
                         ('classicchrome', 'Classic Chrome', '03-Classic-Chrome.cube', 'lut-classic-chrome-full.npy'),
                         ('blockbuster', 'Blockbuster', '19-Blockbuster.cube', 'lut-blockbuster-full.npy'))],
]


def save(rgb, folder, key):
    img = Image.fromarray(rgb)
    img.save(os.path.join(folder, key + '.jpg'), quality=93, subsampling=1)
    long_side = max(img.size)
    scale = 1600 / long_side
    img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS).save(os.path.join(folder, key + '-p.jpg'), quality=88)


def render(job):
    film, scene = job
    if film['id'] in ('classicneg', 'classicchrome', 'blockbuster'):
        common._coef = json.load(open(os.path.join(OUT, 'coef-all.json'), encoding='utf8'))
    std = load_rgb8(path_of(scene))
    std = std[:, :std.shape[1] // 2 * 2]
    cam = np.concatenate([camera_today(std[r:r + 500], film['film']) for r in range(0, std.shape[0], 500)], 0)
    Y, Cb, Cr = to_422(cam)
    folder = os.path.join(SITE, 'img', film['id'], scene)
    os.makedirs(folder, exist_ok=True)
    for key, _, spec in film['versions']:
        if spec == 'std':
            out = std
        elif spec is None:
            out = from_422(Y, Cb, Cr)
        elif spec.startswith('cube:'):
            cube = read_cube(os.path.join(CUBES, spec[5:]))
            out = np.concatenate([apply_cube(std[r:r + 400], cube) for r in range(0, std.shape[0], 400)], 0)
        else:
            out = from_422(*lut_apply_422(Y, Cb, Cr, np.load(os.path.join(OUT, spec))))
        save(out, folder, key)
    print('done', film['id'], scene, flush=True)
    return film['id'], scene, int(std.shape[1]), int(std.shape[0])


if __name__ == '__main__':
    only = sys.argv[1:]                                  # film ids to re-render; none means all of them
    chosen = [f for f in FILMS if not only or f['id'] in only]
    jobs = [(f, s) for f in chosen for s in f['scenes']]
    with mp.Pool(5) as pool:
        sizes = pool.map(render, jobs, chunksize=1)
    dims = {(a, b): (c, d) for a, b, c, d in sizes}
    fresh = {f['id']: dict(id=f['id'], name=f['name'], a=f['a'], b=f['b'],
                           versions=[dict(key=k, label=l) for k, l, _ in f['versions']],
                           scenes=[dict(id=s, width=dims[(f['id'], s)][0], height=dims[(f['id'], s)][1]) for s in f['scenes']])
             for f in chosen}
    path = os.path.join(SITE, 'manifest.json')
    previous = json.load(open(path, encoding='utf-8')) if only and os.path.exists(path) else []
    known = {e['id'] for e in previous}
    manifest = [fresh.get(e['id'], e) for e in previous] + [f for k, f in fresh.items() if k not in known]
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(manifest, fh, indent=1)
    print('manifest written', flush=True)
