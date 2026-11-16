"""Link the GR III 2.10 Terminal module; no camera or card is accessed.

The input is the exact original RTOS, not an already modified image. All code
and immutable samples are appended below initialized RAM. Mutable state is
allocated by the native adapter; one separately reserved RAM word holds it.
"""
import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import zlib
from pathlib import Path
from elftools.elf.elffile import ELFFile

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
ROOT = LAB.parent.parent
OUT = LAB / 'out' / 'firmware'
RTOS_BASE = 0x53000000
RTOS_HASH = '8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67'
RTOS_BYTES = 17520064
LINK_BASE = RTOS_BASE + RTOS_BYTES
ANCHOR = 0x55804374

# Calls and data boundaries recovered from this exact image. The whole image
# hash is authoritative; focused signatures make each ABI dependency visible.
SERVICES = {
    0x530003A8: 'startup zero-fill loop',
    0x5316CE30: 'controller registered Canvas lookup',
    0x5320A020: 'RGBA alpha-key copier',
    0x5320AD88: 'application getter',
    0x5320AEFC: 'AppModel getter',
    0x5320B01C: 'AppTimerModel getter',
    0x5320B31C: 'UserData getter',
    0x53228A90: 'active controller lookup',
    0x5322B1EC: 'AppTimerModel stop',
    0x5322B468: 'AppTimerModel start',
    0x5322B4B4: 'AppTimerModel expiry dispatch',
    0x5324651C: 'saved camera volume',
    0x53246528: 'camera sound-disable flag',
    0x5339A89C: 'owned IconView deleting destructor',
    0x5339A908: 'IconView constructor',
    0x533AB9BC: 'base View Draw bookkeeping',
    0x533ABA64: 'attach child View',
    0x533AC120: 'set View parent',
    0x533AD308: 'invalidate View',
    0x533AD3C0: 'set View visibility',
    0x533AD7F0: 'View descriptor factory',
    0x53566B74: 'private owned WAV stop',
    0x53567004: 'private WAV start',
    0x535677A8: 'audio volume setter',
    0x53568E58: 'AudioServiceFactory getter',
    0x53568D58: 'AudioServiceFactory shutdown owns service destruction',
    0x53568EC0: 'AudioService getter',
    0x53568F8C: 'canonical WAV parser',
    0x536AE668: 'persistent module Mutex constructor',
    0x536AE71C: 'zero-timeout MutexLock',
    0x536AE870: 'MutexUnlock',
    0x536AEF0C: 'persistent module Mutex initialization',
    0x536AF2A8: 'native operator new',
    0x536AF2E4: 'native operator delete on failed initialization',
    0x536AFC5C: 'native millisecond clock',
    0x536B6F68: 'View vector erase',
    0x53B2F9E8: 'LiveViewController vtable',
    0x53B41380: 'QuickViewController vtable',
    0x53C09F10: 'Canvas vtable',
    0x53C0A8A8: 'IconView vtable',
    0x53D1B7B8: 'AudioService vtable',
}
PATCHES = [
    dict(address=0x532D55F8, expected='ac4cfdea', symbol='grmod_hook_shot', link=False,
         reason='Observe image-BE completion and preserve native event0x16c enqueue'),
    dict(address=0x5316CAF8, expected='33ff2fe1', symbol='grmod_hook_transition_before', link=True,
         reason='Detach owned View before an accepted native controller exit'),
    dict(address=0x5316CB74, expected='5431d4e5', symbol='grmod_hook_transition_after', link=False,
         reason='Reattach across LiveView/QuickView; cancel unsupported entered controllers'),
    dict(address=0x533918D0, expected='0dc0a0e1', symbol='grmod_hook_canvas_delete', link=False,
         reason='Detach owned child before native Canvas destruction'),
    dict(address=0x53239818, expected='0dc0a0e1', symbol='grmod_hook_release', link=False,
         reason='Cancel owned animation on native full-release attempt'),
    dict(address=0x53568D58, expected='0dc0a0e1', symbol='grmod_hook_audio_shutdown', link=False,
         reason='Latch custom audio off before native AudioService destruction, including before first shot'),
    dict(address=0x53000460, expected='74438055', replacement='80438055',
         reason='Zero reserved12-byte alignment gap before heap; first word holds adapter pointer'),
]
NATIVE_SYMBOLS = {
    'native_enqueue': 0x532288B0,
    'native_transition_resume': 0x5316CB78,
    'native_canvas_delete_resume': 0x533918D4,
    'native_release_resume': 0x5323981C,
    'native_audio_shutdown_resume': 0x53568D5C,
    'grmod_adapter_state': ANCHOR,
    'grmod_audio_shutdown_latch': ANCHOR+4,
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked_wave(path):
    data = path.read_bytes()
    if len(data) != 1459244:
        raise ValueError(f'{path}: expected full7.6-second canonical stereo WAV')
    header = struct.unpack('<4sI4s4sIHHIIHH4sI', data[:44])
    expected = (b'RIFF', len(data)-8, b'WAVE', b'fmt ', 16, 1, 2, 48000, 192000, 4, 16, b'data', len(data)-44)
    if header != expected:
        raise ValueError(f'{path}: WAV format/chunk bounds differ from native-compatible PCM contract')
    return dict(bytes=len(data), sha256=sha(data), sampleRate=48000, channels=2, bits=16, durationMs=7600)


def checked_asset(path):
    data = path.read_bytes()
    if len(data) < 80 or len(data) > 4*1024*1024 or data[:4] != b'TRM2':
        raise ValueError('Invalid Terminal native asset')
    if struct.unpack_from('<I', data, 60)[0] != len(data) or struct.unpack_from('<I', data, 64)[0] != zlib.crc32(data[80:]):
        raise ValueError('Terminal asset length/CRC changed')
    # The ARM decoder executes complete structural and index validation before
    # rendering. Its verification report must refer to these exact bytes.
    report = json.loads((OUT / 'native-verification.json').read_text(encoding='utf-8'))
    if report.get('artifact_sha256') != sha(data) or report.get('native_assertions', 0) < 500:
        raise ValueError('Run native/check_terminal.py for this asset before linking')
    for name in ('terminal.c', 'terminal.h', 'test_terminal.c'):
        if report.get('source_hashes', {}).get(name) != sha((HERE/name).read_bytes()):
            raise ValueError('Native renderer verification is stale: '+name)
    return dict(bytes=len(data), sha256=sha(data))


def flatten_elf(path):
    with path.open('rb') as stream:
        elf = ELFFile(stream)
        if elf['e_machine'] != 'EM_ARM' or elf.elfclass != 32 or not elf.little_endian:
            raise ValueError('Expected little-endian A32 ELF')
        segments = [s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD']
        if len(segments) != 1 or segments[0]['p_vaddr'] != LINK_BASE:
            raise ValueError('Linker emitted unexpected segment/base')
        segment = segments[0]
        if segment['p_filesz'] != segment['p_memsz']:
            raise ValueError('Appended RTOS has no automatic BSS initialization')
        data = segment.data()
        if not data or LINK_BASE+len(data) >= 0x55000000:
            raise ValueError('Payload reaches initialized RAM')
        table = elf.get_section_by_name('.symtab')
        unresolved = [s.name for s in table.iter_symbols() if s.name and s['st_shndx'] == 'SHN_UNDEF']
        if unresolved:
            raise ValueError('Undefined symbols: '+','.join(unresolved))
        symbols = {s.name: s['st_value'] for s in table.iter_symbols() if s.name and s['st_shndx'] != 'SHN_UNDEF'}
        for name, address in NATIVE_SYMBOLS.items():
            if symbols.get(name) != address:
                raise ValueError('Native binding changed: '+name)
        for section in elf.iter_sections():
            if section.name.startswith(('.data', '.bss')) and section['sh_size']:
                raise ValueError('Mutable state belongs in the owned native heap, not appended RTOS')
        return data, symbols


def build(args):
    OUT.mkdir(parents=True, exist_ok=True)
    rtos = args.rtos.read_bytes()
    if len(rtos) != RTOS_BYTES or sha(rtos) != RTOS_HASH:
        raise ValueError('Only exact original GR III2.10 RTOS is supported')
    for patch in PATCHES:
        at = patch['address']-RTOS_BASE
        if rtos[at:at+4].hex() != patch['expected']:
            raise ValueError('Stock hook signature changed: '+hex(patch['address']))
    asset_path = OUT / 'terminal-native.trm'
    asset = checked_asset(asset_path)
    waves = {name: checked_wave(LAB/'out'/f'terminal-{name}.wav') for name in ('dash', 'portal', 'rocket')}
    assembly = ['.syntax unified', '.arm', '.section .grmod_assets,"a",%progbits']
    inputs = [('terminal_asset', asset_path), *((f'terminal_wav_{name}', LAB/'out'/f'terminal-{name}.wav') for name in waves)]
    for name, path in inputs:
        if '"' in str(path):
            raise ValueError('Unsupported quote in source path')
        assembly += ['.balign 16', f'.global {name}_start', f'{name}_start:',
                     '.incbin "'+path.as_posix()+'"', f'.global {name}_end', f'{name}_end:']
    assembly += ['.section .note.GNU-stack,"",%progbits', '']
    (OUT/'assets.S').write_text('\n'.join(assembly), encoding='utf-8', newline='\n')
    linker = f'''ENTRY(grmod_hook_shot)
PHDRS {{ image PT_LOAD FLAGS(5); }}
SECTIONS {{
  . = 0x{LINK_BASE:x};
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
    (OUT/'terminal.ld').write_text(linker, encoding='utf-8', newline='\n')
    objects = []
    flags = ['-target', 'armv7-none-eabi', '-mcpu=cortex-a9', '-marm', '-mfloat-abi=soft', '-mfpu=none',
             '-Os', '-ffreestanding', '-fno-builtin', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables',
             '-fno-stack-protector', '-fno-common', '-fdata-sections', '-ffunction-sections', '-Wall', '-Wextra', '-Werror']
    sources = [HERE/'terminal.c', HERE/'camera_clock.c', HERE/'camera_gr3.c', HERE/'hooks.S', OUT/'assets.S']
    for source in sources:
        target = OUT/(source.stem+'-firmware.o')
        subprocess.run([args.clang, *flags, '-c', str(source), '-o', str(target)], check=True)
        objects.append(str(target))
    elf_path = OUT/'terminal-payload.elf'
    subprocess.run([args.lld, '-T', str(OUT/'terminal.ld'), '--no-undefined',
                    *('--defsym='+name+'='+hex(address) for name, address in NATIVE_SYMBOLS.items()),
                    *objects, '-o', str(elf_path)], check=True)
    payload, symbols = flatten_elf(elf_path)
    (OUT/'terminal-payload.bin').write_bytes(payload)
    source_paths = [*sources[:-1], HERE/'terminal.h', HERE/'camera_gr3.h', HERE/'camera_clock.h', Path(__file__), LAB/'build-firmware.ts']
    source_hashes = {path.relative_to(ROOT).as_posix(): sha(path.read_bytes()) for path in source_paths}
    evidence = {}
    reports = [OUT/'native-verification.json', LAB/'out'/'firmware-lifecycle'/'clock-verification.json',
               LAB/'out'/'adapter-check'/'adapter-verification.json']
    for path in reports:
        evidence[path.name] = dict(sha256=sha(path.read_bytes()), report=json.loads(path.read_text(encoding='utf-8')))
    if evidence['clock-verification.json']['report']['wrapper_source_sha256'] != sha((HERE/'camera_clock.c').read_bytes()):
        raise ValueError('Native clock verification is stale')
    adapter_report = evidence['adapter-verification.json']['report']
    if adapter_report.get('rtos_sha256') != RTOS_HASH:
        raise ValueError('Adapter verification target changed')
    for name in ('camera_gr3.c', 'camera_gr3.h', 'terminal.c', 'terminal.h', 'camera_clock.c', 'camera_clock.h', 'check_adapter.py'):
        key = (HERE/name).relative_to(ROOT).as_posix()
        if adapter_report.get('source_sha256', {}).get(key) != sha((HERE/name).read_bytes()):
            raise ValueError('Camera adapter verification is stale: '+name)
    manifest = dict(schema=1, camera='GR III', baseVersion='2.10', rtosSha256=RTOS_HASH, base=LINK_BASE,
                    payloadSha256=sha(payload), payloadBytes=len(payload), elfSha256=sha(elf_path.read_bytes()), hardwareTested=False,
                    symbols=symbols, patches=PATCHES,
                    serviceGuards=[dict(address=address, name=name, expected=rtos[address-RTOS_BASE:address-RTOS_BASE+16].hex())
                                   for address, name in sorted(SERVICES.items())],
                    reservedRam=dict(address=ANCHOR, bytes=8, audioShutdownLatch=ANCHOR+4,
                                     zeroFillEnd=0x55804380, heapBegins=0x55804380,
                                     policy='Exact official input only; exclusive state pointer and audio latch; never combine with film slot RAM words'),
                    asset=asset, waves=waves, sourceHashes=source_hashes, evidence=evidence,
                    limits=['Experimental hardware-test candidate; no physical camera execution performed.',
                            'Original native calls tested with controlled OS/driver substitutions; display/DMA/cache and speaker behavior remain unmeasured.',
                            'Completion notification traced statically; physical drive-mode/error/QuickView-disabled event behavior requires a camera trace.',
                            'No version increase; camera model/project/header and original photographic image pipeline are preserved.'])
    (OUT/'payload-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps(dict(output=str(OUT/'terminal-payload.bin'), payloadBytes=len(payload), sha256=sha(payload),
                          base=hex(LINK_BASE), mutablePayloadBytes=0, nativeRamAnchor=hex(ANCHOR),
                          asset=asset, waves=waves, undefinedSymbols=[], hardwareTested=False), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rtos', type=Path, default=ROOT/'scratch'/'video-firmware-high-rate-2026-11-01'/'original-rtos.bin')
    parser.add_argument('--clang', default=shutil.which('clang') or r'C:\Program Files\LLVM\bin\clang.exe')
    parser.add_argument('--lld', default=shutil.which('ld.lld') or r'C:\Program Files\LLVM\bin\ld.lld.exe')
    build(parser.parse_args())
