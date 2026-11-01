"""Reproducible offline JPEG experiments. Original photographs are read only."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageCms, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = Path("C:/Users/Antoine/Pictures/GRMod-JPEG-Experiments-2026-10-31")
SOURCES = [Path("C:/Users/Antoine/Pictures/Ricoh"), Path("C:/Users/Antoine/Pictures/Ricoh2")]
SRGB = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def font(size=24):
    for name in ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"):
        if Path(name).exists():
            return ImageFont.truetype(name, size=size)
    return ImageFont.load_default(size=size)


def open_rgb(path: Path, max_side: int | None = None) -> Image.Image:
    with Image.open(path) as source:
        im = ImageOps.exif_transpose(source)
        profile = source.info.get("icc_profile")
        if profile:
            import io
            try:
                im = ImageCms.profileToProfile(im, ImageCms.ImageCmsProfile(io.BytesIO(profile)), SRGB, outputMode="RGB")
            except (OSError, ValueError, ImageCms.PyCMSError):
                im = im.convert("RGB")
        else:
            im = im.convert("RGB")
        if max_side:
            im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        return im.copy()


def image_array(image: Image.Image) -> np.ndarray:
    return np.asarray(image, dtype=np.float32) / 255.0


def array_image(rgb: np.ndarray) -> Image.Image:
    if not np.isfinite(rgb).all():
        raise ValueError("Non-finite image values")
    return Image.fromarray(np.rint(np.clip(rgb, 0, 1) * 255).astype(np.uint8))


def save_jpeg(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, quality=97, subsampling=0, optimize=True, icc_profile=SRGB.tobytes())


def side_by_side(before: Image.Image, after: Image.Image, labels=("BEFORE", "AFTER"), panel_width=1200) -> Image.Image:
    if before.size != after.size:
        raise ValueError("Comparison dimensions must match")
    left, right = before.copy(), after.copy()
    left.thumbnail((panel_width, 1000), Image.Resampling.LANCZOS)
    right = right.resize(left.size, Image.Resampling.LANCZOS)
    bar, gap = 56, 8
    out = Image.new("RGB", (left.width * 2 + gap, left.height + bar), (18, 22, 27))
    out.paste(left, (0, bar)); out.paste(right, (left.width + gap, bar))
    draw = ImageDraw.Draw(out)
    draw.text((18, 13), labels[0], font=font(23), fill=(220, 225, 232))
    draw.text((left.width + gap + 18, 13), labels[1], font=font(23), fill=(220, 225, 232))
    return out


def exif_data(path: Path) -> dict:
    with Image.open(path) as im:
        exif = im.getexif()
        try:
            detail = exif.get_ifd(34665)
        except (KeyError, TypeError, ValueError):
            detail = {}
        def value(key, default=None):
            v = detail.get(key, exif.get(key, default))
            if isinstance(v, bytes): return v.decode("utf-8", errors="replace").strip("\x00")
            if isinstance(v, (str, int, float, type(None))): return v
            try: return float(v)
            except (TypeError, ValueError): return str(v)
        return {"camera": value(272), "iso": value(34855, 100), "exposure_seconds": value(33434),
                "aperture": value(33437), "datetime": value(36867), "orientation": value(274, 1),
                "native_size": list(im.size), "icc_profile": bool(im.info.get("icc_profile")),
                "software": value(305)}


def inventory(output: Path) -> list[dict]:
    out = output / "00-source-selection"
    out.mkdir(parents=True, exist_ok=True)
    records = []
    for source in SOURCES:
        for path in sorted(source.rglob("*")):
            if path.suffix.lower() not in (".jpg", ".jpeg"):
                continue
            try:
                im = open_rgb(path, 480)
                rgb = image_array(im)
                maximum, minimum = rgb.max(-1), rgb.min(-1)
                chroma = maximum - minimum
                saturation = chroma / np.maximum(maximum, 0.01)
                luma = rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
                raw = next((p for p in [path.with_suffix(".DNG"), path.with_suffix(".dng")] if p.exists()), None)
                records.append({"id": f"{source.name}-{path.stem}", "path": str(path), "raw": str(raw) if raw else None,
                                **exif_data(path), "mean_luma": float(luma.mean()),
                                "highlight_fraction": float((maximum > 0.97).mean()),
                                "shadow_fraction": float((luma < 0.1).mean()),
                                "colour_fraction": float((saturation > 0.4).mean()),
                                "blue_fraction": float(((rgb[..., 2] > rgb[..., 0] * 1.1) & (rgb[..., 2] > rgb[..., 1] * 1.03) & (chroma > 0.08)).mean())})
            except (OSError, ValueError) as error:
                print(f"Skipping unreadable image {path}: {error}", flush=True)
    write_json(out / "inventory.json", records)
    for page, start in enumerate(range(0, len(records), 40)):
        items = records[start:start + 40]
        cell_w, cell_h, cols = 360, 285, 5
        sheet = Image.new("RGB", (cols * cell_w, math.ceil(len(items) / cols) * cell_h), (22, 25, 30))
        draw = ImageDraw.Draw(sheet)
        for n, record in enumerate(items):
            im = open_rgb(Path(record["path"]), 350)
            im.thumbnail((350, 235), Image.Resampling.LANCZOS)
            x, y = (n % cols) * cell_w, (n // cols) * cell_h
            sheet.paste(im, (x + (cell_w - im.width) // 2, y))
            draw.text((x + 7, y + 238), record["id"], font=font(17), fill="white")
            draw.text((x + 7, y + 261), f"ISO {record['iso']}  {'RAW pair' if record['raw'] else 'JPEG'}", font=font(15), fill=(160, 174, 190))
        save_jpeg(sheet, out / f"contact-sheet-{page + 1:02d}.jpg")
    print(json.dumps({"inventory": len(records), "paired_raw": sum(bool(r["raw"]) for r in records), "contact_sheets": math.ceil(len(records) / 40)}, indent=2), flush=True)
    return records


def validate_output(output: Path, sources=None) -> None:
    target = output.resolve()
    for source in sources if sources is not None else SOURCES:
        root = Path(source).resolve()
        if target == root or root in target.parents:
            raise ValueError(f"Output must be outside source tree: {root}")


def result_metrics(before: np.ndarray, after: np.ndarray) -> dict:
    if before.shape != after.shape:
        raise ValueError("Comparison dimensions must match")
    total = before.shape[0] * before.shape[1]
    sums, maximum, changed, clip_before, clip_after = 0.0, 0.0, 0, 0, 0
    for start in range(0, before.shape[0], 128):
        a, b = before[start:start + 128], after[start:start + 128]
        d = np.abs(a - b)
        sums += float(d.sum(dtype=np.float64))
        maximum = max(maximum, float(d.max()))
        changed += int((d.max(-1) > 0.5 / 255).sum())
        clip_before += int((a.max(-1) >= 254.5 / 255).sum())
        clip_after += int((b.max(-1) >= 254.5 / 255).sum())
    return {"mean_absolute_rgb_255": sums / (total * 3) * 255,
            "maximum_channel_change_255": maximum * 255,
            "changed_pixel_fraction": changed / total,
            "near_white_channel_fraction_before": clip_before / total,
            "near_white_channel_fraction_after": clip_after / total,
            "interpretation": "Difference measurements, not an image-quality score; a lower clipping count alone does not prove recovered detail."}


def export_result(output: Path, folder: str, source_id: str, before: np.ndarray, after: np.ndarray,
                  source: dict, basis: str, parameters: dict, representative=False,
                  crop_center=(0.5, 0.5), subfolder=None) -> dict:
    if before.shape != after.shape:
        raise ValueError("Comparison dimensions must match")
    relative = Path(folder) if representative else Path(folder) / "examples" / (subfolder or source_id)
    dest = output / relative
    dest.mkdir(parents=True, exist_ok=True)
    left, right = array_image(before), array_image(after)
    save_jpeg(left, dest / "before.jpg"); save_jpeg(right, dest / "after.jpg")
    preview_left, preview_right = left.copy(), right.copy()
    preview_left.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
    preview_right = preview_right.resize(preview_left.size, Image.Resampling.LANCZOS)
    save_jpeg(preview_left, dest / "before-preview.jpg"); save_jpeg(preview_right, dest / "after-preview.jpg")
    save_jpeg(side_by_side(preview_left, preview_right), dest / "comparison.jpg")
    crop_size = min(640, left.width, left.height)
    cx, cy = int(left.width * crop_center[0]), int(left.height * crop_center[1])
    x = max(0, min(left.width - crop_size, cx - crop_size // 2))
    y = max(0, min(left.height - crop_size, cy - crop_size // 2))
    box = (x, y, x + crop_size, y + crop_size)
    save_jpeg(side_by_side(left.crop(box), right.crop(box), panel_width=crop_size,
                           labels=("BEFORE · 100% pixels", "AFTER · 100% pixels")), dest / "crop-100-percent.jpg")
    result = {"source_id": source_id, "source_path": source["path"], "raw_path": source.get("raw") if "RAW" in basis else None,
              "basis": basis, "iso": source.get("iso"), "output_size": list(left.size),
              "preview_size": list(preview_left.size), "crop_box_xyxy": list(box),
              "crop_basis": "Pixels cropped after this exact render; one output pixel per crop pixel.",
              "before": (relative / "before.jpg").as_posix(), "after": (relative / "after.jpg").as_posix(),
              "before_preview": (relative / "before-preview.jpg").as_posix(),
              "after_preview": (relative / "after-preview.jpg").as_posix(),
              "comparison": (relative / "comparison.jpg").as_posix(),
              "crop": (relative / "crop-100-percent.jpg").as_posix(),
              "parameters": parameters, "metrics": result_metrics(before, after),
              "encoding": {"space": "sRGB", "quality": 97, "chroma_subsampling": "4:4:4", "same_encoding_both_sides": True,
                           "orientation": "Normalized upright before comparison; EXIF location metadata not copied."}}
    write_json(dest / "parameters.json", result)
    return result


def write_cube(path: Path, lut: np.ndarray) -> None:
    size = len(lut)
    lines = ['TITLE "GRMod experimental density and tone"', f"LUT_3D_SIZE {size}", "DOMAIN_MIN 0 0 0", "DOMAIN_MAX 1 1 1"]
    for b in range(size):
        for g in range(size):
            for r in range(size):
                lines.append(" ".join(f"{float(v):.8f}" for v in lut[r, g, b]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


FRAME_SCALE_BASIS = "max(rendered height, rendered width): rotation-independent unrotated sensor-width convention for these 3:2 full frames; kernels scale by this value / 6000"


def processing_frame_width(rgb: np.ndarray) -> int:
    """Return the current full frame's long side, independent of EXIF rotation.

    These sources have landscape 3:2 sensor frames. Their long side represents
    the pre-rotation sensor width at the current full-frame render resolution.
    This helper is not intended for independently processed crops.
    """
    if rgb.ndim != 3 or rgb.shape[2] != 3 or not all(rgb.shape[:2]):
        raise ValueError("rgb must be a nonempty H x W x 3 full frame")
    return int(max(rgb.shape[:2]))


def combination_pipeline(record: dict) -> list[dict]:
    """Source-specific stages shared by execution and recorded provenance."""
    recipes = {
        "Ricoh-AK000075": [("colour_density", .3), ("blue_density", .25), ("skin_tone_colour", .35), ("highlight_gamut", .25), ("film_texture", .45), ("adaptive_grain", .15)],
        "Ricoh-AK000071": [("colour_density", .4), ("blue_density", .55), ("skin_tone_colour", .2), ("highlight_gamut", .2), ("film_texture", .2)],
        "Ricoh2-AK000008": [("colour_density", .6), ("skin_tone_colour", .15), ("highlight_gamut", .3), ("film_texture", .2)],
        "Ricoh-AK000165": [("skin_tone_colour", .2), ("highlight_gamut", .15), ("film_texture", .3), ("adaptive_grain", .15)],
    }
    identifier = record["id"]
    if identifier not in recipes:
        raise ValueError(f"No reviewed combination pipeline for {identifier}")
    return [{"operation": name, "strength": strength} for name, strength in recipes[identifier]]


def lut_target_pipeline() -> list[dict]:
    """The fixed direct target used by color_ops.build_lut and lut_target."""
    return [{"operation": name, "strength": strength} for name, strength in
            [("colour_density", .45), ("blue_density", .35), ("skin_tone_colour", .45), ("highlight_gamut", .35)]]


EXPERIMENTS = [
    ("01-colour-density", "Selective colour density", "Smooth density in saturated warm and green colours, with skin and near-neutral safeguards. This is an authored approximation of the Color Chrome idea.", ["Ricoh2-AK000008", "Ricoh2-AK000011", "Ricoh-AK000089"], "density", .75),
    ("02-blue-density", "Blue density, independently of teal hue", "Deepen blue subjects while retaining their hue. Skies, water and blue objects are all affected; no semantic sky selection.", ["Ricoh-AK000071", "Ricoh2-AK000017", "Ricoh-AK000075"], "blue", .7),
    ("03-highlight-gamut", "Highlight shoulder and gamut handling", "Gently compress the bright end and constrain chroma near gamut boundaries. Existing clipped JPEG detail cannot be reconstructed.", ["Ricoh-AK000078", "Ricoh2-AK000008", "Ricoh2-AK000011"], "highlight", .7),
    ("04-skin-and-tone-colour", "Skin protection and brightness-dependent colour", "Restrained cool shadows and warm highlights, with a broad soft skin-colour safeguard. This is colour-based protection, not face detection.", ["Ricoh-AK000075", "Ricoh-AK000142", "Ricoh2-AK000011"], "skin", .6),
    ("05-complete-recipes", "Recipe: scene-linear WB, tone and detail", "A common camera-WB RAW baseline compared with relative scene-linear warmth, tint, controlled highlights and restrained texture. This demonstrates recipe coordination, not a calibrated camera preset.", ["Ricoh2-AK000008", "Ricoh-R0000001", "Ricoh2-AK000017"], "recipe", .55),
    ("06-texture", "Subtle multiscale texture", "Fine luma detail is gently reduced while broader structure is retained. This Gaussian-band prototype is inspired by the native detail pyramid, with different kernels.", ["Ricoh-AK000075", "Ricoh2-AK000017", "Ricoh-AK000142"], "texture", .7),
    ("07-iso-grain-monochrome", "ISO-aware grain and monochrome texture", "Added grain decreases at high ISO and where fine noise/detail is already present. Separate monochrome comparisons isolate the filter, tone and texture from the colour conversion.", ["Ricoh-AK000165", "Ricoh2-AK000020", "Ricoh2-AK000017"], "grain", .75),
    ("08-highlight-protection-raw", "Highlight protection from actual DNG headroom", "Compare the same decoded scene and exposure with hard output clipping or a smooth shoulder. This uses existing RAW headroom and does not simulate a recaptured lower sensor exposure.", ["Ricoh2-AK000011", "Ricoh-R0000001", "Ricoh2-AK000025"], "raw", .8),
    ("09-true-3d-lut", "Actual 3D finishing LUT", "A real trilinearly interpolated 33-cube combines density, blue, skin and highlight behaviour. Both 17-cube and 33-cube tables are supplied for reuse and fidelity evaluation.", ["Ricoh-AK000071", "Ricoh-AK000075", "Ricoh2-AK000008"], "lut", .5),
    ("10-validation-fidelity", "Validation: target versus native representation", "Compare the authored target with GR Mod's actual matrix/RGB-curve fitter and a quantized software reference. This measures representation error, not Ricoh-to-Fujifilm accuracy.", ["Ricoh-AK000071", "Ricoh-AK000075", "Ricoh2-AK000008"], "validation", .5),
    ("11-combinations", "Combined colour, highlights and texture", "Restrained combinations of the individually demonstrated operations. The supplied pipeline and strength sweeps make each result reproducible.", ["Ricoh-AK000075", "Ricoh-AK000071", "Ricoh2-AK000008", "Ricoh-AK000165"], "combined", .5),
]


def render_experiments(output: Path, only=None, representative_max=0) -> None:
    from color_ops import colour_density, blue_density, highlight_gamut, skin_tone_colour, build_lut, apply_lut, lut_target
    from texture_ops import film_texture, adaptive_grain, monochrome
    from raw_ops import decode_raw, render_baseline, render_protected, render_recipe, render_white_balance
    from gallery import write_gallery
    validate_output(output)
    records = json.loads((output / "00-source-selection/inventory.json").read_text(encoding="utf-8"))
    by_id = {r["id"]: r for r in records}
    used = sorted({identifier for _, _, _, ids, _, _ in EXPERIMENTS for identifier in ids})
    selected = [by_id[i] for i in used]
    source_hashes = {str(Path(p)): digest(Path(p)) for r in selected for p in [r["path"], r.get("raw")] if p}
    write_json(output / "00-source-selection/selection.json", {"sources": selected, "sha256_before": source_hashes,
               "selection": "Visual inspection of five contact sheets; portraits, saturated food/leaves/concert, sky/water, architecture, bright windows and high-ISO interior."})
    lut17, lut33 = build_lut(17), build_lut(33)
    lut_dir = output / "09-true-3d-lut"
    write_cube(lut_dir / "density-and-tone-17.cube", lut17)
    write_cube(lut_dir / "density-and-tone-33.cube", lut33)
    native_path = output / "10-validation-fidelity/native-fit.json"
    # The LUT was regenerated above; an existing fit may describe an older target.
    if only is None or "10-validation-fidelity" in only:
        print("Fitting experiment LUT with existing GR3X matrix/curve fitter...", flush=True)
        subprocess.run([str(ROOT / "node_modules/.bin/vite-node.cmd"), str(Path(__file__).with_name("fit_compare.ts")),
                        str(lut_dir / "density-and-tone-33.cube"), str(native_path)], cwd=ROOT, check=True)
    native = json.loads(native_path.read_text(encoding="utf-8")) if native_path.exists() else None
    native_lut = np.asarray(native["quantized_grid"], np.float32).reshape(33, 33, 33, 3) if native else None
    experiments = []
    crop_centers = {"Ricoh-AK000075": (.43, .24), "Ricoh-AK000142": (.48, .29), "Ricoh-AK000165": (.43, .35),
                    "Ricoh2-AK000008": (.53, .52), "Ricoh2-AK000011": (.6, .24), "Ricoh2-AK000020": (.49, .66)}

    def process(rgb, kind, strength, record):
        width = processing_frame_width(rgb)
        if kind == "density": return colour_density(rgb, strength)
        if kind == "blue": return blue_density(rgb, strength)
        if kind == "highlight": return highlight_gamut(rgb, strength)
        if kind == "skin": return skin_tone_colour(rgb, strength)
        if kind == "texture": return film_texture(rgb, strength, frame_width=width)
        if kind == "grain": return adaptive_grain(rgb, iso=record["iso"] or 100, strength=strength, seed=42, frame_width=width)
        if kind == "lut": return apply_lut(rgb, lut33)
        if kind == "combined":
            operations = {"colour_density": colour_density, "blue_density": blue_density,
                          "skin_tone_colour": skin_tone_colour, "highlight_gamut": highlight_gamut,
                          "film_texture": film_texture, "adaptive_grain": adaptive_grain}
            result = rgb
            for stage in combination_pipeline(record):
                name = stage["operation"]
                options = {"strength": stage["strength"]}
                if name in ("film_texture", "adaptive_grain"): options["frame_width"] = width
                if name == "adaptive_grain": options.update(iso=record["iso"] or 100, seed=42)
                result = operations[name](result, **options)
            return result
        raise ValueError(kind)

    for folder, title, description, identifiers, kind, strength in EXPERIMENTS:
        if only is not None and folder not in only:
            manifest_path = output / folder / "manifest.json"
            if manifest_path.exists(): experiments.append(json.loads(manifest_path.read_text(encoding="utf-8")))
            continue
        experiment = {"folder": folder, "title": title, "description": description,
                      "status": "offline prototype", "results": []}
        for index, identifier in enumerate(identifiers):
            record = by_id[identifier]
            print(f"{folder}: {identifier} ({'full resolution' if index == 0 and not representative_max else 'working resolution'})", flush=True)
            start = time.perf_counter()
            params = {"operation": kind}
            if kind in ("density", "blue", "highlight", "skin", "texture", "grain", "raw"):
                params["strength"] = strength
            if kind in ("raw", "recipe"):
                scene, metadata = decode_raw(record["raw"], half_size=index != 0)
                luminance = scene @ np.array([.2126, .7152, .0722], dtype=np.float32)
                exposure = float(np.clip(.18 / max(float(np.median(luminance)), .02), .75, 3))
                del luminance
                before = render_baseline(scene, exposure=exposure)
                if kind == "raw": after = render_protected(scene, exposure=exposure, strength=strength)
                else:
                    after = render_recipe(scene, exposure=exposure, warmth=.045, tint=-.008)
                    after = highlight_gamut(after, .3)
                    frame_width = processing_frame_width(after)
                    after = film_texture(after, .4, frame_width=frame_width)
                    wb_only = render_white_balance(scene, exposure=exposure, warmth=.045, tint=-.008)
                    params.update({"warmth": .045, "tint": -.008, "frame_width": frame_width,
                                   "frame_scale_basis": FRAME_SCALE_BASIS,
                                   "pipeline": [
                                       {"operation": "render_recipe", "exposure": exposure, "warmth": .045, "tint": -.008,
                                        "relative_wb_basis": "luminance-normalized diagonal gains in already camera-WB scene-linear sRGB; not Kelvin", "highlight_protection_strength": .7},
                                       {"operation": "highlight_gamut", "strength": .3},
                                       {"operation": "film_texture", "strength": .4, "frame_width": frame_width}]})
                params.update({"raw_decode": metadata, "common_exposure_multiplier": exposure,
                               "common_exposure_EV": math.log2(exposure),
                               "working_resolution": "Full demosaic" if index == 0 else "LibRaw half-size demosaic"})
                basis = "RAW: same camera-WB linear LibRaw scene, identical exposure before/after; no auto-brightness"
                del scene
            else:
                im = open_rgb(Path(record["path"]), (representative_max or None) if index == 0 else 2400)
                original = image_array(im)
                before = original
                if kind == "validation":
                    if native_lut is None: raise RuntimeError("Native fit is required for validation experiment")
                    before = lut_target(original); after = apply_lut(original, native_lut)
                    params["native_fit_metrics"] = native["metrics"]
                    params["quantization_basis"] = "Relative Standard normalization, identity Standard matrix; quantized software reference resampled on 33-cube. No camera calibration."
                    params.update({"target_pipeline": lut_target_pipeline(), "grid_size": 33,
                                   "interpolation": "trilinear", "native_fit_file": "10-validation-fidelity/native-fit.json"})
                    save_jpeg(im, output / folder / ("original.jpg" if index == 0 else f"original-{identifier}.jpg"))
                    basis = "BEFORE: direct authored target. AFTER: quantized native matrix/curve software approximation. Original JPEG also supplied."
                else:
                    after = process(before, kind, strength, record)
                    basis = "Camera JPEG as shot; source Image Control may already be stylized. Upright sRGB, identical encoding before/after."
                if kind in ("texture", "grain", "combined"):
                    params.update({"frame_width": processing_frame_width(before), "frame_scale_basis": FRAME_SCALE_BASIS})
                if kind == "grain": params.update({"seed": 42, "iso": record["iso"] or 100})
                if kind == "lut": params.update({"grid_size": 33, "interpolation": "trilinear", "target_pipeline": lut_target_pipeline()})
                if kind == "combined":
                    params["pipeline"] = combination_pipeline(record)
                    if any(stage["operation"] == "adaptive_grain" for stage in params["pipeline"]):
                        params.update({"seed": 42, "iso": record["iso"] or 100})
            result = export_result(output, folder, identifier, before, after, record, basis, params,
                                   representative=index == 0, crop_center=crop_centers.get(identifier, (.5, .5)))
            result["render_and_export_seconds"] = time.perf_counter() - start
            experiment["results"].append(result)
            if kind == "recipe":
                wb_params = {"operation": "white_balance_only", "warmth": .045, "tint": -.008,
                             "raw_decode": metadata, "common_exposure_multiplier": exposure,
                             "common_exposure_EV": math.log2(exposure),
                             "pipeline": [{"operation": "render_white_balance", "exposure": exposure, "warmth": .045, "tint": -.008,
                                           "relative_wb_basis": "luminance-normalized diagonal gains in already camera-WB scene-linear sRGB; not Kelvin",
                                           "highlight_rendering": "baseline hard clipping; no shoulder"}]}
                wb_result = export_result(output, folder, identifier + " · WB only", before, wb_only, record,
                                          "RAW: same camera-WB scene and exposure. AFTER adds only relative scene-linear WB; same baseline clipping and sRGB encoding, no shoulder or texture.",
                                          wb_params, subfolder=identifier + "-wb-only", crop_center=crop_centers.get(identifier, (.5, .5)))
                experiment["results"].append(wb_result)
                del wb_only
            if kind == "grain" and identifier == "Ricoh2-AK000020":
                width = processing_frame_width(before)
                fixed = adaptive_grain(before, iso=100, strength=strength, seed=42, frame_width=width)
                isolation_params = {"operation": "iso_grain_coordination", "strength": strength, "seed": 42,
                                    "before_iso_control": 100, "after_iso_actual": record["iso"] or 100,
                                    "same_noise_algorithm_and_seed": True, "frame_width": width, "frame_scale_basis": FRAME_SCALE_BASIS}
                isolation_result = export_result(output, folder, identifier + " · ISO coordination", fixed, after, record,
                                                "Same JPEG, algorithm, strength and seed. BEFORE: fixed ISO 100 grain control. AFTER: adaptive grain at actual ISO. This isolates ISO coordination, not native grain equivalence.",
                                                isolation_params, subfolder=identifier + "-iso-coordination", crop_center=crop_centers.get(identifier, (.5, .5)))
                experiment["results"].append(isolation_result)
                del fixed
            del after
            if index == 0 and kind in ("density", "blue", "highlight", "skin", "texture", "grain"):
                sweep = []
                preview = image_array(array_image(before).resize(tuple(result["preview_size"]), Image.Resampling.LANCZOS))
                for amount in (.25, .5, 1.0):
                    processed = process(preview, kind, amount, record)
                    name = f"strength-{int(amount * 100):03d}.jpg"
                    save_jpeg(array_image(processed), output / folder / name)
                    sweep_params = {"strength": amount, "file": name, "basis": "Processed at preview size; texture scale follows the full frame's long side."}
                    if kind in ("texture", "grain"):
                        sweep_params.update({"frame_width": processing_frame_width(preview), "frame_scale_basis": FRAME_SCALE_BASIS})
                    if kind == "grain": sweep_params.update({"seed": 42, "iso": record["iso"] or 100})
                    sweep.append(sweep_params)
                write_json(output / folder / "strength-sweep.json", sweep)
                del preview, processed
            if kind == "grain":
                grey = (before @ np.array([.299, .587, .114], np.float32))[..., None]
                grey = np.repeat(grey, 3, axis=-1)
                width = processing_frame_width(before)
                mono = monochrome(before, iso=record["iso"] or 100, strength=.65, seed=42, frame_width=width)
                result = export_result(output, folder, identifier + " · monochrome", grey, mono, record,
                                       "BEFORE: ordinary grayscale of same camera JPEG. AFTER: filter, tone, texture and ISO-aware grain.",
                                       {"operation": "monochrome", "strength": .65, "seed": 42, "iso": record["iso"] or 100,
                                        "frame_width": width, "frame_scale_basis": FRAME_SCALE_BASIS,
                                        "pipeline": [{"operation": "filtered_grayscale", "luma_weights": [.299 + .041 * .65, .587 + .013 * .65, .114 - .054 * .65]},
                                                     {"operation": "endpoint_preserving_cubic_tone", "coefficient": .48 * .65},
                                                     {"operation": "film_texture", "strength": .6 * .65, "frame_width": width},
                                                     {"operation": "adaptive_grain", "strength": .8 * .65, "iso": record["iso"] or 100, "seed": 42, "frame_width": width}]},
                                       subfolder=identifier + "-monochrome", crop_center=crop_centers.get(identifier, (.5, .5)))
                experiment["results"].append(result)
                del grey, mono
            if kind == "validation":
                for size, table in [(17, lut17), (33, lut33)]:
                    approximation = apply_lut(original, table)
                    result = export_result(output, folder, f"{identifier} · {size}-cube fidelity", before, approximation, record,
                                           f"BEFORE: direct target. AFTER: actual trilinear {size}-cube of same target.",
                                           {"operation": "lut_fidelity", "grid_size": size, "interpolation": "trilinear", "target_pipeline": lut_target_pipeline()}, subfolder=f"{identifier}-lut-{size}",
                                           crop_center=crop_centers.get(identifier, (.5, .5)))
                    experiment["results"].append(result)
                    del approximation
            del before
            if kind not in ("raw", "recipe"): del original
        write_json(output / folder / "manifest.json", experiment)
        experiments.append(experiment)
    changed = [p for p, sha in source_hashes.items() if digest(Path(p)) != sha]
    if changed: raise RuntimeError(f"Source hashes changed: {changed}")
    summary = {"created": "2026-10-31", "output": str(output), "experiments": experiments,
               "comparison_count": sum(len(x["results"]) for x in experiments), "selected_source_count": len(selected),
               "source_hashes_verified": source_hashes, "all_originals_used_unchanged": True,
               "limits": ["Offline prototypes, not verified firmware", "No measured Fujifilm reference captures", "RAW output rendering, not a new sensor exposure", "Desktop performance does not predict camera latency"]}
    write_json(output / "summary.json", summary)
    write_gallery(output, experiments, summary)
    overview(output, experiments)
    print(json.dumps({"folders": len(experiments), "comparisons": summary["comparison_count"], "sources_unchanged": not changed, "gallery": str(output / "index.html")}, indent=2), flush=True)


def overview(output: Path, experiments: list[dict]) -> None:
    width, row_height = 1600, 470
    sheet = Image.new("RGB", (width, len(experiments) * row_height), (18, 22, 27))
    draw = ImageDraw.Draw(sheet)
    for row, experiment in enumerate(experiments):
        if not experiment["results"]: continue
        result = experiment["results"][0]
        y = row * row_height
        draw.text((20, y + 10), experiment["title"], font=font(25), fill="white")
        for column, key in enumerate(("before_preview", "after_preview")):
            im = open_rgb(output / result[key], 780)
            im.thumbnail((780, 395), Image.Resampling.LANCZOS)
            x = column * 800 + (800 - im.width) // 2
            sheet.paste(im, (x, y + 65))
            draw.text((column * 800 + 20, y + 43), "BEFORE" if column == 0 else "AFTER", font=font(15), fill=(145, 163, 180))
    save_jpeg(sheet, output / "overview.jpg")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["inventory", "render"])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--only", help="Comma-separated experiment folder names")
    parser.add_argument("--representative-max", type=int, default=0, help="Zero keeps representative JPEG at full native resolution")
    args = parser.parse_args()
    validate_output(args.output)
    if args.command == "inventory": inventory(args.output)
    elif args.command == "render": render_experiments(args.output, set(args.only.split(",")) if args.only else None, args.representative_max)


if __name__ == "__main__":
    main()
