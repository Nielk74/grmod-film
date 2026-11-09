# WP12 — reuse texture and detail between active films

Declared 2026-11-09 before source/test edits. Base `db76c9b42f85d657a760d07af97735854f253c57`. The source-only audit at `research/gr3-210/wp12-texture-reuse-01/REPORT.md` finds no equivalent action: library reapplication changes colour/identity, whereas the useful gap is transferring existing texture/detail settings. Whole-film cloning is rejected. The separate texture-reference audit remains a proposal; it cannot edit shared paths during this implementation.

Parent: `research/gr3-210/wp12-film-order-implementation/source-final.json`, SHA-256 `13563345b4bcbab3d9a7b2ea5e75035a3a9dab2699ddd36890df908b11f753b2`, with 169 composed code/config pins and the completed 301-pass/175-skip gates. Root captures raw preimages and verifies the parent before authorizing edits.

## Exact four-file source/test manifest

| Owner | File | Change |
|---|---|---|
| Implementer | `ui/src/store.ts` | Pure current-source candidates/owner snapshots and a synchronous guarded atomic transfer using existing autosave |
| Implementer | `ui/src/library.tsx` | Immediate target-local chooser inside expanded Recipe, qualified source labels, explicit scope and no clipboard |
| Implementer | `ui/src/i18n.ts` | English/Chinese action, exclusions, Off behavior and concise result/unavailable text as needed |
| Implementer | `core/test/gr3x-ui.test.mjs` | Preservation, nested ownership, neutral clearing, stale/busy/scope/membership refusals and existing persistence/request contracts |
| Root | This manifest, `PLAN.md`, `PRODUCT.md`, `docs/GR3_EXPLORATION_REPORT.md` | Before-edit decision and final verified result |

Implementation evidence belongs only in new ignored `research/gr3-210/wp12-texture-reuse-implementation/**`; root owns its before/browser/final-gate records. The independent reviewer has a separate new evidence directory. Root alone edits the authoritative short report. No other production/test path changes without an explicit root amendment made before that edit. No code refactor, CSS/component/schema/worker/core/native/colour/default-library change is authorized.

## Chosen behavior

- On the currently edited target film, an expanded Recipe offers **Reuse texture/detail from…**. The existing Select performs one immediate explicit choice, then resets to its placeholder; no staged source, clipboard, Apply all or new film. Escape/Tab/outside dismissal changes nothing. Use existing layout and controls; unsupported scope hides this addition. If no eligible source exists, show concise explanatory text instead of an empty actionable menu.
- Scope is the exact loaded supported official GR III / GR III HDF 2.10 and existing recipe capability. Participants must be distinct, active slots. Hide/refuse during firmware opening/build activity and when a participant has a busy/error/unresolved preset or unavailable approved intent. A film with no preset remains valid for its neutral-colour texture settings. Existing global build guards remain authoritative.
- Label choices with editable alias plus stable slot/requested-source identity from the established ID join. Duplicate aliases and two instances of one source must remain distinguishable. Labels do not assert readiness, installation or photo provenance.
- Capture shallow info/raw/model and source/target slot references with the displayed choice; commit rechecks ownership, current target and active membership synchronously. A stale closure after any relevant edit/removal/count/model/source change must refuse without side effects. No await, conversion or new transaction subsystem.
- Whitelist only MTF, grain amount/active size, halation level/active colour, Sharpness, Clarity and Shading. Source Off **clears** MTF/amount/level/zero detail values rather than skipping them. When grain/halation is Off, retain the target's hidden size/colour, matching existing controls; when On, copy the active child choice. Preserve target stored halation `on`, even though the GR III getter derives effective on.
- Preserve target sky, colour/compiled arrays/preset/source, names/icons, global geometry, slot/count/order/hidden state, all unrelated and dormant slots. Create private nested recipe/grain/halation data and publish exactly one target state update, then existing autosave. Never mutate shared neutral defaults, old state/requests, or source objects. Applied settings persist through the existing project format; the action itself has no saved context.
- Explain copied fields, preserved colour/sky/names and Off/hidden behavior in both UI languages. Keep the existing reminder that camera Sharpness/Clarity/Shading are not simulated in the preview. No new look, grain candidate, aesthetic decision or camera session modification.

## Evidence and kill

Meaningful failing regressions precede production edits. Verify the intended field changes and exact exclusions, nested isolation/one notification, active-neutral clearing, source/target guards and stale snapshots, count zero/one/twenty, removal/menu movement, and applied-settings save/restore. Run the focused UI state file and core/UI typechecks; independent review inspects the settled four source hashes. Root then builds the UI, checks actual keyboard/dismissal/duplicate identity/minimum 980 × 640 English/Chinese/restart behavior with in-memory host APIs, runs the full core suite with existing replay control, and verifies composed source/fixed coefficients/sealed packet hashes. This action needs no new browser firmware build or photo experiment.

**Kill/revert:** copying alters colour/sky/identity or dormant data; shared objects alias; a stale/unavailable/busy source can commit; new file/native/asynchronous contracts or extra source paths are necessary; or bounded layout/accessibility cannot pass. Otherwise retain this small action and stop its implementation round. Keep camera/native and closed image directions frozen.

## Before-edit review amendment — requested source in fallback labels

The independent source reviewer found that `lookIdentity` intentionally returns undefined without the optional menu-layout capability. The new chooser's fallback preserves Film N but omits approved/authored/imported source metadata. Authorize a bounded correction only in the already owned `ui/src/store.ts` and `core/test/gr3x-ui.test.mjs`: first reproduce missing requested-source text in meaningful regressions, then retain the complete slot/source label without falsely requiring a menu-order operation. A private pure requested-source label helper may be extracted and reused by the established `lookIdentity` selector and the new fallback; its existing outputs and guards must remain exact. No broad refactor, new path or other behavior change. Preserve preceding source/log evidence and record the revised settled hashes. Independent review must revisit the fix; root reruns final build/full-suite/browser gates on the new epoch.

## Verified result

The amended four-file epoch passes independent source review with zero open findings, 62 focused tests, core/UI typechecks, production build/diff and full **310-pass / 175-skip** suite with the existing official receipt replay. Actual Edge at 980 × 640 passes English/Chinese keyboard focus and Escape/Tab dismissal, source identities, exact intended target changes across twenty serialized slots, Off/latent behavior, restart and unavailable/one-film/no-file states. Browser conversions added, firmware builds, output writes and page errors are zero. Root inspected settled menu/result screenshots. All 169 composed code/config pins match, 165 unowned unchanged; both workers, stylesheet, four coefficient records and thirteen packet hashes are exact. Source overlay SHA-256 `d3ecc3f516e8c76765bf4f885e0fb3bceb867004f2fab95634c3dedfe068615d`; root verification `15d451ffd460837a83e663d60ee0e61a1567853aa329a56d3b6935a1111ff188`. The 485-word report/evidence is under `research/gr3-210/wp12-texture-reuse-implementation`; initial source/runtime epochs remain preserved separately. Servers stopped; no camera or performance claim. Retain the action and close this implementation round.
