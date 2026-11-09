# WP2 read-only implementation audit

Audit base: `db76c9b42f85d657a760d07af97735854f253c57` (2026-11-09, Europe/Paris). Read the human brief and CLAUDE.md. Production files unchanged. Earlier-signal research is frozen; its eight-call JPEG pointer-packet result remains external evidence only.

## Decision and kill criterion

Proceed with a host implementation of crop texture, preserving Portra colour and all film coefficients. Do not spend another reverse-engineering round on a crop bit. This bounded source read found a candidate float at shooting record +0x7b8, used by existing geometry probes, but did not establish its per-exposure writer and binding to the selected JPEG/RAW-development job. Use the human-authorized sensor-anchored default, and an explicit output-relative build option. The eventual hardware keep/kill decision is the user's preference on the same subject at 28/35/50 mm. No camera writes by agents.

## Cheap corpus corrections, replayed

`corpus-corrections.json`: 27 JPEGs, all 4:2:2, **23 distinct DQT sets**. They are 2 × 6000×4000 at recorded 28 mm, 16 × 4800×3200 at 35 mm, and 9 × 3360×2240 at 50 mm (standard EXIF 0xA405). AK000019–27 each have a 4800×3200, 35 mm JPEG and a 6000×4000 DNG DefaultCropSize. This closes crop versus M resize for those files; neither EXIF Software nor this metadata proves a particular mod/film build identity. The direct current MTF predicate rejects all nine 3360 images, although a later shared-buffer descriptor may separately rescue execution. At 3360 the exact grain step is 457, attenuation 143/256 = 0.558594, and Medium's final integer gain is 35/64 = 0.546875. These differ because gain is rounded down once more.

## Descriptor and guard inventory

* Original GR III 2.10 dimension function executed at 0x536a2a30 for four native identities, four size selectors and three magnification arguments. Returned native dimensions do not change with those magnification arguments. Unique native sizes: 6000×4000, 4800×3200, 3360×2240, 1920×1280; 5328×4000, 4272×3200, 2992×2240, 1920×1440; 6000×3376, 4800×2704, 3360×1888, 1920×1080; 4000², 3200², 2240², 1280². Native hidden identities 1/2 are distinct from the custom 4:3/16:9 crop rounding.
* Current T4 custom dimensions (L / M / S / XS), from actual `planGr3xRatio` source:

| Ratio | L | M | S | XS |
|---|---|---|---|---|
| 4:3 | 5332×4000 | 4268×3200 | 2988×2240 | 1708×1280 |
| 16:9 | 6000×3376 | 4800×2700 | 3360×1892 | 1920×1080 |
| 65:24 | 6000×2216 | 4800×1772 | 3360×1240 | 1920×708 |
| 17:6 | 6000×2116 | 4800×1696 | 3360×1184 | 1920×676 |
| 3:4 | 3000×4000 | 2400×3200 | 1680×2240 | 960×1280 |
| 7:6 | 4668×4000 | 3732×3200 | 2612×2240 | 1492×1280 |
| 5:4 | 5000×4000 | 4000×3200 | 2800×2240 | 1600×1280 |

* `core/src/fw/gr3x/geometry.ts:34–35` constructs preview windows within 720×480 and 160×120. Custom screennail widths are 360, 560, 600, 640 or 720. `tools/gr3x/datestamp_probe.py:136–143` uses descriptors 720×480/stride 736 and 160×120; `picture_stage_probe.py` uses the same supported layout. This establishes a **source/fixture** maximum preview width of 720 in the surveyed paths, not a telemetry capture of every live descriptor. Preview size tag 0x0002 is absent from all 27 JPEG MakerNotes, so it supplies no additional real-file descriptor proof.
* Recommend **FILM_MTF_MIN_WIDTH = 960** in both TS and C. It covers all 28 T4 custom main sizes, while 3000 covers only 16. It excludes every surveyed preview. Dynamic ratio bounds permit an XS 1:2 main width of 640; that remains deliberately excluded by this minimal 960 floor and must be called out rather than represented as full coverage of arbitrary ratios.
* `3000×4000` is already 8-aligned; width floor is its only current obstruction. For `5332×4000`, process 5328×4000; for `4800×2700`, process 4800×2696. Keep original descriptors, row stride, last four columns/rows and all padding byte-identical. Continue rejecting odd 4:2:2 widths. TS and C must share the same acceptance predicate; full dimensions still bound memory/cache ranges, while a local view supplies aligned processing dimensions. Do not simply remove the `&7` guard: the three pyramid halvings otherwise produce mismatched arrays and unsafe native indexing.

## Geometry contract, including previews

Use `S(w,h) = max(w, 3*h/2)` in **stored processing coordinates**, not dimensions after EXIF display rotation. Name it `aspectSpan`, separate from stride and plane width. Do not replace width in indexing, seeds, allocation, sampling-grid dimensions or descriptor identity.

For a job with a valid primary main descriptor at config+0x3c:

* Sensor default: `R = S(mainWidth,mainHeight)` — explicitly assumes the main output retains sensor pixel pitch, as authorized for the crop-heavy corpus.
* Output-relative alternate: `R = 6000`.
* Each picture, including screennail/thumbnail: grain step `floor(256*R/S(picture))`; existing attenuation and gain rounding then apply. Halation radius basis is `6000*S(picture)/R`, converted into that picture's actual reduced-grid coordinates. Its grid dimensions and strides stay based on actual width/height. Thus a cropped main image has full sensor-pitch texture, while its smaller previews remain attenuated.
* Example 35 mm main 4800×3200, screennail 720×480: sensor R = 4800 gives main grain step 256 and preview step 1706; halo bases 6000 and 900 respectively. Giving each descriptor its own R would wrongly make previews full strength. Square main 4000² gives S = 6000 and main step 256; a square 720² representation gives S = 1080 and appropriate reduced texture.
* If the primary descriptor is absent, invalid or preview-sized, use the output-relative path rather than infer a cropped main image from a thumbnail or from a later whole-buffer alias. Use a primary-main long-edge check (≥1280) independently from MTF's width floor; this also identifies a 640×1280 custom main for grain/halation. Confirm the actual primary layout on the hardware test card.
* Keep existing `grainRgb(..., channels, span)` and its 100% crop/whole-frame span meaning unchanged when no new options are supplied. Add an **explicit optional geometry object/entry point** for new callers, rather than reinterpret that positional argument. The same applies to `grainYC`'s existing `fullWidth` argument and `halateRgba`'s current preview default. New helper/API options must carry source/main geometry when a preview has been resized or rotated.

## Proposed file-by-file manifest (no edits authorized yet)

| File | Concrete proposed change |
|---|---|
| `core/src/color/texture-geometry.ts` (new) | Policy types, aspectSpan, validated job reference, integer geometry calculations. Legacy/output/sensor policies explicit; no colour changes. Export via `core/src/color/index.ts` if required by its existing barrel. |
| `core/src/color/filmmtf.ts` | 960 floor; even-width validation; process local 8-aligned interior using original stride; preserve tails and descriptor. Do not alter matrices/gains. |
| `tools/filmmtf/filmmtf.c` | Exactly matching guard/local aligned picture view; keep full-frame cache ranges and allocation failure behavior. |
| `core/src/color/grain.ts` | Optional explicit geometry input, preserving legacy positional span semantics and existing output when omitted. Geometry only changes tile step/attenuation calculations. |
| `tools/grain/grain.c` | Matching job reference/descriptor span behavior. Existing uint16 context padding can carry mode 0 legacy / 1 sensor / 2 output-relative without moving fields; derive R once per JPEG job. Preserve tone, gains, tiles and amount meaning. |
| `core/src/fw/aspect/halation.ts` | Optional geometry input for YCC/RGBA reference paths; pass a separate radius span to both red/gold/orange and white spread calculations. Preserve grid/data width. Module selection must retain legacy payload by default for GR IV/old recipes. |
| `tools/halation/halation.c` | Matching radius span for both red and white paths. Existing reserved uint32 context field can carry the policy without changing layout. Derive primary R before enumerating/deduplicating descriptors. |
| `core/src/fw/picture-legacy-code.ts` (new frozen data) | Preserve the three current compiled payload byte strings/lengths and their source provenance before regeneration. Required for exact old-recipe reconstruction; not generated from changed C. |
| `core/src/fw/gr3x/grain-code.ts`, `core/src/fw/gr3x/filmmtf-code.ts`, `core/src/fw/aspect/halation-code.ts` | Regenerate from changed C with recorded source hashes. Never edit base64 by hand. |
| `core/src/fw/gr3x/jpeg-stage.ts` | Texture-policy option, explicit new-versus-legacy payload choice, grain padding/halation reserved mode values, stable MTF→halation→grain→date order. No new stash or exposure hook needed for the fallback. |
| `core/src/fw/gr3x/image-control.ts` | Validate/forward policy; use new native modules only for an explicit WP2 recipe/version. |
| `core/src/fw/gr3x/look-recipe.ts` | Serialize and validate policy/version, absence reconstructing the legacy modules exactly. Reject invalid policy values. This protects old build inspection, which rebuilds and requires byte identity. |
| `core/src/app/engine.ts` | BuildOptions allowlist/types, readback summary and option forwarding, so output-relative is a concrete host option rather than a research note. |
| `examples/gr3x/film-pack-v3/build.ts` | Explicit sensor policy for T-texture and explicit output alternate. Preserve all looks, ratio menu, guard and approved colour coefficients. Root owns approved Gold integration separately; no Portra colour edits. |
| `tools/grain/gen.py`, `tools/filmmtf/gen.py`, `tools/halation/gen.py` | Keep deterministic regeneration; optional tool-path support only if needed. Halation's `readelf` checks may use already installed pyelftools, matching grain/MTF generators, to remove a missing-binutils dependency. |
| `core/test/filmmtf.test.ts`, `core/test/grain.test.ts`, new `core/test/texture-geometry.test.ts`, relevant engine/GR3x round 10 tests | Regression cases below, including recipe compatibility, context ABI and pipeline order. |
| `tools/filmmtf/check.py`, `tools/grain/check.py`, `tools/gr3x/probe-inputs.ts`, `tools/gr3x/picture_stage_probe.py` | Native/reference parity for new guards and policies; update old assertions that non-8-aligned dimensions are refused. Keep canaries, failure paths and legacy checks. |
| New T-texture test card | Same subject 28/35/50, aspect crops, right/bottom 100% tails, grain/halo off/on, old/new policy. Firmware 2.10 only; looks/ratios/guard and recovery instructions preserved. User flashes. |

**Unaffected data:** `grain-tables.ts`, native film menu `films-grain-native.ts`, film defaults/toning amount encoding, Portra colour, film matrices/curves/post matrices, icon data and old round 6 payloads. They must not be regenerated or retuned for geometry. `datestamp.ts` is read for the per-exposure pattern but needs no modification under the authorized fallback. UI preview integration is optional follow-up: existing positional span behavior must stay stable now.

## Meaningful regression cases

1. All current corpus sizes plus all 28 T4 custom sizes; 960 main accepted, 720/160 previews skipped by MTF; odd 5333 rejected; bad stride and allocation failure leave buffers untouched. Dynamic 640×1280 limitation explicit.
2. Full TS/native byte parity on non-flat edge/texture fixtures at 3360, 3000, 5332 and 4800×2700, nontrivial stride and offsets. Aligned-interior results match a separately processed aligned view. Last 4 columns/rows, padding, other planes and descriptor bytes remain exact. Exercise final short strip and the 192-row seam.
3. First primary descriptor plus same-Y whole-buffer alias: apply once to the intended crop. Include invalid-first/valid-fallback and offset pointers; retain actual current dedup semantics rather than assuming every overlap is the same buffer.
4. New geometry gives sensor main step 256 at 6000/4800/3360 and 4000²/3000×4000; output policy retains intended resize attenuation. Preview 720 and 160 use the same job R and stay attenuated. Test preview-only jobs and missing/invalid primary pointers. Native/reference match in all six grain amount/size settings and red/white/gold/orange halo paths.
5. Compare grain RMS/autocorrelation and halo source-pixel radius, with fixed declared fixtures. Do not demand crop byte equality: content-derived seeds change with dimensions. Keep settings 0/off exact and do not alter tone, colour ratio or palette.
6. Legacy recipe rebuild is byte-identical, GR IV unchanged, new policy round-trips through recipe/engine readback, invalid values rejected, and module/context/source hashes match. Full core suite before preparing test firmware; no colour coefficient change for Portra or unaffected films.

## Toolchain status

Global Python has NumPy, Pillow, Unicorn, Capstone and pyelftools. No `ziglang`; PowerShell finds no clang, ld.lld, llvm-objcopy or readelf in PATH. Existing generated versions are clang 21.1.4 (grain), 21.1.0 (MTF), Ubuntu clang 18.1.3 (halation). Builders target ARMv7/Cortex-A9 A32, soft-float, freestanding, no runtime, ROPI/RWPI; MTF uses -O2, grain/halation -Os. Need an existing clang+ld.lld+llvm-objcopy toolchain or an isolated Zig toolchain with these flags, plus readelf or the pyelftools adaptation. Position independence must still be verified by linking at 0x10000 and 0x543f0000. No installation was attempted in this audit.

## Evidence/reproduction

External sibling scripts: `wp2_geometry_audit.py`, `wp2_geometry_audit.mts`, `wp2_corpus_audit.py`, `wp2_dng_meta.py`, `wp2_preview_audit.py`. Run with installed Python and repository `node_modules/.bin/vite-node.cmd`. Outputs here: `geometry-native-corpus.json`, `custom-geometry.json`, `corpus-corrections.json`, `preview-sizes.json`. RTOS SHA256 is `8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67`; native dimensions are original functions, custom sizes are current source, corpus facts are real-file metadata. Copy this small audit package into WP1's stable evidence folder before temp cleanup.

## Root's final authorization (2026-11-09)

The audit above is retained. The concrete implementation is limited to these paths; root owns all reports, approved-Gold reference generation and the hardware test card:

- Create `core/src/color/texture-geometry.ts`.
- Create `core/src/fw/picture-legacy-code.ts` containing the exact three pre-change compiled payloads and provenance.
- Modify `core/src/color/index.ts` only for required geometry exports.
- Modify `core/src/color/filmmtf.ts`.
- Modify `core/src/color/grain.ts`.
- Modify `core/src/fw/aspect/halation.ts`.
- Modify `tools/filmmtf/filmmtf.c`.
- Modify `tools/grain/grain.c`.
- Modify `tools/halation/halation.c`.
- Regenerate `core/src/fw/gr3x/filmmtf-code.ts`.
- Regenerate `core/src/fw/gr3x/grain-code.ts`.
- Regenerate `core/src/fw/aspect/halation-code.ts`.
- Modify `core/src/fw/gr3x/jpeg-stage.ts`.
- Modify `core/src/fw/gr3x/image-control.ts`.
- Modify `core/src/fw/gr3x/look-recipe.ts`.
- Modify `core/src/app/engine.ts`.
- Modify `tools/filmmtf/gen.py` only if required for deterministic generation/tool portability.
- Modify `tools/grain/gen.py` only if required for deterministic generation/tool portability.
- Modify `tools/halation/gen.py` to use available pyelftools for ELF checks and deterministic LF source hashing.
- Modify `core/test/filmmtf.test.ts`.
- Modify `core/test/grain.test.ts`.
- Create `core/test/texture-geometry.test.ts`.
- Modify `core/test/film-recipes.test.ts` for recipe/readback/legacy compatibility.
- Modify `tools/filmmtf/check.py`.
- Modify `tools/grain/check.py`.
- Create `tools/halation/check.py` for new-policy parity; this path did not exist at the base.
- Modify `tools/gr3x/probe-inputs.ts`.
- Modify `tools/gr3x/picture_stage_probe.py`.
- Modify `tools/filmmtf/reference.ts` only for geometry/parity output.

Do not edit `examples/gr3x/film-pack-v3/build.ts` or any film colour source. Root's later test-build tool supplies the new policy. Public option name: `textureGeometry?: 'sensor' | 'output'`; absence keeps exact legacy native payload selection and serialized reconstruction. New recipes explicitly opt in. The output-relative alternative uses aspectSpan and the shared 6000 reference, while the positional legacy preview-span API keeps its old behavior.

Write the meaningful failing regressions before production edits. Capture a representative legacy R10 MTF+grain+halation build before changing modules, then verify exact rebuild/inspection after the change. Compare native/reference non-flat fixtures, not source-text constants alone. The new MTF floor is 960 for this surveyed menu; explicitly exclude unsupported 640-wide custom mains. All 4:2:2 odd widths remain rejected. Keep aligned tails/padding and original descriptors unchanged.

Root is provisioning an isolated Zig 0.15.1 toolchain under ignored `research/gr3-210/toolchain`; do not install a global compiler. Record the actual compiler version, source hashes and link-at-two-address position-independence checks. No device writes, commits, releases or further reverse engineering. Write implementation verification and any concerns to ignored `research/gr3-210/wp2-implementation/report.md`; root updates the concise index.
