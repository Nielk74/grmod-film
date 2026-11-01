// SPDX-License-Identifier: GPL-2.0-only
// Film MTF (core/src/color/filmmtf.ts, tools/filmmtf/filmmtf.c): the reference's behaviour, the generated module's source, and how the
// build puts it into the JPEG stage. The module itself is checked against this reference, byte for byte, by tools/filmmtf/check.py.
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { FILM_MTF_GAINS, FILM_MTF_MARGIN, FILM_MTF_STRIP, filmMtf, filmMtfApplies, filmMtfMatrices } from '../src/color/filmmtf';
import type { Ycc422 } from '../src/color/filmmtf';
import { FILM_MTF_CODE, FILM_MTF_CODE_LENGTH, FILM_MTF_SOURCE_SHA256 } from '../src/fw/gr3x/filmmtf-code';
import { GR3X_HALATION_FILM_STYLE, installGr3xJpegStage } from '../src/fw/gr3x/jpeg-stage';
import type { Gr3xJpegProgram } from '../src/fw/gr3x/jpeg-stage';

/** A deterministic picture with edges, lines and colour; `w` x `h`, stride `w`. */
function picture(w: number, h: number): Ycc422 {
  const y = new Uint8Array(w * h), c = new Uint8Array(w * h);
  let s = 12345;
  const rnd = () => ((s = (s * 1103515245 + 12345) >>> 0) >>> 16) / 65536;
  for (let r = 0; r < h; r++) for (let x = 0; x < w; x++) {
    y[r * w + x] = Math.max(0, Math.min(255, Math.round(128 + 60 * Math.sin(x / 9) * Math.cos(r / 7) + (((x >> 4) + (r >> 3)) & 1 ? 50 : -50) + (rnd() - 0.5) * 12)));
    c[r * w + x] = Math.max(0, Math.min(255, Math.round(128 + 50 * Math.sin(x / 31 + r / 17) + (rnd() - 0.5) * 6)));
  }
  return { y, c, width: w, height: h, stride: w };
}

/** Amplitude of the response to a horizontal luma sinusoid of f cycles/pixel (grey picture). */
function response(f: number): number {
  const w = 1024, h = 96, y = new Uint8Array(w * h), c = new Uint8Array(w * h).fill(128);
  for (let r = 0; r < h; r++) for (let x = 0; x < w; x++) y[r * w + x] = Math.round(128 + 30 * Math.sin(2 * Math.PI * f * (x + 0.5)));
  const src = Uint8Array.from(y), p: Ycc422 = { y, c, width: w, height: h, stride: w };
  expect(filmMtf(p, undefined, 64)).toBe(true);
  const row = 40;
  let sc = 0, ss = 0, ic = 0, is = 0;
  for (let x = 192; x < w - 192; x++) {
    const co = Math.cos(2 * Math.PI * f * (x + 0.5)), si = Math.sin(2 * Math.PI * f * (x + 0.5));
    sc += (p.y[row * w + x] - 128) * co; ss += (p.y[row * w + x] - 128) * si; ic += (src[row * w + x] - 128) * co; is += (src[row * w + x] - 128) * si;
  }
  return Math.hypot(sc, ss) / Math.hypot(ic, is);
}

describe('film MTF: the reference', () => {
  it('leaves a picture exactly as it was when every layer\'s gain is 1', () => {
    const p = picture(512, 400), before = { y: Uint8Array.from(p.y), c: Uint8Array.from(p.c) };
    const unit = { R: [1, 1, 1], G: [1, 1, 1], B: [1, 1, 1] };
    expect(filmMtf(p, filmMtfMatrices(unit), 64)).toBe(true);
    expect(Buffer.from(p.y).equals(Buffer.from(before.y))).toBe(true);
    expect(Buffer.from(p.c).equals(Buffer.from(before.c))).toBe(true);
  });

  it('boosts the 8..33 pixel structures of luma and rolls the finest detail off, as the film does (Kodak E-4050)', () => {
    expect(response(0.003)).toBeGreaterThan(0.97);
    expect(response(0.003)).toBeLessThan(1.04);
    expect(response(0.05)).toBeGreaterThan(1.04);
    expect(response(0.05)).toBeLessThan(1.18);
    expect(response(0.2)).toBeLessThan(0.62);
    expect(response(0.45)).toBeLessThan(0.45);
  });

  it('softens the red layer most: its gains fall to the lowest values at the finest band', () => {
    expect(FILM_MTF_GAINS.R[0]).toBeLessThan(FILM_MTF_GAINS.G[0]);
    expect(FILM_MTF_GAINS.G[0]).toBeLessThan(FILM_MTF_GAINS.B[0]);
    expect(FILM_MTF_GAINS.B[0]).toBeLessThan(0.5);
  });

  it('does the same to the picture whatever the strip boundaries do: a strip is computed with its margin', () => {
    // A picture of exactly one strip plus margin, and the same rows inside a longer picture, agree on the rows far from the picture's ends.
    const w = 256, h1 = FILM_MTF_STRIP + 2 * FILM_MTF_MARGIN, h2 = h1 + FILM_MTF_STRIP, big = picture(w, h2);
    const a: Ycc422 = { y: Uint8Array.from(big.y.subarray(0, w * h1)), c: Uint8Array.from(big.c.subarray(0, w * h1)), width: w, height: h1, stride: w };
    const b: Ycc422 = { y: Uint8Array.from(big.y), c: Uint8Array.from(big.c), width: w, height: h2, stride: w };
    filmMtf(a, undefined, 64); filmMtf(b, undefined, 64);
    let worst = 0;
    for (let r = FILM_MTF_MARGIN + 8; r < h1 - FILM_MTF_MARGIN - 8; r++) for (let x = 0; x < w; x++) worst = Math.max(worst, Math.abs(a.y[r * w + x] - b.y[r * w + x]));
    expect(worst).toBeLessThanOrEqual(1);
  });

  it('refuses pictures it does not handle (a screennail, a thumbnail, odd sizes) and changes nothing', () => {
    expect(filmMtfApplies(6000, 4000)).toBe(true);
    expect(filmMtfApplies(720, 480)).toBe(false);
    expect(filmMtfApplies(160, 120)).toBe(false);
    expect(filmMtfApplies(6001, 4000)).toBe(false);
    expect(filmMtfApplies(6000, 4004)).toBe(false);
    const p = picture(720, 480), y = Uint8Array.from(p.y);
    expect(filmMtf(p)).toBe(false);
    expect(Buffer.from(p.y).equals(Buffer.from(y))).toBe(true);
  });
});

describe('film MTF: the ARM module and its place in the JPEG stage', () => {
  it('is the module built from tools/filmmtf/filmmtf.c (run tools/filmmtf/gen.py after a change)', () => {
    const src = readFileSync(new URL('../../tools/filmmtf/filmmtf.c', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
    expect(createHash('sha256').update(src).digest('hex')).toBe(FILM_MTF_SOURCE_SHA256);
    const code = Buffer.from(FILM_MTF_CODE, 'base64');
    expect(code.length).toBe(FILM_MTF_CODE_LENGTH);
    expect(code.length % 4).toBe(0);
  });

  /** A program that records what the stage appends and in what order its stubs call each other. */
  function program() {
    const blobs: Uint8Array[] = [], stubs: { at: number; source: string }[] = [];
    let at = 0x54000000;
    const p: Gr3xJpegProgram = {
      code: (source: string) => { const a = at; at += 0x40; stubs.push({ at: a, source }); return a; },
      append: (bytes: Uint8Array) => { const a = at; at += (bytes.length + 3) & ~3; blobs.push(bytes); return a; },
      patch: () => undefined, u32: (a: number) => ({ 0x535047d4: 0xe1a0c00d, 0x535047d8: 0xe92ddff0, 0x535047ec: 0xe5914008, 0x536bbc30: 0xe30d01b4, 0x536bbcc0: 0xe1a0c00d,
        0x536bbcac: 0xe1a00001, 0x536af2a8: 0xe1a0c00d, 0x536af2e4: 0xe1a0c00d, 0x536bd838: 0xe1a0c00d, 0x536b6510: 0xe5d0300c, 0x536df3e8: 0xebfffeb7 } as Record<number, number>)[a] ?? 0,
    };
    return { p, blobs, stubs };
  }

  it('is first in the chain (before the halation and the grain), with the context the C module reads', () => {
    const { p, blobs, stubs } = program();
    const films = Array.from({ length: 20 }, (_, k) => k === 11);
    const light = Array.from({ length: 20 }, () => ({ threshold: 0, escale: 1, table: new Uint16Array(256) }));
    const entries = installGr3xJpegStage(p, { halation7: { light }, grain: { settings: films.map(() => 0), camera: true }, filmMtf: { films } })!;
    expect(entries.filmMtf).toBeDefined();
    expect(entries.halation).toBeDefined();
    const mtfStub = stubs.find(s => s.at === entries.filmMtf)!;
    expect(mtfStub.source).toContain(`bl #${entries.filmMtfModule}`);
    // the stub leaves for the halation's, which leaves for the grain's: film MTF first
    expect(mtfStub.source.trim().endsWith(`b #${entries.halation};`)).toBe(true);
    // the context: five functions, the stash, the magic, 36 Q12 matrix values, the look map (film 12 is look 32 + 11)
    const ctx = blobs.find(b => b.length === 28 + 72 + 64 && b[24] === 0x4d && b[25] === 0x54 && b[26] === 0x46 && b[27] === 0x31)!;
    expect(ctx).toBeDefined();
    const v = new DataView(ctx.buffer, ctx.byteOffset), mix = filmMtfMatrices();
    for (let i = 0; i < 36; i++) expect(v.getInt16(28 + i * 2, true)).toBe(mix[i]);
    expect(Array.from(ctx.subarray(100, 164)).map((x, i) => (x ? i : -1)).filter(i => i >= 0)).toEqual([GR3X_HALATION_FILM_STYLE + 11]);
    // the module is the generated one
    expect(blobs.some(b => b.length === FILM_MTF_CODE_LENGTH && Buffer.from(b).toString('base64') === FILM_MTF_CODE)).toBe(true);
  });

  it('needs the round 10 films (the halation\'s look map) and a flag per film', () => {
    const light = Array.from({ length: 4 }, () => ({ threshold: 0, escale: 1, table: new Uint16Array(256) }));
    expect(() => installGr3xJpegStage(program().p, { filmMtf: { films: [true, false, false, false] } })).toThrow();
    expect(() => installGr3xJpegStage(program().p, { halation7: { light }, filmMtf: { films: [true] } })).toThrow();
  });
});
