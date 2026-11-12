"""Package stage 1f only after its delivered diagnostic artifacts are verified.

Run link_loaded.py, build-loaded-stage1.ts, check_hooks_loaded.py and
check_diag_f.py with LOADED_VARIANT=diagf first. --counts records additional
operator-supplied suite totals; it does not replace artifact verification.
Only out/firmware-loaded-stage1f-diagnostic is written. No card or camera is
accessed. Verification finishes before rollback, README or summary are written.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
LAB = HERE.parent
ROOT = LAB.parent.parent
OUT = LAB / 'out' / 'firmware-loaded-stage1f-diagnostic'
BUILD = OUT / 'build'
RTOS_BASE = 0x53000000
PACK_SHA = 'cf04126f5861c3a64123f0cdc95efa5b65443b44aa0ca975854423acf0131f55'
STAGE1_SHA = '5b10170bed7e6aa722b5d80e4187a868c2549e4e0bb648b2763f2f41f9f8ab84'
STAGE1D_SHA = 'd59df016d87decc8f8eb38fd562827688b11b216d0835273decd9444f4284dec'
STAGE1E_SHA = '625f5b63488e95e3b96eda1a689a509a774fb4884df28a308e3d17532e573d15'
EXPECTED_HOOKS = {
    'grmod_hook_shot': (0x532D55F8, 'ac4cfdea'),
    'grmod_hook_transition_before': (0x5316CAF8, '33ff2fe1'),
    'grmod_hook_transition_after': (0x5316CB74, '5431d4e5'),
    'grmod_hook_canvas_delete': (0x533918D0, '0dc0a0e1'),
    'grmod_hook_release': (0x53239818, '0dc0a0e1'),
    'grmod_hook_event': (0x53228AB4, 'b020d1e1'),
}
REQUIRED_SOURCE_PATHS = {
    'tools/loaded-ui/native/loaded.c',
    'tools/loaded-ui/native/camera_diag_f.c',
    'tools/loaded-ui/native/hooks_f.S',
    'tools/loaded-ui/native/loaded.h',
    'tools/loaded-ui/native/loaded_data.h',
    'tools/loaded-ui/native/camera_loaded.h',
    'tools/shot-animation/native/camera_clock.c',
    'tools/shot-animation/native/camera_clock.h',
    'tools/shot-animation/native/hooks.S',
    'tools/loaded-ui/native/link_loaded.py',
    'tools/loaded-ui/build-loaded-stage1.ts',
    'tools/loaded-ui/out/firmware-loaded-stage1f-diagnostic/build/loaded_slots.h',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_artifacts(pack, image, report, manifest, adapter, hooks, *, root=ROOT, build=BUILD):
    """Check actual files, not merely agreement between stale reports.

    The builder's image digest binds its section report to the delivered
    container. Linked files and current manifest sources are read independently.
    """
    root, build = Path(root).resolve(), Path(build).resolve()
    pack_sha, image_sha = sha(pack), sha(image)
    require(pack_sha == PACK_SHA, 'base is not the expected film pack')
    require(image_sha == report['outputSha256'] and len(image) == report['outputBytes'],
            'delivered image differs from build report')
    require(image_sha not in (STAGE1_SHA, STAGE1D_SHA, STAGE1E_SHA),
            'delivered image is an earlier diagnostic or stage 1 image')
    for label, data in (('build report', report), ('payload manifest', manifest)):
        require(data['camera'] == 'GR III' and data['baseVersion'] == '2.10'
                and data['stage'] == '1f' and data['silent'] is True
                and data['hardwareTested'] is False and data['packSha256'] == pack_sha,
                f'{label} is not this untested, silent stage 1f film-pack build')
        patches = data['patches']
        require(len(patches) == len(EXPECTED_HOOKS)
                and {p['symbol']: (p['address'], p['expected']) for p in patches} == EXPECTED_HOOKS,
                f'{label} changed the six established hook sites')
    require(report['versionRaised'] is False, 'diagnostic must not raise the firmware version')
    require(report['checks'] and all(value is True for value in report['checks'].values()),
            'build report contains a failed or missing verification')
    sections = [section for section in report['sections'] if section['name'] == 'RTOS']
    require(len(sections) == 1, 'build report must contain exactly one RTOS section')
    section = sections[0]
    require(all(s['beforeSha256'] == s['afterSha256'] and s['beforeBytes'] == s['afterBytes']
                for s in report['sections'] if s['name'] != 'RTOS'),
            'diagnostic changed a section outside RTOS')
    pack_rtos = (build / 'pack-rtos.bin').read_bytes()
    patched_rtos = (build / 'patched-rtos.bin').read_bytes()
    payload = (build / 'loaded-payload.bin').read_bytes()
    elf = (build / 'loaded-payload.elf').read_bytes()
    pack_rtos_sha, patched_rtos_sha = sha(pack_rtos), sha(patched_rtos)
    payload_sha, elf_sha = sha(payload), sha(elf)
    require(pack_rtos_sha == manifest['packRtosSha256'] == hooks['packRtosSha256'] == section['beforeSha256']
            and len(pack_rtos) == manifest['packRtosBytes'] == section['beforeBytes'],
            'base RTOS differs from manifest, build or hook verification')
    require(patched_rtos_sha == section['afterSha256'] == adapter['patched_rtos_sha256']
            == hooks['patchedRtosSha256'] and len(patched_rtos) == section['afterBytes'],
            'actual patched RTOS differs from build or verification reports')
    require(b'LOADED-STAGE1F-DIAGNOSTIC-HARDWARE-UNTESTED' in patched_rtos,
            'actual patched RTOS is missing the stage 1f diagnostic marker')
    require(elf_sha == manifest['elfSha256'] == adapter['payload_elf_sha256'],
            'actual linked ELF differs from manifest or adapter verification')
    require(payload_sha == manifest['payloadSha256'] == hooks['payloadSha256']
            and len(payload) == manifest['payloadBytes'] == report['payloadBytes'],
            'actual payload differs from manifest, build or hook verification')
    payload_offset = manifest['base'] - RTOS_BASE
    require(payload_offset == len(pack_rtos)
            and patched_rtos[payload_offset:payload_offset + len(payload)] == payload,
            'verified payload is not the payload embedded after the film-pack RTOS')
    require(report['rtosRuntimeEnd'] == RTOS_BASE + len(patched_rtos)
            and report['rtosGrowth'] == len(patched_rtos) - len(pack_rtos),
            'RTOS extent differs from build report')
    source_hashes = manifest['sourceHashes']
    require(isinstance(source_hashes, dict) and REQUIRED_SOURCE_PATHS <= source_hashes.keys(),
            'manifest omits required source or generated-header hashes')
    for relative, expected in source_hashes.items():
        source = (root / relative).resolve()
        require(source.is_relative_to(root), f'manifest source is outside the worktree: {relative}')
        require(source.is_file() and sha(source.read_bytes()) == expected,
                f'source changed after linking: {relative}')
    require(adapter['hardware_tested'] is False and hooks['hardwareTested'] is False,
            'verification reports must retain the untested hardware status')
    require(adapter['assertions'] > 0 and adapter['checks'], 'adapter verification has no assertions or scenarios')
    require(hooks['filmPackBytesKept'] is True and hooks['zeroFillClearsStateWord'] is True
            and hooks['heapHeaderPreserved'] is True and hooks['regressionsRejected'],
            'hook verification is incomplete')
    detours = hooks['detourCases']
    require((isinstance(detours, int) and detours > 0) or (isinstance(detours, list) and bool(detours)),
            'hook verification has no detour cases')
    instruction_costs = adapter.get('instruction_costs')
    require(isinstance(instruction_costs, dict) and bool(instruction_costs)
            and all(type(value) is int and value > 0 for value in instruction_costs.values()),
            'adapter verification must include measured hook instruction_costs')
    return dict(imageSha256=image_sha, packSha256=pack_sha,
                patchedRtosSha256=patched_rtos_sha, packRtosSha256=pack_rtos_sha,
                payloadSha256=payload_sha, elfSha256=elf_sha,
                sourceHashes=dict(source_hashes), instructionCosts=dict(instruction_costs))


def render_readme(image, report, manifest, adapter, hooks, counts, bindings):
    detours = hooks['detourCases'] if isinstance(hooks['detourCases'], int) else len(hooks['detourCases'])
    supplied_counts = ', '.join(f'{key}={value}' for key, value in counts.items()) or 'none supplied'
    costs = ', '.join(f'{key}={value}' for key, value in bindings['instructionCosts'].items())
    return f"""# GR III 2.10 — Loaded stage 1f diagnostic reassessment

**DIAGNOSTIC. Hardware untested. This is not the final Loaded experience.**

This image repairs a layout defect reproduced with the original camera code and
improves the observations needed to investigate the remaining delay. It does not
establish that layout was the only cause of the field behavior, or that film
processing takes a particular number of seconds.

## Identify this image

- File: `fwdc239b.bin`, {len(image):,} bytes.
- SHA-256: `{bindings['imageSha256']}`.
- Base and rollback: the same film pack, SHA-256 `{PACK_SHA}`.
- Marker: `LOADED-STAGE1F-DIAGNOSTIC-HARDWARE-UNTESTED`.
- Six existing hook sites are retained. The completion trigger remains image-BE
  completion at `0x532d55f8`; exposure start/end are observations, not new triggers.
- Silent payload: {manifest['payloadBytes']:,} bytes. RTOS runtime end:
  `{hex(report['rtosRuntimeEnd'])}`. The firmware version is not raised.

Check the delivered file in PowerShell before using it:

```powershell
Get-FileHash .\\fwdc239b.bin -Algorithm SHA256
```

The result must equal the SHA-256 above. The exact base is retained at
`rollback/fwdc239b.bin`; `SHA256SUMS.txt` covers both files.

## What changed and what remains unresolved

The original native layout pass leaves a new child at a zero rectangle when its
parent is already clean and receives no layout request. This is a sufficient
reason for rejected draws. Stage 1f now requests layout after attaching the
diagnostic panel and after attaching the four Loaded views, on every shot. Early
Loaded failures can therefore still show their diagnostic panel. There is no
rotating A/B/C experiment.

`CALL` measures the first panel callback attempt. `COPY` separately measures the
first successful native panel copy. A callback can be rejected, and even a
successful memory copy is not proof of when the physical display refreshed.

The release-control hook uses a single-try mailbox gate to publish an observation.
Its lock-free dropped-record counter can retry an atomic update; the entire
callback is not claimed to have a fixed instruction bound. The UI task consumes
the mailbox and owns allocation, table mutation, cancellation, timers and views.
`RL` counts release-control attempts: native rejection and internal retries can
reach it, so it is not a photo count.

The earlier video shows the Standard panel at 12.0 s, before its second
capture-like blackout at 12.4 s. Portra focus illumination begins around 42 s
and 52 s, with the blackouts later. The user also reports that Fn, Up and other
buttons can wake the animation. These observations are consistent with delayed
processing or UI work being serviced after input, but do not identify a unique
cause or make half-press special. This build keeps the existing completion
trigger while collecting evidence to separate these possibilities.

## Test card — record the screen and the button actions

Keep the same camera settings through the comparison and note the Quick Review
setting. Start a continuous video before each attempt. Make the shutter action
visible or audible and note the time of every button press; the remaining-photo
counter alone does not timestamp the shutter.

1. Select **Portra 400** and take one photo. Make no further input for **30 s**.
   Record whether the panel, colored proof boxes and filmstrip appear by
   themselves. If no panel is visible at 30 s, press **Fn once**, note the time,
   then make no further input and film for **another 30 s**. Do not add repeated
   half-presses. If a panel appears late, keep recording until it clears so that
   all its pages can be read.
2. Wait for the panel to clear. Select **Standard** and repeat the same 30 s
   observation. If it still has no panel, optionally use **Up once** at 30 s,
   note that choice and time, then film another 30 s. Wait for the panel to clear.
3. Select **Portra 400** again and take one photo with your normal subsequent
   inputs allowed. Record exactly which inputs you used and when. Keep filming
   through the panel cycle. This comparison tests whether input changes the
   behavior without assuming which button or task is responsible.

Return the continuous recordings and the input times. Note any visible capture
blackout, panel appearance, proof boxes, filmstrip and capture counter change.
An `RL` or `HK` count is not automatically a one-to-one photo identity.

## Read the panel — 17 pages, 1.5 s each

The cycle lasts **25.5 s after HK**. Page indices below are zero based; visible
timing can still depend on camera scheduling. Record the full cycle.

| Page | Contents |
| --- | --- |
| 0 | `DIAG 1F FIX`, step cells and proof state. |
| 1–6 | `EVENTS n/6 AT HK`: frozen 24-row distinct-event table, four two-line rows per page. |
| 7 | `LAST RL>HK OBS MS`: the last three observed attempt-to-hook intervals and attempt-count deltas. |
| 8 | Per-view counts by controller. |
| 9 | Last reject reasons and surface facts. |
| 10 | Absolute rectangles and current controller. |
| 11 | Event counters; separate `CALL` and successful `COPY` timings. |
| 12 | Cancellation reasons. |
| 13–14 | Two parts of the per-shot diagnostic log. |
| 15 | Global event log. |
| 16 | Events captured before the last completion hook. |

The distinct table resets for each consumed `RL` observation window, rather
than reserving rows permanently for startup events. It freezes at `HK`, so later
button input cannot replace the captured window. `OVF` counts observations that
could not get a table row; `BG` is that count from the preceding observation
window. These are not counts of distinct omitted IDs.

Each table row begins with `R` plus all **eight hexadecimal digits** of a native
message, `U` plus **four hexadecimal digits** of a UI event, or a diagnostic
marker. `N` is its count; `F` and `L` are first/last observed offsets in
milliseconds from the window's release observation. These are UI handling
timestamps, not the native producer's occurrence times. `-` means an unavailable
timestamp or time base, including the first time of coalesced release attempts.
`B:SEEN BEFORE RL` means observed in the preceding window.
That window may include the preceding photo's aftermath. `B` does not establish
periodicity; its absence does not establish capture causality.

The readout shows counts up to 99999, then `99K+`, and millisecond offsets up to
99999, then `99S+`. The full 32-bit values remain in RAM. Page 7 explicitly shows
`NO NEW RL` or `UNKNOWN` when an interval cannot be stated, and `MAILBOX DROP`
counts contended observations that could not be published. Its values are
**observation intervals, not exposure duration**.

UI event `0199` is a shared callback envelope. The logger reads a 32-bit native
ID only for the verified bridge receiver vtable `0x53b1f2cc`, after alignment
and null checks on the receiver and payload. Other `0199` callbacks retain their
UI identity; their payload is not decoded as a native message.

The original firmware's message-name decoder and dispatch paths verify:

| Raw native message | Native meaning | Related UI event |
| --- | --- | --- |
| `22441228` | `EVT_SHOOTING_EXPOSURE_START` | `0162` |
| `22440229` | `EVT_SHOOTING_EXPOSURE_END` | `0163` |
| `23480201` | `EVT_IMAGE_BE_COMPLETE` | `016C`, current completion hook |
| `23480603` | `EVT_IMAGE_BE_QUICK_VIEW_READY` | `016B` |
| `23480204` | `EVT_IMAGE_BE_ALL_IMAGE_WRITE_COMPLETE` | Separate native handler |

`HK` therefore does **not** mean all image writes are complete. UI `016C` has
no photo identity in its payload. Since it is queued by the completion path,
its later dispatch need not fall inside the table already frozen at `HK`.

Reject codes remain: 1 missing surface/root or active transition; 2 inactive,
unattached or nonrunning view; 3 unknown view/buffer; 4 no visible pixels;
5 hidden view; 6 wrong parent; 7 wrong surface; 8 wrong format; 9 invalid surface
geometry; 10 surface-size overflow; 11 invalid/mismatched rectangle;
12 invalid clip; 13 empty intersection.

## Verification and limits

Packaging verified the delivered image digest against the build report; the
actual patched RTOS against the build and both check reports; the actual ELF
against the manifest and adapter report; the actual payload against the manifest,
hook report and RTOS contents; and every manifest source hash against current
files. The six hook sites, unchanged non-RTOS sections and exact base are checked.

The adapter report records {adapter['assertions']} assertions in
{len(adapter['checks'])} scenario groups. The hook report records {detours}
detour cases and rejected regression cases. Measured event-hook instruction
counts: {costs}. These sample steady-state execution from the real event
trampoline to its native continuation, with allocator and clock boundaries
stubbed. They are not milliseconds or a camera performance guarantee.
Diagnostic block: {adapter['diag_block_bytes']:,}
bytes. Additional check counts supplied by the build operator: {supplied_counts}.

See `adapter-verification.json`, `hooks-verification.json`,
`verification-summary.json` and `build/payload-manifest.json` for the evidence.
No real camera was tested for this image. The fixtures substitute allocation,
clock/alarm boundaries, controllers and surfaces; they do not establish RTOS
scheduling, cache/DMA behavior, physical display timing, or the reason input
wakes the observed animation. The field test above is still required.

## Rollback

If the camera is stuck, remove the battery for 10 seconds. Restore the supplied
`rollback/fwdc239b.bin` to the card root as `fwdc239b.bin` and hold MENU while
powering on. Its SHA-256 must be `{PACK_SHA}`. This is the same film-pack base,
not an unrelated stock image. Packaging itself never accesses a card or camera.
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pack', type=Path, required=True)
    parser.add_argument('--counts', default='')
    args = parser.parse_args()
    counts = dict(item.split('=', 1) for item in args.counts.split() if '=' in item)
    pack = args.pack.read_bytes()
    image = (OUT / 'fwdc239b.bin').read_bytes()
    report = json.loads((OUT / 'build-report.json').read_text(encoding='utf-8'))
    manifest = json.loads((BUILD / 'payload-manifest.json').read_text(encoding='utf-8'))
    adapter = json.loads((OUT / 'adapter-verification.json').read_text(encoding='utf-8'))
    hooks = json.loads((OUT / 'hooks-verification.json').read_text(encoding='utf-8'))
    bindings = validate_artifacts(pack, image, report, manifest, adapter, hooks)
    summary = dict(schema=2, stage='1f', diagnostic=True, hardwareTested=False,
                   image=dict(path=str(OUT / 'fwdc239b.bin'), bytes=len(image), sha256=bindings['imageSha256']),
                   base=dict(sha256=bindings['packSha256'], bytes=len(pack)),
                   payloadBytes=manifest['payloadBytes'], rtosGrowth=report['rtosGrowth'],
                   rtosRuntimeEnd=hex(report['rtosRuntimeEnd']), diagAssertions=adapter['assertions'],
                   diagBlockBytes=adapter['diag_block_bytes'], counts=counts, bindings=bindings,
                   reportsSha256={name: sha((OUT / name).read_bytes()) for name in
                                  ('build-report.json', 'adapter-verification.json', 'hooks-verification.json')},
                   manifestSha256=sha((BUILD / 'payload-manifest.json').read_bytes()),
                   packageScriptSha256=sha(Path(__file__).read_bytes()))
    readme = render_readme(image, report, manifest, adapter, hooks, counts, bindings)
    (OUT / 'rollback').mkdir(exist_ok=True)
    (OUT / 'rollback' / 'fwdc239b.bin').write_bytes(pack)
    (OUT / 'SHA256SUMS.txt').write_text(
        f"{bindings['imageSha256']}  fwdc239b.bin\n{bindings['packSha256']}  rollback/fwdc239b.bin\n",
        encoding='utf-8', newline='\n')
    (OUT / 'verification-summary.json').write_text(json.dumps(summary, indent=2) + '\n',
                                                   encoding='utf-8', newline='\n')
    (OUT / 'README.md').write_text(readme, encoding='utf-8', newline='\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
