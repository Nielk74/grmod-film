"""Prepare the before/after comparison page: the user's camera-Standard JPEGs, thumbnails, and
the measured strength of every film variant on them (camera-quantized grids from film_strength_v3.ts).

    python compare_page_v3.py OUT_DIR

OUT_DIR holds models/ (from film_strength_v3.ts); photos/, thumbs/ and data.js are written next to it.
Only JPEGs whose maker note says Standard (ImageTone 0x100) are used: the films are fitted against
Standard, so any other look would be a wrong "before".
"""
from __future__ import annotations

import glob
import json
import struct
import sys
from pathlib import Path

import colour
import numpy as np
from PIL import Image, ImageOps

SOURCES = [r"C:\Users\Antoine\Pictures\Ricoh", r"C:\Users\Antoine\Pictures\Ricoh2"]
STANDARD = 0x100


def image_tone(path: str) -> int | None:
    """Ricoh maker note ("RICOH\\0" + byte order + IFD), tag 0x004f ImageTone."""
    note = Image.open(path).getexif().get_ifd(0x8769).get(0x927C)
    if not note or not note.startswith(b"RICOH"):
        return None
    end = "<" if note[6:8] == b"II" else ">"
    count = struct.unpack(end + "H", note[8:10])[0]
    for i in range(count):
        tag, kind, _, value = struct.unpack(end + "HHI4s", note[10 + 12 * i: 22 + 12 * i])
        if tag == 0x004F:
            return struct.unpack(end + ("H" if kind == 3 else "I"), value[:2] if kind == 3 else value)[0]
    return None


def apply_grid(rgb: np.ndarray, grid: np.ndarray) -> np.ndarray:
    n = grid.shape[0]
    p = np.clip(rgb, 0, 1) * (n - 1)
    lo = np.minimum(p.astype(int), n - 2)
    w = p - lo
    out = np.zeros_like(rgb)
    for i in (0, 1):
        for j in (0, 1):
            for k in (0, 1):
                ww = (w[..., 0] if i else 1 - w[..., 0]) * (w[..., 1] if j else 1 - w[..., 1]) * (w[..., 2] if k else 1 - w[..., 2])
                out += grid[lo[..., 0] + i, lo[..., 1] + j, lo[..., 2] + k] * ww[..., None]
    return out


def lab(rgb: np.ndarray) -> np.ndarray:
    return colour.XYZ_to_Lab(colour.sRGB_to_XYZ(np.clip(rgb, 0, 1)))


def standard_from_raw(theta: np.ndarray, jpeg: str) -> np.ndarray:
    """The calibrated DNG -> camera-Standard model (matrix + per-channel curves over log2 exposure,
    fitted on the user's 37 Standard pairs, held-out 1.74 dE00), with the shot's exposure gain
    matched to its own camera JPEG. Returns display sRGB in the camera JPEG's framing."""
    sys.path.insert(0, str(Path(__file__).parent))
    from raw_ops import decode_raw
    from raw_crop_v2 import crop_raw_to_camera_frame
    k = 22
    knots = np.linspace(-13.0, 2.5, k)
    raw, _ = decode_raw(Path(jpeg).with_suffix(".DNG"), half_size=True)
    raw, _ = crop_raw_to_camera_frame(raw, Path(jpeg).with_suffix(".DNG"))
    cam = np.asarray(ImageOps.exif_transpose(Image.open(jpeg)).convert("RGB"), dtype=np.float32) / 255
    ratio = max(cam.shape[:2]) / 6000  # GR Mod's full-frame RAW: the JPEG's digital crop is centred
    if ratio < 0.99 and max(raw.shape[:2]) > 2700:
        h, w = raw.shape[:2]; ch, cw = round(h * ratio), round(w * ratio)
        raw = raw[(h - ch) // 2:(h - ch) // 2 + ch, (w - cw) // 2:(w - cw) // 2 + cw]
    s = 1600 / max(raw.shape[:2])
    raw = np.stack([np.asarray(Image.fromarray(np.ascontiguousarray(raw[..., c], dtype=np.float32), "F").resize(
        (round(raw.shape[1] * s), round(raw.shape[0] * s)), Image.BOX)) for c in range(3)], -1)
    m = theta[:9].reshape(3, 3)
    cv = theta[9:9 + 3 * k].reshape(3, k)
    vals = (np.cumsum(np.log1p(np.exp(cv)), axis=1) - np.log1p(np.exp(cv[:, :1]))) / 30.0
    def render(gain):
        lx = np.log2(np.maximum(raw @ m.T * gain, 2 ** -13.0))
        return np.clip(np.stack([np.interp(lx[..., c], knots, vals[c]) for c in range(3)], -1), 0, 1)
    small = np.asarray(Image.fromarray((cam * 255).astype(np.uint8)).resize((raw.shape[1], raw.shape[0]), Image.BOX), dtype=np.float32) / 255
    best = min((float(np.mean((render(2 ** g)[::8, ::8] - small[::8, ::8]) ** 2)), g) for g in np.linspace(-2.5, 2.5, 51))[1]
    return render(2 ** best)


def main() -> None:
    out = Path(sys.argv[1])
    theta = np.load(out / "standard-model-theta.npy")
    (out / "photos").mkdir(parents=True, exist_ok=True)
    (out / "thumbs").mkdir(exist_ok=True)
    models = json.loads((out / "models" / "models.json").read_text(encoding="utf-8"))
    n = models["grid"]
    photos, small = [], []
    for folder in SOURCES:
        for path in sorted(glob.glob(str(Path(folder) / "*.JPG"))):
            tone = image_tone(path)
            pid = Path(folder).name + "-" + Path(path).stem
            done = out / "photos" / f"{pid}.jpg"
            if done.exists() and (tone == STANDARD or Path(path).with_suffix(".DNG").exists()):
                # already prepared: reuse it (only the film models changed)
                big = Image.open(done).convert("RGB")
                s = big.copy(); s.thumbnail((360, 360), Image.BOX)
                small.append(np.asarray(s, dtype=np.float32) / 255)
                photos.append({"id": pid, "w": big.width, "h": big.height, "basis": "camera" if tone == STANDARD else "raw", "shotWith": hex(tone) if tone else None})
                continue
            if tone == STANDARD:
                im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
                basis = "camera"
            elif Path(path).with_suffix(".DNG").exists():
                im = Image.fromarray((standard_from_raw(theta, path) * 255 + .5).astype(np.uint8))
                basis = "raw"
            else:
                continue
            pid = Path(folder).name + "-" + Path(path).stem
            big = im.copy(); big.thumbnail((1600, 1600), Image.LANCZOS)
            big.save(out / "photos" / f"{pid}.jpg", quality=92)
            th = im.copy(); th.thumbnail((240, 240), Image.LANCZOS)
            th.save(out / "thumbs" / f"{pid}.jpg", quality=85)
            s = im.copy(); s.thumbnail((360, 360), Image.BOX)
            small.append(np.asarray(s, dtype=np.float32) / 255)
            photos.append({"id": pid, "w": big.width, "h": big.height, "basis": basis, "shotWith": hex(tone) if tone else None})
            print(pid, basis, flush=True)
    print(len(photos), "photos;", sum(p["basis"] == "camera" for p in photos), "camera Standard")
    base_lab = [lab(s) for s in small]
    for m in models["models"]:
        grid = np.frombuffer((out / "models" / f"{m['file']}-native.f32").read_bytes(), dtype="<f4").reshape(n, n, n, 3)
        des = [float(colour.delta_E(b, lab(apply_grid(s, grid)), method="CIE 2000").mean()) for s, b in zip(small, base_lab)]
        m["onPhotosDE00"] = {"median": float(np.median(des)), "p10": float(np.percentile(des, 10)), "p90": float(np.percentile(des, 90))}
        print(f"{m['film']:16s} {m['variant']:8s} median dE00 vs Standard {np.median(des):5.2f}  fit {m['fitMeanDE2000']:.2f}")
    data = {"grid": n, "photos": photos, "models": models["models"]}
    (out / "data.js").write_text("window.COMPARE = " + json.dumps(data) + ";\n", encoding="utf-8")


if __name__ == "__main__":
    main()
