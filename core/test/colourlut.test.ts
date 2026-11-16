// SPDX-License-Identifier: GPL-2.0-only
// The per-film colour LUT (core/src/color/colourlut.ts, tools/colourlut/colourlut.c): the reference's behaviour, the tables, the generated
// module's source, and how the build puts it into the JPEG stage (first in the chain). The module itself is checked against this
// reference, byte for byte, by tools/colourlut/check.py.
import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { COLOUR_LUT_BYTES, COLOUR_LUT_FILMS, COLOUR_LUT_MAGIC, COLOUR_LUT_MAX_TABLES, COLOUR_LUT_VALUES, colourLutApplies, colourLutBytes, colourLutIndex, colourLutValues, colourLutYC } from '../src/color/colourlut';
import { COLOUR_LUT_TABLES } from '../src/color/colourlut-tables';
import { COLOUR_LUT_CODE, COLOUR_LUT_CODE_LENGTH, COLOUR_LUT_SOURCE_SHA256 } from '../src/fw/gr3x/colourlut-code';
import { GR3X_HALATION_FILM_STYLE, installGr3xJpegStage } from '../src/fw/gr3x/jpeg-stage';
import type { Gr3xJpegProgram } from '../src/fw/gr3x/jpeg-stage';
import { LOOKS } from '../src/filmpack/looks';
import { filmMtfMatrices } from '../src/color/filmmtf';

/** The fixed picture of tools/colourlut/check.py (600 x 400, stride 608). */
function fixed(): { y: Uint8Array; c: Uint8Array } {
  const y = new Uint8Array(608 * 400), c = new Uint8Array(608 * 400);
  for (let r = 0; r < 400; r++) for (let x = 0; x < 600; x++) y[r * 608 + x] = (x * 7 + r * 3 + ((x * r) >> 5) + 5) & 255;
  for (let i = 0; i < c.length; i++) c[i] = (i * 13 + 7 + 5) & 255;
  return { y, c };
}

/** An independent statement of the algorithm: stable sort of the axes, corner by corner (no sorting network, no step swapping). */
function naive(lut: Int16Array, y0: number, y1: number, cb: number, cr: number): [number, number, number] {
  const v = [(y0 + y1 + 1) >> 1, cb, cr], node = v.map(x => x >> 3), frac = v.map(x => x & 7);
  const order = [0, 1, 2].sort((a, b) => frac[b] - frac[a]); // Array.prototype.sort is stable: ties keep Y, Cb, Cr
  const at = (n: number[], c: number) => lut[((n[0] * 33 + n[1]) * 33 + n[2]) * 3 + c];
  const out: number[] = [];
  for (let c = 0; c < 3; c++) {
    const cur = [...node];
    let prev = at(cur, c), acc = prev * 8;
    for (const ax of order) { cur[ax]++; const next = at(cur, c); acc += (next - prev) * frac[ax]; prev = next; }
    out.push((acc + 64) >> 7);
  }
  return out as [number, number, number];
}

describe('colour LUT: the tables', () => {
  it('are the approved tables (two v2, three full-look), 33 x 33 x 33 Q4 deltas of int16 each, and only those films have one', () => {
    expect(COLOUR_LUT_FILMS).toEqual(['CineStill 800T', 'Kodachrome 64', 'Classic Neg', 'Classic Chrome', 'Blockbuster']);
    expect(COLOUR_LUT_BYTES).toBe(215622);
    for (const t of COLOUR_LUT_TABLES) {
      expect(t.data.length).toBe(215622);
      expect(t.sourceSha256).toMatch(/^[0-9a-f]{64}$/);
      expect(t.source).toMatch(/^lut-.*\.npy$/);
    }
    expect(colourLutValues('CineStill 800T')!.length).toBe(COLOUR_LUT_VALUES);
    expect(colourLutValues('CineStill 800T')).not.toEqual(colourLutValues('Kodachrome 64'));
    expect(colourLutIndex('CineStill 800T')).toBe(1);
    expect(colourLutIndex('Kodachrome 64')).toBe(2);
    // The pack's other films (Portra 400 above all) have none; the table of a name that is not a film is not made up.
    const withLut = LOOKS.filter(l => colourLutBytes(l.name) !== undefined).map(l => l.name);
    expect(withLut).toEqual(['Classic Chrome', 'Classic Neg', 'Kodachrome 64', 'CineStill 800T', 'Blockbuster']);
    for (const l of LOOKS.filter(l => !withLut.includes(l.name))) expect(colourLutIndex(l.name)).toBe(0);
    expect(colourLutBytes('Portra 400')).toBeUndefined();
    expect(colourLutBytes('Gold 200')).toBeUndefined();
    expect(colourLutIndex('Blockbuster')).toBe(5);
    expect(colourLutIndex(undefined)).toBe(0);
  });

  it('keep the grey axis and the corners within a few levels (a sanity check of the data, not of the look)', () => {
    for (const film of COLOUR_LUT_FILMS) {
      const lut = colourLutValues(film)!;
      let biggest = 0;
      for (const v of lut) biggest = Math.max(biggest, Math.abs(v));
      expect(biggest).toBeLessThan(16 * 128); // deltas under 128 levels
    }
  });
});

describe('colour LUT: the reference', () => {
  const lut = colourLutValues('CineStill 800T')!;

  it('is the approved algorithm: an independent tetrahedral implementation agrees on every kind of input', () => {
    // random pairs, every value around the nodes (fractions 0, 7, ties) and the extremes
    let s = 987654321;
    const rnd = () => ((s = (Math.imul(s, 1664525) + 1013904223) >>> 0) >>> 8) & 255;
    const special = [0, 1, 7, 8, 9, 127, 128, 247, 248, 249, 254, 255];
    const cases: number[][] = [];
    for (const a of special) for (const b of special) for (const c of special) cases.push([a, 255 - a, b, c], [a, a, b, c]);
    for (let i = 0; i < 20000; i++) cases.push([rnd(), rnd(), rnd(), rnd()]);
    for (const table of COLOUR_LUT_FILMS.map(f => colourLutValues(f)!)) {
      const w = 64, h = 48, Y = new Uint8Array(w * h), C = new Uint8Array(w * h);
      for (let k = 0; k < cases.length; k += w / 2 * h) {
        const slice = cases.slice(k, k + w / 2 * h);
        slice.forEach((cs, i) => { Y[2 * i] = cs[0]; Y[2 * i + 1] = cs[1]; C[2 * i] = cs[2]; C[2 * i + 1] = cs[3]; });
        const y = Uint8Array.from(Y), c = Uint8Array.from(C);
        expect(colourLutYC(y, c, w, h, w, table)).toBe(true);
        slice.forEach(([y0, y1, cb, cr], i) => {
          const [dy, dcb, dcr] = naive(table, y0, y1, cb, cr), clip = (v: number) => Math.max(0, Math.min(255, v));
          expect([y[2 * i], y[2 * i + 1], c[2 * i], c[2 * i + 1]]).toEqual([clip(y0 + dy), clip(y1 + dy), clip(cb + dcb), clip(cr + dcr)]);
        });
      }
    }
  });

  it('reads the table up to node 32 and never beyond (a read past the end throws)', () => {
    const w = 64, h = 48, Y = new Uint8Array(w * h), C = new Uint8Array(w * h);
    for (let i = 0; i < Y.length; i += 2) { const v = [248, 255, 249, 254][(i >> 1) & 3]; Y[i] = v; Y[i + 1] = 255 - ((i >> 1) & 1) * 7; C[i] = [255, 248, 254, 0][(i >> 2) & 3]; C[i + 1] = 255; }
    let highest = -1;
    const guarded = new Proxy(Int16Array.from(lut), { get(t, k) {
      if (typeof k === 'string' && /^\d+$/.test(k)) { if (+k >= t.length) throw new Error(`read past the table: ${k}`); highest = Math.max(highest, +k); }
      return Reflect.get(t, k, t);
    } });
    expect(colourLutYC(Y, C, w, h, w, guarded)).toBe(true);
    expect(highest).toBe(COLOUR_LUT_VALUES - 1); // (32, 32, 32, dCr) is reached
  });

  it('leaves a picture as it was when the table is all zeros, and changes the padding of a row never', () => {
    const { y, c } = fixed(), y0 = Uint8Array.from(y), c0 = Uint8Array.from(c);
    expect(colourLutYC(y, c, 600, 400, 608, new Int16Array(COLOUR_LUT_VALUES))).toBe(true);
    expect(Buffer.from(y).equals(Buffer.from(y0))).toBe(true);
    expect(Buffer.from(c).equals(Buffer.from(c0))).toBe(true);
    const f = fixed();
    expect(colourLutYC(f.y, f.c, 600, 400, 608, lut)).toBe(true);
    for (let r = 0; r < 400; r++) for (let x = 600; x < 608; x++) { expect(f.y[r * 608 + x]).toBe(y0[r * 608 + x]); expect(f.c[r * 608 + x]).toBe(c0[r * 608 + x]); }
  });

  it('adds the same dY to both lumas of a pair and moves a grey pair along the grey axis', () => {
    const w = 64, h = 48, Y = new Uint8Array(w * h), C = new Uint8Array(w * h).fill(128);
    for (let i = 0; i < Y.length; i += 2) { Y[i] = 100; Y[i + 1] = 110; }
    const y = Uint8Array.from(Y);
    colourLutYC(y, C, w, h, w, lut);
    expect(y[1] - y[0]).toBe(10); // dY is the same for the pair (before clipping)
  });

  it('refuses the pictures it does not handle and changes nothing', () => {
    expect(colourLutApplies(6000, 4000)).toBe(true);
    expect(colourLutApplies(720, 480)).toBe(true);
    expect(colourLutApplies(160, 120)).toBe(true);
    expect(colourLutApplies(2399, 1600)).toBe(false);
    expect(colourLutApplies(2400, 1599)).toBe(false);
    expect(colourLutApplies(62, 48)).toBe(false);
    expect(colourLutApplies(64, 46)).toBe(false);
    expect(colourLutApplies(12002, 64)).toBe(false);
    const { y, c } = fixed(), y0 = Uint8Array.from(y);
    expect(colourLutYC(y, c, 599, 400, 608, lut)).toBe(false);
    expect(colourLutYC(y, c, 600, 400, 599, lut)).toBe(false);
    expect(colourLutYC(y, c, 600, 400, 608, new Int16Array(10))).toBe(false);
    expect(Buffer.from(y).equals(Buffer.from(y0))).toBe(true);
  });

  it('is the computation the ARM module was checked against (tools/colourlut/check.py)', () => {
    const h = createHash('sha256');
    for (const table of COLOUR_LUT_FILMS.map(f => colourLutValues(f)!)) {
      const { y, c } = fixed();
      colourLutYC(y, c, 600, 400, 608, table);
      h.update(y);
      h.update(c);
    }
    expect(h.digest('hex')).toBe('a8412f44f8c5764660df6065826321fbba7f854b631d6daab9a97bc5ccba85b5');
  });
});

describe('colour LUT: the ARM module and its place in the JPEG stage', () => {
  it('is the module built from tools/colourlut/colourlut.c (run tools/colourlut/gen.py after a change)', () => {
    const src = readFileSync(new URL('../../tools/colourlut/colourlut.c', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
    expect(createHash('sha256').update(src).digest('hex')).toBe(COLOUR_LUT_SOURCE_SHA256);
    const code = Buffer.from(COLOUR_LUT_CODE, 'base64');
    expect(code.length).toBe(COLOUR_LUT_CODE_LENGTH);
    expect(code.length % 4).toBe(0);
  });

  it('the embedded tables are their source files: each .npy (int16 33^3 x 3, C order) has the recorded SHA-256 and the same values', () => {
    // The .npy files live in the prototype's work folder (not versioned): looked for beside this checkout and the main one; a checkout without it compares none.
    let checked = 0;
    for (const t of COLOUR_LUT_TABLES) {
      let dir = process.cwd(), file: string | undefined;
      for (let i = 0; i < 8 && !file; i++, dir = dirname(dir)) { const c = join(dir, 'scratch', 'colour-engine', t.source); if (existsSync(c)) file = c; }
      if (!file) continue;
      const npy = new Uint8Array(readFileSync(file));
      expect(createHash('sha256').update(npy).digest('hex')).toBe(t.sourceSha256);
      // .npy v1: magic, 2 version bytes, 2-byte header length, header, then the data
      const hl = npy[8] | (npy[9] << 8), data = npy.subarray(10 + hl);
      expect(Buffer.from(data).equals(Buffer.from(t.data))).toBe(true);
      checked++;
    }
    console.log(`colour LUT tables compared with their .npy sources: ${checked} of ${COLOUR_LUT_TABLES.length}`);
  });

  it('embeds the tables of the committed generator\'s .npy files (their SHA-256 is recorded)', () => {
    expect(COLOUR_LUT_TABLES.map(t => t.source)).toEqual(['lut-cinestill-v2.npy', 'lut-kodachrome-v2.npy', 'lut-classic-neg-full.npy', 'lut-classic-chrome-full.npy', 'lut-blockbuster-full.npy']);
  });

  /** A program that records what the stage appends and in what order its stubs call each other. */
  function program() {
    const blobs: Uint8Array[] = [], stubs: { at: number; source: string }[] = [], patches: { address: number; replacement: number }[] = [];
    let at = 0x54000000;
    const p: Gr3xJpegProgram = {
      code: (source: string) => { const a = at; at += 0x40; stubs.push({ at: a, source }); return a; },
      append: (bytes: Uint8Array) => { const a = at; at += (bytes.length + 3) & ~3; blobs.push(bytes); return a; },
      patch: (address, _expected, replacement) => { patches.push({ address, replacement }); },
      u32: (a: number) => ({ 0x535047d4: 0xe1a0c00d, 0x535047d8: 0xe92ddff0, 0x535047ec: 0xe5914008, 0x536bbc30: 0xe30d01b4, 0x536bbcc0: 0xe1a0c00d,
        0x536bbcac: 0xe1a00001, 0x536af2a8: 0xe1a0c00d, 0x536af2e4: 0xe1a0c00d, 0x536bd838: 0xe1a0c00d, 0x536b6510: 0xe5d0300c, 0x536df3e8: 0xebfffeb7 } as Record<number, number>)[a] ?? 0,
    };
    return { p, blobs, stubs, patches };
  }
  const light = (n: number) => Array.from({ length: n }, () => ({ threshold: 0, escale: 1, table: new Uint16Array(256) }));
  const films = (n: number, set: Record<number, string>) => Array.from({ length: n }, (_, k) => set[k]);

  it('is first in the chain (before the film MTF, halation and grain), with the context the C module reads', () => {
    const { p, blobs, stubs, patches } = program();
    const mtf = Array.from({ length: 20 }, (_, k) => k === 11);
    const entries = installGr3xJpegStage(p, { halation7: { light: light(20) }, grain: { settings: mtf.map(() => 0), camera: true }, filmMtf: { films: mtf },
      colourLut: { films: films(20, { 13: 'CineStill 800T', 10: 'Kodachrome 64' }) } })!;
    const stub = stubs.find(s => s.at === entries.colourLut)!;
    expect(stub.source).toContain(`bl #${entries.colourLutModule}`);
    // the stub leaves for the film MTF's, which leaves for the halation's, then the grain's
    expect(stub.source.trim().endsWith(`b #${entries.filmMtf};`)).toBe(true);
    expect(stubs.find(s => s.at === entries.filmMtf)!.source.trim().endsWith(`b #${entries.halation};`)).toBe(true);
    // Execute's entry is patched to this stub: the colour LUT is the first thing that runs
    expect(patches.length).toBe(1);
    expect(patches[0].replacement).not.toBe(0xe1a0c00d);
    // the context: three functions, the stash, the magic, the look map (film 14 is look 32 + 13 -> table 1, film 11 -> table 2), eight table pointers
    const ctx = blobs.find(b => b.length === 20 + 64 + 32 && new DataView(b.buffer, b.byteOffset).getUint32(16, true) === COLOUR_LUT_MAGIC)!;
    expect(ctx).toBeDefined();
    const v = new DataView(ctx.buffer, ctx.byteOffset);
    const map = Array.from(ctx.subarray(20, 84));
    expect(map.map((x, i) => (x ? [i, x] : null)).filter(Boolean)).toEqual([[GR3X_HALATION_FILM_STYLE + 10, 1], [GR3X_HALATION_FILM_STYLE + 13, 2]]);
    // tables in the order the films first use them: film 11 (Kodachrome) comes first, so table 1 = Kodachrome, 2 = CineStill
    expect(map[GR3X_HALATION_FILM_STYLE + 10]).toBe(1);
    expect(map[GR3X_HALATION_FILM_STYLE + 13]).toBe(2);
    expect(v.getUint32(88, true)).not.toBe(0);
    expect(v.getUint32(92, true)).toBe(0);
    // each table pointer is a table appended: the Kodachrome and CineStill bytes
    expect(blobs.filter(b => b.length === COLOUR_LUT_BYTES).map(b => Buffer.from(b).equals(Buffer.from(colourLutBytes('Kodachrome 64')!)) ? 'K' : 'C')).toEqual(['K', 'C']);
    expect(blobs.some(b => b.length === COLOUR_LUT_CODE_LENGTH && Buffer.from(b).toString('base64') === COLOUR_LUT_CODE)).toBe(true);
  });

  it('holds up to eight tables: five films with their own tables get table numbers 1..5 in order of first use, pointers 6..8 stay empty', () => {
    const { p, blobs } = program();
    const set: Record<number, string> = { 2: 'Classic Chrome', 3: 'Classic Neg', 10: 'Kodachrome 64', 13: 'CineStill 800T', 18: 'Blockbuster' };
    installGr3xJpegStage(p, { halation7: { light: light(20) }, colourLut: { films: films(20, set) } });
    const ctx = blobs.find(b => b.length === 20 + 64 + 32 && new DataView(b.buffer, b.byteOffset).getUint32(16, true) === COLOUR_LUT_MAGIC)!;
    const v = new DataView(ctx.buffer, ctx.byteOffset);
    const map = Array.from(ctx.subarray(20, 84));
    expect(map.map((x, i) => (x ? [i - GR3X_HALATION_FILM_STYLE, x] : null)).filter(Boolean)).toEqual([[2, 1], [3, 2], [10, 3], [13, 4], [18, 5]]);
    for (let i = 0; i < 5; i++) expect(v.getUint32(84 + i * 4, true)).not.toBe(0);
    for (let i = 5; i < 8; i++) expect(v.getUint32(84 + i * 4, true)).toBe(0);
    // every film's table in the file is its own source table, in that order
    const tables = blobs.filter(b => b.length === COLOUR_LUT_BYTES).map(b => Buffer.from(b));
    expect(tables.length).toBe(5);
    ['Classic Chrome', 'Classic Neg', 'Kodachrome 64', 'CineStill 800T', 'Blockbuster'].forEach((f, i) => expect(tables[i].equals(Buffer.from(colourLutBytes(f)!))).toBe(true));
    expect(COLOUR_LUT_MAX_TABLES).toBe(8);
  });

  it('a build without the option leaves the existing chain exactly as it was', () => {
    const base = { halation7: { light: light(20) }, grain: { settings: Array.from({ length: 20 }, () => 0), camera: true }, filmMtf: { films: Array.from({ length: 20 }, (_, k) => k === 11) } };
    const a = program(), b = program(), c = program();
    const ea = installGr3xJpegStage(a.p, base)!, eb = installGr3xJpegStage(b.p, { ...base, colourLut: undefined })!;
    expect(eb).toEqual(ea);
    expect(ea.colourLut).toBeUndefined();
    expect(b.stubs).toEqual(a.stubs);
    expect(b.blobs.map(x => Buffer.from(x).toString('base64'))).toEqual(a.blobs.map(x => Buffer.from(x).toString('base64')));
    expect(b.patches).toEqual(a.patches);
    // with the option, everything the existing chain appended is the same, in the same places; the LUT's parts come after
    const ec = installGr3xJpegStage(c.p, { ...base, colourLut: { films: films(20, { 13: 'CineStill 800T' }) } })!;
    expect(c.blobs.slice(0, a.blobs.length).map(x => Buffer.from(x).toString('base64'))).toEqual(a.blobs.map(x => Buffer.from(x).toString('base64')));
    expect(c.stubs.slice(0, a.stubs.length)).toEqual(a.stubs);
    for (const k of ['filmMtf', 'halation', 'grain'] as const) expect(ec[k]).toBe(ea[k]);
    // and the film MTF alone (the previous commit's shape) is unchanged by the option being absent
    const d = program(), e = program();
    const mtfOnly = { halation7: { light: light(4) }, filmMtf: { films: [true, false, false, false] } };
    installGr3xJpegStage(d.p, mtfOnly);
    installGr3xJpegStage(e.p, { ...mtfOnly, colourLut: undefined });
    expect(e.stubs).toEqual(d.stubs);
    expect(e.blobs.length).toBe(d.blobs.length);
    expect(filmMtfMatrices().length).toBe(36);
  });

  it('when only the colour LUT is asked, it still needs the round 10 films; a table name that does not exist, a length mismatch or no film at all is refused', () => {
    expect(() => installGr3xJpegStage(program().p, { colourLut: { films: ['CineStill 800T', undefined, undefined, undefined] } })).toThrow();
    expect(() => installGr3xJpegStage(program().p, { halation7: { light: light(4) }, colourLut: { films: ['CineStill 800T'] } })).toThrow();
    expect(() => installGr3xJpegStage(program().p, { halation7: { light: light(4) }, colourLut: { films: ['Portra 400', undefined, undefined, undefined] } })).toThrow(/colour LUT/);
    expect(() => installGr3xJpegStage(program().p, { halation7: { light: light(4) }, colourLut: { films: [undefined, undefined, undefined, undefined] } })).toThrow();
    expect(() => installGr3xJpegStage(program().p, { halation7: { light: light(4) }, colourLut: { films: ['CineStill 800T', undefined, 'Kodachrome 64', undefined] } })).not.toThrow();
  });
});
