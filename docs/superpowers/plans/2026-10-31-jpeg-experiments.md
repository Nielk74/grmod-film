# JPEG experiments implementation plan

> For agentic workers: implement independent experiment modules and review the integrated outputs. The user explicitly selected subagents and autonomous execution without questions.

**Goal:** Implement every proposed JPEG improvement as a reproducible offline experiment, each with real before/after photos, then evaluate useful combinations.

**Architecture:** Add an isolated Python experiment tool under `tools/jpeg_experiments`. Float32 RGB arrays use display sRGB [0,1], except explicitly named scene-linear RAW functions. Original files are read only. Results go to `C:/Users/Antoine/Pictures/GRMod-JPEG-Experiments-2026-10-31`; the existing application and firmware behaviour stay outside this experiment's scope.

**Tech stack:** Python 3.12, NumPy, Pillow, SciPy, rawpy/LibRaw; existing TypeScript colour fitter for native-representation comparisons when feasible.

**Spec:** The user's request and preceding research: colour density; independent blue density; highlight shoulder/gamut handling; skin protection and brightness-dependent colour; complete recipes/WB; native-inspired texture; ISO-aware grain/monochrome; RAW highlight protection; actual 3D LUT; validation of approximation fidelity and useful combinations. Each needs a folder and at least one before/after.

## Global constraints

- No modification, overwrite, move or deletion of original photos. No upload of personal photos.
- Leave existing `tools/directflash/directflash.c` changes untouched.
- Use explicit UTF-8 for text, native Windows paths and shell commands.
- Offline experiments must never be described as camera-verified firmware or measured Fujifilm reproductions.
- Record source path, rendering basis, parameter values, output dimensions and actual comparisons in JSON.
- Before/after must use the same source, crop, orientation, scale and encoding settings. RAW experiments use a declared common RAW baseline.
- Retain reproducible scripts; generated photos belong in the output directory, not Git.
- User authorization supersedes skill confirmation gates: execute without asking questions.

## Review focus

- Achromatic ramps remain neutral under selective colour operations and produce finite bounded outputs.
- Density masks are smooth at colour boundaries; skin safeguards cover low and moderate chroma.
- RAW headroom is genuinely decoded from DNG, not invented from JPEG or labelled as recapture.
- Texture and grain comparisons include 100% crops at a documented pixel scale.
- Combined effects remain reproducible and include individual operations for attribution.

## File manifest

- `tools/jpeg_experiments/color_ops.py` and `test_color_ops.py`: selective density, gamut/shoulder, skin/brightness colour, LUT interpolation.
- `tools/jpeg_experiments/texture_ops.py` and `test_texture_ops.py`: scale-dependent detail, ISO-aware grain, monochrome.
- `tools/jpeg_experiments/raw_ops.py` and `test_raw_ops.py`: actual DNG decoding, WB variants, common RAW baseline and highlight-protected rendering.
- `tools/jpeg_experiments/run.py`: source inventory, selection, deterministic experiments, exports and metadata.
- `tools/jpeg_experiments/gallery.py`: local comparison viewer with matched-size before/after views, contact sheets and crop panels.
- `tools/jpeg_experiments/test_pipeline.py`: originals protected, completeness, matching before/after dimensions, output validation.
- `tools/jpeg_experiments/README.md` and `requirements.txt`: reproducible commands and limits.
- Optional `tools/jpeg_experiments/fit_compare.ts`: exercise existing GR3X fitter independently of firmware.

## Tasks

### Task 1: Inventory and selection (controller)
- [x] Inventory photos and EXIF; create source contact sheets and select diverse real scenes.
- [x] Create isolated Python environment and dependencies.

### Task 2: Colour module (subagent)
- [x] Implement float32, non-mutating functions `colour_density(rgb, strength=0.6)`, `blue_density(rgb, strength=0.5)`, `highlight_gamut(rgb, strength=0.5)`, `skin_tone_colour(rgb, strength=0.5)`.
- [x] Implement `build_lut(size=17)` / `apply_lut(rgb, lut)` with documented grid ordering and a useful brightness/hue/chroma-dependent transform.
- [x] Verify neutrals, smooth masks, boundedness, highlight ordering and identity LUT interpolation on synthetic inputs.

### Task 3: Texture module (subagent, disjoint files)
- [x] Implement `film_texture(rgb, strength=0.5)`, `adaptive_grain(rgb, iso=100, strength=0.5, seed=42)`, `monochrome(rgb, iso=100, strength=0.5, seed=42)`.
- [x] Preserve neutral colour/luma behaviour, deterministic grain and reduced added grain at high ISO; avoid claiming exact native clarity/NR equivalence.
- [x] Verify constants, no mutation, finite bounded outputs, deterministic seed and grain reduction with ISO.

### Task 4: RAW module (subagent, disjoint files)
- [x] Implement `decode_raw(path, half_size=False, wb_mode='camera') -> (linear_rgb, metadata)` retaining usable decoded highlight headroom with documented LibRaw exposure scaling.
- [x] Implement `render_baseline(linear_rgb, exposure=1.0)`, `render_protected(linear_rgb, exposure=1.0, strength=0.7)`, `render_recipe(linear_rgb, exposure=1.0, warmth=0.06, tint=0.0)`.
- [x] Baseline/after use the same decoded scene and documented WB basis; do not imply the experiment changes the original capture.
- [x] Test neutral response, headroom separation, monotonicity and finite bounded output.

### Task 5: Render and compare (controller)
- [x] Generate folders 01-colour-density, 02-blue-density, 03-highlight-gamut, 04-skin-and-tone-colour, 05-complete-recipes, 06-texture, 07-iso-grain-monochrome, 08-highlight-protection-raw, 09-true-3d-lut, 10-validation-fidelity, 11-combinations.
- [x] Each folder includes matched before/after, a side-by-side, parameters/metrics, and at least one full-resolution representative; texture folders include crops.
- [x] Render multiple appropriate sources where possible; add strength variants for representative photos.
- [x] Compare actual LUT outputs and ideal targets; attempt native matrix/curve fitting with the repository model.
- [x] Build a local index gallery with per-experiment navigation and before/after controls.

### Task 6: Review and delivery
- [x] Run experiment tests and existing core suite; report skipped/private-fixture checks accurately.
- [x] Visually inspect every experiment's representative and combined result; tune or reject visibly poor combinations.
- [x] Independent subagent review of provenance, comparisons, algorithms and completeness.
- [x] Validate manifests/files and verify original file hashes remain unchanged.
- [x] Deliver output folder, gallery, representative images and candid findings. Complete the goal only after all outputs exist and checks pass.

## Completion evidence

- 11 experiment folders, 47 matched comparisons, 18 strength variants, 4 cumulative combination sheets, 12 selected scenes.
- All 19 selected JPEG/DNG SHA-256 hashes unchanged.
- 78 focused experiment tests passed with real-DNG integration enabled.
- Core suite: 203 tests passed, 197 skipped; private firmware fixtures are absent.
- Output verification: 347 local files checked; gallery before/after/slider and mobile layout checks passed.
- All 4 combined results reproduced with identical decoded JPEG pixels from their recorded stages.
- Final native fit refreshed after fixing stale-report reuse; fresh refit matches stored grids and metrics.
- Additional retained tools: stage_compare.py, verify_outputs.py, test_refit.py and findings.json.
- Files are offline prototypes; no camera firmware integration or measured Fujifilm match is claimed.
