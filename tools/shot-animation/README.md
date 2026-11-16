# Shutter studies

The approved **Diskette Terminal** post-shot experience for the Ricoh GR III, with a browser review lab and an experimental native firmware build. The user selected the third CRT and requested full-volume Pocket Lab sound and fully animated entrances/exits around its five-second performance. The active page compares three complete character sequences, with six additional illustrated action poses and synchronized sound effects. Sound is enabled at 100% in the browser and starts after a playback gesture.

**Character selected: Diskette Terminal. All three sequences retained, random on each shot.** This is a browser animation study, not a physical-camera performance claim.

| Suggestion | Entrance | Exit | Sprite data |
|---|---|---|---|
| A: Disk Dash | Running strides, skid, squash and rebound | Crouch, heel kick, sprint and dust | Shared 12-pose bank |
| B: Pixel Portal | Portal opens, surprised tumble, landing and balance | Wind-up, leap, shrinking dive and pixel snap | Shared 12-pose bank |
| C: Rocket Delivery | Flight, braking, squash and bounce | Charging, ignition, acceleration and spark trail | Shared 12-pose bank |

All three use a **1400 ms entrance + 5000 ms performance + 1200 ms exit = 7600 ms total**. The middle retains six acting poses: inspect (0 ms into the performance), blink (450), double take (600), delight (1450), thumbs-up (2950), smug approval (3500), with a gentle common body motion. Pocket Lab's existing notes move with the performance's 1400 ms start. Entrance and exit have separate footsteps, sweeps, impacts, portal and jet effects. Playback clears at 7600 ms.

The active sequences use **12 cached 128×128 images**, sampled at 30 fps through seekable paused GSAP timelines. No rendered video frames are stored for playback. Small geometric dust, speed lines, portal segments and flames supply follow-through. `sequence.mjs` owns the timeline, per-action facing and random picker; `src/sequences.tsx` mirrors each pose according to its authored direction. Flame sockets share the mirrored character transform. Turning briefly narrows the character before it changes facing. Core acting stays identical across all three.

Each **Take a picture** click or Enter key draws from a shuffled set of all three sequences. Refills avoid an immediate repeat at the set boundary. Only the chosen sequence animates and plays its SFX; the other comparison panels hold an idle pose. Per-sequence Play and entrance/exit replay controls remain deterministic for inspection, and do not consume random choices. The selected panel and LCD overlay clear on completion.

The shared twelve-pose bank is **196,672 bytes as one-byte indices plus its RGBA palette**, or **25,987 bytes as PNG** with the neon palette. Those measurements are written by `export-sequences.mjs` to `out/sequence-export.json`. The older six-pose GSP asset remains 98,424 bytes. More expressive animation doubles the cached pose pixels, while avoiding the earlier 6.68 MiB dense export. These are storage measurements; real camera frame rate and power consumption remain unmeasured.

The large panels show registered high-resolution artwork; the simulated LCD uses 128×128 indexed PNG sprites. The earlier Q8 exports remain available for study. The current firmware exporter produces a checked TRM2 asset containing the shared indices/palette, Q16 inverse transforms, and ordered filled vector commands. `native/terminal.c` implements the current choreography and effects; `native/camera_gr3.c` integrates it with the exact GR III 2.10 native services.

The source blink cell contained two thin fragments of the preceding frame's shoes in its top padding. `export-compact.mjs` now excludes that three-native-pixel padding band while preserving the antenna and registration. It also writes six standalone core images at 128px and 512px under `src/assets/terminal-core-v5/`. `src/core-art.ts` supplies those bounded images to the active renderer, preventing neighboring-frame filtering. The source atlas remains preserved. Regression coverage checks the clean native/high-resolution padding and travel facing.

## Neon palette and design review

`palette.mjs` supplies the acid-lime phosphor, dark emerald glass, fluorescent orange, hot-magenta accents and ivory effect colors. The export scripts bake a repeatable color grade from the preserved original atlases into every Terminal pose. Geometry and alpha are unchanged by the grade. `src/sequences.tsx` uses the same color roles for portals, exhaust, sparks and speed lines, without a runtime filter, glow pass or additional cached poses. The bank still uses 16 palette entries. Mint and Amber studies keep their original palettes.

The user requested Impeccable agents for the whole design experience. Global `pbakaus/impeccable` 4.8.0 supplies the Asset Producer, Finish Reviewer and Documenter profiles used for the full pass. `AGENTS.md` preserves that workflow, `PRODUCT.md` records confirmed user choices, and `DESIGN.md` plus its sidecar record the implemented system. The review also replaces glyph arrow adornments with authored SVG icons and improves small inspection labels and control targets. The Finish Reviewer found a sound-control defect: re-enabling sound during active playback changed the label without restarting the score. It now resumes from the current playhead, remains silent when paused, and is covered by a browser regression observing real audio-source starts. The final reviewer disposition is `ship` after scoring that fix.

The generated neon study is `src/assets/terminal-neon-study-v6.png`; its exact imagegen prompt is saved in `art-prompt-v6.txt`. The Asset Producer's additional transparent reference and embedded prompt are in `out/terminal-neon-agent-reference.png`, with an exact text sidecar beside it. These are palette references, not replacement drawings. `out/neon-before-after.png` compares the original and graded native-size sprite. Generated GIF, WebM and WAV previews include all three current neon sequences.

## Film pack build: use this one on a camera that has run the film pack

A camera keeps its saved settings across a flash, and official-based code crashes on film looks and added ratios saved under the film pack. The official-based build described in the next section left a camera stuck on 2026-11-05 with no settings reset beforehand, so do not flash it on such a camera.

The film pack build keeps the film pack whole and adds the animation after it: five hook words change, nothing else in the film pack does. Its first hardware test is silent. `camera_gr3.c` is unchanged: the audio latch symbol is linked to a read-only word holding 1, so no audio service or mutex is reached. The state pointer sits in the film pack's zero-filled spare RAM at `0x558043b8`.

```powershell
python tools/shot-animation/native/link_firmware_filmpack.py --pack PATH-TO-FILM-PACK-fwdc239b.bin
npx --no-install vite-node tools/shot-animation/build-firmware-filmpack.ts PATH-TO-FILM-PACK-fwdc239b.bin
python tools/shot-animation/native/check_hooks_filmpack.py
python tools/shot-animation/native/check_adapter_filmpack.py
```

Output goes to `out/firmware-filmpack/`, including flashing and rollback notes. The linker refuses official and first-Terminal images as a base. The silent build boots and animates on the owner's camera (2026-11-05).

With sound: pass `--sound` to all four commands. It embeds the approved soundtracks, patches the audio shutdown hook too, keeps the latch in zero-filled RAM at `0x558043bc`, and writes to `out/firmware-filmpack-sound/`. Its adapter check runs the official build's full 24 sound scenarios inside the final image. Hardware behavior is untested.

## Experimental GR III 2.10 firmware

The build writes `out/firmware/fwdc239b.bin`, `build-report.json`, `payload-manifest.json` and `SHA256SUMS.txt`. It accepts only the exact official GR III 2.10 file, SHA-256 `d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4`. An already modified firmware or a GR IIIx file is rejected. This is an animation build based on that official image; it does not merge another build's film slots or settings changes.

The native implementation uses twelve cached indexed poses and filled geometric effects, with a 240×176 transparent RGBA overlay at `(464,259)` on the 720×480 UI. It samples the approved three timelines at 30 fps, skips stale frames, and clears at 7600 ms. Its state/frame buffer and owned native IconView live in the camera's heap; drawing never allocates or touches captured-image buffers. A private copy of the IconView callback table replaces only Draw and preserves native bookkeeping and destruction. Normal LiveView/QuickView transitions detach and reattach the same owned view without restarting the animation.

The completion hook observes the native still-image backend recipe's terminal `Goodjob` notification, preserving its original application-event enqueue. Original ARM execution verifies thirteen native plans, each with one terminal notification; nine plans omit the preview operation. This establishes a backend-completion trigger independent of that operation. It does **not** establish one notification per physical shutter press or saved file for every RAW+JPEG, burst, multi-exposure, failure or review-disabled setting. Those physical event traces remain to be checked.

Pocket Lab and the transition SFX are embedded as the three approved 7.6-second, 48 kHz stereo PCM16 WAVs. Owned playback uses native volume enum 20, honors camera mute, and restores the saved volume after owned completion/cancellation when the service remains ours or idle. A busy or unavailable device suppresses that shot's new sound immediately; owned cancellation retries without blocking the UI. Foreign playback is never stopped or adjusted by the adapter.

A permanent native mutex serializes the adapter's audio access against native service destruction. UI audio work uses a nonblocking acquire and rechecks the shutdown latch after acquisition; shutdown drains an operation already in flight before native deletion. The native shutdown task's identity is unknown, so the adapter deliberately does not depend on UI-task quiescence. Actual compiled ARM tests cover three preemption windows with separate CPU contexts, including shutdown during state construction, and suppress audio safely if mutex initialization fails. The current persistent state/frame allocation is 171,756 bytes plus the 248-byte native IconView.

The build reserves only eight bytes of startup-zeroed alignment space at `0x55804374`: a state pointer and an audio shutdown latch. It extends the original zero-fill end to `0x55804380`, preserving the heap boundary. All appended RTOS code/assets are immutable, with no writable `.data` or `.bss`. This reservation is exclusive to the exact-official-input build. Seven guarded stock words implement six native-preserving detours and the zero-fill literal; all other original RTOS bytes remain intact, and every other container section is byte-identical. The original model, project, firmware version and photo-processing code are preserved.

These are offline and emulated results. The physical display, real scheduling/frame rate, speaker output and DMA/cache behavior have not been tested on a camera. The output is an **experimental hardware-test candidate**, with no version increase, flash operation or published release.

From the repository root, after installing the lab dependencies and starting its Vite server:

```powershell
node tools/shot-animation/export-firmware.mjs
python tools/shot-animation/native/check_terminal.py
python tools/shot-animation/native/check_clock.py
python tools/shot-animation/native/check_adapter.py
python tools/shot-animation/native/link_firmware.py
npx --no-install vite-node tools/shot-animation/build-firmware.ts PATH-TO-OFFICIAL-fwdc239b.bin
python tools/shot-animation/native/check_hooks.py
python tools/shot-animation/native/check_adapter.py --payload-elf tools/shot-animation/out/firmware/terminal-payload.elf --out tools/shot-animation/out/firmware/adapter-linked
```

The native exporter reuses the indexed pose bank and WAVs produced by `npm run export` and `npm run render:previews`. Its browser captures are also the references for eighteen actual-ARM visual comparisons. The checks use original firmware bodies with explicit OS/driver/heap substitutions, not a whole-camera emulator. Reports hash their tested source, assets and final linked ELF. The packager checks every stock signature, append/branch/RAM bound, full-container checksum, changed range, unchanged section and decoded round-trip before writing output. It refuses to replace a different existing firmware file. The full repository suite must pass before preparing a delivery package.

## Run

From the repository root, using Node 24 or later (the sound regression uses Node's built-in TypeScript stripping):

```powershell
npm ci --prefix tools/shot-animation
npm run dev --prefix tools/shot-animation
```

Open the exact loopback URL printed by Vite, normally `http://127.0.0.1:5186/`. Use **Take a picture**, or Enter while focus is outside an interactive control. Each sequence has a Play button that selects its SFX and starts playback. The shared controls pause, scrub, mute and replay either the entrance or exit. The master sound gain is unity (100%); layered voices are staged and compressed against clipping. This sets application effect volume, not operating-system speaker volume. Pending audio resumes and noise/oscillator sources cancel on stop, repeated shots and hidden pages. Reduced motion shows the finished pose during playback and still clears at the deadline.

## Verify and export

Keep the dev server running:

```powershell
npm test --prefix tools/shot-animation
npm run build --prefix tools/shot-animation
npm run export --prefix tools/shot-animation
npm run verify:browser --prefix tools/shot-animation
npm run render:previews --prefix tools/shot-animation
python tools/shot-animation/native/check.py
npm test
npm run build
```

Playwright requires its Chromium browser (`npx playwright install chromium` from this directory if it is not already present). The native check requires Python packages `unicorn` and `pyelftools`, plus Clang and LLD with ARM support; pass `--clang` and `--lld` for their paths. It compiles the actual freestanding A32 code and executes its tests and the exported assets in Unicorn. No WSL, Unix shell, camera or flash operation is involved. The read-only firmware probe additionally uses `capstone`.

The exporter retains the older `out/diskette-{mint,amber,terminal}.gsp` assets, registers the new action art, and creates `out/terminal-pose-bank.png`, indices, palette, sampled motion tracks and reports. Browser checks exercise `?export=dash`, `?export=portal`, `?export=rocket` and high-resolution `&large=1` views, verify identical five-second acting windows, distinct entrances/exits, clearing, responsive controls and audible offline SFX. `out/entrance-exit-filmstrip.png` captures the choreography. Earlier transitions remain accessible as dock/hop/boot, character options as mint/amber/terminal, and dense experiments as film/robot/focus.

`npm run render:previews` saves an animated GIF, a WebM clip with synchronized stereo SFX, and a WAV for each current sequence in `out/terminal-{dash,portal,rocket}.*`. `render-previews.mjs rocket` can refresh one clip. GIFs are preview exports only; camera playback uses cached sprites. `art-prompt-v5.txt` records the exact built-in imagegen prompt for the six action poses.

The earlier compact **GSP1** format has a 32-byte versioned header, a shared palette of `{rgb565:u16, alpha:u8, reserved:u8}`, explicit u32 frame times, and one plane of u8 palette indices per frame. It supports 1–12 frames with strictly increasing times starting at zero and below 5000 ms, preserving compatibility with earlier three-pose assets. The strict native loader validates size, dimensions, palette, indices, times and CRC. The earlier assets use six sprite uploads; this count does not describe the new action sequences.

The earlier **GSA1** format is still readable by the native player for comparison. It stores 100 RGB565/alpha RLE frames and costs several MiB for detailed illustrations; the user explicitly rejected that rendering/storage cost. It is no longer the default export.

## Native status: earlier prototype

`native/player.c` preserves the **earlier 350 ms Dock/Hop/Boot prototype**. Its compiled ARM tests and 684-point transform parity check cover that earlier prototype only. They do **not** validate or implement the current Dash/Portal/Rocket choreography, rotation, new effects or SFX synthesis. Its required `place` callback applies bottom-centred Q8 widget scale, pixel displacement and opacity. It skips stale poses, clears at 5700 ms, cancels immediately, replaces older shots, handles wrapping and respects the adapter's sound permission. No firmware integration claim follows from those emulator tests.

This historical prototype is retained for comparison. The current firmware implementation uses `native/terminal.c` and `native/camera_gr3.c`, with separate current-asset, clock, adapter, and hook checks. The older prototype's results do not validate the current firmware.

Read-only research identified `Controller/QuickViewController.cpp`, `Model/SoundModel.cpp`, the `PlaySound` diagnostic and AF beep resources in the exact GR III 2.10 RTOS. Those are research candidates, not verified APIs. REA admitted the raw image but its available Windows analysis providers could not analyze this raw ARM target, so the follow-up used the repository's Capstone helper. To reproduce:

```powershell
python tools/shot-animation/probe_firmware.py PATH-TO-OFFICIAL-RTOS --out tools/shot-animation/out/firmware-research.json
```

The probe accepts only the known GR III 2.10 / IIIx 1.60 RTOS hashes. Official firmware inputs and generated builds stay in local ignored directories. The current integration's exact-byte evidence, emulator reports, patch manifest and physical-test limits accompany the generated candidate.

## Skills and art provenance

Research was performed on **2026-11-04**. `research.json` records source URLs and revisions. Initial motion experiments used the current online versions of [Remotion best practices](https://skills.sh/remotion-dev/skills/remotion-best-practices), [official GSAP core](https://skills.sh/greensock/gsap-skills/gsap-core), and [Impeccable animate](https://skills.sh/pbakaus/impeccable/animate). At lookup, skills.sh showed approximately 749K / 82K / 82K installs respectively. These are observed directory counts, not proof of worldwide popularity or superiority.

For the revised art, [Meng To's illustration collection](https://skills.sh/mengto/skills) supplied modern character/style research, particularly Ink Sketch and Bold Pop. The narrower illustration skills are newer and have hundreds of installs, substantially less than the general motion skills. [Rive's community](https://rive.app/community/) and [DiceBear Notionists](https://www.dicebear.com/styles/notionists/) were evaluated as references; neither runtime nor stock artwork was incorporated.

The illustration atlases were created with Codex's built-in **imagegen** tool. `nerd-atlas-v2.png` contains the scientist, CRT and 3D gremlin comparison; the selected CRT supplied the reference for `diskette-atlas-v3.png`. `diskette-atlas-v4.png` extends those characters to six acting poses. `terminal-actions-v5-master.png` adds Terminal's two running strides, airborne surprise, landing, wind-up and flight. `prepare-actions.mjs` registers their centre/baseline and creates the normalized master and 128px strip without repainting the art. Generation prompts are saved in `art-prompt.txt`, `art-prompt-v4.txt` and **`art-prompt-v5.txt`**. These are original generated assets. The active sequences are in `src/sequences.tsx`; the previous compact studies remain in `src/compact.tsx`.

The sample photograph is imported from the repository's existing GR III samples. See `ui/src/assets/samples/CREDITS.md` for its CC BY-SA attribution. The self-hosted Barlow Condensed font is under the SIL Open Font License, copied in `public/FONT-LICENSE.txt`. No Ricoh, Rive, DiceBear or illustration-library assets are redistributed.
