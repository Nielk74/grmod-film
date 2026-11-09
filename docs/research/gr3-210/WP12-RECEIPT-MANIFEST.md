# WP12 — portable host build receipt

> Historical stage record. Firmware/replay environment requirements and current verification limits are qualified in [the shared index](../../GR3_EXPLORATION_REPORT.md). Packet-wide hash assertions below describe the original snapshot; the card metadata was intentionally revised later.

Date: 2026-11-09. Base `db76c9b42f85d657a760d07af97735854f253c57`. The existing-evidence audit at `research/gr3-210/wp12-build-receipt-01/REPORT.md` permits an output-bound host recipe receipt without worker/native changes. It does not prove a byte-identical rebuild. This is a separately authorized product implementation, with no user questions or approval pause.

## Preserved preceding epochs

The camera packet and colour/native/reference assets stay fixed. The completed thirteen-file desktop feature is preserved in `wp12-source-final`; the later one-file worker-constructor fix is preserved in `wp12-dev-bootstrap/engine.verified.ts`. This new epoch may extend the specific UI/test paths below while retaining those exact prior overlays and their verified evidence. It does not revise any sealed firmware or completed image round.

## Exact file manifest — declared before edits

| Owner | File | Change |
|---|---|---|
| Receipt implementer | `ui/src/build-receipt.ts` (new) | Pure, versioned owned build-argument snapshot and portable receipt encoding, deterministic recipe digest, input/output hash and summary checks |
| Receipt implementer | `ui/src/store.ts` | Capture the exact recipe before confirmation/directory awaits; submit the same owned arguments; export receipt beside supported modified folder output with verified writes and explicit partial-failure handling |
| Receipt implementer | `ui/src/app.tsx` | Use the existing export affordance with clear supported-scope firmware/recipe label and description |
| Receipt implementer | `ui/src/i18n.ts` | English/Chinese receipt/export and partial-failure text |
| Receipt implementer | `core/test/build-receipt.test.ts` (new) | Meaningful codec/ownership/hash/unsupported-input tests and exact host API replay control |
| Receipt implementer | `core/test/gr3x-ui.test.mjs` | Real store-flow tests for asynchronous mutation/ownership, complete export and partial failure; unsupported paths retain prior behavior |
| Root | This manifest, `PLAN.md`, `PRODUCT.md`, `docs/GR3_EXPLORATION_REPORT.md` | Scope and concise verified outcomes |

All implementation evidence, scripts and source snapshots remain ignored under `research/gr3-210/wp12-build-receipt-implementation/**`; the preceding audit remains immutable. No other production/test path, config, dependency, endpoint, worker protocol, core/native/generated file or colour source may change. The change is not a cross-file rename/refactor.

## Product and data contract

- Scope only modified **GR III / GR III HDF 2.10 folder exports**. Stock, bridge, GR IIIx/GR IV and card-writing paths keep their existing behavior. No agent invokes a real directory picker/device write; integration/browser writes are in-memory fixtures.
- Pair firmware with a descriptive, output-hash-specific `.grmod.json` receipt, avoiding a misleading fixed-name companion from an older export. No output is published or uploaded.
- Snapshot all four actual builder argument groups into private owned copies before asynchronous confirmation/directory selection. Preserve ordering, omitted keys, explicit false values, compiled coefficients and every submitted binary icon/end-screen asset. Pass those same owned copies to the existing `engine.build`; never rebuild the receipt from later state/history, labels or a refit.
- Include official-input name/version/model, byte length and independently computed SHA-256, checked against the captured `FirmwareInfo`; recompute the returned output SHA-256/length and cross-check the builder's hash and successful checks.
- Use an explicit portable value/binary codec and a deterministic recipe digest. Preserve meaningful typed-array values and byte views; do not use `structuredClone`, silently drop/truncate unsupported data, or depend on later external files. Bound the encoded receipt below the existing host per-file limit and report an oversize/encoding failure before writing the pair.
- Include receipt/codec versions, application version and **exact builder revision: null** when unavailable. Original CUBE/XMP source text is explicitly excluded; submitted fitted coefficients are included. Rebuild verification remains **not performed** in the receipt; any local test replay demonstrates only its pinned control, not a general guarantee.
- Whitelist the result summary: reported/decoded hashes, checks, changed frames/bytes, ranges and built ratios. Do not dump derived features/factory picture arrays or include official firmware bytes, full source/preview photographs, host tokens, local paths or card details. Submitted custom icons/end-screen pixels remain necessary recipe assets, disclosed in the export description.
- Verify each file write using the existing returned byte length/hash checks. A two-file export is not atomic: report a partial outcome explicitly, do not claim complete success, delete/revert firmware, retry a write without authorization, or change card handling if the companion fails.

## Verification and kill criteria

Add failing targeted tests first. Verify independent known-value/byte-view round trips, mutation isolation across asynchronous waits, absent/false options, source/output hash mismatch, unsupported/oversize rejection and honest partial-export results. One pinned real GR III 2.10 control must rebuild from independently decoded submitted receipt arguments to the same output hash; this is a host control only. No photo/image generation or camera work is needed.

Root/reviewer inspect semantics and the supported-scope gate, then run applicable targeted tests, core/UI typechecks, production build and one settled full core suite. Actual Edge must exercise the changed export affordance and mock host writes, including the supported minimum window; no real shell/device writes. Record that the sealed packet remains fixed and preserve the new six-file source overlay.

**Kill/revert this candidate:** exact request/output binding needs transport/native changes; codec loses submitted values/assets; the control cannot replay; unsupported/card paths change; a partial export is reported as complete; or the feature cannot meet the existing browser/type/build gates. Do not broaden this into an importer, firmware editor, project migration, signing system, source archival service or native provenance patch. A receipt is host build evidence, never proof of installation, author authenticity or photograph provenance.

## Verified outcome — closed

All six declared paths are implemented and independently reviewed with no open integration/codec finding. A real official-input control independently decoded the submitted JSON and rebuilt through a fresh Engine to the same `cc2d3fe9…c8b2` output hash. Actual Edge at 980 × 640 verifies the accessible export action, complete pair and distinct receipt/firmware failure outcomes through an in-memory host. Its actual old/new request groups and 31,564,840-byte firmware output match exactly (`68523b40…9c904`); its 118,057-byte companion independently decodes to the outbound arguments with a matching recipe digest. Production firmware/preview workers and CSS remain byte-identical.

Core/UI typechecks, production build and the settled full suite pass: **281 passed, 175 skips (including GR IIIx/IV fixture paths)**, 55.81 seconds, with real receipt replay enabled. All thirteen sealed packet hashes remain exact. The six-file source overlay is `research/gr3-210/wp12-build-receipt-implementation/source-final.json`, SHA-256 `58e9a4b134d3362a63cf4f12edefc4347f09a87156416684967f04f66b97e6de`; the composed build-source/config pins match the prior epochs. The verification server was stopped. No release, real export, device operation or image/colour/native change occurred. No kill occurred; retain the feature and stop this implementation round.
