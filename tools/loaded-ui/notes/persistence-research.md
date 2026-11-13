# Power-off persistence for the per-film frame counters (research only, nothing built)

Question: where could 20 small counters (about 20 bytes, one frame number and one roll number per film slot, so 40 bytes with rolls) live so they survive a
power-off? Sources: the colour engine / film pack RTOS image (read only, `pack-rtos.bin` of the stage 3a build), the repo's GR Mod notes
(`core/src/fw/gr3x/guard.ts`, `endscreen.ts`, `shutdown.ts`, `datestamp.ts`) and its native modules (`tools/gr3x/native/films.c`, `endscreen.c`).
Nothing was run on a camera. "Evidence" below means read in the image or the repo; "inference" is mine.

## Option 1: the camera's own settings store

Two mechanisms exist, both already used by GR Mod.

**1a. Padding bytes of the settings record.** The settings object (UserDataModel, `0x55063f30`) holds the record in use at +4 and seven stored records
(modes, U1..U3) after it, each 0xb28 bytes, "all saved and loaded whole" (guard.ts). GR Mod keeps its soft focus (0x9a1), date imprint (0x9a2) and End Screen
picture (0x9a3) in padding bytes between 0x9a0 and 0x9a4, noted there as camera-tested: saved, loaded and copied to U1..U3 with the record, cleared by the defaults.
The older End Screen rounds also used 0x9a9..0x9ab. Evidence that a free padding range of 20 to 40 bytes exists: none found; the three bytes next to 0x9a4 are used,
the field map of the record is not complete (only offsets some module reads), so a free range would need a full field audit. Per-film data would also be copied into the
U1..U3 records and reset by a "restore defaults": both wrong for a roll counter. Not recommended.

**1b. A record of the HTData store (a file of the camera's internal flash file system).** Evidence:
- The store API GR Mod already calls: `STORAGE()` `0x53828014`, the HTData object at `*(storage+0x14)`, `STORE_SIZE` `0x53829e50`, `STORE_READ` `0x53829fcc`,
  `STORE_WRITE` `0x53829a08` (endscreen.c, films.c). The firmware's own callers use record indices 0, 1, 7 and 8 and some variable ones (loops); GR Mod uses 12 (the films' own
  parameter table, written after every settings save, with a magic, a version and a fingerprint) and 13 (the End Screen choice).
- The index check: the record number goes through `0x53829990`, which accepts 0..15 only (`cmp r1,#0xf`, else an assertion). So there are 16 record slots; 14 and 15 are the
  candidates (I did not find a write or read of them in the firmware, but the variable-index loops at `0x533b9230` / `0x533b9340` were not decoded, so "free" is an inference).
- The record is a file: the name is built with the format `%s%02d.%s` and the prefix `HTData` (so `HTData14.bin`), under a mutex (`0x536ae71c`).
  The write routine `0x53825fa8` writes an 8-byte header with the magic `0xa55a5aa5` and a length/checksum word, and has a two-phase structure (a second name is built
  and written after the first: `cmp r6,#1 / #2`), which looks like a primary plus a backup copy; I did not decode the second name or the recovery on read. Inference: a power loss during a
  write leaves either the old or the new record, with the usual unknown about a half-written file system block.
- Failure modes in the API: `STORE_SIZE` returns something else than the record size when the record does not exist (endscreen.c treats that as "first start"), `STORE_WRITE` returns
  0 on failure. films.c writes its record twice after each settings save ("once more: until it is written, the next start takes the old table over again"), so GR Mod already lives with a write
  that may not have completed.
- Where to hook: reading is easy (on the UI task, when our block is allocated, after the camera has been up 20 s: one `STORE_SIZE` and one `STORE_READ`). Writing: the camera saves its settings at power off
  through the tail call at `0x5322b0a8`, which GR Mod's film pack already patches (the film table and End Screen chain their writes after that save with a stored "prior_save" pointer): we would have to chain behind
  those, or write earlier (see below). Writing a 40-byte file on every photo is the simplest but writes flash each time (inference: wear is probably fine at a few hundred photos a day, latency
  unknown, it is on the UI task and the file system takes a mutex that other tasks also take).
- Risk: write path exercised daily by the film pack on the owner's camera (records 12 and 13), so a new record adds data, not a new mechanism. Remaining risks: an index the camera itself uses (read the record's size first and use it
  only if it does not exist, or if it carries our magic), flash wear, a stall of the UI task while the store is busy, and the generic risk of any write during power loss (corrupting the settings store would reset the
  camera's settings or fail to boot cleanly: not a hardware brick, but a bad day). Confidence that 14 or 15 works: medium (about 70 percent), the layout facts are read, the index use is inferred.
- Effort: medium. A record format `{magic, version, 22 x frame, 22 x roll, checksum}` (about 100 bytes), a read at block allocation, a write at a quiet moment (a transition away from the live view,
  at most once per few seconds), the same recovery rule as films.c (missing or bad magic gives the defaults). A chained write at the power-off save needs a seventh hook or sharing the pack's chain: more work and
  more risk than a write on a transition.

## Option 2: a file on the SD card through the camera's file layer

Evidence: the firmware has a file system service with drive letters (A:, B:, C: seen in resource paths, `C:\REC1.dat` in a debug audio writer, `:\MISC`), a debug shell with `shell_med_fopen`, `fputs`,
`fclose`, `mkdir` (names only), and an image-writing path (`SWriteImageNonSplit`, `DCIM` handlers). I found no open/write/close entry point that UI code uses and I did not trace one from a task context we would be in.
Unknowns: which task may call it, the cost on a card, behaviour with no card, a full card or write protection, and the interaction with the camera's own card writes (a second writer during a JPEG write). The risk is on the user's
card (a corrupted FAT or DCIM) and it needs the card present at the moment of writing; nothing here is evidence for a safe API. Confidence: low (about 25 percent); effort: high; not recommended.

## Option 3: derive the counter from what the camera already persists

Evidence: the firmware has a file numbering setting (`SetupFileNumbering`, continuous or reset), a `GetFileNumber` function and a `FileNo` field. Inference: the last file number survives power-off (or is re-derived from the card)
and a "frame number" could be `file number mod 36 + 1`. What it cannot do: it is global, not per film; it counts RAW+JPEG as one or two depending on the camera, movies and deleted pictures also move it, a card change or format resets it
or jumps it; a new roll on a film change cannot be expressed without storing an offset (which needs option 1 again). Confidence in the reading of the number: low to medium (I did not locate the getter's
storage or its timing). Brick risk: none (read only). Effort: low to medium. Useful only as a fallback "frame = file number" mode, not as a per-film counter.

## Recommendation

Option 1b: one new HTData record (index 14, then 15 if 14 turns out to be used), read once when our block is allocated, written on a transition away from the shooting live view and only when a counter changed, with the films.c rule for a
missing or invalid record (use the defaults) and a runtime check that the record either does not exist or carries our magic before we ever write it. It reuses a write path the film pack runs every day. Before building it, a
diagnostic image should (1) read `STORE_SIZE` of records 9..15 and report which exist (the owner can photograph it), and (2) do one test write of a 16-byte record 14 and read it back after a power cycle, so that "free" and "survives a
power-off" are measured on the real camera instead of inferred. If the owner prefers zero risk, keep the counters volatile (as now); option 3 can show a file number beside the counter later.
