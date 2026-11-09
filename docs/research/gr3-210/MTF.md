# WP5 — one proxy made; user preference pending

Base `db76c9b42f85d657a760d07af97735854f253c57`. Updated 2026-11-09.

**Claim / source:** authored v3 uses the same Portra-derived `FILM_MTF_GAINS` for every film. The user liked this direction. WP2 changes coverage/geometry, preserving accepted gains; production stock gains remain unchanged.

**Sources:** [pinned official PDFs and page renders](../../../research/gr3-210/wp5-sources/sources.json) show:

- Gold E-7022, 2016/2022: PGI/sensitometry/spectral plots, no MTF curves. This source branch remains closed; PGI cannot supply missing channel curves.
- Vision3 H-1-5219, March 2022 page 3: high-frequency **R > G > B**, opposite Portra's **B > G > R**. Drawn support ends near 80 cycles/mm, not the axis endpoint of 600. It is 3200 K/ECN-2/Status M, not measured CineStill/C-41. The changed 2026 undercoat is a different edition.
- Portra E-4050, September 2010 page 5: qualitative ordering supports the current response. The original `tools/filmmtf/fit.ts` is absent; implementation reconstruction does not recover physical calibration.

**Scoped fitter no-go:** the [sampled-kernel experiment](../../../research/gr3-210/wp5-fit-feasibility-01/REPORT.md) found 4:2:2 direction/phase dependence. A naive isotropic RGB fit would attribute sampling to film. Its unjustified objective remains rejected. This does **not** prohibit a clearly labelled artistic comparison; the earlier blanket no-candidate conclusion was too strong.

**One candidate:** [sheet.png](../../../research/gr3-210/review-remediation-01/mtf-proxy/sheet.png), SHA-256 `845a365059040e6d4d7143e7250d38e6a0bb5de11c1777beb2a8242e258cee9a`. Exact label: **Vision3 ordering proxy, not measured CineStill**. It swaps finest-band R/B and analytically normalizes neutral luma. Finest R/G/B gains are .3076372211839777 / .22426670053791328 / .09670980394943472; middle/coarse gains stay fixed. These are hand-set design values, not digitized measurements.

**Controls:** actual current `filmMtf`/`filmMtfMatrices` render both sides. Default/explicit baseline bytes match on both full Standard sources. Neutral-Y Q12 coefficients match per band [961,4262,5339]; four unclipped neutral fixtures match Y before codec, and eight source-DQT codec pairs match decoded Y. Source literal DQT/4:2:2 headers remain exact. Authored CineStill colour/geometry are fixed, grain/halo Off. Full stored 6000×4000 ISO 100/3200 images are encoded before EXIF orientation; four 900×384 paired patches are native 100%, contexts reduced. All eight displayed panels independently match decoded JPEG crops. [436-word report and controls](../../../research/gr3-210/review-remediation-01/mtf-proxy/REPORT.md).

**Decision / next:** one round is complete; no fitter, native edit, production gain change or adoption. The user must judge useful differences at 100% via [USER-DECISIONS](../../../research/gr3-210/USER-DECISIONS.md). Restrained appearance is an agent observation, not the user's preference.

**Kill:** the user sees no useful difference at 100%: retain baseline and close this candidate. That kill has **not** been met. Stop this requested round without generating further candidates.

**Limit:** source noise/WB/NR/sharpening/JPEG history remain. Equal neutral luma does not establish a measured stock, lens, ISP or physical film response. Luma-only/25%-chroma variants remain dropped under the brief.
