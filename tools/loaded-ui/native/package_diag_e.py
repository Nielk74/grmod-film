"""Assemble the stage 1e (diagnostic) delivery folder after link_loaded.py, build-loaded-stage1.ts, check_hooks_loaded.py and
check_diag_e.py have run with LOADED_VARIANT=diage: rollback copy of the exact base, SHA256SUMS.txt, a verification summary, README.md.

  LOADED_VARIANT=diage python native/package_diag_e.py --pack PATH-TO-FILM-PACK --counts "js=38 parity=..."

Never writes anywhere but out/firmware-loaded-stage1e-diagnostic/. No card or camera is accessed.
"""
import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
OUT = LAB/'out'/'firmware-loaded-stage1e-diagnostic'
BUILD = OUT/'build'
PACK_SHA = 'cf04126f5861c3a64123f0cdc95efa5b65443b44aa0ca975854423acf0131f55'
STAGE1_SHA = '5b10170bed7e6aa722b5d80e4187a868c2549e4e0bb648b2763f2f41f9f8ab84'
STAGE1D_SHA = 'd59df016d87decc8f8eb38fd562827688b11b216d0835273decd9444f4284dec'


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
    assert sha(image) not in (STAGE1_SHA, STAGE1D_SHA)
    (OUT/'SHA256SUMS.txt').write_text(f"{sha(image)}  fwdc239b.bin\n{sha(pack)}  rollback/fwdc239b.bin\n", encoding='utf-8', newline='\n')
    summary = dict(image=dict(path=str(OUT/'fwdc239b.bin'), bytes=len(image), sha256=sha(image)), base=dict(sha256=sha(pack), bytes=len(pack)),
                   payloadBytes=manifest['payloadBytes'], rtosGrowth=report['rtosGrowth'], rtosRuntimeEnd=hex(report['rtosRuntimeEnd']),
                   diagAssertions=adapter['assertions'], diagBlockBytes=adapter['diag_block_bytes'], counts=counts)
    (OUT/'verification-summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8', newline='\n')
    detours = hooks['detourCases'] if isinstance(hooks['detourCases'], int) else len(hooks['detourCases'])
    readme = f"""# GR III 2.10: film pack + Loaded stage 1e, DIAGNOSTIC (hardware test)

**DIAGNOSTIC image, not the Loaded experience.** Stage 1d showed that the hook, the film read, every allocation, the view creation and
the first tick succeed on the camera, but that the camera paints our views late or not at all. Stage 1e measures that.

- File: `fwdc239b.bin`, {len(image):,} bytes
- SHA-256: `{sha(image)}`
- Different from stage 1 (`{STAGE1_SHA[:8]}...`) and stage 1d (`{STAGE1D_SHA[:8]}...`); marker string `...LOADED-STAGE1E-DIAGNOSTIC-HARDWARE-UNTESTED` inside the file.
- Same base (film pack `{PACK_SHA}`, kept in `rollback/fwdc239b.bin`), same five hooks, same state word `0x558043b8`, no sound, no settings written. RTOS ends at {hex(report['rtosRuntimeEnd'])}; payload {manifest['payloadBytes']:,} bytes.
- Flashing it keeps the colour engine out (as stage 1d did). Settings are safe: the engine build is this film pack plus a module.

Check the file first (PowerShell): `Get-FileHash .\\fwdc239b.bin -Algorithm SHA256` must print `{sha(image)}`.

## Test card

1. Standard look: take two shots. Photograph the corner of the screen 0.5 s, 2 s and 5 s after the first shot (or film it). Note whether each shot shows the panel and
   whether the coloured test patterns (four boxes: red 1 at the top, green 2 at the bottom, blue 3 at the right, yellow 4 at the left) appear by themselves.
2. A film (Portra 400): take three shots one after the other, waiting for the camera to be ready between shots. Same notes. Note on which shots you had to half press, and how long after the shot.
3. One more Portra 400 shot: do NOT touch anything. Wait 15 seconds and write down what the screen did.
4. On the last shot, half press as soon as you see nothing and photograph the corner right after the half press.
5. Count your shots. The panel's `HOOK` counter (page 5) should equal the number of shots since power-on if the hook fires exactly once per shot. Report both numbers.
6. Report: the panel pages you could photograph (they change every 1.5 s, eight pages, 12 s in all), and what you did and saw.

## The panel (240 x 176 at (464,259), as before), eight pages, one every 1.5 s, about 12 s after each shot

1. Cells (as stage 1d) plus `V A/B/C/D` (the variant of this shot) and `PROOF` while the test patterns show.
2. `V  LV C/K   QV C/K`: per view (1 top, 2 bottom, 3 counter, 4 tab, N the panel): `calls/copied` of `grmod_draw`, split by controller type seen at the call (LV LiveView `0x53b2f9e8`, QV QuickView `0x53b41380`). `calls` is how often the camera asked the view to draw, `copied` how often the pixels were really copied to the screen buffer.
3. `LAST REJECT LV QV`: per view the check that stopped the last draw (0 = copied, `-` = never called). Then the surface the camera gave: `W H STR FMT` (width, visible height, stride, format byte) for LV and QV.
4. `ABS X Y W H PAR`: the absolute rectangle of every view at the last call (the camera's layout result) and whether its parent was the root (1/0); then `NOW` the controller now and its vtable.
5. Events: `HOOK` (never reset; counted before any early return), `RTF H a U b` root not found at the hook / at a timer tick, `LAST VT` the controller vtable low 16 bits seen at the last failure (A000 no app, B000 no model, C000 no controller, E000/E001 root checks), `TRANS B/A` transitions before/after,
   `TICKS` timer ticks, `LATE` ticks later than 100 ms, `STALE` moments found over at their first tick without any Loaded view painted, `SHOT`, `PANEL CALLS` and `FIRST DRAW` (ms from the hook to the first panel draw call), `Pxxxx V x`, `TK1 P a L b` (timer ticks run before the first panel draw / first Loaded copy).
6. Cancels by reason: CLOCK, ROOT, FILM, CREATE, ATTACH, START, TICK, TRANS (menu or unknown destination), CANVAS (canvas deleted), EXT (the release hook, called by the camera on a full-release attempt); `LAST` reason and the hook number; timing of the last shot: `H>R` hook to root found, `H>A` to panel attached, `H>T` to the first timer tick (ms), `CLK` low bits of the clock at the hook.
7. and 8. Log of the last shot, `event controller ms [R reject]`: `HK` hook, `TB`/`TA` transition before/after, `AT` Loaded views attached, `C1..C4` first draw call of each Loaded view (with the reject code), `D1..D4` first successful copy, `PC` first panel call, `XC` cancel (R reason), `RF` root not found, `ST` stale moment, `RA` reattach (R1 re-attached, R0 detached for a tick). Controller letter L, Q or O.

Reject codes: 1 no surface, no root or a transition running; 2 view not on / not attached / Loaded not running; 3 unknown view or no buffer; 4 nothing visible in this view (not dirty); 5 view hidden byte;
6 parent is not the root; 7 surface is not the root's surface; 8 surface format byte is not 5; 9 surface geometry unusable; 10 surface size overflow; 11 rectangle unusable or different from the view's size; 12 clip rectangle unusable; 13 empty intersection.

## The experiments (by hook count modulo 4, shown as `V` on page 1 and page 5)

- Always: on every tick the root, the panel view and the four Loaded views are invalidated (stage 1d invalidated only the root).
- Test patterns: for about one second after cell 9 turns green, the four Loaded buffers hold solid opaque patterns (3 px outline, filled block, the view number) written directly, not by the renderer. If you see them, the view reaches the screen and the renderer is not the problem; if you do not, the draw statistics say why.
- Variant A: plain. Variant B: right after the Loaded views are first attached they are detached for one tick and attached again, as the camera's own transition hooks do (this is the path that showed the strips after your half press). Variant C: the real Loaded moment waits until a Loaded view has been painted (or 6 s), so a late repaint does not find it already over; the patterns stay until then and for one second more. Variant D: both B and C.
- No stronger redraw request was established in the camera code, so none is used (see the report).

## If it gets stuck

Take the battery out for 10 seconds. Put `rollback/fwdc239b.bin` (the unmodified film pack, SHA-256 `{PACK_SHA}`) on the card root as `fwdc239b.bin` and hold MENU while powering on.

## What was and was not checked

Passed in emulation on the delivered bytes ({adapter['assertions']} assertions in {len(adapter['checks'])} scenario groups, `adapter-verification.json`; five hooks {detours} cases and three regressions rejected, `hooks-verification.json`):
all-ok flow with proof patterns on screen through the original canvas draw, then the real moment equal to the JS reference; the four variants; every failure cell of stage 1d again (film read, five allocations, four views, attach, start, first tick, no clock);
counters, cancel reasons, the controller split, the reject codes on a real view object, the log, late and stale ticks, timing fields; suspect B reproduced (a hook before LiveView; one tick on another controller). Other checks: {', '.join(f'{k} {v}' for k, v in counts.items())}.
The Diag block is {adapter['diag_block_bytes']:,} bytes (stage 1d: 169,212; the Terminal block was 172 KB).

Not checked: any real camera; what makes the camera paint late (the point of this test); whether the clock call inside the draw callback is as cheap on the camera as in the timer callback.
"""
    (OUT/'README.md').write_text(readme, encoding='utf-8', newline='\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
