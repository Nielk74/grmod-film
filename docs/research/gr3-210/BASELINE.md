# WP1 — saved base, references and packet

Base `db76c9b42f85d657a760d07af97735854f253c57`, branch `codex/gr3-crop-texture`. Updated 2026-11-09.

**Claim / source:** the base joins main's MTF (`1bd2956`) with approved Gold from `67881cd`, cherry-picked as `db76c9b`. Gold negative +2 EV and common print compensation +1.1417332135 EV were accepted on 2026-11-01. Saved fit parameters, target LUT and authored pack Gold are distinct references.

**Decision:** preserve Portra colour and quantize approved Gold's saved M1/ck/P2 directly. `tools/gr3x/research-reference.ts` reproduces four coefficient records and three authored v3 targets. [Pinned manifest](../../../research/gr3-210/reference-pinned/manifest.json) SHA-256 `49ac27de2266575936c6f562901ed1b784c9d5f74d577fd1e93bd36e242b2c97`. Compare errors only within the same target/fit recipe. The reusable symbol map holds 229 original addresses with scoped evidence; it claims no AF improvement.

**Saved work:** commit `a0bdde5` contains 47 real source/config changes (33 modified, fourteen new) plus 25 documents. The historical raw checkpoint's 170 source paths comprise those 47 and **123 EOL-only differences**. Git normalized source EOLs when committing. Its ZIP is 1,248,130 bytes, SHA-256 `c30f6ff8b187187c717a2501bf2869e1c302477975dbee841c0aefa17f47070a`; the 199 members were independently read back. It excludes firmware/media/dependencies/full evidence and is not a complete repository. [Restore instructions](../../../research/gr3-210/source-checkpoint-01/payload/README.md).

The pre-revision ready packet (14 physical files, thirteen checksum members) and checkpoint ZIP were copied to `C:/Users/Antoine/GRMod-backups/gr3-210-session-01/`; all fifteen copies rehashed exactly. [Verification](../../../research/gr3-210/review-remediation-01/backup-verification.json). Keep that dated backup unchanged; it predates the revised card.

After refreshing origin, no configured remote branch contains `db76c9b`. A later approved `git push -u origin codex/gr3-crop-texture` would upload that base and subsequent local commits/create the branch, without merging main. No push is authorized now.

**Return:** `cf04126f5861c3a64123f0cdc95efa5b65443b44aa0ca975854423acf0131f55`, 38,408,796 bytes, is the all-twenty-film MTF pack with historical halo profile start 228, radii .006/.035, mix .3 and gains ×.78. Fresh reconstruction reproduces it. It has **no shot animation**; the primary checkout's film-pack animation outputs use it as input and differ. This does not prove the currently installed build. Preserve/identify the actual starting file and accept the return difference before a session.

**Card-only revision:** all firmware bytes and eleven other packet files are unchanged. Exact SHA-256 moves:

| File | Before | After |
|---|---|---|
| TEST-CARD.md | `c072e636cb66885fb17ca8a3aa7f0f320c92b2370e0d64af9fd9e28258b6b57e` | `6908b79364c5e57eed9032c728813c1a436c3c56680a46adce9cfc3e09bdb59b` |
| SESSION-MANIFEST.json | `24a1e68ba31ff1cce42eb97e9c56e2d6a83236b20ae6de8144c367592e7dfc5e` | `cc97488555323314fbfa6e307dea70f806998e53c4147410f94b43bdd6fe9978` |
| SHA256SUMS.txt | `3d4191c81cd519b387f7222274112e59973cb53a2915c43b261b0ab5c665cea4` | `13a972f182fe9de480676c2c859659c6dec9405e43e010788996b908b239e3b1` |

SESSION changes only the card's bytes/hash; checksum rows change only card and SESSION. Exact-path Git attributes preserve these three raw text files through checkout.

**Next / kill:** use the saved commits/backups and fixed references. Wrong base, uncovered content, unsafe path or mismatched bytes rejects a restore. Stop archaeology once references reproduce.

**Limit:** local reproducibility is not installation provenance, physical validation, licence clearance or public shipping. Legacy evidence remains at `research/gr3-210/legacy`; old commands/snapshots are historical.
