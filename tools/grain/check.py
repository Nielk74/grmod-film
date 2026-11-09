# SPDX-License-Identifier: GPL-2.0-only
"""Emulator check of the grain module v2 (core/src/fw/gr3x/grain-code.ts).

NOT part of the program. Runs the compiled module in Unicorn on synthetic pictures laid out like the
camera's (the main picture as a window of a wider buffer, a 720x480 screennail and a 160x120
thumbnail) and checks:

  - every grain setting (Weak / Medium / Strong, small / large): each picture's brightness and
    colour planes are what the reference below computes (the same steps as core/src/color/grain.ts),
    byte for byte;
  - the buffers outside the pictures, the tiles and the context are not changed;
  - no stash, an invalid stash, a look without grain, a wrong magic and a picture of another format
    change nothing;
  - the reference of the fixed test picture, whose SHA-256 core/test/grain.test.ts compares with
    the TypeScript reference.

    python3 check.py

Needs the Python packages unicorn and numpy.
"""
import base64
import hashlib
import re
import struct
import sys
from pathlib import Path

import numpy as np
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_SP, UC_ARM_REG_LR

ROOT = Path(__file__).resolve().parents[2]
TS = (ROOT / 'core/src/fw/gr3x/grain-code.ts').read_text(encoding='utf-8')
CODE = base64.b64decode(re.search(r"GRAIN_CODE = '([^']+)'", TS).group(1))
TABLES = (ROOT / 'core/src/color/grain-tables.ts').read_text(encoding='utf-8')


def blobs(name):
    block = re.search(name + r": readonly Uint8Array\[\] = \[(.*?)\];", TABLES, re.S).group(1)
    return [base64.b64decode(s) for s in re.findall(r"b\('([^']+)'\)", block)]


LUMA, COLOUR, TONES = blobs('GRAIN_LUMA_TILES'), blobs('GRAIN_COLOUR_TILES'), blobs('GRAIN_TONES')
GAIN = [38, 64, 102]
MAGIC = 0x324E5247
M32 = 0xFFFFFFFF
T = 128


def offset(i, j, seed):
    i = np.asarray(i, dtype=np.uint64)
    h = ((i * 0x9E3779B1) & M32) ^ ((j * 0x85EBCA77) & M32) ^ seed
    h ^= h >> 15
    h = (h * 0x2C1B3C6D) & M32
    h ^= h >> 12
    h = (h * 0x297A2D39) & M32
    h ^= h >> 15
    return (h & 0x7F7F).astype(np.int64)


def reference(Y, C, w, h, stride, setting, mode=0, main=None):
    """Y, C: bytearrays of the planes (rows `stride` apart), changed in place."""
    amount, size = setting & 3, (setting >> 2) & 1
    if not amount:
        return
    reference2 = 12000
    if mode == 1 and main and max(main) >= 1280:
        reference2 = max(2 * main[0], 3 * main[1])
    step = (reference2 << 8) // max(2 * w, 3 * h) if mode else (6000 << 8) // w
    att = 65536 // step if step > 256 else 256
    gain = (GAIN[amount - 1] * att) >> 8
    if not gain:
        return
    tone = np.frombuffer(TONES[size], dtype=np.uint8).astype(np.int64)
    lt = np.frombuffer(LUMA[size], dtype=np.int8).astype(np.int64)
    ct = np.frombuffer(COLOUR[size], dtype=np.int8).astype(np.int64)
    seed = (w * 0x10001 + h) & M32
    for y in range(8):
        seed = ((seed * 0x01000193) & M32) ^ Y[((h * y) >> 3) * stride + ((w * (7 - y)) >> 3)]
    nbx = (w + 31) >> 5
    x = np.arange(w, dtype=np.int64)
    even = np.flatnonzero(((x & 1) == 0) & (x + 1 < w))
    for y in range(h):
        if not y & 31:
            offs = offset(np.arange(nbx), y >> 5, seed)
        o = offs[x >> 5]
        ty = ((o >> 8) + (((y & 31) * step) >> 8)) & (T - 1)
        tx = (o + (((x & 31) * step) >> 8)) & (T - 1)
        row = np.frombuffer(bytes(Y[y * stride:y * stride + w]), dtype=np.uint8).astype(np.int64)
        f = gain * tone[row]
        Y[y * stride:y * stride + w] = np.clip(row + ((lt[ty * T + tx] * f + 32768) >> 16), 0, 255).astype(np.uint8).tobytes()
        crow = np.frombuffer(bytes(C[y * stride:y * stride + w]), dtype=np.uint8).astype(np.int64).copy()
        c = ty[even] * T + (tx[even] & ~1)
        crow[even] = np.clip(crow[even] + ((ct[c] * f[even] + 32768) >> 16), 0, 255)
        crow[even + 1] = np.clip(crow[even + 1] + ((ct[c + 1] * f[even] + 32768) >> 16), 0, 255)
        C[y * stride:y * stride + w] = crow.astype(np.uint8).tobytes()


def test_picture(w, h, stride, salt=0):
    y = np.arange(h, dtype=np.int64)[:, None]
    x = np.arange(w, dtype=np.int64)[None, :]
    v = (x * 7 + y * 3 + ((x * y) >> 5) + salt) & 255
    plane = np.zeros((h, stride), dtype=np.uint8)
    plane[:, :w] = v
    return bytearray(plane.tobytes())


def test_colour(stride, rows, salt=0):
    return bytearray(bytes((i * 13 + 7 + salt) & 255 for i in range(stride * rows)))


CODE_AT, CTX, TONE_AT, STASH, CONFIG, DESC, STUB, STACK, HEAP, TILES = 0x10000, 0x60000000, 0x60001000, 0x60002000, 0x60003000, 0x60004000, 0x70000000, 0x71000000, 0x48000000, 0x62000000
MAIN_Y, MAIN_C, SN_Y, SN_C, TH_Y, TH_C = 0x80000000, 0x84000000, 0x90000000, 0x90100000, 0x92000000, 0x92010000
BUF_W, BUF_H = 2464, 1700


def run(stash, look_map, magic=MAGIC, fmt=1, main=(2400, 1600), mode=0, primary="valid", heap_limit=0x400000):
    bw, bh = main[0] + 64, main[1] + 100
    mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    mu.mem_map(CODE_AT, 0x10000)
    mu.mem_write(CODE_AT, CODE)
    for base, size in ((CTX, 0x10000), (STUB, 0x1000), (STACK - 0x10000, 0x10000), (HEAP, 0x400000), (TILES, 0x20000)):
        mu.mem_map(base, size)
    mu.mem_map(MAIN_Y, (bw * bh + 0xFFF) & ~0xFFF)
    mu.mem_map(MAIN_C, (bw * bh + 0xFFF) & ~0xFFF)
    mu.mem_map(SN_Y, 0x200000)
    mu.mem_map(TH_Y, 0x20000)
    mw, mh = main
    planes = {
        'main': (MAIN_Y, MAIN_C, test_picture(bw, bh, bw, 11), test_colour(bw, bh, 1), bw, bh),
        'sn': (SN_Y, SN_C, test_picture(720, 480, 736, 22), test_colour(736, 480, 2), 736, 480),
        'th': (TH_Y, TH_C, test_picture(160, 120, 160, 33), test_colour(160, 120, 3), 160, 120),
    }
    for name, (ya, ca, plane, colour, stride, rows) in planes.items():
        mu.mem_write(ya, bytes(plane))
        mu.mem_write(ca, bytes(colour))
    ox, oy = 32, 50
    main_y = MAIN_Y + oy * bw + ox
    for i in range(5):
        mu.mem_write(STUB + i * 16, struct.pack('<I', 0xE12FFF1E))  # bx lr
    heap = [HEAP]

    def hook(uc, addr, size, ud):
        i = (addr - STUB) // 16
        if i == 0:
            uc.reg_write(UC_ARM_REG_R0, 0x553A09C4)
        if i == 3:
            n = (uc.reg_read(UC_ARM_REG_R0) + 63) & ~63
            uc.reg_write(UC_ARM_REG_R0, heap[0] if heap[0] + n <= HEAP + heap_limit else 0)
            heap[0] += n
    mu.hook_add(UC_HOOK_CODE, hook, begin=STUB, end=STUB + 0x50)
    mu.mem_write(TONE_AT, TONES[0] + TONES[1])
    tile_at = [TILES + i * 0x4000 for i in range(4)]
    for at, data in zip(tile_at, LUMA + COLOUR):
        mu.mem_write(at, data)
    mu.mem_write(STASH, struct.pack('<I', stash))
    ctx = struct.pack('<7I', *(STUB + i * 16 for i in range(5)), STASH, TONE_AT) + \
        struct.pack('<4HI', *GAIN, mode, magic) + bytes(look_map) + struct.pack('<4I', *tile_at)
    mu.mem_write(CTX, ctx)

    def desc(a, yp, cp, w, h, stride, ch, form=fmt):
        mu.mem_write(a, struct.pack('<B3xIII HHHH HH 4x', form, yp, cp, 0, w, h, stride, ch, 0, 0))
    desc(DESC, main_y, MAIN_C + oy * bw + ox, mw, mh, bw, bh, 2 if primary == "invalid" else fmt)
    desc(DESC + 0x20, SN_Y, SN_C, 720, 480, 736, 480)
    desc(DESC + 0x40, TH_Y, TH_C, 160, 120, 160, 120)
    # A fourth entry describing the main picture's planes again (the whole sensor): skipped.
    desc(DESC + 0x60, main_y, MAIN_C + oy * bw + ox, mw + 32 if primary == "valid" else mw, mh, bw, bh)
    mu.mem_write(CONFIG + 0x3C, struct.pack('<4I', 0 if primary == 'missing' else DESC + 0x20 if primary == 'preview' else DESC, DESC + 0x20, DESC + 0x40, DESC + 0x60))
    descriptors_before = bytes(mu.mem_read(DESC, 0x80))
    mu.reg_write(UC_ARM_REG_SP, STACK)
    mu.reg_write(UC_ARM_REG_LR, STUB + 0x100)
    mu.reg_write(UC_ARM_REG_R0, CTX)
    mu.reg_write(UC_ARM_REG_R1, CONFIG)
    mu.emu_start(CODE_AT, STUB + 0x100, count=8_000_000_000)
    got = {name: (bytearray(mu.mem_read(ya, len(plane))), bytearray(mu.mem_read(ca, len(colour))))
           for name, (ya, ca, plane, colour, stride, rows) in planes.items()}
    if bytes(mu.mem_read(DESC, 0x80)) != descriptors_before:
        sys.exit('descriptors changed')
    if bytes(mu.mem_read(CTX, len(ctx))) != ctx:
        sys.exit('the context changed')
    for at, data in zip(tile_at, LUMA + COLOUR):
        if bytes(mu.mem_read(at, len(data))) != data:
            sys.exit('a tile changed')
    return planes, got, (ox, oy, mw, mh)


def expected(planes, setting, window, mode=0, primary="valid"):
    main = window[2:] if primary == "valid" else None
    ox, oy, mw, mh = window
    out = {}
    for name, (ya, ca, plane, colour, stride, rows) in planes.items():
        p, c = bytearray(plane), bytearray(colour)
        if name == 'main':
            at = oy * stride + ox
            sy, sc = bytearray(p[at:]), bytearray(c[at:])
            reference(sy, sc, mw, mh, stride, setting, mode, main)
            p[at:], c[at:] = sy, sc
        elif name == 'sn':
            reference(p, c, 720, 480, stride, setting, mode, main)
        else:
            reference(p, c, 160, 120, stride, setting, mode, main)
        out[name] = (p, c)
    return out


def main():
    failures = 0
    look = 32 + 3          # film 4
    for mode in (0, 1, 2):
        for setting in (1, 2, 3, 5, 6, 7):
            lm = bytearray(64)
            lm[look] = setting
            planes, got, window = run(look | 0x10000 | (2 << 8), lm, mode=mode)
            want = expected(planes, setting, window, mode)
            for name in got:
                for k, label in ((0, 'Y'), (1, 'C')):
                    before = planes[name][2 + k]
                    changed = sum(1 for a, b in zip(before, got[name][k]) if a != b)
                    if got[name][k] != want[name][k]:
                        bad = next(i for i, (a, b) in enumerate(zip(got[name][k], want[name][k])) if a != b)
                        print(f'mode {mode} setting {setting} {name} {label}: MISMATCH at byte {bad}: {got[name][k][bad]} != {want[name][k][bad]}')
                        failures += 1
                    else:
                        print(f'mode {mode} setting {setting} {name} {label}: identical ({changed} bytes changed)')
    nothing = [
        ('no stash', 0, MAGIC, 1),
        ('stash without valid bit', look, MAGIC, 1),
        ('look without grain', 32 | 0x10000, MAGIC, 1),
        ('wrong magic', look | 0x10000, MAGIC + 1, 1),
        ('other format', look | 0x10000, MAGIC, 2),
    ]
    for label, stash, magic, fmt in nothing:
        lm = bytearray(64)
        lm[look] = 3
        planes, got, _ = run(stash, lm, magic, fmt)
        same = all(got[n][0] == planes[n][2] and got[n][1] == planes[n][3] for n in got)
        print(f'{label}: {"unchanged" if same else "CHANGED"}')
        failures += 0 if same else 1
    lm = bytearray(64); lm[look] = 6
    for primary in ['missing', 'invalid', 'preview']:
        planes, got, window = run(look | 0x10000, lm, mode=1, primary=primary, main=(1280, 64))
        want = expected(planes, 6, window, 1, primary)
        assert got == want, f'{primary} primary must use output reference and process valid fallback'
        print(f'{primary} primary: output reference with valid fallback, buffers identical')
    planes, got, _ = run(look | 0x10000, lm, mode=1, heap_limit=0, main=(1280, 64))
    assert all(got[n] == (planes[n][2], planes[n][3]) for n in got), 'allocation failure wrote buffers'
    print('allocation failure: all buffers unchanged')
    for main in [(1280, 1280), (960, 1280), (640, 1280)]:
        for mode in [1, 2]:
            planes, got, window = run(look | 0x10000, lm, mode=mode, main=main)
            assert got == expected(planes, 6, window, mode), (main, mode)
        print(f'{main} square/portrait main: both policies match, previews inherit primary')
    # The fixed picture of core/test/grain.test.ts: 600 x 400, stride 608, every setting.
    h = hashlib.sha256()
    for setting in (1, 2, 3, 5, 6, 7):
        p, c = test_picture(600, 400, 608, 5), test_colour(608, 400, 5)
        reference(p, c, 600, 400, 608, setting)
        h.update(bytes(p))
        h.update(bytes(c))
    print('reference SHA-256 of the test picture:', h.hexdigest())
    if failures:
        sys.exit(f'{failures} failures')
    print('all checks passed')


if __name__ == '__main__':
    main()
