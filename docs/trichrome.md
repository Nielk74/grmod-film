# Trichrome burst: desktop proof and camera boundary

**Verdict: desktop proof accepted; real-burst, handheld, and cross-shot camera readiness remain unproven.** This is a reproducible research prototype, not a firmware patch. It demonstrates independently timed RGB ghosts while preserving a static image's sharp detail. The strongest visible motion example is explicitly synthetic. No photos were uploaded, generated, or altered in their source directories. No camera was flashed.

## Reproduce and inspect

Run from this worktree in PowerShell. The tested Python environment already has NumPy and Pillow; the requirements file pins the versions used. An isolated environment is optional:

```powershell
python -m venv scratch/trichrome-env
& scratch/trichrome-env/Scripts/python.exe -m pip install -r tools/trichrome/requirements.txt
& scratch/trichrome-env/Scripts/python.exe -m unittest discover -s tools/trichrome -v
& scratch/trichrome-env/Scripts/python.exe tools/trichrome/run.py --out scratch/trichrome --max-edge 2400
```

The same commands work with `python` directly when its packages match. `--max-edge 2400` processes each portrait at 1600×2400. A crop labelled 100% shows pixels of that declared processing grid, not original sensor pixels. The input dimensions are recorded separately in the source inventory. Increasing `--max-edge` to 6000 is supported but increases desktop memory substantially; that full-size rendering was not run here.

The review gallery is `scratch/trichrome/index.html`. In the dedicated worktree its absolute path is:

`C:/Users/Antoine/.codex/worktrees/trichrome-burst/grmod-film/scratch/trichrome/index.html`

Useful files under that same output directory:

| Evidence | Relative output |
|---|---|
| Summary sheet | `overview.jpg` |
| Static detail versus literal channel mixing | `02-static-identity/comparison.jpg`, `crop-100.jpg` |
| Fractional handheld shift, quarter width/height | `03-static-handheld/crop-100.jpg`, `manifest.json` |
| Same handheld test, half width/height | `03b-static-handheld-factor2/crop-100.jpg`, `manifest.json` |
| Visible synthetic RGB ghosts | `04-synthetic-moving-foreground/comparison.jpg`, `motion-crop-100.jpg` |
| Parallax rejection | `06-synthetic-parallax/comparison.jpg`, `manifest.json` |
| Difficult real concert shots, rejected | `07-real-concert-difficult/comparison.jpg`, `manifest.json` |
| Dominant-motion rejection | `08-synthetic-motion-dominant/comparison.jpg`, `manifest.json` |
| Original immutability | `originals-integrity.json` |
| Source selection and timing caveat | `inventory-before.json`, `sequence-provenance.json` |
| Numerical results, image hashes, memory | `summary.json`, per-case `manifest.json`, `memory.json` |

The script refuses output inside either original directory, hashes **all 288 original files before and after**, strips source EXIF by constructing new images, and checks every output image for unexpected EXIF. Per-case manifests hash each rendered output. Rejected reruns remove old accepted composites. Source filenames and a small metadata whitelist are retained in local audit JSON; GPS, serials, MakerNotes, and private comments are never copied. Original JPEG/DNG/MOV files remain read only.

## Capture provenance: no verified burst

The two original directories contain 194 JPEG files, including two edited duplicates; the inventory examines all files and uses the 192 unedited JPEGs when grouping timestamps. One five-file group, `Ricoh/R0000051.JPG` through `R0000055.JPG`, shares `DateTimeOriginal = 2024:10:04 20:55:46`, dimensions 6000×4000, orientation 8, 1/125 s, f/2.8, and ISO 3200. These are GR III JPEGs whose recorded camera software is 1.71; this photo evidence does not validate firmware 2.10.

However, the EXIF modification times are materially different:

| JPEG | EXIF DateTime | Paired DNG present |
|---|---|---|
| R0000051 | 2024:10:04 20:55:46 | Yes |
| R0000052 | 2024:10:05 01:47:01 | No |
| R0000053 | 2024:10:05 01:47:58 | No |
| R0000054 | 2024:10:05 01:48:12 | No |
| R0000055 | 2024:10:05 01:48:32 | No |

There are no subseconds. Alignment finds zero displacement, and a bounded 1000×1000 high-pass crop from JPEG51/52 has correlation 0.9565. These observations support the **inference** that later files are developments of the same capture. They do not establish the exact development operation. The gallery therefore calls them “real matching JPEG variants, likely RAW developments,” never a verified multi-exposure burst. Their useful role is checking stability and radiometric normalization on real camera-rendered data.

The concert files `AK000090/91/92.JPG` are genuine different captures two seconds apart. Their perspective and lighting change; the translation-only method rejects them. They are labelled separate photographs, not a burst. No independently verified three-exposure burst was found. Field validation of moving people, traffic, flags, water, or clouds remains required.

## Reconstruction and what it preserves

“Quarter resolution” has two possible meanings. The approximately 3 MB proposal requires **one quarter of the width and one quarter of the height**, retaining 1/16 of the pixel count. Quarter pixel count, obtained by halving both axes, costs 12 MB for two channels at 6000×4000. The prototype renders both versions on the same known-shift scene.

For factor 4, retain only unsigned-byte BOX averages of red from exposure 1 and green from exposure 2. Once frame 3 arrives, align each older plane to the matching channel of frame 3, apply a robust same-channel affine gain/offset fit, and calculate:

```text
Rout = R3 + U(normalize(warp(D(R1))) - D(R3))
Gout = G3 + U(normalize(warp(D(G2))) - D(G3))
Bout = B3
```

`D` is integer BOX reduction, with round-half-up; `U` is bilinear expansion. Shifts map frame 3 coordinates into the earlier stored plane. Output rounds and clamps to byte RGB. A companion **literal** comparator uses `[U(R1small), U(G2small), B3]` so its soft red/green detail and static chromatic fringes are visible beside the proposed reconstruction.

For identical inputs with no radiometric or alignment error, the temporal deltas are exactly zero. The reconstructed output equals frame 3 at every pixel, including high-frequency chromatic detail; a random-texture regression and the real-scene static render verify exact identity. The literal comparator differs by mean 7.18 DN across RGB on the real-scene render.

Moving objects remain independent in the low-frequency red and green deltas, so they still produce colored ghosts. There is no motion mask that blends full RGB back toward frame 3. Fine detail of earlier ghost silhouettes is lost at reduction, while all fine detail comes from frame 3. The look is a compromise: broad Harris-shutter separation with frame 3 texture, not three full-resolution filtered exposures. The authored neutral walking figure is deliberately recognizable as synthetic. Its red and green previous positions and blue third position remain visible at thumbnail size; the dedicated 100% crop shows softened earlier contours and frame 3 edge detail. This proves the channel operation, not the aesthetic quality of real moving subjects.

## Measured behavior and unresolved handheld fringes

Default render: NumPy 2.5.2, Pillow 13.0.0, 1600×2400 processing grid. Timing per accepted processing operation was approximately 0.35–0.5 seconds on this desktop, excluding JPEG decode and all evidence writes. This says nothing about camera execution time.

| Case | Prototype result | Interpretation |
|---|---|---|
| Matching real JPEG variants | Accepted; both shifts zero | Real input stability only; exposure independence unverified |
| Identical real-scene triplet | Accepted; max pixel error 0 | Static identity and restored detail proven |
| Known fractional shifts | Accepted; estimated error ≤0.25 processing pixel | Geometry acceptable, residual static color fringes remain |
| Same shifts, factor 2 | Accepted; exact estimated shifts | Fourfold storage does not cure resampling-phase error |
| Synthetic moving foreground | Accepted; independent RGB ghosts | Intended channel separation survives |
| Synthetic gain/offset drift | Accepted | Fits recover approximately 0.92596/−2.776 and 1.06362/−4.235 |
| Split-depth ±20-pixel shifts | Rejected; tile consensus 5/9 | Global translation is insufficient |
| Real concert shots | Rejected; shift outside policy | No confident composite exported |
| Whole-frame unrelated foreground | Rejected | No confident composite exported |

The known shifts are `(5.25, −3.5)` and `(−2.5, 4.75)` processing pixels relative to frame 3. Static errors below compare reconstructed R/G with the same valid crop of unshifted frame 3. The entire scene is static in this test, including water frozen from one photograph.

| Retained planes | RGB MAE | R/G p95 | R/G p99 | R/G maximum | R/G samples >8 DN |
|---|---:|---:|---:|---:|---:|
| Factor 4, 3 MB at sensor size | 1.597 | 8 | 13 | 48 | 4.59% |
| Factor 2, 12 MB at sensor size | 1.941 | 11 | 16 | 43 | 8.16% |

The factor 4 maximum occurs at processing `(1129,666,R)`; the factor 2 maximum is `(1414,1495,G)`. The exact locations and percentile distributions are in each manifest. The 100% sheets show substantial detail preservation but still contain static edge color errors. Exact shift recovery is therefore **insufficient** to establish handheld quality. Changing the storage scale alone did not solve this case. Independent resampling, quantization, and low-pass phase differences survive the geometric correction. The geometric guard can accept such a scene; “accepted” is not a promise of a fringe-free result. The valid crops retain 98.299% of the original processing area at factor 4 and 98.650% at factor 2.

The desktop alignment uses a phase-correlation seed and nine independently matched 24×24 sample tiles, with quarter/eighth stored-pixel refinement. It requires at least five strong tiles and at least 75% agreement among evaluated textured tiles within 0.55 stored pixel. With nine tiles, seven must agree. Weak texture, inconsistent tile motion, unrelated input, and translations over 24 stored pixels reject. This is a conservative prototype policy, not a calibrated camera confidence probability. A minority parallax layer can escape a global consensus guard; it cannot prove that every accepted pixel obeys a translation.

Robust per-channel affine normalization rejects insufficient signal, gains outside 0.7–1.4, offsets outside ±20 DN, or fewer than 60% of sampled nonclipped pixels agreeing within 12 DN. This can approximate modest exposure/WB differences in already-rendered JPEGs. It cannot reconstruct clipped channels, spatially varying stage lighting, independently changed tone curves, or arbitrary film changes. Fixed exposure, WB, Image Control, and focus throughout a burst are the intended mode contract. Larger radiometric drift has a numerical rejection regression.

Fractional offsets use bilinear sampling with explicit valid masks and a conservative common crop, never wraparound or black edge filling. Manifests record the exact crop and retained area. Sensor/output ROI mapping and a future camera policy for a changing field of view remain unresolved. The loader normalizes EXIF orientation before desktop processing and rounds processing dimensions down to multiples of four; a future native adapter must validate actual descriptor dimensions, format, stride, orientation, and crop instead.

## Memory: 3 MB is retained payload, not total peak

All figures below are exact decimal bytes before allocator headers. A YCbCr 4:2:2 image uses one byte Y and one byte interleaved Cb/Cr per pixel, across separate planes; it is not an RGB24 buffer.

| Image | Factor 4 retained R1+G2 | With each stored row aligned to 64 bytes | Factor 2 retained R1+G2 | Existing packed Y+CbCr, borrowed only |
|---|---:|---:|---:|---:|
| 6000×4000 main | 3,000,000 | 3,072,000 | 12,000,000 | 48,000,000 |
| 720×480 screennail | 43,200 | 46,080 | 172,800 | 691,200 |
| 160×120 thumbnail | 2,400 | 3,840 | 9,600 | 38,400 |

The main stored dimensions are 1500×1000 at factor 4 and 3000×2000 at factor 2. Packed factor 4 main storage is 2.861 MiB; factor 2 is 11.444 MiB. Retaining all three sizes separately adds 45,600 packed bytes at factor 4, totaling 3,045,600. At 64-byte stored row alignment the three sizes total 3,121,920 bytes. The desktop `BurstBuffer` limit of 3,100,000 is explicitly for the two packed main planes; it does not budget a complete native implementation.

A straightforward native design might retain both frame 3 reference R/G reductions before modifying its shared YCbCr planes, then reconstruct rows. An explicit provisional peak is 3,072,000 retained bytes + 3,000,000 reference R3/G3 bytes + 196,608 bytes for two 384×256 byte alignment images + approximately 300,000 bytes of row/tile workspace: **about 6.6 MB, plus allocator/cache alignment overhead**. Keeping full signed-16-bit warped and delta planes instead would add approximately 6 MB per channel processed; that is a poor default. These are prospective accounting choices, not measured camera allocation success.

A more economical stream can replace full reference planes with look-ahead row rings, but must preserve original Y/CbCr rows until both RGB deltas have been computed. Writing Y or shared chroma for red first can corrupt the green/blue reference. This implementation does not contain that native stream and does not claim its peak. A camera implementation would also need to replace or bound NumPy's full-frame float intermediates and FFT allocations; the desktop code uses much more than these native estimates.

Camera rows use their descriptor stride, potentially larger than width, and cached DMA surfaces require invalidation before CPU reads and cleaning after writes. For example, a hypothetical 64-byte-aligned 6000-pixel Y/CbCr stride is 6016, making the existing main Y+chroma allocation 48,128,000 bytes. The actual descriptor stride must be read, not inferred. Chroma is shared horizontally at 4:2:2, so native conversion, rounding, and pair writeback need a byte-exact reference/emulator test. Desktop RGB results do not prove native YCbCr parity.

## Firmware evidence and credible integration path

Repository source establishes the following for **GR III 2.10 / GR IIIx 1.60**, with no claim about other firmware builds:

| Source | Established fact | What it does not establish |
|---|---|---|
| `core/src/fw/gr3x/jpeg-stage.ts` | Guarded `JpegEncodeMacroProcess::Execute` hook at 0x535047d4; config at `[r1+8]`; four picture descriptors at config+0x3c..0x48; heap/cache services in context | A unique burst/frame ID, multi-shot scheduling, or cross-exposure ownership |
| `tools/grain/grain.c` | Format1 YCbCr4:2:2 descriptor, separate Y/C planes, stride/c_height checks, duplicate-plane suppression; cache invalidation/clean and alloc/free | Retained storage across calls; its tiny offset array is freed before return |
| `tools/filmmtf/filmmtf.c` | 192-row strips with margins; fail-without-effect on allocation failure; temporary allocations freed before return | Availability of several persistent megabytes during capture |
| `core/src/fw/gr3x/profile.ts` | Exact accepted official GR III2.10 file hash `d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4`; RTOS hash `8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67` | Runtime feasibility or behavior of a new feature |

The local official file at `C:/Users/Antoine/project/grmod-film/scratch/video-firmware-high-rate-2026-11-01/original/fwdc239b.bin` was read only and SHA-256 verified against that exact GR III2.10 profile. No firmware bytes were edited. GR IIIx1.60 was not independently opened in this work.

Additional **source-only** evidence was read from the other local worktree:

`C:/Users/Antoine/project/grmod-film/.claude/worktrees/loaded-ui/tools/shot-animation/`

Its `native/camera_gr3.c` defines an owned `Adapter`, allocates it through 0x536af2a8, initializes it before publishing a permanent pointer, and returns the same state on repeated `create()` calls. Cancellation detaches/stops the player while retaining the owned state. That is a concrete mod-side persistence pattern, stronger than a browser mockup, but it proves neither native heap lifetime during JPEG work nor safe communication between the UI task and the image-processing task. Its header states hardware DMA/display/performance still need physical tests. These external sources were not changed or imported into this branch.

The official-based animation linker reserves 0x55804374/0x55804378 exclusively. The latter is the film pack's halation stash in this repository, so combining those reservations blindly is invalid. The external film-pack-specific linker relocates animation state/latch to 0x558043b8/0x558043bc and verifies its zero-fill contract. Those words are already owned in that build; trichrome needs its own reviewed reservation or a shared mod-state structure. The small stash word cannot hold planes, and an encoder-owned picture pointer must never be retained beyond its valid call.

Source identities retained for review:

| External file | SHA-256 |
|---|---|
| `native/camera_gr3.c` | `663d5a80a6c44254dd28d438482923507ffded699887169ce7341cc234a8b6a7` |
| `native/camera_gr3.h` | `7ba5add07a6d2f5edd749556e6c99e2307e97a1f334c0b6c64469c9134cf7cbb` |
| `native/link_firmware.py` | `08e74b91608ad459866e6f6a1642c42bc2db88be3da9939703746666236919bf` |
| `native/link_firmware_filmpack.py` | `abcf2e006c1160977d00c7ceffd0e39b02dfbe0fd5e6d9d4e15eb8ddc02ab36c` |

No fresh firmware decompilation or camera runtime observation was performed. The evidence above is source inspection plus exact local file identity; address comments are not independent proof of newly inferred native behavior.

The realistic next integration is a dedicated three-shot mode with an owned, bounded state machine:

1. Establish one burst generation, actual shot index, capture completion event, and settings identity upstream of JPEG processing. Prove this independently of QuickView and review settings; UI animation callbacks do not supply the required JPEG scheduling guarantee.
2. Copy reduced R1 during frame1's valid JPEG callback and G2 during frame2's, leaving their normal JPEG saves unchanged. Store only owned pixels, dimensions, settings, and generation metadata. Do not keep native picture pointers. First prove allocator/cache/task ownership and safely synchronized cancellation on the exact firmware.
3. Before touching frame3, validate all metadata and memory, finish alignment and normalization, and prepare a safe failure path. Reject invalid geometry/radiometry and keep frame3's normal JPEG on rejection. The desktop prototype's cropping cannot silently become camera descriptor edits; choose and verify a supported ROI/output policy first.
4. Compose frame3 before optional film-MTF/halation/grain/date finishing, ideally capturing frame1/2 reductions at the same pre-finishing position. Otherwise random grain and different finishing become temporal differences. Existing final ordering is film MTF → halation → grain → date. Reuse native YCbCr conversion/cache conventions only after parity tests.
5. Give screennail and thumbnail the same temporal effect. Either safely regenerate them from composed main or apply resized deltas with proven same-ROI mappings; neither native regeneration API nor its synchronization has been established here. Processing main alone leaves inconsistent playback/EXIF previews.
6. Release planes on success, rejection, allocation failure, cancellation, missed-frame timeout, controller/mode changes, RAW-development entry, shutdown, or a superseding burst. The desktop state machine covers ordered capture, changed token/settings/dimensions, explicit cancel, and timer-driven `expire(now)` when frame3 never arrives. A future adapter must actually call that timer and implement task-safe lifetime. The test timeout is a desktop policy, not a measured hardware interval.

Even after ownership is proved, rotational shake, parallax, moving-dominant scenes, and high-contrast static fringes need field evidence. A tripod-oriented creative mode is a more credible target than everyday handheld capture. Hardware latency, free-heap high-water mark, thermal/power behavior, and JPEG queue pressure remain unknown.

## Verification performed

- `python -m unittest discover -s tools/trichrome -v`: **10 tests passed**, including end-to-end static identity and accepted moving foreground, fractional translation, flat/parallax/unrelated rejection, radiometric fit/rejection, crop edges, memory limit, settings/dimension/token changes, missing-frame expiry, cancellation, and reset after failure/completion.
- `python tools/trichrome/run.py --out scratch/trichrome --max-edge 2400`: **nine cases rendered**, expected three difficult cases rejected; **288 original hashes unchanged**, output images contain no source EXIF. Per-image hashes and numerical percentiles are recorded.
- After isolated `npm ci --ignore-scripts`, `npm test` with `GRMOD_GR3_FIRMWARE` set to the verified GR III2.10 official file: **237 passed, 175 skipped, zero failures**. Skips cover absent GR IIIx and other private fixtures. The existing UI tests emit preview-fetch `ERR_INVALID_URL` warnings under Node but pass; no frontend source changed. The install reported existing dependency audit findings (3 moderate, 1 high, 2 critical); dependencies were not changed.
- No ARM-native trichrome module, firmware patch, camera benchmark, independent real-burst validation, hardware test, push, release, or publish was attempted. Existing native grain/film-MTF checks were not rerun because their sources and compiled modules are unchanged; their prior evidence does not validate this new algorithm.
