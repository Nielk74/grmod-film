"""Validate rendered comparisons and original hashes after the final run."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import unquote

from PIL import Image

from run import DEFAULT_OUTPUT, digest, write_json


def verify(output: Path) -> dict:
    output = output.resolve()
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    experiments = summary["experiments"]
    expected = {f"{n:02d}" for n in range(1, 12)}
    assert {e["folder"][:2] for e in experiments} == expected, "Missing experiment folders"
    comparisons = 0
    checked_files = set()
    def local(relative):
        path = (output / relative).resolve()
        assert output in path.parents, f"Path escapes output: {relative}"
        assert path.is_file(), f"Missing output: {relative}"
        checked_files.add(path)
        return path
    for experiment in experiments:
        assert experiment["results"], f"No comparisons: {experiment['folder']}"
        local(experiment["folder"] + "/manifest.json")
        for result in experiment["results"]:
            comparisons += 1
            assert result["source_path"] and result["basis"] and result["parameters"]
            assert result["metrics"]["mean_absolute_rgb_255"] > 0, "Unchanged experiment output"
            for key in ("before", "after", "before_preview", "after_preview", "comparison", "crop"):
                path = local(result[key])
                with Image.open(path) as im:
                    assert im.mode == "RGB", f"Unexpected image mode: {path}"
                    assert im.info.get("icc_profile"), f"Missing display profile: {path}"
                    if key in ("before", "after"):
                        assert list(im.size) == result["output_size"], f"Mismatch: {path}"
                    if key in ("before_preview", "after_preview"):
                        assert list(im.size) == result["preview_size"], f"Preview mismatch: {path}"
                    im.verify()
            params_path = Path(result["before"]).parent / "parameters.json"
            params = json.loads(local(params_path).read_text(encoding="utf-8"))
            assert params["parameters"] == result["parameters"], f"Parameter record differs: {params_path}"
    assert comparisons == summary["comparison_count"]
    for path, original_hash in summary["source_hashes_verified"].items():
        assert digest(Path(path)) == original_hash, f"Source modified: {path}"
    document = (output / "index.html").read_text(encoding="utf-8")
    assert "https://" not in document and "http://" not in document, "Unexpected remote asset or link"
    for reference in re.findall(r'(?:src|href)="([^"]+)"', document):
        if reference.startswith("#"): continue
        local(unquote(reference))
    report = {"passed": True, "experiment_folders": len(experiments), "comparisons": comparisons,
              "checked_output_files": len(checked_files), "source_hashes_unchanged": len(summary["source_hashes_verified"]),
              "checks": ["All eleven idea/combination folders", "Every comparison differs from its baseline",
                         "Matched dimensions and sRGB encoding", "Image file verification", "Exact parameter provenance",
                         "Local gallery links and no remote assets", "Original SHA-256 hashes unchanged"]}
    write_json(output / "verification.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(verify(args.output), indent=2))
