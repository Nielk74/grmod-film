"""Assemble a stage 3b delivery folder after link_loaded.py, build-loaded-stage1.ts, check_hooks_loaded.py and check_stage3a.py have run with
LOADED_VARIANT=stage3aengine (colour engine base) or stage3afilmpack (film pack base): rollback copy of the exact base, SHA256SUMS.txt,
a verification summary, README.md.

  LOADED_VARIANT=stage3aengine python native/package_stage3a.py --pack PATH-TO-BASE --counts "js=38 parity=..."

Never writes anywhere but out/firmware-loaded-stage3b-engine/ or out/firmware-loaded-stage3b-filmpack/. No card or camera is accessed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
VARIANT = os.environ.get('LOADED_VARIANT', '')
ENGINE = VARIANT == 'stage3bengine'
OUT = LAB/'out'/('firmware-loaded-stage3b-engine' if ENGINE else 'firmware-loaded-stage3b-filmpack')
BUILD = OUT/'build'
ENGINE_SHA = '3367220a951724908c06128cf70c39dc5587ff3ca6e52b2a417d071e5a558ebe'
FILMPACK_SHA = 'cf04126f5861c3a64123f0cdc95efa5b65443b44aa0ca975854423acf0131f55'
BASE_SHA = ENGINE_SHA if ENGINE else FILMPACK_SHA
EARLIER = {'3a-engine': 'fbd5832db668a266b3435d54b1fbecea05589a2db27cafe556db1059b4d3bcc7', '3a-filmpack': '5f4b7edbfd48a9014aada2939bf34365c4024c565bc94a0cbc9da887fc573d25', '1g': '54d3d21d6e5de07fa6a5a291817c5038c1254f737f974d1ba6d0aed7756fbd5b',
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
    readme = f"""# GR III 2.10: {'colour engine' if ENGINE else 'film pack'} + Loaded stage 3b, no false photo on a playback return, per-film counters (hardware test)

Stage 3a (the permanent film tab and frame counter, the strips on a photo) with two changes. This is an experimental image: it has only run in an emulator.

- Size: {len(image):,} bytes
- SHA-256: `{sha(image)}`
- Base: {base_text}
- Rollback: `rollback/fwdc239b.bin` (SHA-256 `{sha(pack)}`).
- Different from the earlier images ({earlier_text}); marker string `...LOADED-STAGE3B-HARDWARE-UNTESTED` inside the file.
- Six hooks, the same six as stage 2a/3a. Only those six words and the RTOS length differ from the base. No sound, no settings written. RTOS ends at {hex(report['rtosRuntimeEnd'])}; payload {manifest['payloadBytes']:,} bytes.

Check the file first (PowerShell): `Get-FileHash .\\fwdc239b.bin -Algorithm SHA256` must print `{sha(image)}`.

## What changed

**A. A photo needs a capture signal.** In stage 3a, coming back to shooting from playback with a half press also dispatched UI event `0x013E` and advanced the counter. `0x013E` is now a photo only when UI event `0x0161` (the capture sequence of a real photo: `0003`, `015E`, `0161`, `00C3`, `0162`, `0163` within 0.21 s of the press, from the stage 1g field data) was seen in the previous 3 s.
The signal is consumed by the accepted `0x013E` (one signal, one photo), expires after 3 s, and is cleared by a transition to a menu or playback (not by the live view / quick review transitions of a photo with quick review on, so such a photo keeps its signal). The 2 s debounce stays. The signal is kept in a spare RAM word (`0x55804394`), so it also works before the block exists. `0163` and `0003` are not required (only two photos were seen; requiring more could reject real photos in drive modes nobody has seen).
A `0x013E` without a signal does nothing visible: no strips, no counter change. The completion hook is unchanged: after an accepted photo it only consumes it; with no accepted photo in 40 s it starts the animation late (a completion notification means a photo was taken).
Counters in the block record accepted photos, `0x013E` rejected for no signal, rejected for an old signal, signals cleared by a transition, and ignored by the debounce (no UI; a future diagnostic image can read them).
A transition-time rejection of a `0x013E` was not added: with quick review on the live view returns right after a transition, so it would reject real photos.

**IMPORTANT (a known unknown): what a return from playback dispatches is NOT known.** If it also dispatches `0x0161`, this fix will not work on the camera. In that case flash the stage 1g diagnostic (`out/firmware-loaded-stage1g-diagnostic`, film pack based; pages 9 and 10 of its panel list the events before a hook) and do a playback return, to read what is dispatched, then I will choose another signal.

**B. A counter and roll number per film for the whole power session.** Each film keeps its own frame counter and roll number: changing the look away and back resumes that film's count (a roll taken out and put back). At frame 36 the counter wraps to 1 and that film's roll number advances. Looks that are not films share the neutral strip's own counter. **They are lost at power-off** (the counters live in RAM; persistence is research only, see `tools/loaded-ui/notes/persistence-research.md`).

Everything else is stage 3a: the permanent tab and counter in the shooting live view (slide-in once, no timer at idle), the strips on a photo with the counter rolling, hidden in menus, playback, quick review and movie, the layout request, the allocation rule (UI-event hook after 5000 events and 20 s, or the first accepted photo).

## NOT in this image

No load animation, no contact sheet, no counter persistence across power-off, no date stamp, no diagnostics panel, no sound, no settings written.{'' if ENGINE else ' No colour engine.'}

## Test card (film the screen)

1. Power on, wait 30 s: the tab and counter slide in and sit there (the counter starts at 1).
2. Show a picture in playback, come back with a half press of the shutter: **the counter must not change and no strips may run.** Repeat with the menu button.
3. Take three photos: the strips run and the counter goes 1, 2, 3, 4.
4. Change the film in the Image Control menu (for example to CineStill 800T): the counter shows 1 for the new film; take a photo (it shows 2); change back to the first film: **its counter resumes at 4**, not 1.
5. Power-cycle: the counters are back at 1 (as before: they are not saved).
6. Tell me: whether the strips and counter ever react to something that is not a photo (playback return, half press, menu), whether a real photo ever gives no strips, and anything odd.

## If it gets stuck

Take the battery out for 10 seconds. Put `rollback/fwdc239b.bin` on the card root as `fwdc239b.bin`, then hold MENU while powering on. Note whether it stopped before the first photo or after it.

## What was and was not checked

Run on the delivered bytes (`build-report.json`, `hooks-verification.json`, `adapter-verification.json`, `verification-summary.json`):
- Only the six hook words and the RTOS length differ from the base; container checksums and round trip; six hooks, {detours} register, flag and stack cases, three deliberate regressions rejected; the linker accepts only the film pack and the colour engine build and checks the three spare RAM words are unreferenced on each.
- {adapter['assertions']} assertions in {len(adapter['checks'])} scenario groups: everything of stage 3a (the idle allocation, slide-in and steady state equal to the JS reference, no timer at idle, a photo with the counter rolling, thirty-six photos and the wrap, menu, Image Control visit, playback, quick review, movie, canvas deletion, failures, completion fallback), plus the capture signal (a lone `0x013E` is not a photo and draws nothing; a signal 4 s old is rejected, 2.9 s accepted and consumed; a half press (AF) gives no signal; a menu transition clears it and the quick review chain keeps it; the completion hook consumes or starts late; the signal before the block exists) and the per-film counters (resume, wrap per film, non-film look). Cost: {cost}.
- Other checks: {', '.join(f'{k} {v}' for k, v in counts.items())}.

Not checked: any real camera; what a playback return dispatches (see above); the capture signal in self-timer, burst and other drive modes; the transition ids used to tell a menu from a shooting controller are the ones the earlier stages used.
"""
    (OUT/'README.md').write_text(readme, encoding='utf-8', newline='\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
