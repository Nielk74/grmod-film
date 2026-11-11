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

OUT = LAB/'out'/'firmware-loaded-stage1'
BUILD = OUT/'build'
EXPECTED_PACK_SHA256 = 'cf04126f5861c3a64123f0cdc95efa5b65443b44aa0ca975854423acf0131f55'
sha = pack_tools.sha


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
    pack_tools.check_pack(pack, stock, patches)
    base = pack_tools.RTOS_BASE + len(pack)
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
    sources = [HERE/'loaded.c', HERE/'camera_loaded.c', NATIVE_TERMINAL/'camera_clock.c', NATIVE_TERMINAL/'hooks.S', BUILD/'assets.S']
    objects = []
    for source in sources:
        target = BUILD/(source.stem+'.o')
        subprocess.run([args.clang, *flags, '-c', str(source), '-o', str(target)], check=True)
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
    headers = [HERE/'loaded.h', HERE/'loaded_data.h', HERE/'camera_loaded.h', NATIVE_TERMINAL/'camera_clock.h']
    source_paths = [*sources[:-1], *headers, Path(__file__), LAB/'build-loaded-stage1.ts']
    manifest = dict(schema=1, camera='GR III', baseVersion='2.10', silent=True, stage=1, hardwareTested=False,
                    packSha256=sha(pack_file), packRtosSha256=sha(pack), packRtosBytes=len(pack), base=base,
                    payloadSha256=sha(payload), payloadBytes=len(payload), elfSha256=sha(elf_path.read_bytes()),
                    symbols=symbols, patches=patches, stateWord=pack_tools.STATE_WORD, audioLatchReadOnly=latch,
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
