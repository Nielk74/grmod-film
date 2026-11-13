# Tier 2 (a 720x480 view): what the firmware allows, and which design to prove first

Sources: the colour engine / film pack RTOS image (read only, the stage 4a build's `pack-rtos.bin`), the stage 1 to 4a notes, `out/native/cost.json` (the renderer's cost
in the ARM emulator). Nothing here was run on a camera except where it says "ran on the camera". "Evidence" = read in the image or measured in the emulator; "inference" is mine.

## 1. The heap we use

- `0x536af2a8` (alloc) and `0x536af2e4` (free) are `operator new` / `delete`: they fetch heap object number 2 from the table at `0x5536c7b8` and call its vtable slot 2 (alloc, `0x536ac840`)
  or slot 3 (free, `0x536acb9c`). Evidence.
- Object 2 is the pool named `NEWOPERATOR`: 16 MiB at `0x59600000..0x5a600000`, created at start-up (`0x536b2288`, `0x536ad1b8(object, 2, name, 0x1000000, 0x59600000, 8)`). The start-up code creates 15 named pools
  (index: name, size): 1 SYSTEM 5 MiB, 2 NEWOPERATOR 16 MiB, 3 AUDIO 0.5 MiB, 4 FILE 15 MiB, 5 USB 0.5 MiB, 6 HOST 10 MiB, 7 CAPTURERECIPE 8 MiB, FACEDETECT 4 MiB, 9 IQ 1 MiB, 10 PPU 128 KiB, 11 AF 8 MiB,
  12 APP 2.5 MiB, 13 INFO 1 MiB, 14 IMAGE1 about 578 MiB, 15 IMAGE2 1 GiB. Evidence.
- **There is no allocator limit of about 176 KB.** The figure I quoted (176,128 = 172 x 1024) is the size of the single block of the Terminal build that ran on the camera (172 KB), and the 1g block (173,436 bytes) stayed under it
  on purpose. It is the largest single block that has run on the camera, not a limit of the allocator. Blocks that ran on the camera: 173,436 (1g), 126,720 twice and 28,672 / 20,736 (stage 1 to 4a, 303 KB per power-on).
- The allocator wrapper (`0x536ac840`): rounds the size up to the alignment, adds a 0x20-byte header, and calls the RTOS byte-pool allocate (`0x53050b58`) with wait option 0 (no wait). If that returns non-zero the wrapper
  returns 0 (null): no assertion, no wait, no log on that path. Evidence (disassembly), not tried on a camera. So a request that does not fit returns null. What I cannot show: the pool's free space and fragmentation at the moment
  (the UI and other tasks share it), so whether 1,382,400 contiguous bytes exist is unknown until probed. A probe that succeeds is freed at once; while it is held (microseconds) another task asking the pool for memory could get null:
  unlikely, not proven harmless.
- Conclusion for design A: a 1,382,400-byte RGBA buffer is not excluded by any limit; it is excluded by nothing but free contiguous space. Unproven.

## 2. Other memory for UI bitmaps

- The UI canvas surface (`root + 0xec`) is the frame buffer our copier draws into: 736 x 480 pixels stride, format byte 5 (32-bit RGBA), observed on the camera (1e panel: `W 720 H 480 STR 736 FMT 5`). The camera clears and repaints it
  in its paint pass; we only copy into it.
- The native RGBA copier `0x5320a020(context, surface, x, y, sx, sy, w, h, bitmap, source)`: alpha-key copy (a source pixel with non-zero alpha is copied as is, no blending), source in any readable memory (our heap blocks), the bitmap
  descriptor is `{width, height, word offset}`. It takes a source sub-rectangle `(sx, sy, w, h)` of the bitmap and a destination origin `(x, y)`: so one call can copy any sub-rectangle of a source bitmap anywhere on the surface. Evidence (the
  call we make in every stage, ran on the camera).
- Other pools (APP, INFO, IQ, ...) belong to other subsystems; IMAGE1/IMAGE2 are the image pipeline's. The same wrapper class serves them, but taking memory from the image pools could starve the picture pipeline. I found no
  pool that is ours to use: no alternative memory is probed in the diagnostic (step S2 is reported as skipped, with this reason).

## 3. Is a full-screen bitmap really needed? (design B)

- The draw path (evidence): the paint method (`0x5316d0f0`) paints a canvas when its root has the dirty flag (`+0xa0`, whole tree: `0x53391b14` then the base draw `0x533ab9bc`, which calls every child's draw slot `+0x4c` once,
  `draw(view, surface)`, no rectangle argument) or the child-dirty flag (`+0xa2`: only children that are themselves dirty are redrawn). A view's absolute rectangle (`+0x30`) and clip (`+0x64`) are set by the layout pass. There is no
  per-rectangle invalidation: a view is drawn whole each time it is invalidated, and the draw callback is called once per paint pass.
- So a full-screen view's draw callback may render and copy in pieces: for each band it renders rows into a small scratch buffer and calls the copier once with the band's destination origin; no big buffer exists. The callback
  decides what it touches; the dirty rectangle is not honoured because there is none.
- Cost (emulator, `out/native/cost.json`): the integer renderer's tier 1 frames cost 0.5 to 1.2 million instructions, tier 2 frames 2.4 to 5.3 million (roll, tier 2, worst 5,254,791). If the renderer can be made to clip to a band, a band of
  48 rows (10 bands) costs about a tenth of a frame (0.25 to 0.5 million) plus a copier call; if it cannot clip early, each band repeats the whole frame (up to ten times 5 million). At roughly 1 instruction per ns (unmeasured on this CPU) that is
  2.5 to 5 ms per frame at best and up to 50 ms at worst, plus the copier's time for 1.38 MB per frame, which nobody has measured. The diagnostic's step S4 measures the whole thing on the camera.

## 4. What a full-screen child of the shooting live view's root costs

- Layout: a new child needs the root's layout request (the finding of stages 1f/1g); done the same way. The layout pass visits the child once per request.
- Compositing: the paint method ends each layer with a commit to the display manager (`0x5323369c`, `0x536c6290`): the UI canvas is a layer of its own that the display controller combines with the live view layer
  (inference from the begin/commit structure; not traced into the hardware). The live view image is not part of our canvas, so a full-screen child whose pixels are transparent (alpha 0) leaves the live view visible, and the camera's own
  readouts (children of the same root, drawn before ours) stay visible where we draw nothing. Opaque pixels cover them. Whether the camera repaints the whole canvas for every live view frame or only when something is invalidated is not
  known: in the stages so far we repaint only when we invalidate.

## 5. Recommendation

| Design | Memory | New mechanism | Verdict |
|---|---|---|---|
| A: one 1,382,400-byte buffer, one 720x480 view | one 1.38 MB block (never allocated before) | a larger single view | unproven, only worth it if the probes show the block exists |
| B: banded draw in the callback | a 46 KB scratch | the copier called per band from the draw callback; the renderer must clip to a band | zero big memory; needs a renderer change and a measured frame time |
| C: several medium views, e.g. eight views of 720 x 60 (172,800 bytes each, the size that has run on the camera) | 1.38 MB in eight proven-size blocks | none: more of the tier 1 mechanism (small fixed views, the layout request) | **the safest extension, honestly** |

**Recommend C** (the contact sheet as a stack of row views at proven block sizes), with B as the fallback if the pool cannot supply eight more blocks. A is not needed unless one view must be one object. The diagnostic proves the two
unproven mechanisms A and B need (a 720 x 480 view with a layout and draw; the banded copier path with its frame time); C needs neither beyond what tier 1 already did, and can be added to the diagnostic cheaply if the owner wants it
measured as well.
