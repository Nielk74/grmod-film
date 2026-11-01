"""Regenerate the approved Gold exposure/print targets from the pinned stock data.

SPDX-License-Identifier: GPL-2.0-only
Stock profiles and generated LUTs: CC BY-SA 4.0; see SPEKTRAFILM_LICENSE.txt.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import colour
import numpy as np
from scipy.optimize import brentq, least_squares

HERE = Path(__file__).resolve().parent
MODEL = HERE.parent / "film_datasheet_v3.py"
HEADER = (
    "# Derived from spektrafilm by Andrea Volpato\n"
    "# https://github.com/andreavolpato/spektrafilm\n"
    "# CC BY-SA 4.0. Modified by Codex for Antoine, 2026-11-01.\n"
    "# Simplified negative exposure + common-scalar print-time experiment. See manifest.json.\n"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path, help="A new output directory")
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists():
        parser.error("--out must not exist; approved assets are never overwritten")

    approved = json.loads((HERE / "approved.json").read_text(encoding="utf-8"))
    for filename, expected in approved["generation_inputs"].items():
        # Existing repository source may use CRLF in a Windows checkout.
        actual = hashlib.sha256((HERE / filename).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        if actual != expected:
            raise ValueError(f"Generation input changed: {filename}")

    spec = importlib.util.spec_from_file_location("grmod_exposure_model", MODEL)
    model = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(model)
    calibration = json.loads((HERE / "calibration.json").read_text(encoding="utf-8"))
    inverse = model.standard_inverse(np.array(calibration["theta"], dtype=float))
    anchor = colour.XYZ_to_sRGB(colour.Lab_to_XYZ([50.0, 0.0, 0.0]))[None, :]
    anchor_scene = inverse(anchor)
    axis = np.linspace(0, 1, 33)
    grid = np.stack(np.meshgrid(axis, axis, axis, indexing="ij"), -1)
    scene = inverse(grid.reshape(-1, 3))
    film = model.Film(
        model.load(HERE / "profiles/kodak_gold_200.json"),
        model.load(HERE / "profiles/kodak_portra_endura.json"),
        "D55", 0.30, float(anchor_scene.mean()),
    )

    def lab(rgb):
        return colour.XYZ_to_Lab(colour.sRGB_to_XYZ(rgb))

    def neutral_error(gain):
        film.print_gain = gain
        return lab(film(anchor_scene))[0] - [50, 0, 0]

    balance = least_squares(neutral_error, film.print_gain.copy(), xtol=1e-12, ftol=1e-12, gtol=1e-12)
    if not balance.success:
        raise RuntimeError(balance.message)
    baseline_gain = balance.x.copy()
    outputs = []
    for name, ev in [("baseline", 0.0), ("candidate", 2.0)]:
        film.exposure = np.full(3, ev * np.log10(2))

        def lightness_error(common_log10):
            film.print_gain = baseline_gain + common_log10
            return float(lab(film(anchor_scene))[0, 0] - 50)

        compensation = brentq(lightness_error, -4, 4, xtol=1e-12)
        film.print_gain = baseline_gain + compensation
        gray = lab(film(anchor_scene))[0]
        filtration_residual = float(np.max(np.abs(
            (film.print_gain[:, None] - film.print_gain[None, :])
            - (baseline_gain[:, None] - baseline_gain[None, :])
        )))
        if abs(gray[0] - 50) > 1e-7 or filtration_residual > 1e-12:
            raise ValueError("Exposure experiment changed its gray/filtration constraints")
        cube = HEADER + model.cube_text(f"kodak_gold_200_{ev:+.0f}EV", film(scene).reshape(33, 33, 33, 3))
        digest = hashlib.sha256(cube.encode("utf-8")).hexdigest()
        expected = approved["targets"][name]["sha256"]
        if digest != expected:
            raise ValueError(f"{name}: generated target differs from the approved asset ({digest})")
        outputs.append((name, cube, {
            "id": name, "negative_exposure_ev": ev,
            "common_print_compensation_ev": compensation / np.log10(2),
            "continuous_middle_gray_Lab": gray.tolist(),
            "filtration_pairwise_residual": filtration_residual, "sha256": digest,
        }))

    out.mkdir(parents=True)
    for name, cube, _ in outputs:
        (out / f"{name}-target.cube").write_text(cube, encoding="utf-8", newline="\n")
    (out / "manifest.json").write_text(json.dumps({
        "experiment": approved["experiment"], "attribution": approved["attribution"],
        "variants": [row for _, _, row in outputs],
    }, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps([row for _, _, row in outputs], indent=2))


if __name__ == "__main__":
    main()
