# SPDX-License-Identifier: GPL-2.0-only
"""Emulator check of the grain module (core/src/fw/gr3x/grain-code.ts).

NOT part of the program. Runs the compiled module in Unicorn on synthetic pictures laid out like the
camera's (the main picture as a window of a wider buffer, a 720x480 screennail and a 160x120
thumbnail) and checks:

  - every grain setting (Weak / Medium / Strong, small / large): each picture's brightness is what
    the reference below computes (the same steps as core/src/color/grain.ts), byte for byte;
  - the colour plane, the buffer outside the pictures and the context are not changed;
  - no stash, an invalid stash, a look without grain, a wrong magic and a picture of another format
    change nothing;
  - the reference of the fixed test picture, whose SHA-256 core/test/grain.test.ts compares with
    the TypeScript reference.

    python3 check.py

Needs the Python packages unicorn and numpy.
"""
import base64
import hashlib
import math
import re
import struct
import sys
from pathlib import Path

import numpy as np
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_SP, UC_ARM_REG_LR

ROOT = Path(__file__).resolve().parents[2]
TS = (ROOT / 'core/src/fw/gr3x/grain-code.ts').read_text()
CODE = base64.b64decode(re.search(r"GRAIN_CODE = '([^']+)'", TS).group(1))
AMOUNT = [9, 15, 24]
CELL = [320, 576]
MAGIC = 0x314E5247
M32 = 0xFFFFFFFF


def tone():
    out = bytearray(3 * 256)
    spread = [0.7, 0.62, 0.5]
    for a in range(3):
        for y in range(256):
            u = (y / 255) ** 0.8
            bell = math.sin(math.pi * u)
            out[a * 256 + y] = int(math.floor(255 * max(0.0, bell) ** spread[a] + 0.5))
    return bytes(out)


TONE = tone()


def noise_row(n, j, seed):
    i = np.arange(n, dtype=np.uint64)
    h = ((i * 0x9E3779B1) & M32) ^ ((j * 0x85EBCA77) & M32) ^ seed
    h ^= h >> 15
    h = (h * 0x2C1B3C6D) & M32
    h ^= h >> 12
    h = (h * 0x297A2D39) & M32
    h ^= h >> 15
    return ((h & 0xFF) + ((h >> 8) & 0xFF)).astype(np.int64) - 255


def reference(Y, w, h, stride, setting):
    """Y: bytearray of the plane (rows `stride` apart), changed in place."""
    amount, size = setting & 3, (setting >> 2) & 1
    if not amount:
        return
    cell, att = (CELL[size] * w) // 6000, 256
    if cell < 256:
        att, cell = cell, 256
    gain = (AMOUNT[amount - 1] * att) >> 8
    if not gain:
        return
    step = (256 << 16) // cell
    nx = ((w * step) >> 16) + 3
    seed = (w * 0x10001 + h) & M32
    for y in range(8):
        seed = ((seed * 0x01000193) & M32) ^ Y[((h * y) >> 3) * stride + ((w * (7 - y)) >> 3)]
    t = np.frombuffer(TONE, dtype=np.uint8)[(amount - 1) * 256:amount * 256].astype(np.int64)
    ra, rb, j0 = noise_row(nx, 0, seed), noise_row(nx, 1, seed), 0
    px = np.arange(w, dtype=np.int64) * step
    li, fx = px >> 16, (px >> 8) & 255
    for y in range(h):
        py = y * step
        j, fy = py >> 16, (py >> 8) & 255
        while j0 < j:
            ra, rb = rb, noise_row(nx, j0 + 2, seed)
            j0 += 1
        mix = ra * 256 + (rb - ra) * fy
        v = (mix[li] * (256 - fx) + mix[li + 1] * fx) >> 16
        row = np.frombuffer(bytes(Y[y * stride:y * stride + w]), dtype=np.uint8).astype(np.int64)
        out = row + ((v * gain * t[row]) >> 16)
        Y[y * stride:y * stride + w] = np.clip(out, 0, 255).astype(np.uint8).tobytes()


def test_picture(w, h, stride, salt=0):
    y = np.arange(h, dtype=np.int64)[:, None]
    x = np.arange(w, dtype=np.int64)[None, :]
    v = (x * 7 + y * 3 + ((x * y) >> 5) + salt) & 255
    plane = np.zeros((h, stride), dtype=np.uint8)
    plane[:, :w] = v
    return bytearray(plane.tobytes())


CODE_AT, CTX, TONE_AT, STASH, CONFIG, DESC, STUB, STACK, HEAP = 0x10000, 0x60000000, 0x60001000, 0x60002000, 0x60003000, 0x60004000, 0x70000000, 0x71000000, 0x48000000
MAIN_Y, MAIN_C, SN_Y, SN_C, TH_Y, TH_C = 0x80000000, 0x84000000, 0x90000000, 0x90100000, 0x92000000, 0x92010000
BUF_W, BUF_H = 2464, 1700


def run(stash, look_map, magic=MAGIC, fmt=1, main=(2400, 1600)):
    mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    mu.mem_map(CODE_AT, 0x10000)
    mu.mem_write(CODE_AT, CODE)
    for base, size in ((CTX, 0x10000), (STUB, 0x1000), (STACK - 0x10000, 0x10000), (HEAP, 0x400000)):
        mu.mem_map(base, size)
    mu.mem_map(MAIN_Y, (BUF_W * BUF_H + 0xFFF) & ~0xFFF)
    mu.mem_map(MAIN_C, (BUF_W * BUF_H + 0xFFF) & ~0xFFF)
    mu.mem_map(SN_Y, 0x200000)
    mu.mem_map(TH_Y, 0x20000)
    mw, mh = main
    planes = {
        'main': (MAIN_Y, MAIN_C, test_picture(BUF_W, BUF_H, BUF_W, 11), BUF_W, BUF_H),
        'sn': (SN_Y, SN_C, test_picture(720, 480, 736, 22), 736, 480),
        'th': (TH_Y, TH_C, test_picture(160, 120, 160, 33), 160, 120),
    }
    chroma = {}
    for name, (ya, ca, plane, stride, rows) in planes.items():
        mu.mem_write(ya, bytes(plane))
        c = bytes((i * 13 + 7) & 255 for i in range(stride * rows))
        mu.mem_write(ca, c)
        chroma[name] = c
    ox, oy = 32, 50
    main_y = MAIN_Y + oy * BUF_W + ox
    for i in range(5):
        mu.mem_write(STUB + i * 16, struct.pack('<I', 0xE12FFF1E))  # bx lr
    heap = [HEAP]

    def hook(uc, addr, size, ud):
        i = (addr - STUB) // 16
        if i == 0:
            uc.reg_write(UC_ARM_REG_R0, 0x553A09C4)
        if i == 3:
            n = (uc.reg_read(UC_ARM_REG_R0) + 63) & ~63
            uc.reg_write(UC_ARM_REG_R0, heap[0])
            heap[0] += n
    mu.hook_add(UC_HOOK_CODE, hook, begin=STUB, end=STUB + 0x50)
    mu.mem_write(TONE_AT, TONE)
    mu.mem_write(STASH, struct.pack('<I', stash))
    ctx = struct.pack('<8I', *(STUB + i * 16 for i in range(5)), STASH, TONE_AT, 0)[:28] + \
        struct.pack('<3H2H2xI', *AMOUNT, *CELL, magic) + bytes(look_map)
    mu.mem_write(CTX, ctx)

    def desc(a, yp, cp, w, h, stride, ch):
        mu.mem_write(a, struct.pack('<B3xIII HHHH HH 4x', fmt, yp, cp, 0, w, h, stride, ch, 0, 0))
    desc(DESC, main_y, MAIN_C + oy * BUF_W + ox, mw, mh, BUF_W, BUF_H)
    desc(DESC + 0x20, SN_Y, SN_C, 720, 480, 736, 480)
    desc(DESC + 0x40, TH_Y, TH_C, 160, 120, 160, 120)
    # A fourth entry describing the main picture's planes again (the whole sensor): skipped.
    desc(DESC + 0x60, main_y, MAIN_C + oy * BUF_W + ox, mw, mh, BUF_W, BUF_H)
    mu.mem_write(CONFIG + 0x3C, struct.pack('<4I', DESC, DESC + 0x20, DESC + 0x40, DESC + 0x60))
    mu.reg_write(UC_ARM_REG_SP, STACK)
    mu.reg_write(UC_ARM_REG_LR, STUB + 0x100)
    mu.reg_write(UC_ARM_REG_R0, CTX)
    mu.reg_write(UC_ARM_REG_R1, CONFIG)
    mu.emu_start(CODE_AT, STUB + 0x100, count=4_000_000_000)
    got = {name: bytearray(mu.mem_read(ya, len(plane))) for name, (ya, ca, plane, stride, rows) in planes.items()}
    for name, (ya, ca, plane, stride, rows) in planes.items():
        if bytes(mu.mem_read(ca, len(chroma[name]))) != chroma[name]:
            sys.exit(f'{name}: the colour plane changed')
    if bytes(mu.mem_read(CTX, len(ctx))) != ctx:
        sys.exit('the context changed')
    return planes, got, (ox, oy, mw, mh)


def expected(planes, setting, window):
    ox, oy, mw, mh = window
    out = {}
    for name, (ya, ca, plane, stride, rows) in planes.items():
        p = bytearray(plane)
        if name == 'main':
            sub = bytearray(p[oy * stride + ox:])
            reference(sub, mw, mh, stride, setting)
            p[oy * stride + ox:] = sub
        elif name == 'sn':
            reference(p, 720, 480, stride, setting)
        else:
            reference(p, 160, 120, stride, setting)
        out[name] = p
    return out


def main():
    failures = 0
    look = 32 + 3          # film 4
    for setting in (1, 2, 3, 5, 6, 7):
        lm = bytearray(64)
        lm[look] = setting
        planes, got, window = run(look | 0x10000 | (2 << 8), lm)
        want = expected(planes, setting, window)
        for name in got:
            changed = sum(1 for a, b in zip(planes[name][2], got[name]) if a != b)
            if got[name] != want[name]:
                bad = next(i for i, (a, b) in enumerate(zip(got[name], want[name])) if a != b)
                print(f'setting {setting} {name}: MISMATCH at byte {bad}: {got[name][bad]} != {want[name][bad]}')
                failures += 1
            else:
                print(f'setting {setting} {name}: identical ({changed} bytes changed)')
    nothing = [
        ('no stash', 0, None, MAGIC, 1),
        ('stash without valid bit', look, None, MAGIC, 1),
        ('look without grain', 32 | 0x10000, None, MAGIC, 1),
        ('wrong magic', look | 0x10000, None, MAGIC + 1, 1),
        ('other format', look | 0x10000, None, MAGIC, 2),
    ]
    for label, stash, _, magic, fmt in nothing:
        lm = bytearray(64)
        lm[look] = 3
        planes, got, _ = run(stash, lm, magic, fmt)
        same = all(got[n] == planes[n][2] for n in got)
        print(f'{label}: {"unchanged" if same else "CHANGED"}')
        failures += 0 if same else 1
    # The fixed picture of core/test/grain.test.ts: 600 x 400, stride 608, every setting.
    h = hashlib.sha256()
    for setting in (1, 2, 3, 5, 6, 7):
        p = test_picture(600, 400, 608, 5)
        reference(p, 600, 400, 608, setting)
        h.update(bytes(p))
    print('reference SHA-256 of the test picture:', h.hexdigest())
    if failures:
        sys.exit(f'{failures} failures')
    print('all checks passed')


if __name__ == '__main__':
    main()
