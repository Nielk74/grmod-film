# Gold 200: negative exposure and compensated printing

Direction 3, accepted by Antoine on 2026-11-01. This saves the exact approved
research look: Kodak Gold 200 on Portra Endura, negative exposure **+2 EV**, then
a common print-exposure adjustment of **+1.141733 EV** to restore middle gray
to L*=50. Chromatic printer filtration remains fixed. Highlights become denser
and warmer; the middle gray also becomes warmer.

The baseline is the simplified spectral model at 0 EV. It differs from the
authored Gold preset in the film pack. This folder is a reusable experiment;
the film-pack build does not load it automatically.

## Saved assets

- `targets/baseline-target.cube` and `targets/candidate-target.cube`: exact
  approved 33³ Standard-display-input target LUTs, with red fastest in cube text.
- `approved.json`: exact fitted M1/RGB-curve/P2 parameters, measured errors,
  hashes of the accepted float32 previews, controls and source attribution.
- `profiles/`: two unmodified pinned spektrafilm data files.
- `calibration.json`: numerical Standard-inverse calibration coefficients from
  the existing 37-pair study. Source photographs and camera firmware are external.

Targets and their camera-model approximations are different outputs. To reproduce
the before/after images that were accepted, use the saved fitted parameters via
`reproduce.ts`; importing the full candidate target in another grading system can
produce a different result.

## Reproduce from the repository root

With project npm dependencies installed:

```powershell
& 'node_modules/.bin/vite-node.cmd' --script 'tools/jpeg_experiments/exposure_print/reproduce.ts' 'scratch/exposure-approved-preview'
```

This checks both target hashes, regenerates all three accepted grids, checks their
SHA-256 identities and independently recomputes the full-cube own-target errors.
Output is little-endian float32 sRGB, shape `[33,33,33,3]`, blue fastest.
Use trilinear interpolation over camera Standard JPEG RGB for the original preview.
Output directories must be new. Append `--refit` to rerun the existing fitter
(`post: true`, `endGreyWeight: 24`) and require the same accepted grid hashes.

To regenerate the physical targets, install `requirements.txt` in a Python 3.12
environment, then run:

```powershell
python 'tools/jpeg_experiments/exposure_print/generate.py' --out 'scratch/exposure-approved-targets'
```

The generator checks stock data, calibration and model hashes (normalized LF) before computing
the targets, and verifies the resulting assets against the approved targets.
Exact identity was verified with the pinned environment; another numerical
runtime can fail the strict check if its numerical results differ.

## Controls and measured limits

Scene illuminant D55; print illuminant CIE A; D50 viewing with Bradford adaptation
to display sRGB; modeled interlayer amount 0.30. At 0 EV only, print gains are
balanced to Lab `[50,0,0]` at the calibrated Standard middle-gray input. For +2 EV,
only one scalar is added to all three print gains. There is no per-photo balance,
push/pull development, new detail recovery, grain or halation.

The continuous target holds L*=50. Cube interpolation and the camera fit introduce
residuals: fitted middle-gray L* is **49.2263 baseline / 49.5778 candidate**. The
camera fit remains an unquantized software model, with no on-camera validation.

Each fit error compares the rendering against **its own different target**:

| ΔE00 | Baseline | Candidate |
|---|---:|---:|
| Photographic sample mean, 18,000 samples | 1.0190 | 0.9419 |
| Full 33³ cube mean | 5.4154 | 4.3192 |
| Full cube p95 | 18.5551 | 19.6846 |
| Full cube maximum | 33.6747 | 42.1978 |

The candidate's larger tail errors can produce severe departures in saturated
or extreme regions. The photo-sample error decrease describes representability;
it does not measure aesthetic quality. The simplified spectral model and its
calibrated JPEG inverse do not establish real-film accuracy or recover clipped
capture data. The look is saved because of the accepted visual preference.

## Attribution and licensing

Stock data: Andrea Volpato, [spektrafilm](https://github.com/andreavolpato/spektrafilm),
pinned at `3bb2c2d2801ff68b92019cf1dbcbb133d60832bc`. Profiles, target LUTs and
derived fitted look parameters/previews remain **CC BY-SA 4.0**; see the unmodified
`SPEKTRAFILM_LICENSE.txt` and `CHANGELOG.txt`. Local script source follows the
repository's GPL-2.0-only license. No upstream implementation code was imported.
