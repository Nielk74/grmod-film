# WP3 — one decisive hue-stage test

Base: `db76c9b42f85d657a760d07af97735854f253c57`. Updated 2026-11-09. Status: T-colour host candidate built and independently reviewed; pixel activity still awaits camera evidence.

**Claim:** the retained native block can reach register packing, but pixel activity and group semantics are unproved.

**Evidence class:** source and emulated. Archived ORCH-005 demonstrated per-film block selection/packing, not changed pixels. All 26 factory styles share a block; 59 of its 60 groups are identity. The count is compatible with 12×5, but that does not establish hue/luminance semantics or activity.

**Decision:** make a strong control-vs-perturbed hardware test before any fitter port. Do not spend further time interpreting register changes as colour output. Portra's existing colour remains unchanged.

**Next step:** T-colour, one chart DNG, registered in-camera RAW developments:

| Probe | Contents | What it decides |
|---|---|---|
| A | Standard block | Control |
| B | All 60 groups strongly perturbed | Whether pixels change |
| C–H | Perturb group g when bit k is set | Six-bit group code |
| I–K | Row-sum scaling 0.5 / 0.75 / 1.25 | Scale and clipping |
| L | Group 0 only, changed row sums | Special group behavior |
| M–N | Distinct neighbouring perturbations | Boundary interpolation on a smooth hue ramp |

**Kill criterion:** B matches A after a valid registered test: record inactivity for the tested route and close the direction. No fitter work before a positive result.

**Limit:** probe slots are diagnostic, not suitable for shooting. Capacity and reset requirements must be explicit in the test build/card.

## Prepared candidate

`tools/gr3x/build-t-colour.mts` creates the ordinary verified R10 base, then appends data and redirects only fourteen existing table cells. Each source block is 60×9 signed int32 Q10 values, **2160 bytes**; 1080 bytes describes packed register fields, not the source allocation. Standard's six-word record is cloned with only its +8 pointer changed, and all eight mode pointers address that probe's complete block. Group 0 preserves its unusual 512 row sum except in the deliberate scaling probes.

Final local candidate: `research/gr3-210/test-session/ready/T-colour/fwdc239b.bin`, SHA-256 `d761ea15d50aeaecee0d08e44e63a00cb4dc0899a405c89fd5e8afd988502283`, 37,840,152 bytes. Evidence/source snapshots: `research/gr3-210/t-colour-host-20261109-r2`; independent review: `research/gr3-210/tcolour-review.md`.

All twenty films have no MTF/grain/date/ADJ Soft Focus module and zero halation gain headers. The six retained exact colour presets are Portra 64, CineStill 65, current Gold 66, approved Gold 67, Kodachrome 68, Astia 69; A–N occupy 70–83. All probes share identical Standard pre-matrix and neutral curve/post/default paths. General Engine deliberately returns unknown/unverified; the standalone format has a separate verifier and never enables normal app writing.

Host verification passes exact reverse to the ordinary base, deterministic byte-identical reapplication, complete independent Python reconstruction of blocks/records/pointers/allowed differences, checksums, sections and the existing bounded loader regression. The independent reviewer additionally checked all six retained payloads, all 137 source hashes and read-only repeat verification: all 12 artifact hashes unchanged. One CLI audit-file rerun defect was fixed before regeneration; the binary hash stayed identical. Camera startup, pixel activity, persistent settings and aesthetics remain untested. Full reset and the common card accompany the file.

First potential applications after a positive result: Gold/Kodachrome skin and CineStill teal versus red. Any Portra colour proposal stays an opt-in comparator chosen by the user.

## Paused halation excitation study

**Claim:** post-render colour can lose source-relative highlight information, and compact seed fits trade average error against false excitation.

**Evidence class:** source/model only; archived ORCH-006/007/011/012.

**Decision:** freeze this direction. Its model target has not been chosen by the user's eye, and its Gold reference predates approved Gold integration.

**Next step:** only a night-photo A/B on the exact reference set can reopen it.

**Kill criterion:** no visible preferred difference: drop it.

**Limit:** the final external ARM lookup spike was not completed and is not passing evidence.
