# WP4 — approved Gold preserved, other preferences pending

Base `db76c9b42f85d657a760d07af97735854f253c57`. Updated 2026-11-09.

**Claim / saved acceptance:** Gold negative +2 EV with compensated print is the accepted direction. `tools/jpeg_experiments/exposure_print/approved.json` pins its exact fit, distinct from the target LUT and authored pack Gold.

**Decision:** preserve saved M1/curves/P2, quantizing directly. Do not refit its LUT or alter Portra colour. T-texture's approved comparator replaces only Pro 400H in slot 64; full resets accompany changed libraries. No exposure or halation coefficient changes occur in this remediation.

**Desktop implementation:** [eight-file manifest](WP4-APPROVED-GOLD-MANIFEST.md). Separate optional `gold-plus2-approved` sits outside the default twenty, with direct frozen arrays/preview and unavailable CIE76 metrics. Official GR III/HDF 2.10 checks apply at selection/restore/model/source transitions. Unsupported active intent stays visible and blocks submission; controls remain independent. Payload SHA-256 `91158f03a8e83fb36563c1ddc9ef8907b153ff6e47a21f8101827a6b92a7fdb6` matches the receipt decoder.

Its real-worker browser build was intercepted in memory (no saved firmware/device write), output `fee0b2f4559c92189e443494f1a3bc606b5d4f3d7931a85daf77fa6e43dae479`. Historical stage gate 296/175 plus typechecks/build is recorded in [implementation report](../../../research/gr3-210/wp4-approved-gold-ui-implementation/REPORT.md); exact environment/skip qualifications are in the shared index. This is host evidence, not installation/camera/real-film validation.

## CineStill latitude

[One sheet](../../../research/gr3-210/wp4-cinestill-01/review/cinestill-latitude-one-round.png), [report](../../../research/gr3-210/wp4-cinestill-01/REPORT.md). The Vision3/4300 K/Endura model at 0 EV is a separate baseline from authored v3 CineStill. Fixed filtration/WB/interlayer with negative 0/+1/+2 EV; common print compensation +.465271/+.931355 EV holds continuous gray L*=50 while b* shifts +5.57/+12.78.

Agent inspection sees milder cream at +1 and stronger yellow/olive sky, skin and highlights at +2. Architecture panels use native 6000×4000 source pixels; portrait panels use declared 1600 px Standard previews. No grain/halo/detail recovery. Own-target full-cube p95 around 15–17 ΔE00 and maxima 36–48 limit representability, not preference.

## Portra opt-in latitude

[One sheet](../../../research/gr3-210/wp4-portra-optin-01/review/portra-optin-one-round.png), [report](../../../research/gr3-210/wp4-portra-optin-01/REPORT.md). Separate Portra/D55/Endura 0 EV model versus +1/+2, print compensation +.554566/+1.157489 EV, fixed filtration/WB/paper/interlayer. Agent inspection sees restrained rosy +1 and pink/cream +2 skin shifts; whites change little. Full-cube p95 around 18 and maxima 32–35 show model limits. No shipped Portra change or automatic optional slot.

**Next / kill:** judge both sheets using [USER-DECISIONS](../../../research/gr3-210/USER-DECISIONS.md). Preference remains pending. Stop a stock's direction if the user sees no preferred variant; no additional sweep now.

**Other scoped decisions:** capture-EV policy remains no-go without AE units/ownership/restoration; ISO-selected curves remain no-go without shot-bound provenance/lifetime/JPEG-job join. Their reports are `wp4-capture-bias-01` and `wp4-iso-contract-01`. These are missing-contract findings, not impossibility proofs. No native tracing follows.

**Licence:** source is GPL-2.0-only; upstream profiles and derived approved Gold numeric data are attributed CC BY-SA 4.0, including embedded UI arrays. Attribution remains intact. [Creative Commons' compatible-licence list](https://creativecommons.org/compatible-licenses/) names one-way GPLv3 compatibility, not GPL-2.0-only. Distribution treatment needs a user decision/review before anything public ships; separate labels alone do not establish clearance.

**Limit:** a simplified negative/print model does not establish exposure chemistry, push/pull or actual film fidelity. No new aesthetic adoption has occurred.
