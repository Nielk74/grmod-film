# Ricoh GR III 2.10 — decisions and next actions

Updated 2026-11-09. Active brief: [user review](research/gr3-210/BRIEF.md). This index replaces the former research queue.

**Base:** `db76c9b42f85d657a760d07af97735854f253c57` on `codex/gr3-crop-texture`: main's MTF plus approved Gold assets from `67881cd`. Portra colour is unchanged.

**Prepared:** T-colour, T-texture and a verified return pack with [one common camera card](../research/gr3-210/test-session/ready/TEST-CARD.md) and `SESSION-MANIFEST.json`. Host checks and independent reviews pass; camera operation remains untested. The user flashes; agents analyze. Stay on 2.10.

## Top five actions

1. Use the fixed local session packet; full reset instructions name both changed libraries and the return path. No agent device writes.
2. Decide WP3 from the same-DNG A/B/A result; no fitter before positive pixels, stop on an inactive result.
3. Compare crop texture at 28/35/50 mm and 100% edges; the host sheet is a model, not camera proof.
4. Analyze matched Standard/film and WB outputs before further fit work. WP9's eight-way DQT test is deferred because RAW halation editing is unverified; no new encoder tracing.
5. Keep references, test binaries and finished image rounds fixed. Reviewed MTF, paired export, reset help, optional approved Gold, film-order identities, texture/detail reuse, same-film comparison and native-pixel centre-crop export are ready locally. One verified flat raw source checkpoint now consolidates the host state. Further image decisions require actual preference or camera pixels; closed image/native directions stay closed.

## Decisions and work queue

| Priority | Package | Status / decision | Next step | Kill criterion |
|---|---|---|---|---|
| P0 | [WP1 base](research/gr3-210/BASELINE.md) | Complete: exact references/base, return pack, 229-address map and verified flat 170-file source checkpoint | Use the local checkpoint on its exact base; no archaeology | Missing/outside pin, unsafe path or archive mismatch rejects restore |
| P0 | [WP2 crop texture](research/gr3-210/CROP_TEXTURE.md) | Host/review/pipeline gates pass; T-texture/card/sheet ready | Camera comparison; no automatic adoption | Unsafe descriptors or failed parity reject the candidate; user picks appearance |
| P0 | [WP3 hue stage](research/gr3-210/COLOR_AXES.md) | T-colour built/reviewed; register packing is not pixel evidence | Same-DNG A/B/A on the common card | B matches A: close the tested direction |
| P1 | [WP4 exposure](research/gr3-210/EXPOSURE.md) | Exact optional approved Gold implemented/reviewed; fixed sheets without adoption; capture-EV and ISO-policy contracts no-go | Use compiled entry without refit/default replacement; preserve user compensation | Lost exact payload, false metrics or unsafe eligibility: stop; AE/ISO contracts stay closed |
| P1 | [WP5 MTF](research/gr3-210/MTF.md) | Gold source branch and naive Vision3 fitter closed; sampled response is direction/phase dependent | Retain gains; no candidate before a justified sampled target/calibration | Unjustified scale/objective: no fitter or new gains |
| P1 | [WP6 grain](research/gr3-210/GRAIN.md) | Two reviewed character sheets complete; final clump changes subtle, no adoption | Preserve baseline; no further sweep without actual preference/camera evidence | Two-round cap reached: stop |
| P1 | [WP7 WB](research/gr3-210/WHITE_BALANCE.md) | Test fixed WB before firmware policy | Same-DNG AWB/fixed developments | AWB preferred: close policy work |
| P1 | [WP8 camera/model](research/gr3-210/CAMERA_VALIDATION.md) | Analyzer/intake ready; one-time folder check found no interpretable return contract | Matched same-WB/settings Standard/film files plus operator/geometry records; no repeat inventory | Unsupported controls withhold verdict; dominant residual stops fit tuning |
| P1 | [WP9 JPEG](research/gr3-210/CAMERA_VALIDATION.md) | 23 DQT sets; controlled matrix deferred, RAW halation editing unverified | Require a usable control route before the matrix; no new tracing | No useful controlled tradeoff: stop encoder tracing |
| P2 | [WP10 AF](research/gr3-210/FOCUS_FROZEN.md) | Frozen: no named failure or baseline | Preserve symbol map only | No failure / acceptable stock AF: remain frozen |
| P2 | [WP11 Snap](research/gr3-210/PRODUCT.md) | Bounded review closed: labels and live aperture ownership unproved | Preserve stock table; no new AF tracing | Missing mapping/owner contract: keep stock |
| P2 | [WP12 product](research/gr3-210/PRODUCT.md) | MTF/dev/receipt/reset/order/reuse/comparison/crop export pass; existing explanations reused | Use completed tools; image decisions require camera pixels or actual preference | No resampling, stale/mislabeled output, unbounded work/new write contract or frozen work |

## Corrections that affect decisions

- 25/27 source JPEGs are crops: 16 at 35 mm, nine at 50 mm; only two are 28 mm.
- AK000019–027 are 35 mm JPEG crops with a full-frame DNG crop. Their crop/resize ambiguity is closed; custom-ratio and exact-build provenance are separate.
- The direct MTF guard rejects 3360 px frames and several non-8-aligned active sizes. A whole-buffer alias has not proved those real crops received MTF.
- Current grain attenuation at 3360 is 143/256; integer medium gain is 35/64. Crop sampling must not be treated as a full-frame resize.
- Old Gold scores concern authored pack Gold. The approved +2 EV exposure-print fit is a separate rendering.
- Compare only the pinned reference set. The older scratch Portra target differs, but the later verified MTF pack's quantized Portra coefficients match current pins exactly.
- Model metrics reject failures; the user's eye approves appearance. Nothing new in this exploration has passed a physical camera test.

## Frozen or dropped

AF thresholds/predictors/lens tuning, hidden scan-range tracing, orientation-point memory, simulated AF metrics, temporary Select, dynamic favorites, navigation-step modelling, texture bypass, block overlap, luma-only Auto grain, histogram overlays/guides, multi-exposure ordering, on-camera audition queues, and halation excitation lookup. Reopen only with the brief's stated evidence or a new user request.

## Record and verification

- [Implementation plan](research/gr3-210/PLAN.md): exact constraints, ownership and gates.
- [Baseline and corrections](research/gr3-210/BASELINE.md): reference identities and superseded claims.
- [Flat source checkpoint](../research/gr3-210/source-checkpoint-01/REPORT.md): one raw 170-file code/config overlay plus 25 dated decision documents on exact base, with independent verifier and restoration instructions. All 199 ZIP members and live source bytes match; complete repository, firmware, media, dependencies and full evidence remain external. [Local ZIP](../research/gr3-210/source-checkpoint-01/checkpoint.zip); 216-file evidence manifest verified.
- [WP2 100% host sheet](../research/gr3-210/wp2-visual/wp2-crop-texture-sheet.png): same native Standard source pixels, fixed Portra colour, Legacy/Sensor/Output; strip-model limits in its `processing.json`.
- [CineStill proxy latitude sheet](../research/gr3-210/wp4-cinestill-01/review/cinestill-latitude-one-round.png): one 0/+1/+2 EV model round, fixed filtration/common print scalar; separate from authored v3 CineStill, no winner selected.
- [Opt-in Portra latitude sheet](../research/gr3-210/wp4-portra-optin-01/review/portra-optin-one-round.png): one 0/+1/+2 EV model round, restrained rosy/cream shifts; a separate model baseline, no shipped Portra change or winner.
- [Grain character sheet](../research/gr3-210/wp6-grain-01/wp6-grain-character-01-sheet.png): one baseline/A/B round with identical luma grain, fixed DQT/4:2:2 and restrained injected chroma; no winner or ISO 5000 claim.
- [Final grain clump sheet](../research/gr3-210/wp6-grain-02/wp6-grain-character-02-sheet.png): new ISO 3200 Standard plus ISO 100, controlled injected strength and fixed chroma; subtle structure changes, no adoption, two-round cap reached.
- [Exact-v3 night halation sheet](../research/gr3-210/halation-night-baseline-01/night-halation-off-on-sheet.png): one reviewed full-frame Off/level 1 gold comparison, same actual grain seed and fixed codec; lamp/window spread, unchanged selected skin/shadow patch. [One-page result](../research/gr3-210/halation-night-baseline-01/REPORT.md); lookup remains frozen.
- [Desktop MTF browser gate](../research/gr3-210/wp12-browser/REPORT.md): full 24 MP original, physical 1:1 at minimum window/DPR 1–2, cancellation and proxy restoration; software preview only.
- [Development-startup fix](../research/gr3-210/wp12-dev-bootstrap/REPORT.md): one worker-constructor expression, real dev/module and production/classic firmware opening/heartbeat, independent review; prior desktop and sealed packet pins unchanged.
- [Portable build receipt](../research/gr3-210/wp12-build-receipt-implementation/REPORT.md): actual submitted coefficients/assets plus input/output checksums; unchanged firmware output in real browser control, independently decoded replay, explicit partial failures. Host evidence only; exact builder revision unknown.
- [Reset / return guide](../research/gr3-210/wp12-reset-guidance-implementation/REPORT.md): optional English/Chinese instructions from both entry points, minimum-window keyboard/scroll/focus and source/model exit pass; no build/write operation. Written guidance only; no camera recovery claim.
- [Exact optional approved Gold](../research/gr3-210/wp4-approved-gold-ui-implementation/REPORT.md): direct frozen coefficients/preview, visible unavailable intent, preserved controls and unchanged default twenty; real-worker receipt independently matches the approved native hash. Software/host evidence only.
- [One-time return-evidence check](../research/gr3-210/wp8-arrival-check-01/REPORT.md): no completed mapping/build/settings/registration records in the named corpus/session folders; filename continuity only, no media-byte freshness claim or analyzer run. Reuse existing intake and stop.
- [Film-order identity correction](../research/gr3-210/wp12-film-order-implementation/REPORT.md): duplicate names/sources now show stable slot/requested-source identity in rows and keyboard actions; existing reorder/hide/reset and native join reused, no payload/default change.
- [Texture/detail reuse](../research/gr3-210/wp12-texture-reuse-implementation/REPORT.md): implemented/reviewed immediate pull between active films; colour/sky/identity and latent Off choices preserved. Independent fallback-label finding closed; actual English/Chinese keyboard/restore/twenty-film checks pass. [Four-file manifest](research/gr3-210/WP12-TEXTURE-REUSE-MANIFEST.md).
- [Same-film texture reference](../research/gr3-210/wp12-texture-reference-implementation/REPORT.md): implemented and independently reviewed Source / Film colour choice; the old/default and textured-right pixels remain exact on a 24 MP original. Colour-only left matches independent texture-Off output. Seventeen actual browser gates cover honest fallbacks, current ownership, unchanged storage and minimum-window English/Chinese physical 1:1. [Four-file manifest](research/gr3-210/WP12-TEXTURE-REFERENCE-MANIFEST.md).
- [Centre-crop export](../research/gr3-210/wp12-comparison-crop-implementation/REPORT.md): reviewed four-file implementation, 25 focused tests and 26 actual browser gates. Five independent PNG decodes match native centre pixels; English/Chinese layouts pass. Shared save lifetime survives remount, stale pre-dispatch work refuses, captured post-dispatch files still verify. [Manifest](research/gr3-210/WP12-COMPARISON-CROP-MANIFEST.md); fixed centre, software preview and existing overwrite limits remain explicit.
- [Preview-meaning audit](../research/gr3-210/wp12-preview-meaning-01/REPORT.md): existing bilingual Recipe notes already distinguish previewed colour/texture from camera Sharpness/Clarity/Shading; reuse and stop. [ISO-contract audit](../research/gr3-210/wp4-iso-contract-01/REPORT.md): missing shot-bound provenance/lifetime/job join triggers no-go; no curve family or native investigation.
- Symbol map: `tools/gr3x/symbols-gr3-210.json` (curated original addresses; no AF improvement implied).
- Local evidence: ignored `research/gr3-210/legacy/manifest.json`; 1,337 files copied and SHA-256 verified. Paths are relative to the manifest. Original log: `REPORT.original.md`; annotated reading copy: `REPORT.md`.
- Latest full suite: **329 passed / 175 private-fixture skips**, with existing independently decoded receipt replay, typechecks/build and independent source/browser gates. Prior stage counts remain in their topic records. Current crop overlay SHA-256: `46c67052bacb04438d3400bfb79d1ad58389188e0d9c7e1ec08eaf0e8e3f25b6`; all 170 code/config pins and thirteen sealed packet hashes match. The 203-file artifact manifest is verified; servers stopped.
- No release, device write or flash has been performed. Public shipping/license treatment of the separately attributed exposure-print assets remains open.

Future updates use **claim → evidence class → decision → next step → kill criterion**, with limitations in one line. Round reports stay within one page and state what changed, what the user should inspect, and what was killed.
