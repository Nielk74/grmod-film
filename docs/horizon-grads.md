# Horizon-locked graduated filters: rejected / parked experiment

**User decision — 2026-11-11: rejected and parked.** After reviewing the images, the user said: "first one is bad. document it but dont build it." The visual result did not meet the user's expectations. No firmware implementation, camera test build or UI integration is planned for this idea. Work on ideas 2 and 3 proceeds separately.

This archived offline experiment applied a graduated-filter change to the user's actual GR III JPEGs, using recorded pitch and residual roll after EXIF rotation. It tested neutral, tobacco, sunset and blue options plus brightness weighting of dark objects. It did not identify sky. The code, generated evidence and technical findings below are preserved as an archival record; reproducibility and passing tests do not override the user's visual rejection or recommend advancing the idea. Nothing here changes firmware, camera settings, films, the application preview or its interface.

## What was rendered

The review output is in this worktree's ignored `scratch/horizon-grads/`. Open `index.html`, the four `comparison-sheet-*.jpg` files, or an individual source folder's `comparison.jpg` and `colours.jpg`. Fifteen source examples cover landscape/portrait lakes, a tilted shore, daylight park, trees, upward street, indoor ceiling, downward food, indoor concert, actual 35 mm digital crops, a state-zero record and an edited JPEG without MakerNotes. All renders are 2000 pixels on the long side; these are viewing-scale experiments, not native-resolution or timing benchmarks.

Each row contains the camera JPEG, neutral one-stop grad, the same grad with brightness weighting, and a mask overlay. Cyan marks the predicted earth horizon; magenta shows mask strength. Lossless PNGs preserve the numerical result for exact pixel checks. Before/after JPEGs use the same sRGB profile, quality 97 and 4:4:4 encoding. The original JPEG's existing camera rendering remains part of the input.

`Ricoh-AK000071-portra.jpg`, `Ricoh-AK000080-portra.jpg` and `Ricoh2-AK000025-portra.jpg` show the same operation after the repository's actual `LOOKS` Portra 400 target. `film_grid.ts` exports that authored operation to a 33³ grid; the Python evaluator interpolates it. This establishes independence from the film's sky hue. It does not establish measured Portra accuracy, the appearance of the fitted firmware coefficients, or that these source JPEGs were camera Standard. There is no generated photographic content.

## Metadata findings and limits

The recursive collection contains **194 JPEGs**, including two `-edited.jpg` copies. **192 contain a 19-byte MakerNote tag 0x022b**. Presence is not proof of valid attitude. The conservative eligibility policy accepts 133 records with state/format byte 1, supported cardinal direction, matching EXIF rotation, plausible angles and supported GR III lens/aspect geometry. It refuses 58 state-zero records, one up/down direction and two stripped edits. The audit property named `version` is provisional: the exact meaning of byte 0 has not been traced. State-zero records often contain plausible changing angles, so this report does not call them missing sensor data. Five state-zero records repeat an identical payload.

The block is read with bounded offsets relative to the beginning of the Ricoh MakerNote. The collection's layout matches the newer documented fields: direction at byte 1, signed little-endian int16 at bytes 3 and 5, and angles interpreted as `-raw/2` degrees. Cardinal values 0/1/2/3 agree with EXIF 1/8/3/6; the residual roll is used in upright coordinates. For example, AK000056's raw block is `010300f9ffe6fffeffc102350032fc4000e600`: direction 3, roll +3.5°, pitch +13°.

The interpretation comes from [ExifTool's Pentax.pm source](https://raw.githubusercontent.com/exiftool/exiftool/master/lib/Image/ExifTool/Pentax.pm), specifically `LevelInfoK3III`. Its general GR III route currently chooses the older K-5 `LevelInfo` byte layout. That route would interpret these bytes incorrectly; this tool explicitly parses the observed layout. ExifTool's own [tag documentation](https://exiftool.org/TagNames/Pentax.html#LevelInfo) warns that the older layout may not apply to other models. The match is evidence, not a Ricoh format specification.

As a further internal check, the trailing three int16 fields behave like an acceleration vector of norm about 1024. Rotating that candidate vector by the cardinal direction gives median disagreements of 0.131° in residual roll and 0.130° in pitch against the interpreted angle fields over 133 eligible records. Its exact field meaning remains a hypothesis. Agreement within the same record supports the decoder's signs/units but cannot independently calibrate the camera level or prove exposure-time freshness.

`audit.json` contains only whitelisted attitude, model/software, geometry and colour-space fields plus source paths/hashes. GPS, capture times, serial numbers and owner fields are not copied. All 194 source SHA-256 values were checked before/after the audit, after selected renders and again by verification. No originals were overwritten.

## Horizon geometry and observed agreement

The pinhole model uses x right, y down and f forward. Clockwise camera roll `r` and upward pitch `p` give an up vector `(-cos(p) sin(r), -cos(p) cos(r), sin(p))`. Thus the signed distance above the ideal horizon is:

```text
d = f * tan(p) - sin(r) * (x-cx) - cos(r) * (y-cy)
```

Positive upward pitch puts the horizon lower in the image. Positive clockwise camera roll makes its line slope upward to the right. The centre is `(width-1)/2, (height-1)/2`. Focal length in pixels is calculated from the **stored image before EXIF rotation**, then scaled uniformly for the rendered image; quarter-turns do not change it.

The lens/sensor model uses the GR III's 18.3 mm focal length and 23.5 × 15.6 mm sensor. An exact 3:2 rectangle inscribed in those nominal dimensions is 23.4 × 15.6 mm. EXIF 35 and 50 mm equivalents define centred crop factors relative to 28 mm. The collection's 4800×3200 and 3360×2240 crop files agree with those factors. Ricoh documents these focal lengths, dimensions and crop options in the [official specifications](https://www.ricoh-imaging.co.jp/english/products/gr-3/spec/). Rounded sensor dimensions, the precise optical centre, lens correction and any stabilization-induced geometry remain approximations; unsupported aspect crops are refused.

`observations.json` records manual picks made on the actual rendered lossless images without fitting a pitch offset or a roll scale. `measure.py` reproduces the residuals and gold observed-line overlays:

| Source | Observation | Mean absolute vertical residual at 2000 px long side |
|---|---|---:|
| Ricoh-AK000069 | Distant lake boundary, landscape | 7.5 px / 0.38% |
| Ricoh-AK000071 | Distant lake boundary, landscape | 6.2 px / 0.31% |
| Ricoh-AK000073 | Distant lake boundary, portrait / EXIF 8 | 9.5 px / 0.48% |
| Ricoh-AK000079 | Tilted near shore, counterexample | 41.4 px / 2.07% |

Picking uncertainty was approximately ±3 px for the distant shores and ±5 px for the near shore. Shore distance, camera height and terrain are unknown. A far-water boundary approximates the horizon but is not an instrumented level target, and a mountain skyline is not the earth horizon. The tilted near shore's observed slope is −3.84°, versus the predicted −10.5°. That disagreement is retained in the evidence. It could reflect perspective along a nonhorizontal/near shoreline, metadata freshness, sensor/correction geometry, or a remaining interpretation issue; these data do not distinguish them. A reliably calibrated tilted horizon is still unverified.

## Effect behavior

The mask is zero at and below the ideal horizon and rises with a smoothstep to full density over `f*tan(16°)` pixels above it. There is no horizon offset chosen per photograph. Strength fades between absolute pitch 35° and 65°, becoming an exact no-op at 65°. Food and concert examples whose predicted horizon is above the frame also naturally have an empty mask. The fixed transition and fade are prototype design choices, not camera facts.

Neutral density attenuates linearized sRGB equally by channel; full mask and one stop is exactly half the linear value. Coloured filters use independent density multipliers: tobacco `(0.52,1.05,1.85)`, sunset `(0.40,1.25,1.95)` and blue `(1.70,1.00,0.42)`. These are authored classic-filter directions, not measurements of commercial Cokin products. All variants preserve pixels outside the mask exactly before JPEG encoding. Recompression may change a few JPEG pixels near transform block boundaries; the lossless PNGs are the identity evidence.

Brightness weighting multiplies the mask by a smoothstep between display-luminance 0.12 and 0.55. On AK000063's dark pixels above the horizon, mean absolute RGB change drops from 3.64 to 0.15 code values, while the overall image change drops from 10.36 to 6.77. Dark trees are better protected, but dark blue skies can also receive less effect; bright buildings and ceilings still darken. AK000059 clearly shows this indoor failure, and the upward 35 mm crop AK000015 changes buildings extensively. These limitations remain part of the archived evidence. The previously considered per-film control is no longer planned following the user's visual rejection.

## Archived firmware feasibility notes — not an implementation plan

The reviewed integration sources are `core/src/fw/gr3x/jpeg-stage.ts`, `core/src/fw/gr3x/datestamp.ts` and `tools/grain/grain.c`. The `gr3x` directory here covers **GR III 2.10 and GR IIIx 1.60**; `fw/aspect` covers the separate GR IV route.

The official GR III file used for repository tests is read-only:

```text
C:/Users/Antoine/project/grmod-film/scratch/video-firmware-high-rate-2026-11-01/original/fwdc239b.bin
SHA-256 d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4
```

That exact container identity matches `tools/gr3x/identity.py`. The guarded source hooks `JpegEncodeMacroProcess::Execute` at 0x535047d4, reads its configuration at argument+8 and processes descriptors at configuration+0x3c..+0x48. Existing grain validates YCbCr 4:2:2 planes, dimensions/strides and pointers, deduplicates shared picture buffers, manages caches, and covers the main image, screennail and thumbnail. This establishes an existing guarded place to add a spatial JPEG operation. The full tests with this official fixture passed; this experiment did not independently execute native code or re-establish every address through a disassembler.

The date-stamp hook snapshots a **cardinal orientation byte**, not continuous roll/pitch: `SetShootingInfoResultBeforeExpose` 0x534322d8, live singleton 0x553458b0 → +0x518 → record → byte +0xc8; the EXIF orientation setter is guarded at 0x535f63d0. It demonstrates a shooting-record snapshot mechanism. It does **not** prove the continuous-level fields' RAM offsets, atomicity, flag semantics, freshness, lifetime or access at JPEG time. Likewise, a completed JPEG's MakerNote cannot supply this data before its encoder runs.

The investigation did not trace the 0x022b writer back to continuous attitude/state fields, establish exposure-time freshness or axes after image correction/cropping, implement a per-exposure snapshot, or establish saved-record handling for in-camera RAW development. These remain historical limitations, not queued implementation work. No RAM addresses were guessed from the JPEG layout. REA's shared native session was being used by another idea, so this pass stayed within reviewed guarded source and verified artifact identity rather than altering that session.

The unimplemented design considered a stage before halation/grain and the date imprint, with fixed-point row coefficients and lookup tables. No native module or parameter row was built, and neither is planned. Native YCbCr equivalence, chroma handling, pair alignment, clipping, speed ratio against grain, buffer cost and camera latency were not established. A single spatial pass and grain both have O(N) work; this does not prove a performance advantage. Consistent geometry across main image, screennail and the 160×120 thumbnail also remained unverified.

## Archival reproduction and historical verification

The commands below document reproduction of the original experiment for archival reference. They are not a plan for additional outputs or builds for this rejected idea. The reproduction environment is this worktree root in PowerShell, with Python 3.12 and the listed dependencies:

```powershell
python -m venv scratch/horizon-grads-env
& scratch/horizon-grads-env/Scripts/python.exe -m pip install -r tools/horizon_grads/requirements.txt
npm ci
& scratch/horizon-grads-env/Scripts/python.exe -m tools.horizon_grads.run audit
& node_modules/.bin/vite-node.cmd tools/horizon_grads/film_grid.ts scratch/horizon-grads/portra.f32
& scratch/horizon-grads-env/Scripts/python.exe -m tools.horizon_grads.run render
& scratch/horizon-grads-env/Scripts/python.exe -m tools.horizon_grads.measure measure
& scratch/horizon-grads-env/Scripts/python.exe -m tools.horizon_grads.measure portra --film-grid scratch/horizon-grads/portra.f32
& scratch/horizon-grads-env/Scripts/python.exe -m tools.horizon_grads.run verify
& scratch/horizon-grads-env/Scripts/python.exe -m unittest tools.horizon_grads.test_horizon -v
$env:GRMOD_GR3_FIRMWARE = 'C:/path/to/official/fwdc239b.bin'
npm test
npm run build
```

Run commands sequentially: measurement and verification read completed renders. The output-path check resolves symlinks and refuses either original source tree. Source selection, filters, geometry and observations are tracked; generated source-derived photos, hashes, manifests and logs remain local.

Historical verification from the original experiment on 2026-11-11: **14 focused tests passed**, including signed metadata decoding, malformed/missing/extreme records, pitch and roll signs, rotation-invariant focal usage, crop/FOV scaling, exact below-mask identity, physical one-stop attenuation, brightness weighting, Portra-grid interpolation, actual landscape/portrait source reads, actual stripped/state-zero no-ops and rendering/verifying twice into the same output. The rerender regression was observed failing on a previous-manifest export and then passing with the fixed explicit image list. Actual result verification checked **194 source hashes and 210 primary image outputs** with no private EXIF or below-mask PNG changes. The repository suite passed **237 tests with 175 skipped**, 34 test files passed and 10 skipped; absent other firmware/private fixtures account for the skips. The UI type-check and production build passed. Existing UI tests log local preview URL warnings and Vite logs the existing `/host.js` bundling warning; neither caused failure. This documentation-only status update did not rerun tests, generate images or build firmware or the application.

**Final status: rejected and parked at the user's request on 2026-11-11.** The offline experiment and its evidence are retained for reference only. No firmware implementation or further build is planned for horizon-locked graduated filters. Reliable live attitude access, tilted-horizon calibration and native camera processing cost remain unresolved archival findings; no camera test, flash, release or hardware verification is claimed.
