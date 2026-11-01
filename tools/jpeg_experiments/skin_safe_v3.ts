// Skin-natural film response: per film, the strongest colour push that keeps skin's saturation within
// x1.2 of camera Standard (median over skin samples from the user's portraits), fitted through GR Mod's
// Engine and added to the comparison page as variant "skinsafe". A second candidate, "skinonly", keeps the
// full film response and caps chroma only on skin colours (OkLab hue 20-80 deg, chroma 0.015-0.18, from
// the samples: hue 29-60, chroma 0.03-0.11) at x1.15 of Standard; the fit shows how much of that the
// camera's global matrix and curves can hold (2026-11-01: almost none, Gold 200 skin x1.67 -> x1.58; run
// with SKIN_ONLY=1). Where the skin-safe push falls below the film's own colour (Gold 200, Nostalgic Neg),
// a middle candidate "filmcolour" keeps the film-response tone with the film's colour as authored.
//   vite-node skin_safe_v3.ts -- OFFICIAL.bin COMPARE_DIR
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { Engine } from '../../core/src/app/engine';
import { LOOKS, cubeText } from '../../core/src/filmpack/looks';
import type { RGB } from '../../core/src/filmpack/looks';
import { GR3X_CAMERA } from '../../core/src/color/gr3x-camera';
import type { PresetResult } from '../../core/src/app/engine';
import { display, filmResponse, lab } from '../../examples/gr3x/film-pack-v3/response';

const FILMS = ['Gold 200', 'Nostalgic Neg', 'Astia', 'Kodachrome 64'];
const LIMIT = 1.2;

const toLin = (v: number) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
/** CIELab chroma (D65), as the skin measurements on the page. */
function chroma(c: RGB): number {
  const r = toLin(c[0]), g = toLin(c[1]), b = toLin(c[2]);
  const X = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047, Y = 0.2126 * r + 0.7152 * g + 0.0722 * b, Z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883;
  const f = (t: number) => (t > 216 / 24389 ? Math.cbrt(t) : (841 / 108) * t + 4 / 29);
  return Math.hypot(500 * (f(X) - f(Y)), 200 * (f(Y) - f(Z)));
}
const smooth = (lo: number, hi: number, x: number) => { const t = Math.min(1, Math.max(0, (x - lo) / (hi - lo))); return t * t * (3 - 2 * t); };
const median = (a: number[]) => { const s = [...a].sort((p, q) => p - q); return s[Math.floor(s.length / 2)]; };

function inverse(a: number[]): number[] {
  const [a0, b, c, d, e, f, g, h, i] = a;
  const det = a0 * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g);
  return [(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det, (f * g - d * i) / det, (a0 * i - c * g) / det, (c * d - a0 * f) / det, (d * h - e * g) / det, (b * g - a0 * h) / det, (a0 * e - b * d) / det];
}
function product(a: number[], b: number[]): number[] {
  return Array.from({ length: 9 }, (_, j) => [0, 1, 2].reduce((s, k) => s + a[Math.floor(j / 3) * 3 + k] * b[k * 3 + j % 3], 0));
}
/** The stored coefficients evaluated as the camera chains them (as film_strength_v3.ts). */
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

const [firmware, dir] = process.argv.slice(2).filter(a => a !== '--');
const engine = await Engine.open(new Uint8Array(readFileSync(firmware)));
const skin = JSON.parse(readFileSync(join(dir, 'skin-samples.json'), 'utf8')) as RGB[];
const modelsPath = join(dir, 'models', 'models.json');
const models = JSON.parse(readFileSync(modelsPath, 'utf8'));
const N = models.grid, grid = new Float64Array(N ** 3 * 3);
let at = 0;
for (let r = 0; r < N; r++) for (let g = 0; g < N; g++) for (let b = 0; b < N; b++) { grid[at++] = r / (N - 1); grid[at++] = g / (N - 1); grid[at++] = b / (N - 1); }
const skinRatio = (op: (c: RGB) => RGB) => median(skin.map(c => chroma(op(c)) / Math.max(chroma(c), 1e-6)));

function save(name: string, variant: string, label: string, op: (c: RGB) => RGB, kC: number, extra: object) {
  const base = LOOKS.find(l => l.name === name)!;
  const fit = engine.convertPreset('cube', cubeText({ ...base, op }, 33), undefined, { post: true });
  const native = nativeGrid(fit, engine.info.standardMatrixQ13, grid);
  const target = new Float32Array(grid.length);
  for (let p = 0; p < grid.length; p += 3) target.set(op([grid[p], grid[p + 1], grid[p + 2]] as RGB), p);
  const index = LOOKS.indexOf(base) + 1, file = `${String(index).padStart(2, '0')}-${variant}`;
  writeFileSync(join(dir, 'models', file + '-native.f32'), new Uint8Array(native.buffer));
  writeFileSync(join(dir, 'models', file + '-target.f32'), new Uint8Array(target.buffer));
  models.models = models.models.filter((m: { film: string; variant: string }) => !(m.film === name && m.variant === variant));
  models.models.push({ film: name, index, variant, label, kL: 0, kC, file, postMatrix: !!fit.postQ9,
    fitMeanDE2000: fit.meanDE2000, fitP95DE2000: fit.p95DE2000, ...extra });
  return fit;
}

/** Full film response, with skin colours' chroma capped at `cap` x Standard. */
function skinOnly(op: (c: RGB) => RGB, cap: number): (c: RGB) => RGB {
  const film = filmResponse(op);
  return c => {
    const x = lab(c), y = lab(film(c));
    const cx = Math.hypot(x[1], x[2]), cy = Math.hypot(y[1], y[2]), h = Math.atan2(x[2], x[1]) * 180 / Math.PI;
    const w = smooth(20, 35, h) * (1 - smooth(65, 80, h)) * smooth(0.015, 0.03, cx) * (1 - smooth(0.13, 0.18, cx)) * smooth(0.25, 0.35, x[0]) * (1 - smooth(0.85, 0.95, x[0]));
    const k = cy > cap * cx ? 1 + w * (cap * cx / cy - 1) : 1;
    return display(y[0], y[1] * k, y[2] * k);
  };
}

for (const name of FILMS) {
  const base = LOOKS.find(l => l.name === name)!;
  const shipped = skinRatio(base.op), v3 = skinRatio(filmResponse(base.op));
  // the strongest push (colour from 1.5 down to 0.5, midtone saturation with it) that keeps skin within the limit
  let pick = { colour: 0.5, mid: 0, ratio: Infinity };
  for (let k = 1.5; k >= 0.5 - 1e-9; k -= 0.05) {
    const mid = Math.max(0, 0.12 * (k - 1) / 0.5);
    const ratio = skinRatio(filmResponse(base.op, k, mid));
    pick = { colour: +k.toFixed(2), mid: +mid.toFixed(3), ratio };
    if (ratio <= LIMIT) break;
  }
  const safe = save(name, 'skinsafe', 'Film response, less colour push (skin within x1.2)', filmResponse(base.op, pick.colour, pick.mid), pick.colour, { skinSafe: { ...pick, shipped, v3 } });
  console.log(`${name}: skin saturation shipped x${shipped.toFixed(2)}, v3 film response x${v3.toFixed(2)} -> colour push ${pick.colour}, midtone sat ${pick.mid}: x${pick.ratio.toFixed(2)} (fit ${safe.meanDE2000!.toFixed(2)})`);
  if (pick.colour < 1) {
    const middle = filmResponse(base.op, 1, 0);
    const fit = save(name, 'filmcolour', "Film response tone, the film's own colour", middle, 1, { skinRatio: skinRatio(middle) });
    console.log(`  middle (film's own colour): skin x${skinRatio(middle).toFixed(2)} (fit ${fit.meanDE2000!.toFixed(2)})`);
  }
  if (process.env.SKIN_ONLY) {
    const only = skinOnly(base.op, 1.15);
    const fit = save(name, 'skinonly', 'Film response, skin colours capped', only, 1.5, { skinOnly: { cap: 1.15, target: skinRatio(only) } });
    console.log(`  skin-only cap: target x${skinRatio(only).toFixed(2)} (fit ${fit.meanDE2000!.toFixed(2)})`);
  }
}
writeFileSync(modelsPath, JSON.stringify(models, null, 1));
