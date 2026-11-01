"""Everything together: today's GR Mod film rendering against the proposed one, at full resolution.

    python combined_v3.py COMPARE_DIR

today:    camera Standard -> film as shipped (camera grid) -> current halation (if the film has it) ->
          current grain (the film's recipe setting).
proposed: camera Standard -> film response (camera grid) -> film MTF -> proposed halation (wider,
          softer, near-clip, red: PROPOSED2) -> proposed grain (tile model; Portra 400 one step up, as Kodak's PGI suggests).
Halation gains: the current design's gain as calibrated on the user's CineStill frame (37), the proposal at
0.78 of it (halation_v3.py). Outputs: the whole picture at 1600 px and a 100 % crop, for both.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).parent))
import grain_v3 as g  # noqa: E402
import halation_v3 as hl  # noqa: E402
from mtf_v3 import film_mtf  # noqa: E402
from compare_page_v3 import apply_grid  # noqa: E402

HAL_GAIN = 37.0

CASES = [
    # photo, film, today's grain (amount, size), proposed grain (amount, size), halation, 100 % crop centre
    ("R0000030", "Portra 400", (1, 0), (2, 0), False, (0.45, 0.42)),
    ("AK000168", "CineStill 800T", (2, 1), (2, 1), True, (0.55, 0.45)),
]


def main():
    d = Path(sys.argv[1])
    out = d / "story"
    data = json.loads((d / "data.js").read_text(encoding="utf-8").split("=", 1)[1].rstrip().rstrip(";"))
    n = data["grid"]

    def grid(film, variant):
        m = next(x for x in data["models"] if x["film"] == film and x["variant"] == variant)
        return np.frombuffer((d / "models" / f"{m['file']}-native.f32").read_bytes(), dtype="<f4").reshape(n, n, n, 3)

    samples = []
    for pid in ["Ricoh-R0000027", "Ricoh-R0000030", "Ricoh-AK000164", "Ricoh2-AK000008", "Ricoh-R0000013", "Ricoh2-AK000016"]:
        im = np.asarray(Image.open(d / "photos" / f"{pid}.jpg"), dtype=np.float64) / 255
        h, w = im.shape[:2]
        samples.append(im[(h - 512) // 2:(h + 512) // 2, (w - 512) // 2:(w + 512) // 2])
    radius = {0: 0.55, 1: 1.3}
    tables = {s: g.fit_table(r, samples)[0] for s, r in radius.items()}
    tiles = {s: g.make_tile(r) for s, r in radius.items()}
    rms = {(a, s): g.to_ycc(g.current_grain(np.full((256, 256, 3), 0.5), a, s))[0].std() for a in (1, 2, 3) for s in (0, 1)}

    for photo, film, (ta, ts), (pa, ps), halation, (cx, cy) in CASES:
        src = np.asarray(ImageOps.exif_transpose(Image.open(rf"C:\Users\Antoine\Pictures\Ricoh\{photo}.JPG")).convert("RGB"), dtype=np.float32) / 255
        H, W = src.shape[:2]
        today = apply_grid(src, grid(film, "current")).astype(np.float64)
        prop = apply_grid(src, grid(film, "film")).astype(np.float64)
        if halation:
            today = hl.halation(today, hl.CURRENT, HAL_GAIN)
        prop = film_mtf(prop)
        if halation:
            prop = hl.halation(prop, hl.PROPOSED2, 0.78 * HAL_GAIN)
        today = g.current_grain(today, ta, ts)
        prop = g.proposed_grain(prop, tiles[ps], tables[ps], rms[(pa, ps)])
        cw = 700
        x0 = int(np.clip(cx * W - cw / 2, 0, W - cw)); y0 = int(np.clip(cy * H - cw / 2, 0, H - cw))
        for tag, img in [("today", today), ("proposed", prop)]:
            im = Image.fromarray((np.clip(img, 0, 1) * 255 + .5).astype(np.uint8))
            whole = im.copy(); whole.thumbnail((1600, 1600), Image.LANCZOS)
            whole.save(out / f"all-{photo}-{tag}.jpg", quality=92)
            im.crop((x0, y0, x0 + cw, y0 + cw)).save(out / f"all-{photo}-{tag}-100.png")
        print(photo, film, "saved", flush=True)


if __name__ == "__main__":
    main()
