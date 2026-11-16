# SPDX-License-Identifier: GPL-2.0-only
"""Emulator check of the colour LUT module (core/src/fw/gr3x/colourlut-code.ts).

NOT part of the program. Runs the compiled module in Unicorn on pictures laid out like the camera's (the
main picture as a window of a wider buffer, a 720x480 screennail with its own stride and a 160x120
thumbnail) and checks:

  - every picture's planes are what the TypeScript reference (core/src/color/colourlut.ts, run by
    reference.ts) computes, byte for byte: full-range random pictures, a sweep of the table's corners, a
    window with a custom stride, tails (widths that are not a multiple of 8) and padding; all eight table numbers;
  - the bytes around and between the pictures (canaries), the padding of every row, the context and the
    tables are not changed (the whole buffers are compared, canaries included);
  - the table is never read outside its 33 x 33 x 33 x 3 values (a hook on every read of it), and the sweep
    does reach its last value;
  - a film without a LUT, a look of 64 or more, no stash, a stash without the valid bit, a wrong magic, a
    table number beyond the eight, a null or unaligned table pointer, an unsupported format (0 and 2), an odd
    width or height, a picture that is too small, too large or whose stride is under its width change
    nothing (the reference agrees on which pictures it leaves alone);
  - the camera result equals the Python prototype (tools/colour_engine/engine.py `lut_apply_422`, with the
    approved .npy tables) on real data: genuine GR III JPEGs, converted to 4:2:2 as the prototype does;
  - the instruction count per megapixel (the module's cost).

    python tools/colourlut/check.py [--quick]      (from anywhere; needs unicorn, numpy, Pillow and node_modules)

--quick leaves out the 24-megapixel real pictures (the prototype comparison runs on a crop instead).
Locations (the prototype and the real pictures are not in git): GRMOD_COLOUR_ENGINE_DIR (tools/colour_engine),
GRMOD_COLOUR_SCRATCH (scratch/colour-engine); by default this checkout's, else the main checkout's.
"""
import base64
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_BLOCK, UC_HOOK_MEM_READ
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_SP, UC_ARM_REG_LR

ROOT = Path(__file__).resolve().parents[2]
TS = (ROOT / 'core/src/fw/gr3x/colourlut-code.ts').read_text()
CODE = base64.b64decode(re.search(r"COLOUR_LUT_CODE = '([^']+)'", TS).group(1))
TABLES_TS = (ROOT / 'core/src/color/colourlut-tables.ts').read_text()
TABLES = {m.group(1): base64.b64decode(m.group(2)) for m in re.finditer(r"film: '([^']+)', source: '[^']+', sourceSha256: '[^']+', data: b\('([^']+)'\)", TABLES_TS)}
FILMS = list(TABLES)           # table n is FILMS[n - 1]
# The eight tables the module can hold: the real ones, then copies of three of them (tables 6..8), so every table number is exercised.
TABLE_FILMS = (FILMS + [FILMS[0], FILMS[2], FILMS[4]] * 2)[:8]
TABLE_SET = [TABLES[f] for f in TABLE_FILMS]
LUT_BYTES = 33 * 33 * 33 * 3 * 2
MAGIC = 0x31554C43
VITE = None
for base in (ROOT, *ROOT.parents):
    c = base / 'node_modules/.bin' / ('vite-node.cmd' if sys.platform == 'win32' else 'vite-node')
    if c.exists():
        VITE = c
        break
CODE_AT, CTX, STASH, CONFIG, DESC, STUB, STACK = 0x10000, 0x60000000, 0x60002000, 0x60003000, 0x60004000, 0x70000000, 0x71000000
LUT_AT = [0x62000000 + i * 0x100000 for i in range(8)]   # room for the module's eight tables
N_TABLES = 8
LOOK = 32 + 3                  # film 4
VALID = 0x10000
CANARY = 0xA5
MARGIN = 0x1000


def search(env, *rel):
    cands = ([Path(os.environ[env])] if os.environ.get(env) else []) + [base / Path(*rel) for base in (ROOT, *ROOT.parents)]
    for c in cands:
        if c.exists():
            return c
    return None


ENGINE_DIR = search('GRMOD_COLOUR_ENGINE_DIR', 'tools', 'colour_engine')
SCRATCH = search('GRMOD_COLOUR_SCRATCH', 'scratch', 'colour-engine')


def reference(jobs):
    """jobs: [(film or '', w, h, stride, y bytes, c bytes)] -> ([(y, c)], [ran])"""
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        spec = []
        for i, (film, w, h, stride, y, c) in enumerate(jobs):
            (t / f'iy{i}').write_bytes(bytes(y))
            (t / f'ic{i}').write_bytes(bytes(c))
            spec.append(dict(film=film, inY=str(t / f'iy{i}'), inC=str(t / f'ic{i}'), width=w, height=h, stride=stride, outY=str(t / f'oy{i}'), outC=str(t / f'oc{i}')))
        (t / 'jobs.json').write_text(json.dumps(spec))
        r = subprocess.run([str(VITE), str(ROOT / 'tools/colourlut/reference.ts'), '--', str(t / 'jobs.json')], capture_output=True, text=True, cwd=ROOT)
        if r.returncode:
            sys.exit(r.stdout + r.stderr)
        ran = json.loads(r.stdout.strip().splitlines()[-1])
        return [(bytearray((t / f'oy{i}').read_bytes()), bytearray((t / f'oc{i}').read_bytes())) for i in range(len(jobs))], ran


def make_noise(w, h, stride, rows, seed):
    """Full-range random luma and chroma (every node of the table, every fraction), padding random too."""
    rng = np.random.RandomState(seed)
    y = rng.randint(0, 256, (rows, stride)).astype(np.uint8)
    c = rng.randint(0, 256, (rows, stride)).astype(np.uint8)
    # a smooth part as well: ramps of a photograph
    xs = np.arange(w)[None, :]
    ys = np.arange(min(h, rows))[:, None]
    half = min(h, rows) // 2
    y[:half, :w] = ((xs * 255 // max(w - 1, 1) + ys[:half] * 3) & 255).astype(np.uint8)
    c[:half, :w] = ((xs // 2 * 5 + ys[:half] * 7 + 40) & 255).astype(np.uint8)
    return y, c


SWEEP = [0, 1, 2, 7, 8, 9, 120, 127, 128, 129, 247, 248, 249, 253, 254, 255]


def make_sweep(w, h, stride, rows, seed):
    """Pairs at the table's nodes and the values around them: (Y0, Y1) x Cb x Cr, then noise."""
    y, c = make_noise(w, h, stride, rows, seed)
    n = 0
    for cb in SWEEP:
        for cr in SWEEP:
            for y0 in SWEEP:
                for y1 in (y0, 255 - y0, (y0 + 1) & 255):
                    r, x = divmod(n, w // 2)
                    n += 1
                    y[r, 2 * x], y[r, 2 * x + 1], c[r, 2 * x], c[r, 2 * x + 1] = y0, y1, cb, cr
    assert n // (w // 2) + 1 < h
    return y, c


class Pic:
    def __init__(self, name, w, h, stride, rows, y, c, ox=0, oy=0, fmt=1, c_height=None, film=None):
        self.name, self.w, self.h, self.stride, self.rows, self.ox, self.oy, self.fmt = name, w, h, stride, rows, ox, oy, fmt
        self.y, self.c = bytearray(y.tobytes()), bytearray(c.tobytes())
        self.c_height = rows - oy if c_height is None else c_height
        self.at = oy * stride + ox


def camera_pictures(main, sn_seed=22, th_seed=33, make=make_noise, fmt=1):
    """The main picture (w, h, buffer width, buffer height, ox, oy), a 720x480 screennail with stride 736 and a 160x120 thumbnail."""
    w, h, bw, bh, ox, oy = main
    pics = [Pic('main', w, h, bw, bh, *make(w, h, bw, bh, 11), ox=ox, oy=oy, fmt=fmt)]
    pics.append(Pic('sn', 720, 480, 736, 480, *make_noise(720, 480, 736, 480, sn_seed), fmt=fmt))
    pics.append(Pic('th', 160, 120, 160, 120, *make_noise(160, 120, 160, 120, th_seed), fmt=fmt))
    return pics


class Result:
    pass


def run(pics, look_map=None, stash=LOOK | VALID, magic=MAGIC, luts=None, dup=True, bounds=False, count=False, tables=None):
    """Run the module once on the pictures (config entries in order, a repeat of the first one last when `dup`)."""
    mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    mu.mem_map(CODE_AT, 0x10000)
    mu.mem_write(CODE_AT, CODE)
    for base, size in ((CTX, 0x10000), (STUB, 0x1000), (STACK - 0x10000, 0x10000)):
        mu.mem_map(base, size)
    tables = tables or TABLE_SET
    lut_regions = []
    for at, data in zip(LUT_AT, tables):
        mu.mem_map(at, 0x40000)
        mu.mem_write(at, bytes([CANARY]) * 0x40000)
        mu.mem_write(at + MARGIN, data)
        lut_regions.append((at, at + MARGIN, len(data)))
    bases, regions = [], []
    addr = 0x80000000
    for i, p in enumerate(pics):
        size = (len(p.y) + 2 * MARGIN + 0xFFF) & ~0xFFF
        ya, ca = addr, addr + size + 0x1000
        mu.mem_map(ya, size)
        mu.mem_map(ca, size)
        for a, plane in ((ya, p.y), (ca, p.c)):
            mu.mem_write(a, bytes([CANARY]) * size)
            mu.mem_write(a + MARGIN, bytes(plane))
        bases.append((ya + MARGIN, ca + MARGIN))
        regions.append((ya, ca, size))
        addr += 2 * size + 0x2000
        addr = (addr + 0xFFFFF) & ~0xFFFFF
    for i in range(5):
        mu.mem_write(STUB + i * 16, struct.pack('<I', 0xE12FFF1E))  # bx lr

    def hook(uc, a, size, ud):
        if (a - STUB) // 16 == 0:
            uc.reg_write(UC_ARM_REG_R0, 0x553A09C4)
    mu.hook_add(UC_HOOK_CODE, hook, begin=STUB, end=STUB + 0x50)
    mu.mem_write(STASH, struct.pack('<I', stash))
    lm = look_map if look_map is not None else [1 if i == LOOK else 0 for i in range(64)]
    ptrs = luts if luts is not None else ([r[1] for r in lut_regions] + [0] * N_TABLES)[:N_TABLES]
    ctx = struct.pack('<5I', STUB, STUB + 16, STUB + 32, STASH, magic) + bytes(lm) + struct.pack('<8I', *(list(ptrs) + [0] * N_TABLES)[:N_TABLES])
    mu.mem_write(CTX, ctx)
    descs = []
    for i, (p, (yb, cb)) in enumerate(zip(pics, bases)):
        d = DESC + i * 0x20
        mu.mem_write(d, struct.pack('<B3xIII HHHH HH 4x', p.fmt, yb + p.at, cb + p.at, 0, p.w, p.h, p.stride, p.c_height, 0, 0))
        descs.append(d)
    entries = descs[:4]
    if dup:  # another entry with the same planes (the whole sensor): skipped
        entries = (descs + [descs[0]] * 4)[:3] + [descs[0]]
    entries = (entries + [0, 0, 0, 0])[:4]
    mu.mem_write(CONFIG + 0x3C, struct.pack('<4I', *entries))
    res = Result()
    res.instr, res.reads, res.max_read, res.bad = 0, 0, -1, []
    if count:
        def block(uc, a, size, ud):
            res.instr += size // 4
        mu.hook_add(UC_HOOK_BLOCK, block, begin=CODE_AT, end=CODE_AT + 0x10000)
    if bounds:
        def mem(uc, access, a, size, value, ud):
            for base, start, n in lut_regions:
                if base <= a < base + 0x40000:
                    if a < start or a + size > start + n:
                        res.bad.append((a - start, size))
                    else:
                        res.max_read = max(res.max_read, a - start + size - 1)
                    res.reads += 1
        mu.hook_add(UC_HOOK_MEM_READ, mem, begin=LUT_AT[0], end=LUT_AT[-1] + 0x40000)
    mu.reg_write(UC_ARM_REG_SP, STACK)
    mu.reg_write(UC_ARM_REG_LR, STUB + 0x100)
    mu.reg_write(UC_ARM_REG_R0, CTX)
    mu.reg_write(UC_ARM_REG_R1, CONFIG)
    mu.emu_start(CODE_AT, STUB + 0x100, count=60_000_000_000)
    res.got = []
    for p, (ya, ca, size) in zip(pics, regions):
        res.got.append((bytes(mu.mem_read(ya, size)), bytes(mu.mem_read(ca, size))))
    if bytes(mu.mem_read(CTX, len(ctx))) != ctx:
        sys.exit('the context changed')
    for (at, start, n), data in zip(lut_regions, tables):
        if bytes(mu.mem_read(at, 0x40000)) != bytes([CANARY]) * MARGIN + data + bytes([CANARY]) * (0x40000 - MARGIN - n):
            sys.exit('a table changed')
    res.regions = regions
    return res


def expected(pics, films):
    """Expected region bytes (canaries, buffer) of each picture: the reference applied to the picture's window."""
    jobs = [(f, p.w, p.h, p.stride, p.y[p.at:], p.c[p.at:]) for p, f in zip(pics, films)]
    outs, ran = reference(jobs)
    exp = []
    for p, (oy, oc) in zip(pics, outs):
        y, c = bytearray(p.y), bytearray(p.c)
        y[p.at:], c[p.at:] = oy, oc
        pad = bytes([CANARY]) * MARGIN
        size = (len(p.y) + 2 * MARGIN + 0xFFF) & ~0xFFF
        tail = bytes([CANARY]) * (size - MARGIN - len(p.y))
        exp.append((pad + bytes(y) + tail, pad + bytes(c) + tail))
    return exp, ran


failures = 0
passes = 0
skips = 0


def check(label, ok, detail=''):
    global failures, passes
    if ok:
        passes += 1
        print(f'ok   {label}{(" " + detail) if detail else ""}')
    else:
        failures += 1
        print(f'FAIL {label} {detail}')


def compare(label, res, exp, pics, ran_expected=None, ran=None):
    for p, (gy, gc), (ey, ec) in zip(pics, res.got, exp):
        for what, g, e in (('Y', gy, ey), ('C', gc, ec)):
            if g == e:
                continue
            diff = np.flatnonzero(np.frombuffer(g, np.uint8) != np.frombuffer(e, np.uint8))
            check(f'{label}: {p.name} {what}', False, f'{len(diff)} bytes differ, first at buffer offset {diff[:4] - MARGIN}')
            return
    if ran_expected is not None:
        check(f'{label}: the reference handles exactly the pictures expected', ran == ran_expected, f'{ran} vs {ran_expected}')
    changed = [sum(1 for a, b in zip(g[0][MARGIN:MARGIN + len(p.y)], p.y) if a != b) if len(p.y) < 3_000_000 else int(np.count_nonzero(np.frombuffer(g[0][MARGIN:MARGIN + len(p.y)], np.uint8) != np.frombuffer(bytes(p.y), np.uint8))) for p, g in zip(pics, res.got)]
    check(f'{label}: byte for byte the reference, canaries and padding intact', True, f'(luma bytes changed per picture: {changed})')


def main():
    global failures, skips
    quick = '--quick' in sys.argv
    if VITE is None:
        sys.exit('vite-node not found (npm install)')
    t0 = time.time()
    # --- positive: both tables, a window with its own stride, the screennail and thumbnail, a repeated entry
    for table, film in enumerate(TABLE_FILMS, 1):
        lm = [table if i == LOOK else 0 for i in range(64)]
        pics = camera_pictures((2400, 1600, 2464, 1700, 32, 50))
        res = run(pics, look_map=lm)
        exp, ran = expected(pics, [film] * 3)
        compare(f'{film} (table {table}), main window + screennail + thumbnail', res, exp, pics, [True] * 3, ran)
    # --- tails and padding: widths that are not a multiple of 8, a stride far above the width, a window offset
    for main in ((2398, 1598, 2464, 1700, 36, 50), (2402, 1602, 2600, 1700, 8, 40), (66, 50, 80, 60, 4, 3)):
        pics = camera_pictures(main)
        res = run(pics)
        exp, ran = expected(pics, [FILMS[0]] * 3)
        compare(f'tails and padding, main {main[0]}x{main[1]} in {main[2]}x{main[3]} at ({main[4]},{main[5]})', res, exp, pics, [True] * 3, ran)
    # --- the table's corners and nodes, with every read of the table checked
    pics = camera_pictures((1024, 64, 1024, 64, 0, 0), make=make_sweep)
    res = run(pics, bounds=True)
    exp, ran = expected(pics, [FILMS[0]] * 3)
    compare('sweep of the table nodes', res, exp, pics, [True] * 3, ran)
    check('the table is never read outside its 107811 values', not res.bad, f'({res.reads} reads, highest byte read {res.max_read} of {LUT_BYTES - 1})')
    check('the sweep reaches the last value (node 32, 32, 32)', res.max_read == LUT_BYTES - 1)
    # --- nothing changes
    base = camera_pictures((2400, 1600, 2464, 1700, 32, 50))

    def unchanged(label, films=None, **kw):
        pics = [Pic(p.name, p.w, p.h, p.stride, p.rows, np.frombuffer(bytes(p.y), np.uint8), np.frombuffer(bytes(p.c), np.uint8), p.ox, p.oy, p.fmt, p.c_height) for p in base]
        res = run(pics, **kw)
        exp, ran = expected(pics, [''] * 3)
        same = all(g == e for gp, ep in zip(res.got, exp) for g, e in zip(gp, ep))
        check(f'{label}: nothing changes', same)
    unchanged('film without a LUT', look_map=[0] * 64)
    unchanged('other film (look 34)', stash=34 | VALID)
    unchanged('no stash', stash=0)
    unchanged('stash without the valid bit', stash=LOOK)
    unchanged('look 128 (not a film)', stash=128 | VALID)
    unchanged('look 64', stash=64 | VALID, look_map=[1] * 64)
    unchanged('wrong magic', magic=MAGIC + 1)
    unchanged('table number 9', look_map=[9 if i == LOOK else 0 for i in range(64)])
    unchanged('table number 255', look_map=[255 if i == LOOK else 0 for i in range(64)])
    unchanged('null table pointer', luts=[0, 0, 0, 0])
    unchanged('unaligned table pointer', luts=[LUT_AT[0] + MARGIN + 2, 0, 0, 0])
    unchanged('table pointer outside RAM', luts=[0x20000000, 0, 0, 0])
    # --- pictures that are not handled, with the others still handled (the reference decides which)
    # (label, change to the main picture's descriptor or size, does the reference see the problem: it does for sizes, not for lies in the descriptor)
    FILM = FILMS[0]
    for label, kw, sees in (('odd width', dict(main=(2399, 1600, 2464, 1700, 32, 50)), True), ('odd height', dict(main=(2400, 1599, 2464, 1700, 32, 50)), True),
                            ('too narrow (62)', dict(main=(62, 1600, 2464, 1700, 32, 50)), True), ('too short (46)', dict(main=(2400, 46, 2464, 1700, 32, 50)), True),
                            ('too wide (12002)', dict(main=(12002, 64, 12004, 80, 0, 0)), True), ('too tall (12002)', dict(main=(64, 12002, 80, 12004, 0, 0)), True),
                            ('stride under the width', dict(stride=2390), False), ('chroma plane shorter than the picture', dict(c_height=1599), False)):
        pics = camera_pictures(kw.get('main', (2400, 1600, 2464, 1700, 32, 50)))
        if 'stride' in kw:
            pics[0].stride = kw['stride']
        if 'c_height' in kw:
            pics[0].c_height = kw['c_height']
        res = run(pics)
        exp, ran = expected(pics, [FILM if sees else '', FILM, FILM])
        compare(f'{label}: main left alone, the others handled', res, exp, pics, [False, True, True], ran)
    pics = camera_pictures((2400, 1600, 2464, 1700, 34, 50))
    res = run(pics)
    exp, ran = expected(pics, ['', FILM, FILM])
    compare('window not 4-byte aligned (34): main left alone, the others handled', res, exp, pics, None, ran)
    for label, fmt in (('format 0', 0), ('format 2', 2), ('format 255', 255)):
        pics = camera_pictures((2400, 1600, 2464, 1700, 32, 50), fmt=fmt)
        res = run(pics)
        exp, ran = expected(pics, [''] * 3)
        compare(f'{label}: all pictures left alone', res, exp, pics, [False] * 3, ran)
    # --- instruction count: the main picture only is large; count on a 3 MP window and the small pictures
    pics = camera_pictures((2048, 1536, 2112, 1600, 32, 24))
    res = run(pics, count=True)
    exp, ran = expected(pics, [FILMS[0]] * 3)
    compare('instruction count run', res, exp, pics, [True] * 3, ran)
    mp = (2048 * 1536 + 720 * 480 + 160 * 120) / 1e6
    print(f'     {res.instr} instructions for {mp:.3f} MP of pictures: {res.instr / mp / 1e6:.1f} M instructions per megapixel '
          f'(a 24 MP main picture: {res.instr / mp * 24 / 1e9:.2f} G instructions)')
    # --- the fixed picture of core/test/colourlut.test.ts: 600 x 400, stride 608, every table; the module's output and the reference's hash
    import hashlib
    h = hashlib.sha256()
    for table, film in enumerate(FILMS, 1):
        yy, xx = np.arange(400, dtype=np.int64)[:, None], np.arange(600, dtype=np.int64)[None, :]
        py = np.zeros((400, 608), np.uint8)
        py[:, :600] = ((xx * 7 + yy * 3 + ((xx * yy) >> 5) + 5) & 255).astype(np.uint8)
        pc = ((np.arange(608 * 400, dtype=np.int64) * 13 + 7 + 5) & 255).astype(np.uint8).reshape(400, 608)
        pics = [Pic('main', 600, 400, 608, 400, py, pc)]
        res = run(pics, look_map=[table if i == LOOK else 0 for i in range(64)])
        exp, ran = expected(pics, [film])
        compare(f'fixed picture, {film}', res, exp, pics, [True], ran)
        h.update(res.got[0][0][MARGIN:MARGIN + 608 * 400])
        h.update(res.got[0][1][MARGIN:MARGIN + 608 * 400])
    print('SHA-256 of the module output on the fixed picture (every table, in order):', h.hexdigest())
    # --- real data against the Python prototype
    real(quick)
    print(f'{passes} checks passed, {failures} failed, {skips} skipped, in {time.time() - t0:.0f} s')
    if failures:
        sys.exit(f'{failures} failures')
    print('all checks passed')


def real(quick):
    global skips
    if ENGINE_DIR is None or SCRATCH is None:
        print('SKIP the comparison with the Python prototype: tools/colour_engine or scratch/colour-engine not found (GRMOD_COLOUR_ENGINE_DIR, GRMOD_COLOUR_SCRATCH)')
        skips += 1
        return
    sys.path.insert(0, str(ENGINE_DIR))
    from PIL import Image
    import engine
    img = SCRATCH / 'site' / 'img'
    # (film, table file, picture): the approved v2 tables and the camera's own "standard" renderings of real scenes
    cases = [('CineStill 800T', 'lut-cinestill-v2.npy', img / 'cinestill/AK000164/standard.jpg'),
             ('Kodachrome 64', 'lut-kodachrome-v2.npy', img / 'kodachrome/R0000023/standard.jpg'),
             ('CineStill 800T', 'lut-cinestill-v2.npy', img / 'cinestill/R0000005/standard.jpg'),
             ('Kodachrome 64', 'lut-kodachrome-v2.npy', img / 'kodachrome/R0000030/standard.jpg'),
             ('Classic Neg', 'lut-classic-neg-full.npy', img / 'cinestill/AK000164/standard.jpg'),
             ('Classic Chrome', 'lut-classic-chrome-full.npy', img / 'kodachrome/R0000023/standard.jpg'),
             ('Blockbuster', 'lut-blockbuster-full.npy', img / 'cinestill/R0000005/standard.jpg')]
    for film, npy, path in cases:
        if not path.exists() or not (SCRATCH / npy).exists():
            print(f'SKIP real data {path}: not found')
            skips += 1
            continue
        lut = np.load(SCRATCH / npy)
        if bytes(np.ascontiguousarray(lut.astype('<i2')).tobytes()) != TABLES[film]:
            check(f'{film}: the embedded table is the approved {npy}', False)
            continue
        check(f'{film}: the embedded table is the approved {npy}', True)
        rgb = np.asarray(Image.open(path).convert('RGB'))
        if quick and rgb.shape[0] > 1500:
            rgb = rgb[2000:3200]
        h, w = rgb.shape[:2]
        h -= h % 2
        w -= w % 2
        Y, Cb, Cr = engine.to_422(np.ascontiguousarray(rgb[:h, :w]))
        want_y, want_cb, want_cr = engine.lut_apply_422(Y, Cb, Cr, lut)   # the approved look
        c = np.empty((h, w), np.uint8)
        c[:, 0::2], c[:, 1::2] = Cb, Cr
        stride = w + 64
        py, pc = np.zeros((h, stride), np.uint8), np.zeros((h, stride), np.uint8)
        py[:, :w], pc[:, :w] = Y, c
        pad = np.random.RandomState(5).randint(0, 256, (h, 64)).astype(np.uint8)
        py[:, w:], pc[:, w:] = pad, pad[::-1]
        lm = [FILMS.index(film) + 1 if i == LOOK else 0 for i in range(64)]
        pics = [Pic('main', w, h, stride, h, py, pc)]
        t = time.time()
        res = run(pics, look_map=lm, dup=False, count=True)
        gy = np.frombuffer(res.got[0][0][MARGIN:MARGIN + len(pics[0].y)], np.uint8).reshape(h, stride)
        gc = np.frombuffer(res.got[0][1][MARGIN:MARGIN + len(pics[0].c)], np.uint8).reshape(h, stride)
        ok_y = np.array_equal(gy[:, :w], want_y)
        ok_cb = np.array_equal(gc[:, 0:w:2], want_cb)
        ok_cr = np.array_equal(gc[:, 1:w:2], want_cr)
        ok_pad = np.array_equal(gy[:, w:], pad) and np.array_equal(gc[:, w:], pad[::-1])
        ok_can = res.got[0][0][:MARGIN] == bytes([CANARY]) * MARGIN and res.got[0][0][MARGIN + len(pics[0].y):] == bytes([CANARY]) * (len(res.got[0][0]) - MARGIN - len(pics[0].y))
        moved = int(np.count_nonzero(want_y != Y))
        check(f'real data {path.parent.parent.name}/{path.parent.name} {w}x{h} + {film}: camera = prototype lut_apply_422, byte for byte',
              ok_y and ok_cb and ok_cr and ok_pad and ok_can,
              f'(Y {ok_y}, Cb {ok_cb}, Cr {ok_cr}, padding {ok_pad}, canaries {ok_can}; {moved} of {w * h} luma values moved by the LUT; '
              f'{res.instr / (w * h / 1e6) / 1e6:.1f} M instr/MP; {time.time() - t:.0f} s)')


if __name__ == '__main__':
    main()
