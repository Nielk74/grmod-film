"""Link the Loaded stage 1 module on top of one exact GR III 2.10 film pack image.

Same method and same hook sites as tools/shot-animation/native/link_firmware_filmpack.py (the silent Terminal
build that ran on a camera on 2026-11-05): the film pack stays whole, the payload is appended after its RTOS, five
hook words change, nothing else. Loaded replaces Terminal; there is no artwork, sound or audio code.

The film pack to build on is an argument; its SHA-256 must be the expected one (default: the 2026-11-02 pack).
No camera or card is accessed.
"""
import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
LAB = HERE.parent
ROOT = LAB.parent.parent
MAIN = ROOT.parents[2]                     # the main checkout (read-only for this work)
NATIVE_TERMINAL = ROOT/'tools'/'shot-animation'/'native'
sys.path.insert(0, str(NATIVE_TERMINAL))
import link_firmware as official  # noqa: E402  SERVICES, PATCHES, NATIVE_SYMBOLS
import link_firmware_filmpack as pack_tools  # noqa: E402  decode_container, rtos_of, check_pack, flatten

import os  # noqa: E402
VARIANT = os.environ.get('LOADED_VARIANT', '')
DIAG = VARIANT in ('diag', 'diage', 'diagf', 'diagg')      # stage 1d / 1e: the diagnostic adapters, their own folder and marker
OUT = LAB/'out'/{'diag': 'firmware-loaded-stage1d-diagnostic', 'diage': 'firmware-loaded-stage1e-diagnostic', 'diagf': 'firmware-loaded-stage1f-diagnostic', 'diagg': 'firmware-loaded-stage1g-diagnostic', 'stage2a': 'firmware-loaded-stage2a'}.get(VARIANT, 'firmware-loaded-stage1')
ADAPTER = {'diag': 'camera_diag.c', 'diage': 'camera_diag_e.c', 'diagf': 'camera_diag_f.c', 'diagg': 'camera_diag_g.c', 'stage2a': 'camera_loaded2.c'}.get(VARIANT, 'camera_loaded.c')
BUILD = OUT/'build'
EXPECTED_PACK_SHA256 = 'cf04126f5861c3a64123f0cdc95efa5b65443b44aa0ca975854423acf0131f55'
sha = pack_tools.sha
RTOS_BASE = pack_tools.RTOS_BASE
FIRST_FILM_LOOK = 64
# Where the film pack's builder (core/src/fw/gr3x/image-control-research.ts, look-resources.ts) puts the film names:
#  - the camera's name lookup 0x532a985c is hooked: its first word becomes a branch to a stub made of one
#    `cmp r1,#look; movweq r0,#textId; bxeq lr` triple per film (look = 64 + slot), then `mov ip,sp; b 0x532a9860`;
#  - the text directory (one row of text pointers per language) is moved: its address is patched into the two
#    movw/movt pairs at TEXT_ROOT_SITES; row 1 is English; a text record is {u8 units + 1, 1, 0, 0, u32 pointer} and the
#    pointer addresses UTF-16LE characters.
NAME_LOOKUP = 0x532a985c
TEXT_ROOT_SITES = [(0x533966e8, 0x533966f0), (0x533970fc, 0x53397100)]
ENGLISH_ROW = 1


def read_slot_names(rtos):
    def u32(va):
        at = va-RTOS_BASE
        if not 0 <= at <= len(rtos)-4:
            raise ValueError(f'address {va:#x} is outside the RTOS image')
        return struct.unpack_from('<I', rtos, at)[0]

    def immediate(low, high):
        if (low & 0x0ff00000) != 0x03000000 or (high & 0x0ff00000) != 0x03400000:
            raise ValueError('text directory address is not a movw/movt pair')
        return ((((high >> 4) & 0xf000) | (high & 0xfff)) << 16) | (((low >> 4) & 0xf000) | (low & 0xfff))
    roots = {immediate(u32(lo), u32(hi)) for lo, hi in TEXT_ROOT_SITES}
    if len(roots) != 1:
        raise ValueError('the two text directory sites disagree')
    directory = roots.pop()
    row = u32(directory+4*ENGLISH_ROW)
    entry = u32(NAME_LOOKUP)
    if (entry & 0xff000000) != 0xea000000:
        raise ValueError('the name lookup is not hooked: this is not a film pack')
    offset = entry & 0xffffff
    if offset & 0x800000:
        offset -= 0x1000000
    at = NAME_LOOKUP+8+offset*4
    slots = []
    while True:
        compare = u32(at)
        if (compare & 0xfffff000) != 0xe3510000 or compare & 0xf00:
            break
        move, bx = u32(at+4), u32(at+8)
        if (move & 0x0ff0f000) != 0x03000000 or bx != 0x012fff1e:
            raise ValueError(f'unexpected name lookup stub word at {at+4:#x}')
        look, text = compare & 0xff, ((move >> 4) & 0xf000) | (move & 0xfff)
        if look != FIRST_FILM_LOOK+len(slots):
            raise ValueError(f'film looks must be consecutive from {FIRST_FILM_LOOK}: got {look}')
        record = u32(row+4*text)
        units, pointer = (rtos[record-RTOS_BASE], u32(record+4))
        raw = rtos[pointer-RTOS_BASE:pointer-RTOS_BASE+2*(units-1)]
        slots.append(dict(slot=len(slots), look=look, textId=text, name=raw.decode('utf-16-le')))
        at += 12
    if not 1 <= len(slots) <= 20:
        raise ValueError(f'expected 1..20 film slots in the name lookup, found {len(slots)}')
    if u32(at) != 0xe1a0c00d or (u32(at+4) & 0xff000000) != 0xea000000:
        raise ValueError('name lookup stub does not end with the displaced native instruction')
    return slots


def match_slots(names, films):
    """Give every film pack slot its Loaded film by name; refuse the base when a slot has none (no silent neutral strip)."""
    table = {name: index for index, name in films}
    unmatched = [slot for slot in names if slot['name'] not in table]
    if unmatched:
        raise ValueError('No Loaded film for film pack slot(s): ' + ', '.join(f"{x['slot']} ({x['name']!r}, look {x['look']})" for x in unmatched))
    for slot in names:
        slot['film'] = table[slot['name']]
        slot['loadedName'] = slot['name']


def loaded_films():
    out = subprocess.run(['node', '-e', "import('./src/films.mjs').then(m=>console.log(JSON.stringify(m.FILMS.map(f=>[f.index,f.name]))))"],
                         capture_output=True, text=True, check=True, cwd=str(LAB))
    return json.loads(out.stdout)


def build(args):
    BUILD.mkdir(parents=True, exist_ok=True)
    pack_file = args.pack.read_bytes()
    if sha(pack_file) != args.pack_sha256:
        raise ValueError(f'Refusing this base: SHA-256 {sha(pack_file)} is not the expected film pack {args.pack_sha256}')
    stock = args.stock_rtos.read_bytes()
    if sha(stock) != official.RTOS_HASH:
        raise ValueError('Official reference RTOS changed')
    pack = pack_tools.rtos_of(pack_tools.decode_container(pack_file))
    patches, native = pack_tools.PATCHES, pack_tools.NATIVE_SYMBOLS
    if VARIANT in ('diagf', 'diagg', 'stage2a'):       # a sixth hook, stage 1f only: the UI event dispatcher's first instruction
        at = 0x53228AB4 - RTOS_BASE
        patches = [*patches, dict(address=0x53228AB4, expected=pack[at:at+4].hex(), symbol='grmod_hook_event', link=False,
                                  reason='Log every UI event the camera dispatches (stage 1f diagnostic)')]
        native = {**native, 'native_event_resume': 0x53228AB8, 'grmod_alloc_flag': 0x5580438C, 'grmod_armed_flag': 0x55804390}
    pack_tools.check_pack(pack, stock, patches)
    base = pack_tools.RTOS_BASE + len(pack)
    # The slot-to-film table comes from the names in THIS image; a slot without a Loaded film refuses the base.
    names = read_slot_names(pack)
    match_slots(names, loaded_films())
    header = ['/* Generated by link_loaded.py from the names in the base image. Do not edit. */', '#ifndef LOADED_SLOTS_H', '#define LOADED_SLOTS_H',
              f'#define LD_SLOTS {len(names)}u',
              'static const uint8_t ld_film_of_slot[LD_SLOTS] = { ' + ', '.join(str(x['film']) for x in names) + ' };', '#endif', '']
    (BUILD/'loaded_slots.h').write_text(chr(10).join(header), encoding='utf-8', newline=chr(10))
    assembly = ['.syntax unified', '.arm', '.section .grmod_assets,"a",%progbits', '.balign 4',
                '.global grmod_audio_shutdown_latch', 'grmod_audio_shutdown_latch:', '.word 1',
                '.section .note.GNU-stack,"",%progbits', '']
    (BUILD/'assets.S').write_text('\n'.join(assembly), encoding='utf-8', newline='\n')
    linker = f'''ENTRY(grmod_hook_shot)
PHDRS {{ image PT_LOAD FLAGS(5); }}
SECTIONS {{
  . = 0x{base:x};
  .text : {{ KEEP(*(.text.grmod_hooks)) *(.text .text.*) }} :image
  .rodata ALIGN(16) : {{ *(.rodata .rodata.*) }} :image
  .grmod_assets ALIGN(16) : {{ KEEP(*(.grmod_assets)) }} :image
  .data ALIGN(4) : {{ *(.data .data.*) }} :image
  .bss : {{ *(.bss .bss.*) *(COMMON) }} :image
  ASSERT(SIZEOF(.data) == 0, "mutable RTOS data forbidden")
  ASSERT(SIZEOF(.bss) == 0, "mutable RTOS BSS forbidden")
  /DISCARD/ : {{ *(.ARM.exidx* .ARM.extab*) *(.comment) *(.note*) }}
}}
'''
    (BUILD/'loaded.ld').write_text(linker, encoding='utf-8', newline='\n')
    flags = ['-target', 'armv7-none-eabi', '-mcpu=cortex-a9', '-marm', '-mfloat-abi=soft', '-mfpu=none',
             '-Os', '-ffreestanding', '-fno-builtin', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables',
             '-fno-stack-protector', '-fno-common', '-fdata-sections', '-ffunction-sections', '-Wall', '-Wextra', '-Werror']
    sources = [HERE/'loaded.c', HERE/ADAPTER, NATIVE_TERMINAL/'camera_clock.c', NATIVE_TERMINAL/'hooks.S',
               *([HERE/'hooks_f.S'] if VARIANT in ('diagf', 'diagg', 'stage2a') else []), BUILD/'assets.S']
    objects = []
    for source in sources:
        target = BUILD/(source.stem+'.o')
        subprocess.run([args.clang, *flags, '-I', str(BUILD), '-c', str(source), '-o', str(target)], check=True)
        objects.append(str(target))
    elf_path = BUILD/'loaded-payload.elf'
    subprocess.run([args.lld, '-T', str(BUILD/'loaded.ld'), '--no-undefined',
                    *('--defsym='+name+'='+hex(address) for name, address in native.items()),
                    *objects, '-o', str(elf_path)], check=True)
    payload, symbols = pack_tools.flatten(elf_path, base, native)
    (BUILD/'loaded-payload.bin').write_bytes(payload)
    latch = symbols['grmod_audio_shutdown_latch']
    if payload[latch-base:latch-base+4] != struct.pack('<I', 1):
        raise ValueError('The audio latch must be a read-only word holding 1')
    headers = [HERE/'loaded.h', HERE/'loaded_data.h', HERE/'camera_loaded.h', NATIVE_TERMINAL/'camera_clock.h', BUILD/'loaded_slots.h']
    source_paths = [*sources[:-1], *headers, Path(__file__), LAB/'build-loaded-stage1.ts']
    manifest = dict(schema=1, camera='GR III', baseVersion='2.10', silent=True, stage={'diag': '1d', 'diage': '1e', 'diagf': '1f', 'diagg': '1g', 'stage2a': '2a'}.get(VARIANT, 1), hardwareTested=False,
                    packSha256=sha(pack_file), packRtosSha256=sha(pack), packRtosBytes=len(pack), base=base,
                    payloadSha256=sha(payload), payloadBytes=len(payload), elfSha256=sha(elf_path.read_bytes()),
                    symbols=symbols, slots=names, patches=patches, stateWord=pack_tools.STATE_WORD, audioLatchReadOnly=latch,
                    packZeroFillEnd=pack_tools.PACK_ZERO_FILL_END,
                    sourceHashes={p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in source_paths})
    (BUILD/'payload-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps(dict(payloadBytes=len(payload), sha256=sha(payload), base=hex(base), end=hex(base+len(payload)),
                          stateWord=hex(pack_tools.STATE_WORD), packSha256=sha(pack_file)), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pack', type=Path, default=MAIN/'scratch'/'film-mtf-all-films-firmware-2026-11-02'/'fwdc239b.bin',
                        help='the film pack fwdc239b.bin to build on (read only)')
    parser.add_argument('--pack-sha256', default=EXPECTED_PACK_SHA256, help='the SHA-256 the base must have')
    parser.add_argument('--stock-rtos', type=Path, default=MAIN/'scratch'/'video-firmware-high-rate-2026-11-01'/'original-rtos.bin')
    parser.add_argument('--clang', default=shutil.which('clang') or r'C:\Program Files\LLVM\bin\clang.exe')
    parser.add_argument('--lld', default=shutil.which('ld.lld') or r'C:\Program Files\LLVM\bin\ld.lld.exe')
    build(parser.parse_args())
