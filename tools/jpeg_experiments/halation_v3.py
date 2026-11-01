"""Halation: the camera's current design (tools/halation/halation.c, 0.8.2 constants) against a proposed
wider, more orange, gentler one, on a frame shot with CineStill 800T + Halation strong.

    python halation_v3.py COMPARE_DIR

The current design is simulated in float (light from max(Y, R) above a start, squared; two spreads of
box radius narrow/wide x width, three box passes each; channels lifted by a "screen"), and its gain is
calibrated so that Standard-from-RAW + CineStill (camera grid) + simulated halation matches the camera
JPEG of the same frame around the highlights. The proposal reuses that calibrated energy.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from scipy import ndimage

CURRENT = {"start": 220, "narrow": 0.0035, "wide": 0.012, "mix": 0.6, "channels": (1.0, 0.06, 0.03)}
PROPOSED = {"start": 200, "narrow": 0.006, "wide": 0.035, "mix": 0.3, "channels": (1.0, 0.38, 0.14)}
# Second proposal (2026-11-01): PROPOSED's early start (200) fogged a large lit doorway at night orange from
# the inside; halation shows as a halo around bright areas, not on them. Start near clipping, keep the wide
# soft spread, and a redder colour (spectral film models: ~3 % red, 0.3 % green, 0.1 % blue).
PROPOSED2 = {"start": 228, "narrow": 0.006, "wide": 0.035, "mix": 0.3, "channels": (1.0, 0.22, 0.08)}


def box3(m: np.ndarray, r: float) -> np.ndarray:
    size = max(1, int(round(2 * r + 1)))
    for _ in range(3):
        m = ndimage.uniform_filter(m, size=size, mode="nearest")
    return m


def lin(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def halation(img: np.ndarray, p: dict, gain: float) -> np.ndarray:
    y = img @ np.array([0.299, 0.587, 0.114])
    v = np.maximum(y, img[..., 0]) * 255
    start = p["start"]
    light = np.clip((lin(v / 255) - lin(start / 255)) / (1 - lin(start / 255)), 0, 1) ** 2
    w = img.shape[1]
    spread = p["mix"] * box3(light, p["narrow"] * w) + (1 - p["mix"]) * box3(light, p["wide"] * w)
    lift = np.clip(spread * gain, 0, 1)[..., None] * np.array(p["channels"])
    return 1 - (1 - img) * (1 - np.clip(lift, 0, 1))


def apply_grid(rgb, grid):
    n = grid.shape[0]
    q = np.clip(rgb, 0, 1) * (n - 1)
    lo = np.minimum(q.astype(int), n - 2); f = q - lo
    out = np.zeros_like(rgb)
    for i in (0, 1):
        for j in (0, 1):
            for k in (0, 1):
                ww = (f[..., 0] if i else 1 - f[..., 0]) * (f[..., 1] if j else 1 - f[..., 1]) * (f[..., 2] if k else 1 - f[..., 2])
                out += grid[lo[..., 0] + i, lo[..., 1] + j, lo[..., 2] + k] * ww[..., None]
    return out


def main() -> None:
    d = Path(sys.argv[1])
    data = json.loads((d / "data.js").read_text(encoding="utf-8").split("=", 1)[1].rstrip().rstrip(";"))
    n = data["grid"]
    m = next(x for x in data["models"] if x["film"] == "CineStill 800T" and x["variant"] == "current")
    grid = np.frombuffer((d / "models" / f"{m['file']}-native.f32").read_bytes(), dtype="<f4").reshape(n, n, n, 3)
    results = {}
    for frame in ["AK000021", "AK000024"]:
        std = np.asarray(Image.open(d / "photos" / f"Ricoh2-{frame}.jpg"), dtype=np.float32) / 255
        film = apply_grid(std, grid)
        cam = ImageOps.exif_transpose(Image.open(rf"C:\Users\Antoine\Pictures\Ricoh2\{frame}.JPG")).convert("RGB")
        cam = np.asarray(cam.resize((std.shape[1], std.shape[0]), Image.LANCZOS), dtype=np.float32) / 255
        # calibrate the current design's gain where the camera added light (red rose clearly above the film)
        zone = ndimage.binary_dilation((cam[..., 0] - film[..., 0]) > 0.08, iterations=6)
        best = min((float(np.mean((halation(film, CURRENT, g)[zone] - cam[zone]) ** 2)), g) for g in np.linspace(1, 40, 79))
        gain = best[1]
        cur = halation(film, CURRENT, gain)
        # The proposal spreads light ~3x wider; at the current design's total light it all but disappears
        # (tried). Its gain is 0.78x the calibrated current gain, chosen by eye on AK000021 between 0.39x
        # (too faint) and 1.36x (fogs the dark clothes).
        lo = 0.78 * gain
        prop = halation(film, PROPOSED, lo)
        for name, img in [("camera", cam), ("film-only", film), ("current-sim", cur), ("proposed", prop)]:
            Image.fromarray((np.clip(img, 0, 1) * 255 + .5).astype(np.uint8)).save(d / "story" / f"halation-{frame}-{name}.jpg", quality=92)
        err_sim = float(np.sqrt(np.mean((cur[zone] - cam[zone]) ** 2)))
        err_none = float(np.sqrt(np.mean((film[zone] - cam[zone]) ** 2)))
        results[frame] = {"gain": gain, "zonePixels": int(zone.sum()), "rmsCameraVsSim": err_sim, "rmsCameraVsNoHalation": err_none, "proposedGain": lo}
        print(frame, results[frame])
    (d / "story" / "halation.json").write_text(json.dumps({"current": CURRENT, "proposed": PROPOSED, "frames": results}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
