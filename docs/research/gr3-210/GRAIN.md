# WP6 — two sheets awaiting the user's preference

Base `db76c9b42f85d657a760d07af97735854f253c57`. Updated 2026-11-09.

**Claim / recorded preference:** the user wants better grain. WP2 addresses crop attenuation on the host; it does not select a preferred grain character. Published PGI/granularity data cannot calibrate the full encoded RGB spectrum.

**Decision:** preserve accepted production grain. Two bounded comparison rounds exist; the user has not judged either. The previous statement that the two-round kill was met is withdrawn. Producing two rounds does not mean two rounds with no preferred variant. No automatic third round follows this remediation.

## Round 1 — colour grain

[Sheet](../../../research/gr3-210/wp6-grain-01/wp6-grain-character-01-sheet.png), SHA-256 `9f0c03a68cec3766004ebfa9db0587cc3c7eba278d38f31ec9038fd0b3c7a47f`. Native ISO 100 Standard R0000027, matching source pixels/seed and fixed pinned colour per stock. Baseline/A/B change newly injected chroma only: A multiplies it by 128/256; B ramps from 64/256 below Y64 to 192/256 at Y128 and full at Y192. Source chroma is not denoised.

Within each stock the pre-JPEG Y plane is byte-identical. Literal source DQT/4:2:2 stay fixed; post-codec luma-strength differences are below .0015 level. The 900×256 panels show restrained colour-speckle choices. [Controls/report](../../../research/gr3-210/wp6-grain-01/report.md). This is an artistic hypothesis, not measured stock grain or a rate-control result.

## Round 2 — clump mixture

[Sheet](../../../research/gr3-210/wp6-grain-02/wp6-grain-character-02-sheet.png), SHA-256 `ea67ad77d0bfd76388c99f5612b7a9656200cc4ef3c01f213f13c659a07ae032`. New native ISO 3200 Standard R0000006 plus the ISO 100 control; source pixels, colour/MTF and literal DQT/4:2:2 are fixed. Rotation is display-only.

Only injected luminance clumps change. Small/large mixtures are Portra 7/8:1/8, current Gold 3/4:1/4 and CineStill 1/4:3/4, with accepted primary size/phase retained. Chroma stays exact before conversion/JPEG. Closed-form normalization holds added-Y RMS within .663% and mean within .01425 level. Separate replay reproduces outputs and panels. [Report](../../../research/gr3-210/wp6-grain-02/REPORT.md); [review](../../../research/gr3-210/wp6-grain-02-review/REPORT.md).

Agent inspection found subtle changes: Portra hard to separate, Gold more grouped and CineStill finer. This is not the user's choice. Existing ISO 3200 noise remains. No clean ISO 5000 Standard was found: AK000019–020 use ImageTone 0x811b and AK000021–024 0x811d. Do not add film/grain twice or relabel ISO 3200 as ISO 5000 cleanup.

**Next:** use [USER-DECISIONS](../../../research/gr3-210/USER-DECISIONS.md) to choose baseline/A/B for round 1 and baseline/candidate for round 2, separately by film.

**Kill:** after the user's judgments, two rounds with no preferred variant close that direction. The criterion remains pending. No metrics-only sweep or automatic adoption.

**Retained negative results:** block overlap showed no useful real-photo benefit; luma-only Auto does not remove chroma mottling; the prior coarse chroma cleanup lost faint true colour with little high-ISO benefit. These rejected candidates are not reintroduced. Future cleanup needs a new visual hypothesis/control. WP9 must separate grain changes from JPEG-table variation before compression-retention claims.
