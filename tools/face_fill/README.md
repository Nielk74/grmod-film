# Face fill light and skin keeper experiment

This offline experiment uses a real local YuNet face detector, soft oval masks,
and a broad skin-colour gate. It neither patches firmware nor uploads photos.
The user originals under `C:/Users/Antoine/Pictures/Ricoh` and `Ricoh2` are read
only. Generated output contains no source EXIF, GPS, date or camera serial.

From this worktree's root, in PowerShell:

```powershell
python -m venv scratch/face-fill-env
& scratch/face-fill-env/Scripts/python.exe -m pip install -r tools/face_fill/requirements.txt
npm ci
& tools/face_fill/download_model.ps1
& node_modules/.bin/vite-node.cmd tools/face_fill/export_films.ts -- scratch/face-fill/models
& scratch/face-fill-env/Scripts/python.exe tools/face_fill/audit.py
& scratch/face-fill-env/Scripts/python.exe -m pytest tools/face_fill -q
& scratch/face-fill-env/Scripts/python.exe tools/face_fill/run.py
& scratch/face-fill-env/Scripts/python.exe tools/face_fill/verify_outputs.py --record
& scratch/face-fill-env/Scripts/python.exe tools/face_fill/verify_outputs.py
```

`run.py` defaults to the native resolution after EXIF rotation, with six real
scenes: daylight, partly occluded/window, warm night, another daylight portrait,
a multi-person night scene, and warm food/tableware with no visible face. The first three names
are `R0000030`, `R0000005`, and `AK000164`. For a draft use `--max-side 1600`;
the manifest then explicitly labels the crop scale as non-native. `--only`
accepts source-relative IDs, for example `Ricoh/R0000030.JPG`. Re-running with
another selection replaces the global summary; use a separate output folder
and copy/download its models for independent runs.

Each scene has original/fill JPEGs, masks, overlays, raw detector-scale failure
sheets, four film comparisons, 100% crops and a manifest. `portrait-comparison.jpg`
shows original / fill / full Gold target / one-input keeper / reference upper
bound. `metadata-populated-boxes.jpg` shows all populated MakerNote structures.
All thumbnails in a comparison have equal scaling. Crops are taken after a
full-frame render; no separate crop detector or processing pass is used.

`verify_outputs.py --record` reopens each original, recomputes fill from the
saved detector boxes, matches the exported JPEG bytes exactly, saves lossless
PNG source/fill/support evidence, checks exact outside-mask identity, checks
zero new float clipping, checks no-face identity, and records SHA-256 hashes
of every generated image. A subsequent run without `--record` verifies those
same hashes and decoded lossless images. `run.py --verify` is a lighter check
of all scene JPEG decodes, profiles, absence of EXIF, original hashes and
recorded numerical bounds; its numerical fields alone are not independent
proof of rendering.

The model is OpenCV Zoo's `face_detection_yunet_2023mar.onnx`, SHA-256
`8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`,
distributed under its [MIT licence](https://github.com/opencv/opencv_zoo/blob/main/models/face_detection_yunet/LICENSE).
The downloader refuses another binary even if the upstream `main` URL changes.
The model remains in ignored scratch storage. Candidate threshold is 0.80;
acceptance requires score >=0.82 on at least two of 320/640/960/1600-pixel
long-side inputs. The highest-confidence box is retained after IoU >0.4
clustering. This experimental policy was chosen on these pictures; it is not
an independently validated detector operating point. All candidates and
rejections remain in the manifests, including real misses at individual scales.

The fill gain is up to 0.85 EV in **decoded display-linear sRGB**, attenuated
near highlights, and never a sensor-exposure recovery claim. Overlapping masks
combine by maximum, so repeated faces do not receive stacked exposure. The
skin gate is a warm-colour heuristic; it cannot reliably distinguish skin,
hair, lips, skin-coloured clothing or wood. Read `docs/face-fill.md` for the
visual judgement and the camera-integration boundaries.

The one-input keeper contracts linear RGB chroma 30% toward neutral at the
same luminance inside a mask derived from the full film render. It reduces
orange intensity but cannot undo hue rotations or recover clipped channels.
The **reference upper bound** preserves the film luminance and restores 85%
of the source chromaticity under the source-derived mask; it needs a second
pre-film image and is not implementable from the current JPEG hook alone.
Neither keeper changes the film globally. These are separate alternatives;
the comparison does not combine fill and keeper.

The film grid exporter uses the actual repository `LOOKS` and `filmResponse`
with pre-`95ba6de` defaults (colour push 1.5, mid saturation 0.12). It exports a
33-cube sampled target for Gold 200, Nostalgic Neg, Astia and Kodachrome 64.
It does not reverse the existing camera recipe and does not emulate the
native matrix/curve fitter, MTF, halation, grain or later highlight shoulder.
Source Image Control numeric codes are retained in the safe metadata record;
Standard code 256 is a useful basis but does not establish neutral recipe
sliders or white balance calibration.

Optional bounded firmware evidence:

```powershell
& scratch/face-fill-env/Scripts/python.exe tools/face_fill/firmware_scan.py `
  'C:/Users/Antoine/project/grmod-film/scratch/video-firmware-high-rate-2026-11-01/original-rtos.bin' `
  'C:/Users/Antoine/project/grmod-film/scratch/video-firmware-high-rate-2026-11-01/original/fwdc239b.bin'
```

This requires exact official GR III 2.10 hashes and uses Capstone for a small
metadata switch range. The raw ARM target was unsupported by this configured
REA server on Windows; no unavailable provider is represented as having run.
This static scan and stored JPEG boxes do not prove live shot-box availability
at the JPEG stage. No firmware or photos are redistributed by this commit.
