# WP12 — desktop film-detail implementation

Updated 2026-11-09. User-authorized brief: `BRIEF.md`, WP12. No questions or approval pause. The read-only design is `research/gr3-210/wp12-desktop-mtf.md`, SHA-256 `1ed82633c5b629cbd79773e8998e164044300d0d989e4855f27ea36d5130241e`.

## Fixed preceding round

The completed T-colour/T-texture/return packet remains immutable under `research/gr3-210/test-session/ready`. Before desktop edits, root saved 168 exact source files, the tracked diff and all untracked source changes under `research/gr3-210/round1-source`; all 138 build-source LF hashes match. Snapshot manifest SHA-256: `d523e4a6ae50768eb4414d3d95c9118373369ecea4cf1fa75038b804e360779d`.

The whole-project reference search is `research/gr3-210/wp12-ui-search.txt` (139 matching source/document lines, normal repository ignore rules; frozen research caches excluded). All thirteen paths below were verified. This is a new UI feature, not a rename or native refactor.

## Concrete design

- Optional per-film **Film detail (MTF)** switch in the existing Recipe. Only literal true persists/sends; Off is absence. No stock colour/default retuning or automatic Sharpness/Clarity edits.
- Optional build-wide texture policy: existing/absent, sensor, output. Preserve absent legacy recipes. Copy summaries show inspected MTF/policy without a new modified-firmware editor/importer.
- Session-only original JPEG Blob plus explicit stored dimensions/orientation. Existing proxy persistence stays unchanged. Bundled/restored proxies cannot supply original-pixel detail.
- Dedicated image-preview worker: colour → MTF → halation → grain, in stored coordinates, then display orientation/downsize. It must not block the firmware worker/heartbeat or show stale results after source/slot/family/settings changes.
- Full-source rendering is the complete first path. The optional ROI optimization is deferred; root's bounded phase proof does not establish halo/grain ROI context.
- Match guards to the selected native module: absent policy keeps width≥4096 and both dimensions eight-aligned; explicit policies use even width≥960 and aligned-prefix processing. Preserve alpha, untouched tails and old no-MTF/absent-policy proxy output.
- Original JPEG decode must be proved for EXIF orientations, including mirrored ones, rather than relying on browser `imageOrientation: none`. Reduced/unknown/unsupported source and released-original states are visible and honest. No silent upsampling or invented camera-main provenance.

## Exact file-by-file change manifest

| File | Action / responsibility |
|---|---|
| `ui/src/store.ts` | Modify recipe/policy state, canonical persistence, build requests/readback labels and session-only original source/generation actions |
| `ui/src/library.tsx` | Modify existing Recipe switch, summary and factual shared-response/native-control note |
| `ui/src/pages.tsx` | Modify global texture/geometry controls, async preview status and full-pixel before/after loupe |
| `ui/src/preview.ts` | Modify typed frame resolver, pure render stages, lazy worker client and stale-result handling; preserve colour math |
| `ui/src/preview.worker.ts` | Create dedicated image rendering worker/protocol; no firmware or host I/O |
| `ui/src/pixels.ts` | Add preview-only JPEG geometry/orientation normalization; leave end-screen helpers intact |
| `ui/src/i18n.ts` | Add matching English/Chinese labels, meaningful limits/status and Copy labels |
| `ui/src/styles.css` | Add only incumbent geometry/status layout, responsive wrapping and preview-pane height handling |
| `core/src/color/filmmtf.ts` | Add RGBA delta adapter and explicit legacy/new preview eligibility; reuse unchanged kernel |
| `core/src/color/index.ts` | Export the small MTF preview API through the existing colour namespace |
| `core/test/gr3x-ui.test.mjs` | Add meaningful real state/build/persistence/family/Copy regression cases |
| `core/test/filmmtf.test.ts` | Add non-flat adapter/oracle, alpha/tail/no-op/guard cases |
| `core/test/desktop-preview.test.ts` | Create pure geometry/orientation/generation/render-contract regressions |

Ownership: root implements `core/src/color/filmmtf.ts`, its barrel export and `core/test/filmmtf.test.ts`; the camera UI agent owns the other ten files. Root also owns this document/index, final review and browser verification. Extra paths require an exact updated manifest before edits; the implementer can ask root, never the user. Agreed API: `filmMtfPreviewApplies(width,height,policy?)` and `filmMtfRgba(data,width,height,policy?)`, with optional sensor/output policy and absent legacy behavior. The adapter returns false for unsupported/no-op guards, true for an applied filter even when a flat fixture has zero delta.

## Verification and boundaries

Write meaningful failing regressions before implementation: lost MTF flag/policy on restore, MTF-only build request, family isolation, malformed values, original/proxy states, orientation, wrong-size legacy processing, stage order and stale results. The RGBA adapter compares the established YCbCr kernel's changes, preserves alpha/exterior bytes and does not replace untouched colour with a lossy 4:2:2 round trip.

Run targeted checks, core typecheck/full suite, UI typecheck/build, and one real wide/narrow browser interaction check with an attached original and a proxy-only restoration. Exercise keyboard Switch/disclosure, busy/cancel states, stale slot/source responses and actual-pixel loupe. Do not repeat native C/firmware emulation without a new concern; no native payload or colour source changes are authorized.

No edits to film-look data, native C/generated payloads, Engine schemas, look-recipe serialization, firmware worker/client, components, sealed packet, references or previous round source snapshot. No release, push, commit or device operation. Preserve all completed artifact hashes.

**Kill:** keep the working CLI and stop the desktop feature if optional-state/legacy compatibility, native eligibility/order, stored-orientation original rendering or responsive interaction cannot be established. Do not substitute reduced pixels, retune colour or invent native provenance to pass a gate.

## Settled result

The implementation satisfies the declared first-path gates. Separate adapter and UI reviews have no remaining concrete findings. Final source-stable checks: **263 tests pass, 175 skip** (missing private fixtures), core/UI typechecks pass, production build passes, diff check is clean. The final ten-file implementation record is `research/gr3-210/wp12-implementation/implementation.json`, SHA-256 `c59f4e69ef1fa11897982a0ccdbd43b09e8cfe2663ecb6723fb748fd7b871e6d`; the complete thirteen-file browser/source manifest is `research/gr3-210/wp12-browser/browser-manifest.json`.

Actual Edge verifies a 24 MP source, explicit main confirmation, physical 1:1 at the supported minimum window and DPR 1/2, keyboard controls, cancelled source/slot results and proxy-only restoration. A browser-found app-scale omission in the incumbent loupe was corrected within the owned paths before final checks. Decode serialization prevents overlapping large-raster allocation inside one renderer; running compute jobs terminate on cancellation. Production uses a classic worker. Separate actual decoder checks cover no-EXIF and EXIF 1–8 with independent full-pixel orientation permutations.

The old colour helpers and proxy-filter branch remain unchanged. Per-film state is opt-in, colour/defaults are not retuned, ROI is deferred, and camera origin remains an explicit operator declaration. All thirteen sealed packet file hashes were reverified with the same session-manifest hash. No commit, release, push or device operation occurred.
