"""Measured shoreline observations and Portra illustration on the exact renders.

Manual observations are approximate far-water boundaries, not a calibration
target. Residuals include shoreline distance/height, visual picking uncertainty,
unknown sensor-level latency and any in-camera geometry correction.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import struct

import numpy as np
from PIL import Image, ImageDraw

from tools.horizon_grads.metadata import safe_output
from tools.horizon_grads.process import apply_grad
from tools.horizon_grads.run import DEFAULT_OUTPUT, overlay, panel
from tools.jpeg_experiments.run import array_image, font, image_array, save_jpeg, write_json


def trilinear(rgb, grid):
    size = grid.shape[0]
    pos = np.clip(rgb, 0, 1) * (size - 1)
    low = np.minimum(np.floor(pos).astype(np.int32), size - 2)
    frac = pos - low
    out = np.zeros_like(rgb)
    for r in (0, 1):
        for g in (0, 1):
            for b in (0, 1):
                w = ((frac[..., 0] if r else 1 - frac[..., 0]) *
                     (frac[..., 1] if g else 1 - frac[..., 1]) *
                     (frac[..., 2] if b else 1 - frac[..., 2]))
                out += grid[low[..., 0] + r, low[..., 1] + g, low[..., 2] + b] * w[..., None]
    return np.clip(out, 0, 1)


def measure(output: Path):
    observed = json.loads(Path(__file__).with_name("observations.json").read_text(encoding="utf-8"))
    observations = []
    tiles = []
    for obs in observed["observations"]:
        sub = output / obs["id"]
        record = json.loads((sub / "manifest.json").read_text(encoding="utf-8"))
        meta = record["metadata_used"]
        before = Image.open(sub / "before.png").convert("RGB")
        mask = np.asarray(Image.open(sub / "mask.png"), dtype=np.float32) / 65535
        im = overlay(image_array(before), mask, meta)
        draw = ImageDraw.Draw(im)
        errors = []
        r, p = math.radians(meta["roll_deg"]), math.radians(meta["pitch_deg"])
        points = []
        # Coordinates were picked on the 2000-long render, then normalized.
        for u, v in obs["points_uv"]:
            x, y = u * (im.width - 1), v * (im.height - 1)
            expected_y = (im.height - 1) / 2 + (meta["focal_px"] * math.tan(p) - math.sin(r) * (x - (im.width - 1) / 2)) / math.cos(r)
            errors.append(y - expected_y)
            points.append((x, y))
            draw.ellipse((x - 9, y - 9, x + 9, y + 9), fill=(255, 200, 30))
        draw.line(points, fill=(255, 200, 30), width=3)
        result = {**obs, "render_size": list(before.size), "predicted_roll_deg": meta["roll_deg"],
                  "predicted_pitch_deg": meta["pitch_deg"], "residual_y_px": errors,
                  "mean_abs_residual_px": float(np.abs(errors).mean()),
                  "mean_abs_residual_fraction_long_side": float(np.abs(errors).mean() / max(im.size)),
                  "observed_line_slope_deg": math.degrees(math.atan2(points[-1][1] - points[0][1], points[-1][0] - points[0][0])),
                  "predicted_line_slope_deg": -meta["roll_deg"]}
        observations.append(result)
        title = f"{obs['id']} | cyan predicted; gold observed shore | mean |dy| {result['mean_abs_residual_px']:.1f}px at {max(im.size)}px"
        tile = panel([im], [obs["interpretation"]], width=1200, max_height=900, title=title)
        save_jpeg(tile, output / (obs["id"] + "-horizon-observation.jpg"))
        tiles.append(tile)
    combined = Image.new("RGB", (1200, sum(t.height for t in tiles)), (20, 24, 29))
    y = 0
    for tile in tiles:
        combined.paste(tile, (0, y))
        y += tile.height
    save_jpeg(combined, output / "horizon-observations.jpg")
    # Independent numerical consistency with the trailing 3 int16 fields, whose
    # interpretation as an acceleration-like vector remains a hypothesis.
    audit = json.loads((output / "audit.json").read_text(encoding="utf-8"))
    residuals = []
    for row in audit:
        if not row["valid"]:
            continue
        x, y, z = struct.unpack_from("<hhh", bytes.fromhex(row["raw_level_hex"]), 13)
        direction = row["camera_orientation"]
        x, y = ((x, y), (y, -x), (-x, -y), (-y, x))[direction]
        if x == y == 0:
            continue
        roll = -math.degrees(math.atan2(x, -y))
        pitch = math.degrees(math.atan2(z, math.hypot(x, y)))
        residuals.append([abs(roll - row["roll_deg"]), abs(pitch - row["pitch_deg"]), math.sqrt(x*x + y*y + z*z)])
    values = np.asarray(residuals)
    report = {"observations": observations,
              "trailing_vector_hypothesis": {"n": len(residuals), "median_abs_roll_disagreement_deg": float(np.median(values[:, 0])),
                                              "median_abs_pitch_disagreement_deg": float(np.median(values[:, 1])),
                                              "median_vector_norm": float(np.median(values[:, 2])),
                                              "limitation": "Algebraic consistency within one metadata record supports angle decoding; it is not independent camera attitude calibration."}}
    write_json(output / "horizon-observations.json", report)
    print(json.dumps(report, indent=2), flush=True)


def portra(output: Path, grid_path: Path):
    model = json.loads(Path(str(grid_path) + ".json").read_text(encoding="utf-8"))
    grid = np.fromfile(grid_path, dtype="<f4").reshape((model["size"],) * 3 + (3,))
    results = []
    for key in ("Ricoh-AK000071", "Ricoh-AK000080", "Ricoh2-AK000025"):
        sub = output / key
        before = Image.open(sub / "before.png").convert("RGB")
        mask = np.asarray(Image.open(sub / "mask.png"), dtype=np.float32) / 65535
        rgb = image_array(before)
        film = trilinear(rgb, grid)
        after = apply_grad(film, mask, "neutral", 1)
        tile = panel([before, array_image(film), array_image(after)],
                     ["Actual camera JPEG", "Repository Portra target", "Same Portra + 1-stop grad"], width=640,
                     title=f"{key} | same horizon mask, independent of film hue | authored target on existing JPEG")
        save_jpeg(tile, output / (key + "-portra.jpg"))
        outside = mask == 0
        results.append({"id": key, "outside_mask_max_change": float(np.abs(film - after)[outside].max()) if outside.any() else None,
                        "mean_abs_change_255": float(np.abs(film - after).mean() * 255), "size": list(before.size)})
    write_json(output / "portra-manifest.json", {"model": model, "results": results})
    print(json.dumps(results, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("measure", "portra"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--film-grid", type=Path)
    args = parser.parse_args()
    out = safe_output(args.output)
    if args.command == "measure":
        measure(out)
    else:
        if args.film_grid is None:
            parser.error("portra requires --film-grid")
        portra(out, args.film_grid)
