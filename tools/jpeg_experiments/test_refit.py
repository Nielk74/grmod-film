"""A regenerated LUT must never be paired with a stale native-fit report."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import run


@pytest.mark.parametrize("only, needs_fit", [(None, True), ({"10-validation-fidelity"}, True), ({"11-combinations"}, False)])
def test_existing_native_report_is_refreshed_when_its_experiment_is_requested(tmp_path, monkeypatch, only, needs_fit):
    source = tmp_path / "originals" / "image.jpg"
    source.parent.mkdir()
    Image.new("RGB", (24, 16), (70, 120, 160)).save(source)
    record = {"id": "Ricoh-AK000075", "path": str(source), "raw": None, "iso": 100}
    output = tmp_path / "results"
    run.write_json(output / "00-source-selection/inventory.json", [record])
    folder = "10-validation-fidelity" if needs_fit else "11-combinations"
    kind = "validation" if needs_fit else "combined"
    monkeypatch.setattr(run, "EXPERIMENTS", [(folder, "Regression fixture", "Synthetic regression", [record["id"]], kind, .5)])
    report_path = output / "10-validation-fidelity/native-fit.json"
    fixture = {"quantized_grid": np.zeros((33, 33, 33, 3), np.float32).ravel().tolist(), "metrics": {"revision": "stale"}}
    run.write_json(report_path, fixture)
    calls = []

    def fresh_fit(command, **kwargs):
        calls.append(command)
        fixture["metrics"] = {"revision": "fresh"}
        run.write_json(report_path, fixture)

    monkeypatch.setattr(run.subprocess, "run", fresh_fit)
    run.render_experiments(output, only=only)
    assert len(calls) == int(needs_fit)
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved["metrics"]["revision"] == ("fresh" if needs_fit else "stale")
