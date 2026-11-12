"""Assemble the stage 2a delivery folder after link_loaded.py, build-loaded-stage1.ts, check_hooks_loaded.py and check_stage2a.py have run
with LOADED_VARIANT=stage2a: rollback copy of the exact base, SHA256SUMS.txt, a verification summary, README.md.

  LOADED_VARIANT=stage2a python native/package_stage2a.py --pack PATH-TO-FILM-PACK --counts "js=38 parity=..."

Never writes anywhere but out/firmware-loaded-stage2a/. No card or camera is accessed.
"""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
OUT = LAB/'out'/'firmware-loaded-stage2a'
BUILD = OUT/'build'
PACK_SHA = 'cf04126f5861c3a64123f0cdc95efa5b65443b44aa0ca975854423acf0131f55'
EARLIER = {'stage 1 (first build)': '5b10170bed7e6aa722b5d80e4187a868c2549e4e0bb648b2763f2f41f9f8ab84',
           '1d': 'd59df016d87decc8f8eb38fd562827688b11b216d0835273decd9444f4284dec',
           '1e': '625f5b63488e95e3b96eda1a689a509a774fb4884df28a308e3d17532e573d15',
           '1f': '4299ffeb6f34b5630a837d681cb33a1e36783f32e56dfa62b35fc7e1b756e388',
           '1g': '54d3d21d6e5de07fa6a5a291817c5038c1254f737f974d1ba6d0aed7756fbd5b'}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pack', type=Path, required=True)
    ap.add_argument('--counts', default='')
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
    assert sha(image) not in EARLIER.values()
    (OUT/'SHA256SUMS.txt').write_text(f"{sha(image)}  fwdc239b.bin\n{sha(pack)}  rollback/fwdc239b.bin\n", encoding='utf-8', newline='\n')
    cost = adapter['per_event_cost_instructions']
    summary = dict(image=dict(path=str(OUT/'fwdc239b.bin'), bytes=len(image), sha256=sha(image)), base=dict(sha256=sha(pack), bytes=len(pack)),
                   payloadBytes=manifest['payloadBytes'], rtosGrowth=report['rtosGrowth'], rtosRuntimeEnd=hex(report['rtosRuntimeEnd']),
                   adapterAssertions=adapter['assertions'], perEventCostInstructions=cost, counts=counts)
    (OUT/'verification-summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8', newline='\n')
    detours = hooks['detourCases'] if isinstance(hooks['detourCases'], int) else len(hooks['detourCases'])
    slot_table = chr(10).join(f"  - slot {x['slot']:2d}, look {x['look']}: {x['name']!r} -> Loaded film {x['film']}" for x in manifest['slots'])
    earlier = ', '.join(f"{k} `{v[:8]}...`" for k, v in EARLIER.items())
    readme = f"""# GR III 2.10: film pack + Loaded stage 2a (hardware test)

Flash `fwdc239b.bin` from this folder. This is an experimental image: it has only run in an emulator.

- Size: {len(image):,} bytes
- SHA-256: `{sha(image)}`
- Built on the plain film pack `{PACK_SHA}` ({len(pack):,} bytes), kept in `rollback/fwdc239b.bin`. **The colour engine is not in this image** (the base is the film pack); flashing it removes the colour engine until a rebased image exists. Settings are safe: the engine build is this film pack plus a module.
- Different from the earlier images ({earlier}); marker string `...LOADED-STAGE2A-HARDWARE-UNTESTED` inside the file.
- Six hooks: the five of the earlier stages plus one at the first instruction of the UI event dispatcher (`0x53228ab4`). Only those six words (and the RTOS length) differ from the film pack. No sound, no settings written. RTOS ends at {hex(report['rtosRuntimeEnd'])}; payload {manifest['payloadBytes']:,} bytes.

Check the file first (PowerShell): `Get-FileHash .\\fwdc239b.bin -Algorithm SHA256` must print `{sha(image)}`.

## What it does

After each photo the strips, counter and tab of the "roll of film" moment play and clear (as in stage 1: top and bottom bands in the film's own format, a mechanical frame counter and the film's tab, 2.0 s in all, end of roll on frame 36).
**What is new: it starts when the live view returns after the photo, about 0.5 s after the press, not 15 to 20 s later at the camera's completion notification.**

- Trigger: the camera dispatches the UI event `0x013E` twice per photo, a fraction of a second apart, exactly when the live view returns (field data of the stage 1g video; it never fires for half presses or menus). The first one is accepted; it and anything within 2 s of an accepted one is ignored, so the second of the pair and a burst count as one photo.
- The completion hook (`0x532d55f8`, the earlier trigger) no longer starts a second animation: it only consumes the acceptance of its photo (up to four are queued, each with its time; one older than 40 s is dropped). If it fires and no `0x013E` was accepted, it starts the animation late, as stage 1 did, and counts a fallback.
- A second photo (a key accepted 2 s or more after the previous one) restarts the animation (no new slide-in while the views still show); the frame counter advances once per photo; completion notifications consume the acceptances in order.
- The release hook (`0x53239818`) used to cancel the animation. In the field data it fires together with the completion, so for a Standard photo it would cut the animation 0.4 s after it began: it now does nothing.
- Self-timer, burst and movie are unknown on this camera. The build must not crash: a self-timer photo is expected to give `0x013E` at the capture (so the animation plays then); a burst gives one animation (keys within 2 s are one photo); movie mode gives no animation (the film read refuses it).

Films: the 20 films of the base, in slot order, as the linker read their names out of the image:
{slot_table}
A look that is not one of the pack's films plays the neutral grey strip printed "GR III". The frame number is a counter the adapter keeps: it starts at 1 at the first photo after power-on and is lost at power off (roll 1 for shots 1 to 36).

## Allocation (and what it means for the first photo)

Nothing is allocated before the camera has been up for about 20 s, and never in the release hook. The UI-event hook counts UI events in a spare zero-filled RAM word (`0x55804390`) while no block exists; at 5000 events (about 20 s) and an OS clock reading of 20 s or more, the next UI event allocates the animation's memory (303 KB: the state and the four pixel buffers) once, on the UI task. A failure is remembered in a second spare word (`0x5580438c`) and not retried.
A photo before that point: the first accepted `0x013E` allocates at that moment (the same hook and task as the idle allocation, and a photo was just taken, so the camera is up), so the first photo should animate too; if that allocation fails there is no animation for it and the completion hook tries once more, late. The animation's memory is kept until power off.

## Layout

The four views are asked to be laid out after they are attached (the root is asked through its own vtable slot `0x20`): without it, a view attached to a root that has just been painted keeps the rectangle 0,0,0,0 and is never drawn (stage 1f/1g finding, reproduced in the emulator with the camera's own layout code).

## NOT in this image

No permanent tab or counter, no load animation, no contact sheet, no diagnostics panel, no sound, no menu, no settings written, no date stamp on the slide mount, no colour engine.

## Test card (film the screen, say out loud when you press the shutter)

1. Power on. Wait at least 30 s with the camera idle.
2. Portra 400: one photo. Do NOT half press afterwards. What to look for: the screen goes black for about half a second after the press; **the strips advance starts when the live view comes back**, about 0.5 s after the press (not 15 to 20 s later); the counter and tab slide in and out; everything is gone 2 s after that. Nothing may start again 15 to 20 s later.
3. Standard look: one photo, the same: a grey strip printed GR III.
4. Three more film looks, one photo each (a slide film, an instant film, a black and white film): the format differs (slide mount, instant print, ...).
5. Then, if you like: two photos 3 seconds apart; a photo then menu; a half press without a photo (nothing should appear).
6. Tell me: when the animation started relative to the press, whether anything appeared again 15 to 20 s later, whether the camera ever felt slower, and anything odd.

## If it gets stuck

Take the battery out for 10 seconds. Put `rollback/fwdc239b.bin` (the unmodified film pack) on the card root as `fwdc239b.bin`, then hold MENU while powering on. Note whether it stopped before the first photo or after it.

## What was and was not checked

Passed in emulation on the delivered bytes (`build-report.json`, `hooks-verification.json`, `adapter-verification.json`, `verification-summary.json`):
- Film pack bytes kept apart from the six hook words and the RTOS length; container checksums and round trip; six hooks, {detours} register, flag and stack cases, three deliberate regressions rejected; the base is refused unless it is the film pack.
- {adapter['assertions']} assertions in {len(adapter['checks'])} scenario groups: the fast path and idle allocation, the key event (accepted, first frame and later frames equal the JS reference, layout on a clean root), the double event and the 2 s rule, the first photo before the guard (and a failed allocation), the completion hook (consume, fallback, 40 s limit, the Standard timing), two photos back to back, film change between photos, a refused view, another controller, no clock, transitions and canvas deletion, a burst and eighty photos.
- Cost of one ordinary UI event through the real trampoline and dispatcher: {cost} instructions (trampoline and displaced instruction included).
- Other checks: {', '.join(f'{k} {v}' for k, v in counts.items())}.

Not checked: any real camera; whether `0x013E` also fires at the capture for the self-timer, burst and drive modes; whether allocating on the first accepted key (rather than after 20 s) is safe on hardware (it is the same hook, task and allocator call, with the camera certainly up); drawing speed and cache behaviour; what the camera's own bottom row looks like under the bands.
"""
    (OUT/'README.md').write_text(readme, encoding='utf-8', newline='\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
