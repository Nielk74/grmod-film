# WP5 — per-stock MTF

Base: `db76c9b42f85d657a760d07af97735854f253c57`. Updated 2026-11-09.

**Claim:** v3 gives all films Portra's layer-response curves; the user accepted this MTF direction.

**Evidence class:** source and recorded user preference. `examples/gr3x/film-pack-v3/build.ts` enables the same `FILM_MTF_GAINS` for every film. `core/src/color/filmmtf.ts` and `tools/filmmtf/filmmtf.c` implement the same layer-mixing pyramid.

**Decision:** WP2 makes the accepted response work in crop modes on the host. Preserve its gains. The bounded stock-source and sampled-kernel checks below select no replacement. Luma-only and 25%-chroma variants stay closed: prior visual effects were subtle and did not establish a preference.

**Next step:** retain all current gains. Gold replacement is closed on the available source evidence. The follow-up kernel/scale feasibility round also stops before a Vision3 fitter: the current sampled response is direction/phase dependent, and its original physical calibration is not established. A future named proxy needs a justified sampled forward objective before any new gain array.

**Kill criterion:** the user sees no useful difference at 100%: retain the existing curves and close that stock-specific variant.

**Limit:** published film MTF is not the camera lens/ISP response. No numeric fit metric approves the rendering.

Desktop selection and preview are tracked under WP12; preview must include MTF before halation and grain.

## Bounded primary-source result

**Evidence class:** official Kodak PDFs, visually checked graphs. `research/gr3-210/wp5-sources/sources.json` pins five files and eight page renders; `evidence.md` records axes, pages, uncertainty and a per-band equal-luma comparison formula.

- GOLD E-7022, [March 2022](https://www.kodakprofessional.com/sites/default/files/wysiwyg/E7022-1.pdf) and [February 2016](https://business.kodakmoments.com/sites/default/files/files/resources/E7022_Gold_200.pdf), contains PGI, sensitometry and spectral graphs; neither reviewed edition provides MTF or channel RMS curves. PGI 44/64 cannot generate the missing layer response. Stop this Gold-MTF branch unless a correctly identified source arrives.
- VISION3 H-1-5219 [March 2022, page 3](https://www.kodak.com/content/products-brochures/Film/VISION3_5219_7219_Technical-data.pdf) has three labelled RGB MTF curves at one 3200 K / ECN-2 / Status M condition. At high frequencies R > G > B, opposite Portra's B > G > R. The drawn curves stop near 80 cycles/mm; the axis extending to 600 is not measured support.
- [March 2026 Vision3](https://www.kodak.com/content/products-brochures/motion-picture/KODAK-VISION3-5219-7219-technical-information.pdf) describes a changed anti-halation undercoat replacing remjet. Pin the 2022 edition for the older proxy; neither sheet measures CineStill's preparation or C-41 response.
- Portra [E-4050, September 2010, page 5](https://business.kodakmoments.com/sites/default/files/files/resources/portra400-techpub-e4050.pdf) supports the current qualitative layer ordering. The source comment's `tools/filmmtf/fit.ts` is absent; reference/check/generation tools reproduce the implementation, not its original curve-to-gain fit. Do not claim that missing provenance has been recovered.

**Decision:** this round stops at source evidence. No invented Gold curve, scalar-to-RGB substitution or unlabelled CineStill replacement. A Vision3 comparison must match neutral-input luma per band, hold colour/geometry/grain/halation and codec tables fixed, and remain a rendering hypothesis for 100% user comparison.

## Sampled-kernel fit feasibility — no-go this round

**Evidence class:** unchanged TypeScript kernel and fixed integer YCbCr controls, not camera data. `research/gr3-210/wp5-fit-feasibility-01/REPORT.md` and `verification.json` pin inputs, source hashes and the bounded response experiment. No graph dataset, fitter or stock gains were generated.

A declared 36 mm / 6000 px mapping means 6 µm per pixel, with luma Nyquist at 83.33 cycles/mm and horizontal 4:2:2 chroma Nyquist at 41.67. This is a virtual rendering scale, not recovered camera/Portra calibration; all measured probes stay inside the graph's approximately 80 cycles/mm support. Unity controls preserve the packed planes exactly, ruling out a changed-kernel or round-trip error as the response difference.

At 78.125 cycles/mm, filtered-to-packing diagonal R/G/B amplitudes are about 0.249/0.242/0.290 horizontally and 0.117/0.267/0.365 vertically. At 41.67 cycles/mm, a one-pixel horizontal phase shift changes R's filtered/packing ratio from 0.696 to 0.364. A format-only control does not remove this dependence. Fitting three independent isotropic RGB curves would attribute sampling behavior to film; equal-luma normalization alone cannot fix that objective.

**Decision / kill:** stop the naive scalar-layer fitter before candidate generation and preserve the accepted response. Reopen only with bounded graph-reading intervals, an explicit virtual pitch and a forward target that accounts for direction, phase and 4:2:2, followed by neutral-luma and eye/camera gates. Vision3/ECN-2 would still be a named proxy, not a measured CineStill/C-41 response. No new native experiment or aesthetic sweep follows this no-go.
