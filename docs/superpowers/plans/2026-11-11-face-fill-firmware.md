# Face fill firmware implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline. The user authorized two native firmware experiments and the parent reviews this feature; do not create additional agents.

**Goal:** Produce one manually testable GR III 2.10 firmware with bounded face-local fill on the existing twenty-film v3 pack.

**Architecture:** Trace a shot-owned face result into the still JPEG configuration and copy validated rectangles into module-owned bounded storage. A position-independent native module processes supported YCbCr 4:2:2 pictures before the existing picture chain, leaving Standard and missing/invalid results untouched. Use a separate experimental installer/builder rather than new public UI or application settings.

**Tech stack:** TypeScript firmware container/build helpers, freestanding ARM C, Zig/LLVM, Python Capstone/Unicorn and independent integer reference.

**Spec:** User request to build two custom firmwares for manual testing; parent assignment of 11 November 2026, following `docs/face-fill.md`.

## Global constraints

- Exact GR III 2.10 official input only; container/RTOS hashes pinned to the existing profile.
- Windows PowerShell; explicit text encodings; originals and shared worktrees read only.
- Full npm suite with official fixture before naming a final flashable artifact.
- No external publish, tag, push, flashing or camera/card writes.
- Missing/stale/unrecognized face data must no-op. Do not dereference a live exposure pointer without proved lifetime.
- Preserve existing film colour and recipe defaults. Standard is the proposed unchanged control.
- Parent decision: disable extra FilmMTF only in the isolated experimental baseline to isolate this operation and avoid MTF heap/latency; preserve v3 colour/tone/recipes.
- No pre-film reference for keeper. Include only a verified one-input variant if feasible.

## Review focus

- A second exposure or stale list must not inherit prior face boxes: trace/probe shot ownership and explicit invalidation.
- Crop/orientation/aspect transforms must match the actual encoded picture; unsupported modes must no-op.
- Malformed descriptors, rectangles, counts, plane overlap, strides and padding must never cause out-of-range writes.
- Native state, stack, cache operations and the complete existing JPEG chain must remain intact.
- Feature enablement must be understandable and observable on camera; do not deliver an inert/diagnostic-only artifact as complete.

## Files and review boundaries

New `tools/face_fill_firmware/trace.py`: bounded exact-byte source and native reader probes.
New `tools/face_fill_firmware/module.c`, `gen.py`, `check.py`: module, position independence and independent byte-for-byte tests.
New `tools/face_fill_firmware/install.ts`, `build.ts`: guarded post-v3 installation, repack, patch map, readback and artifact audit.
New `tools/face_fill_firmware/README.md`: build and manual enable/control/rollback instructions.
Existing `docs/face-fill.md`: append observed native results and remaining hardware uncertainty.
Existing dependency file may gain pinned native build/probe dependencies. No broad refactor is planned.

### Task 1: Prove shot-specific source and mapping

- [x] Trace original 0x040b writer and reader and the JPEG configuration/record owner.
- [x] Save bounded source-byte evidence and reproduce original native reader/copy behaviour under Unicorn.
- [x] Establish crop and orientation semantics; define supported subset and fail-closed gates.
- [x] Parent review of trace and proposed native control before installing anything.

### Task 2: Native module and reference

- [x] Write failing numerical/descriptor tests first.
- [x] Implement bounded soft oval/skin gate, headroom-protected face fill in actual YCbCr 4:2:2.
- [x] Test no-face, Standard, malformed data, overlapping rectangles/descriptors/planes, stride/padding, allocation failure and page guards.
- [x] Compile at two origins and compare bytes; verify no runtime imports/data relocations.
- [x] Compare native bytes to an independent integer reference and check callee-saved registers/stack/cache activity.

### Task 3: Guarded firmware installer and complete hook

- [x] Build existing twenty-film v3 baseline without changing its colour/recipes.
- [x] Install module only at exact instruction guards with bounded owned data.
- [x] Probe actual source-read + full JPEG chain with valid, absent and invalid faces; compare reference pixels and CPU/cache integrity.
- [x] Verify container readback, original identity, every modified range and module source hash.

### Task 4: Acceptance and handoff

- [x] Full npm suite with official GR III fixture, type checks and build checks as appropriate.
- [x] Independent native/source/hook probes tied to exact candidate hash.
- [x] Parent critique and corrections.
- [x] Save one final `scratch/face-fill-firmware/fwdc239b.bin`, SHA, build report, patch map and manual instructions including control and rollback.
- [x] Commit source only after verification; leave generated firmware local and untracked.

## Acceptance limits

The source/capture/config/setup and complete synthetic installed-chain probes pass; the physical camera queue, burst membership and timing have not been observed. RAW development is unsupported/unverified and may use valid saved face records. Supported manual-test subset is full L6000×4000,3:2,zero offsets; other geometry no-ops. No hardware flash/publish is performed. Parent independently verified full npm suite/typecheck/UI build before final candidate rebuild.
