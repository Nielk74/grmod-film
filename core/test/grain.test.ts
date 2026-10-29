// SPDX-License-Identifier: GPL-2.0-only
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { GRAIN_AMOUNT, GRAIN_CELL, grainRgb, grainSetting, grainTone, grainY } from '../src/color/grain';
import { GRAIN_SOURCE_SHA256 } from '../src/fw/gr3x/grain-code';

/** The synthetic picture of tools/grain/check.py (`test_picture`). */
function testPicture(w: number, h: number, stride: number, salt: number): Uint8Array {
  const p = new Uint8Array(stride * h);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) p[y * stride + x] = (x * 7 + y * 3 + ((x * y) >> 5) + salt) & 255;
  return p;
}

describe('film grain (GR III films)', () => {
  it('is the computation the ARM module was checked against (tools/grain/check.py)', () => {
    const h = createHash('sha256');
    for (const setting of [1, 2, 3, 5, 6, 7]) {
      const p = testPicture(600, 400, 608, 5);
      grainY(p, 600, 400, 608, setting);
      h.update(p);
    }
    expect(h.digest('hex')).toBe('bf343074092a7fa1d6975e0366cfa2b0d4f56f3f36af9a1ca53459b6a8bafde8');
  });

  it('the compiled module is the one of the committed source', () => {
    const src = readFileSync(new URL('../../tools/grain/grain.c', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
    expect(createHash('sha256').update(src).digest('hex')).toBe(GRAIN_SOURCE_SHA256);
  });

  it('settings, tables and the size of the effect', () => {
    expect(grainSetting(undefined)).toBe(0);
    expect(grainSetting({ amount: 0, size: 'large' })).toBe(0);
    expect(grainSetting({ amount: 2, size: 'small' })).toBe(2);
    expect(grainSetting({ amount: 3, size: 'large' })).toBe(7);
    const tone = grainTone();
    expect(tone.length).toBe(768);
    for (let a = 0; a < 3; a++) {
      expect(tone[a * 256]).toBe(0);
      expect(tone[a * 256 + 255]).toBe(0);
      expect(Math.max(...tone.subarray(a * 256, a * 256 + 256))).toBe(255);
    }
    expect(GRAIN_AMOUNT[0] < GRAIN_AMOUNT[1] && GRAIN_AMOUNT[1] < GRAIN_AMOUNT[2]).toBe(true);
    expect(GRAIN_CELL[0] < GRAIN_CELL[1]).toBe(true);
    // Mid grey, full size: the spread grows with the amount; black and white stay as they are.
    const spread = (setting: number) => {
      const w = 6000, h = 64, p = new Uint8Array(w * h).fill(110);
      grainY(p, w, h, w, setting);
      let s = 0, s2 = 0;
      for (const v of p) { s += v; s2 += v * v; }
      const m = s / p.length;
      return Math.sqrt(s2 / p.length - m * m);
    };
    const [weak, medium, strong] = [1, 2, 3].map(spread);
    expect(weak).toBeGreaterThan(1.2);
    expect(medium).toBeGreaterThan(weak);
    expect(strong).toBeGreaterThan(medium);
    expect(strong).toBeLessThan(10);
    for (const level of [0, 255]) {
      const p = new Uint8Array(6000 * 8).fill(level);
      grainY(p, 6000, 8, 6000, 3);
      expect(p.every(v => v === level)).toBe(true);
    }
  });

  it('the preview changes brightness only, by the same amount on R, G and B', () => {
    const w = 320, h = 200, rgb = new Uint8Array(w * h * 3);
    for (let i = 0; i < w * h; i++) rgb.set([120, 100, 90], i * 3);
    const before = rgb.slice();
    grainRgb(rgb, w, h, 3, 3, w);
    let changed = 0;
    for (let i = 0; i < w * h; i++) {
      const d = [0, 1, 2].map(c => rgb[i * 3 + c] - before[i * 3 + c]);
      expect(d[0]).toBe(d[1]);
      expect(d[1]).toBe(d[2]);
      if (d[0]) changed++;
    }
    expect(changed).toBeGreaterThan(w * h / 4);
  });
});
