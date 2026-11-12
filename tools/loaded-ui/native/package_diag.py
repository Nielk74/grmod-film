"""Assemble the stage 1d (diagnostic) delivery folder after link_loaded.py, build-loaded-stage1.ts, check_hooks_loaded.py and
check_diag.py have run with LOADED_VARIANT=diag: rollback copy of the exact base, SHA256SUMS.txt, a verification summary, README.md.

  LOADED_VARIANT=diag python native/package_diag.py --pack PATH-TO-FILM-PACK --counts "js=38 parity=..."

Never writes anywhere but out/firmware-loaded-stage1d-diagnostic/. No card or camera is accessed.
"""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
OUT = LAB/'out'/'firmware-loaded-stage1d-diagnostic'
BUILD = OUT/'build'
PACK_SHA = 'cf04126f5861c3a64123f0cdc95efa5b65443b44aa0ca975854423acf0131f55'
STAGE1_SHA = '5b10170bed7e6aa722b5d80e4187a868c2549e4e0bb648b2763f2f41f9f8ab84'


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
    assert sha(image) != STAGE1_SHA
    (OUT/'SHA256SUMS.txt').write_text(f"{sha(image)}  fwdc239b.bin\n{sha(pack)}  rollback/fwdc239b.bin\n", encoding='utf-8', newline='\n')
    summary = dict(image=dict(path=str(OUT/'fwdc239b.bin'), bytes=len(image), sha256=sha(image)), base=dict(sha256=sha(pack), bytes=len(pack)),
                   payloadBytes=manifest['payloadBytes'], rtosGrowth=report['rtosGrowth'], rtosRuntimeEnd=hex(report['rtosRuntimeEnd']),
                   diagAssertions=adapter['assertions'], counts=counts)
    (OUT/'verification-summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8', newline='\n')
    detours = hooks['detourCases'] if isinstance(hooks['detourCases'], int) else len(hooks['detourCases'])
    cells = chr(10).join(f"| {n} | {t} | {m} |" for n, t, m in [
        ('1', 'hook fired and clock read', 'green: the shot hook ran and the clock gave a time. Red: the clock failed (the panel still shows).'),
        ('2', 'root found', 'green: the live view screen and its root were found, so the panel could be attached. (If this cannot be done, no panel appears at all.)'),
        ('3', 'film read', 'green, with text `L<look> F<film>` (the look byte read from the settings and the Loaded film it maps to; look 64 and up are the pack films, 11 is Standard). Red, with the reason as text: `NO RECORD` (settings pointer null), `MISALIGNED`, `MOVIE n` (movie flag), `SET n` (active set above 2).'),
        ('4', 'Loaded state allocated', 'green: the 496-byte state block was allocated. Red: the allocation returned null.'),
        ('5A..5D', 'the four pixel buffers', 'top 126,720 / bottom 126,720 / counter 20,736 / tab 28,672 bytes. A red one is the buffer whose allocation returned null; everything allocated for Loaded is freed then.'),
        ('6', 'four views created', 'red: the view factory returned null for one of the four.'),
        ('7', 'attached', 'red: the four views could not be attached to the screen tree.'),
        ('8', '`loaded_start` accepted', 'red: the clock failed or the Loaded engine refused the parameters.'),
        ('9', 'first tick', 'red: the Loaded renderer refused its first frame.')])
    readme = f"""# GR III 2.10: film pack + Loaded stage 1d, DIAGNOSTIC (hardware test)

**This is a DIAGNOSTIC image. It is not the Loaded experience.** Its only job is to show, on the camera's own screen, how far the Loaded
code got after each shot, because stage 1 (`{STAGE1_SHA[:8]}...`) showed nothing and nothing told us why. Flash it, shoot three times, photograph the corner, report.

- File: `fwdc239b.bin`, {len(image):,} bytes
- SHA-256: `{sha(image)}`
- Stage 1 it replaces for this test (different file): `{STAGE1_SHA}`
- Built on the film pack `{PACK_SHA}` ({len(pack):,} bytes), kept in `rollback/fwdc239b.bin`. Same base, same five hooks, same state word `0x558043b8`, no sound, no settings written.
- RTOS ends at {hex(report['rtosRuntimeEnd'])}; payload {manifest['payloadBytes']:,} bytes.

## Before you flash: your camera currently runs the colour engine build

Flashing this image removes the colour engine (the per-film 3D colour tables) until a rebased image exists; Loaded and the colour engine
are not combined yet. Your settings are safe: the colour engine build is this film pack plus one module (same 446 changed official words,
same looks 64 to 83, same ratios and settings guard; it differs in two retargeted branches and in the appended data), and this image is
that same film pack plus a different module. To go back to the colour engine build, flash it again from
`scratch/colour-engine/firmware-test/` (that file's SHA-256 begins `3367220a`).

## Check that the right file is on the card (before the update)

In PowerShell, in the folder of the card (or the copy you put on it):

    Get-FileHash .\\fwdc239b.bin -Algorithm SHA256

The hash must be exactly `{sha(image)}` (case does not matter). `{STAGE1_SHA[:8]}...` is stage 1 and `{PACK_SHA[:8]}...` is the plain film pack: both are wrong for this test.
A card that holds the older stage 1 file under the same name is the most likely reason nothing appeared, so check this first.
Replace the file on the card root, run the update (hold MENU while powering on), wait for the camera to restart itself.

## Test card (about five minutes)

1. Standard look (not a film), P mode, take one photo. Watch the right-bottom corner for about six seconds, photograph the screen with your phone as soon as the panel is up.
2. A pack film (Portra 400, or any film), take one photo, photograph the corner.
3. One more photo with the same film, photograph the corner.
4. Report, for each of the three: whether a panel appeared at all, and for each of the twelve cells its colour (grey / orange / green / red) and the text lines.
   If no panel appears at all, say so: that means the update was not applied, or the shot hook did not run, or the screen root was not found (cell 2 cannot be shown without a root).

## What the panel is

One panel, 240 x 176 pixels, at the corner the Terminal build used (464,259), drawn by one view built exactly like the Terminal's (one 169 KB block, one view, one timer),
visible about six seconds after every completed shot. Twelve cells in two rows of six, each with its label above it:

| cell | step | meaning |
|---|---|---|
{cells}

Colours: grey = not reached, orange = running (shown on the screen one timer tick, 33 ms, before the step executes, so a step that hangs or crashes stays orange), green = ok, red = failed.
Text: line 1 is the film read (`L75 F11`: look 75, Loaded film 11), line 2 `SHOT n` is the shot counter since power-on, line 3 `Pxxxx` is the low 16 bits of the panel block's address in hex
(it proves the block was allocated and stays the same on every shot). The steps run one per 33 ms tick, about a second in total, after the panel is already visible, so each failure leaves its cell on the screen.
When all twelve are green the real Loaded moment plays (strips, counter, tab) with the panel staying in its corner until six seconds after the shot.
MENU, playback or any other event removes the panel and the Loaded views at once.

## Can the update be recognised without shooting?

No cheap signal is built in and none is claimed. The image has the same version number as the film pack and changes no menu text, list or icon (the official container header, every
section except the RTOS and the film pack's own bytes are unchanged), so the menus look the same as your colour engine build and the film pack. One hint only, not added and not verified: the colour engine
build adds a colour step to saved pictures of five films (CineStill 800T, Kodachrome 64, Classic Neg, Classic Chrome, Blockbuster) estimated at about 1.4 G instructions for a 24 MP picture, so
saving one may be visibly slower there than with this image; that is an estimate from its test card, never measured. The reliable check is the file hash above plus the panel.

## If it gets stuck

Take the battery out for 10 seconds. Put `rollback/fwdc239b.bin` (the unmodified film pack, SHA-256 `{PACK_SHA}`) on the card root as `fwdc239b.bin`, then hold MENU while powering on.
Say whether it stopped before the first photo or after it.

## What was and was not checked

Passed in emulation on the delivered bytes (`build-report.json`, `hooks-verification.json`, `adapter-verification.json`, `verification-summary.json`):
- Film pack bytes kept apart from the five hook words and the RTOS length; container checksums and decode round trip; five hooks, {detours} register, flag and stack cases, three deliberate regressions rejected.
- {adapter['assertions']} assertions in {len(adapter['checks'])} diagnostic scenarios with the original native tree, timer, clock and copier bodies: all-ok (twelve cells, two ticks per step, the Loaded first frame equals the JS reference, the panel and the four views drawn by the original canvas draw, everything gone after the panel window), each failure cell
  (record null, misaligned record, movie byte, set 3, each of the five allocations failing, each of the four views refused, attach failing, `loaded_start` refusing, first tick refusing, no clock): the right cell red, later cells grey, earlier green, only the panel attached, canaries intact, shooting not delayed (the hook itself makes three allocations: the block, the view and one child-list slot), the next shot works; cancel, menu, shooting transitions, canvas deletion; 61 shots with no allocation growth.
- Other checks run on the same sources: {', '.join(f'{k} {v}' for k, v in counts.items())}.

Not checked: any real camera; whether the allocator returns null or something else when it cannot give memory (the native view factory writes through a null pointer, so a null from the allocator at view creation would crash natively before cell 6 could show; the failure of cell 6 was provoked at the factory itself);
the vector growth the screen tree does while attaching (8, 16 and 32 byte allocations); drawing speed and cache behaviour.
"""
    (OUT/'README.md').write_text(readme, encoding='utf-8', newline='\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
