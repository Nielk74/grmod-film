# Loaded stage 1f reassessment — 2026-11-12

**Status: diagnostic rebuilt and packaged; software verification passed; no hardware
validation.** This document separates an independently reproduced layout defect
from the unresolved camera timing. Stage 1f remains a diagnostic, not the final
Loaded experience.

## Evidence identities and scope

The previous `loaded-ui` worktree was treated as read-only. Work and evidence
belong to the new `loaded-ui-stage1f-fix/grmod-film` worktree.

| Input | Identity |
| --- | --- |
| Original GR III 2.10 RTOS | 17,520,064 bytes; SHA-256 `8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67` |
| Exact film-pack base and rollback | SHA-256 `cf04126f5861c3a64123f0cdc95efa5b65443b44aa0ca975854423acf0131f55` |
| User video | `VID20261112020034.mp4`, 79.644041 s, 1080×1920, nominal 30 fps |
| Audited pre-reassessment stage 1f ELF | SHA-256 `fb5365d1834cd7d8c7840d70d02a444b0f4beaa14edc8a0ad6b9dcc851e63ff7` |
| Audited pre-reassessment patched RTOS | SHA-256 `e1d09c24d4b736755773b649dd2dbee09c6c2840f08646f9f42c3c31b679315e` |

The last two hashes identify the candidate that was audited, not the new output.
No camera, card, release, tag or publication is part of this work.

Evidence files are kept under `scratch/audit-layout`, `scratch/audit-trigger`,
`scratch/audit-video` and `scratch/stage1f-audit`. These are local audit artifacts,
not required product files. The original RTOS and video remain external inputs.

## Independently established layout defect

Executing the unmodified camera's view creation, attachment, layout and paint
code reproduces the defect on an already clean root. A newly constructed type-10
view already has its own layout flags set. Attaching/showing it does not propagate
a new request through a clean parent. Its absolute and clip rectangles therefore
remain zero and drawing is rejected. Ordinary draw invalidation is a separate
operation and does not substitute for layout.

The root's virtual method at slot `+0x20`, pointing to `0x533ab3cc`, marks the
required ancestor layout work. Calling it with the attached child as requestor
lets the following native paint compute the expected rectangle. Eight relevant
original-firmware function ranges match the film-pack base byte for byte.

The pre-reassessment diagnostic panel had the same attachment defect. On a clean
root, it became visible only if a later successful Loaded attachment happened to
request layout. Failure before that stage could hide the error panel itself.
Both the panel and all four Loaded views now request layout after attachment.
This behavior applies to every shot and reattachment.

The earlier A/B/C experiment was history dependent: a successful A shot laid out
views whose rectangles were retained by B and C. Sequential A→B→C shots could
therefore all copy successfully. The revised diagnostic has one stable layout
behavior and identifies itself as `DIAG 1F FIX`.

The earlier `first_draw_ms` measured the first panel callback even when it was
rejected. The audit reproduced a callback at +77 ms with reject 11 and zero
copies, followed by a successful copy at +100 ms without changing the recorded
77 ms. The revised panel keeps attempted `CALL` and successful `COPY` timing
separate. A successful native copy remains weaker evidence than a physical
display observation.

Evidence: `audit-layout/original-stock-results.json`, `stock-layout-results.json`,
`diagf-panel-results.json`, `diagf-sequential-variants.json`,
`diagf-first-draw-results.json` and the accompanying `audit-report.txt`.

## Native trigger and task semantics

The native message-name decoder at `0x5382d2e0` was executed after reproducing the
stock initialization copy. The native dispatch routes were also executed with
only application/model getters stubbed. These identities are not inferred from
neighboring strings or low-byte ordinals:

| Raw message | Native name | Verified route |
| --- | --- | --- |
| `22441228` | `EVT_SHOOTING_EXPOSURE_START` | UI `0162` |
| `22440229` | `EVT_SHOOTING_EXPOSURE_END` | UI `0163` |
| `23480201` | `EVT_IMAGE_BE_COMPLETE` | Existing hook at `0x532d55f8`, then UI `016C` |
| `23480603` | `EVT_IMAGE_BE_QUICK_VIEW_READY` | UI `016B` |
| `23480204` | `EVT_IMAGE_BE_ALL_IMAGE_WRITE_COMPLETE` | Separate handler `0x53236ab4` |
| `22441601` | `EVT_SHOOTING_RELEASE_START` | Native message |
| `22441702` | `EVT_SHOOTING_RELEASE_STOP` | Native message |
| `22441703` | `EVT_SHOOTING_RELEASE_START_CANCELED` | Native message |
| `2244102A` | `EVT_SHOOTING_READOUT_START` | Native message |

The recovered completion path is the UI loop → queue drain → UI `0199` receiver
callback → native-message dispatcher → CaptureImageModel → BE-completion hook.
This supports retaining UI operations on that path. The six existing hook sites
and the BE-completion trigger are unchanged. Exposure events are observed to
clarify timing; they do not silently become a new animation trigger.

`HK` is not proof of physical exposure time or all-image-write completion. The
subsequent `016C` enqueue carries neither payload nor receiver identity, so it
does not identify a particular photo. Its dispatch can occur after a snapshot
already frozen at `HK`.

The release hook runs at the entry to
`ShootingModel::OnReleaseControlTriggerOn`, `0x53239818`, before validation. The
native refusal path was executed: model byte `+0x0a == 2` still reaches this entry
and returns zero. A busy path may also be retried internally by release-stop
handling. `RL` therefore counts attempts, not photos. The last-RL-to-HK interval
is an observation interval with an attempt-count delta, not exposure duration.

The old release callback called cancellation code that mutated UI state despite
its logging-only comment. The revised callback uses a single-try mailbox gate
to publish an observation. The dropped-record counter uses a lock-free atomic
increment that can retry; this does not establish a fixed bound on every
instruction of the entire release callback. The UI task consumes the record and
owns allocation, mutable telemetry, cancellation, timers and views. Contended
observations that cannot be published are counted explicitly.

The native UI envelope is 12 bytes: a uint16 ID at offset 0, payload pointer at
4 and receiver pointer at 8. For `0199`, decode a raw uint32 ID only after checking
nonnull aligned receiver, its vtable `0x53b1f2cc`, and nonnull aligned payload.
Read only payload offset zero. Other `0199` callback payloads must not be
dereferenced as native messages. The logger keeps all 32 bits of a raw ID for
lookup and display.

Evidence: `audit-trigger/trigger-evidence.json`, `findings.txt`,
`native-message-name-decoder.txt`, `raw-message-to-ui-envelope.txt` and
`verify_trigger_evidence.py`. A bounded direct-reference scan does not establish
complete indirect-call coverage or every possible task route.

## Corrected video observations

Individual `ffmpeg -ss` seeks, mostly 0.2 s apart, were inspected directly. A
decoded frame may be approximately one frame later than the requested timestamp.
The first overview made with output `-r 1` has unreliable index-derived labels;
only individual `tNNN.NNN.png` frames and `dense_*.jpg` sheets support the timings
below. The video cannot reveal the electrical half/full-press detent.

| Time in video | Observation |
| --- | --- |
| 0.0–0.6 s | Standard, green focus boxes, native remaining count 2048, no panel. |
| 0.8–1.6 s; 1.8 s | LCD black, then live view at 2047, no panel. |
| 11.8 s; 12.0–12.2 s | Green focus illumination, then diagnostic panel while count is still 2047. |
| 12.4–13.0 s; 13.2 s | Second blackout, then live view at 2046 and panel rectangle. |
| 18.5 s | Standard ABS rows 1–4 each show `0 0 0 0 1`; the diagnostic panel is visible. |
| 42.0–42.6 s; 43.6–44.2 s | Portra illumination first; later blackout, returning at 44.4 s with 2045 and no panel. |
| 51.8–52.2 s; 53.8–54.6 s | Portra illumination first; later blackout, returning at 54.8 s with 2044 and no panel. |
| 58.6 s | Diagnostic panel reports `SHOT 3`; native count stays 2044. |
| 59.4 s; 60.4 s | Proof boxes, then filmstrip showing 3, advancing to 4 by 61.5 s. |
| 73.2 s | Diagnostic panel reports `SHOT 4`; native count is still 2044. |
| 73.8 s; 74.8 s | Proof boxes, then filmstrip showing 4, advancing to 5 by 76.0 s. |

The Standard panel precedes the second capture-like blackout. The earlier labels
“photo at 11.5 s” and “Portra photos at 42 s and 52 s” were overconfident: the
latter coincide with focus illumination, not the later blackouts. Blackout plus
counter decrement is stronger capture evidence than the counter alone, but does
not provide an exact shutter timestamp.

Four capture-like blackout/decrement sequences are visible. The late Portra
panels then show SHOT 3 and SHOT 4 without another visible blackout or decrement.
This makes deferred earlier work at a later wakeup a relevant hypothesis; it does
not choose between processing, queue delivery, scheduling or a render condition.
The user additionally reports that Fn, Up and other buttons wake the animation.
Half-press is therefore not established as a unique trigger.

No Quick Review settings page is visible. Quick Review being disabled is
user-supplied context, not an independent finding from this recording. The earlier
7/8 ms “FIRST DRAW” values must not be treated as physical-shutter-to-display
latency.

Evidence: `audit-video/audit-report.txt`, `dense_standard.jpg`,
`dense_portra_first.jpg`, `dense_portra_second.jpg`, `dense_panel_first.jpg`,
`dense_panel_second.jpg`, `panels_0.png` and `panels_4.png`.

## Revised diagnostic contract

The distinct-event table has 24 rows, reset for each consumed RL observation
window. Startup traffic cannot permanently reserve all rows. Counts, first/last
times and identifiers freeze at HK so later button input does not rewrite that
window. Overflows are explicit. Event timestamps measure UI handling, not when
the native producer originally emitted its message.

| Zero-based page | Readout |
| --- | --- |
| 0 | `DIAG 1F FIX`, cells and proof status. |
| 1–6 | `EVENTS n/6 AT HK`, four two-line entries each. |
| 7 | `LAST RL>HK OBS MS`, three intervals and their RL-count deltas. |
| 8 | Per-view counts. |
| 9 | Last rejection and surface facts. |
| 10 | Absolute rectangles. |
| 11 | Event counters, first callback `CALL`, first successful `COPY`. |
| 12 | Cancellations. |
| 13–14 | Per-shot log. |
| 15 | Global log. |
| 16 | Pre-hook log. |

Seventeen pages at 1.5 s each give a 25.5 s cycle after HK. An event row contains
`R` plus eight raw-ID hex digits or `U` plus four UI-ID hex digits, `N` count and
optional `B`; its second line has `F` and `L` millisecond offsets. `B:SEEN BEFORE
RL` means only observed in the preceding interval, which may include the previous
photo's aftermath. It is neither a periodicity test nor a causal classification.
An absent B is not proof of capture causality. `OVF` counts observations that
could not obtain a table row; it increments for each unrecordable hit, not just
each distinct unknown ID. `BG` gives that count for the preceding window.

Counts display up to 99999, then `99K+`; millisecond times up to 99999, then
`99S+`. Full 32-bit values remain in RAM. Unknown row time is `-`; this also covers
a first timestamp unavailable because mailbox observations were coalesced. Page
7 uses `NO NEW RL` or `UNKNOWN` when appropriate and displays `MAILBOX DROP`.
Invalid clocks must not become a plausible zero-duration observation.

## Hardware capture to perform

Record the screen continuously, with the shutter action visible or audible, and
note Quick Review and the exact time of every input. Keep settings stable.

1. Portra 400, one photo, no input for 30 s. If no panel is visible at 30 s, press
   Fn once, record its time, then film another 30 s with no further input. Keep
   recording through the full cycle if the panel appears late; wait for it to clear.
2. Standard, one photo, the same 30 s observation. Optionally use Up once after
   30 s if no panel appears, recording that choice and time, then another 30 s.
   Wait for the panel to clear.
3. Portra 400, one photo with normal subsequent inputs allowed. Record what was
   pressed and when, and keep filming through the panel cycle.

Record panel, proof boxes, filmstrip, blackouts and remaining-count changes
separately. Do not infer photo count from RL or a unique photo identity from HK.

## Reproduction and build commands

Use the new worktree only. The Python environment needs Unicorn, Capstone and
pyelftools; linking needs the configured ARM-capable Clang and LLD. PowerShell
variables below name local tools and read-only inputs; assign their actual paths
before running. The native build's default stock path follows a different
worktree layout, so pass `--stock-rtos` explicitly.

```powershell
$env:LOADED_VARIANT = 'diagf'
$env:PYTHONDONTWRITEBYTECODE = '1'
& $pythonPath scratch/audit-layout/audit_original.py
& $pythonPath scratch/audit-trigger/verify_trigger_evidence.py
& $pythonPath tools/loaded-ui/native/link_loaded.py --pack $filmPackPath --stock-rtos $stockRtosPath --clang $clangPath --lld $lldPath
& $nodePath node_modules/vite-node/vite-node.mjs tools/loaded-ui/build-loaded-stage1.ts $filmPackPath
& $pythonPath tools/loaded-ui/native/check_diag_f_events.py
& $pythonPath tools/loaded-ui/native/check_diag_f.py
& $pythonPath tools/loaded-ui/native/check_hooks_loaded.py
& $pythonPath tools/loaded-ui/native/check_loaded.py
npm.cmd --prefix tools/loaded-ui test
npm.cmd --prefix tools/shot-animation test
npm.cmd test
& $pythonPath tools/loaded-ui/native/check_package_diag_f.py
& $pythonPath tools/loaded-ui/native/package_diag_f.py --pack $filmPackPath --counts $verifiedCounts
```

Set `$verifiedCounts` to the actual verified suite totals. That argument records
operator-supplied results; it cannot override artifact verification. Earlier
adapter/hook regression runs and deterministic
reproduction of earlier diagnostic images are also required by the plan, using
their own variants and output directories. Restore `LOADED_VARIANT=diagf` before
the final stage 1f checks and packaging.

`check_loaded.py` includes the 622 robustness checks as well as renderer parity;
the standalone robustness script is not an additional required pass here.

The focused tests must cover clean-root first paint and early failure, ordinary
sequential shots, reattachment, callback versus successful-copy timing, release
mailbox/UI ownership, raw-ID distinction and invalid bridge pointers, startup
table saturation, clock failure, overflow, frozen snapshots, contention and real
event-trampoline instruction counts. The measured counts sample steady-state
execution from the real event trampoline to its native continuation with
allocator/clock boundaries stubbed. They are not CPU time measurements.

## Artifact binding and final verification record

Packaging refuses to write delivery files until the following agree:

- Delivered container bytes/hash and build report identity/checks.
- Actual `patched-rtos.bin`, the build report's RTOS section and both verification
  reports, plus actual pack RTOS identity and extent.
- Actual payload bytes/hash, manifest, hook report and payload slice in RTOS.
- Actual ELF hash, manifest and adapter report.
- Every current manifest source hash, including the generated slots header.
- The six established hook sites, unchanged non-RTOS sections, exact base,
  unraised version, hardware-untested identity and measured instruction costs.

The summary also records report, manifest and packaging-script hashes. Agreement
between two reports without checking actual files is insufficient. The rollback
is copied only after validation and is the exact film pack above.

| Final result | Value |
| --- | --- |
| Rebuilt stage 1f output SHA-256 | `d598635d29380fd895337e4eae34275f25938e6f06632f7b82164f267706ccc4` — actual image digest matches build report and packaging validation passed |
| Output bytes / payload bytes / RTOS extent | 38,524,400 / 53,220 / `0x541b15c0` |
| Diagnostic assertions / scenarios | 230 assertions across 13 scenario groups; diagnostic block 173,476 bytes |
| Focused telemetry tests | 15 passed, including clock recovery and rendered unknown-time glyph checks |
| Event-hook sampled instruction counts | New timer 219; repeated timer 193; timer after 500 ms 225; raw message 232; full table unknown ID 324 |
| Six-hook verification / rejected regressions | 24 detour cases; 3 regressions rejected: film-pack byte, appended film byte and missed hook |
| Renderer parity / robustness | 4,280 cases; 21,400 view-frames matched, zero mismatched; 622 robustness checks |
| Repository suite | 206 passed; 197 fixture-dependent skipped |
| Loaded / shot-animation JavaScript suites | 38 / 41 passed |
| Packaging validation | 11 checks passed against final actual artifacts; altered bytes and stale/missing evidence rejected without editing build outputs |
| Delivery packaging | Completed; README, checksums, verification summary and exact-base rollback written after validation |
| Earlier adapter/hook regressions and image reproduction | Stage 1, 1d and 1e adapter/hook checks passed; each image reproduced its recorded digest exactly |
| Hardware validation | **Not performed** |

The final software logs are `scratch/stage1f-audit/diagf-final.txt`,
`focused-final.txt`, `hooks-final.txt`, `renderer-full.txt`,
`repository-final.txt`, `loaded-js-final.txt`, `shot-js-final.txt` and
`earlier-image-reproduction.json`. The 17 rendered panel pages were visually
checked in `panels-final.png`; full raw IDs, unknown-time dash and colon footer
remain legible. The packaging regressions first ran as the read-only scratch
script `scratch/audit-video/test_package_diag_f.py` and are preserved as
`tools/loaded-ui/native/check_package_diag_f.py`, where all 11 passed again after
the final packaging text corrections.

The baseline run recorded by the plan was 206 repository tests passed and 197
fixture-dependent tests skipped, plus 38 Loaded JavaScript tests passed. These
are baseline results, not evidence for the final rebuilt bytes. The copied
candidate failed its asserted instruction-cost bound (157/132/157 against
`<120`), which must not be reported as a passing check.

The fixtures substitute allocation, clocks, alarms, controller inputs and
synthetic surfaces. They cannot establish RTOS scheduling, cache/DMA effects,
physical display timing, or why input wakes the field animation. The proven
layout correction and clearer observations narrow the investigation; only a
corrected hardware capture can resolve the remaining behavior.
