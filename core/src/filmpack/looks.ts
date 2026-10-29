// SPDX-License-Identifier: GPL-2.0-only
import type { Gr3xFilmDefaults } from '../fw/gr3x/film-recipe';
import type { Grain } from '../color/grain';

/**
 * GR Mod's film library (GR III / IIIx films): the film pack's looks: each one a colour transform of the camera's Standard rendering
 * (display sRGB in, display sRGB out), written as a few operations in OkLab / linear light.
 * `cubeText` samples them into .cube files, which are fitted to GR III's film format (matrix, three
 * curves, second matrix) like any imported preset; what a hue-selective move cannot be in that
 * format, the fit approximates (examples/gr3x/film-pack/build.ts prints the error of every look).
 *
 * The Fujifilm film simulations and the film stocks are interpretations from their published
 * descriptions and well-known character, not measured profiles.
 */

export type RGB = [number, number, number];
export type Op = (c: RGB) => RGB;

// ------------------------------------------------------------------ colour spaces

const toLin = (v: number) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
const toDisp = (v: number) => (v <= 0.0031308 ? v * 12.92 : 1.055 * Math.max(0, v) ** (1 / 2.4) - 0.055);
const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);

function linToOklab(r: number, g: number, b: number): RGB {
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s];
}

function oklabToLin(L: number, a: number, b: number): RGB {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s];
}

/** Display sRGB to OkLCh (hue in degrees) and back; out-of-gamut results are clipped. */
function toLch(c: RGB): RGB {
  const [L, a, b] = linToOklab(toLin(c[0]), toLin(c[1]), toLin(c[2]));
  return [L, Math.hypot(a, b), ((Math.atan2(b, a) * 180) / Math.PI + 360) % 360];
}
function fromLch(L: number, C: number, h: number): RGB {
  const r = (h * Math.PI) / 180;
  const lin = oklabToLin(L, C * Math.cos(r), C * Math.sin(r));
  return [clamp01(toDisp(lin[0])), clamp01(toDisp(lin[1])), clamp01(toDisp(lin[2]))];
}

// ------------------------------------------------------------------ curves

/** Monotone cubic (Fritsch-Carlson) through points sorted by x. */
export function monotone(points: readonly [number, number][]): (x: number) => number {
  const n = points.length, xs = points.map(p => p[0]), ys = points.map(p => p[1]);
  const d = xs.slice(1).map((x, i) => (ys[i + 1] - ys[i]) / (x - xs[i]));
  const m = xs.map((_, i) => (i === 0 ? d[0] : i === n - 1 ? d[n - 2] : d[i - 1] * d[i] <= 0 ? 0 : (d[i - 1] + d[i]) / 2));
  for (let i = 0; i < n - 1; i++) {
    if (d[i] === 0) { m[i] = m[i + 1] = 0; continue; }
    const a = m[i] / d[i], b = m[i + 1] / d[i], s = a * a + b * b;
    if (s > 9) { const t = 3 / Math.sqrt(s); m[i] = t * a * d[i]; m[i + 1] = t * b * d[i]; }
  }
  return (x: number) => {
    if (x <= xs[0]) return ys[0];
    if (x >= xs[n - 1]) return ys[n - 1];
    let i = 0;
    while (x > xs[i + 1]) i++;
    const h = xs[i + 1] - xs[i], t = (x - xs[i]) / h, t2 = t * t, t3 = t2 * t;
    return (2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * h * m[i] + (-2 * t3 + 3 * t2) * ys[i + 1] + (t3 - t2) * h * m[i + 1];
  };
}

// ------------------------------------------------------------------ operations

/** The same tone curve on R, G and B (as film: contrast also adds saturation). */
export const curve = (points: [number, number][]): Op => {
  const f = monotone(points);
  return c => [clamp01(f(c[0])), clamp01(f(c[1])), clamp01(f(c[2]))];
};

/** A curve of its own per channel (cross-processing, colour casts that change with brightness). */
export const channelCurves = (r: [number, number][], g: [number, number][], b: [number, number][]): Op => {
  const f = [monotone(r), monotone(g), monotone(b)];
  return c => [clamp01(f[0](c[0])), clamp01(f[1](c[1])), clamp01(f[2](c[2]))];
};

/** OkLab chroma times `k`. */
export const saturation = (k: number): Op => c => { const [L, C, h] = toLch(c); return fromLch(L, C * k, h); };

/** Chroma by brightness: `shadows` at black, `mids` at middle grey, `highs` at white. */
export const saturationByTone = (shadows: number, mids: number, highs: number): Op => c => {
  const [L, C, h] = toLch(c);
  const k = L < 0.6 ? shadows + (mids - shadows) * (L / 0.6) : mids + (highs - mids) * ((L - 0.6) / 0.4);
  return fromLch(L, C * k, h);
};

export interface HueBand {
  /** OkLCh hue in degrees: red ~25, orange / skin ~55, yellow ~100, green ~140, cyan ~195, blue ~260, magenta ~330. */
  hue: number;
  /** Half width in degrees (cosine falloff). */
  width: number;
  sat?: number;
  /** Degrees added to the hue at the band's centre. */
  shift?: number;
  /** Lightness factor (only coloured pixels: neutrals are left alone). */
  light?: number;
}

/** Hue-selective saturation, hue and lightness changes (as Fujifilm's colour science pushes some hues). */
export const bands = (...list: HueBand[]): Op => c => {
  let [L, C, h] = toLch(c);
  const colourful = Math.min(1, C / 0.06);
  let k = 1, dh = 0, dl = 1;
  for (const b of list) {
    const dist = Math.abs(((h - b.hue + 540) % 360) - 180);
    if (dist >= b.width) continue;
    const w = 0.5 + 0.5 * Math.cos((Math.PI * dist) / b.width);
    k *= 1 + ((b.sat ?? 1) - 1) * w;
    dh += (b.shift ?? 0) * w;
    dl *= 1 + ((b.light ?? 1) - 1) * w * colourful;
  }
  return fromLch(L * dl, C * k, (h + dh + 360) % 360);
};

/** Pull hues within `width` of `hue` towards it (smoother, more even skin). */
export const attract = (hue: number, width: number, strength: number): Op => c => {
  const [L, C, h] = toLch(c);
  const d = ((h - hue + 540) % 360) - 180;
  if (Math.abs(d) >= width) return c;
  const w = 0.5 + 0.5 * Math.cos((Math.PI * d) / width);
  return fromLch(L, C, (h - d * strength * w + 360) % 360);
};

/** Split toning: OkLab (a, b) added in the shadows and in the highlights (a: +red / -green, b: +yellow / -blue). */
export const split = (shadow: [number, number], high: [number, number]): Op => c => {
  const [L0, a0, b0] = linToOklab(toLin(c[0]), toLin(c[1]), toLin(c[2]));
  const t = clamp01(L0), ws = (1 - t) * (1 - t) * (t > 0.02 ? 1 : t / 0.02), wh = t * t;
  const lin = oklabToLin(L0, a0 + shadow[0] * ws + high[0] * wh, b0 + shadow[1] * ws + high[1] * wh);
  return [clamp01(toDisp(lin[0])), clamp01(toDisp(lin[1])), clamp01(toDisp(lin[2]))];
};

/** White balance: gains on linear R, G, B (normalised so that luminance stays). */
export const balance = (r: number, g: number, b: number): Op => {
  const n = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return c => [clamp01(toDisp((toLin(c[0]) * r) / n)), clamp01(toDisp((toLin(c[1]) * g) / n)), clamp01(toDisp((toLin(c[2]) * b) / n))];
};

/** Linear-light channel mixer (rows: new R, G, B from old R, G, B). */
export const mixer = (m: number[][]): Op => c => {
  const l = [toLin(c[0]), toLin(c[1]), toLin(c[2])];
  return [0, 1, 2].map(r => clamp01(toDisp(m[r][0] * l[0] + m[r][1] * l[1] + m[r][2] * l[2]))) as RGB;
};

/**
 * Skies toward teal, the way film does it and the camera's film format can carry it: a linear-light
 * channel mix that trims red (by `red`) and lifts green (by `green`) in proportion to how far blue
 * stands above them. Blue skies and water turn cyan-teal; warm colours, which have little blue, move
 * little (a touch warmer). Neutrals stay neutral (every row sums to 1).
 */
export const teal = (red: number, green: number): Op => mixer([[1, red, -red], [0, 1 - green, green], [0, 0, 1]]);

/**
 * Greens toward cyan (Superia-like foliage): blue lifted where green stands above red. Foliage turns
 * teal-green, skin and yellows (more red than green) get a touch less blue, so a little warmer.
 */
export const greenCyan = (amount: number): Op => mixer([[1, 0, 0], [0, 1, 0], [-amount, amount, 1]]);

/** Black and white from linear light with filter weights (they should sum to 1). */
export const mono = (wr: number, wg: number, wb: number): Op => c => {
  const y = clamp01(toDisp(wr * toLin(c[0]) + wg * toLin(c[1]) + wb * toLin(c[2])));
  return [y, y, y];
};

export const chain = (...ops: Op[]): Op => c => ops.reduce((v, op) => op(v), c);

// ------------------------------------------------------------------ the looks

export type LookGroup = 'fujifilm' | 'stock' | 'oppo' | 'creative';

export interface Look {
  /** Camera menu name (1..24 printable ASCII). */
  name: string;
  /** Where the look comes from (the library's sections). */
  group: LookGroup;
  /** Icon: caption (up to 9 characters) and a big code (up to 3). */
  caption: string;
  code: string;
  /** Icon colours: panel, caption band, code ink, caption ink. */
  colors: { panel: RGB; band: RGB; ink: RGB; captionInk: RGB };
  /** One line for the README / preview page. */
  about: string;
  /** The film's recipe besides its colour (GR III round 10): where the camera's parameters start
   * (film-recipe.ts) and its grain (grain.ts). */
  recipe?: { defaults?: Gr3xFilmDefaults; grain?: Grain };
  op: Op;
}

export const LOOKS: Look[] = [
  // ---------------------------------------------------------------- Fujifilm film simulations
  {
    name: 'Velvia', group: 'fujifilm', caption: 'VELVIA', code: 'V',
    colors: { panel: [32, 86, 160], band: [62, 150, 72], ink: [255, 214, 64], captionInk: [255, 255, 255] },
    about: 'Landscape slide film: deep blue skies, lush greens, reds leaning magenta, dense shadows.',
    recipe: { defaults: { sharpness: 1, clarity: 1 } },
    op: chain(
      curve([[0, 0], [0.1, 0.072], [0.25, 0.212], [0.5, 0.5], [0.75, 0.785], [0.9, 0.925], [1, 1]]),
      saturation(1.16),
      bands(
        { hue: 140, width: 45, sat: 1.12, shift: 5, light: 0.95 },
        { hue: 255, width: 45, sat: 1.12, shift: 4, light: 0.9 },
        { hue: 25, width: 30, sat: 1.06, shift: -6 },
        { hue: 60, width: 22, sat: 0.92 },
      ),
    ),
  },
  {
    name: 'Astia', group: 'fujifilm', caption: 'ASTIA', code: 'A',
    colors: { panel: [196, 92, 132], band: [62, 150, 72], ink: [255, 255, 255], captionInk: [255, 255, 255] },
    about: 'Soft slide film: vivid blues and greens over a gentle tonal scale, flattering skin.',
    recipe: {},
    op: chain(
      curve([[0, 0], [0.15, 0.138], [0.5, 0.505], [0.8, 0.79], [0.95, 0.93], [1, 0.99]]),
      saturation(1.08),
      bands(
        { hue: 245, width: 50, sat: 1.1 },
        { hue: 145, width: 45, sat: 1.06, shift: 3 },
        { hue: 55, width: 28, sat: 0.94, light: 1.02 },
      ),
      split([0, 0], [0.002, 0.006]),
    ),
  },
  {
    name: 'Classic Chrome', group: 'fujifilm', caption: 'CLASSIC', code: 'CC',
    colors: { panel: [118, 108, 92], band: [196, 80, 44], ink: [242, 232, 206], captionInk: [255, 255, 255] },
    about: 'Documentary magazine colour: muted, cyan-leaning skies, olive greens, hard shadows.',
    recipe: { defaults: { clarity: 1 }, grain: { amount: 1, size: 'small' } },
    op: chain(
      mixer([[1.153, 0.168, -0.320], [0.026, 0.834, 0.140], [-0.079, 0.086, 0.992]]), // teal skies (teal_solve.py)
      curve([[0, 0], [0.1, 0.068], [0.25, 0.21], [0.5, 0.5], [0.75, 0.77], [0.92, 0.92], [1, 0.99]]),
      saturation(0.76),
      bands(
        { hue: 25, width: 30, sat: 0.95, shift: 5, light: 0.96 },
        { hue: 80, width: 38, sat: 0.85, shift: 9, light: 0.97 },
        { hue: 50, width: 26, shift: 4 },
        { hue: 135, width: 42, sat: 0.8, shift: 2 },
        { hue: 225, width: 50, sat: 0.92, light: 0.94 },
      ),
      split([-0.004, -0.006], [0.002, 0.008]),
    ),
  },
  {
    name: 'Classic Neg', group: 'fujifilm', caption: 'CLASSIC', code: 'NC',
    colors: { panel: [40, 120, 116], band: [212, 60, 60], ink: [255, 236, 170], captionInk: [255, 255, 255] },
    about: 'Everyday colour negative: hard contrast, teal shadows, warm highlights, cyan skies, rosy reds.',
    recipe: { defaults: { clarity: 1 }, grain: { amount: 1, size: 'small' } },
    op: chain(
      mixer([[1.451, -0.383, -0.068], [0.151, 0.492, 0.358], [-0.080, 0.088, 0.992]]), // teal skies (teal_solve.py)
      curve([[0, 0], [0.1, 0.055], [0.3, 0.262], [0.5, 0.5], [0.7, 0.735], [0.9, 0.915], [1, 0.975]]),
      saturation(0.8),
      bands(
        { hue: 28, width: 30, sat: 1.18, shift: -7 },
        { hue: 60, width: 20, sat: 0.95 },
        { hue: 95, width: 34, sat: 0.88, shift: 14 },
        { hue: 160, width: 45, sat: 0.85, light: 0.92 },
        { hue: 220, width: 45, sat: 0.95, light: 0.9 },
      ),
      split([-0.024, -0.01], [0.006, 0.02]),
      saturationByTone(1.05, 1.0, 0.78),
    ),
  },
  {
    name: 'Nostalgic Neg', group: 'fujifilm', caption: 'NOSTALGIC', code: 'NN',
    colors: { panel: [168, 98, 40], band: [236, 176, 70], ink: [255, 246, 220], captionInk: [70, 40, 20] },
    about: '1970s American new colour: amber highlights, rich shadows, warm golden softness.',
    recipe: { defaults: { sharpness: -1 }, grain: { amount: 1, size: 'small' } },
    op: chain(
      mixer([[1.076, 0.092, -0.168], [0.060, 0.944, -0.004], [0.047, -0.081, 1.034]]), // teal skies (teal_solve.py)
      curve([[0, 0], [0.1, 0.08], [0.3, 0.29], [0.5, 0.5], [0.75, 0.742], [0.9, 0.878], [1, 0.97]]),
      split([0.002, 0.004], [0.01, 0.03]),
      saturationByTone(1.14, 1.02, 0.88),
      bands(
        { hue: 30, width: 30, sat: 1.05, shift: 6 },
        { hue: 140, width: 42, sat: 0.86, shift: -12 },
        { hue: 240, width: 50, sat: 0.85 },
      ),
    ),
  },
  {
    name: 'Pro Neg Hi', group: 'fujifilm', caption: 'PRO NEG', code: 'NH',
    colors: { panel: [70, 76, 96], band: [150, 150, 160], ink: [255, 255, 255], captionInk: [30, 30, 40] },
    about: 'Portrait negative with a little punch: natural skin, moderate contrast, restrained colour.',
    recipe: { defaults: { sharpness: -1 } },
    op: chain(
      curve([[0, 0], [0.15, 0.142], [0.5, 0.5], [0.85, 0.862], [1, 1]]),
      saturation(0.9),
      attract(52, 28, 0.3),
      bands({ hue: 52, width: 28, sat: 1.04, light: 1.015 }),
      split([-0.003, -0.004], [0, 0.002]),
    ),
  },
  {
    name: 'Pro Neg Std', group: 'fujifilm', caption: 'PRO NEG', code: 'NS',
    colors: { panel: [110, 116, 130], band: [190, 190, 196], ink: [255, 255, 255], captionInk: [30, 30, 40] },
    about: 'Studio portrait negative: very soft tonality, low saturation, smooth skin.',
    recipe: { defaults: { sharpness: -1, clarity: -1 } },
    op: chain(
      mixer([[1.334, -0.241, -0.093], [0.198, 0.808, -0.006], [0.140, -0.141, 1.001]]), // teal skies (teal_solve.py)
      curve([[0, 0.012], [0.2, 0.212], [0.5, 0.5], [0.8, 0.788], [1, 0.985]]),
      saturation(0.78),
      attract(52, 28, 0.25),
      bands({ hue: 145, width: 40, sat: 0.88, shift: 6 }),
      split([-0.006, -0.002], [0.001, 0.003]),
    ),
  },
  {
    name: 'Eterna', group: 'fujifilm', caption: 'ETERNA', code: 'E',
    colors: { panel: [30, 64, 70], band: [90, 140, 140], ink: [240, 196, 120], captionInk: [255, 255, 255] },
    about: 'Motion picture film: flat, lifted, desaturated, teal shadows, skin kept warm.',
    recipe: { defaults: { sharpness: -1, halation: { strength: 1, white: true } }, grain: { amount: 1, size: 'small' } },
    op: chain(
      mixer([[1.267, -0.155, -0.112], [0.076, 0.682, 0.242], [-0.075, 0.081, 0.994]]), // teal skies (teal_solve.py)
      curve([[0, 0.024], [0.15, 0.15], [0.5, 0.49], [0.8, 0.775], [0.95, 0.915], [1, 0.96]]),
      saturation(0.68),
      bands(
        { hue: 55, width: 30, sat: 1.12 },
        { hue: 250, width: 50, sat: 0.9 },
        { hue: 140, width: 40, sat: 0.85, shift: 10 },
      ),
      split([-0.012, -0.008], [0.003, 0.006]),
    ),
  },
  {
    name: 'Acros', group: 'fujifilm', caption: 'ACROS', code: 'AC',
    colors: { panel: [24, 24, 24], band: [110, 110, 110], ink: [255, 255, 255], captionInk: [255, 255, 255] },
    about: 'Fine-grain black and white: deep blacks, smooth bright highlights, rich midtone separation.',
    recipe: { defaults: { sharpness: 1 }, grain: { amount: 2, size: 'small' } },
    op: chain(
      mono(0.3, 0.6, 0.1),
      curve([[0, 0], [0.08, 0.048], [0.25, 0.205], [0.5, 0.5], [0.78, 0.812], [0.95, 0.962], [1, 1]]),
    ),
  },
  {
    name: 'Acros Red', group: 'fujifilm', caption: 'ACROS+R', code: 'AR',
    colors: { panel: [24, 24, 24], band: [200, 40, 40], ink: [255, 255, 255], captionInk: [255, 255, 255] },
    about: 'Acros through a red filter: dark dramatic skies, luminous skin and brick.',
    recipe: { defaults: { clarity: 1 }, grain: { amount: 2, size: 'small' } },
    op: chain(
      mono(0.72, 0.33, -0.05),
      curve([[0, 0], [0.08, 0.044], [0.25, 0.2], [0.5, 0.5], [0.78, 0.82], [0.95, 0.966], [1, 1]]),
    ),
  },
  // ---------------------------------------------------------------- film stocks, as Fujifilm recipes do them
  {
    name: 'Kodachrome 64', group: 'stock', caption: 'KODACHR', code: '64',
    colors: { panel: [194, 44, 53], band: [248, 191, 39], ink: [255, 255, 255], captionInk: [255, 255, 255] },
    about: 'The classic slide: iconic deep reds, dense blue skies, warm and contrasty.',
    recipe: { defaults: { sharpness: 1, clarity: 1 }, grain: { amount: 1, size: 'small' } },
    op: chain(
      mixer([[1.125, 0.030, -0.154], [0.087, 0.916, -0.003], [0.067, -0.099, 1.033]]), // teal skies (teal_solve.py)
      curve([[0, 0], [0.1, 0.064], [0.3, 0.278], [0.5, 0.5], [0.75, 0.78], [0.92, 0.935], [1, 1]]),
      saturation(0.94),
      bands(
        { hue: 25, width: 30, sat: 1.25, shift: 2, light: 0.95 },
        { hue: 80, width: 30, sat: 1.05 },
        { hue: 140, width: 40, sat: 0.8, shift: -8 },
        { hue: 250, width: 45, sat: 1.1, light: 0.88 },
      ),
      split([0, -0.004], [0.004, 0.014]),
    ),
  },
  {
    name: 'Portra 400', group: 'stock', caption: 'PORTRA', code: '400',
    colors: { panel: [116, 86, 154], band: [248, 191, 39], ink: [255, 255, 255], captionInk: [60, 40, 90] },
    about: 'The portrait negative: creamy warm highlights, glowing skin, pastel greens and blues.',
    recipe: { defaults: { sharpness: -1, clarity: -1 }, grain: { amount: 1, size: 'small' } },
    op: chain(
      mixer([[1.120, 0.063, -0.183], [0.081, 0.829, 0.090], [0.028, -0.063, 1.036]]), // teal skies (teal_solve.py)
      curve([[0, 0.015], [0.2, 0.206], [0.5, 0.51], [0.8, 0.81], [0.95, 0.935], [1, 0.97]]),
      split([-0.003, 0], [0.006, 0.02]),
      saturation(0.88),
      attract(52, 28, 0.25),
      bands(
        { hue: 50, width: 30, sat: 1.08, shift: 2, light: 1.02 },
        { hue: 140, width: 40, sat: 0.75, shift: -14 },
        { hue: 245, width: 50, sat: 0.8, light: 1.03 },
      ),
    ),
  },
  {
    name: 'Gold 200', group: 'stock', caption: 'GOLD', code: '200',
    colors: { panel: [151, 39, 136], band: [248, 191, 39], ink: [255, 220, 60], captionInk: [192, 32, 46] },
    about: 'Sunny consumer film: golden cast, warm saturated yellows and oranges, summer nostalgia.',
    recipe: { defaults: { halation: { strength: 1 } }, grain: { amount: 2, size: 'small' } },
    op: chain(
      mixer([[1.125, 0.030, -0.154], [0.087, 0.916, -0.003], [0.067, -0.099, 1.033]]), // teal skies (teal_solve.py)
      curve([[0, 0], [0.12, 0.1], [0.5, 0.51], [0.85, 0.86], [1, 0.985]]),
      split([0.002, 0.008], [0.006, 0.03]),
      saturation(1.04),
      bands(
        { hue: 85, width: 35, sat: 1.15, shift: -4 },
        { hue: 30, width: 25, sat: 1.05, shift: 6 },
        { hue: 140, width: 40, sat: 0.9, shift: -10 },
        { hue: 250, width: 50, sat: 0.85 },
      ),
    ),
  },
  {
    name: 'CineStill 800T', group: 'stock', caption: 'CINE', code: '8T',
    colors: { panel: [20, 20, 22], band: [211, 38, 49], ink: [255, 255, 255], captionInk: [255, 255, 255] },
    about: 'Tungsten cinema stock for the night: cool teal shadows, glowing reds. Try it with Halation.',
    recipe: { defaults: { sharpness: -1, halation: { strength: 2 } }, grain: { amount: 2, size: 'large' } },
    op: chain(
      balance(0.9, 0.98, 1.14),
      curve([[0, 0.01], [0.15, 0.132], [0.5, 0.5], [0.85, 0.87], [1, 0.99]]),
      split([-0.026, -0.03], [0.006, 0.0]),
      saturation(0.9),
      bands(
        { hue: 28, width: 30, sat: 1.22, shift: -4 },
        { hue: 60, width: 25, sat: 0.95, shift: -3 },
        { hue: 90, width: 30, sat: 0.85 },
        { hue: 140, width: 40, sat: 0.8, shift: 20 },
      ),
    ),
  },
  // ---------------------------------------------------------------- OPPO Find X9 (from reviewers' descriptions)
  {
    name: 'Primrose', group: 'oppo', caption: 'PRIMROSE', code: 'PR',
    colors: { panel: [228, 196, 92], band: [120, 150, 80], ink: [80, 50, 30], captionInk: [255, 255, 255] },
    about: "OPPO Find X9's Portra-inspired filter: warm soft shadows, gentle contrast, greens and city tones kept pleasant.",
    recipe: { defaults: { sharpness: -1 }, grain: { amount: 1, size: 'small' } },
    op: chain(
      mixer([[1.297, -0.176, -0.121], [0.202, 0.721, 0.077], [0.146, -0.231, 1.084]]), // teal skies (teal_solve.py)
      curve([[0, 0.022], [0.15, 0.158], [0.5, 0.505], [0.82, 0.825], [0.95, 0.94], [1, 0.975]]),
      split([0.008, 0.016], [0.004, 0.014]),
      saturation(0.92),
      attract(55, 28, 0.2),
      bands(
        { hue: 55, width: 30, sat: 1.04, light: 1.02 },
        { hue: 130, width: 45, sat: 0.98, shift: -8 },
        { hue: 245, width: 50, sat: 0.85, light: 1.02 },
      ),
    ),
  },
  {
    name: 'Hasselblad Std', group: 'oppo', caption: 'HASSEL', code: 'H',
    colors: { panel: [30, 30, 32], band: [180, 180, 184], ink: [255, 255, 255], captionInk: [20, 20, 20] },
    about: 'Hasselblad natural colour (as OPPO tunes it): true-to-life hues, soft highlight roll-off, open shadows, unforced skin.',
    recipe: {},
    op: chain(
      curve([[0, 0.006], [0.12, 0.118], [0.5, 0.5], [0.85, 0.84], [0.95, 0.935], [1, 0.985]]),
      saturation(0.94),
      bands(
        { hue: 25, width: 30, sat: 1.05, shift: 2 },
        { hue: 60, width: 25, sat: 0.94, shift: -3 },
        { hue: 140, width: 45, sat: 0.95, shift: 4 },
        { hue: 250, width: 50, sat: 1.03, shift: 3 },
      ),
      split([0, -0.002], [0.001, 0.003]),
    ),
  },
  // ---------------------------------------------------------------- creative
  {
    name: 'Aerochrome', group: 'creative', caption: 'INFRARED', code: 'IR',
    colors: { panel: [190, 30, 110], band: [40, 40, 120], ink: [255, 255, 255], captionInk: [255, 255, 255] },
    about: 'False-colour infrared: foliage and grass turn crimson, skies go cyan-blue, skin stays pale. Wild in summer.',
    recipe: { defaults: { clarity: 1 }, grain: { amount: 2, size: 'small' } },
    op: chain(
      mixer([[0.65, 0.5, -0.15], [0.55, -0.1, 0.55], [0.1, 0.2, 0.7]]),
      saturation(1.2),
      curve([[0, 0], [0.12, 0.1], [0.5, 0.5], [0.88, 0.9], [1, 1]]),
    ),
  },
  {
    name: 'Instant', group: 'creative', caption: 'INSTANT', code: 'IN',
    colors: { panel: [236, 230, 214], band: [60, 140, 160], ink: [40, 40, 40], captionInk: [255, 255, 255] },
    about: 'Instant film: low contrast, milky blacks, creamy highlights, cyan-tinted shadows.',
    recipe: { defaults: { sharpness: -2, clarity: -1 }, grain: { amount: 1, size: 'large' } },
    op: chain(
      mixer([[1.267, -0.155, -0.112], [0.076, 0.682, 0.242], [-0.075, 0.081, 0.994]]), // teal skies (teal_solve.py)
      curve([[0, 0.09], [0.2, 0.24], [0.5, 0.5], [0.8, 0.78], [1, 0.92]]),
      split([-0.02, -0.008], [0.008, 0.032]),
      saturation(0.76),
      bands(
        { hue: 30, width: 30, sat: 1.05, shift: 8 },
        { hue: 250, width: 50, sat: 0.8 },
        { hue: 140, width: 40, sat: 0.85, shift: 10 },
      ),
    ),
  },
  {
    name: 'Blockbuster', group: 'creative', caption: 'CINEMA', code: 'TO',
    colors: { panel: [20, 96, 110], band: [236, 120, 40], ink: [255, 170, 80], captionInk: [255, 255, 255] },
    about: 'Teal and orange grade: warm skin and lights against teal shadows and skies.',
    recipe: { defaults: { clarity: 1, halation: { strength: 1, white: true } }, grain: { amount: 1, size: 'large' } },
    op: chain(
      mixer([[1.463, -0.400, -0.064], [0.146, 0.438, 0.415], [-0.140, 0.216, 0.924]]), // teal skies (teal_solve.py)
      curve([[0, 0], [0.1, 0.068], [0.5, 0.5], [0.9, 0.93], [1, 1]]),
      bands(
        { hue: 55, width: 40, sat: 1.28, shift: -2 },
        { hue: 245, width: 60, sat: 1.1 },
        { hue: 140, width: 50, sat: 0.75, shift: 40 },
        { hue: 100, width: 25, sat: 0.85, shift: -18 },
      ),
      split([-0.036, -0.03], [0.014, 0.03]),
      saturation(0.9),
    ),
  },
  {
    name: 'Platinum', group: 'creative', caption: 'PLATINUM', code: 'PT',
    colors: { panel: [60, 64, 76], band: [196, 170, 130], ink: [240, 226, 200], captionInk: [40, 36, 30] },
    about: 'Split-toned black and white: cool shadows, warm platinum highlights, soft contrast.',
    recipe: { defaults: { clarity: -1 }, grain: { amount: 2, size: 'small' } },
    op: chain(
      mono(0.3, 0.6, 0.1),
      curve([[0, 0.02], [0.1, 0.08], [0.25, 0.215], [0.5, 0.5], [0.8, 0.81], [1, 0.985]]),
      split([-0.006, -0.016], [0.006, 0.02]),
    ),
  },
];

/** A look as a .cube (33 points, sRGB display domain). */
export function cubeText(look: Look, size = 33): string {
  const lines = [`TITLE "${look.name}"`, `LUT_3D_SIZE ${size}`, 'DOMAIN_MIN 0 0 0', 'DOMAIN_MAX 1 1 1'];
  for (let b = 0; b < size; b++) for (let g = 0; g < size; g++) for (let r = 0; r < size; r++) {
    const o = look.op([r / (size - 1), g / (size - 1), b / (size - 1)]);
    lines.push(`${o[0].toFixed(6)} ${o[1].toFixed(6)} ${o[2].toFixed(6)}`);
  }
  return lines.join('\n') + '\n';
}
