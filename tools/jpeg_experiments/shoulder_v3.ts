// The focus films (Portra 400, CineStill 800T, Gold 200 as applied in film pack v3), fitted with extra weight on
// the grey ends (END_GREY copies, see convertPreset's endGreyWeight) and optionally a highlight shoulder: white
// drops by SHOULDER (OkLab L) over the top third of the range. Added to the comparison page as VARIANT.
//   END_GREY=24 SHOULDER=0.03 VARIANT=shoulder vite-node shoulder_v3.ts -- OFFICIAL.bin COMPARE_DIR
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { Engine } from '../../core/src/app/engine';
import type { PresetResult } from '../../core/src/app/engine';
import { LOOKS, cubeText } from '../../core/src/filmpack/looks';
import type { RGB } from '../../core/src/filmpack/looks';
import { GR3X_CAMERA } from '../../core/src/color/gr3x-camera';
import { filmResponse } from '../../examples/gr3x/film-pack-v3/response';

const SHOULDER = Number(process.env.SHOULDER ?? 0.03), END_GREY = Number(process.env.END_GREY ?? 0), VARIANT = process.env.VARIANT ?? 'shoulder';
// as applied in film pack v3 (build.ts COLOUR_PUSH; the others use film response's 1.5 and 0.12)
const PUSH: Record<string, [number, number]> = { 'Gold 200': [1, 0] };

function inverse(a: number[]): number[] {
  const [a0, b, c, d, e, f, g, h, i] = a;
  const det = a0 * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g);
  return [(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det, (f * g - d * i) / det, (a0 * i - c * g) / det, (c * d - a0 * f) / det, (d * h - e * g) / det, (b * g - a0 * h) / det, (a0 * e - b * d) / det];
}
function product(a: number[], b: number[]): number[] {
  return Array.from({ length: 9 }, (_, j) => [0, 1, 2].reduce((s, k) => s + a[Math.floor(j / 3) * 3 + k] * b[k * 3 + j % 3], 0));
}
/** The stored coefficients evaluated as the camera chains them (as skin_safe_v3.ts). */
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

const toLin = (v: number) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
function chroma(c: RGB): number {
  const r = toLin(c[0]), g = toLin(c[1]), b = toLin(c[2]);
  const X = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047, Y = 0.2126 * r + 0.7152 * g + 0.0722 * b, Z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883;
  const f = (t: number) => (t > 216 / 24389 ? Math.cbrt(t) : (841 / 108) * t + 4 / 29);
  return Math.hypot(500 * (f(X) - f(Y)), 200 * (f(Y) - f(Z)));
}
const median = (a: number[]) => { const s = [...a].sort((p, q) => p - q); return s[Math.floor(s.length / 2)]; };

const [firmware, dir] = process.argv.slice(2).filter(a => a !== '--');
const engine = await Engine.open(new Uint8Array(readFileSync(firmware)));
const skin = JSON.parse(readFileSync(join(dir, 'skin-samples.json'), 'utf8')) as RGB[];
const modelsPath = join(dir, 'models', 'models.json');
const models = JSON.parse(readFileSync(modelsPath, 'utf8'));
const N = models.grid, grid = new Float64Array(N ** 3 * 3);
let at = 0;
for (let r = 0; r < N; r++) for (let g = 0; g < N; g++) for (let b = 0; b < N; b++) { grid[at++] = r / (N - 1); grid[at++] = g / (N - 1); grid[at++] = b / (N - 1); }
const skinRatio = (op: (c: RGB) => RGB) => median(skin.map(c => chroma(op(c)) / Math.max(chroma(c), 1e-6)));
const skinFlat = Float64Array.from(skin.flat());

const median2 = median;
for (const name of ['Portra 400', 'CineStill 800T', 'Gold 200']) {
  const base = LOOKS.find(l => l.name === name)!, push = PUSH[name];
  const op = filmResponse(base.op, push?.[0], push?.[1], SHOULDER);
  const fit = engine.convertPreset('cube', cubeText({ ...base, op }, 33), undefined, { post: true, endGreyWeight: END_GREY });
  const native = nativeGrid(fit, engine.info.standardMatrixQ13, grid);
  const target = new Float32Array(grid.length);
  for (let p = 0; p < grid.length; p += 3) target.set(op([grid[p], grid[p + 1], grid[p + 2]] as RGB), p);
  const nativeSkin = nativeGrid(fit, engine.info.standardMatrixQ13, skinFlat);
  const keptSkin = median2(skin.map((c, i) => chroma([nativeSkin[i * 3], nativeSkin[i * 3 + 1], nativeSkin[i * 3 + 2]]) / Math.max(chroma(c), 1e-6)));
  const index = LOOKS.indexOf(base) + 1, file = `${String(index).padStart(2, '0')}-${VARIANT}`;
  writeFileSync(join(dir, 'models', file + '-native.f32'), new Uint8Array(native.buffer));
  writeFileSync(join(dir, 'models', file + '-target.f32'), new Uint8Array(target.buffer));
  models.models = models.models.filter((m: { film: string; variant: string }) => !(m.film === name && m.variant === VARIANT));
  models.models.push({ film: name, index, variant: VARIANT, label: `Grey ends weighted x${END_GREY}, shoulder ${SHOULDER}`, kL: 0, kC: push?.[0] ?? 1.5, file,
    postMatrix: !!fit.postQ9, fitMeanDE2000: fit.meanDE2000, fitP95DE2000: fit.p95DE2000, shoulder: SHOULDER, endGreyWeight: END_GREY });
  console.log(`${name} (${VARIANT}): end grey ${END_GREY}, shoulder ${SHOULDER}; skin x${keptSkin.toFixed(2)} in the camera; fit ${fit.meanDE2000!.toFixed(2)} (p95 ${fit.p95DE2000!.toFixed(2)}); white -> ${(Math.max(...Array.from(native.subarray(native.length - 3))) * 255).toFixed(0)}`);
}
writeFileSync(modelsPath, JSON.stringify(models, null, 1));
