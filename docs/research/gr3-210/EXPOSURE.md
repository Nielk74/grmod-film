# WP4 — accepted exposure latitude axis

Base: `db76c9b42f85d657a760d07af97735854f253c57`. Updated 2026-11-09.

**Claim:** Gold negative +2 EV with compensated printing is an accepted visual direction.

**Evidence class:** saved user acceptance and source assets. `tools/jpeg_experiments/exposure_print/approved.json` pins the candidate fit and target; README distinguishes them from authored pack Gold.

**Decision:** preserve the approved fit and show it as `Gold +2 EV (approved)` beside current Gold. Do not substitute a new fit of its LUT or alter Portra colour. The existing backend has twenty film IDs and v3 uses all twenty, so a comparator build must explicitly name any displaced non-priority entry and include the reset procedure.

**Next step:** saved grids and direct quantization now reproduce; the named approved comparator is in the host-verified T-texture candidate, replacing only Pro 400H in slot 64. One CineStill/Vision3 proxy round and one separately named opt-in Portra model round are complete below. No second sweep or new winner is selected. Shipped Portra remains unchanged.

**Kill criterion:** stop a new stock's sweep after its visual comparison shows no preferred variant. Metrics may reject artifacts but cannot select the look.

**Limit:** the simplified spectral model does not establish actual negative exposure, push/pull chemistry or real-film matching.

## Exact approved Gold in the desktop library

The bounded source audit is **GO for local implementation**, not a new aesthetic round. The current library exposes only authored Gold and refits built-ins through CUBE conversion; that cannot stand in for the already approved fit. Independent serialization of the pinned Q13/three curves/Q9 reproduces the approved 1,572-byte payload exactly (`91158f03a8e83fb36563c1ddc9ef8907b153ff6e47a21f8101827a6b92a7fdb6`), and the saved preview parameters match the accepted archive. Audit: `research/gr3-210/wp4-approved-gold-ui-01/REPORT.md`; exact plan: `wp4-approved-gold-ui-plan/PLAN.md`.

The [eight-file implementation](WP4-APPROVED-GOLD-MANIFEST.md) is complete locally and independently reviewed. It adds a separately optional `gold-plus2-approved` identity outside the default twenty, using direct private compiled arrays and honest unavailable CIE76 metrics. Exact official GR III 2.10 source/profile checks apply at selection, restore and every model/source transition. Unavailable active intent stays visible and blocks modified submission before destination selection; no refit, authored-Gold fallback or Standard under the approved name. Independent recipe/texture controls and authored Gold/Portra remain fixed.

Actual Edge selection adds zero conversion requests, preserves controls, restarts and returns from unsupported/no-source states correctly, and keeps the original twenty. A 6000 × 4000 original renders at physical 1:1 at the minimum window. One real-worker export was intercepted entirely in memory: output SHA-256 `fee0b2f4559c92189e443494f1a3bc606b5d4f3d7931a85daf77fa6e43dae479`. The independently decoded receipt matches every submitted argument, the exact approved native payload and 22 build checks. No firmware binary was saved or device touched. Full suite **296 passed / 175 skipped**, typechecks/build/diff and both source reviews pass; four fixed coefficient records and thirteen sealed packet hashes remain exact. The eight-file overlay is `research/gr3-210/wp4-approved-gold-ui-implementation/source-final.json`, SHA-256 `919a5d81e300105809e86bef98a127a2fd7e2ea2bed17be352467df60255636d`. Its 442-word report records limits: software preview, no new replay/camera/real-film validation, no capture-EV change or new aesthetic adoption.

## CineStill proxy — one host comparison

**Evidence class:** software model on known Standard photographs. `research/gr3-210/wp4-cinestill-01/REPORT.md` and its input/artifact manifests pin the unmodified Vision3 profile, Endura, calibration, three target cubes, matched fit grids and licenses. Approved Gold's method-control grid reproduces exactly. The comparison is against the same Vision3/4300 K/Endura model at 0 EV, separately from authored v3 CineStill.

**Changed:** negative exposure 0/+1/+2 EV, with fixed channel filtration/interlayer/input WB and one common print scalar. The +1/+2 variants need +0.465271/+0.931355 EV print compensation to hold continuous gray L*=50. They also move gray b* to +5.57/+12.78; brightness compensation does not preserve hue.

**Inspect:** `review/cinestill-latitude-one-round.png` shows milder cream warmth at +1 and stronger yellow/olive sky, beige/yellow skin and denser yellow highlights at +2. The architecture patch uses native 6000×4000 source pixels; portrait 100% patches use the declared 1600 px Standard previews. There is no grain/halation or new capture detail. Daytime cheek median ΔE00 moves about 4.09/8.50; night skin moves less. This is a substantial colour choice, not an automatic improvement.

**Decision:** adopt nothing. Own-target full-cube p95 errors remain about 15–17 and maxima 36–48 ΔE00, despite lower sampled-photo errors. Metrics expose that limit and do not select an EV. This is one visual round, with no production/firmware edit. Stop this stock's exposure direction if the user finds no preferred variant; do not run another parameter sweep without a new reason.

## Portra — one opt-in host comparison

**Evidence class:** Portra 400 / D55 / Endura software model on the same verified Standard architecture, daytime skin and night sources. The 0 EV model is distinct from shipped Portra; `research/gr3-210/wp4-portra-optin-01/REPORT.md` and its manifests pin both. The existing profile matches the pinned official source and earlier study, and the approved Gold method control reproduces exactly.

**Changed:** negative exposure 0/+1/+2 EV with fixed filtration, WB, paper and interlayer. Common print compensation is +0.554566/+1.157489 EV. Continuous gray stays L*=50 while a*/b* drift; the native parameter approximation does not hold gray exactly. The sheet shows restrained rosy midtone shifts at +1 and warmer pink/cream daytime skin at +2, with smaller mixed night changes. Whites remain nearly unchanged; it does not reproduce Gold's stronger dense-cream response.

**Decision:** adopt nothing and stop this round. Full-cube p95 remains about 18 ΔE00 and maxima 32–35 despite sampled-photo means near 0.94–0.95. The +1 skin change is comparable to its approximation error. The sheet is an opt-in aesthetic comparison, not real-film or camera validation, and supplies no reason to retune shipped Portra. Further tuning requires a new actual preference. Sheet SHA-256: `f440b0235169e729bfa587430e6b5196d56e0901e0b6956055b4924648fe48b8`.

## Later controls

Per-film capture AE bias is **closed no-go under the existing-evidence gate**. The current ten-parameter recipe is an image-processing contract: `key` is not a proven capture-EV setter. Known film/parameter owners do not establish AE get/set units, range and lifetime, preservation/restoration of user compensation, or a nonrecursive capture-safe transition. The first missing contract triggered the stop; no new native trace, emulation or policy followed. See `research/gr3-210/wp4-capture-bias-01/REPORT.md` (298 words; SHA-256 `e89fa6938de5ed67db3a83dee7c53bf3dfb68db291e444b4ef3e39543c3de262`). This is a scoped feasibility decision, not proof that native AE control is impossible.

ISO-selected curve families remain unimplemented. They require shot-bound ISO provenance, which has not been joined to the JPEG job; neither an ISO family nor a capture AE policy is in the crop candidate. Current compensation, defaults, colours and test binaries are unchanged.

The later bounded existing-evidence audit is **no-go** for ISO policy and stops at that prerequisite. The current JPEG-stage interface supplies no verified ISO encoding, exposure owner/lifetime or same-job join; an opaque configuration pointer and known film stash do not close it. No map hunt, native trace/xrefs/disassembly/emulation, media inventory or curve selection followed. This does not establish that native ISO is absent or impossible to obtain. Decision: `research/gr3-210/wp4-iso-contract-01/REPORT.md`, 326 words, SHA-256 `a01f3aee91f9a0892c45b4ead127e1f5d2e45e03629fad38c5c88f740684abe3`. Preserve the fixed renders until a separately established shot contract exists.

## Attribution boundary

Profiles and derived assets carry the recorded CC BY-SA 4.0 attribution; local script source carries GPL-2.0-only. Preserve the existing license/attribution files and keep derived assets separate. Public shipping/license treatment is unresolved; this round prepares local research artifacts and does not publish a release.
