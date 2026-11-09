# WP6 — stock character and high-ISO texture

Base: `db76c9b42f85d657a760d07af97735854f253c57`. Updated 2026-11-09.

**Claim:** the user wants better grain; crop attenuation is the first concrete defect to address.

**Evidence class:** recorded user preference and source. `core/src/color/grain.ts` and `tools/grain/grain.c` share the tile, tone and gain method. v3 primarily changes Portra's amount rather than giving the focus stocks different grain character.

**Decision:** crop texture is repaired on the host, and two bounded character rounds are complete. Preserve the accepted grain; neither round supplies an adopted replacement. Published granularity constrains the discussion but does not calibrate encoded RGB spectra. The ISO 5000 film-rendered files are excluded from a second film/grain application; the final clean-content comparison is explicitly ISO 3200.

**Next step:** both bounded character rounds are complete and independently checked. Preserve the accepted baseline; stop this direction without a new actual preference/camera result. The final round used new clean ISO 3200 Standard content, with no parameter sweep or adoption. No clean ISO 5000 Standard was found: `AK000019–020` have ImageTone `0x811b`; `AK000021–024` have `0x811d`. Do not add grain twice to those film JPEGs or relabel ISO 3200 as ISO 5000.

**Kill criterion:** two visual rounds without a preferred variant: stop that grain direction.

**Limit:** published granularity is not a complete perceptual grain model.

## One colour-grain character round

**Evidence class:** artistic/software-model comparison on native ISO 100 Standard `R0000027.JPG`, with fixed pinned colour within each stock, matching source pixels and seed. No production or sealed-file edits. `research/gr3-210/wp6-grain-01/report.md` records source/codec/parameter hashes and limits.

**Changed:** only newly injected chroma grain. A multiplies it by 128/256 throughout; B uses 64/256 below Y64, ramps to 192/256 at Y128 and full strength at Y192. Source chroma is not filtered. Tiles, placement, tone table, grain amount/size and the luminance output remain fixed. The research chroma implementation reproduces accepted baseline chroma exactly at scale 256.

**Controls:** within each stock the pre-JPEG Y plane is byte-identical. Added Y RMS is about 3.49 for Portra/CineStill and 3.48 for current Gold. Added chroma RMS falls from about 1.28/1.33/1.27 to 0.68/0.71/0.68 for A and 0.97/0.95/0.97 for B. Every output uses the same literal source DQT tables and 4:2:2 codec; post-JPEG luma-strength differences stay below 0.0015 level. This does not model camera rate control or remove original image noise.

**Inspect:** `wp6-grain-character-01-sheet.png`, SHA-256 `9f0c03a68cec3766004ebfa9db0587cc3c7eba278d38f31ec9038fd0b3c7a47f`. Matching 900×256 native-pixel panels show a subtle colour-speckle/texture choice across Portra, CineStill and current Gold; no winner is adopted. Source PGI is not RMS; Vision3's density/exposure and 48 µm aperture requirements do not supply an encoded RGB grain spectrum. These are labelled design hypotheses, not measured stock-specific spectra.

**Kill:** retain baseline if neither candidate is preferred. At most one further bounded round needs new clean content or eye feedback; stop after two rounds without preference. No high-ISO denoising or mottling claim.

## Final clump-mixture round — stopped, no adoption

**Evidence class:** one artistic host comparison on native Standard `R0000006.JPG`, ISO 3200, 6000×4000/EXIF 6, plus the prior ISO 100 control. The sole sheet is `research/gr3-210/wp6-grain-02/wp6-grain-character-02-sheet.png`, SHA-256 `ea67ad77d0bfd76388c99f5612b7a9656200cc4ef3c01f213f13c659a07ae032`. All 900×256 panels use the same source pixels, exact pinned colours/MTF and per-source literal DQT/4:2:2; rotation is a display step without resampling.

**Changed:** only injected luminance clumps. The frozen small/large mixtures are Portra 7/8:1/8, current Gold 3/4:1/4 and CineStill 1/4:3/4, retaining the accepted primary size/phase. Chroma remains byte-identical before conversion/JPEG. One closed-form offline normalization controls added-Y moments; no Auto behavior, denoising or parameter search is introduced. The actual rounded/clipped full-strip and patch RMS differences stay within 0.663%, and mean differences within 0.01425 level. Independent replay reproduces the baseline, candidate bytes, clipping and displayed panels.

**Appearance / decision:** differences are subtle: Portra is hard to separate, Gold is slightly more grouped and CineStill slightly finer. The ungrained ISO 3200 control already contains camera texture; neither candidate removes it. No preferred variant or stock-spectrum/ISO 5000/mottling claim is established. This is round two of two: preserve the accepted baseline and stop this direction. Further work needs a new actual preference or camera result, not another metrics-only sweep. Full controls and limits are in `wp6-grain-02/REPORT.md`; independent review is `wp6-grain-02-review/REPORT.md` (SHA-256 `333def7bce496b4ebc63c0a595478eea2e71085d3ab2287d91f065ed79cbdb63`).

## What was ruled out

| Direction | Evidence class | Decision |
|---|---|---|
| Block overlap | Model/JPEG/real-photo inspection, IMG-010/011 | Freeze: no useful real-photo benefit established |
| Luma-only Auto grain budget | Model/reference execution, IMG-013 | Drop: it does not remove existing chroma mottling |
| First coarse chroma cleanup | Reference execution and real-photo sheets, IMG-014–016 | Reject current candidate: little high-ISO benefit and faint true colour texture loss |

A future chroma-only cleanup or per-film NR default needs a new visual hypothesis and a different failure control. The existing negative candidate is not silently reintroduced. DQT variability must be accounted for through WP9 before claiming compression retention gains.
