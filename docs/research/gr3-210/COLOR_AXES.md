# WP3 — test pixel activity separately by route

Base `db76c9b42f85d657a760d07af97735854f253c57`. Updated 2026-11-09.

**Claim / source and emulation:** per-film block selection reaches register packing, but this does not prove pixel activity or hue/luminance semantics. Factory styles share one block; 59/60 groups are identity. The 12×5 interpretation remains hypothetical.

**Decision:** test strong perturbations before a fitter. Portra colour remains unchanged. [Builder](../../../tools/gr3x/build-t-colour.mts) appends data to a verified ordinary R10 base, redirecting fourteen table cells. Each source block is 60×9 signed int32 Q10, 2160 bytes; the packed register representation is smaller. The cloned Standard record changes only its block pointer, preserving selector/ancillary fields.

| Probe | Contents / question |
|---|---|
| A | Standard control |
| B | All sixty groups perturbed: do pixels change? |
| C–H | Six-bit group coding |
| I–K | Row sums scaled .5/.75/1.25 |
| L | Special group 0 scaling |
| M–N | Neighbouring perturbations on a smooth hue ramp |

**Prepared evidence:** T-colour SHA-256 `d761ea15d50aeaecee0d08e44e63a00cb4dc0899a405c89fd5e8afd988502283`, 37,840,152 bytes. Reverse/reapplication, independent Python reconstruction, sections/checksums/pointers and retained colour payload checks pass. [Host evidence](../../../research/gr3-210/t-colour-host-20261109-r2/); [review](../../../research/gr3-210/tcolour-review.md). General Engine inspection intentionally remains unverified for this diagnostic format. No normal app write is enabled.

Six exact colours occupy 64–69: Portra, CineStill, authored Gold, approved Gold, Kodachrome, Astia. Probes A–N occupy 70–83. There is no MTF/grain/date/ADJ Soft Focus module, and halo gain headers are zero. Full resets are required entering and leaving the changed library.

**Next:** follow the revised common card after texture comparisons. First develop the same chart DNG A/B/A without saving to U1/U2/U3. If B changes pixels, develop C–N for semantics. If B matches, take one conditional A and one B tripod capture with fixed manual settings, also without U-bank saves. Stop on anomalies; separately label RAW-development and capture results.

The repository search found the blanket development-only policy in the brief/topic notes, but no capture-specific technical crash/write/lens reason behind it. Coefficient bounds and preservation checks are not hardware-safety proof. The newer user instruction authorizes this narrow capture exception; probes remain unsuitable for normal photography.

**Kill:** a valid negative result closes only the tested route. RAW equality alone cannot close capture. Do not port a fitter before positive pixels. Hardware startup, persistent settings and image behavior remain untested.

## Halation evidence

The historical exact-v3 night sheet and new daylight [haze diagnosis](../../../research/gr3-210/review-remediation-01/haze/REPORT.md) now exist. Approved Gold's GUI crop reproduced exactly; both full and actual legacy proxy paths show heavy yellow lift. Provisionally too strong for these bright highlights; no demonstrated new integration defect, no code/strength change. The desktop default and historical pack halo profiles differ, so their intensities are not interchangeable. No documented camera halation positive control was established. User preference remains open; excitation lookup work does not restart automatically.
