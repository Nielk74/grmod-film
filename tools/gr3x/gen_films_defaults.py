# SPDX-License-Identifier: GPL-2.0-only
"""Pre-compile tools/gr3x/native/films.c with -DFILM_DEFAULTS (round 10 films that start from their
own recipe values, GR Mod's film recipes) and write core/src/fw/gr3x/films-defaults-native.ts; with
--grain-row also -DGRAIN_ROW (the films' Grain row and gold Halation) into films-grain-native.ts.

As gen_films.py (the module without recipes, whose committed bytes this does not touch): compiled
once per film count (1..20), linked at a reference address with `--emit-relocs` and stored with its
relocation list; `linkModule()` places it at the real address. Every variant is linked a second
time at another address with other symbol values and compared with the relocated first build.

Toolchain: `python -m ziglang` (pip install ziglang) for the compiler, linker and objcopy, and
pyelftools (pip install pyelftools) to read the ELF, so neither clang nor binutils are needed.
"""
import base64
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SOURCE = HERE / 'native' / 'films.c'
GRAIN_ROW = '--grain-row' in sys.argv[1:]
TARGET = REPO / ('core/src/fw/gr3x/films-grain-native.ts' if GRAIN_ROW else 'core/src/fw/gr3x/films-defaults-native.ts')
NAME = 'GR3X_FILMS_GRAIN' if GRAIN_ROW else 'GR3X_FILMS_DEFAULTS'
ZIG = [sys.executable, '-m', 'ziglang']
FLAGS = ['-target', 'arm-freestanding-eabi', '-mcpu=cortex_a9', '-marm', '-mfloat-abi=soft', '-Os', '-ffreestanding',
         '-fno-builtin', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables', '-nostdlib', '-Wall', '-Werror',
         '-DFILM_DEFAULTS'] + (['-DGRAIN_ROW'] if GRAIN_ROW else [])
COUNTS = range(1, 21)
BINDINGS = ['prior_native_save', 'prior_native_load', 'storage_singleton', 'store_write', 'store_read', 'store_size',
            'heap_alloc', 'sp_gap', 'settings_object', 'slot_prints', 'film_defaults']
EXPORTS = ['sp_load', 'sp_save', 'sp_style_set', 'sp_before_recall', 'sp_hal', 'sp_hal_put', 'sp_col', 'sp_col_put',
           'sp_hal_text', 'sp_raw_init', 'sp_raw_own', 'sp_raw_sync'] + (['sp_grain', 'sp_grain_put', 'sp_grain_text'] if GRAIN_ROW else [])
RELOC_NAMES = {28: 'R_ARM_CALL', 29: 'R_ARM_JUMP24', 43: 'R_ARM_MOVW_ABS_NC', 44: 'R_ARM_MOVT_ABS'}


def run(command):
    result = subprocess.run([str(item) for item in command], capture_output=True, text=True)
    if result.returncode:
        raise SystemExit(' '.join(map(str, command)) + '\n' + result.stdout + result.stderr)
    return result.stdout


def compile_module(count, origin, bindings, relocs):
    with tempfile.TemporaryDirectory(prefix='grmod-films-defaults-') as folder:
        d = Path(folder)
        (d / 'm.c').write_text(f'#define SLOT_COUNT {count}\n' + SOURCE.read_text(encoding='utf-8'), encoding='utf-8')
        script = ' '.join(f'{name} = {value:#x};' for name, value in bindings.items())
        script += (f' SECTIONS {{ . = {origin:#x}; .text : {{ *(.text*) *(.rodata*) }} '
                   '/DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) } }')
        (d / 'm.ld').write_text(script, encoding='ascii')
        run(ZIG + ['cc', *FLAGS, '-c', d / 'm.c', '-o', d / 'm.o'])
        link = ZIG + ['ld.lld', '-T', d / 'm.ld', '--entry=sp_load', '-o', d / 'm.elf', d / 'm.o']
        if relocs:
            link.append('--emit-relocs')
        run(link)
        run(ZIG + ['objcopy', '-O', 'binary', '--only-section=.text', d / 'm.elf', d / 'm.arm'])
        blob = (d / 'm.arm').read_bytes()
        blob += bytes(-len(blob) % 4)   # the read-only tables end the section: pad to whole words
        with open(d / 'm.elf', 'rb') as f:
            elf = ELFFile(f)
            for section in elf.iter_sections():
                if section.name in ('.data', '.bss') and section['sh_size']:
                    raise SystemExit(f'the module must not have {section.name}')
            symtab = elf.get_section_by_name('.symtab')
            syms = list(symtab.iter_symbols())
            if any(s['st_shndx'] == 'SHN_UNDEF' and s.name for s in syms):
                raise SystemExit('undefined symbol')
            if any(s.name.startswith('__aeabi') or s.name in ('memset', 'memcpy') for s in syms):
                raise SystemExit('library call in the module')
            symbols = {s.name: s['st_value'] for s in syms if s.name}
            table = []
            if relocs:
                for section in elf.iter_sections():
                    if not isinstance(section, RelocationSection) or not section.name.startswith('.rel.text'):
                        continue
                    for r in section.iter_relocations():
                        sym = symtab.get_symbol(r['r_info_sym'])
                        name = sym.name or elf.get_section(sym['st_shndx']).name if sym['st_shndx'] not in ('SHN_ABS', 'SHN_UNDEF') else sym.name
                        kind = RELOC_NAMES.get(r['r_info_type'])
                        if not kind:
                            raise SystemExit(f'unsupported relocation type {r["r_info_type"]}')
                        table.append((r['r_offset'], kind, name, sym['st_value']))
        return blob, symbols, table


def half(word):
    return ((word >> 4) & 0xF000) | (word & 0xFFF)


def make_template(count):
    origin = 0x54400000
    bindings = {symbol: 0x53400000 + 0x1234 * (index + 1) * 4 for index, symbol in enumerate(BINDINGS)}
    plain, _, _ = compile_module(count, origin, bindings, False)
    blob, symbols, table = compile_module(count, origin, bindings, True)
    if plain != blob or len(blob) % 4:
        raise SystemExit('--emit-relocs changed the code')
    words = list(struct.unpack('<%dI' % (len(blob) // 4), blob))
    relocs, pending = [], {}
    for address, kind, symbol, value in table:
        offset = address - origin
        if not 0 <= offset < len(blob) or offset % 4:
            raise SystemExit('relocation outside the module')
        word = words[offset // 4]
        if symbol in bindings:
            if value != bindings[symbol]:
                raise SystemExit('unexpected symbol value')
            target = ['x', BINDINGS.index(symbol)]
        else:
            if not origin <= value < origin + len(blob):
                raise SystemExit(f'symbol {symbol} is neither bound nor inside the module')
            target = ['i', value - origin]
        if kind == 'R_ARM_MOVW_ABS_NC':
            pending[(symbol, (word >> 12) & 15)] = (offset, half(word), target, value)
        elif kind == 'R_ARM_MOVT_ABS':
            low_offset, low, low_target, low_value = pending.pop((symbol, (word >> 12) & 15))
            addend = ((half(word) << 16 | low) - value) & 0xFFFFFFFF
            relocs.append([low_offset, 'w', *target, addend])
            relocs.append([offset, 't', *target, addend])
        else:
            displacement = word & 0xFFFFFF
            if displacement & 0x800000:
                displacement -= 1 << 24
            destination = address + 8 + displacement * 4
            if target[0] == 'x' and destination != value:
                raise SystemExit(f'a branch to {symbol} does not land on it (destination {destination:#x})')
            relocs.append([offset, 'b', *target, (destination - value) & 0xFFFFFFFF])
    if pending:
        raise SystemExit('unpaired MOVW relocation')
    relocs.sort()
    return {'blob': blob, 'relocs': relocs, 'exports': {s: symbols[s] - origin for s in EXPORTS}}


def relocate(template, origin, bindings):
    """The arithmetic of aspect/native-link.ts, tested here against lld."""
    words = list(struct.unpack('<%dI' % (len(template['blob']) // 4), template['blob']))
    for offset, kind, where, index, addend in template['relocs']:
        symbol = bindings[BINDINGS[index]] if where == 'x' else origin + index
        value = (symbol + addend) & 0xFFFFFFFF
        word = words[offset // 4]
        if kind in ('w', 't'):
            imm = value & 0xFFFF if kind == 'w' else value >> 16
            word = (word & 0xFFF0F000) | ((imm & 0xF000) << 4) | (imm & 0xFFF)
        else:
            delta = value - (origin + offset + 8)
            if delta % 4 or not -(1 << 25) <= delta < (1 << 25):
                raise SystemExit('branch out of range')
            word = (word & 0xFF000000) | ((delta >> 2) & 0xFFFFFF)
        words[offset // 4] = word
    return struct.pack('<%dI' % len(words), *words)


def main():
    out = {'bindings': BINDINGS, 'variants': {}}
    for count in COUNTS:
        template = make_template(count)
        origin = 0x543FC1D0 + 0x10 * count
        bindings = {symbol: 0x5370A5DC + 0x00FEDCB8 * (index + 1) % 0x00F00000 // 4 * 4 for index, symbol in enumerate(BINDINGS)}
        expected, symbols, _ = compile_module(count, origin, bindings, False)
        if relocate(template, origin, bindings) != expected:
            raise SystemExit(f'{count}: relocated template differs from a real link')
        for symbol, offset in template['exports'].items():
            if symbols[symbol] - origin != offset:
                raise SystemExit('export offset moved')
        out['variants'][count] = {'code': base64.b64encode(template['blob']).decode('ascii'),
                                  'relocs': template['relocs'], 'exports': template['exports']}
        print(f'{count:2d} films: {len(template["blob"])} bytes, {len(template["relocs"])} relocations')
    version = run(ZIG + ['cc', '--version']).splitlines()[0]
    source_hash = hashlib.sha256(SOURCE.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
    TARGET.write_text(
        '// SPDX-License-Identifier: GPL-2.0-only\n'
        '// GENERATED by tools/gr3x/gen_films_defaults.py -- do not edit.\n'
        '//\n'
        + ('// ARM code compiled from tools/gr3x/native/films.c with -DFILM_DEFAULTS -DGRAIN_ROW (round 10 films\n'
           "// with GR Mod's Grain row and gold Halation in the Toning byte, starting from their recipe's values).\n"
           if GRAIN_ROW else
           '// ARM code compiled from tools/gr3x/native/films.c with -DFILM_DEFAULTS (round 10 films that start\n'
           "// from their recipe's values; builds without recipes use films-native.ts, unchanged).\n") +
        f'// Compiler: {version}, flags {" ".join(FLAGS)}.\n'
        '// One variant per film count. Relocations as in ../aspect/native.ts.\n\n'
        "import type { NativeModule } from '../aspect/native';\n\n"
        f'export const {NAME}_SOURCE_SHA256 = "{source_hash}";\n'
        f'export const {NAME}_MODULE: NativeModule = {json.dumps(out, separators=(",", ":"))} as unknown as NativeModule;\n',
        encoding='utf-8', newline='\n')
    print(f'{TARGET}')


if __name__ == '__main__':
    main()
