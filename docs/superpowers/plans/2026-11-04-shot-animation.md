# Five-second post-shot animation implementation plan

**Goal:** Compare three polished, funny nerd animations made using three current online skills, choose the strongest, and prepare it for the Ricoh screen after each successful shot.

**Spec:** User requested a small animation on the Ricoh camera, satisfying motion, exactly five seconds, optional sound, three experiments with three different skills, and an agent-selected winner.

**Architecture:** Isolated Vite/React comparison lab with actual GSAP, Remotion and Web Animations implementations. Export deterministic 20 fps transparent tiles into a bounded RLE RGB565 asset. A freestanding C player consumes successful-shot, UI-tick and interrupt events through an explicit camera adapter. Camera integration requires verified event, overlay, timing and sound services; do not substitute the JPEG image pipeline or modify captured photos.

**Tech stack:** React 18, Remotion 4.0.540, GSAP 3.15.1, WAAPI, Node, Python, freestanding C.

## File manifest

- `tools/shot-animation/package.json`, `package-lock.json`, `tsconfig.json`, `index.html`, `.gitignore`: independent lab and reproducible dependencies.
- `tools/shot-animation/src/main.tsx`, `artwork.tsx`, `experiments.tsx`, `sound.ts`, `styles.css`: comparison, three authored sequences, controllable synthesized sound.
- `tools/shot-animation/codec.mjs`, `export.mjs`: strict asset format, deterministic exports and visual QA captures.
- `tools/shot-animation/native/player.h`, `player.c`, `test_player.c`, `check.py`: portable bounded native playback and host/ARM checks.
- `tools/shot-animation/test/codec.test.mjs`: format corruption and roundtrip tests.
- `tools/shot-animation/README.md`, `research.json`: skill provenance, measured comparison, winner and integration status.

## Constraints and review focus

- All three run exactly 5000 ms; 100 frames at 20 fps in the camera asset.
- Small transparent overlay, designed against the 720×480 native UI; no text or graphics burned into JPEG/DNG.
- No blocking sleeps, no allocations in a tick, no queued animations after burst capture, immediate cancellation for new shutter/menu/playback/power events.
- Sound defaults off; camera mute must be respected; no invented firmware sound address.
- A slow UI tick skips stale frames rather than extending the five-second deadline.
- Validate all header, frame and run bounds before playback, including truncated streams and corrupt payloads.
- Browser preview, native core verification and physical camera verification are separate claims.

## Tasks

- [x] Read current skill instructions and record upstream revisions and popularity evidence.
- [x] Build all three sequences with deterministic seeking, comparison and optional sound.
- [x] Render at actual size, compare keyframes and motion, choose the winner.
- [x] Test asset corruption/roundtrip and native interruption/deadline behavior, export the winner.
- [x] Research the native hook and sound path; connect only verified services. Research identified candidates, but no adapter is verified; no firmware was patched or delivered.
- [x] Run the repository suite and lab build; obtain an independent code review. Both lifecycle findings were fixed with regression coverage.

## Accepted steering

The user selected Pocket Lab's sound, rejected the original geometric illustrations, and requested all three new art directions. A generated atlas provided scientist, CRT and tactile 3D alternatives. The user selected the second (CRT/Diskette), then asked for cheaper frame rendering and more closely related alternatives.

The user subsequently asked for a little more animation. The active result is three CRT variants (Mint, Amber, Terminal), 128×128, six acting frames, 16 colours, 5000 ms and 98,424 bytes each. Shared timings in `timing.mjs` are 0, 450, 600, 1450, 2950 and 3500 ms, with clearing at 5000 ms. GSP1 uses a shared RGB565/alpha palette and indices; its validated explicit timings support 1–12 frames and retain compatibility with three-pose assets. The native player renders six times; sound ticks are independent of redraws. Earlier studies remain for provenance. New files include `timing.mjs`, `test/six-poses.test.mjs`, `art-prompt-v4.txt`, the v4 atlas and strips, alongside the prior compact player and verification tools.

The remaining real-camera task is a verified adapter for successful-shot, owned overlay, UI clock/cancel and sound/mute services. This remains outstanding and is explicitly documented as unverified.

Latest steering: the user chose Terminal (third character), requested maximum Pocket Lab effect volume, entry/exit on top of the five seconds, and three suggestions. The active page compares Soft Dock, Tiny Hop and CRT Boot using that same Terminal asset. The timeline is 350 ms in + 5000 ms act + 350 ms out. Browser audio peak gain is 1 and defaults enabled; playback still needs a gesture. Native `place` callbacks implement Q8 position/scale/opacity with no extra sprite planes. A 684-point native/browser parity check covers all three transitions. The sprite payload remains 98,424 bytes.

## Revision: authored character actions

The user rejected the 350 ms widget transitions as insufficiently animated and asked for proper character animation and SFX. Rebuild three complete entrance/exit sequences around Terminal: Disk Dash (run, skid, dash away), Pixel Portal (emerge, tumble, land, dive back), Rocket Delivery (fly in, brake, charge, blast off). My timing choice is 1400 ms entrance + the unchanged 5000 ms performance + 1200 ms exit. Use six additional illustrated action poses, 30 fps transform choreography, anticipation, squash, follow-through and small bounded geometry effects. Pocket Lab's core melody remains; each sequence gains synchronized entrance/exit sound effects, with application volume at 100% and mixed levels limited against clipping.

File manifest: add `sequence.mjs` (seekable GSAP choreography), `src/sequences.tsx` (sprites/effects), `prepare-actions.mjs` and action art (cached 128px sprite assets), `sfx.mjs` (sound score), `test/sequence.test.mjs` and SFX regressions. Update `src/main.tsx`, `src/sound.ts`, `src/styles.css`, browser verification, package scripts and README. Preserve the earlier `timing.mjs`/native prototype as explicitly documented earlier research: its checks do not validate the new choreography. Verify the visual motion with rendered entrance/exit filmstrips, audio with OfflineAudioContext, lifecycle controls with Playwright, and the normal build/tests. No firmware integration claim until a real adapter is verified.

Latest accepted steering: retain all Dash/Portal/Rocket sequences and pick randomly after each shot. Correct two stray shoe-edge fragments above the blink pose and make the mascot face its destination during travel. The source blink cell includes those fragments in the first two native rows; isolate core frames and omit its first three padding rows without touching the antenna. Add facing to the timeline/export, per-pose mirroring with shared flame sockets and short turn anticipation. Portal dives face right; running and rocket travel face left. Random triggers draw shuffled sets of three, with no immediate repeats across refills; manual audition stays deterministic. The active preview animates only the chosen sequence. No firmware adapter or flash operation is part of this correction.
