// SPDX-License-Identifier: GPL-2.0-only
/**
 * "Film response": a film pushed the way a negative and its print build their look, instead of
 * scaling every difference from Standard (which also doubles a film's faded black and compressed white
 * and made CineStill flat at night). From the 2026-10-31 study (tools/jpeg_experiments/film_strength_v3.ts):
 *  - the film's own black and white stay; its tonal change is amplified x1.5 in the midtones only,
 *    not in the deep shadows (from OkLab L 0.2, about sRGB 0.08: a film's toe keeps night shots open);
 *  - a print-like midtone S (contrast around mid grey, none at the ends);
 *  - its colour identity x1.5, with interlayer-style saturation in the midtones (+12 %: DIR couplers
 *    purify colour where density forms) and the print's desaturation towards white.
 */
import type { Op, RGB } from '../../../core/src/filmpack/looks';

const toLin = (v: number) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
const toDisp = (v: number) => (v <= 0.0031308 ? v * 12.92 : 1.055 * Math.max(0, v) ** (1 / 2.4) - 0.055);
const smooth = (lo: number, hi: number, x: number) => { const t = Math.min(1, Math.max(0, (x - lo) / (hi - lo))); return t * t * (3 - 2 * t); };

export function lab(c: RGB): RGB {
  const r = toLin(c[0]), g = toLin(c[1]), b = toLin(c[2]);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s, 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s, 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s];
}

function linOf(L: number, a: number, b: number): RGB {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3, m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3, s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s, -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s];
}

/** Lab -> display, shrinking chroma (same L and hue) until it fits instead of clipping channels. */
export function display(L: number, a: number, b: number): RGB {
  L = Math.min(1, Math.max(0, L));
  const inside = (k: number) => linOf(L, a * k, b * k).every(v => v >= -1e-4 && v <= 1 + 1e-4);
  let k = 1;
  if (!inside(1)) { let lo = 0, hi = 1; for (let i = 0; i < 18; i++) { const mid = (lo + hi) / 2; if (inside(mid)) lo = mid; else hi = mid; } k = lo; }
  const v = linOf(L, a * k, b * k);
  return [toDisp(Math.min(1, Math.max(0, v[0]))), toDisp(Math.min(1, Math.max(0, v[1]))), toDisp(Math.min(1, Math.max(0, v[2])))];
}

/**
 * The film's colour change x1.5, never past grey. A first version extrapolated a and b linearly: where a
 * film removes colour (black and white, toned black and white) x1.5 overshot through grey into the
 * complementary colour (Acros came out with a sepia sky and purple trees). Now:
 *  - a film that adds colour: chroma x1.5 of its change;
 *  - a film that removes some colour: the chroma ratio is extrapolated multiplicatively (never below 0);
 *  - a film that removes almost all of it (chroma under about a third, as monochrome and toned films):
 *    the film's own colour, toning included;
 *  - hue turns are amplified only where both colours are clearly chromatic.
 */
function pushColour(x: RGB, f: RGB, k: number): [number, number] {
  const cx = Math.hypot(x[1], x[2]), cf = Math.hypot(f[1], f[2]);
  const r = cf / Math.max(cx, 1e-6);
  const c = r >= 1 ? cx + k * (cf - cx) : cf * r ** ((k - 1) * smooth(0.25, 0.6, r));
  const hx = Math.atan2(x[2], x[1]), hf = Math.atan2(f[2], f[1]);
  const dh = ((hf - hx + 3 * Math.PI) % (2 * Math.PI)) - Math.PI;
  const h = hf + (k - 1) * dh * smooth(0.02, 0.05, cx) * smooth(0.02, 0.05, cf);
  return [c * Math.cos(h), c * Math.sin(h)];
}

/** A setting that may depend on the colour's OkLab hue (degrees, 0-360: skin 29-60, yellow 110, green 142, cyan 195, blue 264). */
export type Hued = number | ((hue: number) => number);
const at = (v: Hued, hue: number) => (typeof v === 'number' ? v : v(hue));

/** Warm colours (skin, reds, oranges, up to yellow) get `warm`, greens through blues and purples get `cool`;
 * the changes are broad (40 degrees) so the camera's matrix and curves can follow them. */
export const warmCool = (warm: number, cool: number): Hued => hue => {
  const w = smooth(85, 125, hue) * (1 - smooth(315, 350, hue));
  return warm + (cool - warm) * w;
};

/** `colour`: how far the film's colour change is pushed (1: as the film; v3: 1.5); `midSaturation`: the
 * interlayer saturation in the midtones (v3: 0.12). Lower values keep skin closer to Standard. Either may
 * depend on the hue; near neutral they take their value at skin's hue, so grey ramps keep one tint. */
export function filmResponse(op: Op, colour: Hued = 1.5, midSaturation: Hued = 0.12): Op {
  return c => {
    const x = lab(c), f = lab(op(c));
    const mid = smooth(0.2, 0.45, x[0]) * (1 - smooth(0.75, 0.95, x[0]));
    let L = x[0] + (1 + 0.5 * mid) * (f[0] - x[0]);
    L += 0.18 * (L - 0.5) * mid;
    const hue = ((Math.atan2(x[2], x[1]) * 180) / Math.PI + 360) % 360, chromatic = smooth(0.01, 0.04, Math.hypot(x[1], x[2]));
    const mixed = (v: Hued) => at(v, 45) + chromatic * (at(v, hue) - at(v, 45));
    const [a, b] = pushColour(x, f, mixed(colour));
    const s = (1 + mixed(midSaturation) * mid) * (1 - 0.2 * smooth(0.82, 1, L));
    return display(L, a * s, b * s);
  };
}
