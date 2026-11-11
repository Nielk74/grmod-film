"""Compile native/loaded.c freestanding for A32, run it in Unicorn and compare it with the JS reference.

  python native/check_loaded.py            full run: build, regenerate data check, parity, robustness
  python native/check_loaded.py --quick    focus subset only (about one case in four)

Parity: for every case in out/native/parity.json (written by native/export-parity.mjs from the JS renderer),
the C renderer fills the five views in emulated memory and the CRC-32 of each view's RGBA bytes must equal the
JS one. On a mismatch the JS pixels of that case are dumped and the first differing pixel is reported.
No firmware or camera is touched.
"""
import argparse
import shutil
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_BLOCK
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / 'out' / 'native'
CLANG = shutil.which('clang') or r'C:\Program Files\LLVM\bin\clang.exe'
LLD = shutil.which('ld.lld') or r'C:\Program Files\LLVM\bin\ld.lld.exe'
V_FULL, V_TOP, V_BOTTOM, V_COUNTER, V_TAB = range(5)
VIEW_NAMES = ['full', 'top', 'bottom', 'counter', 'tab']
RECT = [(0, 0, 720, 480), (0, 0, 720, 44), (0, 436, 720, 44), (612, 380, 108, 48), (0, 376, 128, 56)]
MOMENTS = {'live': 0, 'shot': 1, 'load': 2, 'roll': 3, 'none': 4}
GUARD = 0x1000
PAT = 0xA5


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    obj = OUT / 'loaded.o'
    subprocess.run([CLANG, '-target', 'armv7-none-eabi', '-mcpu=cortex-a9', '-marm', '-mfloat-abi=soft', '-mfpu=none',
                    '-Os', '-ffreestanding', '-fno-builtin', '-fno-unwind-tables', '-fno-asynchronous-unwind-tables',
                    '-fno-stack-protector', '-Wall', '-Wextra', '-Werror', '-c', str(HERE / 'loaded.c'), '-o', str(obj)], check=True)
    elf = OUT / 'loaded.elf'
    subprocess.run([LLD, '-Ttext=0x10000000', '--entry=loaded_init', '--no-undefined', str(obj), '-o', str(elf)], check=True)
    return elf


class Emu:
    STATE = 0x21000000
    BLOCK = 0x22000000
    BUF = 0x30000000

    def __init__(self, elf_path):
        self.cpu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        c = self.cpu
        c.mem_map(0x10000, 0x1000); c.mem_map(0x10000000, 0x100000); c.mem_map(0x20000000, 0x40000)
        c.mem_map(0x21000000, 0x10000); c.mem_map(0x22000000, 0x10000); c.mem_map(self.BUF, 0x600000)
        with Path(elf_path).open('rb') as f:
            elf = ELFFile(f)
            self.sections = {s.name: s['sh_size'] for s in elf.iter_sections()}
            for seg in elf.iter_segments():
                if seg['p_type'] == 'PT_LOAD':
                    c.mem_write(seg['p_vaddr'], seg.data())
            self.sym = {s.name: s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()}
        self.state = self.STATE + GUARD
        self.state_bytes = self.read32(self.sym['loaded_state_bytes'])
        # buffers: one region per view with a guard of PAT bytes on both sides
        self.base = {}
        off = GUARD
        for v, (_, _, w, h) in enumerate(RECT):
            size = w * h * 4
            self.base[v] = (self.BUF + off, size)
            off += (size + 2 * GUARD + 0xfff) & ~0xfff
        self.blocks_run = 0
        self.guard_reset()
        self.thumbs_addr = self.BUF + 0x500000
        self.cpu.mem_write(self.thumbs_addr, (OUT / 'thumbs.bin').read_bytes())
        self.hook = None
        self.counting = False

    def read32(self, addr):
        return struct.unpack('<I', bytes(self.cpu.mem_read(addr, 4)))[0]

    def guard_reset(self):
        c = self.cpu
        c.mem_write(self.STATE, bytes([PAT]) * GUARD)
        c.mem_write(self.STATE + GUARD + self.state_bytes, bytes([PAT]) * GUARD)
        for v, (addr, size) in self.base.items():
            c.mem_write(addr - GUARD, bytes([PAT]) * GUARD)
            c.mem_write(addr + size, bytes([PAT]) * GUARD)

    def zero_buffers(self):
        for v, (addr, size) in self.base.items():
            self.cpu.mem_write(addr, bytes(size))

    def guards_ok(self):
        c = self.cpu
        p = bytes([PAT]) * GUARD
        if bytes(c.mem_read(self.STATE, GUARD)) != p or bytes(c.mem_read(self.STATE + GUARD + self.state_bytes, GUARD)) != p:
            return False
        for v, (addr, size) in self.base.items():
            if bytes(c.mem_read(addr - GUARD, GUARD)) != p or bytes(c.mem_read(addr + size, GUARD)) != p:
                return False
        return True

    def call(self, name, *args):
        c = self.cpu
        c.reg_write(UC_ARM_REG_SP, 0x2003f000); c.reg_write(UC_ARM_REG_LR, 0x20000000)
        for reg, val in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3), args):
            c.reg_write(reg, val & 0xffffffff)
        c.emu_start(self.sym[name], 0x20000000, count=2_000_000_000)
        assert c.reg_read(UC_ARM_REG_PC) == 0x20000000, name + ': did not return'
        r = c.reg_read(UC_ARM_REG_R0)
        return r - (1 << 32) if r & 0x80000000 else r

    def start_counting(self):
        self.blocks_run = 0
        def hook(uc, address, size, user):
            self.blocks_run += size // 4
        if self.hook is None:
            self.hook = self.cpu.hook_add(UC_HOOK_BLOCK, hook)

    def stop_counting(self):
        if self.hook is not None:
            self.cpu.hook_del(self.hook); self.hook = None
        return self.blocks_run

    def write_buffers(self, tier, strides=None, caps=None, null=()):
        """loaded_buffers at BLOCK: pixels[5], stride[5], capacity[5]."""
        px, stride, cap = [], [], []
        for v, (_, _, w, h) in enumerate(RECT):
            s = (strides or {}).get(v, w)
            px.append(0 if v in null else self.base[v][0]); stride.append(s)
            cap.append((caps or {}).get(v, s * h))
        self.cpu.mem_write(self.BLOCK, struct.pack('<15I', *px, *stride, *cap))
        return self.BLOCK

    def write_params(self, c, thumbs_addr=None):
        t = thumbs_addr if thumbs_addr is not None else (self.thumbs_addr if c.get('thumbs') else 0)
        blob = struct.pack('<7I3i3IiI', c.get('momentId', MOMENTS[c['moment']] if 'moment' in c else 0), c['film'], c['frame'], c['roll'], c['tier'],
                           c['tabMode'], c['counterMode'], c['peek'], c['tabPeek'], c['counterPeek'], c['month'], c['year'], t, c['circled'], c.get('hold', 0))
        self.cpu.mem_write(self.BLOCK + 0x100, blob)
        return self.BLOCK + 0x100

    def view_hash(self, v, stride=None):
        addr, size = self.base[v]
        _, _, w, h = RECT[v]
        data = bytes(self.cpu.mem_read(addr, size if not stride else stride * h * 4))
        if stride and stride != w:
            data = b''.join(data[y * stride * 4:y * stride * 4 + w * 4] for y in range(h))
        return zlib.crc32(data), data

    def hashes(self, strides=None):
        return [self.view_hash(v, (strides or {}).get(v))[0] for v in range(5)]


def first_diff(case_index, view, emu, strides=None):
    subprocess.run(['node', str(HERE / 'export-parity.mjs'), '--dump', str(case_index)], check=True, cwd=str(ROOT))
    dump = (OUT / f'dump-{case_index}.bin').read_bytes()
    off = sum(w * h * 4 for (_, _, w, h) in RECT[:view])
    w, h = RECT[view][2], RECT[view][3]
    want = dump[off:off + w * h * 4]
    have = emu.view_hash(view, (strides or {}).get(view))[1]
    for i in range(0, len(want), 4):
        if want[i:i + 4] != have[i:i + 4]:
            p = i // 4
            return f'first differing pixel x={p % w} y={p // w}: js=0x{struct.unpack("<I", want[i:i + 4])[0]:08x} c=0x{struct.unpack("<I", have[i:i + 4])[0]:08x}'
    return 'pixels identical (hash only differs?)'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--quick', action='store_true')
    ap.add_argument('--limit', type=int, default=8)
    args = ap.parse_args()
    t0 = time.time()
    elf = build()
    for cmd in (['node', 'gen-native.mjs', '--check'], ['node', 'native/export-parity.mjs']):
        subprocess.run(cmd, check=True, cwd=str(ROOT))
    import json
    cases = json.loads((OUT / 'parity.json').read_text(encoding='utf8'))['cases']
    emu = Emu(elf)
    bad_sections = [n for n in ('.data', '.bss') if emu.sections.get(n, 0)]
    assert not bad_sections, f'writable sections present: {bad_sections}'
    print('sections:', {k: v for k, v in emu.sections.items() if v and k in ('.text', '.rodata', '.data', '.bss', '.ARM.exidx')},
          'state bytes', emu.state_bytes)
    emu.call('loaded_init', emu.state)
    st, mism = 0, []
    subset = cases[::4] if args.quick else cases
    compared = matched = 0
    for n, c in enumerate(subset):
        ci = cases.index(c) if args.quick else n
        emu.write_buffers(c['tier'])
        p = emu.write_params(c)
        r = emu.call('loaded_render', emu.state, emu.BLOCK, p, c['t'])
        if r != 0:
            mism.append(f'case {ci}: loaded_render returned {r}')
            continue
        if not emu.guards_ok():
            mism.append(f'case {ci}: guard canary overwritten'); break
        got = emu.hashes()
        for v in range(5):
            compared += 1
            if got[v] == c['hashes'][v]:
                matched += 1
            else:
                mism.append(f'case {ci} ({c["moment"]} film {c["film"]} frame {c["frame"]} tier {c["tier"]} t={c["t"]}) view {VIEW_NAMES[v]}: '
                            + first_diff(ci, v, emu))
        if len(mism) >= args.limit:
            break
    print(f'parity: {len(subset)} cases, {compared} view-frames compared, {matched} matched, {compared - matched} mismatched')
    for m in mism:
        print('  MISMATCH', m)
    if mism:
        sys.exit(1)
    from check_robust import run_robustness  # noqa: E402
    run_robustness(emu, cases)
    print(f'ok in {time.time() - t0:.0f}s')


if __name__ == '__main__':
    sys.path.insert(0, str(HERE))
    main()
