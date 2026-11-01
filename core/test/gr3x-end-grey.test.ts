// SPDX-License-Identifier: GPL-2.0-only
// `endGreyWeight`: extra grey samples at both ends of the range in the GR III / IIIx cube fit, so that a look's
// tinted white (cream highlights) is held instead of coming out nearly neutral.
import { describe, expect, it } from 'vitest';
import { convertGr3xCube, endGreySamples } from '../src/color/gr3x-import';
import { GR3X_CAMERA } from '../src/color/gr3x-camera';

/** A 17-point cube that is Standard with a cream tint rising into the highlights (blue -12 %, green -5 % at white). */
function creamCube(): string {
  const n = 17, lines = ['TITLE "Cream highlights"', `LUT_3D_SIZE ${n}`];
  for (let b = 0; b < n; b++) for (let g = 0; g < n; g++) for (let r = 0; r < n; r++) {
    const R = r / (n - 1), G = g / (n - 1), B = b / (n - 1), l = ((R + G + B) / 3) ** 3;
    lines.push([R, G * (1 - 0.05 * l), B * (1 - 0.12 * l)].map(v => v.toFixed(6)).join(' '));
  }
  return lines.join('\n') + '\n';
}

/** How far the fitted camera's white is from the cube's cream white (blue channel, 0..1). */
const whiteBlueError = (weight?: number): number => {
  const c = convertGr3xCube(creamCube(), { post: true, endGreyWeight: weight });
  return Math.abs(GR3X_CAMERA.slotApply(c.params, Float64Array.from([1, 1, 1]))[2] - 0.88);
};

describe('end grey weight (GR III / IIIx cube fit)', () => {
  it('adds two 41-step ramps per copy, one per end', () => {
    const s = endGreySamples(3);
    expect(s.length).toBe(3 * 2 * 41 * 3);
    expect(Math.min(...s)).toBe(0);
    expect(Math.max(...s)).toBe(1);
    expect(endGreySamples(0).length).toBe(0);
  });

  it('leaves the fit alone at 0', () => {
    const a = convertGr3xCube(creamCube(), { post: true }), b = convertGr3xCube(creamCube(), { post: true, endGreyWeight: 0 });
    expect(b.params.M1).toEqual(a.params.M1);
    expect(b.meanDE2000).toBe(a.meanDE2000);
  });

  it('holds a cream white better than the plain fit', () => {
    const plain = whiteBlueError(), weighted = whiteBlueError(24);
    expect(weighted).toBeLessThan(plain);
    expect(weighted).toBeLessThan(0.03);
  });
});
