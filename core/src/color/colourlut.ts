// SPDX-License-Identifier: GPL-2.0-only
/**
 * Per-film 3D colour LUT of GR III films (round 10): the tables the build gives the camera's module
 * (tools/colourlut/colourlut.c) and the same integer steps as a TypeScript reference. `colourLutYC` is
 * the module's computation, byte for byte (checked against the ARM code in an emulator,
 * tools/colourlut/check.py), and the integer algorithm of the colour engine prototype
 * (tools/colour_engine/engine.py `lut_apply_422`), which made the approved look.
 *
 * Each horizontal pixel pair of a YCbCr 4:2:2 picture is looked up at (Ym, Cb, Cr), Ym = (Y0 + Y1 + 1) >> 1,
 * in a 33 x 33 x 33 table of Q4 deltas (dY, dCb, dCr) by tetrahedral interpolation (node v >> 3, fraction
 * v & 7, axes walked by descending fraction, ties in the order Y, Cb, Cr; result (acc + 64) >> 7). dY goes
 * to both lumas of the pair, dCb and dCr to the chroma, each clipped to 0..255.
 */
import { COLOUR_LUT_TABLES } from './colourlut-tables';

export const COLOUR_LUT_MAGIC = 0x31554c43; // 'CLU1'
export const COLOUR_LUT_N = 33;
/** The module's context has room for this many tables (colourlut.c `lut[8]`). */
export const COLOUR_LUT_MAX_TABLES = 8;
export const COLOUR_LUT_VALUES = COLOUR_LUT_N ** 3 * 3;
export const COLOUR_LUT_BYTES = COLOUR_LUT_VALUES * 2;
/** The films that have a LUT, in the order the module's tables are numbered (table n is `COLOUR_LUT_FILMS[n - 1]`). */
export const COLOUR_LUT_FILMS: readonly string[] = COLOUR_LUT_TABLES.map(t => t.film);

/** The film's table as the module reads it (little-endian int16 bytes), or undefined: the film has no LUT. */
export function colourLutBytes(film: string): Uint8Array | undefined {
  return COLOUR_LUT_TABLES.find(t => t.film === film)?.data;
}

/** The film's table as values: [Y node][Cb node][Cr node][dY dCb dCr], Q4 deltas. */
export function colourLutValues(film: string): Int16Array | undefined {
  const b = colourLutBytes(film);
  if (!b) return undefined;
  const out = new Int16Array(COLOUR_LUT_VALUES), v = new DataView(b.buffer, b.byteOffset, b.byteLength);
  for (let i = 0; i < out.length; i++) out[i] = v.getInt16(i * 2, true);
  return out;
}

/** The module's table number of a film (1..), 0: no LUT. */
export function colourLutIndex(film: string | undefined): number {
  const i = film === undefined ? -1 : COLOUR_LUT_FILMS.indexOf(film);
  return i + 1;
}

/** The pictures the module handles: YCbCr 4:2:2 of 64 x 48 to 12000 x 12000, an even width and height. */
export function colourLutApplies(w: number, h: number): boolean {
  return w >= 64 && h >= 48 && w <= 12000 && h <= 12000 && !(w & 1) && !(h & 1);
}

const clamp8 = (v: number) => (v < 0 ? 0 : v > 255 ? 255 : v);

/**
 * Apply a table to a picture in place, as the camera does to each of its pictures: `Y` (`w` x `h` values `stride`
 * apart) and its 4:2:2 colour plane `C` ((Cb, Cr) pairs, the same stride). Returns false (and changes nothing) for
 * a picture the module leaves alone.
 */
export function colourLutYC(Y: Uint8Array | Uint8ClampedArray, C: Uint8Array | Uint8ClampedArray, w: number, h: number, stride: number,
  lut: Int16Array): boolean {
  if (!colourLutApplies(w, h) || stride < w || lut.length !== COLOUR_LUT_VALUES) return false;
  for (let y = 0; y < h; y++) {
    const row = y * stride;
    for (let x = 0; x < w; x += 2) {
      const y0 = Y[row + x], y1 = Y[row + x + 1], cb = C[row + x], cr = C[row + x + 1];
      const vy = (y0 + y1 + 1) >> 1;
      let f0 = vy & 7, f1 = cb & 7, f2 = cr & 7, a0 = 0, a1 = 1, a2 = 2, t: number;
      const p0 = ((vy >> 3) * 1089 + (cb >> 3) * 33 + (cr >> 3)) * 3;
      if (f1 > f0) { t = f0; f0 = f1; f1 = t; t = a0; a0 = a1; a1 = t; }
      if (f2 > f1) { t = f1; f1 = f2; f2 = t; t = a1; a1 = a2; a2 = t; }
      if (f1 > f0) { t = f0; f0 = f1; f1 = t; t = a0; a0 = a1; a1 = t; }
      const step = (a: number) => (a === 0 ? 3267 : a === 1 ? 99 : 3);
      const p1 = p0 + step(a0), p2 = p1 + step(a1), p3 = p2 + step(a2);
      const d = (c: number) => ((lut[p0 + c] << 3) + (lut[p1 + c] - lut[p0 + c]) * f0 + (lut[p2 + c] - lut[p1 + c]) * f1 + (lut[p3 + c] - lut[p2 + c]) * f2 + 64) >> 7;
      const dy = d(0);
      Y[row + x] = clamp8(y0 + dy);
      Y[row + x + 1] = clamp8(y1 + dy);
      C[row + x] = clamp8(cb + d(1));
      C[row + x + 1] = clamp8(cr + d(2));
    }
  }
  return true;
}
