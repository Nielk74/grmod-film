// SPDX-License-Identifier: GPL-2.0-only
/**
 * GR III 2.10 / IIIx 1.60, round 10: a film's recipe besides its colour. GR Mod's film recipes, as
 * Fujifilm's: the values the camera's parameters start from for the film (native/films.c,
 * -DFILM_DEFAULTS), and its grain (grain.c, fixed in the build).
 *
 * The parameters are the camera's own processing on top of the film's colour (the film renders as
 * Standard with them): every parameter the films have can start elsewhere than neutral. GR Mod's UI
 * offers those colour cannot hold (Sharpness, Shading, Clarity, Halation); the others work too.
 * The parameter screen's "0" stays the neutral value, so the screen shows the recipe as its
 * offsets (Sharpness -1, ...), and a changed value is kept per film and photo set as always.
 */
import { FirmwareError } from '../types';
import type { Grain } from '../../color/grain';

/** -4..+4 each (0 neutral), the camera's scales. */
export interface Gr3xFilmDefaults {
  saturation?: number; hue?: number; key?: number; contrast?: number; highlight?: number; shadow?: number;
  sharpness?: number; shading?: number; clarity?: number;
  /** The film's Halation row: 0 off, 1..3 weak / medium / strong; white, gold or orange (gold and orange: builds with the
   * Grain row, `grainRow`), else red. */
  halation?: { strength: 0 | 1 | 2 | 3; white?: boolean; gold?: boolean; orange?: boolean };
}

/** films.c's parameter order (FIELD): saturation, hue, key, contrast, highlight, shadow, sharpness, Toning (Halation), shading, clarity. */
export const GR3X_RECIPE_NP = 10;
const ORDER = ['saturation', 'hue', 'key', 'contrast', 'highlight', 'shadow', 'sharpness', null, 'shading', 'clarity'] as const;
export const GR3X_NEUTRAL_PARAMETERS: readonly number[] = [4, 4, 4, 4, 4, 4, 4, 0, 4, 4];
/** GR IV's Toning states (films.c ON_STATE / OFF_STATE): on red 1 / 3 / 2, white 4 / 5 / 6; off red 0, white 9;
 * with the Grain row (films.c GRAIN_ROW) gold on 12 / 13 / 14, off 15, orange on 18 / 19 / 20, off 21,
 * and the grain amount g adds 24 g. */
const ON_RED = [1, 3, 2], ON_WHITE = [4, 5, 6], ON_GOLD = [12, 13, 14], ON_ORANGE = [18, 19, 20];
export const GR3X_HALATION_STATES = 24;

export function validateGr3xFilmDefaults(d: Gr3xFilmDefaults | undefined): void {
  if (d === undefined) return;
  if (!d || typeof d !== 'object') throw new FirmwareError('bad-edit', 'film recipe: defaults');
  for (const key of ORDER) {
    if (!key) continue;
    const v = d[key];
    if (v !== undefined && !(Number.isInteger(v) && v >= -4 && v <= 4)) throw new FirmwareError('bad-edit', `film recipe: ${key} is -4..+4`);
  }
  if (d.halation !== undefined && (!d.halation || ![0, 1, 2, 3].includes(d.halation.strength) || (d.halation.white !== undefined && typeof d.halation.white !== 'boolean')
      || (d.halation.gold !== undefined && typeof d.halation.gold !== 'boolean') || (d.halation.orange !== undefined && typeof d.halation.orange !== 'boolean')
      || [d.halation.white, d.halation.gold, d.halation.orange].filter(Boolean).length > 1))
    throw new FirmwareError('bad-edit', 'film recipe: halation');
  const known = new Set<string>([...ORDER.filter(Boolean) as string[], 'halation']);
  if (Object.keys(d).some(k => !known.has(k))) throw new FirmwareError('bad-edit', 'film recipe: unknown parameter');
}

/** The ten bytes the film starts from (films.c's order and scales). `grain`: builds with the Grain row,
 * the grain amount the film starts from (0 off, 1..3), in the Toning byte with the Halation. */
export function gr3xFilmDefaultBytes(d: Gr3xFilmDefaults | undefined, grain = 0): Uint8Array {
  validateGr3xFilmDefaults(d);
  if (![0, 1, 2, 3].includes(grain)) throw new FirmwareError('bad-edit', 'film recipe: grain');
  const out = Uint8Array.from(GR3X_NEUTRAL_PARAMETERS);
  out[7] = GR3X_HALATION_STATES * grain;
  if (!d) return out;
  ORDER.forEach((key, j) => { if (key && d[key] !== undefined) out[j] = 4 + d[key]!; });
  if (d.halation) out[7] += d.halation.strength ? (d.halation.white ? ON_WHITE : d.halation.gold ? ON_GOLD : d.halation.orange ? ON_ORANGE : ON_RED)[d.halation.strength - 1]
    : d.halation.white ? 9 : d.halation.gold ? 15 : d.halation.orange ? 21 : 0;
  return out;
}

/** True when the film starts anywhere but neutral. */
export function gr3xHasDefaults(d: Gr3xFilmDefaults | undefined): boolean {
  const b = gr3xFilmDefaultBytes(d);
  return b.some((v, j) => v !== GR3X_NEUTRAL_PARAMETERS[j]);
}

/** The defaults as stored in the build recipe: only the parameters that differ from neutral. */
export function gr3xCanonicalDefaults(d: Gr3xFilmDefaults | undefined): Gr3xFilmDefaults | undefined {
  if (!gr3xHasDefaults(d)) return undefined;
  const out: Gr3xFilmDefaults = {};
  for (const key of ORDER) if (key && d![key]) out[key] = d![key];
  if (d!.halation && (d!.halation.strength || d!.halation.white || d!.halation.gold || d!.halation.orange))
    out.halation = { strength: d!.halation.strength, ...(d!.halation.white ? { white: true } : {}), ...(d!.halation.gold ? { gold: true } : {}),
      ...(d!.halation.orange ? { orange: true } : {}) };
  return out;
}

/** A film's fingerprint with its starting values (a film whose recipe changed starts again from it).
 * Without defaults the fingerprint is the colour's alone, as before. */
export function gr3xRecipePrint(print: number, d: Gr3xFilmDefaults | undefined, grain = 0): number {
  if (!gr3xHasDefaults(d) && !grain) return print;
  let h = print >>> 0;
  for (const v of [0x52, ...gr3xFilmDefaultBytes(d, grain)]) { h ^= v; h = Math.imul(h, 0x01000193) >>> 0; }
  return h || 1;
}

export function validateGr3xGrain(g: Grain | undefined): void {
  if (g === undefined) return;
  if (!g || ![0, 1, 2, 3].includes(g.amount) || !['small', 'large'].includes(g.size)) throw new FirmwareError('bad-edit', 'film recipe: grain');
}
