"""Build the real freestanding ARM player and execute it in Unicorn.

Requires clang/ld.lld with ARM support, pyelftools and unicorn. No camera,
firmware patching, host C runtime, WSL or Unix shell is needed.
"""
import argparse
import json
import shutil
import subprocess
import struct
from pathlib import Path
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

HERE = Path(__file__).resolve().parent
LAB = HERE.parent

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clang', default=shutil.which('clang') or r'C:\Program Files\LLVM\bin\clang.exe')
    parser.add_argument('--lld', default=shutil.which('ld.lld') or r'C:\Program Files\LLVM\bin\ld.lld.exe')
    args = parser.parse_args()
    out = LAB / 'out' / 'native'
    out.mkdir(parents=True, exist_ok=True)
    objects = []
    for name in ('player', 'test_player'):
        obj = out / (name + '.o')
        subprocess.run([args.clang, '-target', 'armv7-none-eabi', '-mcpu=cortex-a9', '-marm', '-mfloat-abi=soft', '-mfpu=none',
                        '-Os', '-ffreestanding', '-fno-builtin', '-fno-unwind-tables',
                        '-fno-asynchronous-unwind-tables', '-fno-stack-protector',
                        '-Wall', '-Wextra', '-Werror', '-c', str(HERE / (name + '.c')), '-o', str(obj)], check=True)
        objects.append(str(obj))
    elf_path = out / 'player-tests.elf'
    subprocess.run([args.lld, '-Ttext=0x10000000', '--entry=test_all', '--no-undefined',
                    *objects, '-o', str(elf_path)], check=True)
    cpu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    # LLD emits a small ELF program-header load segment at 0x10000 too.
    cpu.mem_map(0x10000, 0x1000)
    cpu.mem_map(0x10000000, 0x100000)
    cpu.mem_map(0x20000000, 0x20000)
    cpu.mem_map(0x30000000, 0x800000)
    symbols = {}
    with elf_path.open('rb') as stream:
        elf = ELFFile(stream)
        for segment in elf.iter_segments():
            if segment['p_type'] == 'PT_LOAD':
                cpu.mem_write(segment['p_vaddr'], segment.data())
        symbols = {s.name: s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()}

    def call(name, r0=0, r1=0, r2=0):
        cpu.reg_write(UC_ARM_REG_SP, 0x2001f000)
        cpu.reg_write(UC_ARM_REG_LR, 0x20000000)
        cpu.reg_write(UC_ARM_REG_R0, r0)
        cpu.reg_write(UC_ARM_REG_R1, r1)
        cpu.reg_write(UC_ARM_REG_R2, r2)
        # A maximal 8 MiB asset needs ~700M ARM instructions for the initial
        # bitwise CRC pass. This is test-emulator work, not a per-frame task.
        cpu.emu_start(symbols[name], 0x20000000, count=1_000_000_000)
        assert cpu.reg_read(UC_ARM_REG_PC) == 0x20000000, 'instruction budget exhausted'
        line = cpu.reg_read(UC_ARM_REG_R0)
        assert line == 0, f'{name} failed at test_player.c:{line}'

    call('test_all')
    tested = []
    for name in ('film', 'robot', 'focus'):
        asset = LAB / 'out' / (name + '.gsa')
        if asset.exists():
            blob = asset.read_bytes()
            cpu.mem_write(0x30000000, blob)
            call('test_asset', 0x30000000, len(blob))
            tested.append(name)
    compact = []
    for asset in sorted((LAB / 'out').glob('diskette-*.gsp')):
        blob = asset.read_bytes()
        cpu.mem_write(0x30000000, blob)
        call('test_compact', 0x30000000, len(blob))
        poses = int.from_bytes(blob[10:12], 'little')
        compact.append(dict(name=asset.stem, bytes=len(blob), poses=poses, spriteUploads=poses))
    # Sample the actual C callbacks against the shared browser math, including
    # negative hop offsets and Q8 scan-line scaling, every 25 ms in all modes.
    timing_uri = json.dumps((LAB / 'timing.mjs').as_uri())
    script = ('import {motionAt} from ' + timing_uri + '; const rows=[]; '
              'for(let v=0;v<3;v++)for(let ms=0;ms<5700;ms+=25){const s=motionAt(ms,v);'
              'rows.push([ms,v,s.y,Math.round(s.opacity*255),Math.round(s.scaleX*256),Math.round(s.scaleY*256)]);}'
              'console.log(JSON.stringify(rows));')
    samples = json.loads(subprocess.run([shutil.which('node') or 'node', '--input-type=module', '-e', script],
                                       check=True, capture_output=True, text=True, encoding='utf-8').stdout)
    for ms, variant, *expected in samples:
        call('test_motion_sample', ms, variant, 0x20010000)
        actual = list(struct.unpack('<iIII', cpu.mem_read(0x20010000,16)))
        assert actual == expected, (ms, variant, actual, expected)
    checks = int.from_bytes(cpu.mem_read(symbols['checks'], 4), 'little')
    report = dict(arm_player_assertions=checks, actual_assets=tested, frames_per_asset=100,
                  performance_ms=5000, enter_ms=350, leave_ms=350, deadline_ms=5700,
                  transition_samples_matching_browser=len(samples), clock_wrap_tested=True, cancellation_tested=True,
                  repeated_capture_tested=True, mute_tested=True, corrupt_assets_rejected=True,
                  compact_assets=compact, camera_adapter_verified=False, hardware_tested=False)
    (out / 'verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
