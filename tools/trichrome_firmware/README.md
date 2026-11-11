# GR III 2.10 experimental tripod trichrome firmware

This is an actual manual-test firmware candidate built from the GR III 2.10 official file and the existing 20-film v3 pack. It saves the first two continuous exposures normally and composites the third. Native ARM tests and installed hook-chain tests pass with synthetic capture records. Camera startup, real event ordering, processing time, available heap and photo graphic output remain untested.

The candidate is `scratch/trichrome-firmware/fwdc239b.bin`. The adjacent `build-report.json` records its SHA256, source hashes, native entry addresses and container self checks; `patchmap.json` lists every edit. No camera was flashed, and no file was published. The GR IIIx and GR IV have not been targeted by this builder.

## Manual camera test

1. Use a GR III supported by the official 2.10 file. Keep the verified official firmware available as the rollback file. Install this test candidate using the camera's normal firmware-update procedure; flashing is performed manually by the owner.
2. For the first test, select one of the 20 added films, image size **Large**, aspect **3:2**, JPEG or RAW+JPEG, manual exposure, fixed ISO and fixed white balance. Prefocus, then use manual focus so AF updates cannot change the strict settings snapshot. Turn the film's **Grain** and **Halation** off. Disable interval, bracket and composite modes. Use a tripod and a static background with a moving person, hand or object.
3. Select the ordinary continuous drive setting. Press and hold the shutter for three exposures in one continuous release, then let go. Allow JPEG processing to  finish. Expected: photo  1 and photo  2 retain their ordinary film rendering; photo  3 has displaced red/green/blue traces on the moving subject while static content stays sharp. Pictures after the third exposure in the same release are ordinary. The next continuous release arms a new group.
4. Compare all three full JPEGs and their playback previews. Check that the moving subject separates into  temporal color traces and that frame 3's fine texture survives. A stationary three-shot sequence is the static negative control. Another negative control is **Standard**, which must remain ordinary even in continuous drive. Single-shot drive must also remain ordinary.
5. To disable the feature, select Standard/another facto ry look or single-shot drive. A native single-release command clears the pending group. Power cycling clears all state. A new continuous release discards the previous partial group. Use the official rollback file through the camera's normal update procedure when finished; this project does not flash or roll back the camera auto matically.

An identity, settings, orientation, geometry, memory or timing mismatch leaves a normal JPEG. If all three pictures remain normal, report that result to gether with drive, film, image size and capture count: actual exposure-record propagation is an explicit hardware unknown. Do not interpret a no-effect result as proof of successful capture tagging.

## Exact operation and control

`OnReleaseContinuous` at `0x5342c964` arms one owned epoch. `SetShootingInfoResultBeforeExpose` at `0x534322d8` tags its `r2` CommonProperty pointer with exposure ordinals 1, 2, 3. The adapter requires the native continuous drive byte `Common+0x6f4 == 2`, an added film byte `Common+0x77c` in 64..83, identical bytes `Common+0x6c4..0x819` and orientation byte `Common+0xc8` across the group. These exact settings bytes include the known native UserSetting aggregate. There is no guessed exposure counter or arbitrary JPEG-call counting.

The original internal JPEG config builder `0x5350e624`, selecto r `0x5350e114` and dispatch prefix carry the frame-owned Common pointer at `config+0x34`. The JPEG hook `0x535047d4` consumes only a matching, unconsumed capture tag. Queued old records, duplicate calls, unrelated single shots, RAW processing without a real exposure tag, changed settings/orientation, an out-of-order third JPEG and an expired group fail closed. The optional Common override in `0x53510800` conservatively clears the group. The optional-copy method is also used by normal setup; it is not labelled RAW-only. A nonzero source override is the invalidation trigger.

The adapter does not cancel merely when the shutter is released: the third JPEG may still be queued. The native operating-clock wrapper `0x536afc5c` supplies the short elapsed timer; original wrapper execution with only its OS `get_tim` boundary substituted verifies return semantics and high/low word normalization. Existing native UI clock analysis supplies the milliseconds interpretation. Unsigned subtraction handles the 32-bit wrap, tested near `0xfffffff0`. Expiry is 30 seconds and is checked on callbacks. A partial group may retain its bounded pixel allocation until another callback, a new release or power-off; there is no background timer task.

At frame 1, the module reserves owned sto rage for quarter-width, quarter-height R and G planes of main, screennail and thumbnail; this is **1/16 of the area**, not 1/4. Frame 1 sto res R1, frame 2 sto res G2. Both borrowed native Y/C planes remain unchanged by this feature. Frame 3 computes reduced R3/G3, expands the temporal differences with pixel-center bilinear interpolation, and adds the corresponding integer Y/Cb/Cr deltas to  its existing YCbCr4:2:2 pixels. This retains frame 3 detail and gives exact static YCbCr identity. Shared 4:2:2 chroma, integer rounding and clipping mean dynamic blue cannot be promised mathematically identical to  an independent full-resolution B3 plane. All three JPEG picture descripto rs receive the same temporal operation at their own resolution.

There is **no handheld alignment or exposure/WB normalization** in this candidate. Use the tripod and fixed settings above . The deskto p experiment in `docs/trichrome.md` already found material fringes under fractional handheld shifts; more retained pixels did not cure them. This candidate establishes an executable native experiment, not field-validated aesthetics or handheld readiness.

## Memory, ownership and safety limits

Only the test build reserves `0x5580438c`, an otherwise unused word in round 10's documented startup-zeroed gap. The builder guards the extended zero-fill end `0x558043c0` and unchanged native heap setup. No animation state is reused, and the baseline has no shot-animation module. An ato mic0 → initializing → published pointer lazily creates a **524-byte owned adapter**; publication follows complete initialization. It persists until power-off. Pixel sto rage is owned separately and is freed after frame 3 or a reset. No JPEG, encoder, descripto r, settings or borrowed pixel pointer survives as an image buffer: the three temporary capture tags are scalar record addresses used only as matching identities.

For main6000×4000, screennail 720×480 and thumbnail 160×120:

| Allocation | Requested native bytes |
| --- | ---: |
| Two reduced main channel planes | 3,000,000 |
| Two reduced screennail channel planes | 43,200 |
| Two reduced thumbnail channel planes | 2,400 |
| Two signed delta rows per channel, max width 1500 | 12,000 |
| Persistent adapter, including the 100-byte core state | 524 |
| **Peak additional owned request** | **3,058,124** |

The full-resolution preflight actually executes the native allocato r request with the 6000×4000 main stride 6144, rather than inferring a camera heap footprint from deskto p memory. Allocato r overhead, baseline modules, encoder buffers, RTOS task stacks, hardware caches and available free camera heap are additional and unmeasured. The wrapper itself saves 328 bytes of registers/FPU state on the existing task stack, plus ordinary C call frames; SP resto ration and callee-saved integrity are tested. Deskto p render speed says nothing about camera processing speed.

The metadata lock never spins. Contention aborts the group. The processing lock pins sto rage while a callback uses it; cancellation defers free until safe. A cancellation after frame 3 composition has started permits that already-current JPEG operation to  finish and then releases sto rage. The whole frame 3 descripto r set is checked before the first pixel write: format1, valid multiple-of4 dimensions 16..6000, stride bounds, nonzero-overflow-safe RAM ranges above `0x5d000000`, height/chroma coverage, zero crop origin, matching group geometry and nonoverlapping Y/C planes and pictures. The main picture must be 3:2; thumbnail 4:3 remains valid. Unsupported crop origins and dimensions produce a normal frame 3. No full sensor descripto r is edited in place and no speculative sensor/ISP patch is installed.

The experimental baseline disables **only added FilmMTF** to  isolate this operation and reduce latency/heap competition. It preserves the v3 film color/to ne and 20-film controls, existing Grain/Halation/date/end-screen features and their native hook chain. The shared default pack is unchanged. The no-MTF baseline hash is pinned to `0eedc01b7f61cee64d6228978b0f99a01090a49491d6cb103dbfee4a3cc4fa59`. The five hook words plus appended code/record/checksum and RTOS size field are the entire additional decoded change; `selfCheckGrown` checks every existing byte outside those declared ranges.

## Reproduce and inspect

From this worktree in PowerShell, with Python containing NumPy, Pillow, Unicorn, Capsto ne, pyelfto ols and ziglang, and the reposito ry's isolated npm dependencies installed:

```powershell
$env:GRMOD_GR3_FIRMWARE = 'C:/Users/Anto ine/project/grmod-film/scratch/video-firmware-high-rate-2026-11-01/original/fwdc239b.bin'
npm test
python to ols/trichrome_firmware/build_baseline.py
python to ols/trichrome_firmware/trace.py
python to ols/trichrome_firmware/check.py
python to ols/trichrome_firmware/check_camera.py
node node_modules/vite-node/vite-node.mjs to ols/trichrome_firmware/build.ts
python to ols/trichrome_firmware/check_installed.py
python to ols/trichrome_firmware/render.py
```

`build_baseline.py` reads the shared builder without editing it, makes an exact checked empty-MTF-Set transformation in ignored scratch, records all source/cube/end-screen hashes, and invokes the existing builder. `build.ts` accepts only the exact official GR III2.10 source and pinned no-MTF baseline, guards original native APIs, resolves prior hooks only inside the baseline's appended RTOS, compiles a module with no writable RTOS globals, grows by a whole container frame, repacks, decodes and reads back every patch and module byte. All 23 container self checks must pass.

The focused evidence is in `scratch/trichrome-firmware/`:

- `native-lineage-verification.json`: unchanged original JPEG config/record lineage, drive setter/getter and native clock-wrapper execution. Synthetic objects; not a camera event trace.
- `native-core-verification.json`: independent integer parity, exact static identity, motion, stride padding, allocation failure, range/crop/alias rejection, rearming and deferred cancellation. Heap prefix/tail sentinels and unmapped surrounding pages detect overrun and use-after-free.
- `native-adapter-verification.json`: actual ARM adapter/hooks on synthetic exposure records; arm/source/film/settings/orientation/geometry/duplicates/order/expiry/clock-wrap failures, full register/FPU/flag/SP preservation and full-resolution allocato r preflight.
- `installed-hook-verification.json`: loads the **actual candidate RTOS**, enters its installed addresses, runs prior baseline orientation and JPEG wrappers, executes the original config builder, checks all three pictures against the independent reference and reaches the original native+4 continuations.
- `visual/native-reference-comparison.jpg`, `visual/native-reference-motion100.jpg`, full lossless PNGs and `visual/manifest.json`: 6000×4000 integer-reference render from one read-only real still with explicitly authored geometric motion. Source hash unchanged and no EXIF copied. This is controlled synthesis, not a captured burst or camera output.

The official rollback input SHA256 is `d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4`. The corresponding original RTOS SHA256 is `8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67`. No original photo  or official firmware is modified by these scripts.
