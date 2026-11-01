"""Do the film variants treat skin well? Skin-tone shifts per film and variant on the user's photos.

    python skin_v3.py COMPARE_DIR

Skin pixels: a conservative colour gate on the Standard photos (CIELAB hue 25..65 deg, chroma 10..45,
L* 25..85; the classic JPEG YCbCr skin box as a second gate), photos with at least 1 % skin. For every
model (camera-quantized grid): skin's mean hue shift (deg), chroma ratio and lightness shift, against
the same measures over the whole picture. Skin that turns magenta (hue down) or green/yellow (hue up), or
that saturates or greys much more than the rest of the picture, is what portrait photographers notice first.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import colour
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from compare_page_v3 import apply_grid  # noqa: E402


def lab(rgb):
    return colour.XYZ_to_Lab(colour.sRGB_to_XYZ(np.clip(rgb, 0, 1)))


def main():
    d = Path(sys.argv[1])
    data = json.loads((d / "data.js").read_text(encoding="utf-8").split("=", 1)[1].rstrip().rstrip(";"))
    n = data["grid"]
    skins = []
    for p in data["photos"]:
        im = Image.open(d / "photos" / f"{p['id']}.jpg"); im.thumbnail((400, 400))
        rgb = np.asarray(im, dtype=np.float64) / 255
        L = lab(rgb); C = np.hypot(L[..., 1], L[..., 2]); h = np.degrees(np.arctan2(L[..., 2], L[..., 1])) % 360
        r, g, b = rgb[..., 0] * 255, rgb[..., 1] * 255, rgb[..., 2] * 255
        cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b; cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b
        m = (h > 25) & (h < 65) & (C > 10) & (C < 45) & (L[..., 0] > 25) & (L[..., 0] < 85) & (cb > 77) & (cb < 127) & (cr > 133) & (cr < 173)
        if m.mean() >= 0.01:
            skins.append((p["id"], rgb, m))
    print(len(skins), "photos with skin")
    rows = []
    for mdl in data["models"]:
        grid = np.frombuffer((d / "models" / f"{mdl['file']}-native.f32").read_bytes(), dtype="<f4").reshape(n, n, n, 3)
        dh, cr_, dl, dh_all, cr_all = [], [], [], [], []
        for pid, rgb, m in skins:
            a, b = lab(rgb), lab(apply_grid(rgb, grid))
            ha = np.degrees(np.arctan2(a[..., 2], a[..., 1])); hb = np.degrees(np.arctan2(b[..., 2], b[..., 1]))
            dhue = (hb - ha + 180) % 360 - 180
            ca, cb_ = np.hypot(a[..., 1], a[..., 2]), np.hypot(b[..., 1], b[..., 2])
            dh.append(float(np.mean(dhue[m]))); cr_.append(float(cb_[m].mean() / ca[m].mean())); dl.append(float(np.mean(b[..., 0][m] - a[..., 0][m])))
            col = ca > 10
            dh_all.append(float(np.mean(dhue[col]))); cr_all.append(float(cb_[col].mean() / ca[col].mean()))
        rows.append({"film": mdl["film"], "variant": mdl["variant"], "skinHueShift": round(np.median(dh), 1),
                     "skinChroma": round(np.median(cr_), 2), "skinL": round(np.median(dl), 1),
                     "pictureHueShift": round(np.median(dh_all), 1), "pictureChroma": round(np.median(cr_all), 2)})
    rows.sort(key=lambda r: -abs(r["skinHueShift"]))
    for r in rows:
        flag = []
        if r["skinHueShift"] < -5: flag.append("towards magenta")
        if r["skinHueShift"] > 5: flag.append("towards yellow")
        if r["skinChroma"] > 1.3: flag.append("over-saturated")
        if r["skinChroma"] < 0.7: flag.append("greyed")
        r["flags"] = flag
        print(f"{r['film']:18s} {r['variant']:13s} skin hue {r['skinHueShift']:+5.1f} chroma x{r['skinChroma']:.2f} L {r['skinL']:+5.1f} | picture hue {r['pictureHueShift']:+5.1f} chroma x{r['pictureChroma']:.2f} {' '.join(flag)}")
    (d / "story" / "skin.json").write_text(json.dumps({"photos": [s[0] for s in skins], "rows": rows}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
