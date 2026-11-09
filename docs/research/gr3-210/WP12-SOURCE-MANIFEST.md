# WP12 follow-up — informational preview input readback

Base: `db76c9b42f85d657a760d07af97735854f253c57`. **Closed no-go: the six-file implementation below was not executed.** The ignored bounded prototype is `research/gr3-210/wp12-preview-source-01`. Independent review triggered the declared malformed-input kill; the completed desktop MTF sources remain fixed.

## Preserved preceding result

The completed desktop MTF round has 263 passing tests, 175 private-fixture skips, passing core/UI typechecks/build and actual browser gates. Its thirteen exact source files are preserved under `research/gr3-210/wp12-source-final/files`, as an overlay on the earlier round-one snapshot. Overlay manifest SHA-256: `4125724f23681057b503622fd3d42b69ec563259d40769220f2941bc47077fda`. The sealed camera packet, its manifests and preceding evidence remain fixed.

The source-consumer search covered `ui`, `core`, `tools` and `docs` for `PreviewOriginal`, `previewJpeg`, `loadPreviewFile` and `previewOriginal`. There is no rename or native refactor. The six existing paths below are the complete implementation boundary.

## Concrete behavior

- Within the existing **Preview source and geometry** disclosure, show **Standard recorded**, **other/custom control recorded**, or **not recorded/recognized** for a newly attached supported JPEG. Keep the text informational, with no success badge or verified-origin claim.
- A short note explains that colour comparisons should use a Standard JPEG and that camera adjustments or later edits remain in the source. Metadata does not prove neutral settings, untouched pixels, installed firmware, selected payload or editing history. A copied-Standard-metadata counterexample must remain valid as a recorded-metadata result.
- Parse only the actually established JPEG/EXIF/Ricoh MakerNote layout, with explicit byte order, type/count, offset-base and container bounds. Missing, unsupported, malformed, duplicate or ambiguous records return unknown without changing image decoding or geometry eligibility.
- Derive the readback from the currently attached bytes. Keep it private/session-only with the original Blob; source/sample/family changes and proxy-only restoration clear it through the existing ownership lifecycle. Do not infer identity from filenames, Make/Model or Software.
- Generic artistic previews remain allowed. Classification never selects a model/film, applies or bypasses a transform, rejects a photo, changes MTF/texture settings, alters build requests, retunes coefficients or persists source metadata.

## Exact implementation manifest

| File | Change |
|---|---|
| `ui/src/pixels.ts` | Add a pure bounded recorded-control classifier and a small optional original-source information type; preserve every existing decoder/geometry/orientation helper body and input bytes |
| `ui/src/store.ts` | Read original bytes once for geometry and information, then attach the information atomically to the current session original; retain all source/family generation checks and persistence/build behavior |
| `ui/src/pages.tsx` | Render the informational readback/note in the existing source disclosure, without a new status gate, panel, interaction or pixel/render change |
| `ui/src/i18n.ts` | Add matching English/Chinese factual labels and concise interpretation copy |
| `core/test/desktop-preview.test.ts` | Add meaningful parser positive/negative, container-bound, duplicate, unsupported and input-preservation regressions using synthetic metadata fixtures; retain prior geometry/render/loupe tests |
| `core/test/gr3x-ui.test.mjs` | Extend the existing pixels mock and verify current-source lifecycle, proxy/family clearing, no persistence and identical build requests |

The source-prototype agent implements these six paths after review; root owns this document/index, final review and production browser checks. Extra paths require a concrete updated manifest before edits. Existing styles, components, colour math, worker, firmware/core schemas, native/generated sources and film assets are outside scope.

## Gates and kill

Write failing parser/state regressions before production changes. Match the independently checked prototype on its supported fixtures. Test recorded metadata separately from trustworthy pixel provenance; unsupported metadata must never be promoted to Standard or block generic previewing. Check source replacement/release/restart and build/persistence invariance. Prove existing decode/render helper bodies and colour payloads unchanged.

Then run targeted regressions, the full applicable core suite with the official GR III fixture, core/UI typechecks, production build and diff check. Review the parser/state/copy independently and verify actual production browser labels for real recorded Standard, other/custom and unknown inputs, including source replacement and proxy restoration. Recheck the normal original-pixel render/loupe after the disclosure change; no new native/firmware run is justified.

**Kill:** retain the already verified desktop feature without this readback if bounds/layout cannot be established, unknown metadata is overclaimed, source ownership or build/persistence isolation changes, or the wording suggests neutral/rendering/build proof. No additional native tracing, broad EXIF library or camera patch follows this failure. This is an information improvement, not a colour correction or firmware provenance solution.

## Closing result

The selected ImageTone path is bounded, but the prototype does not validate unrelated field spans/types or the root next-IFD link. Four independently constructed malformed records still return Standard recorded. This violates the stronger every-field-bound / malformed-to-unknown manifest contract; the initial seven real fixtures and 21 passing controls do not override those failures. The writer withdrew its production recommendation. No correction, broader validator or implementation followed the kill.

The recorded-value lesson remains useful: use Standard JPEGs for judging the colour transform, and do not treat recorded Standard metadata as neutral settings, untouched pixels, editing-history or build proof. The copied-metadata control demonstrates that distinction. Source report SHA-256: `37abe8a1eebef06497804fe57ae3bbf72913371957bbf0d716c8c4a822652b3f`; independent report: `ec8e89251a44be9e4476727fc6defc5ae949adebfe876d379b29c348ebfe11c0`. All thirteen preceding desktop source pins and seven originals remain unchanged. This document preserves the unexecuted concrete design, not an active implementation queue.
