# Loaded UI diagnostic reassessment implementation plan

> Execution: implement in this new worktree with independent evidence audits and a final review. The user authorized completion without questions.

**Goal:** repair proven layout and diagnostic defects, preserving a truthful distinction between emulated rendering and camera timing.

**Architecture:** keep the recovered UI-task completion hook and timer-driven adapter. Explicitly request native layout after every attachment. Confine mutable telemetry and native UI operations to the UI task; the release-control callback publishes a bounded mailbox. Decode the verified native-message envelope, capture per-window distinct events, and freeze the readout at completion.

**Tech stack:** freestanding ARM C, LLVM, Python/Unicorn/Capstone, TypeScript firmware container builder, Node tests.

**Spec:** user request and handoff attachments; later corrections require independently checking the diagnosis, and record that Fn/Up/other buttons can wake the animation. Original worktree is read-only. No camera, card, release, tag, or push is requested.

## File manifest

- `tools/loaded-ui/native/camera_diag_f.c`: stable panel/Loaded layout, successful-copy timing, release mailbox, guarded 32-bit message decoding, window reset and frozen event table, honest compact readout.
- `tools/loaded-ui/native/check_diag_f.py`: replace contaminated A/B/C expectations, exercise normal sequential shots and early-failure panel painting, maintain all existing failure/lifecycle scenarios, call focused telemetry checks.
- `tools/loaded-ui/native/check_diag_f_events.py` (new): failing regressions for UI mutation from release, startup-table saturation, raw-message distinction, clock failure, overflow, mailbox contention, snapshot stability, and bounded instruction costs through real trampoline.
- `tools/loaded-ui/native/link_loaded.py`: preserve copied allocation flag binding; include new verification input hashes if required.
- `tools/loaded-ui/native/package_diag_f.py`: bind reports to delivered bytes; accurate README/test card, unproven timing marked as such.
- `tools/loaded-ui/native/check_package_diag_f.py` (new): preserve eleven package binding regressions, including stale sources and altered binary/report rejection.
- `docs/LOADED_STAGE1F_REASSESSMENT.md` (new): verified evidence, corrected video timeline, limitations, build/test commands and delivered hash.
- Ignored `scratch/stage1f-audit`, `scratch/audit-*`, and `tools/loaded-ui/out`: provenance, visual/disassembly evidence, test logs and rebuilt artifacts only.

## Tasks and checks

- [x] Create managed worktree at source HEAD and copy unfinished changes/artifacts without writing source. Branch `codex/loaded-ui-stage1f-fix`.
- [x] Independently reproduce layout using original firmware, audit UI callback/message semantics, inspect original video.
- [x] Baseline default repository suite: 206 passed, 197 fixture-dependent skipped. Loaded JS: 38 passed. Copied stage1f fails its own cost assertion: 157/132/157 instructions versus asserted <120.
- [x] Reproduce release callback detaching views/stopping timer; reproduce table saturation excluding new 0199/016c events after a new release.
- [x] Write and run focused regressions against copied implementation before fixes; preserve expected failures in the local audit logs.
- [x] Apply scoped repairs and run all 15 focused regressions green, including independent-review clock recovery and visible unknown-time glyph checks.
- [x] Rebuild final bytes; pass 230 diagnostic assertions, 24 hook cases, 21,400 renderer frames and 622 robustness checks. Earlier stage 1/1d/1e images reproduce byte for byte and their adapter/hook checks pass. Repository: 206 passed, 197 unavailable-fixture skips; Loaded JS: 38 passed; shot-animation JS: 41 passed.
- [x] Correct package/readme, pass 11 package binding tests, verify hashes and source isolation, independently review, and prepare the verified local change for commit.

Final packaged diagnostic SHA-256: `d598635d29380fd895337e4eae34275f25938e6f06632f7b82164f267706ccc4`.
Hardware validation remains outside this completed implementation/packaging run; the delivered test card records the remaining timing question.

## Review focus

- A clean parent at first attachment and failure before Loaded allocation must still show the diagnostic panel.
- Later successful shots must not inherit a hidden A/B/C experiment condition.
- Release-control attempts can fail/retry; last attempt to completion is not exposure latency or one-photo pairing.
- Timer event0199 must not conceal raw message23480201 or cause arbitrary pointer reads.
- An early boot event flood, late button input, clock failure or concurrent release must not silently overwrite/mislabel the captured event window.

## Evidence rulings

- Layout is a sufficient, independently reproduced defect, not proof of the sole hardware cause.
- Stock BE-completion messages reach this hook through the recovered UI callback chain. The exact reason for delayed visible animation remains unresolved without a corrected camera capture.
- The video first shows the Standard panel before its second capture-like blackout; earlier shutter timestamps were overconfident.
- User reports Fn, Up and other buttons also wake animations. Do not label half-press as the unique cause.
- Background markers mean only seen in the preceding observation window; no causal or periodic classification is established.
