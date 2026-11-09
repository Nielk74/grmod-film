# WP12 — distinguish film identities in Menu order

Date: 2026-11-09. Base `db76c9b42f85d657a760d07af97735854f253c57`. The separate UI/build audits conclude **reuse existing reordering**. One concrete P2 remains: two legal identical camera names hide approved-versus-authored source identity in Menu order rows and accessible actions. Source: `ui/src/store.ts`'s `lookName`, and `ui/src/pages.tsx`'s `LookOrder` row/action rendering. No detached payload or builder defect was found. Audits: `research/gr3-210/wp12-film-order-ui-01/REPORT.md` and `wp12-film-order-build-01/REPORT.md`.

Parent: closed approved-Gold eight-file overlay `research/gr3-210/wp4-approved-gold-ui-implementation/source-final.json`, SHA-256 `919a5d81e300105809e86bef98a127a2fd7e2ea2bed17be352467df60255636d`. Its 169 composed code/config pins, 296/175 suite, exact coefficients and sealed packet remain the reference.

## Exact three-file source/test manifest — before edits

| Owner | File | Change |
|---|---|---|
| Implementer | `ui/src/store.ts` | Pure read-only row metadata selector joining existing menu key to stable film-slot and requested preset identity; preserve `lookName`, all state/schema/operations/output |
| Implementer | `ui/src/pages.tsx` | Secondary visible identity and matching accessible action/movement names, using existing styles/labels and bounded subtitle markup; keep editable camera name and current controls |
| Implementer | `core/test/gr3x-ui.test.mjs` | Meaningful duplicate-name, slot/source join, reorder/hide/remove/restore and unsupported-scope controls; assert payload/state/guard preservation |
| Root | This manifest, `PLAN.md`, `PRODUCT.md`, `docs/GR3_EXPLORATION_REPORT.md` | Before-edit plan and verified decision |

Root captures all three raw preimages first. Implementation evidence and the final three-file overlay belong under ignored `research/gr3-210/wp12-film-order-implementation/**`. Implementer owns those three files and that directory, excluding root-owned before/browser/final-gate artifacts. One independent reviewer owns a separate four-file evidence directory. Root alone maintains the short authoritative report. No other production/test path may change before a separately declared amendment.

## Concrete behavior

- Scope the new film metadata to the loaded supported GR III / GR III HDF 2.10 film rows. Factory entries and other model/profile behavior keep their existing labels. Reuse the existing native-key/SlotId join; do not infer identity from an editable name or list position.
- Keep the primary camera name editable and unchanged, including valid duplicates. Add a compact secondary identity that gives the matching film slot and requested built-in/imported source. Reuse the existing firmware slot display name, built-in film names, approved-Gold constant and preset basename/title; no internal numeric address/key is needed in product copy.
- Even two instances of one source must remain distinguishable by their stable slot. The exact approved built-in identity remains separate from authored Gold. Requested source metadata is not an eligibility, camera-installation, photograph-provenance or physical-film claim. Unavailable/unknown built-in intent retains the existing guards and must not become a ready badge or fallback.
- Move up/down, hide/show and the live movement announcement include enough of the same identity to distinguish duplicate names with keyboard/assistive technology. Preserve drag handling, focus restoration, reduced motion, Standard protection and reset.
- Preserve all order/hide/native keys, film count, recipes, arrays, name ownership, pending requests, output and receipt behavior. No preset reapplication/conversion, identity migration, dynamic favorites, new menu, new movement algorithm or native tracing.
- Fit the supported 980 × 640 window. Reuse existing typography/classes with compact locally constrained subtitle markup. Long imported text may truncate visibly with full accessible identity/title; it may not push controls outside the row. If another production path is required, stop and declare an amendment before editing.

## Verification and kill

Capture the old actual browser control with an approved Gold and authored Gold both named `Street`: their Menu order labels/actions are identical. Add semantic failing regressions before production changes for identity derivation and preservation, not tests that merely mirror static text. Implement, run the focused UI state file and core/UI typechecks, and provide settled raw pins. Independent review inspects source/data purity and accessible identity. Root owns the final production build, actual keyboard/minimum-window/rename/reorder/hide/reset/restart controls, existing/full tests and composed/packet equality. All browser host operations stay in memory; no firmware build/export, card/device action or new photo is needed for this presentation change.

**Kill/revert:** source/slot identity cannot be derived from the established key join; metadata mutates/reapplies a preset or changes output/defaults; it falsely asserts readiness/installation; duplicate instances remain ambiguous; or bounded layout/accessibility checks fail. Otherwise reuse the current order workflow with this small label correction and stop the round. No new hardware contract, dynamic favorite or image experiment follows.

## Verified result

The three declared paths pass independent source review, the focused 53-test UI file, core/UI typechecks, production build/diff and full **301-pass / 175-skip** suite. Existing suite native-build/replay controls run; no new browser firmware build/export was performed. Edge at 980 × 640 confirms distinct-source and same-source duplicate aliases, accessible actions/live names, keyboard focus, rename/hide/reset/restart, bounded long import metadata and unavailable intent refusing output before a picker/build. Menu edits preserve source/recipe values and add no conversion requests. All host APIs are in memory, with zero browser build/output/page errors. All 169 composed code/config pins, 166 unowned, both workers, approved helper, CSS/i18n sources, four coefficient records and thirteen packet hashes match. Source overlay SHA-256 `13563345b4bcbab3d9a7b2ea5e75035a3a9dab2699ddd36890df908b11f753b2`; root verification `023937b79bfa89799b9981475fe6968fbbd3815b90d0f1834839730835d86d01`. Details/report/source overlays are under `research/gr3-210/wp12-film-order-implementation`; preview server stopped. No new native ordering, readiness/installation proof or camera claim follows.
