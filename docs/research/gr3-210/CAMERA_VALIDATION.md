# WP8–9 — camera/model residuals and JPEG rate control

Base: `db76c9b42f85d657a760d07af97735854f253c57`. Updated 2026-11-09.

## WP8 — matched Standard and film developments

**Claim:** the earlier 37-pair calibration is prior camera-Standard calibration, not the missing Standard-to-film validation.

**Evidence class:** real files and saved calibration. `tools/jpeg_experiments/exposure_print/calibration.json` carries the prior coefficients. The original study is under the user's `Pictures/GRMod-Camera-Truth-2026-10-31`; its report identifies 28 training and nine held-out Standard pairs.

**Decision:** reuse that calibration. Do not repeat it or claim it validates the per-film ISP model.

**Next step:** the common card specifies matched texture-off Standard/film developments. The reviewed ignored prototype under `research/gr3-210/wp8-analyzer/` accepts explicit DNG/JPEG/build/slot/settings mapping, screens registration and clipping, inventories DQT/size, and checks A/B/A repeat controls. It reuses the existing quantized model/core colour math. The corrected revision passes 21 tests with zero skips; an independent 40,000-sample formula check matches all float32 components exactly. These are host controls, not returned camera evidence.

The review found and closed an unsupported-settings attribution error: equal nonneutral controls do not validate the neutral Standard inverse. Model evaluation now requires explicit supported neutral controls; missing, extra or nonneutral settings retain the inventory but omit model execution and verdicts. DQT or sampling differences suppress the film-model dominance verdict. Registration can miss subpixel resampling, including a tested 0.25-pixel shift: manual stored-pixel geometry review remains mandatory. Source and review pins are in `research/gr3-210/wp8-analyzer-review.md`; no native ISP or camera accuracy is established.

**Kill criterion:** camera/model residual exceeds target-fit error: stop fine fit tuning and correct the ISP model first.

**Limit:** a JPEG inverse cannot restore clipped source information; model fit is not a real-film match. Physical-film comparison is outside this unprompted camera session.

The bounded intake audit is **reuse and stop**: the fixed card, `SLOTS.csv`, session manifest and existing `wp8-analyzer/mapping.example.csv`, `builds.example.json` and `README.md` already define the association contract. No second template or importer is needed. Populate their placeholders from real returns and operator records. Installed build, selected style, same-DNG origin and actual settings remain declarations; chronology, filenames and EXIF cannot prove them. Native Standard is slot 11, distinct from T-colour's 70/71/70 activity control. Each supported residual pair needs the same-WB/settings native Standard; extra WB-only outputs and T-texture capture comparisons remain contextual rather than forced model evidence. Missing/duplicate/unsupported inputs withhold or invalidate the relevant comparison without inference or repair. The 462-word audit is `research/gr3-210/wp8-return-intake-01/REPORT.md`, SHA-256 `2b0b38e44d719bc324c61d41337f949991c69a495568cffee1c9f605a7afab58`; it read text/source only and changed no packet or analyzer file.

The later one-time arrival check is also **reuse and stop**. The explicitly named Ricoh2/session folders contain no interpretable completed result contract. Current JPEG names match the historical 27-file set, but the old inventory has no byte lengths/mtimes and media contents were not read or hashed, so byte/time freshness is unknown. The session area has the prepared packet and unfilled draft rather than returned mapping/operator/settings/registration declarations. Existing examples remain placeholders. No analyzer run, duplicate template, further folder search or recurring check follows. See `research/gr3-210/wp8-arrival-check-01/REPORT.md` (317 words; SHA-256 `832dc7073bbbba6ebf97dc975932089ffb7b23f2a6b8dcaadb467b4a2ad283cb`).

## WP9 — grain and JPEG tables

**Claim:** the corpus has 23 distinct DQT sets across 27 JPEGs, all 4:2:2; the earlier two table fixtures do not describe a single fixed encoder policy.

**Evidence class:** real-file Pillow audit. Table variability occurs within shared size/ISO groups; the rate-control mechanism is not established.

**Decision:** treat IMG-011/ORCH-009 as two sampled table conditions. Do not trace the encoder policy before a controlled same-DNG comparison.

**Next step:** controlled same-DNG developments with grain Off/Low/Medium/High and halation on/off, only after a usable control route is established. The repository test note explicitly says RAW development shows Standard's parameter page and cannot edit halation there. The common card must not invent those controls; this block remains pending rather than triggering another native tracing round. Compare DQT, sizes and registered detail when controlled files become available.

**Kill criterion:** no table change or useful visible/detail tradeoff in this controlled test: do not continue native rate-control tracing.

**Limit:** variability alone does not prove grain caused coarser quantization.
