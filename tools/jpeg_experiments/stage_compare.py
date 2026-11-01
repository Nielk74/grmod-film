"""Rebuild each combined result step by step, checking exact reproducibility."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from color_ops import colour_density, blue_density, highlight_gamut, skin_tone_colour
from texture_ops import film_texture, adaptive_grain
from gallery import write_gallery
from run import DEFAULT_OUTPUT, open_rgb, image_array, array_image, save_jpeg, font, write_json


def make_stages(output: Path) -> list[dict]:
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    combined = next(e for e in summary["experiments"] if e["folder"] == "11-combinations")
    reports = []
    functions = {"colour_density": colour_density, "blue_density": blue_density,
                 "highlight_gamut": highlight_gamut, "skin_tone_colour": skin_tone_colour,
                 "film_texture": film_texture, "adaptive_grain": adaptive_grain}
    for result in combined["results"]:
        relative = Path("11-combinations/stages") / result["source_id"]
        dest = output / relative
        dest.mkdir(parents=True, exist_ok=True)
        image = open_rgb(Path(result["source_path"]), max(result["output_size"]))
        rgb = image_array(image)
        assert list(image.size) == result["output_size"]
        snapshots = [("Original", image.copy())]
        stages = result["parameters"]["pipeline"]
        for index, stage in enumerate(stages, 1):
            op, amount = stage["operation"], stage["strength"]
            kwargs = {"strength": amount}
            if op in ("film_texture", "adaptive_grain"):
                kwargs["frame_width"] = result["parameters"]["frame_width"]
            if op == "adaptive_grain":
                kwargs.update(iso=result["iso"] or 100, seed=42)
            rgb = functions[op](rgb, **kwargs)
            im = array_image(rgb)
            if index == len(stages):
                save_jpeg(im, dest / "final-stage.jpg")
                with Image.open(dest / "final-stage.jpg") as stage_image, Image.open(output / result["after"]) as final_image:
                    assert np.array_equal(np.asarray(stage_image), np.asarray(final_image)), "Combination does not reproduce its recorded stages"
            im.thumbnail((720, 720), Image.Resampling.LANCZOS)
            snapshots.append((f"{index}. + {op.replace('_', ' ')} ({amount:g})", im))
        snapshots[0][1].thumbnail((720, 720), Image.Resampling.LANCZOS)
        cell_w, cell_h, cols = 760, 790, 2
        rows = (len(snapshots) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), (18, 22, 27))
        draw = ImageDraw.Draw(sheet)
        for index, (label, im) in enumerate(snapshots):
            x, y = (index % cols) * cell_w, (index // cols) * cell_h
            draw.text((x + 20, y + 12), label, font=font(21), fill=(225, 231, 238))
            sheet.paste(im, (x + (cell_w - im.width) // 2, y + 52 + (720 - im.height) // 2))
        save_jpeg(sheet, dest / "stage-sheet.jpg")
        record = {"source_id": result["source_id"], "pipeline": stages,
                  "output_size": result["output_size"], "final_stage_decoded_pixels_identical_to_after_jpeg": True,
                  "comparison_basis": "Decoded pixels; ICC profile creation timestamps can differ between Python processes.",
                  "stage_sheet": (relative / "stage-sheet.jpg").as_posix()}
        write_json(dest / "stages.json", record)
        result["stage_sheet"] = record["stage_sheet"]
        reports.append(record)
        print(f"Reproduced {result['source_id']}: {len(stages)} stages, final JPEG pixels identical", flush=True)
    write_json(output / "11-combinations/manifest.json", combined)
    write_json(output / "summary.json", summary)
    write_json(output / "11-combinations/stages.json", reports)
    write_gallery(output, summary["experiments"], summary)
    return reports


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    make_stages(args.output)
