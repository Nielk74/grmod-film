"""Banding check for the rich Portra LUTs: histogram gaps in the sky and neighbour steps in smooth areas."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np

from common import OUT, camera_today, load_rgb8
from engine import from_422, lut_apply_422, to_422
from sheets import path_of


def smooth_steps(a, b):
    found = []
    for axis in (0, 1):
        da = np.abs(np.diff(a.astype(np.int16), axis=axis)).max(-1)
        db = np.abs(np.diff(b.astype(np.int16), axis=axis)).max(-1)
        found.append(db[da <= 1])
    d = np.concatenate(found)
    return int(d.max()), float((d >= 3).mean()) * 100, float((d >= 6).mean()) * 100


def gaps(channel):
    """Unused code values inside the used range of a smooth region: a true sign of posterization."""
    values = np.unique(channel)
    return int(values.max() - values.min() + 1 - values.size), int(values.min()), int(values.max())


for scene in ('R0000022', 'R0000023', 'R0000027'):
    std = load_rgb8(path_of(scene))
    std = std[:, :std.shape[1] // 2 * 2]
    cam = np.concatenate([camera_today(std[r:r + 500], 'Portra 400') for r in range(0, std.shape[0], 500)], 0)
    Y, Cb, Cr = to_422(cam)
    today = from_422(Y, Cb, Cr)
    h, w, _ = today.shape
    sky = today[:h // 6, w // 4:3 * w // 4]
    print(scene, 'today sky gaps (unused, min, max) per channel', [gaps(sky[..., c]) for c in range(3)], flush=True)
    for key in ('rich', 'richwarm', 'ektar'):
        out = from_422(*lut_apply_422(Y, Cb, Cr, np.load(os.path.join(OUT, f'lut-portra-{key}.npy'))))
        top, ge3, ge6 = smooth_steps(today, out)
        patch = out[:h // 6, w // 4:3 * w // 4]
        print(f'  {key}: smooth-area max step {top}, >=3: {ge3:.2f}%, >=6: {ge6:.3f}%; sky gaps', [gaps(patch[..., c]) for c in range(3)], flush=True)
