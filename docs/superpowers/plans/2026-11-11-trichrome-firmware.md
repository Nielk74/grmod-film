# Trichrome GR III 2.10 Firmware Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans in this worktree. No additional agents. Parent supplies independent review. Execution was explicitly authorized; no repeated design approval gate.

**Goal:** Build one experimental film-pack-based firmware that saves continuous-drive frames1/2 normally and applies quarter-width/height R1/G2 temporal deltas to frame3, consistently across main/screennail/thumbnail.

**Architecture:** An isolated post-builder accepts only the hash-pinned official GR III2.10 input and an independently verified v3 baseline with added film MTF disabled. A native module owns bounded persistent state and pixels; capture generation and frame membership must come from traced native capture events, never three arbitrary JPEG calls. Tripod-only integer alignment is acceptable for this first manual-test candidate; unproven handheld registration is not enabled.

**Tech Stack:** TypeScript existing container/firmware APIs; freestanding A32 C/assembly compiled by Zig Clang; Python Capstone/Unicorn/NumPy independent reference and structural audits.

**Spec:** User-requested actual custom firmware and parent task brief; existing desktop effect and limitations in `docs/trichrome.md`.

## Global constraints

- Work only on `codex/trichrome-burst` in this managed worktree. No push/release/flash.
- Official file SHA256 `d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4`; RTOS `8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67`.
- Preserve20film/v3color/tone/rows; disable extra film MTF in this experimental baseline only.
- Retain only owned R1/G2 pixel planes. Preflight all allocations/metadata before frame3 writes. Failure leaves normal frame3.
- Never combine unrelated single shots, different bursts/settings, or RAW developments.
- Full npm suite with official fixture before artifact delivery. Native parity, hook ABI, lifetime/failure, guard-page and patch-map audits required.

## File manifest (all new unless subsequently reviewed)

- `tools/trichrome_firmware/trace.py`: hash-pinned read-only native capture/queue provenance investigation and retained evidence.
- `tools/trichrome_firmware/native/trichrome.c`, `trichrome.h`: bounded state and integer YCbCr4:2:2 channel operation.
- `tools/trichrome_firmware/native/hooks.S`: exact guarded capture/JPEG interpositions preserving ABI/flags.
- `tools/trichrome_firmware/check.py`: Unicorn native/reference and lifetime tests, measured allocations and guards.
- `tools/trichrome_firmware/link.py`: deterministic freestanding link, sections/symbols/address guards.
- `tools/trichrome_firmware/build.ts`: v3 baseline/postpatch/container/readback/patch-map verification.
- `tools/trichrome_firmware/README.md`: exact manual tripod test, feature activation/reset, hashes and limits.
- This plan. Existing shared files remain unmodified unless a concrete manifest is sent to the parent first.

## Review focus

1. Queued frames crossing release boundaries: tag native capture generation/index before queuing; otherwise block the candidate.
2. RAW development/duplicate callbacks: explicit source identity gate, no-op and reset tests.
3. Concurrent cancellation/free: prove callback task serialization or use a reviewed state lock with complete initialization/lifetime.
4. Partial image or allocation failure: all output descriptors and scratch allocations validated before any frame3 pixel write.
5. Chroma alias/stride/crop errors: independent integer reference, guard pages, padding and static identity checks.

## Tasks and ledger

- [x] **1. Native capture contract for manual testing:** Original JPEG config/record lineage and native drive/clock functions execute in Unicorn. Native BeforeExpose supplies own exposure tags; JPEG consumes matching tags once. No native generation counter was established. Parent explicitly accepted this conservative fails-closed architecture for the experimental camera test; actual BeforeExpose-to-JPEG pointer identity/event ordering remains a hardware unknown.
- [x] **2. Native operation:** Independent integer parity, static identity, moving foreground, stride padding, guard pages/sentinels, aliases/ranges/crops, allocation failures, order, rearming and deferred cancellation pass. Actual full-resolution preflight requests 3,057,600 pixel/scratch bytes plus a524-byte adapter.
- [x] **3. Exact hooks:** Five guarded entries, linker-resolved continuations, atomic bootstrap at reserved5580438c, complete GPR/FPU/flags/SP tests. Actual candidate RTOS enters existing orientation/JPEG prior chains, executes original config builder and reaches native+4 with all three pictures exact on small fixtures.
- [x] **4. Build and audit:** Full npm suite with official fixture; pinned no-extra-MTF baseline; deterministic module; container growth/readback; all23 container checks; full change-range audit and hashes. README contains manual tripod/fixed exposure/WB/MF recipe and rollback reference. No flash/publish operation performed.

**Result:** One actual experimental GR III2.10 test candidate in `scratch/trichrome-firmware/fwdc239b.bin`; exact hashes and evidence in adjacent reports. Native exposure tagging counts actual BeforeExpose events, never arbitrary JPEG calls. Main/screennail/thumbnail all process consistently. No real burst or camera latency/heap/startup claim. The full-resolution visual is explicitly controlled synthesis over a read-only real photo.

**Expanded all-new implementation manifest approved during review:** `native/camera.c`, `build_baseline.py`, `check_camera.py`, `check_installed.py`, `render.py`, `audit.py` and pinned `requirements.txt` supplement the initial manifest. No existing shared source file was changed.
