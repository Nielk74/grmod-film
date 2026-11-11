# Face fill manual-test firmware

This produces one **experimental RICOH GR III 2.10** firmware on the twenty-film v3 pack. It adds face-local fill before the existing JPEG picture chain and a one-input skin chroma keeper on Astia, Nostalgic Neg, Kodachrome 64 and Gold 200. It is a manually testable prototype, not hardware-qualified firmware. GR IIIx, GR IV and other official input versions are rejected.

The fixed fill LUT targets +0.85 EV on a gray sRGB-like response, with a broad warm-skin Cb/Cr gate, a soft oval and RGB headroom protection. Overlapping faces use the maximum weight, rather than stacking lift. The keeper contracts Cb/Cr toward neutral by at most 77/256, approximately 30%, under the same mask. This does **not** reconstruct pre-film colour or restore the stronger matrices preceding `95ba6de`. Existing film colours, tone curves and recipes remain unchanged. Extra FilmMTF is disabled in this test baseline by emptying its set in an isolated copy of the baseline builder; the shared/default builder is unchanged. Existing halation, grain and date stages remain chained after the face module.

## Manual test

The generated file is `scratch/face-fill-firmware/fwdc239b.bin`. Check its hash against `build-report.json` before copying it to a card. The candidate from this source is **38,433,372 bytes**, SHA-256:

`fbb5b129766e313b54694ba5d1042a861d2cee49d3121653de4d1cba02030eca`

1. Use a **GR III**, with the existing GR Mod installation/update procedure. Keep the pristine official **2.10** file and the currently working firmware separately. The exact rollback input used here is `C:/Users/Antoine/project/grmod-film/scratch/video-firmware-high-rate-2026-11-01/original/fwdc239b.bin`, SHA-256 `d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4`. This build does not establish whether a camera already on newer firmware will accept a downgrade; do not assume it will.
2. Follow [Ricoh's GR III update procedure](https://www.ricoh-imaging.co.jp/english/support/digital/gr3_s.html): fully charged battery, update file at the SD card root, power off, then start while holding MENU and follow the update prompts. Do not interrupt the update. That page now distributes newer official firmware; use the preserved **2.10** input for this experiment, rather than substituting its current download. Reinstall the saved known-working file with the same procedure to roll back, subject to the camera's own version checks. No camera/card writes are performed by these tools.
3. Start with still JPEG **L / 3:2 / no digital crop**, single shot, Auto-area AF, **Face/Eye Detection On**, and a custom film. Half-press and confirm that the camera shows a face/eye box before taking the picture. The relevant AF settings are described in [Ricoh's GR III manual](https://www.ricoh-imaging.co.jp/english/support/man-pdf/gr-3.pdf). The kernel runs for film IDs 64–83 only. **Standard bypasses the new stage** and is the immediate control. It adds no new menu or adjustable strength.
4. Photograph a face by a window, a daylight face and a face under dim warm light, holding exposure and white balance fixed. Expect lifted face midtones and a gentler skin chroma on the four keeper films, with the background retaining film contrast. Also shoot a non-face scene, neutral objects, bright skin highlights, two faces and a deliberate silhouette. The feature may be undesirable for the silhouette.
5. For a same-film A/B, compare the no-extra-MTF baseline `scratch/face-fill-firmware/baseline-no-extra-mtf/fwdc239b.bin` with this candidate, keeping exposure, white balance and recipe fixed. Face/Eye Detection Off is a useful additional test, but Standard or the baseline is the definitive bypass: this work has not observed the AF hardware's scheduling live. A valid populated B list drives the effect; an empty list does not.
6. If a custom-film portrait shows no effect, first check L/3:2/no crop, the visible face box and a populated **current/B** `0x040b` result. The three old portrait JPEGs used below have empty camera face lists; they cannot demonstrate camera detection. Missed, unsupported or invalid records deliberately leave the picture unchanged. Keep sample JPEGs and note the film, AF setting, exposure and whether the face box was visible.

The main picture must be 6000×4000. Supported same-ratio screennail/thumbnail descriptors, with zero offsets, are scaled independently from that coordinate system; main and screennail are tested together. Nonzero offsets, other aspects, smaller main JPEGs, digital crops, odd/unknown formats and thumbnail-only requests are unsupported. An unsupported thumbnail can remain unchanged. RAW development is **unsupported/unverified** and may apply a valid saved face record; it is not claimed to no-op. No timing, burst membership, power-loss recovery or on-camera quality claim follows from desktop emulation.

## Native source evidence

All fixed addresses are pinned to the pristine GR III 2.10 RTOS SHA-256 `8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67`. `trace.py` executes original firmware bytes, with explicit boundary stubs documented in its report:

- Original capture `0x5345133c` writes the `CommonProperty*` supplied as its third stack argument. Header `+0x38d50` contains encoded image dimensions. A count `+0x38d68` and B count `+0x38d6c` are u16; rectangles use 64-byte records at `+0x38d70` and `+0x38ff0`. B uses the current detector ring; A uses the preceding ring. Native `0x53450a8c` resets/repopulates the current result. Probes seed stale count 9 and previous A count 3, then observe B counts 0/1/9 from synthetic current results. Native 16.16 sensor coordinates map to encoded 6000×4000 coordinates before EXIF rotation.
- The small capture wrapper clears **only B count** before the original function. A skipped result branch therefore cannot inherit the old B count. No persistent face cache, live exposure pointer, allocation or new shared RAM word is introduced. Rectangles are validated and copied onto the face module's bounded stack before processing.
- Original JPEG config builder `0x5350e624`, selector `0x5350e114` and dispatch prefix `0x5351eb6c` prove macro ID 6's config is `frame+0x9b8`; config `+0x34` is `[frame+0x44c8]`, the job's CommonProperty pointer. `+0x3c..+0x48` are its picture descriptors. The existing frame constructor allocates the per-frame Common object. The physical capture-to-render queue has not been observed on a camera: the end-to-end probe supplies the same owned record to original capture and the actual builder, then runs the installed chain.
- Ordinary Develop's vtable `0x53c627b8` selects setup `0x535059ec`. Native Execute/setup prefixes store config `+0x34` at development context `+0x82d0` and set format `+0x82ac` to zero. Native look read `0x536db7d8` then uses **direct Common `+0x77c`**. The probe deliberately sets the secondary `+0x71248` look differently. Movie records (`+0x44`) are excluded; that byte is not a RAW-development discriminator.
- Native MakerNote reader `0x535ee208` and writer `0x53605ef4` prove the `0x040b` layout. The original reader overwrites slot zero with each decoded rectangle, retaining the last there; this existing behavior is recorded, not repaired. The writer correctly strides 64 bytes and serializes A then B contiguously. RAW redevelopment of multiple saved faces remains especially unverified.

The module consumes native planar Y + interleaved CbCr 4:2:2, not RGB. Its lift is a gray-response approximation in gamma-coded Y; measured RGB luminance is reported separately. Descriptor `+0x0c` is opaque and ignored, matching the existing grain module's acceptance convention. Width/height/stride/chroma height, alignment, pointer ranges, plane extent and all cross-picture aliases are checked directly. It performs no allocation, bounds face count at ten, deduplicates exact plane aliases, rejects partial aliases before any write and flushes/cleans aligned cache ranges. Both wrappers preserve volatile registers and NZCVQ flags; the existing baseline chain's original `mov ip,sp` handover is verified.

## Reproduce on Windows PowerShell

Run from this isolated worktree. Text IO uses UTF-8; source photos and official inputs remain read-only. Private portraits are never uploaded.

```powershell
python -m venv scratch/face-fill-env
& scratch/face-fill-env/Scripts/python.exe -m pip install -r tools/face_fill_firmware/requirements.txt
npm ci
$env:GRMOD_GR3_FIRMWARE = 'C:/Users/Antoine/project/grmod-film/scratch/video-firmware-high-rate-2026-11-01/original/fwdc239b.bin'
npm test
npm -w core run typecheck
npm run build
& scratch/face-fill-env/Scripts/python.exe tools/face_fill_firmware/build_baseline.py
& scratch/face-fill-env/Scripts/python.exe tools/face_fill_firmware/gen.py
& scratch/face-fill-env/Scripts/python.exe tools/face_fill_firmware/check.py
& scratch/face-fill-env/Scripts/python.exe tools/face_fill_firmware/trace.py 'C:/Users/Antoine/project/grmod-film/scratch/video-firmware-high-rate-2026-11-01/original-rtos.bin'
& node_modules/.bin/vite-node.cmd tools/face_fill_firmware/build.ts -- $env:GRMOD_GR3_FIRMWARE
& scratch/face-fill-env/Scripts/python.exe tools/face_fill_firmware/hook_check.py
```

The isolated baseline builder uses the shared read-only Pro 400H cube and eight `.bgr` end screens listed in `baseline-report.json`. Its pinned baseline hash is `0eedc01b7f61cee64d6228978b0f99a01090a49491d6cb103dbfee4a3cc4fa59`. `gen.py` links at two origins, compares exact code bytes and rejects runtime imports/data. The installer pins the official/container/RTOS/baseline/module/source hashes, guards both entry words, appends one 24,576-byte RTOS frame and reads the rebuilt container back. Its complete diff audit permits only the two entry words, RTOS size field and appended frame; all other baseline bytes must match after the insertion. No official binary or generated candidate is tracked.

`check.py` passes **41 native pixel cases + 4 capture-clear cases**: independent byte parity, no face/Standard/invalid inputs, overlap, mixed faces, main+screennail scaling, active rows/padding/guarded writes, plane and cross-picture aliases, invalid alignment/end pointers, nonzero offsets, opaque descriptor fields, saturated/neutral/dark/clipped pixels, immutable metadata/context, cache alignment and callee-saved registers/stack. `hook_check.py` runs **five actual capture → native config builder → installed JPEG-chain cases**, plus exact wrapper register/flag checks. It also forces an existing grain allocation to fail and verifies a recoverable result. Cache/device/allocator/platform/time boundaries are stubbed; ISP, JPEG compression and live scheduling are not emulated.

The full suite with the official GR III fixture passes **237 tests / 175 skipped / 0 failed**, and core TypeScript and the production UI build pass. Other unavailable firmware fixtures account for the skips. The parent independently reran the suite and probes during review. Existing Node preview URL warnings and Vite `host.js` notice remain unchanged.

## Native photo evidence

After the earlier desktop experiment in `tools/face_fill/README.md` has generated its summary and real YuNet detections, run:

```powershell
& scratch/face-fill-env/Scripts/python.exe tools/face_fill_firmware/photos.py
```

This executes the actual compiled ARM kernel on each 6000×4000 source converted to full-range BT.601-like YCbCr422, compares every native output byte to an independent NumPy reference, and verifies source hashes before/after. Real recorded YuNet boxes stand in for current/B because these old shots contain empty camera results. The desktop model/source provenance remains in the earlier experiment. The photo demo enables keeper explicitly to show combined behavior; actual firmware enables keeper only for the four listed films. It is not evidence of true ISP transfer characteristics or native camera detections.

Output root: `C:/Users/Antoine/.codex/worktrees/face-fill-skin/grmod-film/scratch/face-fill-firmware/photos/`. Open each of `R0000030`, `R0000005`, `AK000164` with suffix `-native-sheet.jpg` and `-native-crop-100.jpg`. Columns are the YCbCr422 basis, actual ARM fill+keeper and earlier RGB desktop fill. The crops are 768×768 native pixels, one source pixel per crop pixel. Full native outputs have suffix `-native.jpg`; no source EXIF/GPS is copied.

Linear sRGB luminance on the same independent original-image skin core (`desktop mask >166/255`) gives:

| Source | Core median lift | Core p90 lift | Newly clipped RGB pixels |
| --- | ---: | ---: | ---: |
| R0000030 daylight | 0.721 EV | 0.862 EV | 0 |
| R0000005 window | 0.774 EV | 0.850 EV | 0 |
| AK000164 night | 0.753 EV | 0.839 EV | 0 |

`photos/report.json` pins the actual module hash, source hashes, rectangles, native/reference equality and measurements. The earlier desktop sheets retain multi-face, detector misses/false positives, no-face and mask evidence. This small portrait selection does not establish skin-tone diversity. Warm clothes, wood, lips or hair inside a false face box can pass the colour heuristic. Face misses, lighting shifts and unusual skin colour remain manual-test cases.
