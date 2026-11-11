"""Assemble the stage 1 delivery folder after link_loaded.py, build-loaded-stage1.ts, check_hooks_loaded.py and
check_adapter_loaded.py have run: rollback copy of the exact base, SHA256SUMS.txt, a verification summary and README.md.

  python native/package_loaded_stage1.py --pack PATH-TO-FILM-PACK --counts "js=36 parity=... "

Never writes anywhere but out/firmware-loaded-stage1/. No card or camera is accessed.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
OUT = LAB/'out'/'firmware-loaded-stage1'
BUILD = OUT/'build'
MAIN = LAB.parent.parent.parents[2]
TERMINAL_REPORT = MAIN/'tools'/'shot-animation'/'out'/'firmware-filmpack'/'build-report.json'
PACK_SHA = 'cf04126f5861c3a64123f0cdc95efa5b65443b44aa0ca975854423acf0131f55'


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pack', type=Path, required=True)
    ap.add_argument('--counts', default='', help='key=value pairs from the test runs, embedded in the README')
    args = ap.parse_args()
    counts = dict(kv.split('=', 1) for kv in args.counts.split() if '=' in kv)
    pack = args.pack.read_bytes()
    assert sha(pack) == PACK_SHA, 'base is not the expected film pack'
    (OUT/'rollback').mkdir(exist_ok=True)
    (OUT/'rollback'/'fwdc239b.bin').write_bytes(pack)
    image = (OUT/'fwdc239b.bin').read_bytes()
    report = json.loads((OUT/'build-report.json').read_text(encoding='utf-8'))
    manifest = json.loads((BUILD/'payload-manifest.json').read_text(encoding='utf-8'))
    adapter = json.loads((OUT/'adapter-verification.json').read_text(encoding='utf-8'))
    hooks = json.loads((OUT/'hooks-verification.json').read_text(encoding='utf-8'))
    assert sha(image) == report['outputSha256'] and len(image) == report['outputBytes']
    assert adapter['patched_rtos_sha256'] == hooks['patchedRtosSha256'], 'checks ran on different images'
    assert adapter['payload_elf_sha256'] == manifest['elfSha256'], 'adapter check ran on another payload'
    (OUT/'SHA256SUMS.txt').write_text(f"{sha(image)}  fwdc239b.bin\n{sha(pack)}  rollback/fwdc239b.bin\n", encoding='utf-8', newline='\n')
    terminal = json.loads(TERMINAL_REPORT.read_text(encoding='utf-8')) if TERMINAL_REPORT.exists() else None
    assert [x['film'] for x in manifest['slots']] and all(x['name'] == x['loadedName'] for x in manifest['slots'])
    summary = dict(image=dict(path=str(OUT/'fwdc239b.bin'), bytes=len(image), sha256=sha(image)),
                   base=dict(sha256=sha(pack), bytes=len(pack)), payloadBytes=manifest['payloadBytes'], rtosGrowth=report['rtosGrowth'],
                   rtosRuntimeEnd=hex(report['rtosRuntimeEnd']), counts=counts,
                   terminalBuild=(dict(sha256=terminal['outputSha256'], bytes=terminal['outputBytes'], rtosGrowth=terminal['rtosGrowth'],
                                       rtosRuntimeEnd=hex(terminal['rtosRuntimeEnd'])) if terminal else None))
    (OUT/'verification-summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8', newline='\n')
    d = (len(image)-terminal['outputBytes']) if terminal else None
    e = (report['rtosRuntimeEnd']-terminal['rtosRuntimeEnd']) if terminal else None
    slot_table = chr(10).join(f"  - slot {x['slot']:2d}, look {x['look']}: {x['name']!r} -> Loaded film {x['film']} ({x['loadedName']})" for x in manifest['slots'])
    readme = f"""# GR III 2.10: film pack + Loaded, stage 1 (hardware test)

Flash `fwdc239b.bin` from this folder. This is an experimental image: nobody has run it on a camera.

- Size: {len(image):,} bytes
- SHA-256: `{sha(image)}`
- Built on film pack: `{PACK_SHA}` ({len(pack):,} bytes), kept in `rollback/fwdc239b.bin`
- Replaces the silent Terminal build (`fe722fad61a8987ff332f15f1370fc6af1c33e7eaff31b9cf2e1ea3b623b1450`, 40,146,548 bytes, boots and animates on the owner's camera, 2026-11-05). Loaded and Terminal do not coexist.
- Compared with that build: {abs(d):,} bytes {'smaller' if d is not None and d < 0 else 'larger'}; the RTOS ends at {hex(report['rtosRuntimeEnd'])} instead of {hex(terminal['rtosRuntimeEnd']) if terminal else '?'} ({abs(e):,} bytes {'earlier' if e is not None and e < 0 else 'later'}). Payload {manifest['payloadBytes']:,} bytes (Terminal: 1,673,388), RTOS growth {report['rtosGrowth']:,} bytes.

## What it does

After each completed shot, for the film selected in the standard (or active custom) photo set, a "roll of film" moment plays and then clears:

- two opaque bands (top and bottom of the screen) in the film's own format: colour or black-and-white negative strip with edge print and
  perforations, cine strip with keycode, slide mount, instant print. They are on screen for 1.3 to 1.8 seconds depending on the format;
- a mechanical frame counter (right) and the film's box-flap tab (left), above the camera's bottom row. They slide in with the shot, stay
  after the strips have left (about half a second, showing the new frame number) and slide out again. The whole sequence is 2.0 seconds
  from the shot in every format;
- on the 36th frame of a roll, the end-of-roll moment follows the shot (film rewinding into a cassette, 3.4 s) with the counter and tab
  staying in place, then half a second of counter at 1 and the slide-out. Nothing pops between the two moments.

Nothing is shown in live view outside a moment. A shot while the furniture is still showing restarts the moment without a new slide-in;
MENU, playback or any other event removes everything at once. A look that is not one of the pack's films (Standard, Vivid ...) plays a
neutral grey strip printed "GR III". No sound, no menu, no settings written, no date stamp on the slide mount. There is no Load moment, no
permanent counter, no full-screen view and no contact sheet in stage 1.

Films: the 20 films of the base, in slot order, as the linker read their names out of the image (`slots` in `build-report.json`):
{slot_table}

The frame number is a counter the adapter keeps: it starts at 1 at the first completed shot after power-on and is lost at power off
(expected in stage 1: the counter going back to 1 after a power cycle is not a bug).
The roll number is derived from it (roll 1 for shots 1 to 36 ...). It is not the file number on the card; no readable source for that
was established (see below).

## Why it is built this way

A camera keeps its saved settings across a flash. The first Terminal build was based on official firmware, which crashes on film looks
and added ratios saved under the film pack. This build keeps every film pack byte except five hook words and the RTOS length,
exactly as the silent Terminal build that ran: same five hook sites, same trampolines, same state word in the film pack's spare RAM
(`0x558043b8`), same view lifetime. Coming from the film pack, no settings reset is needed. Before flashing official firmware or any
build with fewer films or ratios, follow section 5 of `docs/GR3_HDF_210_TEST.txt`.

## Flashing

1. Copy `fwdc239b.bin` to the card root and run the normal update (hold MENU while powering on). Fully charged battery; do not open the card door.
2. Start with the dial on P. Select a film (not Standard) for the first checks.

## How the film is read and how the slot table was made

From the UI task, with plain loads and no call: the settings object (the singleton that `0x5320b31c` returns, `0x55063f30`; the
function's body was disassembled in this image) holds a pointer to the record in use at +4; byte `0x44` is the movie flag, byte `0x1c0` the
active Image Control set (0 to 2) and byte `0x1c2 + 2 * set` that set's look. The camera's own Image Control line getter (`0x5326c1cc`,
original body, executed in the emulator for 138 cases) and the film pack's native modules (`tools/gr3x/native/films.c`, `slots3.c`) use the
same bytes. Looks 64 + k are the pack's films; looks 11 to 22 are the camera's own. The slot-to-film table is generated at link time from the base
image itself: the camera's name lookup (`0x532a985c`) is hooked by the pack's builder with one `cmp r1,#look; movweq r0,#text; bxeq lr` triple
per film, the text directory's address is in the two `movw`/`movt` pairs at `0x533966e8` and `0x533970fc`, row 1 is English, and a text
record is {{units + 1, 1, 0, 0, pointer to UTF-16}} (core/src/fw/gr3x/image-control-research.ts). The linker reads the 20 names that way, matches
them by name with the Loaded film table and refuses the base if any slot has no Loaded film. A null or misaligned record pointer, a movie flag or an active set above 2
gives no animation.

## Test card (note what you see after each step)

0. Expected in stage 1, not bugs: the counter starts at 1 again after every power cycle, and it is not the file number on the card.

1. Take a photo with Portra 400, then Gold 200, then CineStill 800T. Expected: black strips with yellow / amber / red edge print slide in at
   the top and bottom and the film advances by one frame; the counter and tab slide in, the counter rolls; the strips leave and the counter and tab stay half a second showing the
   new number and then slide out; all gone 2 seconds after the shot.
2. One slide film (Kodachrome 64 or Classic Chrome): a cream mount drops in at top and bottom and pushes out sideways.
3. Instant: a white print border covers the top and bottom bands and rises and leaves.
4. A Standard / Vivid look: a grey strip printed GR III.
5. Take a second photo while one is playing; then press MENU during one; then playback during one. The animation must restart, or vanish at
   once, and the camera must stay responsive in every case. Take the next shot a second after the previous one: it must not be delayed.
6. Power off and on again, and shoot: the counter restarts at 1.
7. Burst, RAW+JPEG, and review turned off: note what happens (unknown, see below). Movie mode: nothing should play.
8. If it is practical, shoot to frame 36 (a roll needs 36 shots since power-on): the 36th shot is followed by a rewinding film.
9. Tell me: does the picture stay visible and sharp under the bands, does the camera's own bottom row look wrong while a band covers it,
   and does a shot ever feel slower?

## If it gets stuck

Take the battery out for 10 seconds. Put `rollback/fwdc239b.bin` on the card root as `fwdc239b.bin`, then hold MENU while powering on.
That file is the unmodified film pack this build started from. Note whether it stopped before the first photo or after it: that
points to different causes (before the first photo: the payload or the film pack; after it: the adapter).

## What was and was not checked

Passed in emulation, on the delivered bytes (details in `build-report.json`, `hooks-verification.json`, `adapter-verification.json`):
- Film pack bytes kept, apart from the five hook words and the RTOS length; every other section byte identical; container checksums and decode round trip.
- Five hooks: {len(hooks['detourCases'])} register, flag and stack cases; three deliberate regressions rejected; the start-up zero fill clears the state word.
- {adapter['assertions']} assertions in {len(adapter['checks'])} adapter scenarios using the original native view tree, timer, clock and RGBA copier bodies: four views attached
  and detached together, transitions mid-moment, a second shot mid-moment, cancel, canvas deletion, an allocation failure at each of the
  five allocations, unknown film, frame 36 into the end of the roll, 32-bit clock wrap, 80 shots, draws rejected per view. The audio service
  page was unmapped for the whole run.
- The pixels the linked payload produces equal the JS reference for every sampled case.
- Counts: {', '.join(f'{k} {v}' for k, v in counts.items())}.

Not checked:
- Any real camera: boot, display, drawing speed, cache behaviour, heap room. The adapter allocates about {adapter['total_heap_bytes']/1024:.0f} KB (Terminal: 172 KB) and copies
  about 303 KB of pixels per frame through the native copier (Terminal: 169 KB).
- What the native allocator does when it cannot satisfy a request, and how much heap is free. The trace reached this far: the adapter's `0x536af2a8`
  looks up heap object number 2 in the table at `0x5536c7b8` and calls its virtual method at offset 8 with (object, size, 0, caller). Object 2 was
  created at start-up by `0x536ad1b8(object, 2, name, 0x1000000, 0x59600000, 8)` (code at `0x536b2280`): a 16 MiB pool at `0x59600000..0x5a600000`,
  so the 303 KB are under 2 percent of it. The object lives in zero-filled RAM and its virtual table, the allocation method and any free-space
  query were not located statically, so the failure behaviour (null, assertion or wait) and a headroom check are NOT established. The adapter
  assumes a null return and has no headroom check.
- The buffers are allocated once, at the first shot, and kept until power off. `heap_free` has never run on a camera (the Terminal build only called it
  on a failed asset load); here it runs only on a failed allocation.
- Which camera events fire the moment in burst, RAW+JPEG, failed-write or review-off shooting: the hook observes the still-image backend's
  completion notification; one notification per physical shutter press or saved file is not established.
- The file number and the date are not read at all in this stage.
- How the camera's own bottom row, level indicator and icons look under or next to the bands (the bands cover the top and bottom 44 rows
  of the review image opaquely).
"""
    (OUT/'README.md').write_text(readme, encoding='utf-8', newline='\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
