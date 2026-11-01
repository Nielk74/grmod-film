// SPDX-License-Identifier: GPL-2.0-only
/**
 * Film grain of GR III films (round 10, grain v2): the parameters and tables the build gives the
 * camera's module (tools/grain/grain.c), and the same integer steps for GR Mod's preview. `grainYC`
 * is the module's computation, bit for bit (checked against the ARM code in an emulator,
 * tools/grain/check.py); see grain.c for the method: tiles of film grain cut from the Boolean film
 * grain model (tools/grain/tiles.py, grain-tables.ts), laid in 32-pixel blocks at random offsets,
 * brightness and colour, scaled by a brightness table.
 */
import { GRAIN_COLOUR_TILES, GRAIN_LUMA_TILES, GRAIN_TILE_SIZE, GRAIN_TONES } from './grain-tables';

export type GrainAmount = 0 | 1 | 2 | 3;
export type GrainSize = 'small' | 'large';
export interface Grain { amount: GrainAmount; size: GrainSize }

/** Weak, Medium, Strong: the grain's luma RMS at mid grey, x 16 (2.4, 4, 6.4 levels, as version 1). */
export const GRAIN_GAIN: readonly [number, number, number] = [38, 64, 102];
export const GRAIN_MAGIC = 0x324e5247; // 'GRN2'
const FULL_WIDTH = 6000;
const T = GRAIN_TILE_SIZE;

/** Strength by brightness of small and large grain (2 x 256, 128 = as at mid grey): strongest in the
 * shadows and lower midtones, fading towards the highlights, none at black and white. */
export function grainTone(): Uint8Array {
  const out = new Uint8Array(512);
  out.set(GRAIN_TONES[0], 0);
  out.set(GRAIN_TONES[1], 256);
  return out;
}

/** The module's setting byte of a film: 0 none, else amount | size << 2. */
export function grainSetting(g: Grain | undefined): number {
  if (!g || !g.amount) return 0;
  return g.amount | (g.size === 'large' ? 4 : 0);
}

/** A block's offset in the tile: x in bits 0..6, y in bits 8..14 (grain.c `offset`). */
function offset(i: number, j: number, seed: number): number {
  let h = (Math.imul(i, 0x9e3779b1) ^ Math.imul(j, 0x85ebca77) ^ seed) >>> 0;
  h ^= h >>> 15; h = Math.imul(h, 0x2c1b3c6d) >>> 0; h ^= h >>> 12; h = Math.imul(h, 0x297a2d39) >>> 0; h ^= h >>> 15;
  return h & 0x7f7f;
}

const s8 = (v: number) => (v << 24) >> 24;
const clamp8 = (v: number) => (v < 0 ? 0 : v > 255 ? 255 : v);

/**
 * Add the grain of `setting` (grainSetting) to a picture in place, as the camera does to each of its
 * pictures: `Y` (`w` x `h` values `stride` apart) and its 4:2:2 colour plane `C` ((Cb, Cr) pairs, the
 * same stride). `fullWidth`: how many pixels of a 6000-wide picture the width shows (the camera: 6000;
 * the picture's width decides the grain's scale).
 */
export function grainYC(Y: Uint8Array | Uint8ClampedArray, C: Uint8Array | Uint8ClampedArray, w: number, h: number, stride: number,
  setting: number, fullWidth = FULL_WIDTH): void {
  const amount = setting & 3, size = (setting >> 2) & 1;
  if (!amount) return;
  const step = Math.floor((fullWidth * 256) / w) >>> 0;
  const att = step > 256 ? Math.floor(65536 / step) : 256;
  const gain = (GRAIN_GAIN[amount - 1] * att) >> 8;
  if (!gain) return;
  const tone = GRAIN_TONES[size], lt = GRAIN_LUMA_TILES[size], ct = GRAIN_COLOUR_TILES[size];
  const nbx = (w + 31) >> 5, offs = new Uint16Array(nbx);
  let seed = (Math.imul(w, 0x10001) + h) >>> 0;
  for (let y = 0; y < 8; y++) seed = (Math.imul(seed, 0x01000193) ^ Y[((h * y) >> 3) * stride + ((w * (7 - y)) >> 3)]) >>> 0;
  for (let y = 0; y < h; y++) {
    const row = y * stride, ty0 = ((y & 31) * step) >>> 8;
    if (!(y & 31)) for (let x = 0; x < nbx; x++) offs[x] = offset(x, y >> 5, seed);
    for (let x = 0; x < w; x++) {
      const o = offs[x >> 5];
      const ty = ((o >> 8) + ty0) & (T - 1);
      const tx = (o + (((x & 31) * step) >>> 8)) & (T - 1);
      const v = Y[row + x], f = gain * tone[v];
      Y[row + x] = clamp8(v + ((s8(lt[ty * T + tx]) * f + 32768) >> 16));
      if (!(x & 1) && x + 1 < w) {
        const c = ty * T + (tx & ~1);
        C[row + x] = clamp8(C[row + x] + ((s8(ct[c]) * f + 32768) >> 16));
        C[row + x + 1] = clamp8(C[row + x + 1] + ((s8(ct[c + 1]) * f + 32768) >> 16));
      }
    }
  }
}

/**
 * Preview: grain on an RGB picture (8-bit, interleaved) through JPEG's YCbCr, as the camera adds it.
 * `span`: how many pixels of the camera's 6000-wide picture the preview's width shows (6000: the
 * whole photo, as the camera's JPEG scaled down; the preview's own width: a 100% crop).
 */
export function grainRgb(rgb: Uint8Array | Uint8ClampedArray, w: number, h: number, setting: number, channels = 3, span = FULL_WIDTH): void {
  if (!(setting & 3)) return;
  const n = w * h, Y = new Uint8Array(n), C = new Uint8Array(n);
  for (let i = 0; i < n; i++) {
    const o = i * channels, r = rgb[o], g = rgb[o + 1], b = rgb[o + 2];
    Y[i] = clamp8(Math.round(0.299 * r + 0.587 * g + 0.114 * b));
    // 4:2:2: the pair's Cb at the even pixel, Cr at the odd one (from the even pixel's colour)
    if (!((i % w) & 1)) {
      C[i] = clamp8(Math.round(128 - 0.168736 * r - 0.331264 * g + 0.5 * b));
      if ((i % w) + 1 < w) C[i + 1] = clamp8(Math.round(128 + 0.5 * r - 0.418688 * g - 0.081312 * b));
    }
  }
  const Y0 = Y.slice(), C0 = C.slice();
  grainYC(Y, C, w, h, w, setting, span);
  for (let i = 0; i < n; i++) {
    const x = i % w, p = x & 1 ? i - 1 : i;
    const dy = Y[i] - Y0[i], dcb = C[p] - C0[p], dcr = p + 1 < (i - x) + w ? C[p + 1] - C0[p + 1] : 0;
    if (!dy && !dcb && !dcr) continue;
    const o = i * channels;
    rgb[o] = clamp8(Math.round(rgb[o] + dy + 1.402 * dcr));
    rgb[o + 1] = clamp8(Math.round(rgb[o + 1] + dy - 0.344136 * dcb - 0.714136 * dcr));
    rgb[o + 2] = clamp8(Math.round(rgb[o + 2] + dy + 1.772 * dcb));
  }
}
