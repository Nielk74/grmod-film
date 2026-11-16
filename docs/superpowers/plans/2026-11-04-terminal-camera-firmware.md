# Terminal camera firmware implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved neon Terminal post-shot animation into an exact GR III 2.10 custom firmware image.

**Architecture:** Preserve the approved twelve native sprites and sample the existing animation into bounded fixed-point transform and vector-command data. A freestanding ARM renderer consumes that data without a browser or stored video frames. A camera adapter uses only independently established capture/UI/timer/bitmap/audio services; the container builder validates stock bytes, model identity, checksums and round-trip output before packaging.

**Tech Stack:** Node24, TypeScript firmware container tools, Playwright for vector extraction, freestanding A32 C compiled with Clang/LLD, Python Capstone/Unicorn for ABI and native execution checks.

**Spec:** `tools/shot-animation/PRODUCT.md` and the user's instruction to build the custom GR III firmware now.

## Global constraints

- Target the exact GR III2.10 official file `fwdc239b.bin`, SHA256 `d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4`; reject other input identities.
- Preserve all three random transitions, the approved neon raster art, 1400ms entrance, full5000ms performance,1200ms exit, facing and synchronized Pocket Lab/SFX.
- Twelve cached128×128 poses; no stored video frames or photographic JPEG/DNG buffer changes.
- Nonblocking UI-task rendering, bounded writes and allocations, replacement on a new shot, immediate interruption for native camera lifecycle changes.
- Keep camera sound ownership and mute policy explicit; an unavailable or busy sound device must not block capturing.
- No guessed firmware addresses. A string occurrence is a discovery candidate, not a verified ABI or hook.
- Run full project tests before a release artifact. Do not flash the camera or publish a release as part of this build request.

## Review focus

- Failed shots or a disabled quick-review setting must not fabricate a successful-shot animation.
- New shutter/menu/playback/power events must cancel owned visuals and audio without stopping an unrelated sound.
- Late/wrapping clock values must skip stale frames and clear at7600ms.
- Malformed asset counts, offsets, palette indices and geometry must fail before the first framebuffer write.
- Patched stock instructions, branch ranges, initialized RAM and container section identities must all be verified before generating the output file.

## Task1: Camera service evidence

**Files:** evidence/helpers only under `tools/shot-animation/out/firmware-lifecycle/` and `out/firmware-overlay-sound/`; the existing read-only `probe_firmware.py` remains available.

**Interfaces:** produces exact input hash, stock byte signatures, caller/callee analysis, ABI records and explicit known/unknown facts for capture, timer, bitmap ownership and sound services.

- [x] Verify the exact official and RTOS identities against the repository's GR3_210 profile.
- [x] Trace capture, UI dispatch, timer, overlay lifecycle and audio resource ownership; distinguish inferred candidates from demonstrated paths.
- [x] Execute focused original ARM code with controlled substitutes where possible to test argument layouts and state transitions.
- [x] Record evidence for every proposed patch site and callable service. Establish owned UI/audio lifetime with native tree removal and a permanent mutex that drains in-flight audio before destruction. Label the result as an experimental hardware-test candidate, with physical completion-mode and device behavior still unverified.

## Task2: Native asset and renderer

**Files:** create `tools/shot-animation/firmware-assets.mjs`, `export-firmware.mjs`, `test/firmware-assets.test.mjs`, `native/terminal.h`, `native/terminal.c`, `native/test_terminal.c`, `native/check_terminal.py`. Preserve the earlier prototype's `player.*` and its tests.

**Interfaces:** `encodeTerminalAsset({palette,indices,samples})` returns a versioned checked binary. `terminal_load(player,asset,bytes)` validates it. `terminal_render(player,sequence,elapsed,rgba,stride)` draws a bounded240×176 transparent frame from128px cached poses and geometric commands. `terminal_shot`, `terminal_tick`, and `terminal_cancel` own nonblocking lifecycle callbacks and random selection. The adapter supplies UI-owned storage and a verified millisecond clock.

- [x] Write and run failing asset tests for alpha/pose preservation, full three-sequence timing, affine placement/facing, malformed offsets/indices/commands and deterministic export.
- [x] Export30fps inverse affine samples and ordered filled geometric commands from the current renderer; deduplicate repeated effect data and keep raster pose pixels shared.
- [x] Implement strict binary decoding and integer bounded rasterization; no allocation or floating-point library in a frame.
- [x] Run real compiled ARM tests with canaries, corruption cases, deadlines, wrapping time, repeated shots and cancellation. Compare sampled native artwork placement and effect geometry with browser exports.

## Task3: Verified camera adapter and container

**Files:** create `tools/shot-animation/native/camera_gr3.c` and `tools/shot-animation/build-firmware.ts` only after Task1 establishes the services consumed. Add focused original-image/emulator checks alongside the native checker. Update `README.md` with actual build results.

**Interfaces:** consumes Task1's verified ABI and byte signatures and Task2's immutable asset/renderer. Produces a deterministic patch manifest and a GR III-only rebuilt container. Rejects missing service evidence, signature mismatch, unsupported identity, out-of-range branches and overlapping memory/patch ranges.

- [ ] Write failing adapter tests covering successful/failed shot, review disabled, periodic UI tick and interruption, render ownership and audio cancel/mute/busy paths.

  The adapter tests cover the callback, periodic ticks, ownership, interruption, timing, audio and teardown. Native producer fixtures cover thirteen recipe plans, including nine without a preview operation. Physical successful/failed-shot, review-disabled, RAW+JPEG and drive-mode cardinality remain unchecked; neither the candidate nor its reports claim those hardware results.

- [x] Implement only the established adapter paths. Never route the animation through the captured-image processing buffer.
- [x] Validate all stock signatures before any mutation, link the ARM payload, append aligned data/code, repair required section/container checksums and decode the output again.
- [x] Verify all changed ranges, runtime addresses, unchanged unrelated sections, target model/version and rebuilt bytes.

## Task4: Delivery verification

**Files:** build artifacts and reports under `tools/shot-animation/out/firmware/`; durable build/native source stays in the lab. No version bump, tag, push or GitHub release is requested.

- [x] Run the full repository and animation test suites, production builds and native/emulator checks with explicit skipped-test counts.
- [x] Obtain a fresh firmware code/evidence review and resolve material findings. Review caught stale artifact binding and the native audio factory's dangling service pointer; exact hash binding, a shutdown latch and native mutex serialization resolve them. Final actual-payload tests cover three shutdown preemption windows.
- [x] Package the actual rebuilt `fwdc239b.bin` with SHA256, patch/build reports and target-specific notes, accurately stating physical-camera test status.

Final local candidate generated 2026-11-05: 36,557,676 bytes, SHA-256 `99f375bf0ec83df3a15d1d096555d2669677188540caa88f61737c8fb858d0b0`. The verified delivery archive is `tools/shot-animation/out/firmware/GRIII-210-neon-terminal-experimental.zip`. Repository tests: 228 passed / 175 fixture-dependent skipped; animation tests: 41 passed; current native renderer: 596 assertions and 18 visual comparisons; final actual linked adapter: 24 scenarios; final detours: 24 flag cases; container: all31 checks pass. Physical camera validation remains the unchecked scope recorded above.
