// SPDX-License-Identifier: GPL-2.0-only
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { aspectSpan, textureGrainStep, textureRadiusSpan, textureReferenceSpan } from '../src/color/texture-geometry';
import { halateYcc, halationModule } from '../src/fw/aspect/halation';
import { HALATION_SOURCE_SHA256 } from '../src/fw/aspect/halation-code';
import { LEGACY_HALATION_CODE, LEGACY_FILM_MTF_CODE, LEGACY_GRAIN_CODE } from '../src/fw/picture-legacy-code';
import { filmMtfApplies } from '../src/color/filmmtf';
import { GR3X_T4_CUSTOM, planGr3xRatio } from '../src/fw/gr3x/geometry';

describe('stored crop texture geometry', () => {
  it('uses aspect span for landscapes, squares and portrait crops, keeping a single job reference', () => {
    for (const main of [{ width: 6000, height: 4000 }, { width: 4800, height: 3200 }, { width: 3360, height: 2240 }, { width: 4000, height: 4000 }, { width: 3000, height: 4000 }]) {
      const geometry = { policy: 'sensor' as const, main };
      expect(textureGrainStep(main.width, main.height, geometry)).toBe(256);
      expect(textureRadiusSpan(main.width, main.height, geometry)).toBe(6000);
      expect(textureGrainStep(720, 480, geometry)).toBeGreaterThan(256);
      expect(textureGrainStep(160, 120, geometry)).toBeGreaterThan(256);
    }
    const sensor = { policy: 'sensor' as const, main: { width: 4800, height: 3200 } };
    expect(textureGrainStep(720, 480, sensor)).toBe(1706);
    expect(textureRadiusSpan(720, 480, sensor)).toBe(900);
    expect(textureGrainStep(3360, 2240, { policy: 'output' })).toBe(457);
    expect(aspectSpan(4000, 4000)).toBe(6000);
  });

  it('uses the output reference when the primary main is missing, invalid or preview-sized', () => {
    for (const main of [undefined, { width: 720, height: 480 }, { width: 3361, height: 2240 }, { width: 0, height: 0 }, { width: NaN, height: 2240 }]) {
      expect(textureReferenceSpan({ policy: 'sensor', main })).toBe(6000);
    }
    // This main is intentionally outside MTF's 960 floor, but is still a main for grain/halation.
    expect(textureReferenceSpan({ policy: 'sensor', main: { width: 640, height: 1280 } })).toBe(1920);
    expect(filmMtfApplies(640, 1280)).toBe(false);
  });

  it('uses explicit stored picture geometry for a rotated host preview without changing indexing dimensions', () => {
    const main = { width: 4800, height: 3200 };
    const stored = { policy: 'sensor' as const, main };
    const rotated = { ...stored, picture: { width: 600, height: 400 } };
    expect(textureGrainStep(400, 600, rotated)).toBe(textureGrainStep(600, 400, stored));
    expect(textureRadiusSpan(400, 600, rotated)).toBe(textureRadiusSpan(600, 400, stored));
  });

  it('covers the complete surveyed T4 menu while excluding preview widths', () => {
    for (const ratio of GR3X_T4_CUSTOM) {
      const plan = planGr3xRatio(ratio.ratio);
      for (const size of plan.sizes) expect(filmMtfApplies(size[0], size[1])).toBe(true);
    }
    expect(filmMtfApplies(720, 480)).toBe(false);
    expect(filmMtfApplies(160, 120)).toBe(false);
  });

  it('keeps frozen legacy module identities and GR IV default halation byte-exact', () => {
    const sha = (value: string) => createHash('sha256').update(Buffer.from(value, 'base64')).digest('hex');
    expect(sha(LEGACY_GRAIN_CODE)).toBe('da9cc6e34521892545d9a998789501e5360d7d8f7c28cc4c8169c4a5a743b0dd');
    expect(sha(LEGACY_FILM_MTF_CODE)).toBe('92439d21afbac0b072bd16454282dad6184909f4505fe8ca8db3dae7d627335b');
    expect(sha(LEGACY_HALATION_CODE)).toBe('4b1b6331b1617b54ce512453ecd869ea020da640eee6f72fd791d24362c7b663');
    expect(Buffer.from(halationModule()).toString('base64')).toBe(LEGACY_HALATION_CODE);
    const source = readFileSync(new URL('../../tools/halation/halation.c', import.meta.url), 'utf8').replace(/\r\n/g, '\n');
    expect(createHash('sha256').update(source).digest('hex')).toBe(HALATION_SOURCE_SHA256);
  });

  it('spreads red, white, gold and orange using the separate radius span; off stays exact', () => {
    const w = 1280, h = 96, original = new Uint8Array(w * h).fill(20), chroma = new Uint8Array(w * h).fill(128);
    for (let y = 32; y < 64; y++) original.fill(252, y * w + 620, y * w + 660);
    for (const colour of ['red', 'white', 'gold', 'orange'] as const) {
      const sensor = original.slice(), output = original.slice(), off = original.slice(), offC = chroma.slice();
      halateYcc(sensor, chroma.slice(), w, h, 3, undefined, colour, { policy: 'sensor', main: { width: w, height: h } });
      halateYcc(output, chroma.slice(), w, h, 3, undefined, colour, { policy: 'output' });
      expect(sensor).not.toEqual(output);
      halateYcc(off, offC, w, h, 0 as never, undefined, colour, { policy: 'sensor', main: { width: w, height: h } });
      expect(off).toEqual(original); expect(offC).toEqual(chroma);
    }
  });
});

