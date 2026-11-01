// SPDX-License-Identifier: GPL-2.0-only
/**
 * Films re-authored for film pack v3 (the 2026-11-01 review of the whole pack on one photo: Astia,
 * Hasselblad Std and Pro Neg Hi were hard to tell from Standard). Each is written with the library's own
 * operations (core/src/filmpack/looks.ts) and goes through film response like the other films.
 */
import { bands, chain, curve, split } from '../../../core/src/filmpack/looks';
import type { Op } from '../../../core/src/filmpack/looks';

/**
 * Astia as a slide film worth shooting: a slide's contrast (deep shadows, clean bright highlights), vivid
 * blues turned a little towards cyan, richer greens, a touch of cool in the shadows, and skin left alone
 * (a hair less colour, a hair lighter). Blues and greens are far from skin, so the camera's global matrix
 * and curves can carry them without moving skin. `level` 1 is moderate, 2 strong.
 */
export const astiaSlide = (level: number): Op => chain(
  curve([[0, 0], [0.1, 0.1 - 0.03 * level], [0.28, 0.28 - 0.04 * level], [0.5, 0.5], [0.74, 0.74 + 0.04 * level], [0.9, 0.9 + 0.03 * level], [1, 1]]),
  bands(
    { hue: 262, width: 55, sat: 1 + 0.3 * level, shift: -5 * level },
    { hue: 195, width: 40, sat: 1 + 0.15 * level },
    { hue: 142, width: 48, sat: 1 + 0.25 * level, shift: 4 * level },
    { hue: 55, width: 30, sat: 1 - 0.04 * level, light: 1 + 0.015 * level },
  ),
  split([0, -0.002 * level], [0, 0]),
);
