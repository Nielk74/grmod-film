// SPDX-License-Identifier: GPL-2.0-only
/**
 * Film grain of GR III films (round 10): the parameters and tables the build gives the camera's
 * module (tools/grain/grain.c), and the same integer steps for GR Mod's preview. `grainY` is the
 * module's computation, bit for bit (checked against the ARM code in an emulator,
 * tools/grain/check.py); see grain.c for the method.
 */

export type GrainAmount = 0 | 1 | 2 | 3;
export type GrainSize = 'small' | 'large';
export interface Grain { amount: GrainAmount; size: GrainSize }

/** Noise gain of Weak, Medium, Strong (of 256): luma spread at the midtones about 2.4 / 4 / 6.4. */
export const GRAIN_AMOUNT: readonly [number, number, number] = [9, 15, 24];
/** Lattice spacing of small and large grain on a 6000-pixel-wide picture, in 1/256 pixel. */
export const GRAIN_CELL: readonly [number, number] = [320, 576];
export const GRAIN_MAGIC = 0x314e5247; // 'GRN1'
const FULL_WIDTH = 6000;

/** Strength by brightness (0..255) for Weak, Medium, Strong: strongest in the midtones (a little
 * below middle grey, as negative film), little in deep shadows and none in clipped highlights;
 * Strong reaches further into both. */
export function grainTone(): Uint8Array {
  const out = new Uint8Array(3 * 256);
  const spread = [0.7, 0.62, 0.5];
  for (let a = 0; a < 3; a++) for (let y = 0; y < 256; y++) {
    const u = (y / 255) ** 0.8;
    const bell = Math.sin(Math.PI * u);
    out[a * 256 + y] = Math.round(255 * Math.max(0, bell) ** spread[a]);
  }
  return out;
}

/** The module's setting byte of a film: 0 none, else amount | size << 2. */
export function grainSetting(g: Grain | undefined): number {
  if (!g || !g.amount) return 0;
  return g.amount | (g.size === 'large' ? 4 : 0);
}

function noise(i: number, j: number, seed: number): number {
  let h = (Math.imul(i, 0x9e3779b1) ^ Math.imul(j, 0x85ebca77) ^ seed) >>> 0;
  h ^= h >>> 15; h = Math.imul(h, 0x2c1b3c6d) >>> 0; h ^= h >>> 12; h = Math.imul(h, 0x297a2d39) >>> 0; h ^= h >>> 15;
  return (h & 0xff) + ((h >>> 8) & 0xff) - 255;
}

/**
 * Add the grain of `setting` (grainSetting) to a luma plane in place: `w` x `h` values `stride`
 * apart, as the camera does to each of its pictures (the picture's width decides the grain's scale).
 */
export function grainY(Y: Uint8Array, w: number, h: number, stride: number, setting: number,
  tone: Uint8Array = grainTone(), amounts: readonly number[] = GRAIN_AMOUNT, cells: readonly number[] = GRAIN_CELL): void {
  const amount = setting & 3, size = (setting >> 2) & 1;
  if (!amount) return;
  let cell = Math.floor((cells[size] * w) / FULL_WIDTH), att = 256;
  if (cell < 256) { att = cell; cell = 256; }
  const gain = (amounts[amount - 1] * att) >> 8;
  if (!gain) return;
  const step = Math.floor((256 << 16) / cell);
  const nx = ((w * step) >>> 16) + 3;
  let seed = (w * 0x10001 + h) >>> 0;
  for (let y = 0; y < 8; y++) seed = (Math.imul(seed, 0x01000193) ^ Y[((h * y) >> 3) * stride + ((w * (7 - y)) >> 3)]) >>> 0;
  const t = tone.subarray((amount - 1) * 256, amount * 256);
  let ra = new Int16Array(nx), rb = new Int16Array(nx);
  const mix = new Int32Array(nx);
  const fill = (row: Int16Array, j: number) => { for (let i = 0; i < nx; i++) row[i] = noise(i, j, seed); };
  let j0 = 0;
  fill(ra, 0); fill(rb, 1);
  for (let y = 0; y < h; y++) {
    const py = y * step, j = py >>> 16, fy = (py >>> 8) & 255;
    while (j0 < j) { const tmp = ra; ra = rb; rb = tmp; j0++; fill(rb, j0 + 1); }
    for (let i = 0; i < nx; i++) mix[i] = ra[i] * 256 + (rb[i] - ra[i]) * fy;
    const row = y * stride;
    for (let x = 0, px = 0; x < w; x++, px += step) {
      const li = px >>> 16, fx = (px >>> 8) & 255;
      const v = (mix[li] * (256 - fx) + mix[li + 1] * fx) >> 16;
      let v2 = Y[row + x];
      v2 += (v * gain * t[v2]) >> 16;
      Y[row + x] = v2 < 0 ? 0 : v2 > 255 ? 255 : v2;
    }
  }
}

/**
 * Preview: grain on an RGB picture (8-bit, interleaved) through JPEG's YCbCr, the brightness only.
 * `span`: how many pixels of the camera's 6000-wide picture the preview's width shows (6000: the
 * whole photo, as the camera's JPEG scaled down; the preview's own width: a 100% crop).
 */
export function grainRgb(rgb: Uint8Array | Uint8ClampedArray, w: number, h: number, setting: number, channels = 3, span = FULL_WIDTH): void {
  if (!(setting & 3)) return;
  const Y = new Uint8Array(w * h);
  for (let i = 0; i < w * h; i++) {
    const o = i * channels;
    Y[i] = Math.min(255, Math.max(0, Math.round(0.299 * rgb[o] + 0.587 * rgb[o + 1] + 0.114 * rgb[o + 2])));
  }
  const before = Y.slice();
  // grainY scales the lattice by w / 6000: a preview showing `span` camera pixels needs it by w / span.
  const cells = GRAIN_CELL.map(c => Math.max(1, Math.round((c * FULL_WIDTH) / span)));
  grainY(Y, w, h, w, setting, grainTone(), GRAIN_AMOUNT, cells);
  for (let i = 0; i < w * h; i++) {
    const d = Y[i] - before[i];
    if (!d) continue;
    const o = i * channels;
    for (let c = 0; c < 3; c++) { const v = rgb[o + c] + d; rgb[o + c] = v < 0 ? 0 : v > 255 ? 255 : v; }
  }
}
