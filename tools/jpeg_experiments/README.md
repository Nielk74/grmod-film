# JPEG processing experiments

Reproducible offline comparisons for the JPEG-improvement research of 31 October 2026. These tools do not patch firmware or change the application's processing. They use deterministic numerical image processing; no generative retouching or photo upload is involved.

The user's original files in `C:/Users/Antoine/Pictures/Ricoh` and `C:/Users/Antoine/Pictures/Ricoh2` are read only. The default results directory is `C:/Users/Antoine/Pictures/GRMod-JPEG-Experiments-2026-10-31`. The tool refuses output inside either source directory and verifies SHA-256 hashes for every selected JPEG/DNG after rendering.

## Reproduce on Windows

From the repository root in PowerShell:

```powershell
python -m venv scratch/jpeg-experiments-env
& scratch/jpeg-experiments-env/Scripts/python.exe -m pip install -r tools/jpeg_experiments/requirements.txt
& scratch/jpeg-experiments-env/Scripts/python.exe tools/jpeg_experiments/run.py inventory
& scratch/jpeg-experiments-env/Scripts/python.exe tools/jpeg_experiments/run.py render
& scratch/jpeg-experiments-env/Scripts/python.exe tools/jpeg_experiments/stage_compare.py
& scratch/jpeg-experiments-env/Scripts/python.exe tools/jpeg_experiments/verify_outputs.py
```

The native-representation experiment invokes the repository's existing `node_modules/.bin/vite-node.cmd`. Install the project's normal npm dependencies first if they are absent. The selected photographs are identified explicitly in `run.py`; filenames refer to this local research collection.

Open `index.html` in the results directory. It works directly from local files and contains no remote assets or tracking. A local HTTP server can also serve that directory.

To rerender one experiment, pass its complete folder name:

```powershell
& scratch/jpeg-experiments-env/Scripts/python.exe tools/jpeg_experiments/run.py render --only 02-blue-density
```

`--representative-max 1600` is a faster draft mode for JPEG representatives. Omit it for native-resolution representatives. Additional scene examples are usually processed at 2400 pixels on the long side. RAW representatives use full AHD demosaicing; additional RAW examples use LibRaw's half-size decode. Every result records its exact dimensions and basis.

## Outputs

Each idea has a folder containing `before.jpg`, `after.jpg`, `comparison.jpg`, `crop-100-percent.jpg`, `parameters.json` and `manifest.json`. Additional examples live under `examples/`. Browser previews are capped at 2400 pixels; the main before/after files retain the representative's native decoded size. Whole-image comparison panels are scaled identically. The 100% crop is extracted after the full render, never rerendered as an independent crop.

Folders 01-04 test selective colour, blue density, highlight/gamut handling and skin/brightness colour individually. Folder 05 tests a coordinated scene-linear RAW recipe. Folders 06-07 test detail and ISO-aware grain/monochrome. Folder 08 tests highlight rendering from actual DNG headroom. Folder 09 includes actual 17-cube and 33-cube LUTs. Folder 10 compares the target with LUT interpolation and the existing native matrix/curve fitter. Folder 11 tests combinations.

Folder 05 also includes WB-only pairs. Folder 07 includes a fixed-ISO versus actual-ISO grain pair on the same photograph, using the same strength and noise seed. Texture scale uses the long side of each selected 3:2 full frame, so EXIF rotation does not change the spatial scale.

`stage_compare.py` rebuilds each combined image from its exact recorded stages, verifies that its final decoded JPEG pixels match the exported result, and adds cumulative stage sheets to the gallery. `verify_outputs.py` validates all eleven folders, local gallery links, matching dimensions, parameter records, image encoding and original hashes. The verdicts in `findings.json` record both promising and underperforming experiments. The gallery uses an output-directory copy of that file when present.

`summary.json` links every comparison and records hashes. `00-source-selection` contains the full source inventory, selection provenance and contact sheets. JPEGs are encoded with identical quality 97, 4:4:4 and embedded sRGB profiles on both sides. Source GPS and other EXIF fields are not copied into processed files.

## Interpretation limits

- The photos' existing camera Image Control can already be stylized. JPEG finishing experiments operate on those actual camera JPEGs; they are not guaranteed Standard input.
- These are authored aesthetic prototypes, not measured Fujifilm simulations. No Fujifilm reference captures were supplied.
- RAW comparisons use one shared LibRaw camera-WB decode and a common exposure multiplier recorded in the parameters. The baseline clips output headroom; the protected version applies a smooth shoulder. This uses information in the original DNG and does not claim a new capture exposure, expanded sensor range or recovery of sensor-clipped data.
- Recipe warmth/tint are relative scene-linear gains after camera WB, not calibrated Kelvin or camera sensor WB settings.
- Texture uses Gaussian difference bands inspired by the existing native clarity stage; it does not reproduce native interpolation or noise reduction. The grain model is also a separate prototype with ISO/noise/detail coordination.
- The fitter comparison uses GR3X software modelling and explicit relative Standard normalization. Its integer-format approximation and sampled comparison LUT are documented in `native-fit.json`; it is not a camera calibration or exact ISP emulation.
- Numerical before/after differences and clipping counts describe a change, not an objective quality improvement. Desktop timings do not establish camera processing speed.

## Verification

```powershell
$env:GRMOD_TEST_DNG = 'C:/Users/Antoine/Pictures/Ricoh2/AK000001.DNG'
& scratch/jpeg-experiments-env/Scripts/python.exe -m pytest tools/jpeg_experiments -q
npm test
```

The RAW integration test is skipped when `GRMOD_TEST_DNG` is absent; the array-based tests still run. Run this focused Python suite rather than bare repository `pytest`, which also collects unrelated firmware/reference tools with separate dependencies.

The implementation plan is `docs/superpowers/plans/2026-10-31-jpeg-experiments.md`. Numerical colour and RAW probe evidence is retained in `color_notes.json` and `raw_notes.json`.
