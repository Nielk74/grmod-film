"""Film sharpness (MTF) + grain at 100 %: today's rendering against a film-like one.

    python mtf_v3.py COMPARE_DIR

today:    camera Standard JPEG (its own sharpening) -> film colour -> current GR Mod grain.
proposed: camera Standard JPEG -> film colour -> film MTF -> proposed grain (grain_v3.py).
Film MTF: film resolves less fine detail than a sharpened digital file but has development
adjacency (edge) effects that add contrast at mid scale. Here: a gentle low-pass in linear light
(sigma 0.8 px: lens + emulsion, and it takes the edge off the camera's own sharpening), then a
mid-scale unsharp mask on luma (sigma 3 px, +25 %: the adjacency effect). Grain is added after, so it
stays crisp as on film. On the camera this maps onto the films' sharpness and clarity defaults
(native controls; their exact response is not modelled here).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).parent))
import grain_v3 as g  # noqa: E402


def film_mtf(rgb, soften=0.8, edge_sigma=3.0, edge=0.25):
    lin = g.lin(rgb)
    lin = np.stack([ndimage.gaussian_filter(lin[..., c], soften) for c in range(3)], -1)
    out = g.enc(lin)
    y, cb, cr = g.to_ycc(out)
    y = y + edge * (y - ndimage.gaussian_filter(y, edge_sigma))
    return g.from_ycc(y, cb, cr)


def main():
    d = Path(sys.argv[1])
    out = d / "story"
    import json
    data = json.loads((d / "data.js").read_text(encoding="utf-8").split("=", 1)[1].rstrip().rstrip(";"))
    n = data["grid"]
    from compare_page_v3 import apply_grid

    def grid(film, variant):
        m = next(x for x in data["models"] if x["film"] == film and x["variant"] == variant)
        return np.frombuffer((d / "models" / f"{m['file']}-native.f32").read_bytes(), dtype="<f4").reshape(n, n, n, 3)

    radius = {0: 0.55, 1: 1.3}
    samples = []
    for pid in ["Ricoh-R0000027", "Ricoh-R0000030", "Ricoh-AK000164", "Ricoh2-AK000008", "Ricoh-R0000013", "Ricoh2-AK000016"]:
        im = np.asarray(Image.open(d / "photos" / f"{pid}.jpg"), dtype=np.float64) / 255
        h, w = im.shape[:2]
        samples.append(im[(h - 512) // 2:(h + 512) // 2, (w - 512) // 2:(w + 512) // 2])
    tables = {s: g.fit_table(r, samples)[0] for s, r in radius.items()}
    tiles = {s: g.make_tile(r) for s, r in radius.items()}
    # (photo, crop centre, film, variant, grain amount/size): crops shown at 200 %
    cases = [
        ("R0000030", (0.45, 0.42), "Portra 400", "film", (1, 0)),
        ("R0000023", (0.50, 0.30), "Portra 400", "datasheet", (1, 0)),
        ("AK000164", (0.40, 0.40), "CineStill 800T", "film", (2, 1)),
    ]
    for photo, (fx, fy), film, variant, (amount, size) in cases:
        src = ImageOps.exif_transpose(Image.open(rf"C:\Users\Antoine\Pictures\Ricoh\{photo}.JPG")).convert("RGB")
        W, H = src.size
        cw = 420
        x0 = int(np.clip(fx * W - cw / 2, 0, W - cw)); y0 = int(np.clip(fy * H - cw / 2, 0, H - cw))
        crop = np.asarray(src.crop((x0, y0, x0 + cw, y0 + cw)), dtype=np.float64) / 255
        base = apply_grid(crop, grid(film, variant))
        today = g.current_grain(base, amount, size, x0=x0, y0=y0)
        rms = g.to_ycc(g.current_grain(np.full((256, 256, 3), 0.5), amount, size))[0].std()
        prop = g.proposed_grain(film_mtf(base), tiles[size], tables[size], rms)
        for tag, img in [("today", today), ("film", prop)]:
            im = Image.fromarray((np.clip(img, 0, 1) * 255 + .5).astype(np.uint8))
            im.resize((cw * 2, cw * 2), Image.NEAREST).save(out / f"full100-{photo}-{tag}.png")
        print(photo, film, variant, "saved", flush=True)


if __name__ == "__main__":
    main()
