"""Assemble the stage 1e (diagnostic) delivery folder after link_loaded.py, build-loaded-stage1.ts, check_hooks_loaded.py and
check_diag_g.py have run with LOADED_VARIANT=diagg: rollback copy of the exact base, SHA256SUMS.txt, a verification summary, README.md.

  LOADED_VARIANT=diagg python native/package_diag_g.py --pack PATH-TO-FILM-PACK --counts "js=38 parity=..."

Never writes anywhere but out/firmware-loaded-stage1g-diagnostic/. No card or camera is accessed.
"""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
OUT = LAB/'out'/'firmware-loaded-stage1g-diagnostic'
BUILD = OUT/'build'
PACK_SHA = 'cf04126f5861c3a64123f0cdc95efa5b65443b44aa0ca975854423acf0131f55'
STAGE1_SHA = '5b10170bed7e6aa722b5d80e4187a868c2549e4e0bb648b2763f2f41f9f8ab84'
STAGE1D_SHA = 'd59df016d87decc8f8eb38fd562827688b11b216d0835273decd9444f4284dec'
STAGE1E_SHA = '625f5b63488e95e3b96eda1a689a509a774fb4884df28a308e3d17532e573d15'
STAGE1F_SHA = '4299ffeb6f34b5630a837d681cb33a1e36783f32e56dfa62b35fc7e1b756e388'


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
    assert sha(image) not in (STAGE1_SHA, STAGE1D_SHA, STAGE1E_SHA, STAGE1F_SHA)
    (OUT/'SHA256SUMS.txt').write_text(f"{sha(image)}  fwdc239b.bin\n{sha(pack)}  rollback/fwdc239b.bin\n", encoding='utf-8', newline='\n')
    summary = dict(image=dict(path=str(OUT/'fwdc239b.bin'), bytes=len(image), sha256=sha(image)), base=dict(sha256=sha(pack), bytes=len(pack)),
                   payloadBytes=manifest['payloadBytes'], rtosGrowth=report['rtosGrowth'], rtosRuntimeEnd=hex(report['rtosRuntimeEnd']),
                   diagAssertions=adapter['assertions'], diagBlockBytes=adapter['diag_block_bytes'], counts=counts)
    (OUT/'verification-summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8', newline='\n')
    detours = hooks['detourCases'] if isinstance(hooks['detourCases'], int) else len(hooks['detourCases'])
    readme = f"""# GR III 2.10: film pack + Loaded stage 1g, DIAGNOSTIC (hardware test)

**DIAGNOSTIC image, not the Loaded experience.** Stage 1f showed that the layout fix works (the proof patterns and the real strips, tab and counter drew) and that, for a film look, the completion hook fires about 19 s after the shutter.
It also showed that the event log did not exist yet when the shutter was pressed, so nothing was recorded between the press and the hook. This image makes the log exist from about 20 s after power-on, before any shutter, and answers: which UI events happen between the press and the completion hook?

- File: `fwdc239b.bin`, {len(image):,} bytes
- SHA-256: `{sha(image)}`
- Different from stage 1 (`{STAGE1_SHA[:8]}...`, since rebuilt with the layout fix), 1d (`{STAGE1D_SHA[:8]}...`), 1e (`{STAGE1E_SHA[:8]}...`) and 1f (`{STAGE1F_SHA[:8]}...`); marker string `...LOADED-STAGE1G-DIAGNOSTIC-HARDWARE-UNTESTED`.
- Same base (film pack `{PACK_SHA}`, kept in `rollback/fwdc239b.bin`), no sound, no settings written. Six hooks: the five of the earlier stages plus the one at the first instruction of the UI event dispatcher (`0x53228ab4`). RTOS ends at {hex(report['rtosRuntimeEnd'])}; payload {manifest['payloadBytes']:,} bytes.

**Colour engine caveat.** Your camera may currently run the colour engine build; flashing this image removes it until a rebased image exists (the engine build is the same film pack plus a different module, so saved settings are safe). To go back, flash the engine file again (SHA-256 begins `3367220a`).

Check the file first (PowerShell): `Get-FileHash .\\fwdc239b.bin -Algorithm SHA256` must print `{sha(image)}`.

## What changed since 1f

1. Variant A only (timer ticks plus the layout request) for every photo. The proof patterns still show for one second before the real strips.
2. **How the log block is allocated.** The UI-event hook counts UI events in a spare zero-filled RAM word (`0x55804390`) while no block exists (a handful of instructions, no clock read, no allocation).
   When the count reaches 5000 (about 20 s at the 250 events per second you measured) AND the OS clock (`grmod_clock_ms`, the same call the shot hook uses) reads 20 s or more, the next UI event allocates the block, once, on the UI task.
   A failure sets a second spare word (`0x5580438c`) and is never retried. The shutter release hook only raises the count to the threshold (a late boot cannot lose arming); it allocates nothing. The shot hook still allocates the block if it does not exist yet, as in every stage.
   Why it is safe at that moment: by 20 s of uptime the camera is up and the UI task has been running its normal allocations for most of that time; the allocation is one request of the size the panel's buffer already has (the same native allocator call, from the same task, as the shot hook makes); nothing else is touched.
   What I could not verify: the clock being time since power-on (the owner's readings fit, but the code only shows it is the OS time getter), so the count threshold is there as well: the block is made when both hold.
3. Each distinct event id keeps the time and the first parameter word (`event+4`: the dispatcher itself reads `+4` and `+8` of every event, so the event is at least 12 bytes; nothing past it is read) of its last four occurrences. 32 ids fit; ids beyond that are counted in `OVF`.
4. **Pages 9 and 10 replace the old "before last hook" page**: every event id that occurred at most 3 times in the window before the current hook, with its time relative to the hook in ms (negative), its count, and its first parameter. The window is the time since the previous hook but never less than the last 25 s
   (so a Standard photo 0.5 s earlier still gives 25 s); at the first hook since the block exists it starts at the block's allocation. Ids that occurred 4 or more times in the window (periodic ones) are not listed but counted (`PER`). Up to 19 rows over the two pages, earliest first, `REST n` for the ones that did not fit.

## The panel: 16 pages of 1.5 s, 24 s after each hook (it was 21 s)

Pages 1 to 8 are unchanged (cells, per-view draw counts by controller type, last reject and surface, absolute rectangles, event counters, cancels and timing, the log of the last shot).
Page 9 and 10: `ID PARAM -MS N`, the window above (`ID` 4 hex digits or `RL` `HK` `TB` `TA`; `PARAM` the low 16 bits of the first parameter word; `-MS` the age at the hook; `N` the count). Page 10 ends with `REST` (ids that did not fit), `PER` (periodic ids left out) and `W` (the window in seconds).
Pages 11 to 14: the distinct-id table since the last release (`ID FIRST LAST N !`, `!` = seen between the previous hook and that release), 8 rows per page, up to 32 rows, `ROWS`, `OVF` and the release count at the foot.
Page 15: RL to HK for the last three photos (`NO RL` if the log did not exist at the release). Page 16: the raw log, the last 8 events with the time between them.

## Test card

1. Power on. Leave the camera idle for at least 30 s (the log block is made at about 20 s, nothing to do for it).
2. Film the screen. Take ONE Portra 400 photo and do NOT half press afterwards. Say out loud when the shutter was pressed (or note the video time).
3. Wait for the panel (about 19 s later) and photograph pages 9 and 10 (the window before the hook) and, if you can, pages 11 to 15. Each page shows for 1.5 s; the cycle is 24 s, so you can film it.
4. Repeat once with the Standard look (power on again is not needed): one photo, filmed, pages 9 and 10 photographed.
5. Report the video, the shutter times, and the `HOOK` count (page 5) against the number of photos.

## If it gets stuck

Take the battery out for 10 seconds. Put `rollback/fwdc239b.bin` (the unmodified film pack, SHA-256 `{PACK_SHA}`) on the card root as `fwdc239b.bin` and hold MENU while powering on.

## What was and was not checked

Passed in emulation on the delivered bytes ({adapter['assertions']} assertions in {len(adapter['checks'])} scenario groups, `adapter-verification.json`; six hooks {detours} cases and three regressions rejected, `hooks-verification.json`): the allocation rule (count and clock, release raising the count, failure remembered), the event count path, variant A on a clean root for every hook,
the table with parameters and four times per id, the window snapshot (at most three, relative ages, 25 s minimum after a hook 0.5 s earlier, allocation start at the first hook, periodic ids counted, the earliest 24 rows kept), and all the earlier scenarios. Other checks: {', '.join(f'{k} {v}' for k, v in counts.items())}.
Diag block {adapter['diag_block_bytes']:,} bytes.

Not checked: any real camera; the clock's origin; whether the allocation at about 20 s is safe on hardware (the shot hook has always allocated the same buffer); what the UI events mean (that is what this test collects); the shots-left counter (source not found).
"""
    (OUT/'README.md').write_text(readme, encoding='utf-8', newline='\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
