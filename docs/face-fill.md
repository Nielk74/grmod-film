# Face-aware fill and skin keeper: experiment, 11 November 2026

The local experiment produces useful face lift on the requested daylight,
window/occluded and night portraits, and a one-input keeper reduces the
excessive orange intensity of full-strength film targets while preserving
their treatment of the rest of the frame. It is an experiment worth keeping
for review. It is not a camera-ready module: the live face-result handoff,
colour-space conversion, mask reliability, and a calibrated keeper remain
unresolved.

No firmware was built, flashed, published or released for this work. No photo
was uploaded, generated, retouched by a generative model, or edited in place.
The source and verification commands are in `tools/face_fill/README.md`.

## Correcting the face metadata premise

The two source folders contain **194 JPEGs, of which 192 have recognized
`RICOH\0II` MakerNotes**. The bounded audit finds none of the legacy Pentax
`0x0060`, `0x0076`, `0x0077`, `0x0227` or `0x0228` face tags. That negative
search does not establish absence of face data.

All 192 recognized MakerNotes contain **tag `0x040b`, 1640 bytes**. ExifTool
names this `FaceInfoK3III`. Interpreting its first words as a candidate layout
gives a 6000x4000 image size, a plausible central AF area and two count-like
fields at words 6 and 8. In 177 files both fields are zero and the whole
payload has the same SHA-256. Fifteen files have nonzero fields and distinct
payloads. Four header pairs occur with multiple faces (2/1, 1/4, 4/4 and 3/3).

The K-3 III layout is not completely transferable to GR III: the documented
second array at word 210 is empty in this collection, while a file with header
0/1 can have its face rectangle at word 10. Therefore the audit records both
the tentative ExifTool interpretation and every nonzero rectangle slot at
`10 + 20*i`, without assigning a proven owner or meaning to either stream.
Rectangles look like `(x,y,width,height)` in the **encoded** 6000x4000 image.
Drawing there and then applying the original EXIF orientation aligns many of
them with actual faces. The sheet includes all 15 populated files, including
extra boxes that do not align cleanly with a current face. Neither count
field is silently treated as an exact list length.

The three requested files (`R0000030`, `R0000005`, `AK000164`) all have the
same empty structure. They therefore use YuNet stand-in boxes in this
experiment. Empty fields do not establish that the user disabled face
detection, nor that the camera never detected the person earlier.

The interpretation was checked against the primary
[ExifTool Pentax tag definitions](https://exiftool.sourceforge.net/TagNames/Pentax.html)
and its [current source](https://github.com/exiftool/exiftool/blob/master/lib/Image/ExifTool/Pentax.pm).
The older [Ricoh FaceInfo structure](https://exiftool.sourceforge.net/TagNames/Ricoh.html)
is a different layout and was not applied to the GR III MakerNotes.

## What the desktop algorithm actually does

YuNet runs locally, with a fixed model hash, at four image scales. A candidate
score is not a probability of correctness. Acceptance requires >=0.82 on two
scales, and overlapping results are grouped by IoU. The policy was selected
using these pictures, so the examples demonstrate feasibility rather than
held-out detector performance. Every raw candidate, score and scale remains
in JSON. Orange rectangles identify rejections. `detector-scale-failures.jpg`
shows the actual misses at individual scales: the large daylight and night
faces are missed at 1600 pixels; the partly covered window face is missed at
320 and 1600. The daylight background candidate does not meet consensus.

The mask multiplies a soft oval by a smooth warm-colour gate in OkLab. It is
computed at up to 1600 pixels and resized to the full image. Colour smoothing
avoids individual pore-sized islands; there is still no semantic skin, hair,
eye or lip segmentation. Masks combine by maximum, so overlapping or duplicate
face boxes cannot stack light. All coordinates are relative to the
EXIF-transposed image; there is no implicit sensor crop. The native metadata
overlay uses the encoded orientation before transposition, separately from
the detector path.

Fill is a multiplicative gain up to **0.85 EV in decoded display-linear sRGB**,
with a smooth highlight attenuation and a peak-channel headroom limit. This
is a JPEG dodge with a reflector-like falloff. The camera's rendering, white
balance, clipping, noise and original recipe are already baked in. It cannot
restore clipped sensor information, lost shadow detail or original colour.
Measured EV is `log2(Y_after/Y_before)` with Rec.709/sRGB linear luminance,
reported over mask weights >0.65. A face with low mask weights receives less
than the maximum gain; the stated setting is not claimed as whole-face EV.

The final native render gives the following results. Outside-mask float
differences and newly clipped float pixels are zero for all six scenes.

| Scene | Oriented size | Accepted / rejected groups | Median core lift | 10th-percentile core lift |
|---|---|---|---|---|
| Daylight `R0000030` | 4000x6000 | 1 / 1 | 0.759 EV | 0.585 EV |
| Occluded/window `R0000005` | 4000x6000 | 1 / 0 | 0.845 EV | 0.640 EV |
| Warm night `AK000164` | 4000x6000 | 1 / 0 | 0.848 EV | 0.665 EV |
| Daylight `AK000075` | 4000x6000 | 1 / 0 | 0.839 EV | 0.633 EV |
| Group at night `R0000043` | 6000x4000 | 8 / 0 | 0.850 EV | 0.681 EV |
| Food/tableware `Ricoh2/AK000001` | 3200x4800 | 0 / 0 | No change | No change |

The comparison keeps fill separate from the keeper to expose their different
effects. There are two keeper variants:

| Variant | Information available | Operation and limitation |
|---|---|---|
| One-input keeper | Finished full-film RGB plus face boxes | Reduces chroma 30% toward neutral at constant display-linear luminance under a mask measured on the film RGB. Plausible JPEG-stage operation after RGB/YCbCr conversion; reduces orange intensity but cannot restore a hue shift or clipped channel. |
| Reference upper bound | Pre-film source RGB **and** full-film RGB plus face boxes | Blends 85% toward source chromaticity at the film luminance under the source-derived mask, with luminance-preserving gamut contraction. This needs an unavailable second image/buffer at the existing JPEG hook; it is a target for comparison, not evidence of a directly ported keeper. |

Both keep the full film outside the mask, exactly in float before output
encoding. The reference variant is not an inverse transform of a globally
weakened film. A post-film JPEG cannot manufacture the missing pre-film
reference. For a native one-input implementation, film-specific chroma/tint
limits need calibration rather than one amount for all films and light.

## Film basis and scene coverage

The full-film comparisons use the repository's authored `LOOKS` and
`filmResponse` at the strength settings used before `95ba6de`: colour push
1.5, midtone saturation 0.12. That commit reduced Gold 200 and Nostalgic Neg to
1/0, Astia to 1.2/0.048, and Kodachrome 64 to 1.1/0.024 because a skin-only cap
did not survive the native global fit. The experiment samples the actual
authored operations into 33-cubes and applies trilinear interpolation. It
omits native matrix/curve fitting, later shoulder changes, MTF, halation and
grain. It therefore validates a spatial finishing target, not identical ISP
output or a measured film stock.

All three main JPEGs report Image Control 256 (Standard), which is a useful
starting basis. This does not prove default recipe sliders or calibrated
white balance. Additional scenes deliberately include other baked controls:
`AK000075` and `R0000043` are 262 (Positive Film), and the no-face food/tableware scene
`Ricoh2/AK000001` is 266 (Cross Processing 2). Their film overlays are stress
cases for masking, not clean Standard-to-film emulation measurements.

The same person appears in most close portraits. Darker/warmer synthetic
colour swatches test numerical gate behaviour, but this collection does not
validate ethnicity or skin-tone diversity. The group scene adds multiple
faces and warm skin under difficult night light; it still cannot establish
broad robustness. No-face identity and warm clothing outside the face
support are checked explicitly. A skin-coloured object inside an accepted
false face box can still be changed.

## Firmware evidence at the desktop experiment stage

The exact official **GR III 2.10** container SHA-256 is
`d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4`;
the separately extracted RTOS SHA-256 is
`8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67`.
Both match the repository's identities before fixed addresses are used.
This investigation did not separately inspect a GR IIIx image.

The configured REA server rejected raw ARM analysis on Windows; no supported
deep provider was configured. A bounded, reproducible Capstone/byte fallback
finds `m_pcFaceDetectionService`, `src/FaceDetectionService.cpp`, and the
`ImageShootingInfoExtractor` diagnostics for size and center-position lists
at `0x53d2f89c` and `0x53d2fa00`. A small switch disassembly near `0x535eee34`
compares legacy metadata tags `0x0227` and `0x0228`. These are static
observations about readers and strings. They do not prove that those tags
are written by these cameras, nor that a live face service exposes usable
shot boxes at JPEG time. The stored `0x040b` evidence is separate and stronger
for the existence of some saved face results.

The existing `core/src/fw/gr3x/jpeg-stage.ts` hook processes finished YCbCr
pictures at `JpegEncodeMacroProcess::Execute`; it currently stashes look and
halation state, not a face list. The repository's `capture_resume_probe.py`
verifies detector configuration only. A camera implementation still needs:

1. A proven shot-time face result source, count, ownership, timestamp and
   lifetime, including what happens when detection is off, misses, changes
   between preview and exposure, or a burst reuses storage.
2. Verified transforms for full sensor, digital crop, aspect ratio, encoded
   JPEG dimensions, EXIF rotation, thumbnail and screennail. Native metadata
   alignment in this collection is evidence for those files only.
3. A bounded per-face mask in the camera's actual YCbCr representation,
   RGB conversion/gamma matching, integer precision and highlight behaviour.
   Desktop RGB performance says nothing about camera processing time.
4. Camera A/B captures covering skin, eye/lip/hair transitions, clothing,
   warm LED light, dark faces, clipped speculars, false positives and no face.
5. A mode or recipe policy for deliberate silhouettes and scenes where
   face lift would undo the intended exposure. No automatic default is
   justified by these six examples.

Fill is the more direct candidate for an optional JPEG finishing feature.
The one-input keeper is plausible but needs colour calibration. The
reference keeper requires earlier pipeline access or another render. These
results can inform the darkroom-print roadmap without claiming that its
broader local tone work or native integration is already done.

## Evidence and verification

Generated images remain local and ignored by Git. In this worktree the output
root is:

`C:/Users/Antoine/.codex/worktrees/face-fill-skin/grmod-film/scratch/face-fill/`

Start with `portrait-comparison.jpg`, `metadata-populated-boxes.jpg`, then
each scene's `fill-sheet.jpg`, `fill-crop-100.jpg`, `mask-overlay.jpg`,
`detector-scale-failures.jpg`, and the four film `*-sheet.jpg` and
`*-crop-100.jpg` files. Source/processed full frames retain native dimensions;
the sheets themselves are scaled for comparison. The 100% crops are 768x768
pixels from the finished native frame. Each manifest records the exact crop
rectangle and source hashes before and after processing.

`metadata-audit.json` retains safe tag summaries, counts, rectangle slots and
payload hashes. `firmware-evidence.json` retains string addresses, exact
instruction bytes and the explicit unresolved questions. Scene
`artifact-hashes.json` files cover every generated JPEG/PNG. `verification.json`
records independently reopened/recomputed source/fill exports and lossless
outside-mask/no-face checks. Pixel metrics describe a change; visual
preference remains a judgement rather than an objective quality score.

The focused Python suite passes **13 tests** covering no-face identity,
overlap, display-linear EV, highlight protection, source immutability, broad
skin gates, both keepers' luminance preservation, independent X/Y coordinate
mapping, consensus, invalid inputs, MakerNote bounds and source-directory
guards, isolated verifier imports and ICC verification across processes.
`npm test` with the official GR III fixture passes **237 tests**, with
**175 skipped** for unavailable other fixtures. Core TypeScript checking and
the production UI build pass. The unchanged suite logs its existing preview
URL warnings under Node; Vite also reports the existing `host.js` bundling
notice. None of these checks is a hardware timing or image-quality test.

## Native manual-test prototype

Following the user's approval to build two custom firmwares, the face feature
now has a separate native implementation and guarded builder in
[`tools/face_fill_firmware/README.md`](../tools/face_fill_firmware/README.md).
That document contains exact addresses, boundary stubs, pinned input hashes,
reproduction commands, installation/control/rollback instructions and the
remaining hardware limits. The earlier integration list above records the
desktop experiment's starting position; the evidence below advances it.

The prototype processes the camera's Y + CbCr 4:2:2 pictures before the existing
v3 JPEG chain. Its gray-response LUT targets +0.85 EV, with a soft face oval,
a broad warm chroma gate and headroom protection. A realistic one-input
keeper contracts Cb/Cr by at most approximately 30% on Astia, Nostalgic Neg,
Kodachrome 64 and Gold 200. It does not restore pre-`95ba6de` heavy-film
rendering or recover unavailable pre-film colours. The twenty-film v3 colour,
tone and recipe defaults are retained. Extra FilmMTF is disabled only in the
isolated experimental baseline, by parent decision to isolate the new JPEG
operation and avoid that stage's transient heap/latency; the shared builder
is unchanged.

Original capture and metadata instructions establish separate preceding/A
and current/B lists in CommonProperty. The current ring is reset and
repopulated before B is copied. A small pre-capture wrapper also clears B
count before the original function, covering a skipped-result branch.
Original config builder, selector and Develop setup instructions prove that
JPEG config `+0x34` points to the per-frame owned CommonProperty and that
normal development reads its direct film byte at `+0x77c`. The module copies
validated B rectangles to its bounded stack, uses no allocation or persistent
face pointer, and leaves Standard, missing/invalid faces and unsupported
geometry unchanged. Full L 6000×4000, 3:2, zero-offset pictures and their
same-ratio screennails are the supported test subset. Other aspects, digital
crops, smaller main JPEGs, nonzero offsets and RAW development are outside
the validated subset. RAW development may apply valid saved faces; no RAW
no-op claim is made.

The complete synthetic probe executes patched original capture, the real
JPEG configuration builder and the installed JPEG chain with the same owned
record. Native/reference pixels, missing faces, Standard, a failed allocation
in the existing grain stage, CPU/register/stack handover and both wrappers'
flags are checked. This is not observation of the physical camera's
capture-to-render queue. AF scheduling, burst membership, ISP transfer and
hardware timing remain manual-test questions. The feature deliberately
no-ops if valid current records do not reach JPEG.

On the three requested portraits, every full-resolution native ARM byte
matches the independent NumPy reference. Measured median linear-sRGB skin
core lift is 0.721 EV daylight, 0.774 EV window and 0.753 EV night, with zero
new RGB clip pixels in these comparisons. The core is the same independent
original-image desktop skin mask above 166/255. Actual ARM fill+keeper is
shown against the YCbCr422 basis and earlier RGB fill in:

`C:/Users/Antoine/.codex/worktrees/face-fill-skin/grmod-film/scratch/face-fill-firmware/photos/`

Open `R0000030-native-sheet.jpg`, `R0000005-native-sheet.jpg`,
`AK000164-native-sheet.jpg` and their `-native-crop-100.jpg` counterparts.
`photos/report.json` pins the final native module hash, untouched source
hashes, encoded rectangles and measured exposure. These old photos have
empty camera face lists, so the real saved YuNet detections remain the
stand-in for this pixel test. The earlier multi-face, no-face, miss and
false-positive sheets remain relevant; this small selection does not prove
skin-tone diversity or camera detector quality.

Native validation passes 41 independent pixel cases and four capture-clear
cases. The source traces and five complete installed-chain cases pass.
The final candidate is `scratch/face-fill-firmware/fwdc239b.bin`,
38,433,372 bytes, SHA-256
`fbb5b129766e313b54694ba5d1042a861d2cee49d3121653de4d1cba02030eca`.
Container readback and the complete baseline-byte diff audit permit only
two entry-word patches, the RTOS size field and one appended 24,576-byte
RTOS frame. All non-RTOS sections remain identical to the reviewed
no-extra-MTF v3 baseline. The parent independently reran 237 npm tests with
175 fixture-related skips, core type checking and the production UI build.
No firmware was flashed, pushed or published.
