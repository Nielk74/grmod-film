"""Assemble a stage 4a delivery folder after link_loaded.py, build-loaded-stage1.ts, check_hooks_loaded.py and check_stage3a.py have run with
LOADED_VARIANT=stage3aengine (colour engine base) or stage3afilmpack (film pack base): rollback copy of the exact base, SHA256SUMS.txt,
a verification summary, README.md.

  LOADED_VARIANT=stage3aengine python native/package_stage3a.py --pack PATH-TO-BASE --counts "js=38 parity=..."

Never writes anywhere but out/firmware-loaded-stage4a-engine/ or out/firmware-loaded-stage4a-filmpack/. No card or camera is accessed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
VARIANT = os.environ.get('LOADED_VARIANT', '')
ENGINE = VARIANT == 'stage4aengine'
OUT = LAB/'out'/('firmware-loaded-stage4a-engine' if ENGINE else 'firmware-loaded-stage4a-filmpack')
BUILD = OUT/'build'
ENGINE_SHA = '3367220a951724908c06128cf70c39dc5587ff3ca6e52b2a417d071e5a558ebe'
FILMPACK_SHA = 'cf04126f5861c3a64123f0cdc95efa5b65443b44aa0ca975854423acf0131f55'
BASE_SHA = ENGINE_SHA if ENGINE else FILMPACK_SHA
EARLIER = {'3b-engine': 'd5cf1deafcc7e90133883ef83497d9615b682b87def84833e2a362fbbc66a8df', '3b-filmpack': '2be05acb78e2bd3b406622673b654cd4d3de13d02cc08db9a2013f80cb7bfb36', '3a-engine': 'fbd5832db668a266b3435d54b1fbecea05589a2db27cafe556db1059b4d3bcc7', '3a-filmpack': '5f4b7edbfd48a9014aada2939bf34365c4024c565bc94a0cbc9da887fc573d25', '1g': '54d3d21d6e5de07fa6a5a291817c5038c1254f737f974d1ba6d0aed7756fbd5b',
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
    readme = f"""# GR III 2.10: {'colour engine' if ENGINE else 'film pack'} + Loaded stage 4a, the film-load (canister) animation (hardware test)

Stage 3b (which worked on your camera: no false photos on a playback return, the permanent tab and counter, per-film counters) plus **the film-load animation when you change the film**. This is an experimental image: it has only run in an emulator.

- Size: {len(image):,} bytes
- SHA-256: `{sha(image)}`
- Base: {base_text}
- Rollback: `rollback/fwdc239b.bin` (SHA-256 `{sha(pack)}`).
- Different from the earlier images ({earlier_text}); marker string `...LOADED-STAGE4A-HARDWARE-UNTESTED` inside the file.
- Six hooks, the same six as before. Only those six words and the RTOS length differ from the base. No sound, no settings written. RTOS ends at {hex(report['rtosRuntimeEnd'])}; payload {manifest['payloadBytes']:,} bytes.

Check the file first (PowerShell): `Get-FileHash .\\fwdc239b.bin -Algorithm SHA256` must print `{sha(image)}`.

## What changed

- **The load moment.** When the live view comes back (after the Image Control menu, or any menu) and the selected film is not the one shown before, the lab's canister-loading moment plays once (2.2 s: the cassette drops in, bounces, the leader pulls out across the screen, the counter loads), drawn in the same four small views as the strips (no full-screen view), then the permanent tab and counter settle.
- **The counter lands on that film's own number.** A film swapped back in resumes its count (a roll put back) and the load plays anyway, like reloading a part-used roll. The lab loads a fresh roll at frame 1; the per-film counters are your decision from stage 3b.
- **Looks that are not films** (Standard and the camera's other looks, the neutral strip) get no load, only the slide-in of stage 3a. The first time the tab appears after power-on is not a film change: the slide-in.
- **A photo during the load takes over:** the strips run with the tab and counter held, the load stops, the counter advances once, the tab and counter end showing the new number. Leaving the live view (menu, playback, movie) cancels the load at once; coming back with the same film replays nothing (the slide-in); coming back with another film starts that film's load from the beginning.
- **Detection (unchanged from 3a/3b):** a film change is noticed when a transition ends in the shooting live view and at a photo. A look changed inside the live view without a transition is noticed at the next photo or transition. If the film was changed before the animation memory exists (about 20 s after power-on and before any photo), nothing is shown for it and the first show is the slide-in.
- **Cost:** no timer outside the load, the strips and the slide-in. Measured in the emulator (instructions): {cost}. The idle cost is the same as in 3b.

Everything else is stage 3b: the capture signal (`0x0161` before a `0x013E` makes a photo), per-film counters for the power session (lost at power-off), the strips on a photo with the counter rolling, hidden in menus, playback, quick review and movie, the layout request, the allocation rule (UI-event hook after 5000 events and 20 s, or the first accepted photo).

## NOT in this image

No contact sheet, no counter persistence across power-off, no full-screen (tier 2) view, no diagnostics panel, no sound, no settings written, no date stamp.{'' if ENGINE else ' No colour engine.'}

## Test card (film the screen)

1. Power on. Wait at least 30 s with the camera idle: the tab and counter slide in once and sit there.
2. Open the Image Control menu, change the film, close it: **the canister load must play once** (about 2 s), then the tab and counter sit there with that film's counter. Change through several films, including Standard (no load for Standard, only the slide-in), and back to a film you used before (the load plays, its counter resumes).
3. Change a film and immediately take a photo (during the load): the strips take over, the counter advances by one, the tab and counter end at the new number.
4. If you can, open the main menu while a load is playing: it disappears at once; closing the menu shows the slide-in, not the load again.
5. Take photos, play back an image, come back with a half press: as in 3b (no false photo, nothing odd).
6. Tell me: whether the load plays on every film change and only then, how the load looks over the camera's own furniture, whether anything flickers or stays on screen, whether the camera feels slower, and anything odd.

## If it gets stuck

Take the battery out for 10 seconds. Put `rollback/fwdc239b.bin` on the card root as `fwdc239b.bin`, then hold MENU while powering on. Note whether it stopped before the first photo or after it.

## What was and was not checked

Run on the delivered bytes (`build-report.json`, `hooks-verification.json`, `adapter-verification.json`, `verification-summary.json`):
- Only the six hook words and the RTOS length differ from the base; container checksums and round trip; six hooks, {detours} register, flag and stack cases, three deliberate regressions rejected; the linker accepts only the film pack and the colour engine build.
- {adapter['assertions']} assertions in {len(adapter['checks'])} scenario groups: everything of stages 3a and 3b, plus the load: a film change at the return to the live view (twelve frames equal the JS reference, then the tab and counter settle), every film slot (first, middle and last frame equal the JS reference), the quick review chain and the same film replay nothing, the neutral strip gets no load, a photo during the load, leaving the live view cancels it, another film starts its own load, a film chosen before the block exists, an attach failure and a missing clock (the next transition plays the load), an allocation failure, and the cost.
- Other checks: {', '.join(f'{k} {v}' for k, v in counts.items())}.

Not checked: any real camera; how your Image Control menu return looks to the transition hooks (the tab text updating in 3a/3b suggests the detection works, but a return that is not a controller transition would play no load); how the load looks over the camera's own furniture; drawing speed and cache behaviour; the load in the small views only (tier 1) as the lab shows it for tier 1.
"""
    (OUT/'README.md').write_text(readme, encoding='utf-8', newline='\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
