"""Development depletion ("adjacency effect"), the idea behind Filmulator, as a camera-feasible step.

    python develop_v3.py COMPARE_DIR

In a developing film, bright regions use up the developer around them: large bright areas end up
less dense than their exposure says (a highlight shoulder that depends on the area), small bright
spots stay bright and darken their surroundings a little (local contrast, edge effects). Filmulator
(Carlo Vaccari, GPL-3.0) simulates crystal growth and developer diffusion step by step; this is not its
code but the closed-form adjacency approximation of it, which a JPEG-stage module can afford (a
low-resolution blurred light map, as the halation module already builds):

    out = E * (1 + a*m) / (1 + a*blur(E))      in linear light, m = mid grey (unchanged)

`a` ("drama") sets the depletion, the blur radius (a fraction of the width) the developer's reach.
Applied to luma in linear light; colour follows the luma ratio. Rendered on top of the film rendering.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).parent))
from compare_page_v3 import apply_grid  # noqa: E402


def lin(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def enc(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * x ** (1 / 2.4) - 0.055)


def develop(rgb, drama=0.6, reach=0.03, mid=0.18):
    y = rgb @ np.array([0.2126, 0.7152, 0.0722])
    e = lin(y)
    h, w = e.shape
    # the developer's reach at low resolution (as the halation module's map), three box passes
    s = max(1, round(w / 512))
    small = e[: h - h % s, : w - w % s].reshape(h // s, s, w // s, s).mean((1, 3))
    r = max(1, round(reach * w / s / 2))
    for _ in range(3):
        small = ndimage.uniform_filter(small, 2 * r + 1, mode="nearest")
    blur = ndimage.zoom(small, (h / small.shape[0], w / small.shape[1]), order=1)[:h, :w]
    if blur.shape != e.shape:
        blur = np.pad(blur, ((0, h - blur.shape[0]), (0, w - blur.shape[1])), mode="edge")
    e2 = e * (1 + drama * mid) / (1 + drama * blur)
    ratio = (enc(e2) + 1e-4) / (y + 1e-4)
    return np.clip(rgb * ratio[..., None], 0, 1)


def main():
    d = Path(sys.argv[1])
    data = json.loads((d / "data.js").read_text(encoding="utf-8").split("=", 1)[1].rstrip().rstrip(";"))
    n = data["grid"]
    m = next(x for x in data["models"] if x["film"] == "Portra 400" and x["variant"] == "film")
    grid = np.frombuffer((d / "models" / f"{m['file']}-native.f32").read_bytes(), dtype="<f4").reshape(n, n, n, 3)
    out = d / "story"
    for pid in ["Ricoh-R0000027", "Ricoh-R0000030", "Ricoh-R0000022", "Ricoh2-AK000025", "Ricoh-R0000018", "Ricoh2-AK000003"]:
        im = np.asarray(Image.open(d / "photos" / f"{pid}.jpg"), dtype=np.float64) / 255
        base = apply_grid(im, grid).astype(np.float64)
        rows = [base] + [develop(base, a, 0.03) for a in (0.6, 1.5)] + [develop(base, 1.5, 0.008)]
        for tag, img in zip(["none", "a06", "a15", "a15-small"], rows):
            Image.fromarray((np.clip(img, 0, 1) * 255 + .5).astype(np.uint8)).save(out / f"develop-{pid}-{tag}.jpg", quality=92)
        print(pid, "saved", flush=True)


if __name__ == "__main__":
    main()
