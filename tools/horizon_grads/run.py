"""Reproduce: python -m tools.horizon_grads.run audit|render|verify.

All source I/O is read-only. Only whitelisted attitude/lens metadata is recorded;
GPS, timestamps, owner names and serial numbers are never copied to outputs.
"""
from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path
import time

import numpy as np
from PIL import Image, ImageDraw

from tools.horizon_grads.metadata import SOURCES, digest, read_metadata, safe_output
from tools.horizon_grads.process import STYLES, apply_grad, brightness_weight, focal_pixels, horizon_distance, make_mask
from tools.jpeg_experiments.run import array_image, font, image_array, open_rgb, save_jpeg, write_json

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "scratch/horizon-grads"
PRODUCED_IMAGES = ("before.png", "neutral.png", "weighted.png", "overlay.png", "before.jpg", "neutral.jpg",
                   "weighted.jpg", "overlay.jpg", "mask.png", "comparison.jpg", "colours.jpg", "tobacco.jpg", "sunset.jpg", "blue.jpg")


def panel(images, labels, width=480, max_height=500, title=""):
    if len(images) != len(labels):
        raise ValueError("One label per panel required")
    resized = []
    for im in images:
        tile = im.copy()
        tile.thumbnail((width, max_height), Image.Resampling.LANCZOS)
        resized.append(tile)
    h = max(im.height for im in resized)
    out = Image.new("RGB", (width * len(images), h + 92), (20, 24, 29))
    draw = ImageDraw.Draw(out)
    draw.text((12, 8), title, font=font(19), fill="white")
    for n, (im, label) in enumerate(zip(resized, labels)):
        draw.text((n * width + 12, 40), label, font=font(18), fill=(200, 213, 225))
        out.paste(im, (n * width + (width - im.width) // 2, 84))
    return out


def audit(output: Path):
    paths = sorted(p for root in SOURCES for p in root.rglob("*") if p.suffix.lower() in (".jpg", ".jpeg"))
    records = []
    # Hash every JPEG before the contact-sheet decode and rehash after it.
    for path in paths:
        records.append({"id": f"{path.parent.name}-{path.stem}", "path": str(path.resolve()),
                        "sha256_before": digest(path), **read_metadata(path)})
    for page, start in enumerate(range(0, len(records), 30), 1):
        items = records[start:start + 30]
        cell_w, cell_h, cols = 350, 310, 5
        out = Image.new("RGB", (cols * cell_w, math.ceil(len(items) / cols) * cell_h), (20, 24, 29))
        draw = ImageDraw.Draw(out)
        for n, record in enumerate(items):
            im = open_rgb(Path(record["path"]), 340)
            im.thumbnail((340, 230), Image.Resampling.LANCZOS)
            x, y = n % cols * cell_w, n // cols * cell_h
            out.paste(im, (x + (cell_w - im.width) // 2, y))
            draw.text((x + 8, y + 235), record["id"], font=font(17), fill="white")
            label = f"r={record.get('roll_deg')} p={record.get('pitch_deg')}  EXIF {record['exif_orientation']}"
            draw.text((x + 8, y + 258), label, font=font(16), fill=(169, 199, 221))
            draw.text((x + 8, y + 281), "VALID" if record["valid"] else record["reason"][:36],
                      font=font(14), fill=(130, 220, 161) if record["valid"] else (255, 157, 118))
        save_jpeg(out, output / f"contact-{page:02d}.jpg")
    for record in records:
        record["sha256_after"] = digest(Path(record["path"]))
        if record["sha256_before"] != record["sha256_after"]:
            raise RuntimeError(f"Original hash changed: {record['id']}")
    write_json(output / "audit.json", records)
    summary = {"jpeg_count": len(records), "level_present": sum("raw_level_hex" in r for r in records),
               "usable": sum(r["valid"] for r in records), "invalid": [{"id": r["id"], "reason": r["reason"]} for r in records if not r["valid"]],
               "all_hashes_unchanged": True, "contact_sheets": math.ceil(len(records) / 30),
               "focal35_counts": {str(f): sum(r["focal35_mm"] == f for r in records) for f in sorted(set(r["focal35_mm"] for r in records))}}
    write_json(output / "audit-summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


def overlay(rgb, mask, metadata):
    tinted = rgb * (1 - 0.42 * mask[..., None]) + np.array([0.9, 0.08, 0.9]) * (0.42 * mask[..., None])
    im = array_image(tinted)
    if metadata["valid"] and abs(metadata["pitch_deg"]) < 65:
        d = horizon_distance(im.width, im.height, metadata["focal_px"], metadata["roll_deg"], metadata["pitch_deg"])
        pix = np.array(im)
        pix[np.abs(d) < max(1.3, im.width / 700)] = [30, 255, 194]
        im = Image.fromarray(pix)
    return im


def render(output: Path, max_side: int, selection_path: Path):
    audit_records = json.loads((output / "audit.json").read_text(encoding="utf-8"))
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    lookup = {r["id"]: r for r in audit_records}
    rendered = []
    sheets = []
    for item in selection["sources"]:
        source = lookup[item["id"]]
        path = Path(source["path"])
        before_hash = digest(path)
        before = open_rgb(path, max_side)
        rgb = image_array(before)
        meta = dict(source)
        meta["focal_px"] = focal_pixels(*source["stored_size"], source["focal_mm"] or 18.3, source["focal35_mm"] or 28) * max(before.size) / max(source["stored_size"])
        mask = make_mask(before.width, before.height, meta)
        plain = apply_grad(rgb, mask, "neutral", 1)
        smart = apply_grad(rgb, mask, "neutral", 1, weighted=True)
        sub = output / item["id"]
        sub.mkdir(parents=True, exist_ok=True)
        # Lossless copies make exact outside-mask identity independently testable.
        for name, image in (("before", before), ("neutral", array_image(plain)), ("weighted", array_image(smart)),
                            ("overlay", overlay(rgb, mask, meta))):
            image.save(sub / f"{name}.png")
            save_jpeg(image, sub / f"{name}.jpg")
        Image.fromarray(np.rint(mask * 65535).astype(np.uint16)).save(sub / "mask.png")
        title = f"{item['id']} | {item['purpose']} | roll {meta.get('roll_deg')} pitch {meta.get('pitch_deg')} deg"
        compare = panel([before, array_image(plain), array_image(smart), overlay(rgb, mask, meta)],
                        ["Actual camera JPEG", "Neutral grad, 1 stop", "Same + brightness weight", "Mask + predicted horizon"], title=title)
        save_jpeg(compare, sub / "comparison.jpg")
        sheets.append(compare)
        colour_images = [before]
        for style in STYLES:
            after = array_image(apply_grad(rgb, mask, style, 1))
            save_jpeg(after, sub / f"{style}.jpg")
            colour_images.append(after)
        save_jpeg(panel(colour_images, ["Actual camera JPEG", "Neutral", "Tobacco", "Sunset", "Blue"], title=title, width=430), sub / "colours.jpg")
        outside = mask == 0
        after_hash = digest(path)
        if before_hash != after_hash or before_hash != source["sha256_before"]:
            raise RuntimeError(f"Original changed: {item['id']}")
        metrics = {"mask_nonzero_fraction": float((mask > 0).mean()), "mask_mean": float(mask.mean()),
                   "outside_mask_max_change_float": float(np.abs(plain - rgb)[outside].max()) if outside.any() else None,
                   "mean_abs_rgb_change_255": float(np.abs(plain - rgb).mean() * 255),
                   "weighted_mean_abs_rgb_change_255": float(np.abs(smart - rgb).mean() * 255),
                   "dark_above_horizon_mean_change_255": float(np.abs(plain - rgb)[(mask > .2) & (brightness_weight(rgb) < .2)].mean() * 255) if ((mask > .2) & (brightness_weight(rgb) < .2)).any() else None,
                   "dark_above_horizon_weighted_change_255": float(np.abs(smart - rgb)[(mask > .2) & (brightness_weight(rgb) < .2)].mean() * 255) if ((mask > .2) & (brightness_weight(rgb) < .2)).any() else None}
        record = {"source": source, "purpose": item["purpose"], "render_size": list(before.size), "metadata_used": meta,
                  "parameters": {"stops": 1, "transition_deg": 16, "fade_pitch_deg": [35, 65], "density_channel_multipliers": STYLES,
                                 "brightness_weight_display_luma": [0.12, 0.55]}, "metrics": metrics,
                  "sha256_after_render": after_hash, "files": {name: digest(sub / name) for name in PRODUCED_IMAGES}}
        write_json(sub / "manifest.json", record)
        rendered.append(record)
        print(f"Rendered {item['id']}: {before.width}x{before.height}, mask {metrics['mask_nonzero_fraction']:.1%}", flush=True)
    for page, start in enumerate(range(0, len(sheets), 4), 1):
        chosen = sheets[start:start + 4]
        out = Image.new("RGB", (max(im.width for im in chosen), sum(im.height for im in chosen)), (20, 24, 29))
        y = 0
        for im in chosen:
            out.paste(im, (0, y))
            y += im.height
        save_jpeg(out, output / f"comparison-sheet-{page:02d}.jpg")
    write_json(output / "render-manifest.json", {"source_selection": str(selection_path.resolve()), "max_side": max_side,
                                               "basis": "actual camera JPEG; EXIF upright; sRGB; identical output encoding Q97 4:4:4; no source EXIF copied",
                                               "results": rendered})
    links = []
    for item in selection["sources"]:
        key = html.escape(item["id"])
        links.append(f'<h2>{key}: {html.escape(item["purpose"])}</h2><a href="{key}/comparison.jpg"><img src="{key}/comparison.jpg"></a><a href="{key}/colours.jpg">Colour options</a>')
    (output / "index.html").write_text('<!doctype html><meta charset="utf-8"><title>Horizon grads</title><style>body{background:#14181d;color:#e5edf5;font:16px sans-serif;margin:24px}img{width:100%;max-width:1920px}a{color:#90d8ff}</style><h1>Horizon-locked graduated filters — actual JPEGs</h1><p>1 stop neutral / brightness weight / mask overlay. Cyan line: predicted earth horizon. Magenta: amount of grad. This is not sky segmentation. <a href="audit-summary.json">Metadata audit</a></p>' + ''.join(links), encoding="utf-8")


def verify(output: Path):
    audit_records = json.loads((output / "audit.json").read_text(encoding="utf-8"))
    manifest = json.loads((output / "render-manifest.json").read_text(encoding="utf-8"))
    failures = []
    for record in audit_records:
        if digest(Path(record["path"])) != record["sha256_before"]:
            failures.append(f"Original changed: {record['id']}")
    images = 0
    for record in manifest["results"]:
        sub = output / record["source"]["id"]
        for name, sha in record["files"].items():
            path = sub / name
            if name not in PRODUCED_IMAGES:
                failures.append(f"Unexpected exported file: {path}")
                continue
            if digest(path) != sha:
                failures.append(f"Output hash changed: {path}")
            with Image.open(path) as im:
                im.load()
                if im.getexif():
                    failures.append(f"EXIF copied: {path}")
                if im.format != ("PNG" if path.suffix == ".png" else "JPEG"):
                    failures.append(f"Unexpected format: {path}")
                if name not in ("comparison.jpg", "colours.jpg") and list(im.size) != record["render_size"]:
                    failures.append(f"Unexpected dimensions: {path}")
                images += 1
        with Image.open(sub / "before.png") as im:
            before = np.array(im)
        with Image.open(sub / "neutral.png") as im:
            after = np.array(im)
        with Image.open(sub / "weighted.png") as im:
            smart = np.array(im)
        with Image.open(sub / "mask.png") as im:
            zero = np.array(im) == 0
        if not np.array_equal(before[zero], after[zero]) or not np.array_equal(before[zero], smart[zero]):
            failures.append(f"Pixels below horizon changed: {sub}")
        if not record["source"]["valid"] and not np.array_equal(before, after):
            failures.append(f"Invalid metadata did not no-op: {sub}")
    report = {"source_hashes_verified": len(audit_records), "output_images_verified": images,
              "exact_outside_mask_identity": not failures, "private_exif_absent": not failures, "failures": failures}
    write_json(output / "verification.json", report)
    print(json.dumps(report, indent=2), flush=True)
    if failures:
        raise RuntimeError("Verification failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("audit", "render", "verify"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--selection", type=Path, default=Path(__file__).with_name("selection.json"))
    parser.add_argument("--max-side", type=int, default=2000)
    args = parser.parse_args()
    output = safe_output(args.output)
    output.mkdir(parents=True, exist_ok=True)
    if args.max_side < 100:
        parser.error("max-side must be at least 100")
    started = time.perf_counter()
    if args.command == "audit":
        audit(output)
    elif args.command == "render":
        render(output, args.max_side, args.selection)
    else:
        verify(output)
    print(f"{args.command}: {time.perf_counter() - started:.2f}s desktop wall time", flush=True)


if __name__ == "__main__":
    main()
