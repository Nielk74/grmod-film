"""Safety and comparison-integrity checks for the experiment exporter."""
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import run


def test_output_cannot_write_into_either_source_tree(tmp_path):
    source = tmp_path / "originals"
    source.mkdir()
    with pytest.raises(ValueError, match="source"):
        run.validate_output(source / "experiments", [source])
    with pytest.raises(ValueError, match="source"):
        run.validate_output(source, [source])
    run.validate_output(tmp_path / "results", [source])


def test_comparison_refuses_different_dimensions():
    with pytest.raises(ValueError, match="dimensions"):
        run.side_by_side(Image.new("RGB", (20, 30)), Image.new("RGB", (30, 20)))


def test_metrics_distinguish_identity_and_changed_pixels():
    rgb = np.full((8, 8, 3), 0.5, np.float32)
    assert run.result_metrics(rgb, rgb)["mean_absolute_rgb_255"] == 0
    changed = rgb.copy()
    changed[0, 0] += 0.1
    assert run.result_metrics(rgb, changed)["changed_pixel_fraction"] == pytest.approx(1 / 64)


def test_export_keeps_source_bytes_and_matching_comparison_sizes(tmp_path):
    source = tmp_path / "input.jpg"
    Image.new("RGB", (80, 60), (80, 120, 150)).save(source)
    original_hash = run.digest(source)
    before = run.image_array(run.open_rgb(source))
    after = np.clip(before * 0.95, 0, 1)
    output = tmp_path / "output"
    result = run.export_result(output, "01-test", "sample", before, after,
                               {"path": str(source), "id": "sample", "iso": 100},
                               "Camera JPEG as shot", {"strength": 0.5}, representative=True)
    assert run.digest(source) == original_hash
    assert result["output_size"] == [80, 60]
    with Image.open(output / result["before"]) as left, Image.open(output / result["after"]) as right:
        assert left.size == right.size == (80, 60)
    assert (output / result["comparison"]).exists()
    assert (output / "01-test" / "parameters.json").exists()


def test_processing_scale_is_identical_for_rotated_portrait_and_landscape():
    helper = getattr(run, "processing_frame_width", None)
    assert callable(helper), "processing_frame_width must declare the rotation-independent scale"
    landscape = np.zeros((16, 24, 3), np.float32)
    portrait = landscape.transpose(1, 0, 2)
    assert helper(landscape) == helper(portrait) == 24


@pytest.mark.parametrize("identifier, expected", [
    ("Ricoh-AK000075", [("colour_density", .3), ("blue_density", .25), ("skin_tone_colour", .35), ("highlight_gamut", .25), ("film_texture", .45), ("adaptive_grain", .15)]),
    ("Ricoh-AK000071", [("colour_density", .4), ("blue_density", .55), ("skin_tone_colour", .2), ("highlight_gamut", .2), ("film_texture", .2)]),
    ("Ricoh2-AK000008", [("colour_density", .6), ("skin_tone_colour", .15), ("highlight_gamut", .3), ("film_texture", .2)]),
    ("Ricoh-AK000165", [("skin_tone_colour", .2), ("highlight_gamut", .15), ("film_texture", .3), ("adaptive_grain", .15)]),
])
def test_source_specific_combination_pipeline(identifier, expected):
    helper = getattr(run, "combination_pipeline", None)
    assert callable(helper), "combination_pipeline must provide both execution and provenance"
    stages = helper({"id": identifier})
    assert [(stage["operation"], stage["strength"]) for stage in stages] == expected


def test_combination_export_records_executed_pipeline_and_scale(tmp_path, monkeypatch):
    import json

    helper = getattr(run, "combination_pipeline", None)
    assert callable(helper), "combination_pipeline must be implemented"
    source = tmp_path / "portrait.jpg"
    rgb = np.random.default_rng(4).integers(20, 230, (24, 16, 3), dtype=np.uint8)
    Image.fromarray(rgb).save(source)
    record = {"id": "Ricoh-AK000075", "path": str(source), "raw": None, "iso": 100}
    output = tmp_path / "results"
    run.write_json(output / "00-source-selection/inventory.json", [record])
    monkeypatch.setattr(run, "EXPERIMENTS", [("11-combinations", "Combined", "Synthetic regression fixture", [record["id"]], "combined", .5)])
    run.render_experiments(output, only={"11-combinations"})
    result = json.loads((output / "11-combinations/parameters.json").read_text(encoding="utf-8"))
    parameters = result["parameters"]
    assert parameters["pipeline"] == helper(record)
    assert parameters["frame_width"] == 24
    assert "max" in parameters["frame_scale_basis"]
    assert "strength" not in parameters


def test_high_iso_export_isolates_iso_with_same_seed_strength_and_frame(tmp_path, monkeypatch):
    import json

    source = tmp_path / "high-iso.jpg"
    Image.new("RGB", (24, 16), (110, 100, 90)).save(source)
    record = {"id": "Ricoh2-AK000020", "path": str(source), "raw": None, "iso": 5000}
    output = tmp_path / "results"
    run.write_json(output / "00-source-selection/inventory.json", [record])
    monkeypatch.setattr(run, "EXPERIMENTS", [("07-iso-grain-monochrome", "Grain", "Synthetic regression fixture", [record["id"]], "grain", .75)])
    run.render_experiments(output, only={"07-iso-grain-monochrome"})
    manifest = json.loads((output / "07-iso-grain-monochrome/manifest.json").read_text(encoding="utf-8"))
    results = manifest["results"]
    assert len(results) == 3
    control = next(item for item in results if item["parameters"]["operation"] == "iso_grain_coordination")
    parameters = control["parameters"]
    assert parameters["before_iso_control"] == 100 and parameters["after_iso_actual"] == 5000
    assert parameters["seed"] == 42 and parameters["strength"] == .75
    assert parameters["frame_width"] == 24 and parameters["same_noise_algorithm_and_seed"]
    assert control["output_size"] == [24, 16]
    assert (output / control["crop"]).exists()
    mono = next(item for item in results if item["parameters"]["operation"] == "monochrome")
    stages = mono["parameters"]["pipeline"]
    assert stages[-2]["strength"] == pytest.approx(.39)
    assert stages[-1]["strength"] == pytest.approx(.52)
