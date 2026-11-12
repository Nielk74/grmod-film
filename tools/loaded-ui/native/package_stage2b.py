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
OUT = LAB/'out'/'firmware-loaded-stage2b-engine'
BUILD = OUT/'build'
PACK_SHA = '3367220a951724908c06128cf70c39dc5587ff3ca6e52b2a417d071e5a558ebe'     # the colour engine base
FILMPACK_SHA = 'cf04126f5861c3a64123f0cdc95efa5b65443b44aa0ca975854423acf0131f55'
EARLIER = {'stage 1 (first build)': '5b10170bed7e6aa722b5d80e4187a868c2549e4e0bb648b2763f2f41f9f8ab84',
           '1d': 'd59df016d87decc8f8eb38fd562827688b11b216d0835273decd9444f4284dec',
           '1e': '625f5b63488e95e3b96eda1a689a509a774fb4884df28a308e3d17532e573d15',
           '1f': '4299ffeb6f34b5630a837d681cb33a1e36783f32e56dfa62b35fc7e1b756e388',
           '1g': '54d3d21d6e5de07fa6a5a291817c5038c1254f737f974d1ba6d0aed7756fbd5b',
           '2a': '780420f3abaf90622f9200366c7314bda59fa1a519ed7232cc2d1f44f74643b7'}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pack', type=Path, required=True, help='the colour engine base')
    ap.add_argument('--filmpack', type=Path, required=True, help='the film pack, as the second rollback')
    ap.add_argument('--counts', default='')
    args = ap.parse_args()
    counts = dict(kv.split('=', 1) for kv in args.counts.split() if '=' in kv)
    pack = args.pack.read_bytes()
    assert sha(pack) == PACK_SHA, 'base is not the expected film pack'
    filmpack = args.filmpack.read_bytes()
    assert sha(filmpack) == FILMPACK_SHA, 'not the film pack'
    (OUT/'rollback').mkdir(exist_ok=True)
    (OUT/'rollback-filmpack').mkdir(exist_ok=True)
    (OUT/'rollback'/'fwdc239b.bin').write_bytes(pack)
    (OUT/'rollback-filmpack'/'fwdc239b.bin').write_bytes(filmpack)
    image = (OUT/'fwdc239b.bin').read_bytes()
    report = json.loads((OUT/'build-report.json').read_text(encoding='utf-8'))
    manifest = json.loads((BUILD/'payload-manifest.json').read_text(encoding='utf-8'))
    adapter = json.loads((OUT/'adapter-verification.json').read_text(encoding='utf-8'))
    hooks = json.loads((OUT/'hooks-verification.json').read_text(encoding='utf-8'))
    assert sha(image) == report['outputSha256'] and len(image) == report['outputBytes']
    assert adapter['patched_rtos_sha256'] == hooks['patchedRtosSha256'], 'checks ran on different images'
    assert adapter['payload_elf_sha256'] == manifest['elfSha256'], 'adapter check ran on another payload'
    assert sha(image) not in EARLIER.values()
    (OUT/'SHA256SUMS.txt').write_text(f"{sha(image)}  fwdc239b.bin\n{sha(pack)}  rollback/fwdc239b.bin\n{sha(filmpack)}  rollback-filmpack/fwdc239b.bin\n", encoding='utf-8', newline='\n')
    cost = adapter['per_event_cost_instructions']
    summary = dict(image=dict(path=str(OUT/'fwdc239b.bin'), bytes=len(image), sha256=sha(image)), base=dict(sha256=sha(pack), bytes=len(pack), name='colour engine (five LUT tables)'),
                   payloadBytes=manifest['payloadBytes'], rtosGrowth=report['rtosGrowth'], rtosRuntimeEnd=hex(report['rtosRuntimeEnd']),
                   adapterAssertions=adapter['assertions'], perEventCostInstructions=cost, counts=counts)
    (OUT/'verification-summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8', newline='\n')
    detours = hooks['detourCases'] if isinstance(hooks['detourCases'], int) else len(hooks['detourCases'])
    adapter_end_note = f"payload {manifest['payloadBytes']:,} bytes, RTOS growth {report['rtosGrowth']:,} bytes"
    slot_table = chr(10).join(f"  - slot {x['slot']:2d}, look {x['look']}: {x['name']!r} -> Loaded film {x['film']}" for x in manifest['slots'])
    earlier = ', '.join(f"{k} `{v[:8]}...`" for k, v in EARLIER.items())
    readme = f"""# GR III 2.10: colour engine + Loaded stage 2b (hardware test)

Stage 2a (which worked on your camera) rebased onto the colour engine firmware, so you keep the five colour-engine film looks. This is an experimental image: it has only run in an emulator.

- Size: {len(image):,} bytes
- SHA-256: `{sha(image)}`
- Base: the colour engine build `fwdc239b.bin` (`{PACK_SHA}`, {len(pack):,} bytes: the film pack plus the per-film 3D colour tables for CineStill 800T, Kodachrome 64, Classic Neg, Classic Chrome and Blockbuster), read only, never modified.
- **Rollback: `rollback/fwdc239b.bin` is the UNMODIFIED colour engine base** (SHA-256 `{PACK_SHA}`). Second rollback: `rollback-filmpack/fwdc239b.bin`, the plain film pack (`{FILMPACK_SHA}`), without the colour engine.
- Different from the earlier images ({earlier}); marker string `...LOADED-STAGE2B-HARDWARE-UNTESTED` inside the file.
- Six hooks, the same six as stage 2a. Only those six words and the RTOS length differ from the colour engine base: its own patches (the colour engine's two retargeted branches at `0x535047d4` and `0x536f028c`, its tables and module) are untouched, and our hook sites, state word `0x558043b8`, spare words `0x55804390` and `0x5580438c` and the heap area are not used by that base (the linker scans it for references and refuses the image otherwise). Our code is appended after the engine's: the RTOS ends at {hex(report['rtosRuntimeEnd'])} ({adapter_end_note}). No sound, no settings written.

Check the file first (PowerShell): `Get-FileHash .\\fwdc239b.bin -Algorithm SHA256` must print `{sha(image)}`.

## What it does

Exactly stage 2a, on the colour engine: after each photo the strips, counter and tab of the "roll of film" moment play and clear. They start when the live view returns after the photo (UI event `0x013E`, about 0.5 s after the press), not at the camera's completion notification 15 to 20 s later; the completion hook only consumes that photo's acceptance and, if no `0x013E` came, starts the animation late.
A second `0x013E` within 2 s of an accepted one is ignored; a photo 2 s or more later restarts the animation; the frame counter advances once per photo. Nothing is allocated before the camera has been up about 20 s (5000 UI events and 20 s on the OS clock); the first accepted `0x013E` allocates if that has not happened yet.
The release hook no longer cancels anything (it fires with the completion). Self-timer, burst and movie: no crash; a burst is one photo; movie gives no animation.

The 20 film names are read out of this image (the colour engine adds colour tables, not looks: the slot table is the same as the film pack's, and every slot has a Loaded film; a look that is not one of the pack's films plays the neutral grey strip printed GR III):
{slot_table}

## NOT in this image

No permanent tab or counter, no load animation, no contact sheet, no diagnostics panel, no sound, no menu, no settings written, no date stamp on the slide mount.

## Test card (film the screen, say out loud when you press the shutter)

1. Power on. Wait at least 30 s with the camera idle.
2. One photo each, with Portra 400, CineStill 800T, Gold 200, Kodachrome 64 and Standard. Do not half press afterwards. What to look for: the strips advance starts when the live view comes back (about 0.5 s after the press); nothing starts again 15 to 20 s later; the colour of the pictures is the colour engine's (CineStill and Kodachrome with their own tables).
3. Tell me: whether the strips start as in stage 2a, whether saving CineStill or Kodachrome pictures is as slow as before, whether anything else looks different from the colour engine build you had, and anything odd.

## If it gets stuck

Take the battery out for 10 seconds. Put `rollback/fwdc239b.bin` (your colour engine build, unmodified) on the card root as `fwdc239b.bin`, then hold MENU while powering on. If that does not help, use `rollback-filmpack/fwdc239b.bin` the same way. Note whether it stopped before the first photo or after it.

## What was and was not checked

Run on the engine-based bytes (`build-report.json`, `hooks-verification.json`, `adapter-verification.json`, `verification-summary.json`):
- Only the six hook words and the RTOS length differ from the colour engine base; container checksums and round trip; six hooks, {detours} register, flag and stack cases, three deliberate regressions rejected; the linker accepts exactly two bases (the film pack and this colour engine build) and checks, on each, that our six hook sites are byte-identical to the stock firmware's, that the reserved RAM words are unreferenced, the trailer, zero fill and identity.
- {adapter['assertions']} assertions in {len(adapter['checks'])} scenario groups (the same scenarios as stage 2a, on these bytes). Cost of one ordinary UI event: {cost} instructions.
- Other checks: {', '.join(f'{k} {v}' for k, v in counts.items())}.

Not checked: any real camera; whether the colour engine's JPEG-step work (a different task) and our drawing interfere (the memory they use is separate: ours is the UI task's heap); the speed of saving pictures; everything listed for stage 2a.
"""
    (OUT/'README.md').write_text(readme, encoding='utf-8', newline='\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
