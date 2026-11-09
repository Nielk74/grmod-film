# WP1 — one flat verified source checkpoint

> Historical stage record. Firmware/replay environment requirements and current verification limits are qualified in [the shared index](../../GR3_EXPLORATION_REPORT.md). Packet-wide hash assertions below describe the original snapshot; the card metadata was intentionally revised later.

Declared before checkpoint copies or archive creation on 2026-11-09. Base `db76c9b42f85d657a760d07af97735854f253c57`; current branch `codex/gr3-crop-texture`. This consolidates verified local source bytes after the completed comparison-crop round. It does not change product code or reopen closed experiments.

**Claim and purpose:** ten chronological overlays are useful audit history but awkward to restore. Git uses `core.autocrlf=true` here; a patch alone does not preserve the verified raw file bytes. Produce one flat overlay of the complete 170 composed code/config paths, accompanied by current decision documents and explicit exact-base restoration instructions.

## Exact manifest and ownership

| Owner | Path | Permitted work |
|---|---|---|
| Root | This manifest, `BASELINE.md`, `PLAN.md`, short shared `docs/GR3_EXPLORATION_REPORT.md` | Declare/checkpoint decisions and final result; preserve readable index |
| Root | ignored `research/gr3-210/source-checkpoint-01/**` (new) | Capture raw inputs, create checkpoint scripts/flat `source/` files/decision `docs/` copies/manifest/README/local ZIP and independent readback results |
| Independent verifier agent | ignored `research/gr3-210/source-checkpoint-01/{verify-checkpoint.py,verifier-review.json}` only | Standalone stdlib verifier and its contract/self-test record; no import of root packager or restoration writes |
| Audit agents | Read-only Git/source/epoch/document inspection | Check coverage, base, line-ending/path semantics and artifact completeness; return findings to root |

No production/config/test file, Git index/branch/history, dependency installation, existing closed evidence, coefficient data, camera packet or device path may change. Root alone maintains the authoritative shared report. The checkpoint evidence report is at most 600 words; manifest and restoration details may be separate.

## Input, coverage and path gates

- Pin the exact base commit and latest closed `wp12-comparison-crop-implementation/source-final.json` (`46c67052bacb04438d3400bfb79d1ad58389188e0d9c7e1ec08eaf0e8e3f25b6`). Its checked composition contains 170 code/config paths and all current non-doc code/config changes. Verify every raw size/digest before copying; a parent history is context, not required to apply the flat overlay.
- Record all tracked/untracked nonignored changes using NUL-delimited Git output. Reject deletions/renames or a changed non-doc source/config path outside the 170 pins. Distinguish base-tracked and introduced files. Record raw versus normalized Git-blob differences without changing line endings. Include all 170 raw files even when their only difference from Git is EOL conversion.
- Use repository-relative forward-slash paths. Reject absolute/drive/UNC paths, empty or dot/dot-dot components, backslashes/colons/control bytes, duplicate case-insensitive names, symlinks/reparse points, and any resolved path outside the new checkpoint directory or repository. Never follow the existing ignored dependency junctions. Files must be regular files.
- Copy current `docs/GR3_EXPLORATION_REPORT.md` and `docs/research/gr3-210/*.md` as a clearly dated decision snapshot. The snapshot does not include later closing text; record its hashes. Preserve required external-evidence links as local dependencies, without pretending those targets are inside the source archive.

## Packaging and verification

Capture the decision documents once root's crop closure and this plan are saved. Copy source/docs bytes without conversion. Record SHA-256, bytes, base membership and source-relative names. Include a bounded self-contained verifier that checks manifest paths and archived bytes without writing the repository. Create one local ZIP; independently enumerate its members, reject extras/unsafe/duplicate paths, decode and hash every archived file. An independent verifier must not import the packager. Exercise malformed path/missing/corrupted-byte controls against in-memory or disposable checkpoint-only fixtures; never alter the live tree or existing evidence. Do not auto-apply the archive or run a Git checkout/reset.

The just-completed source is tested by 329 full passes / 175 skips (including GR IIIx/IV fixture paths), typechecks/build and independent source/browser acceptance. Packaging adds no product change; byte/readback verification is its additional gate. Recheck live 170 pins, fixed coefficients and sealed packet after packaging. Keep existing epoch manifests immutable.

Restoration requires a separate checkout at the exact base, applying raw files to their repository-relative paths, and verifying them before dependency install/build. The checkpoint is not a complete repository or full evidence backup. Exclude firmware binaries/derived research, original media, `node_modules`, runtime junctions, caches and `ui/dist`; unchanged assets and lockfiles come from the Git base. No release, license clearance, install/flash provenance or camera result follows.

**Kill criterion:** unresolved base/pin, any uncovered current non-doc change, unsafe/ambiguous file path, unintended mutation, missing/extra/corrupt archived member or false claim of standalone completeness stops the checkpoint. Fix a packaging defect only inside the declared new directory, preserve a rejected attempt, and repeat affected archive gates. Do not invent another source feature to justify continued work.

## Final result

**Retain and close.** Independent coverage and restoration-contract audits pass. The 170 raw source/config files cover all 47 non-doc changes; 156 base-tracked paths include 123 EOL-only differences and 33 content changes, plus fourteen introduced paths. The 25-document snapshot records 37 external-link occurrences/26 distinct targets as omitted dependencies. Every source entry declares required Boolean base membership, with exact 156/14 totals; root clarified the initial optional schema before packaging, and two semantic negative controls were observed red→green. The independent verifier imports no packager and performs no extraction/apply.

The actual ZIP and unpacked payload pass the standalone verifier. Root independently reads all 199 members and compares source bytes with the external inventory and live tree. All 170 pins, four coefficient records, thirteen sealed packet hashes and 203 closed crop-evidence files remain exact. The verifier's final self-check passes 56/0 with one Windows filesystem-symlink privilege skip; ZIP symlink/reparse controls pass. Actual Python 3.12.10; 3.9 syntax/API compatibility reviewed. Root's first ancillary readback assumed byte counts in older packet records; that checker/failure is preserved and the corrected check passes. The archive and product source did not change for that correction.

[ZIP](../../../research/gr3-210/source-checkpoint-01/checkpoint.zip): 1,248,130 bytes; SHA-256 `c30f6ff8b187187c717a2501bf2869e1c302477975dbee841c0aefa17f47070a`. [414-word report](../../../research/gr3-210/source-checkpoint-01/REPORT.md); [root verification](../../../research/gr3-210/source-checkpoint-01/root-verification.json) SHA-256 `19d80ed63b1e8309d933454907eeac47de9c9b9b544e5ac12339f225a969c1ac`. The 216-file [artifact manifest](../../../research/gr3-210/source-checkpoint-01/artifact-manifest.json), SHA-256 `c86ac708a3835ff60a5e85d1413a90be51d943add71f0f7958131a5ea0604d2b`, is freshly re-read and verified. No fresh-checkout application, clean native rebuild, product change, release, device write or camera result is claimed. Closing decision text is later than the dated snapshot and does not alter it.
