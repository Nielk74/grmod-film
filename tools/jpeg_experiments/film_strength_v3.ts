// Stronger film variants -> real Engine fit -> camera-quantized 17^3 grids for the comparison page.
// A variant moves each film further from Standard in OkLab: L by kL, a/b by kC (k = 1 is the film as shipped).
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { Engine } from '../../core/src/app/engine';
import { LOOKS, cubeText } from '../../core/src/filmpack/looks';
import type { Look, RGB, Op } from '../../core/src/filmpack/looks';
import { GR3X_CAMERA } from '../../core/src/color/gr3x-camera';
import type { PresetResult } from '../../core/src/app/engine';

const toLin = (v: number) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
const toDisp = (v: number) => (v <= 0.0031308 ? v * 12.92 : 1.055 * Math.max(0, v) ** (1 / 2.4) - 0.055);
function lab(c: RGB): RGB {
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
function display(L: number, a: number, b: number): RGB {
  L = Math.min(1, Math.max(0, L));
  const inside = (k: number) => linOf(L, a * k, b * k).every(v => v >= -1e-4 && v <= 1 + 1e-4);
  let k = 1;
  if (!inside(1)) { let lo = 0, hi = 1; for (let i = 0; i < 18; i++) { const mid = (lo + hi) / 2; if (inside(mid)) lo = mid; else hi = mid; } k = lo; }
  const v = linOf(L, a * k, b * k);
  return [toDisp(Math.min(1, Math.max(0, v[0]))), toDisp(Math.min(1, Math.max(0, v[1]))), toDisp(Math.min(1, Math.max(0, v[2])))];
}
function stronger(op: Op, kL: number, kC: number): Op {
  return c => {
    const x = lab(c), f = lab(op(c));
    const [a, b] = pushColour(x, f, kC);
    return display(x[0] + kL * (f[0] - x[0]), a, b);
  };
}

const smooth = (lo: number, hi: number, x: number) => { const t = Math.min(1, Math.max(0, (x - lo) / (hi - lo))); return t * t * (3 - 2 * t); };
/**
 * A film's colour change scaled by k, never past grey (examples/gr3x/film-pack-v3/response.ts). A first
 * version extrapolated a and b linearly: on black-and-white films it overshot through grey into the
 * complementary colour (Acros with a sepia sky and purple trees). Adding colour: chroma change x k;
 * removing some: multiplicative (never below 0); removing almost all (monochrome, toned): the film's own
 * colour; hue turns amplified only where both colours are clearly chromatic.
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
/**
 * "Film response": push a film the way negative + print film builds its look, instead of scaling every
 * difference from Standard (which doubles a film's faded black and compressed white too):
 *  - the film's own black and white stay; its tonal change is amplified in the midtones only (x1.5),
 *    and not in the deep shadows (a first try from OkLab 0.08 crushed night shots);
 *  - a print-like midtone S (contrast around mid grey, none at the ends);
 *  - its colour identity x1.5, with interlayer-style saturation in the midtones (DIR couplers: purer
 *    colour where density forms) and the print's highlight desaturation towards white.
 */
function filmResponse(op: Op): Op {
  return c => {
    const x = lab(c), f = lab(op(c));
    // starts above the deep shadows (OkLab 0.2, about sRGB 0.08): a film's toe keeps night shots open
    const mid = smooth(0.2, 0.45, x[0]) * (1 - smooth(0.75, 0.95, x[0]));
    let L = x[0] + (1 + 0.5 * mid) * (f[0] - x[0]);
    L += 0.18 * (L - 0.5) * mid;
    const [a, b] = pushColour(x, f, 1.5);
    const s = (1 + 0.12 * mid) * (1 - 0.2 * smooth(0.82, 1, L));
    return display(L, a * s, b * s);
  };
}

function inverse(a: number[]): number[] {
  const [a0, b, c, d, e, f, g, h, i] = a;
  const det = a0 * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g);
  return [(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det, (f * g - d * i) / det, (a0 * i - c * g) / det, (c * d - a0 * f) / det, (d * h - e * g) / det, (b * g - a0 * h) / det, (a0 * e - b * d) / det];
}
function product(a: number[], b: number[]): number[] {
  return Array.from({ length: 9 }, (_, j) => [0, 1, 2].reduce((s, k) => s + a[Math.floor(j / 3) * 3 + k] * b[k * 3 + j % 3], 0));
}
/** The stored coefficients evaluated as the camera chains them (same as film_pipeline_v2.ts). */
function nativeGrid(fit: PresetResult, standard: number[], grid: Float64Array): Float32Array {
  const matrix = product(Array.from(fit.matrixQ13, v => v / 8192), inverse(standard.map(v => v / 8192)));
  const post = fit.postQ9 ? Array.from(fit.postQ9, v => v / 512) : [1, 0, 0, 0, 1, 0, 0, 0, 1];
  const out = new Float32Array(grid.length), lin = [0, 0, 0], curved = [0, 0, 0];
  for (let p = 0; p < grid.length; p += 3) {
    for (let c = 0; c < 3; c++) lin[c] = GR3X_CAMERA.Sinv(grid[p + c]);
    for (let c = 0; c < 3; c++) {
      const l = matrix[c * 3] * lin[0] + matrix[c * 3 + 1] * lin[1] + matrix[c * 3 + 2] * lin[2];
      const disp = GR3X_CAMERA.S(Math.max(0, Math.min(1, l)));
      const position = Math.max(0, Math.min(255, disp * 16383 / 64));
      const low = Math.min(254, Math.floor(position)), t = position - low;
      curved[c] = (fit.curves[c][low] * (1 - t) + fit.curves[c][low + 1] * t) / 16383;
    }
    for (let c = 0; c < 3; c++) out[p + c] = Math.max(0, Math.min(1, post[c * 3] * curved[0] + post[c * 3 + 1] * curved[1] + post[c * 3 + 2] * curved[2]));
  }
  return out;
}

const [firmware, outDir, only] = process.argv.slice(2).filter(a => a !== '--');
mkdirSync(outDir, { recursive: true });
const engine = await Engine.open(new Uint8Array(readFileSync(firmware)));
const N = 17, grid = new Float64Array(N ** 3 * 3);
let at = 0;
for (let r = 0; r < N; r++) for (let g = 0; g < N; g++) for (let b = 0; b < N; b++) { grid[at++] = r / (N - 1); grid[at++] = g / (N - 1); grid[at++] = b / (N - 1); }
const VARIANTS = [
  { id: 'current', label: 'As shipped', kL: 1, kC: 1 },
  { id: 'x1.5', label: 'Intensity ×1.5', kL: 1.5, kC: 1.5 },
  { id: 'x2', label: 'Intensity ×2', kL: 2, kC: 2 },
  { id: 'tone', label: 'Tone-led (L×2, colour×1.25)', kL: 2, kC: 1.25 },
  { id: 'film', label: 'Film response (mid tone, print S, colour×1.5)', kL: 0, kC: 1.5 },
];
const models: object[] = [];
for (const [i, base] of LOOKS.entries()) {
  if (only && !base.name.toLowerCase().includes(only.toLowerCase())) continue;
  for (const v of VARIANTS) {
    const op = v.id === 'current' ? base.op : v.id === 'film' ? filmResponse(base.op) : stronger(base.op, v.kL, v.kC);
    const look: Look = { ...base, op };
    const t0 = Date.now();
    let fit: PresetResult, post = true;
    try { fit = engine.convertPreset('cube', cubeText(look, 33), undefined, { post: true }); }
    catch (e) {
      // The camera's post-curve matrix is 12-bit: a target that needs more is fitted without it.
      console.log(`${base.name} ${v.id}: ${(e as Error).message}; refitting without the post matrix`);
      fit = engine.convertPreset('cube', cubeText(look, 33), undefined, { post: false }); post = false;
    }
    const native = nativeGrid(fit, engine.info.standardMatrixQ13, grid);
    const target = new Float32Array(grid.length);
    for (let p = 0; p < grid.length; p += 3) target.set(op([grid[p], grid[p + 1], grid[p + 2]] as RGB), p);
    const file = `${String(i + 1).padStart(2, '0')}-${v.id}`;
    writeFileSync(join(outDir, file + '-native.f32'), new Uint8Array(native.buffer));
    writeFileSync(join(outDir, file + '-target.f32'), new Uint8Array(target.buffer));
    models.push({ film: base.name, index: i + 1, variant: v.id, label: v.label, kL: v.kL, kC: v.kC, file, postMatrix: post, fitMeanDE2000: fit.meanDE2000, fitP95DE2000: fit.p95DE2000 });
    console.log(`${base.name} ${v.id}: fit ${fit.meanDE2000.toFixed(2)} / p95 ${fit.p95DE2000.toFixed(2)} (${Date.now() - t0} ms)`);
  }
}
writeFileSync(join(outDir, 'models.json'), JSON.stringify({ grid: N, order: '[r,g,b,ch], b fastest, float32 LE', firmware: engine.info.sha256, models }, null, 1));
