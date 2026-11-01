# SPDX-License-Identifier: GPL-2.0-only
"""Emulator check of the film MTF module (core/src/fw/gr3x/filmmtf-code.ts).

NOT part of the program. Runs the compiled module in Unicorn on a synthetic picture laid out like the
camera's (the main picture as a window of a wider buffer, a 720x480 screennail and a 160x120 thumbnail)
and checks:

  - the main picture's planes are what the TypeScript reference (core/src/color/filmmtf.ts, run by
    reference.ts) computes, byte for byte, over several strips;
  - the screennail and thumbnail, the bytes outside the picture and the context are not changed;
  - no stash, an invalid stash, a film without the film MTF, a wrong magic, a picture of another format,
    a width that is not a multiple of 8, and a heap that is too small change nothing;
  - the instruction count per megapixel (the module's cost).

    python check.py        (from the repository root; needs unicorn, numpy and node_modules)

Needs the Python packages unicorn and numpy.
"""
import base64
import json
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_SP, UC_ARM_REG_LR

ROOT = Path(__file__).resolve().parents[2]
TS = (ROOT / 'core/src/fw/gr3x/filmmtf-code.ts').read_text()
CODE = base64.b64decode(re.search(r"FILM_MTF_CODE = '([^']+)'", TS).group(1))
VITE = ROOT / 'node_modules/.bin/vite-node.cmd' if sys.platform == 'win32' else ROOT / 'node_modules/.bin/vite-node'
MAGIC = 0x3146544D
CODE_AT, CTX, STASH, CONFIG, DESC, STUB, STACK, HEAP = 0x10000, 0x60000000, 0x60002000, 0x60003000, 0x60004000, 0x70000000, 0x71000000, 0x48000000
MAIN_Y, MAIN_C, SN_Y, SN_C, TH_Y, TH_C = 0x80000000, 0x84000000, 0x90000000, 0x90100000, 0x92000000, 0x92010000


def picture(w, h, stride, seed):
    """Edges, ramps, thin lines, noise and colour: what a film MTF should visibly change."""
    rng = np.random.RandomState(seed)
    y = np.arange(h)[:, None]
    x = np.arange(w)[None, :]
    v = 128 + 60 * np.sin(x / 37.0) * np.cos(y / 23.0) + 20 * np.sin(x / 3.1 + y / 5.3)
    v = v + 70 * (((x // 97 + y // 61) & 1) * 2 - 1) * ((x % 331) < 200)
    v = v + 40 * (((x + 2 * y) % 29) < 2)
    v = v + rng.normal(0, 6, (h, w))
    plane = np.zeros((h, stride), dtype=np.uint8)
    plane[:, :w] = np.clip(v, 0, 255).astype(np.uint8)
    c = np.zeros((h, stride), dtype=np.uint8)
    cb = 128 + 50 * np.sin(x / 71.0 + y / 41.0) + 40 * (((x // 53) & 1) * 2 - 1) * ((y % 150) < 90)
    cr = 128 + 45 * np.cos(x / 53.0 - y / 29.0) + 35 * (((y // 47) & 1) * 2 - 1) * ((x % 200) < 130)
    c[:, 0:w:2] = np.clip(cb[:, 0:w:2] + rng.normal(0, 3, (h, w // 2)), 0, 255).astype(np.uint8)
    c[:, 1:w:2] = np.clip(cr[:, 0:w:2] + rng.normal(0, 3, (h, w // 2)), 0, 255).astype(np.uint8)
    return plane, c


def reference(plane, c, w, h, stride):
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        (t / 'iy').write_bytes(plane.tobytes())
        (t / 'ic').write_bytes(c.tobytes())
        r = subprocess.run([str(VITE), str(ROOT / 'tools/filmmtf/reference.ts'), '--', str(t / 'iy'), str(t / 'ic'), str(w), str(h), str(stride), str(t / 'oy'), str(t / 'oc'), str(t / 'mix')],
                           capture_output=True, text=True, cwd=ROOT)
        if r.returncode:
            sys.exit(r.stdout + r.stderr)
        info = json.loads((t / 'mix').read_text())
        return (np.frombuffer((t / 'oy').read_bytes(), dtype=np.uint8).reshape(h, stride),
                np.frombuffer((t / 'oc').read_bytes(), dtype=np.uint8).reshape(h, stride), info)


def run(mix, data, stash=0x10000 | 35, look_map=None, magic=MAGIC, fmt=1, main=(4096, 520), heap_size=0x800000, buf=(4160, 600)):
    mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    mu.mem_map(CODE_AT, 0x10000)
    mu.mem_write(CODE_AT, CODE)
    for base, size in ((CTX, 0x10000), (STUB, 0x1000), (STACK - 0x10000, 0x10000), (HEAP, 0x1000000)):
        mu.mem_map(base, size)
    bw, bh = buf
    mu.mem_map(MAIN_Y, (bw * bh + 0xFFF) & ~0xFFF)
    mu.mem_map(MAIN_C, (bw * bh + 0xFFF) & ~0xFFF)
    mu.mem_map(SN_Y, 0x200000)
    mu.mem_map(TH_Y, 0x20000)
    mw, mh = main
    ox, oy = 32, 40
    py, pc = data
    sn, th = picture(720, 480, 736, 22), picture(160, 120, 160, 33)
    planes = {'main': (MAIN_Y, MAIN_C, bytearray(py.tobytes()), bytearray(pc.tobytes())),
              'sn': (SN_Y, SN_C, bytearray(sn[0].tobytes()), bytearray(sn[1].tobytes())),
              'th': (TH_Y, TH_C, bytearray(th[0].tobytes()), bytearray(th[1].tobytes()))}
    for name, (ya, ca, y, c) in planes.items():
        mu.mem_write(ya, bytes(y))
        mu.mem_write(ca, bytes(c))
    main_y, main_c = MAIN_Y + oy * bw + ox, MAIN_C + oy * bw + ox
    for i in range(5):
        mu.mem_write(STUB + i * 16, struct.pack('<I', 0xE12FFF1E))  # bx lr
    heap = [HEAP]

    def hook(uc, addr, size, ud):
        i = (addr - STUB) // 16
        if i == 0:
            uc.reg_write(UC_ARM_REG_R0, 0x553A09C4)
        if i == 3:
            n = (uc.reg_read(UC_ARM_REG_R0) + 63) & ~63
            if heap[0] + n > HEAP + heap_size:
                uc.reg_write(UC_ARM_REG_R0, 0)
            else:
                uc.reg_write(UC_ARM_REG_R0, heap[0])
                heap[0] += n
    mu.hook_add(UC_HOOK_CODE, hook, begin=STUB, end=STUB + 0x50)
    mu.mem_write(STASH, struct.pack('<I', stash))
    lm = look_map if look_map is not None else [1 if i == 35 else 0 for i in range(64)]
    ctx = struct.pack('<7I', *(STUB + i * 16 for i in range(5)), STASH, magic) + struct.pack('<36h', *mix) + bytes(lm)
    mu.mem_write(CTX, ctx)

    def desc(a, yp, cp, w, h, stride, ch):
        mu.mem_write(a, struct.pack('<B3xIII HHHH HH 4x', fmt, yp, cp, 0, w, h, stride, ch, 0, 0))
    desc(DESC, main_y, main_c, mw, mh, bw, bh)
    desc(DESC + 0x20, SN_Y, SN_C, 720, 480, 736, 480)
    desc(DESC + 0x40, TH_Y, TH_C, 160, 120, 160, 120)
    desc(DESC + 0x60, main_y, main_c, mw, mh, bw, bh)
    mu.mem_write(CONFIG + 0x3C, struct.pack('<4I', DESC, DESC + 0x20, DESC + 0x40, DESC + 0x60))
    mu.reg_write(UC_ARM_REG_SP, STACK)
    mu.reg_write(UC_ARM_REG_LR, STUB + 0x100)
    mu.reg_write(UC_ARM_REG_R0, CTX)
    mu.reg_write(UC_ARM_REG_R1, CONFIG)
    n = [0]

    def counter(uc, addr, size, ud):
        n[0] += 1
    mu.hook_add(UC_HOOK_CODE, counter, begin=CODE_AT, end=CODE_AT + 0x10000)
    mu.emu_start(CODE_AT, STUB + 0x100, count=40_000_000_000)
    got = {name: (bytes(mu.mem_read(ya, len(y))), bytes(mu.mem_read(ca, len(c)))) for name, (ya, ca, y, c) in planes.items()}
    if bytes(mu.mem_read(CTX, len(ctx))) != ctx:
        sys.exit('the context changed')
    return planes, got, n[0], heap[0] - HEAP


def main():
    bw, bh, mw, mh = 4160, 600, 4096, 520
    ox, oy = 32, 40
    py, pc = picture(bw, bh, bw, 11)
    # the main picture is a window of the buffer; the reference sees it with the buffer's stride
    window_y = np.ascontiguousarray(py[oy:oy + mh, ox:])
    window_c = np.ascontiguousarray(pc[oy:oy + mh, ox:])
    stride = bw - ox
    ry, rc, info = reference(window_y, window_c, mw, mh, stride)
    mix = info['mix']
    failures = 0

    def same(name, got, want):
        nonlocal failures
        if got != want:
            diff = np.flatnonzero(np.frombuffer(got, np.uint8) != np.frombuffer(want, np.uint8))
            print(f'FAIL {name}: {len(diff)} bytes differ, first at {diff[:5]}')
            failures += 1
        else:
            print(f'ok   {name}')

    planes, got, instr, used = run(mix, data=(py, pc))
    full_y = bytearray(planes['main'][2])
    full_c = bytearray(planes['main'][3])
    for r in range(mh):
        a = (oy + r) * bw + ox
        full_y[a:a + mw] = ry[r, :mw].tobytes()
        full_c[a:a + mw] = rc[r, :mw].tobytes()
    same('main picture = reference, byte for byte', got['main'][0], bytes(full_y))
    same('main chroma = reference, byte for byte', got['main'][1], bytes(full_c))
    same('screennail untouched', got['sn'][0] + got['sn'][1], bytes(planes['sn'][2]) + bytes(planes['sn'][3]))
    same('thumbnail untouched', got['th'][0] + got['th'][1], bytes(planes['th'][2]) + bytes(planes['th'][3]))
    changed = np.count_nonzero(np.frombuffer(got['main'][0], np.uint8) != np.frombuffer(bytes(planes['main'][2]), np.uint8))
    print(f'     {changed} luma bytes changed; {instr / (mw * mh / 1e6) / 1e6:.0f} M instructions per megapixel; heap used {used / 1e6:.1f} MB')
    if changed < mw * mh // 4:
        print('FAIL the picture was hardly changed')
        failures += 1
    for name, kw in (('no valid stash', dict(stash=35)), ('another film', dict(stash=0x10000 | 36)), ('film without the film MTF', dict(look_map=[0] * 64)),
                     ('wrong magic', dict(magic=0x12345678)), ('another picture format', dict(fmt=2)), ('width not a multiple of 8', dict(main=(4090, 520))),
                     ('heap too small', dict(heap_size=0x100000))):
        p2, g2, *_ = run(mix, data=(py, pc), **kw)
        same(f'{name}: nothing changes', g2['main'][0] + g2['main'][1], bytes(p2['main'][2]) + bytes(p2['main'][3]))
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
