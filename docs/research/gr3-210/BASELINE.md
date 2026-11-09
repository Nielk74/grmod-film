# WP1 — one base, exact references, durable evidence

Base: `db76c9b42f85d657a760d07af97735854f253c57`, branch `codex/gr3-crop-texture`. Updated 2026-11-09.

## Integrated code and accepted Gold

**Claim:** this tree contains main's two film-MTF commits and the saved approved Gold exposure-print experiment.

**Evidence class:** source. `1bd2956` contains MTF; `67881cd` adds fourteen exposure-print research files only. Its cherry-pick is `db76c9b`. The saved Gold is negative exposure +2 EV with common print compensation +1.1417332135 EV, accepted 2026-11-01. See `tools/jpeg_experiments/exposure_print/approved.json` and its README.

**Decision:** use this base. Keep authored pack Gold and the approved fitted Gold as different named references. Preserve Portra's colour. Quantize the saved approved `M1`/`ck`/`P2` parameters directly; importing its target LUT and refitting would produce a different approximation.

**Next step:** use the completed pinned references in the two test builders. Integrated-base core verification passed: 237 tests passed, 175 skipped, zero failed (34 files passed / 10 skipped; 94.50 s). Missing private fixtures remain skipped.

**Kill criterion:** stop branch archaeology once these references reproduce; do not rebuild a different target to chase better model scores.

**Limit:** the approved Gold is a preferred software rendering; it is not measured film truth or an installed pack entry.

## Reference set

| Reference | Identity | Use |
|---|---|---|
| v3 Portra 400 | Exact v3 response, shoulder 0.03, end-grey weight 24 | Colour stays fixed |
| v3 CineStill 800T | Exact v3 response, shoulder 0.03, end-grey weight 24 | Current pack comparator |
| v3 authored Gold 200 | v3 colour push 1, midtone 0, shoulder 0.03 | Preserve existing Gold |
| Gold +2 EV (approved) | Saved candidate fit in `exposure_print/approved.json` | Separate named comparator |

Do not compare numerical errors between different target/fit recipes. Archived ORCH-006/007 and CRE-016 are not the reference set for future decisions. `tools/gr3x/research-reference.ts` reproduces all four coefficient files and the three current v3 target cubes. The authoritative local manifest is `research/gr3-210/reference-pinned/manifest.json`, SHA-256 `49ac27de2266575936c6f562901ed1b784c9d5f74d577fd1e93bd36e242b2c97`. All accepted preview grids reproduce. The approved candidate float grid is `c86865ce62eaf6595e3887834a68aa57a3a88acfe70ef221ef510e674e74ec80`.

| Quantized colour payload | SHA-256 |
|---|---|
| Portra | `890bcdf75029951d3fb3de19fcb24300f4e22ec93061a2c07c7f1b1b378e9197` |
| CineStill | `249ed05a44826b00415d5555dc7160c211ec4295193209ae9409fe8fab730948` |
| Current Gold | `6caa69980013cd07992ed4fa2c775ca143d509350b43458cdf6ffe6a1d682894` |
| Approved Gold | `91158f03a8e83fb36563c1ddc9ef8907b153ff6e47a21f8101827a6b92a7fdb6` |

## Verified local return pack

`research/gr3-210/inputs/current-pack-mtf.bin` is the later all-twenty-film MTF pack, SHA-256 `cf04126f5861c3a64123f0cdc95efa5b65443b44aa0ca975854423acf0131f55`, 38,408,796 bytes. A fresh Engine reconstructs it byte for byte with its declared historical v3 halation profile: start 228, narrow 0.006, wide 0.035, mix 0.3, shipped gains multiplied by 0.78 and rounded to two decimals. Declare that profile before opening the Engine. Its Portra/CineStill/current Gold quantized coefficients match the pins above exactly. The older November 1 v3 file predates MTF and is not the texture baseline. This establishes a local artifact, not which file is currently installed on the camera. Evidence: `research/gr3-210/return-pack-survey.json`.

## Durable legacy evidence

**Claim:** the old log and all four research directories have been copied out of temporary storage.

**Evidence class:** real files. Ignored `research/gr3-210/legacy/manifest.json` indexes 1,337 files by relative path, byte size and SHA-256; all copied bytes were re-read and verified. `REPORT.original.md` preserves the original log; `REPORT.md` is a reading copy with superseded annotations and targeted prose-spacing repairs. The archived tree includes scripts, firmware-derived fixtures, raw arrays and results.

**Decision:** authoritative decisions live in these topic files and the short index. Legacy scripts with embedded absolute paths are historical artifacts, not current reproduction commands. New active work uses repository tools and relative output paths.

**Next step:** record new reference/build artifacts alongside current code; keep the legacy manifest immutable.

**Kill criterion:** do not port every frozen probe merely to make old commands convenient.

**Limit:** preserving a failed or synthetic probe does not make it passing or hardware evidence.

## Corrections and superseded entries

| Old entry/claim | Current decision |
|---|---|
| AF-002 confidence interpretation | Superseded by AF-004; preserve only scoped symbol evidence |
| CRE-003 / CRE-014 crop uncertainty | Focal-length metadata identifies the 35 mm JPEG crops with full DNG crop in AK000019–027; custom ratios and build identity remain separate |
| UI-011 bypass/interaction candidate | Later UI-015 evidence supersedes its event assumptions; omit bypass from the test build |
| AF-UI-004 temporary Select | Dropped: AF-UI-005 identifies the stock feature |
| Two JPEG DQT fixtures called exact camera tables | They are two samples; the corpus has 23 distinct sets |
| Old Gold metrics | Describe authored pack Gold, not the separately approved exposure-print fit |
| Halation seed model improvements | Frozen pending a night-photo comparison; no production adoption |

The completed symbol map is `tools/gr3x/symbols-gr3-210.json`: 229 unique original addresses across 25 scopes, with analyst-assigned labels, explicit roles and evidence classes. Its 529 report references, 77 source references and 10 artifact references resolve. SHA-256 `90ab2e9362baddc67afcec23d9b7b490368f9ef1ff94f6460a5eb5735cfa024b`. None claims new hardware validation; AF remains frozen.

## Flat current-source checkpoint

**Claim:** the completed host source/config state can now be transferred as one raw-byte overlay on the exact integrated base. [414-word result](../../../research/gr3-210/source-checkpoint-01/REPORT.md); [declared manifest](WP1-SOURCE-CHECKPOINT-MANIFEST.md). This replaces manual composition of the ten historical source overlays for restoration while preserving their audit history.

**Evidence class: source, Git metadata and real archive bytes.** Independent audits confirm every current non-document change is covered by 170 pinned files: 156 base-tracked and fourteen introduced, totaling 3,790,943 bytes. Of the base-tracked paths, 123 differ from Git only in CRLF and 33 have content changes. All raw files are included; a Git patch of the 47 changes is insufficient for byte-exact reproduction. A dated 25-document decision snapshot is separate from source; its 37 external-link occurrences reference 26 distinct omitted local-evidence paths.

**Decision:** retain the [local checkpoint ZIP](../../../research/gr3-210/source-checkpoint-01/checkpoint.zip), 1,248,130 bytes, SHA-256 `c30f6ff8b187187c717a2501bf2869e1c302477975dbee841c0aefa17f47070a`. The manifest is `2f9646fd1c0fee54197d6a5bdb51a50d65e8650ae9d46ba8b5245dbabff2c408`. The standalone stdlib verifier passes the real ZIP and unpacked directory with 199 exact members. Root independently decodes every member and compares all 170 source bytes with the external inventory/live tree. Corrupt, missing/extra, EOL-altered and unsafe/link members are rejected. Final self-check: 56 passes, zero failures, one Windows filesystem-symlink privilege skip; ZIP symlink/reparse controls pass. Actual runtime: Python 3.12.10; Python 3.9 compatibility reviewed.

**Next step:** follow the [README](../../../research/gr3-210/source-checkpoint-01/payload/README.md) in a separate exact-base checkout, verify first, copy raw bytes and verify all 170 afterward. There is no automatic restore. Root verification SHA-256 `19d80ed63b1e8309d933454907eeac47de9c9b9b544e5ac12339f225a969c1ac`; 216-file evidence-manifest SHA-256 `c86ac708a3835ff60a5e85d1413a90be51d943add71f0f7958131a5ea0604d2b`. All source pins, four coefficient records, thirteen camera-packet hashes and 203 closed crop-evidence files remain unchanged. The corrected 329-pass/175-skip source gate remains valid; packaging changes no product code.

**Kill criterion:** wrong base, uncovered changes, unsafe paths or failed byte/membership checks reject the checkpoint/restore. Do not reopen baseline archaeology or other killed research.

**Limit:** archive readback was tested, not application to a fresh checkout or a clean native rebuild. Unchanged base assets/notices, firmware, original media, dependencies/toolchains, private fixtures and full ignored evidence remain external. The decision snapshot predates this closing text; no camera, release, license-clearance or installation claim follows.
