// SPDX-License-Identifier: GPL-2.0-only
/**
 * Where each film puts the sky: the hue and chroma (OkLCh) of sky pixels of the GR III Standard
 * samples, before, through the look itself and through the fitted film as the camera applies it.
 *
 *   npx vite-node examples/gr3x/film-pack/sky.ts [film,film,...]
 *
 * Hues: blue ~255, sky blue ~235, cyan ~200, teal ~185..195.
 */
import { readFileSync } from 'node:fs';
import { decodeBaselineJpeg } from '../../../core/src/jpeg/decoder';
import { convertGr3xCube } from '../../../core/src/color/gr3x-import';
import { GR3X_CAMERA } from '../../../core/src/color/gr3x-camera';
import { LOOKS, cubeText } from '../../../core/src/filmpack/looks';

const only = process.argv[2]?.split(',');
const root = new URL('../../../ui/src/assets/samples/', import.meta.url);
/** Sky: bluish, bright enough, from the top part of the frame. */
function skyPixels(file: string, topFraction: number): Float64Array {
  const { width, height, rgb } = decodeBaselineJpeg(new Uint8Array(readFileSync(new URL(file, root))));
  const out: number[] = [];
  for (let y = 0; y < Math.floor(height * topFraction); y += 4) for (let x = 0; x < width; x += 4) {
    const i = (y * width + x) * 3, r = rgb[i], g = rgb[i + 1], b = rgb[i + 2];
    if (b > r + 25 && b > g && b > 90) out.push(r / 255, g / 255, b / 255);
  }
  return Float64Array.from(out);
}
const toLin = (v: number) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
function lch(p: Float64Array): [number, number, number] {
  let a = 0, b = 0, L = 0; const n = p.length / 3;
  for (let i = 0; i < p.length; i += 3) {
    const r = toLin(p[i]), g = toLin(p[i + 1]), bl = toLin(p[i + 2]);
    const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * bl), m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * bl), s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * bl);
    L += 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s;
    a += 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
    b += 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
  }
  return [L / n, Math.hypot(a / n, b / n), ((Math.atan2(b / n, a / n) * 180) / Math.PI + 360) % 360];
}
const sky = [skyPixels('gr3-hill.jpg', 0.45), skyPixels('gr3-r0000023.jpg', 0.35), skyPixels('gr3-r0000022.jpg', 0.35)];
const all = Float64Array.from(sky.flatMap(s => Array.from(s)));
const fmt = ([L, C, h]: number[]) => `h ${h.toFixed(0).padStart(3)}  C ${C.toFixed(3)}  L ${L.toFixed(2)}`;
console.log(`${'Standard'.padEnd(16)} ${fmt(lch(all))}   (${all.length / 3} sky pixels)`);
/** Colours to protect: light and dark skin, foliage, a yellow (sRGB, as Standard renders them). */
const PATCHES: [string, number[]][] = [['skin', [194, 150, 130]], ['dark skin', [115, 82, 68]], ['foliage', [87, 108, 67]], ['yellow', [224, 163, 46]]];
const patch = (rgb: number[]) => Float64Array.from(rgb.map(v => v / 255));
const hueOf = (p: Float64Array) => lch(p)[2];
for (const look of LOOKS) {
  if (only && !only.includes(look.name)) continue;
  const ideal = new Float64Array(all.length);
  for (let i = 0; i < all.length; i += 3) ideal.set(look.op([all[i], all[i + 1], all[i + 2]]), i);
  const fit = convertGr3xCube(cubeText(look), { post: true });
  const film = GR3X_CAMERA.slotApply(fit.params, all);
  const shifts = PATCHES.map(([n, rgb]) => {
    const p = patch(rgb), d = (((hueOf(GR3X_CAMERA.slotApply(fit.params, p)) - hueOf(p)) + 540) % 360) - 180;
    const k = lch(GR3X_CAMERA.slotApply(fit.params, p))[1] / lch(p)[1];
    return `${n} ${d >= 0 ? '+' : ''}${d.toFixed(0)}°×${k.toFixed(2)}`;
  }).join(', ');
  console.log(`${look.name.padEnd(16)} look ${fmt(lch(ideal))}   film ${fmt(lch(film))}   fit ΔE00 ${fit.meanDE2000!.toFixed(2)}   film hue shifts: ${shifts}`);
}
