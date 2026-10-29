// SPDX-License-Identifier: GPL-2.0-only
import { describe, expect, it } from 'vitest';
import { GR3X_CAMERA } from '../src/color/gr3x-camera';
import { tealSkyMix, tealSkyQ13, withTealSky } from '../src/color/sky';
import { quantizeSlot } from '../src/color';
import type { SlotParams } from '../src/color/camera';
import { KN } from '../src/color/camera';

const toLin = (v: number) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
/** OkLCh hue (degrees) of an sRGB colour (0..1). */
function hue([r, g, b]: number[]): number {
  const [R, G, B] = [r, g, b].map(toLin);
  const l = Math.cbrt(0.4122214708 * R + 0.5363325363 * G + 0.0514459929 * B), m = Math.cbrt(0.2119034982 * R + 0.6806995451 * G + 0.1073969566 * B), s = Math.cbrt(0.0883024619 * R + 0.2817188376 * G + 0.6299787005 * B);
  const a = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s, bb = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
  return ((Math.atan2(bb, a) * 180) / Math.PI + 360) % 360;
}
const identity: SlotParams = { M1: [[1, 0, 0], [0, 1, 0], [0, 0, 1]], ck: [0, 1, 2].map(() => Float64Array.from(KN)) };
const through = (p: SlotParams, rgb: number[]) => Array.from(GR3X_CAMERA.slotApply(p, Float64Array.from(rgb.map(v => v / 255))));

describe('teal sky', () => {
  it('keeps neutrals neutral at every step, and step 0 is the film unchanged', () => {
    for (let k = -4; k <= 4; k++) for (const row of tealSkyMix(k)) expect(row[0] + row[1] + row[2]).toBeCloseTo(1, 12);
    expect(withTealSky(identity, 0)).toBe(identity);
    const grey = through(withTealSky(identity, 4), [128, 128, 128]);
    expect(Math.abs(grey[0] - grey[1]) + Math.abs(grey[1] - grey[2])).toBeLessThan(1e-9);
  });

  it('turns a GR III sky toward teal step by step, skin barely moves, negative steps go bluer', () => {
    const sky = [95, 140, 200], skin = [194, 150, 130];
    const h = (k: number, c: number[]) => hue(through(withTealSky(identity, k), c));
    const h0 = h(0, sky);
    expect(h0).toBeGreaterThan(250);
    expect(h(2, sky)).toBeLessThan(h0 - 6);
    expect(h(4, sky)).toBeLessThan(h(2, sky) - 6);
    expect(h(4, sky)).toBeLessThan(h0 - 15);
    expect(h(-4, sky)).toBeGreaterThan(h0 + 6);
    expect(Math.abs(h(4, skin) - h(0, skin))).toBeLessThan(5);
  });

  it('the firmware\'s matrices (a film\'s Hue in the camera) are the preview\'s, grey stays grey', () => {
    // A camera matrix like Standard's (Q13, rows summing to 8192).
    const STD = [11000, -2300, -508, -1500, 10500, -808, 200, -2700, 10692];
    // A film with some colour of its own (not the identity).
    const film: SlotParams = { ...identity, M1: [[1.08, -0.05, -0.03], [-0.02, 0.97, 0.05], [0.01, -0.04, 1.03]] };
    const q = quantizeSlot(film, STD).matrixQ13;
    expect(Array.from(tealSkyQ13(q, STD, 0))).toEqual(Array.from(q));
    for (let k = -4; k <= 4; k++) {
      const m = tealSkyQ13(q, STD, k), want = quantizeSlot(withTealSky(film, k), STD).matrixQ13;
      for (let r = 0; r < 3; r++) expect(m[r * 3] + m[r * 3 + 1] + m[r * 3 + 2]).toBe(8192);
      m.forEach((v, j) => expect(Math.abs(v - want[j])).toBeLessThanOrEqual(2));
    }
  });
});
