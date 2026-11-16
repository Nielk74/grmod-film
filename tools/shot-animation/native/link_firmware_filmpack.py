"""Link the Terminal module on top of one exact GR III 2.10 film pack image.

Why this exists: a camera keeps its saved settings across a flash. Film looks
64..83 and added ratios saved under the film pack make official-based code fault,
so the first Terminal build (official base, no films, no settings guard) can fail
at startup. Here the film pack stays whole: its looks, ratios and guard are kept
byte for byte, and only the animation is added after them.

Silent (default, camera-tested 2026-11-05): camera_gr3.c is not changed for that.
The audio latch symbol is bound to a read-only word holding 1, which the adapter
reads as "audio already shut down": no mutex is created and no audio service is
touched. The WAV labels are empty and the audio shutdown hook is not patched, so
its callback is unreachable.

--sound: the three approved WAVs are embedded, the latch is a zero-filled RAM word
and the audio shutdown hook is patched, as in the official-based build.

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
from elftools.elf.elffile import ELFFile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import link_firmware as official  # noqa: E402  SERVICES, PATCHES, checked_asset

LAB = HERE.parent
ROOT = LAB.parent.parent
OUT = LAB/'out'/'firmware-filmpack'
SOUND_OUT = LAB/'out'/'firmware-filmpack-sound'
RTOS_BASE = 0x53000000
PACK_RTOS_BYTES = 18478528
PACK_TRAILER = b'GR3-HDF-210-ADJ9-T10-HARDWARE-UNTESTED\0'
PACK_ZERO_FILL_END = 0x558043c0
# Round 10 assigns 0x55804374..0x55804388. The zero fill runs to 0x558043c0, whose
# heap header comes next. This word is zeroed at every start and used by nothing else.
STATE_WORD = 0x558043b8
LATCH_WORD = 0x558043bc
FREE_WORDS = range(0x5580438c, PACK_ZERO_FILL_END, 4)
SILENT_SKIPS = {0x53568d58, 0x53000460}
PATCHES = [p for p in official.PATCHES if p['address'] not in SILENT_SKIPS]
NATIVE_SYMBOLS = {name: address for name, address in official.NATIVE_SYMBOLS.items()
                  if name not in ('grmod_adapter_state', 'grmod_audio_shutdown_latch')}
NATIVE_SYMBOLS['grmod_adapter_state'] = STATE_WORD
SOUND_PATCHES = [p for p in official.PATCHES if p['address'] != 0x53000460]
SOUND_SYMBOLS = {**NATIVE_SYMBOLS, 'grmod_audio_shutdown_latch': LATCH_WORD}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def decode_container(raw):
    """Port of parseFrames in core/src/fw/container.ts, for an exact trusted build output."""
    out = bytearray()
    pos, size = 0x80, len(raw)
    while pos+2 <= size:
        prefix = raw[pos] << 8 | raw[pos+1]
        pos += 2
        if prefix == 0:
            break
        end = pos+(prefix & 0x7fff)
        if prefix & 0x8000:
            out += raw[pos:end]
            pos = end
            continue
        while pos < end:
            flags = raw[pos] << 8 | raw[pos+1]
            pos += 2
            for bit in range(15, -1, -1):
                if pos >= end:
                    break
                if not flags & (1 << bit):
                    out.append(raw[pos])
                    pos += 1
                    continue
                first, second = raw[pos], raw[pos+1]
                pos += 2
                distance = ((first & 0xf8) << 5)+second
                count = first & 7
                if count == 7:
                    extra = raw[pos]
                    pos += 1
                    count += extra
                    while extra == 255:
                        extra = raw[pos]
                        pos += 1
                        count += extra
                if not distance:
                    break
                for _ in range(count+3):
                    out.append(out[-distance])
        pos = end
    return bytes(out)


def rtos_of(decoded):
    at = 0
    while at+16 <= len(decoded):
        name = decoded[at:at+8].rstrip(b'\0')
        size = struct.unpack_from('<I', decoded, at+12)[0]
        if name == b'RTOS':
            return decoded[at+16:at+16+size]
        if name == b'RES' or not name:
            break
        at += 16+size
    raise ValueError('No RTOS section')


def ram_word_references(rtos, words):
    """Literal words and movw/movt pairs naming any of the given addresses."""
    wanted = set(words)
    count = len(rtos)//4
    values = struct.unpack('<%dI' % count, rtos[:count*4])
    found = []
    for index, word in enumerate(values):
        if word in wanted:
            found.append(hex(RTOS_BASE+index*4))
        if (word & 0x0ff00000) == 0x03400000 and (((word >> 16) & 15) << 12 | word & 0xfff) == 0x5580:
            register = (word >> 12) & 15
            for back in range(index-1, max(0, index-40), -1):
                low = values[back]
                if (low & 0x0ff00000) == 0x03000000 and ((low >> 12) & 15) == register:
                    if 0x55800000 | ((low >> 16) & 15) << 12 | low & 0xfff in wanted:
                        found.append(hex(RTOS_BASE+index*4))
                    break
    return found


def check_pack(pack, stock, patches=PATCHES):
    """Refuse anything but a complete round 10 film pack the animation can sit on."""
    if len(pack) != PACK_RTOS_BYTES or pack[-4-len(PACK_TRAILER):-4] != PACK_TRAILER:
        raise ValueError('Input is not a GR III 2.10 film pack (official images have no films or settings guard)')
    if struct.unpack_from('<I', pack, 0x460)[0] != PACK_ZERO_FILL_END:
        raise ValueError('Film pack zero fill does not reach its added RAM words')
    project, product = struct.unpack_from('<2I', pack, 0x2030)
    if (project, product) != (588, 78350) or struct.unpack_from('>I', pack, 0x2038)[0] != 0x020a151b:
        raise ValueError('Film pack identity is not GR III 2.10')
    for patch in patches:
        at = patch['address']-RTOS_BASE
        if pack[at:at+4].hex() != patch['expected']:
            raise ValueError('Film pack already patches hook site '+hex(patch['address']))
    for address, name in official.SERVICES.items():
        at = address-RTOS_BASE
        if pack[at:at+16] != stock[at:at+16]:
            raise ValueError('Film pack changes a service the animation calls: '+name)
    used = ram_word_references(pack, FREE_WORDS)
    if used:
        raise ValueError('Film pack uses a RAM word thought to be free: '+', '.join(used))


def flatten(path, base, native=NATIVE_SYMBOLS):
    with path.open('rb') as stream:
        elf = ELFFile(stream)
        if elf['e_machine'] != 'EM_ARM' or elf.elfclass != 32 or not elf.little_endian:
            raise ValueError('Expected little-endian A32 ELF')
        segments = [s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD']
        if len(segments) != 1 or segments[0]['p_vaddr'] != base or segments[0]['p_filesz'] != segments[0]['p_memsz']:
            raise ValueError('Linker emitted an unexpected segment')
        data = segments[0].data()
        if base+len(data) >= 0x55000000:
            raise ValueError('Payload reaches initialized RAM')
        table = elf.get_section_by_name('.symtab')
        unresolved = [s.name for s in table.iter_symbols() if s.name and s['st_shndx'] == 'SHN_UNDEF']
        if unresolved:
            raise ValueError('Undefined symbols: '+','.join(unresolved))
        symbols = {s.name: s['st_value'] for s in table.iter_symbols() if s.name and s['st_shndx'] != 'SHN_UNDEF'}
        for name, address in native.items():
            if symbols.get(name) != address:
                raise ValueError('Native binding changed: '+name)
        for section in elf.iter_sections():
            if section.name.startswith(('.data', '.bss')) and section['sh_size']:
                raise ValueError('Mutable state belongs in the native heap, not the read-only RTOS')
    return data, symbols


def build(args):
    sound = args.sound
    out = SOUND_OUT if sound else OUT
    patches, native = (SOUND_PATCHES, SOUND_SYMBOLS) if sound else (PATCHES, NATIVE_SYMBOLS)
    out.mkdir(parents=True, exist_ok=True)
    stock = args.stock_rtos.read_bytes()
    if sha(stock) != official.RTOS_HASH:
        raise ValueError('Official reference RTOS changed')
    pack_file = args.pack.read_bytes()
    pack = rtos_of(decode_container(pack_file))
    check_pack(pack, stock, patches)
    base = RTOS_BASE+len(pack)
    asset = official.checked_asset(official.OUT/'terminal-native.trm')
    # The sound scenarios already ran against this exact adapter source.
    tested = json.loads((official.OUT/'adapter-linked'/'adapter-verification.json').read_text(encoding='utf-8'))
    for name in ('camera_gr3.c', 'camera_gr3.h', 'terminal.c', 'terminal.h', 'camera_clock.c', 'camera_clock.h'):
        key = (HERE/name).relative_to(ROOT).as_posix()
        if tested['source_sha256'].get(key) != sha((HERE/name).read_bytes()):
            raise ValueError('Adapter source differs from the verified adapter: '+name)
    assembly = ['.syntax unified', '.arm', '.section .grmod_assets,"a",%progbits', '.balign 4']
    if not sound:
        assembly += ['.global grmod_audio_shutdown_latch', 'grmod_audio_shutdown_latch:', '.word 1']
    assembly += ['.balign 16', '.global terminal_asset_start', 'terminal_asset_start:',
                 '.incbin "'+(official.OUT/'terminal-native.trm').as_posix()+'"',
                 '.global terminal_asset_end', 'terminal_asset_end:', '.balign 4']
    waves = {}
    approved = json.loads((official.OUT/'payload-manifest.json').read_text(encoding='utf-8'))['waves']
    for name in ('dash', 'portal', 'rocket'):
        assembly.append(f'.global terminal_wav_{name}_start, terminal_wav_{name}_end')
        if sound:
            path = LAB/'out'/f'terminal-{name}.wav'
            waves[name] = official.checked_wave(path)
            if waves[name]['sha256'] != approved[name]['sha256']:
                raise ValueError('Soundtrack differs from the approved one: '+name)
            assembly += ['.balign 16', f'terminal_wav_{name}_start:', '.incbin "'+path.as_posix()+'"']
        else:
            assembly.append(f'terminal_wav_{name}_start:')
        assembly.append(f'terminal_wav_{name}_end:')
    assembly += ['.section .note.GNU-stack,"",%progbits', '']
    (out/'assets.S').write_text('\n'.join(assembly), encoding='utf-8', newline='\n')
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
    (out/'terminal.ld').write_text(linker, encoding='utf-8', newline='\n')
    flags = ['-target', 'armv7-none-eabi', '-mcpu=cortex-a9', '-marm', '-mfloat-abi=soft', '-mfpu=none',
             '-Os', '-ffreestanding', '-fno-builtin', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables',
             '-fno-stack-protector', '-fno-common', '-fdata-sections', '-ffunction-sections', '-Wall', '-Wextra', '-Werror']
    sources = [HERE/'terminal.c', HERE/'camera_clock.c', HERE/'camera_gr3.c', HERE/'hooks.S', out/'assets.S']
    objects = []
    for source in sources:
        target = out/(source.stem+'.o')
        subprocess.run([args.clang, *flags, '-c', str(source), '-o', str(target)], check=True)
        objects.append(str(target))
    elf_path = out/'terminal-payload.elf'
    subprocess.run([args.lld, '-T', str(out/'terminal.ld'), '--no-undefined',
                    *('--defsym='+name+'='+hex(address) for name, address in native.items()),
                    *objects, '-o', str(elf_path)], check=True)
    payload, symbols = flatten(elf_path, base, native)
    (out/'terminal-payload.bin').write_bytes(payload)
    latch = symbols['grmod_audio_shutdown_latch']
    if not sound and payload[latch-base:latch-base+4] != struct.pack('<I', 1):
        raise ValueError('Silent build needs a read-only audio latch holding 1')
    if sound and not STATE_WORD < latch < PACK_ZERO_FILL_END:
        raise ValueError('Sound build needs a zero-filled RAM latch')
    for name in waves:
        if symbols[f'terminal_wav_{name}_end']-symbols[f'terminal_wav_{name}_start'] != waves[name]['bytes']:
            raise ValueError('Embedded soundtrack extent changed: '+name)
    source_paths = [*sources[:-1], HERE/'terminal.h', HERE/'camera_gr3.h', HERE/'camera_clock.h', Path(__file__),
                    LAB/'build-firmware-filmpack.ts']
    manifest = dict(schema=1, camera='GR III', baseVersion='2.10', silent=not sound, hardwareTested=False,
                    packSha256=sha(pack_file), packRtosSha256=sha(pack), packRtosBytes=len(pack), base=base,
                    payloadSha256=sha(payload), payloadBytes=len(payload), elfSha256=sha(elf_path.read_bytes()),
                    symbols=symbols, patches=patches, stateWord=STATE_WORD,
                    **({'audioLatchWord': latch, 'waves': waves} if sound else {'audioLatchReadOnly': latch}),
                    packZeroFillEnd=PACK_ZERO_FILL_END, asset=asset,
                    sourceHashes={p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in source_paths})
    (out/'payload-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps(dict(payloadBytes=len(payload), sha256=sha(payload), base=hex(base), end=hex(base+len(payload)),
                          stateWord=hex(STATE_WORD), audioLatch=hex(latch), packSha256=sha(pack_file)), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pack', type=Path, default=ROOT/'scratch'/'film-mtf-all-films-firmware-2026-11-02'/'fwdc239b.bin')
    parser.add_argument('--stock-rtos', type=Path, default=ROOT/'scratch'/'video-firmware-high-rate-2026-11-01'/'original-rtos.bin')
    parser.add_argument('--sound', action='store_true', help='Embed the approved soundtracks and patch the audio shutdown hook')
    parser.add_argument('--clang', default=shutil.which('clang') or r'C:\Program Files\LLVM\bin\clang.exe')
    parser.add_argument('--lld', default=shutil.which('ld.lld') or r'C:\Program Files\LLVM\bin\ld.lld.exe')
    build(parser.parse_args())
