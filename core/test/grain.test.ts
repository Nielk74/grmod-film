// SPDX-License-Identifier: GPL-2.0-only
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { GRAIN_GAIN, grainRgb, grainSetting, grainTone, grainYC } from '../src/color/grain';
import { GRAIN_COLOUR_TILES, GRAIN_LUMA_TILES, GRAIN_TILE_SIZE } from '../src/color/grain-tables';
import { GRAIN_SOURCE_SHA256 } from '../src/fw/gr3x/grain-code';

/** The synthetic pictures of tools/grain/check.py (`test_picture`, `test_colour`). */
function testPicture(w: number, h: number, stride: number, salt: number): Uint8Array {
  const p = new Uint8Array(stride * h);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) p[y * stride + x] = (x * 7 + y * 3 + ((x * y) >> 5) + salt) & 255;
  return p;
}
function testColour(stride: number, rows: number, salt: number): Uint8Array {
  const c = new Uint8Array(stride * rows);
  for (let i = 0; i < c.length; i++) c[i] = (i * 13 + 7 + salt) & 255;
  return c;
}

describe('film grain v2 (GR III films)', () => {
  it('is the computation the ARM module was checked against (tools/grain/check.py)', () => {
    const h = createHash('sha256');
    for (const setting of [1, 2, 3, 5, 6, 7]) {
      const p = testPicture(600, 400, 608, 5), c = testColour(608, 400, 5);
      grainYC(p, c, 600, 400, 608, setting);
      h.update(p);
      h.update(c);
    }
    expect(h.digest('hex')).toBe('f22a366ec1cae0c5a6050b71827553fdadb6a3657731142316eba169fc93a806');
  });

  it('the compiled module is the one of the committed source', () => {
    const src = readFileSync(new URL('../../tools/grain/grain.c', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
    expect(createHash('sha256').update(src).digest('hex')).toBe(GRAIN_SOURCE_SHA256);
  });

  it('settings, tiles, tables and the size of the effect', () => {
    expect(grainSetting(undefined)).toBe(0);
    expect(grainSetting({ amount: 0, size: 'large' })).toBe(0);
    expect(grainSetting({ amount: 2, size: 'small' })).toBe(2);
    expect(grainSetting({ amount: 3, size: 'large' })).toBe(7);
    const N = GRAIN_TILE_SIZE;
    for (const t of [...GRAIN_LUMA_TILES, ...GRAIN_COLOUR_TILES]) expect(t.length).toBe(N * N);
    // Luma tiles: zero mean, standard deviation 32 (one unit); colour about a third of it.
    const std = (t: Uint8Array) => {
      let s = 0, s2 = 0;
      for (const b of t) { const v = (b << 24) >> 24; s += v; s2 += v * v; }
      return { mean: s / t.length, sd: Math.sqrt(s2 / t.length - (s / t.length) ** 2) };
    };
    for (const t of GRAIN_LUMA_TILES) { const { mean, sd } = std(t); expect(Math.abs(mean)).toBeLessThan(1); expect(sd).toBeGreaterThan(31); expect(sd).toBeLessThan(33); }
    for (const t of GRAIN_COLOUR_TILES) { const { sd } = std(t); expect(sd).toBeGreaterThan(6); expect(sd).toBeLessThan(18); }
    const tone = grainTone();
    expect(tone.length).toBe(512);
    for (let s = 0; s < 2; s++) {
      const t = tone.subarray(s * 256, s * 256 + 256);
      expect(t[0]).toBe(0);
      expect(t[255]).toBe(0);
      expect(t[128]).toBe(128);
      // strongest in the shadows / lower midtones, weaker in the highlights
      const peak = t.indexOf(Math.max(...t));
      expect(peak).toBeGreaterThan(30);
      expect(peak).toBeLessThan(100);
      expect(t[220]).toBeLessThan(t[128]);
    }
    expect(GRAIN_GAIN[0] < GRAIN_GAIN[1] && GRAIN_GAIN[1] < GRAIN_GAIN[2]).toBe(true);
    // Mid grey, full size: the spread is about 2.4 / 4 / 6.4 levels; black and white stay as they are.
    const spread = (setting: number) => {
      const w = 6000, h = 64, p = new Uint8Array(w * h).fill(128), c = new Uint8Array(w * h).fill(128);
      grainYC(p, c, w, h, w, setting);
      let s = 0, s2 = 0;
      for (const v of p) { s += v; s2 += v * v; }
      const m = s / p.length;
      return { sd: Math.sqrt(s2 / p.length - m * m), mean: m };
    };
    const [weak, medium, strong] = [1, 2, 3].map(spread);
    expect(weak.sd).toBeGreaterThan(2);
    expect(weak.sd).toBeLessThan(2.8);
    expect(medium.sd).toBeGreaterThan(3.5);
    expect(medium.sd).toBeLessThan(4.5);
    expect(strong.sd).toBeGreaterThan(5.8);
    expect(strong.sd).toBeLessThan(7);
    // rounded to nearest: no darkening on average
    for (const r of [weak, medium, strong]) expect(Math.abs(r.mean - 128)).toBeLessThan(0.15);
    for (const level of [0, 255]) {
      const p = new Uint8Array(6000 * 8).fill(level), c = new Uint8Array(6000 * 8).fill(100);
      grainYC(p, c, 6000, 8, 6000, 7);
      expect(p.every(v => v === level)).toBe(true);
      expect(c.every(v => v === 100)).toBe(true);
    }
  });

  it('the preview adds grain to brightness, and some to colour', () => {
    const w = 320, h = 200, rgb = new Uint8Array(w * h * 3);
    for (let i = 0; i < w * h; i++) rgb.set([120, 100, 90], i * 3);
    const before = rgb.slice();
    grainRgb(rgb, w, h, 3, 3, w);
    let changed = 0, colour = 0, sum = 0;
    for (let i = 0; i < w * h; i++) {
      const d = [0, 1, 2].map(c => rgb[i * 3 + c] - before[i * 3 + c]);
      if (d.some(v => v)) changed++;
      if (d[0] !== d[1] || d[1] !== d[2]) colour++;
      sum += (d[0] + d[1] + d[2]) / 3;
    }
    expect(changed).toBeGreaterThan(w * h / 2);
    expect(colour).toBeGreaterThan(w * h / 10);
    expect(Math.abs(sum / (w * h))).toBeLessThan(0.3);
  });
});
