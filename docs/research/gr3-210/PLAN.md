# GR III crop texture and decisive camera tests — implementation plan

> **For agentic workers:** use the existing research team for independent audits, implement each owned task with regression checks, and request a separate review before packaging firmware. Continue autonomously; do not ask the user questions.

**Goal:** deliver reproducible GR III 2.10 test builds for crop texture and the hue stage, preserving the accepted film work.

**Architecture:** use one branch containing main's MTF work and the saved approved Gold. Keep the camera modules and their TypeScript references in agreement. Keep historical evidence in ignored local storage and authoritative decisions in a short index and topic files.

**Tech stack:** TypeScript/Vitest, freestanding A32 C and Unicorn, Python image analysis.

**Spec:** [BRIEF.md](BRIEF.md), the user's 2026-11-09 review, supersedes the old report index.

## Constraints

- Target only the verified GR III 2.10 container; never flash, write a device, or prepare a 2.20 update.
- Preserve Portra 400 colour. Approved Gold is a separately named comparator, never a silent replacement.
- Every build carries the compatible looks, ratios and guard; any reduced-library build includes all section 5 reset steps from `docs/GR3_HDF_210_TEST.txt`.
- No release, tag, push or publication. Run the full core suite before packaging deliverables; record skipped fixture coverage.
- Record base SHA, artifact hashes and evidence class. A model or emulation result cannot approve an aesthetic change.
- Each task has a kill criterion. Frozen research remains frozen unless the user provides a new reason.

## Change manifest and ownership

| Owner | Files | Purpose |
|---|---|---|
| Root | `docs/GR3_EXPLORATION_REPORT.md` | Replace the long log with an index under 150 lines |
| Root | `docs/research/gr3-210/{BRIEF,PLAN,BASELINE,CROP_TEXTURE,COLOR_AXES,EXPOSURE,MTF,GRAIN,WHITE_BALANCE,CAMERA_VALIDATION,PRODUCT,FOCUS_FROZEN}.md` | Brief, plan and one decision file per topic |
| Root | ignored `research/gr3-210/legacy/**` and its relative manifest | Preserve old log, scripts, data and results |
| Root | `.gitignore` | Track only `docs/research/gr3-210` decision documents while keeping local evidence ignored |
| Reference agent | `tools/gr3x/research-reference.ts` | Portable exact-reference reproduction, with no temporary or primary-checkout dependencies |
| UI agent | `tools/gr3x/symbols-gr3-210.json` | Verified addresses with scoped confidence and evidence |
| Root | fourteen files from `67881cd` under `tools/jpeg_experiments/exposure_print/` | Bring the approved Gold assets onto the MTF base |
| Texture implementer | manifest to be settled from WP2 audit before edits | Reference/native crop processing and meaningful regressions |
| Root | test-build scripts, build manifests and one test card, exact files declared before edits | Produce T-colour and T-texture with a return path |

## Review focus

- Small pictures remain excluded from MTF; a 50 mm crop must be processed.
- Aligned interiors are processed without touching right/bottom tails or stride padding.
- A sensor crop and a downsize have distinct texture policies; the default and fallback are explicit.
- Settings survive flashes; slot identity, recipes, crop lists and guards are checked in both test builds.
- Approved Gold's stored fitted parameters remain distinct from its target LUT and the authored pack Gold.

## Task 1 — establish the base and usable record (WP1)

- [x] Verify that `67881cd` adds only the approved exposure-print research assets.
- [x] Create `codex/gr3-crop-texture` from `1bd2956` and cherry-pick that commit; integrated base is `db76c9b42f85d657a760d07af97735854f253c57`.
- [x] Reproduce all approved preview hashes; stable float-grid audit is under `research/gr3-210/reference-audit`.
- [x] Save exact v3 priority-film transforms plus a separately named approved Gold reference with `tools/gr3x/research-reference.ts`; authoritative output is `reference-pinned`.
- [x] Preserve legacy evidence outside temporary storage; write a relative manifest and distinguish old commands from current reproduction commands.
- [x] Replace the report, mark superseded claims, and create the 229-address symbol map.
- [x] Run the full core suite on the integrated base (237 pass / 175 skip) and verify that Portra colour source files are unchanged.

**Kill criterion:** stop baseline archaeology once the exact accepted references and one integrated base are reproducible. Do not re-run frozen experiments.

## Task 2 — repair crop-mode texture on the host (WP2)

- [x] Confirm crop dimensions/focal-length metadata in all 27 source files, and descriptor rejection/scaling from the actual code.
- [x] Declare the final file manifest in `WP2-MANIFEST.md`; add meaningful failing regressions before production edits.
- [x] Implement reference/native changes together with explicit sensor/output policies and exact legacy behavior when omitted. Close the bounded crop-property audit without a verified per-shot bit.
- [x] Regenerate with isolated Zig 0.15.1 / clang 20.1.2; verify two link origins and native/reference parity.
- [x] Run targeted regressions, type checking and the full core suite (249 pass / 175 skip); independent review closed its one RGB preview finding after a verified fix.
- [x] Make one actual-content 100% host sheet at 6000/4800/3360 widths, with Legacy/Sensor/Output columns, identical pinned Portra colour, no halation, recorded strip/seed limits. Camera comparison remains separate.

**Kill criterion:** reject unsafe descriptor/provenance assumptions. Stop after one reviewable host candidate; aesthetic adoption waits for the user's camera comparison.

## Task 3 — prepare one decisive camera session (WP3, WP7–9)

- [x] Build and independently review T-colour's control/all-group/bit-code/scale/adjacent-index probes, keeping semantics hypothetical. General Engine rejects diagnostics by design; standalone verification reverses/reapplies and independently decodes them.
- [x] Build/review T-texture with preserved ratios/guard, crop fixes and approved Gold. Explicit choice: keep current Soft Focus; omit ADJ Grain replacement.
- [x] Respect twenty films. T-texture displaces only Pro 400H in slot 64; T-colour keeps six exact colour comparators plus fourteen probes. Full section 5 reset required on entering/leaving changed libraries.
- [x] Give both candidates hashes and one common card, with chart A/B/A,28/35/50 texture, matched film/Standard and WB developments. WP9 eight-way DQT matrix is explicitly deferred: no verified RAW halation editing route, no invented controls or new tracing.
- [x] Include verified Return-current-MTF path/hash. Local packet: `research/gr3-210/test-session/ready`; host checks/reviews pass, hardware operation remains untested. No SD-card write or flash performed.

**Kill criterion:** T-colour B matches A after registered RAW development: close the hue-stage direction. Do not port a fitter before that result.

## Task 4 — continue only the accepted image directions

- [x] WP4 bounded host round: preserve approved Gold and prepare one CineStill plus one opt-in Portra latitude sheet. No new aesthetic winner or shipped Portra change.
- [x] WP5 bounded source/fit feasibility: Gold has no reviewed curves; a naive Vision3 fitter lacks a justified sampled objective/calibration. No gains or comparator selected; preserve Portra's response.
- [x] WP6: two independently reviewed character rounds, the final one on new clean ISO 3200 content. No adoption or ISO 5000 cleanup claim; stop the sweep at its two-round cap.
- [ ] WP7–9: analyze returned WB, matched Standard/film and grain/DQT files before further calibration or rate-control tracing.
- [x] WP12 desktop MTF: optional state/build/Copy plumbing and full-source worker preview. Independent reviews, actual browser gates and final 263-pass/175-skip suite pass; preceding camera packet remains fixed.
- [x] WP11–12 bounded native contracts: Software build tag and Snap/Hyperfocal are no-go on existing writer/label/aperture evidence; preserve stock behavior and stop tracing.
- [x] WP12 follow-up prototype: recorded Standard/other/unknown is useful metadata information, but strict malformed-input review fails; six-file implementation remains unexecuted, desktop sources unchanged.
- [x] One exact-current-v3 night halation Off/On host baseline, using the actual pack header and unchanged seed, full-frame geometry and literal source codec; no new lookup or aesthetic adoption. Independent review is recorded with the sheet.
- [x] WP12 concrete development bootstrap repair: one constructor-only edit, actual module/classic browser gates and 263-pass/175-skip full suite; preceding source/packet pins fixed.
- [x] WP4 capture-EV / WP12 texture-status existing contracts: both closed no-go on missing AE ownership/restore and text ownership/refresh/width joins. No new native tracing or implementation followed either kill.
- [x] WP12 portable build receipt: six declared paths implemented with complete owned request/assets and byte pairing; independent reviews, real decoded replay, actual browser old/new output parity and distinct failure outcomes pass. Final suite 281/175 plus typechecks/build; source overlay pinned, sealed packet fixed, unknown exact builder/replay limits explicit.
- [x] WP8 return-file intake: existing card, slot/session catalog and analyzer CSV/build templates cover association. Reuse and stop; no duplicate implementation. Operator declarations and matched same-WB Standard requirements stay explicit.
- [x] WP8 one-time evidence arrival check: named corpus/session folders have no interpretable completed mapping/build/settings/registration contract. Filename continuity only, no media-byte/freshness inference. Reuse intake; no analysis or repeat inventory.
- [x] WP12 reset-guidance audit: modified exports lack the complete existing instructions; source audits preserve the five steps, historical qualifiers and identity limits. Existing card remains fixed.
- [x] WP12 reset-guide implementation: only app/i18n/styles under `WP12-RESET-MANIFEST.md`; final independent copy/interaction reviews, actual English/Chinese keyboard/scroll/focus/source/scope checks, 281/175 suite and typechecks/build pass. Three-file overlay pinned; packet fixed; no operation or camera claim.
- [x] WP4 approved-Gold UI feasibility: exact approved quantized payload/preview can be a separate optional entry outside the default twenty. No refit, CIE76 fabrication or unsupported named-Standard fallback; bounded source audit GO, no implementation in that audit.
- [x] WP4 approved-Gold optional UI: eight declared paths implemented; separate exact coefficients/preview, retained unavailable intent, complete ownership/model/source and preflight controls. Both source reviews, actual browser/independent receipt decode and full 296/175 suite/typechecks/build pass. Parent sources, default twenty and sealed packet fixed; no device or new aesthetic claim.
- [x] WP12 existing film-order acceptance: UI/build audits say reuse existing drag/buttons/hide/reset and stable ID-based output. One P2 duplicate editable-name ambiguity is presentation only; no builder/native change or broader reordering implementation.
- [x] WP12 film-order identity labels: three declared paths, five semantic red→green cases, source review, actual minimum-window keyboard/source/rename/hide/reset/restart/import/guard checks, 301/175 suite and typechecks/build pass. Native workflow/payloads/defaults and sealed packet stay fixed.
- [x] WP12 bounded host-tool feasibility: no equivalent same-film texture reference or narrow recipe reuse control. Source audits give conditional GO for existing renderer/two-plane reuse and immediate guarded texture/detail pull; whole-film cloning/clipboard/default expansion rejected. No execution in the audits.
- [x] WP12 texture/detail reuse: four declared paths, independent source-label finding reproduced/fixed/reviewed, 62 focused / 310 full passes with 175 skips, typechecks/build and actual English/Chinese keyboard/Off/restore/twenty-film/source-refusal checks. Overlay pinned; camera packet and fixed image/native references unchanged.
- [x] WP12 same-film texture reference: four declared paths pass independent source review, 12 focused / 316 full tests with 175 skips, typechecks/build and seventeen actual browser gates. Old/default/right pixels and storage remain exact; Film colour left equals independent texture-Off output. Physical 1:1 and English/Chinese minimum-window checks pass. The overlay is pinned; no extra reference plane/cache/ROI, aesthetic variant, native or packet change.
- [x] Bounded source-only decisions: ISO policy stops at missing shot provenance/lifetime/job join; existing bilingual preview-versus-camera notes are adequate and reused. Fixed-centre comparison crop has conditional GO through existing planes/APIs; no source or runtime work in these audits.
- [x] WP12 centre-crop export: exact four paths under `WP12-COMPARISON-CROP-MANIFEST.md`. Initial review's save-lifetime/page gaps were meaningfully reproduced, fixed and re-reviewed; the rejected epoch stays archived. Corrected 25 focused / 329 full tests with 175 skips, typechecks/build/diff and 26 actual browser gates pass. Five independent PNG oracles verify unscaled native panels; root inspected English/Chinese output/layout. Shared busy lifetime, stale pre-dispatch refusal, captured-file post-dispatch verification, no-extra-work/storage gates and all 170 code/config pins pass. Four-file overlay and 203-file artifact manifest sealed; camera packet fixed.
- [x] WP1 flat source checkpoint: `WP1-SOURCE-CHECKPOINT-MANIFEST.md` closes one verified 170-file raw overlay plus 25 dated decision documents on exact base `db76c9b`. Independent Git/coverage/restoration audits and standalone verifier pass on the actual ZIP/directory; all 199 members match external pinned/live bytes. Membership semantics, 123 EOL-only files and fourteen introduced paths are explicit. A checker-only optional-byte-count defect was corrected with the failed attempt preserved; archive/product unchanged. Final 216-file evidence manifest verified. The source's 329/175 test gate, four coefficients, thirteen packet hashes and 203 closed crop-evidence files stay fixed; no restore/rebuild/release/device operation claimed.

**Current stopping boundary:** independent remaining-work review found no new direction that survives the brief without actual preference or contract-complete camera returns. Preserve completed host tools and sealed evidence. Do not add another prototype, sweep, repeated inventory or native trace to substitute for those results. Existing camera analysis remains open and uses the prepared intake/analyzer when the required records and files arrive.

**Kill criteria:** each topic file states its visual or measurement gate. No direction continues on emulator case counts alone.

## Test-builder file manifest (declared before edits)

- UI agent creates `tools/gr3x/build-t-colour.mts` only: standalone fourteen-probe builder and versioned verification; general Engine inspection remains unverified for its manually redirected blocks.
- Root creates `tools/gr3x/build-t-texture.mts` only: pinned official/current/reference inputs, sensor/output policy, approved Gold in slot 64 replacing Pro 400H, preserved other 19 colours/features/ratios/guard/pictures, independent pinned Python decoder, explicit unvalidated filenames pending final review.
- Root maintains this plan, the short index and topic status. Final test card and source/build evidence stay under ignored `research/gr3-210`; no changes to the example v3 builder or film colour data.
