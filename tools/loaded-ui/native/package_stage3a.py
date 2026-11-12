"""Assemble a stage 3a delivery folder after link_loaded.py, build-loaded-stage1.ts, check_hooks_loaded.py and check_stage3a.py have run with
LOADED_VARIANT=stage3aengine (colour engine base) or stage3afilmpack (film pack base): rollback copy of the exact base, SHA256SUMS.txt,
a verification summary, README.md.

  LOADED_VARIANT=stage3aengine python native/package_stage3a.py --pack PATH-TO-BASE --counts "js=38 parity=..."

Never writes anywhere but out/firmware-loaded-stage3a-engine/ or out/firmware-loaded-stage3a-filmpack/. No card or camera is accessed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
VARIANT = os.environ.get('LOADED_VARIANT', '')
ENGINE = VARIANT == 'stage3aengine'
OUT = LAB/'out'/('firmware-loaded-stage3a-engine' if ENGINE else 'firmware-loaded-stage3a-filmpack')
BUILD = OUT/'build'
ENGINE_SHA = '3367220a951724908c06128cf70c39dc5587ff3ca6e52b2a417d071e5a558ebe'
FILMPACK_SHA = 'cf04126f5861c3a64123f0cdc95efa5b65443b44aa0ca975854423acf0131f55'
BASE_SHA = ENGINE_SHA if ENGINE else FILMPACK_SHA
EARLIER = {'1g': '54d3d21d6e5de07fa6a5a291817c5038c1254f737f974d1ba6d0aed7756fbd5b',
           '2a': '780420f3abaf90622f9200366c7314bda59fa1a519ed7232cc2d1f44f74643b7'}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pack', type=Path, required=True)
    ap.add_argument('--counts', default='')
    ap.add_argument('--earlier', default='', help='extra earlier hashes, name=hash pairs')
    args = ap.parse_args()
    counts = dict(kv.split('=', 1) for kv in args.counts.split() if '=' in kv)
    earlier = dict(EARLIER, **dict(kv.split('=', 1) for kv in args.earlier.split() if '=' in kv))
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
                   adapterAssertions=adapter['assertions'], costInstructions=cost, counts=counts)
    (OUT/'verification-summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8', newline='\n')
    detours = hooks['detourCases'] if isinstance(hooks['detourCases'], int) else len(hooks['detourCases'])
    slot_table = chr(10).join(f"  - slot {x['slot']:2d}, look {x['look']}: {x['name']!r} -> Loaded film {x['film']}" for x in manifest['slots'])
    earlier_text = ', '.join(f"{k} `{v[:8]}...`" for k, v in earlier.items())
    base_text = (f"the colour engine build `{ENGINE_SHA}` ({len(pack):,} bytes: the film pack plus the per-film 3D colour tables), read only, never modified. "
                 "Your colour engine looks are kept. The rollback is that same unmodified file." if ENGINE else
                 f"the plain film pack `{FILMPACK_SHA}` ({len(pack):,} bytes). **The colour engine is not in this image** (this is the film-pack twin of the engine image from the same sources): flashing it removes the colour engine until you flash the engine image again. Settings are safe: the engine build is the film pack plus a module.")
    readme = f"""# GR III 2.10: {'colour engine' if ENGINE else 'film pack'} + Loaded stage 3a, permanent film tab and frame counter (hardware test)

Stage 2a/2b (the strips start when the live view returns after a photo) plus the **permanent film tab and mechanical frame counter in the shooting live view**: the screen always shows the loaded film while you shoot. This is an experimental image: it has only run in an emulator.

- Size: {len(image):,} bytes
- SHA-256: `{sha(image)}`
- Base: {base_text}
- Rollback: `rollback/fwdc239b.bin` (SHA-256 `{sha(pack)}`).
- Different from the earlier images ({earlier_text}); marker string `...LOADED-STAGE3A-HARDWARE-UNTESTED` inside the file.
- Six hooks, the same six as stage 2a/2b. Only those six words and the RTOS length differ from the base. No sound, no settings written. RTOS ends at {hex(report['rtosRuntimeEnd'])}; payload {manifest['payloadBytes']:,} bytes.

Check the file first (PowerShell): `Get-FileHash .\\fwdc239b.bin -Algorithm SHA256` must print `{sha(image)}`.

## What it does

- **The tab and the counter sit in the live view.** The film's tab (name and format as in the lab design) at the left and the mechanical counter at the right, above the camera's bottom row, clear of the other furniture (the same rectangles as the strips' furniture: counter 108 x 48 at (612,380), tab 128 x 56 at (0,376)). When the shooting live view appears they slide in once (180 ms) and then sit there. Nothing is drawn again until something changes.
- **No timer at idle.** The views are redrawn only on a change: the slide-in, a photo, a film change, a return to the live view. Measured in the emulator: {cost}.
- **A photo** (UI event `0x013E`, about 0.5 s after the press, as in 2a): the strips run with the tab and counter held in place and the counter rolls to the next number; when the strips are gone the tab and counter stay, showing the new number. The completion hook only consumes the photo's acceptance (late start fallback as in 2a). A key within 2 s of an accepted one is ignored.
- **Visible only in the shooting live view.** Every controller transition hides them (the transition hooks of the earlier stages); when a transition ends in the shooting live view they come back with the slide-in. Menu, Image Control menu, playback, quick review, movie and anything else: nothing is shown, no timer.
- **Film change = new roll.** When you come back to the live view from the menu with another look (or take a photo after changing it), the tab shows the new look, the counter goes back to 1 and the roll number advances. Decision for you to confirm: a new film is a new roll.
- **The counter** counts accepted photos since power-on (frame 1 first). The file number reader is not established, so it is not used. At frame 36 the photo is followed by the end-of-roll moment (rewind) and the counter wraps to 1 (the contact sheet comes later).
- **Allocation:** as in 2a: nothing before the camera has been up about 20 s (5000 UI events counted in `0x55804390`, and 20 s on the OS clock); then the UI-event hook allocates once and, if the shooting live view is up, shows the views. If a photo comes first, the first accepted `0x013E` allocates. A failure is remembered in `0x5580438c`; allocation or attach failures show nothing and never crash, and the next transition tries once more.
- The 20 film names are read from the image; a look that is not one of the pack's films shows the neutral grey tab printed GR III.
{slot_table}

## NOT in this image

No load animation, no contact sheet, no date stamp, no diagnostics panel, no sound, no settings written.{'' if ENGINE else ' No colour engine.'}

Known limits: a look change made in the live view without leaving it (a dial or button, no menu) is noticed only at the next photo or the next transition; movie mode is noticed only when a transition ends in the live view.

## Test card (film the screen)

1. Power on. Wait at least 30 s with the camera idle: the tab and counter should slide in once about 20 s after power-on if the shooting live view is up (or at your first photo) and then sit there without flicker.
2. Shoot three photos: the strips run, the counter rolls 1 to 2 to 3 to 4, the tab and counter stay afterwards.
3. Open the Image Control menu, change the look (for example to Portra 400 or CineStill), close it: the tab and counter slide in again with the new look, the counter at 1.
4. Open the main menu and come back. Play back an image and come back. Half press (AF): nothing should change or flicker.
5. Tell me: whether the tab and counter are where you want them (clear of the other furniture), whether anything flickers or stays on a menu or in playback, whether the camera feels slower, and anything odd.

## If it gets stuck

Take the battery out for 10 seconds. Put `rollback/fwdc239b.bin` on the card root as `fwdc239b.bin`, then hold MENU while powering on. Note whether it stopped before the first photo or after it.

## What was and was not checked

Run on the delivered bytes (`build-report.json`, `hooks-verification.json`, `adapter-verification.json`, `verification-summary.json`):
- Only the six hook words and the RTOS length differ from the base; container checksums and round trip; six hooks, {detours} register, flag and stack cases, three deliberate regressions rejected; the linker accepts only the film pack and the colour engine build.
- {adapter['assertions']} assertions in {len(adapter['checks'])} scenario groups: the idle allocation and the slide-in (six frames and the steady state equal the JS reference, then no timer), a half press, a photo with the counter rolling, thirty-six photos and the wrap, menu / Image Control visit with a film change / playback / quick review / movie / canvas deletion, a film change at a photo, a photo before the block exists, allocation, attach and clock failures with the retry at the next transition, a photo during the slide-in, two photos, the completion fallback, sixty photos with no growth, and the cost.
- Other checks: {', '.join(f'{k} {v}' for k, v in counts.items())}.

Not checked: any real camera; whether the Image Control menu is a controller transition (the owner's visit is simulated as one: if it is an overlay on the live view, the views stay and the film change is noticed at the next photo); drawing speed and cache behaviour; how the tab and counter look over the camera's own furniture.
"""
    (OUT/'README.md').write_text(readme, encoding='utf-8', newline='\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
