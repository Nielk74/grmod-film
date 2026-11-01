"""Film has no auto white balance: warm-light scenes rendered as a daylight film would see them.

    python wb_v3.py COMPARE_DIR

A daylight-balanced film under tungsten or sodium light comes out warm orange, the look of night and
interior shots on film; a lab scanning it corrects only part of that. The camera's auto white balance
neutralises it before any film is applied. Here each DNG is developed with white balance multipliers
between the camera's (k = 0, as today) and LibRaw's daylight ones (k = 1, no correction), in log space
(k = 0.5: a lab's partial correction), rendered through the calibrated GR III Standard model at the
exposure fitted on the camera's own JPEG, then through Portra 400 film response.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rawpy
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).parent))
from compare_page_v3 import apply_grid  # noqa: E402
from raw_crop_v2 import crop_raw_to_camera_frame  # noqa: E402

THETA_K = 22
KNOTS = np.linspace(-13.0, 2.5, THETA_K)


def standard(theta, lin, gain):
    m = theta[:9].reshape(3, 3)
    cv = theta[9:9 + 3 * THETA_K].reshape(3, THETA_K)
    vals = (np.cumsum(np.log1p(np.exp(cv)), axis=1) - np.log1p(np.exp(cv[:, :1]))) / 30.0
    x = np.log2(np.maximum(lin @ m.T * gain, 2 ** -13.0))
    return np.clip(np.stack([np.interp(x[..., c], KNOTS, vals[c]) for c in range(3)], -1), 0, 1)


def develop(path, k):
    with rawpy.imread(str(path)) as raw:
        cam = np.array(raw.camera_whitebalance[:4], float); day = np.array(raw.daylight_whitebalance[:4], float)
        cam[3] = cam[3] or cam[1]; day[3] = day[3] or day[1]
        cam /= cam[1]; day /= day[1]
        wb = np.exp((1 - k) * np.log(cam) + k * np.log(day))
        out = raw.postprocess(demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD, half_size=True, user_wb=list(wb),
                              output_color=rawpy.ColorSpace.sRGB, output_bps=16, no_auto_bright=True, adjust_maximum_thr=0.0,
                              highlight_mode=rawpy.HighlightMode.Clip, exp_shift=0.25, gamma=(1, 1))
    return out.astype(np.float32) / (65535.0 * 0.25)


def main():
    d = Path(sys.argv[1])
    theta = np.load(d / "standard-model-theta.npy")
    data = json.loads((d / "data.js").read_text(encoding="utf-8").split("=", 1)[1].rstrip().rstrip(";"))
    n = data["grid"]
    m = next(x for x in data["models"] if x["film"] == "Portra 400" and x["variant"] == "film")
    grid = np.frombuffer((d / "models" / f"{m['file']}-native.f32").read_bytes(), dtype="<f4").reshape(n, n, n, 3)
    for name in ["Ricoh/R0000007", "Ricoh/R0000013", "Ricoh/AK000164", "Ricoh/R0000011", "Ricoh/R0000006"]:
        dng = Path(rf"C:\Users\Antoine\Pictures\{name}.DNG")
        cam_jpg = np.asarray(ImageOps.exif_transpose(Image.open(dng.with_suffix(".JPG"))).convert("RGB"), dtype=np.float32) / 255
        renders = {}
        gain = None
        for k in (0.0, 0.5, 1.0):
            lin, _ = crop_raw_to_camera_frame(develop(dng, k), dng)
            s = 1600 / max(lin.shape[:2])
            lin = np.stack([np.asarray(Image.fromarray(np.ascontiguousarray(lin[..., c]), "F").resize(
                (round(lin.shape[1] * s), round(lin.shape[0] * s)), Image.BOX)) for c in range(3)], -1)
            if gain is None:  # exposure as the camera chose it: fit on its own JPEG, camera white balance
                ref = np.asarray(Image.fromarray((cam_jpg * 255).astype(np.uint8)).resize((lin.shape[1], lin.shape[0]), Image.BOX), dtype=np.float32) / 255
                gain = min(((float(np.mean((standard(theta, lin[::6, ::6], 2 ** g) - ref[::6, ::6]) ** 2)), 2 ** g) for g in np.linspace(-2.5, 2.5, 51)))[1]
            renders[k] = apply_grid(standard(theta, lin, gain), grid)
        stem = name.replace("/", "-")
        for k, img in renders.items():
            Image.fromarray((np.clip(img, 0, 1) * 255 + .5).astype(np.uint8)).save(d / "story" / f"wb-{stem}-k{int(k * 10):02d}.jpg", quality=92)
        print(stem, "gain", round(gain, 2), flush=True)


if __name__ == "__main__":
    main()
