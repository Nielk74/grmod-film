"""Skin anchoring for film targets: undo most of a film's hue rotation on skin tones, keep the rest.

    python skin_anchor_v3.py IN.cube OUT.cube [keep]

The datasheet films (film_datasheet_v3.py) turn skin 10-17 degrees towards magenta: the simplified
model has no masking couplers, uses a smooth sRGB basis for spectra, and the film's red layer peaks
where skin reflectance rises. Film makers and digital simulations protect skin as a memory colour; this
does the same on the target: inside a smooth window of skin hues (OkLab hue 25..85 deg, chroma 0.02..0.16,
lightness 0.35..0.92), the film's hue change relative to its input (camera Standard) is scaled down to
`keep` (default 0.25). Lightness, chroma and every other colour stay as the film's data gives them.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np


def lin(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def enc(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * x ** (1 / 2.4) - 0.055)


M1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929], [0.2119034982, 0.6806995451, 0.1073969566], [0.0883024619, 0.2817188376, 0.6299787005]])
M2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468], [1.9779984951, -2.4285922050, 0.4505937099], [0.0259040371, 0.7827717662, -0.8086757660]])


def oklab(rgb):
    return np.cbrt(lin(rgb) @ M1.T) @ M2.T


def from_oklab(lab):
    lms = (lab @ np.linalg.inv(M2).T) ** 3
    return enc(lms @ np.linalg.inv(M1).T)


def smooth(lo, hi, x):
    t = np.clip((x - lo) / (hi - lo), 0, 1)
    return t * t * (3 - 2 * t)


def read_cube(path):
    rows, n, header = [], None, []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        s = line.split()
        if not s:
            continue
        if s[0] == "LUT_3D_SIZE":
            n = int(s[1])
        if s[0][0].isdigit() or s[0][0] in "-.":
            rows.append([float(v) for v in s])
        else:
            header.append(line)
    return n, np.array(rows).reshape(n, n, n, 3).transpose(2, 1, 0, 3), header  # [r,g,b]


def anchor(lut, keep=0.25):
    n = lut.shape[0]
    axis = np.linspace(0, 1, n)
    src = np.stack(np.meshgrid(axis, axis, axis, indexing="ij"), -1)
    a, b = oklab(src), oklab(lut)
    ha, hb = np.arctan2(a[..., 2], a[..., 1]), np.arctan2(b[..., 2], b[..., 1])
    ca, cb = np.hypot(a[..., 1], a[..., 2]), np.hypot(b[..., 1], b[..., 2])
    deg = np.degrees(ha) % 360
    w = (smooth(15, 35, deg) * (1 - smooth(75, 95, deg)) * smooth(0.015, 0.03, ca) * (1 - smooth(0.14, 0.2, ca))
         * smooth(0.3, 0.4, a[..., 0]) * (1 - smooth(0.9, 0.97, a[..., 0])))
    dh = (hb - ha + np.pi) % (2 * np.pi) - np.pi
    h = ha + dh * (1 - w * (1 - keep))
    out = np.stack([b[..., 0], cb * np.cos(h), cb * np.sin(h)], -1)
    return np.clip(from_oklab(out), 0, 1)


def main():
    src, dst = sys.argv[1], sys.argv[2]
    keep = float(sys.argv[3]) if len(sys.argv) > 3 else 0.25
    n, lut, header = read_cube(src)
    out = anchor(lut, keep)
    lines = [h if not h.startswith("TITLE") else h[:-1] + f' (skin anchored {keep})"' for h in header]
    for bb in range(n):
        for g in range(n):
            for r in range(n):
                lines.append("%.6f %.6f %.6f" % tuple(out[r, g, bb]))
    Path(dst).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote", dst)


if __name__ == "__main__":
    main()
