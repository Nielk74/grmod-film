# WP8–9 — matched camera outputs and grain/JPEG controls

Base `db76c9b42f85d657a760d07af97735854f253c57`. Updated 2026-11-09.

## WP8 — Standard to film

**Claim / real files:** the prior 37-pair study (28 training, nine held out) calibrates camera Standard, not Standard-to-film behavior. Reuse `tools/jpeg_experiments/exposure_print/calibration.json`; do not repeat that study or call it film validation.

**Decision / prepared host evidence:** the existing ignored [analyzer](../../../research/gr3-210/wp8-analyzer/README.md) accepts explicit DNG/JPEG/build/slot/settings associations, checks registration/clipping, inventories DQT/size and A/B/A controls, and reuses core quantized colour math. Its corrected revision passes 21 tests; a separate 40,000-sample formula check matches float32 components. [Review](../../../research/gr3-210/wp8-analyzer-review.md).

Unsupported/missing/nonneutral settings withhold model execution and verdicts; equal nonneutral controls do not validate the neutral inverse. DQT/sampling differences withhold film-model dominance. Registration can miss a .25-pixel resampling shift; manual stored-pixel review is required.

**Next:** use the revised common card's matched same-DNG, same-WB/settings texture-Off Standard/film developments. Native Standard is slot 11, distinct from probe A. Existing card, SLOTS.csv, session manifest and analyzer examples already provide the intake contract. Fill them from operator records; filenames, chronology and EXIF cannot prove installed build, selected style or same-DNG origin. WB-only and T-texture captures remain context rather than forced residual pairs.

The [one-time arrival check](../../../research/gr3-210/wp8-arrival-check-01/REPORT.md) found no completed interpretable mapping/build/settings/registration contract. Filename continuity is not byte/freshness evidence. No analyzer run or repeated inventory followed.

**Kill / limit:** camera/model residual dominating target-fit error stops finer fitting. Clipped JPEG data cannot be recovered; model fit is not actual film fidelity. Physical-film comparisons need separate user participation.

## WP9 — grain separately from halation

**Claim / real-file audit:** 27 JPEGs contain 23 literal DQT sets, all 4:2:2, including variability within size/ISO groups. Earlier fixtures are two samples, not a fixed camera encoder policy. Variability alone does not prove grain caused coarser tables.

**Control-route finding:** `core/src/fw/gr3x/films-r10.ts:340–343` maps RAW development to Standard's page. `halation-rows.ts:126–134` adds custom kinds 10/11/15 to shooting, not Standard; kind 11 is custom grain. No custom Off/Low/Medium/High RAW control or shooting-to-reopen inheritance is established. Stock Standard grain is not the custom film control. The earlier halo blocker did not by itself establish this grain limitation.

**Next:** shortest existing route is four T-texture tripod captures at grain 0/1/2/3, halation Off, fixed manual exposure/WB/scene/size/film. The revised card specifies this without new firmware or flashes. Compare DQT/file size/detail, explicitly retaining capture noise, registration and rate-control confounds; these are not same-DNG developments. Custom grain setter preserves halo (`tools/gr3x/native/films.c:339–343`).

The combined eight-way same-DNG halo/grain matrix remains deferred because usable RAW controls are not established. No new encoder/native tracing follows now.

**Kill:** no useful controlled table/detail tradeoff stops encoder tracing. **Limit:** independent captures cannot perfectly isolate stochastic source noise, and host fixed-table sheets cannot establish camera rate control.
