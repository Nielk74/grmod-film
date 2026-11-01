"""Normal-view colour differences, fixed before-image masks, no quality scoring."""
from __future__ import annotations
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter
from colour.models import sRGB_to_XYZ, XYZ_to_Lab
from colour.difference import delta_E_CIE2000

VIEW_LONGSIDE = 900

def normal_view(rgb, longside=VIEW_LONGSIDE):
    a = np.asarray(rgb, dtype=np.float32)
    h, w = a.shape[:2]
    if max(h, w) <= longside:
        return a.copy()
    size = (round(w * longside / max(h, w)), round(h * longside / max(h, w)))
    # Float per-channel resize avoids quantizing away small differences.
    return np.stack([np.asarray(Image.fromarray(a[..., c]).resize(size, Image.Resampling.LANCZOS)) for c in range(3)], axis=-1).clip(0, 1)

def lab(rgb):
    return XYZ_to_Lab(sRGB_to_XYZ(np.asarray(rgb, dtype=np.float64)))

def de00(a, b):
    return delta_E_CIE2000(lab(a), lab(b))

def fixed_masks(before):
    a = np.asarray(before)
    r, g, b = np.moveaxis(a, -1, 0)
    chromatic = (a.max(-1) - a.min(-1)) > .10
    green = chromatic & (g > r * 1.04) & (g > b * 1.05)
    blue = chromatic & (b > r + .04) & (b > g * .98)
    red = chromatic & (r > g + .03) & (r > b + .03)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[-1:1:complex(h), -1:1:complex(w)]
    luma = a @ np.array([.2126, .7152, .0722])
    bright = luma > .60
    surround = gaussian_filter(bright.astype(np.float32), sigma=60*max(h,w)/6000) > .02
    return {'all': np.ones((h, w), dtype=bool), 'colour': green | blue | red,
            'green': green, 'blue': blue, 'red': red,
            'neutrals': (a.max(-1)-a.min(-1)<.08) & (luma>.08),
            'corners': xx ** 2 + yy ** 2 > 1.0,
            'highlights_and_surround': bright | surround, 'shadows': luma < .35}

def summarize(delta, mask):
    values = delta[np.asarray(mask, dtype=bool)]
    result = {'pixels': int(values.size), 'coverage': float(np.mean(mask))}
    if values.size:
        result.update(mean_de00=float(values.mean()), p95_de00=float(np.percentile(values, 95)),
                      fraction_ge3=float(np.mean(values >= 3)))
    else:
        result.update(mean_de00=None, p95_de00=None, fraction_ge3=None)
    return result

def measure(before, after, masks=None):
    a, b = normal_view(before), normal_view(after)
    if a.shape != b.shape:
        raise ValueError('Matched display dimensions required')
    masks = fixed_masks(a) if masks is None else masks
    d = de00(a, b)
    return {'view_longside': max(a.shape[:2]), 'mean_absolute_rgb_255': float(np.mean(np.abs(a-b)) * 255),
            'regions': {name: summarize(d, mask) for name, mask in masks.items()}}
