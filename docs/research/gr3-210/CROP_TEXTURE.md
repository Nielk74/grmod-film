# WP2 — texture in the crop modes the user shoots

Base: `db76c9b42f85d657a760d07af97735854f253c57`. Updated 2026-11-09. Status: host implementation, independent review and texture packaging verified. Common session assembling; no camera validation.

## What the real files establish

**Claim:** 25 of the 27 Ricoh2 JPEGs use camera crops; crop texture is the first implementation priority.

**Evidence class:** real files. EXIF `0xA405` groups: two 28 mm / 6000 px images, sixteen 35 mm / 4800 px images and nine 50 mm / 3360 px images. AK000019–027 are 35 mm JPEGs at 4800×3200 with DNG DefaultCrop 6000×4000. This closes their crop-versus-resize ambiguity. Earlier pairs keep the DNG crop equal to the JPEG crop.

**Decision:** use these files to prioritize crop processing. The full-DNG/cropped-JPEG behavior exists in real files; metadata alone does not identify the exact firmware build that produced them.

**Next step:** use the completed corpus and descriptor-size audits in `research/gr3-210/wp2-audit`; compare the host candidate on the camera.

**Kill criterion:** do not infer custom-ratio hardware validation or a specific hook installation from the same evidence.

**Limit:** the pixel readout and exact encoder descriptor for each capture were not recorded in these files.

## MTF coverage and alignment

**Claim:** the former direct MTF predicate rejects 3360 px images and several non-8-aligned active sizes.

**Evidence class:** source and emulated geometry. Before WP2, `core/src/color/filmmtf.ts` and `tools/filmmtf/filmmtf.c` require width ≥4096 and both dimensions divisible by eight. That rejects all nine 50 mm JPEG sizes directly, plus 5332×4000 and 4800×2700. A whole-buffer alias has not proved those real crops received MTF.

**Decision:** explicit `textureGeometry: 'sensor' | 'output'` enables the new modules. MTF accepts even 4:2:2 widths from 960 and processes the local 8-aligned interior. Surveyed 720 px screennails and 160 px thumbnails remain excluded. Original descriptor dimensions, right/bottom tails and stride padding stay unchanged. Arbitrary 640 px-wide custom mains remain unsupported by MTF.

**Next step:** the common camera comparison. Native/reference fixtures cover actual 3360×2240, 3000×4000, 5332×4000, 4800×2700 and 960×1280 sizes, aligned tails, padding, aliases, descriptor/heap canaries, invalid-first fallback and allocation failure. The saved legacy R10 build still reconstructs at SHA-256 `c25f45439dbd1ea3dd339bd59400bf5a1d698043dd610e2425c11f8acbc7faf1`. Absence of the new option retains all three frozen native payloads and exact old-recipe reconstruction; GR IV stays on that path. Independent review has no open findings. T-texture sensor candidate `631974813579e055a65f80c1558133acd7f27259edf2b4dcfb9dc052c2f21768` passes fresh-Engine reconstruction and the pinned Python decoder, with 446 declared sites matching and untouched sections preserved. Its reviewed copy is `research/gr3-210/test-session/ready/T-texture/fwdc239b.bin`; the common card and session manifest are complete. Hardware remains untested.

**Kill criterion:** reject any change that writes outside the active aligned region, affects preview/thumbnail descriptors, or fails reference/native parity.

**Limit:** an aligned interior leaves a narrow unprocessed edge; the test card must include edge inspection.

## Grain and halation scale

**Claim:** legacy grain scaling treats a narrow crop like a downsized full frame.

**Evidence class:** source. At width 3360 with fullWidth 6000, `grainYC` computes step 457 and attenuation 143/256. After integer gain rounding, medium gain becomes 35 instead of 64. A crop preserves sensor sampling and does not require the full-frame resize attenuation.

**Decision:** span is `max(width, height × 3/2)` in stored processing coordinates. The bounded property audit did not establish per-shot crop provenance and is closed. Sensor policy uses the primary main span once per job; output policy uses 6000. Previews inherit that reference; missing, invalid or preview-sized primaries fall back to 6000. Grain uses `floor(256×reference/pictureSpan)` and halo radii use the corresponding picture/reference ratio. Plane indexing, seeds, palette and excitation stay unchanged. Existing positional APIs keep their span semantics; optional host metadata carries pre-display-rotation geometry.

**Next step:** compare at 28/35/50 mm and square/portrait crops. The odd-width rotated RGB preview fix passed independent review; native/YCC odd widths remain rejected. Final full suite: 249 tests passed, 175 skipped, plus type checking. Native parity covers all grain settings and four halo colours. Isolated Zig 0.15.1 / clang 20.1.2 payloads match at two link origins. The separate pipeline probe passes 3,528 stash states, dispatch/reference checks, registers/stack and balanced allocations; its native-look negative control is unchanged with zero allocation/cache calls. Evidence: `research/gr3-210/wp2-implementation/sensor-probe/stage-report.json`.

**Synthetic scale result:** at 6000/4800/3360 widths, Medium sensor grain RMS is about 4.03/4.01/4.01 versus output 4.03/3.17/2.22; sensor lag-one correlation stays about 0.53, whereas output falls to about 0.22 at 3360. Red halo horizontal RMS radius stays about 48–49 source pixels sensor versus output 49/42/34. Declared fixtures are in `research/gr3-210/wp2-implementation/texture-metrics.json`. These verify scaling, not appearance.

**Real-content host sheet:** `research/gr3-210/wp2-visual/wp2-crop-texture-sheet.png`, SHA-256 `255d8f73a6201b58cc22bc41ae7e7e12d7d52c923d46fa0a254c4da03c4b6c6b`. Input is the native 6000×4000 ISO 100 Standard `R0000027.JPG`, with ImageTone 0x100 and Orientation 1 verified. One 6000×384 strip is centrally cropped to 6000/4800/3360 without resize, processed, then identical 900×256 source regions are shown at 100%. The 28 mm row is byte-identical; at 35 mm Output equals Legacy, while Sensor retains grain; at 50 mm Output adds MTF while Sensor also restores grain scale. Colour is pinned Portra once, with no halation. `processing.json` pins source/colour hashes, coordinates and seeds. It is a declared strip rendering, not real 28/35/50 mm camera captures; strip-derived seeds differ from full-frame seeds.

**Test-library choice:** T-texture puts the separately named approved Gold in slot 64 instead of Pro 400H. The other 19 colours, including Portra and current Gold, remain exact. It retains Soft Focus; ADJ Grain's shared-function tradeoff is deferred. Full section 5 resets accompany this changed library and its return pack.

**Kill criterion:** keep or revert according to the user's old/new 100% camera comparison; stop after a safe host candidate is packaged.

**Limit:** no aesthetic choice is approved by amplitude statistics alone. Sensor policy assumes retained sensor pixel pitch and cannot classify a true resize without provenance. No new camera result is claimed.
