"""Assemble a stage 5a delivery folder after link_loaded.py, build-loaded-stage1.ts, check_hooks_loaded.py and check_stage5a.py have run with
LOADED_VARIANT = stage5aengine | stage5afilmpack (36-frame rolls) | stage5atest3engine | stage5atest3filmpack (the TEST image, 3-frame rolls):
rollback copy of the exact base, SHA256SUMS.txt, a verification summary, README.md.

  LOADED_VARIANT=stage5aengine python native/package_stage5a.py --pack PATH-TO-BASE --counts "js=38 parity=..."

Never writes anywhere but out/firmware-loaded-stage5a-*/. No card or camera is accessed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
VARIANT = os.environ.get('LOADED_VARIANT', '')
ENGINE = VARIANT.endswith('engine')
TEST = 'test3' in VARIANT
assert VARIANT in ('stage5aengine', 'stage5afilmpack', 'stage5atest3engine', 'stage5atest3filmpack'), VARIANT
OUT = LAB/'out'/('firmware-loaded-stage5a-' + ('test3-' if TEST else '') + ('engine' if ENGINE else 'filmpack'))
BUILD = OUT/'build'
ENGINE_SHA = '3367220a951724908c06128cf70c39dc5587ff3ca6e52b2a417d071e5a558ebe'
FILMPACK_SHA = 'cf04126f5861c3a64123f0cdc95efa5b65443b44aa0ca975854423acf0131f55'
# LOADED_ENGINE_NO_MTF=1: the engine base without the film MTF (2026-11-16, about 7 s less per film photo).
NO_MTF = ENGINE and os.environ.get('LOADED_ENGINE_NO_MTF') == '1'
if NO_MTF:
    ENGINE_SHA = '5a4d2726c1264ef9d2148f922fe02f313e573a367a854bb010692f91d22431ed'
BASE_SHA = ENGINE_SHA if ENGINE else FILMPACK_SHA


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pack', type=Path, required=True)
    ap.add_argument('--counts', default='')
    ap.add_argument('--earlier', default='', help='earlier image hashes, name=hash pairs')
    ap.add_argument('--sheet-cost', default='', help='the measured sheet cost line for the README (from the 36-frame engine run)')
    args = ap.parse_args()
    counts = dict(kv.split('=', 1) for kv in args.counts.split() if '=' in kv)
    earlier = dict(kv.split('=', 1) for kv in args.earlier.split() if '=' in kv)
    pack = args.pack.read_bytes()
    assert sha(pack) == BASE_SHA, 'base is not the expected one'
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
    assert sha(image) not in earlier.values()
    (OUT/'SHA256SUMS.txt').write_text(f"{sha(image)}  fwdc239b.bin\n{sha(pack)}  rollback/fwdc239b.bin\n", encoding='utf-8', newline='\n')
    cost = adapter['cost_instructions']
    summary = dict(image=dict(path=str(OUT/'fwdc239b.bin'), bytes=len(image), sha256=sha(image)),
                   base=dict(sha256=sha(pack), bytes=len(pack), name=manifest['baseName']),
                   payloadBytes=manifest['payloadBytes'], rtosGrowth=report['rtosGrowth'], rtosRuntimeEnd=hex(report['rtosRuntimeEnd']),
                   adapterAssertions=adapter['assertions'], costInstructions=cost, counts=counts, rollFrames=3 if TEST else 36)
    (OUT/'verification-summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8', newline='\n')
    detours = hooks['detourCases'] if isinstance(hooks['detourCases'], int) else len(hooks['detourCases'])
    earlier_text = ', '.join(f"{k} `{v[:8]}...`" for k, v in earlier.items())
    base_text = (f"the colour engine build **without the film MTF** `{ENGINE_SHA}` ({len(pack):,} bytes: the film pack plus the per-film 3D colour tables; the film sharpness step that cost about 7 s per film photo is gone), read only, never modified. "
                 "Your colour engine looks are kept. The rollback is that same unmodified file (no film MTF either); the previous engine image with the film MTF begins `3367220a`." if NO_MTF else
                 f"the colour engine build `{ENGINE_SHA}` ({len(pack):,} bytes: the film pack plus the per-film 3D colour tables), read only, never modified. "
                 "Your colour engine looks are kept. The rollback is that same unmodified file." if ENGINE else
                 f"the plain film pack `{FILMPACK_SHA}` ({len(pack):,} bytes). **The colour engine is not in this image** (this is the film-pack twin of the engine image from the same sources): flashing it removes the colour engine until you flash the engine image again. Settings are safe: the engine build is the film pack plus a module.")
    n = 3 if TEST else 36
    title = f"{'colour engine' if ENGINE else 'film pack'} + Loaded stage 5a, the end-of-roll contact sheet" + (" (TEST IMAGE: rolls of 3 frames)" if TEST else " (rolls of 36)")
    test_banner = f"""
> **THIS IS THE TEST IMAGE.** A roll is **3 frames** here, not 36, so the contact sheet plays after the **third** photo of each film. It is the same code as the 36-frame image (the roll length is the only build-time difference). Do not keep it installed for real shooting: the counter wraps every 3 photos.
""" if TEST else ""
    test_card = f"""1. Power on. Wait at least 30 s with the camera idle (the tab and counter slide in once and sit there).
2. Take **3 photos**, a few seconds apart (more than 2 s: two shutter events closer than that count as one photo). The tab shows the counter 1, 2, 3 (as always); after the **third** photo's strips the **contact sheet must play full screen** (about 3.4 s): a paper sheet with four film strips of 36 small placeholder frames that fill in one after another, a red grease-pencil ring around one frame, the top band reading the roll number, then FRAMES EXPOSED, REWINDING, FILM REWOUND, the cassette and leader in the bottom band, and the counter counting back to 1. Then the tab and counter return at **1** (roll 2).
3. Change the film in the Image Control menu (the canister load of 4a plays), then take 3 more photos: the sheet plays after the third, with that film's colours.
4. Take a photo **during** the sheet: the sheet must stop at once, the strips of the photo run, the counter shows 2 (frame 1 of the new roll was the photo).
5. Open the main menu **during** the sheet: it must disappear at once; closing the menu shows the slide-in, not the sheet again.
6. Film the screen for steps 2, 4 and 5 and tell me: whether the sheet appears at the end of the third photo and only then, whether the live view keeps running behind it (it is covered by the opaque sheet, and visible above and below it), whether it looks smooth or choppy (it ticks at 20 frames per second by design), whether anything flickers, tears or stays on screen afterwards, whether the camera feels slow (half-press AF during the sheet), whether the sheet ever fails to play (then the moment is skipped: the counter simply goes back to 1), and anything odd.""" if TEST else f"""1. Power on. Wait at least 30 s with the camera idle.
2. Shoot a roll: **36 photos** on one film (the tab counter shows the frame number). After the strips of the **36th** photo the **contact sheet must play full screen** (about 3.4 s): a paper sheet with four film strips of 36 small placeholder frames that fill in one after another, a red grease-pencil ring around one frame, the top band reading the roll number, FRAMES EXPOSED, REWINDING, FILM REWOUND, the cassette and leader in the bottom band, the counter counting back to 1. Then the tab and counter return at **1** (roll 2).
   (If you do not want to shoot 36 photos, use the test image `firmware-loaded-stage5a-test3-*`: its rolls are 3 frames.)
3. Take a photo during the sheet (it stops at once, the strips run, the counter shows 2); open a menu during the sheet (it disappears at once and is not replayed).
4. Tell me what you saw (as in the test image card): smoothness, flicker, anything left on the screen, whether the camera felt slow, whether the sheet is skipped."""
    sheet_cost = args.sheet_cost or ('sheet frames were measured in the 36-frame image: ' + json.dumps({k: v for k, v in cost.items() if k.startswith('sheet')}))
    readme = f"""# GR III 2.10: {title}
{test_banner}
Stage 4a (which worked on your camera) plus **the end-of-roll contact sheet, full screen (tier 2)**. Stage 4b proved on your camera that a 1.38 MB buffer and a 720x480 view work; this is the first real use of them. Experimental image: the sheet has only run in an emulator.

- Size: {len(image):,} bytes
- SHA-256: `{sha(image)}`
- Base: {base_text}
- Rollback: `rollback/fwdc239b.bin` (SHA-256 `{sha(pack)}`).
- Different from the earlier images ({earlier_text}); marker string `...LOADED-STAGE5A-{'TEST3-ROLL-OF-THREE-' if TEST else ''}HARDWARE-UNTESTED` inside the file.
- Six hooks, the same six as before. Only those six words and the RTOS length differ from the base. No sound, nothing written. RTOS ends at {hex(report['rtosRuntimeEnd'])}; payload {manifest['payloadBytes']:,} bytes. The stage 4b diagnostic is not in this image.

Check the file first (PowerShell): `Get-FileHash .\\fwdc239b.bin -Algorithm SHA256` must print `{sha(image)}`.

## What changed

- **The sheet.** The photo that completes a roll ({n} frames per film, per-film counters as in 3b/4a) plays its strips as before. When they are over, the lab's end-of-roll moment plays full screen for 3.4 s: the contact sheet (stylised placeholder frames tinted by the film, numbering, a grease-pencil ring), the camera rewinding in the top and bottom bands, the counter counting back to 1. Then the permanent tab and counter come back at frame 1 of the next roll (the roll number advances, as in 3b).
- **How (design A).** When the moment starts the camera is asked for ONE 1,382,400-byte buffer (RGBA 720x480, the exact block that 4b allocated on your camera). The same renderer as the lab draws each frame into it; a 720x480 view at 0,0 (below the four small views, so the counter stays on top of the sheet) copies it to the screen. At the end, or on any cancel, the view is removed and the buffer freed. The buffer exists only during the moment; idle cost is unchanged from 4a (no timer outside the moments).
- **Frame interval: 50 ms (20 frames per second).** A sheet frame costs 2.4 to 5.3 million instructions to render plus the copy of 1.38 MB; 4b measured about 2.2 ms per million instructions and about 25 ms for a full-screen draw on your camera, so a frame is roughly 25 to 40 ms of the camera's UI task. At the 33 ms tick of the strips that would keep the UI task busy nearly all the time; at 50 ms it leaves room for the camera's own UI events (4b: 216 events per second during a 41 ms repaint against 267 before). Frames are never skipped silently: the sheet is drawn for the current clock, so a slow frame only means the next one is later; the moment still ends at 3.4 s. If it looks choppy the interval is one constant.
- **If the buffer or the view cannot be had:** the moment is skipped, the tab and counter come back at frame 1 of the next roll, and the failure is counted (not retried within the same roll end; the next roll end tries again). No crash, no leak.
- **Cancel rules:** a menu, playback or movie transition, a canvas deletion or a missing clock ends the sheet at once and frees the buffer (coming back shows the slide-in, not the sheet); a new photo ends it at once (the strips run, the counter advances from 1 of the new roll; a photo during the strips of the last frame skips the sheet for that roll); a half press does nothing; a film change needs a menu visit, which cancels it, and the new film's load plays as in 4a.
- **Cost:** {sheet_cost}

## NOT in this image

- **Real thumbnails.** The sheet shows stylised placeholder frames (film-tinted tiles with numbers), not your photos. Reading real thumbnails from the camera is a separate later research item; nothing of your photos is read.
- No counter persistence across power-off, no sound, no settings written, no date stamp.{'' if ENGINE else ' No colour engine.'}
- The alternative if the big buffer ever fails on some camera state: banded drawing without a big buffer (design B, proven in 4b at 41 ms per frame). Not used here.

## Test card (film the screen)
{test_banner}
{test_card}

## If it gets stuck

Take the battery out for 10 seconds. Put `rollback/fwdc239b.bin` on the card root as `fwdc239b.bin`, then hold MENU while powering on. Note whether it stopped before, during or after the sheet.

## What was and was not checked

Run on the delivered bytes (`build-report.json`, `hooks-verification.json`, `adapter-verification.json`, `verification-summary.json`):
- Only the six hook words and the RTOS length differ from the base; container checksums and round trip; six hooks, {detours} register, flag and stack cases, three deliberate regressions rejected; the linker accepts only the film pack and the colour engine build.
- {adapter['assertions']} assertions in {len(adapter['checks'])} scenario groups: the roll end (sheet frames equal the lab's JS reference by CRC, first, middle and last, and every film), the allocation of one 1,382,400-byte buffer and its release, the view order and its layout rectangle, the pixels on the screen, an allocation failure, a view refusal, a missing clock, cancel by menu, playback, movie, canvas deletion, photo and film change at several moments, two roll ends in a row, ten roll ends without a leak, and{' everything of stage 4a (36-frame scenarios only in the 36-frame image).' if TEST else ' everything of stage 4a.'}
- Other checks: {', '.join(f'{k} {v}' for k, v in counts.items())}.

Not checked: any real camera; the hardware time of a sheet frame (estimated from 4b) and how the display combines the sheet with the live view during the moment; how the 4a to 5a sequence feels; the sheet drawn over the camera's own furniture other than the counter.
"""
    (OUT/'README.md').write_text(readme, encoding='utf-8', newline='\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
