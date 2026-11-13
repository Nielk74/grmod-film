"""Assemble a stage 4b (tier 2 hardware proof) delivery folder after link_loaded.py, build-loaded-stage1.ts, check_hooks_loaded.py and check_stage4b.py have run with
LOADED_VARIANT=stage4btier2engine (colour engine base) or stage4btier2filmpack (film pack base): rollback copy of the exact base, SHA256SUMS.txt,
a verification summary, README.md.

  LOADED_VARIANT=stage4btier2engine python native/package_stage4b.py --pack PATH-TO-BASE --counts "js=38 parity=..."

Never writes anywhere but out/firmware-loaded-stage4b-tier2-engine/ or out/firmware-loaded-stage4b-tier2-filmpack/. No card or camera is accessed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
VARIANT = os.environ.get('LOADED_VARIANT', '')
ENGINE = VARIANT == 'stage4btier2engine'
OUT = LAB/'out'/('firmware-loaded-stage4b-tier2-engine' if ENGINE else 'firmware-loaded-stage4b-tier2-filmpack')
BUILD = OUT/'build'
ENGINE_SHA = '3367220a951724908c06128cf70c39dc5587ff3ca6e52b2a417d071e5a558ebe'
FILMPACK_SHA = 'cf04126f5861c3a64123f0cdc95efa5b65443b44aa0ca975854423acf0131f55'
BASE_SHA = ENGINE_SHA if ENGINE else FILMPACK_SHA


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pack', type=Path, required=True)
    ap.add_argument('--counts', default='')
    ap.add_argument('--earlier', default='', help='earlier image hashes, name=hash pairs')
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
                   adapterAssertions=adapter['assertions'], costInstructions=cost, counts=counts)
    (OUT/'verification-summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8', newline='\n')
    detours = hooks['detourCases'] if isinstance(hooks['detourCases'], int) else len(hooks['detourCases'])
    earlier_text = ', '.join(f"{k} `{v[:8]}...`" for k, v in earlier.items())
    base_text = (f"the colour engine build `{ENGINE_SHA}` ({len(pack):,} bytes: the film pack plus the per-film 3D colour tables), read only, never modified. "
                 "Your colour engine looks are kept. The rollback is that same unmodified file." if ENGINE else
                 f"the plain film pack `{FILMPACK_SHA}` ({len(pack):,} bytes). **The colour engine is not in this image** (this is the film-pack twin of the engine image from the same sources): flashing it removes the colour engine until you flash the engine image again. Settings are safe: the engine build is the film pack plus a module.")
    readme = f"""# GR III 2.10: {'colour engine' if ENGINE else 'film pack'} + Loaded stage 4b, TIER 2 HARDWARE PROOF (diagnostic)

Stage 4a (Loaded exactly as it worked on your camera) plus **a one-off hardware test of the full-screen (720x480) view** that the contact sheet needs. This is a diagnostic, not a feature.
Experimental image: it has only run in an emulator.

## WARNING: read this first

**The full-screen test is the first thing in this project that may stall, freeze or glitch the camera.** Nothing in tier 2 has ever run on a camera. The test asks the firmware for blocks up to
1.4 MB, attaches a full-screen view to the live view and draws it, and the camera could stall (a freeze on the live view, a blank screen, a restart). Nothing is written to the card or to the camera's
settings, so a battery pull and the rollback below always recover it. Do this test with the card out of anything you care about being mid-write (take no photo while the test runs).
The test runs once per power-on, only after the SECOND photo you take, and it stops by itself within about 20 s, or at once if you open a menu or play back.

- Size: {len(image):,} bytes
- SHA-256: `{sha(image)}`
- Base: {base_text}
- Rollback: `rollback/fwdc239b.bin` (SHA-256 `{sha(pack)}`).
- Different from the earlier images ({earlier_text}); marker string `...LOADED-STAGE4B-TIER2-DIAGNOSTIC-HARDWARE-UNTESTED` inside the file.
- Six hooks, the same six as before. Only those six words and the RTOS length differ from the base. No sound, nothing written. RTOS ends at {hex(report['rtosRuntimeEnd'])}; payload {manifest['payloadBytes']:,} bytes.

Check the file first (PowerShell): `Get-FileHash .\\fwdc239b.bin -Algorithm SHA256` must print `{sha(image)}`.

## What the test does (once per power-on, after your second accepted photo, when its strips are over)

Every step is logged green (OK) or red (FAIL with a reason); after a failure the following steps are skipped (the clean-up still runs). The results appear as pages in a small panel in the same
style as the earlier diagnostics (about 1.5 s per page, then a verdict page that stays until the test is over):

1. **S1 allocation probes:** 64 KB, 128 KB, 176 KB, 256 KB, 512 KB, 1 MB, 1.4 MB, each allocated and freed at once, stopping at the first refusal. From the allocator's code a request that does not fit
   returns null (no assertion, no wait), so the large probes are in this image as a normal step. They are the part I cannot prove harmless without a camera: while a 1.4 MB block is held (microseconds) another task asking the pool for
   memory could be refused. If you prefer not to risk it, ask for a variant without the 1 MB and 1.4 MB probes.
2. **S2 alternative memory:** skipped on purpose. I found no pool that is ours to use; see `notes/tier2-feasibility.md`.
3. **S3 views:** a 360x240 view, then a 720x480 view, each attached at 0,0 with the layout request, drawn with a test pattern (grid, colour bars, a frame counter); it logs whether the layout rectangle was accepted and the first draw time in ms (OS clock).
4. **S4 banded draw (design B):** the same full-screen view drawn in 16-row bands through the copier, no big buffer, for 30 frames: the milliseconds per frame, and the number of UI events per second during the test against before it (does the live view keep updating).
5. **S5 clean-up:** every test view removed, the live view and the normal Loaded views return, and the free counters are compared (no leak).

The test never starts when its first allocation fails, never runs twice in one power-on, and is cancelled by any transition (menu, playback) or by a photo.

## Test card (film the screen)

1. Power on. Wait 30 s with the camera idle (the Loaded tab and counter sit there as in 4a).
2. Take **two photos**, a few seconds apart. After the second photo's strips finish, the test starts.
3. Film the screen the whole time and photograph or film every result page (S1 to the verdict).
4. During the test **half-press the shutter once** to see if the autofocus still responds (do not take a photo: it would cancel the test).
5. Tell me: whether the live view flickered, froze or tore (especially during S3 and S4), whether the camera kept responding, whether the test pattern showed on the screen (colour bars at the top, a grid, a frame counter in the middle),
   what each page said, and whether the normal tab and counter returned afterwards.

## If it gets stuck

Take the battery out for 10 seconds. Put `rollback/fwdc239b.bin` on the card root as `fwdc239b.bin`, then hold MENU while powering on. Note which step was showing when it stopped.

## What was and was not checked

Run on the delivered bytes (`build-report.json`, `hooks-verification.json`, `adapter-verification.json`, `verification-summary.json`):
- Only the six hook words and the RTOS length differ from the base; container checksums and round trip; six hooks, {detours} register, flag and stack cases, three deliberate regressions rejected; the linker accepts only the film pack and the colour engine build.
- {adapter['assertions']} assertions in {len(adapter['checks'])} scenario groups: everything of stage 4a (with the proof disabled), plus the proof: the trigger (second accepted photo only), every step and its pages, the pixels of the buffered and the banded draws, refusals of 1 MB / 512 KB / the proof block / a view, no leak, cancellation by a transition or a photo, no second run, and the cost.
- Other checks: {', '.join(f'{k} {v}' for k, v in counts.items())}.

Not checked: any real camera; whether the pool has 1.4 MB free; the frame time of a banded full-screen draw (emulator cost only); how the display combines a full-screen canvas with the live view; what the camera does with a layout request for a view this size.
"""
    (OUT/'README.md').write_text(readme, encoding='utf-8', newline='\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
