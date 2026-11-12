"""Assemble the stage 1e (diagnostic) delivery folder after link_loaded.py, build-loaded-stage1.ts, check_hooks_loaded.py and
check_diag_f.py have run with LOADED_VARIANT=diagf: rollback copy of the exact base, SHA256SUMS.txt, a verification summary, README.md.

  LOADED_VARIANT=diagf python native/package_diag_f.py --pack PATH-TO-FILM-PACK --counts "js=38 parity=..."

Never writes anywhere but out/firmware-loaded-stage1f-diagnostic/. No card or camera is accessed.
"""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
OUT = LAB/'out'/'firmware-loaded-stage1f-diagnostic'
BUILD = OUT/'build'
PACK_SHA = 'cf04126f5861c3a64123f0cdc95efa5b65443b44aa0ca975854423acf0131f55'
STAGE1_SHA = '5b10170bed7e6aa722b5d80e4187a868c2549e4e0bb648b2763f2f41f9f8ab84'
STAGE1D_SHA = 'd59df016d87decc8f8eb38fd562827688b11b216d0835273decd9444f4284dec'
STAGE1E_SHA = '625f5b63488e95e3b96eda1a689a509a774fb4884df28a308e3d17532e573d15'


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
    assert sha(image) not in (STAGE1_SHA, STAGE1D_SHA, STAGE1E_SHA)
    (OUT/'SHA256SUMS.txt').write_text(f"{sha(image)}  fwdc239b.bin\n{sha(pack)}  rollback/fwdc239b.bin\n", encoding='utf-8', newline='\n')
    summary = dict(image=dict(path=str(OUT/'fwdc239b.bin'), bytes=len(image), sha256=sha(image)), base=dict(sha256=sha(pack), bytes=len(pack)),
                   payloadBytes=manifest['payloadBytes'], rtosGrowth=report['rtosGrowth'], rtosRuntimeEnd=hex(report['rtosRuntimeEnd']),
                   diagAssertions=adapter['assertions'], diagBlockBytes=adapter['diag_block_bytes'], counts=counts)
    (OUT/'verification-summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8', newline='\n')
    detours = hooks['detourCases'] if isinstance(hooks['detourCases'], int) else len(hooks['detourCases'])
    readme = f"""# GR III 2.10: film pack + Loaded stage 1f, DIAGNOSTIC and candidate fix (hardware test)

**DIAGNOSTIC image, not the Loaded experience.** Two field findings from your stage 1e video are built in:
1. The four Loaded views had the rectangle 0,0,0,0 when they were attached on a timer tick, so every draw was rejected (code 11). The cause, reproduced with the camera's own layout code in the emulator:
   a fresh view already carries its own "needs layout" flag, so showing it does not flag the root, and a root that has just been painted never visits it. This image asks the root to lay out its new children (variant A below).
2. For a film look the completion hook this adapter uses fires 15 to 20 s after the photo (the film processing), not at the exposure. This image does not change the trigger; it records every UI event the camera dispatches with the clock,
   to find an earlier one (pages 9 to 12).

- File: `fwdc239b.bin`, {len(image):,} bytes
- SHA-256: `{sha(image)}`
- Different from stage 1 (`{STAGE1_SHA[:8]}...`, which has since been rebuilt with the layout fix, so it is no longer that hash), stage 1d (`{STAGE1D_SHA[:8]}...`) and stage 1e (`{STAGE1E_SHA[:8]}...`); marker string `...LOADED-STAGE1F-DIAGNOSTIC-HARDWARE-UNTESTED`.
- Same base (film pack `{PACK_SHA}`, kept in `rollback/fwdc239b.bin`), no sound, no settings written. **Six hooks this time**: the five of the earlier stages plus a sixth at the first instruction of the UI event dispatcher (`0x53228ab4`, displaced instruction `ldrh r2,[r1]`, replayed). RTOS ends at {hex(report['rtosRuntimeEnd'])}; payload {manifest['payloadBytes']:,} bytes.
- Flashing it keeps the colour engine out (as before). Settings are safe: the engine build is this film pack plus a module.

Check the file first (PowerShell): `Get-FileHash .\\fwdc239b.bin -Algorithm SHA256` must print `{sha(image)}`.

## Variants (by hook count: 1, 4, 7 ... A; 2, 5, 8 ... B; 3, 6, 9 ... C; shown as `V A/B/C` on page 1)

- A: the Loaded steps run on timer ticks (as in 1d and 1e) and, after the four views are attached, the root is asked to lay out its new children (the candidate fix).
- B: the Loaded steps up to the attach run inside the hook with the panel, with no layout request (the "attach in the hook" idea; the emulator says the views keep 0,0,0,0).
- C: stage 1e's behaviour, timer ticks and no request (the control).
Expected if the analysis is right: in A the proof patterns (red 1 top, green 2 bottom, blue 3 counter, yellow 4 tab) and then the strips appear by themselves; B and C behave like 1e (page 4 `ABS` rows `0 0 0 0`, page 3 reject 11) unless the camera happens to lay out the tree itself.

## Test card (keep the camera on, film the screen for the whole of each step)

1. Portra 400, ONE photo, no half press afterwards, touch nothing for 30 s. Film the screen for the whole 30 s and note the time of the shutter press. The panel appears when the completion hook fires (about 15 to 20 s for a film) and stays 21 s.
2. Standard look, ONE photo, same: nothing touched for 30 s, filmed.
3. Portra 400, a normal shot: half press, then full press (and release), then wait 30 s, filmed.
4. When a panel is up, photograph pages 9, 10, 11 and 12 (the table) each time they come round (each page shows for 1.5 s, the cycle is 21 s). Also page 5 (`HOOK`) once.
5. Report the video and the photos, the number of photos taken against the `HOOK` counter, and which variant (A, B, C) each photo had.

## The panel, fourteen pages of 1.5 s, about 21 s after each hook

Pages 1 to 8 are those of stage 1e (cells and variant, per-view draw counts by controller type, last reject and surface, absolute rectangles, event counters, cancels and timing, the log of the last shot, second part). Reject codes: 1 no surface, root or transition running; 2 view not on / not attached / Loaded not running; 3 unknown view or no buffer;
4 nothing visible in this view; 5 view hidden; 6 parent is not the root; 7 surface is not the root's; 8 surface format is not 5; 9 surface geometry unusable; 10 surface size overflow; 11 rectangle unusable or different from the view's size; 12 clip unusable; 13 empty intersection.

**Pages 9, 10 and 11: what happened after the shutter.** One row per distinct id: the UI event ids the camera dispatches (4 hex digits), plus the synthetic kinds `RL` (shutter release hook), `HK` (completion hook), `TB` / `TA` (transition before / after). Up to 24 rows (`ROWS` and `OVF` at the foot of each page: ids beyond 24 are counted, not shown).
Columns: `ID`, `FIRST` the time of the first occurrence after the most recent RL (seconds since that RL, one decimal), `LAST` the time of the last occurrence (seconds since that RL), `N` how many times since that RL, and a `!` at the end of the row if the same id also occurred between the previous HK and this RL (so a `!` row is periodic, not tied to a photo).
Rows are sorted by FIRST, eight per page (1/3, 2/3, 3/3). The per-RL fields are reset at every RL; an id that fires every 33 ms still takes one row. Ids that did not occur since the last RL are not shown.
**Page 12: RL to HK** for the last three photos (the delay between the shutter release hook and the completion hook, `NO RL` if no release happened since the previous hook), and the RL and HK counts. The shots-left counter is not shown: I did not find where it is stored.
Pages 13 and 14 are the raw log: the last 8 global events with the time since the previous one, and the 8 events before the last hook.

## Who writes the log (the design note)

- The block (a 170 KB buffer, the same kind as the panel's) is allocated by the UI-event hook on the first UI event it sees, once; if the allocation fails a spare RAM word is set and the hook never tries again. The shot hook still allocates it if it does not exist yet, as before.
- The shutter release hook runs in a task that is not identified, so it never allocates. With no block it does nothing. With a block it writes only its own lane: an atomic increment of `rl_count`, the clock into `rl_time`, and one ring entry (the ring index is claimed with an atomic increment, so UI-task and release-hook entries cannot overwrite each other). It still cancels a running shot, as every stage has.
- The distinct-id table has one writer, the UI-task callbacks (event hook, transition hooks, shot hook); the release lane is folded into it on the next UI-task callback. The other hooks do nothing until the first photo.
- Cost: measured in the emulator through the real trampoline and the real dispatcher, one dispatched event costs about 130 to 160 instructions (trampoline included, clock read included); the worst case, a full table and an id not in it, about 280 in the callback. Events that arrive faster than 500 ms for many different ids: the table counts all of them (24 rows, overflow counted), the ring takes one entry per id and 500 ms, per 16 id slots, and is bounded (160 entries, it wraps).

## If it gets stuck

Take the battery out for 10 seconds. Put `rollback/fwdc239b.bin` (the unmodified film pack, SHA-256 `{PACK_SHA}`) on the card root as `fwdc239b.bin` and hold MENU while powering on.

## What was and was not checked

Passed in emulation on the delivered bytes ({adapter['assertions']} assertions in {len(adapter['checks'])} scenario groups, `adapter-verification.json`; six hooks {detours} cases including the new one, and three regressions rejected, `hooks-verification.json`).
Layout reproduced and fixed with the original native layout pass; all earlier 1e scenarios (flows, failure cells, counters, reject codes, draw statistics) plus the global log, the release hook creating the block, the sixth hook and the pre-hook snapshot. Other checks: {', '.join(f'{k} {v}' for k, v in counts.items())}.
Diag block {adapter['diag_block_bytes']:,} bytes.

Not checked: any real camera; whether the camera lays the tree out itself after the hook (the panel works at the hook on the camera, which suggests it does); what the UI events mean (that is what this test collects); whether allocating the block from the UI-event hook at the first event is safe that early (the UI task has run by then, nothing else is touched at that moment); the shots-left counter.
"""
    (OUT/'README.md').write_text(readme, encoding='utf-8', newline='\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
