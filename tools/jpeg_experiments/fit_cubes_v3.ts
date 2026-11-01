// Fit .cube targets (Standard display -> film display) through GR Mod's Engine and add them to the
// comparison page's models as a variant of the matching film:
//   vite-node fit_cubes_v3.ts -- OFFICIAL.bin CUBE_DIR MODELS_DIR VARIANT_ID "LABEL" FILM=file.cube ...
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { Engine } from '../../core/src/app/engine';
import { GR3X_CAMERA } from '../../core/src/color/gr3x-camera';
import { parseCube, applyCube } from '../../core/src/color/cube';
import type { PresetResult } from '../../core/src/app/engine';

function inverse(a: number[]): number[] {
  const [a0, b, c, d, e, f, g, h, i] = a;
  const det = a0 * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g);
  return [(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det, (f * g - d * i) / det, (a0 * i - c * g) / det, (c * d - a0 * f) / det, (d * h - e * g) / det, (b * g - a0 * h) / det, (a0 * e - b * d) / det];
}
function product(a: number[], b: number[]): number[] {
  return Array.from({ length: 9 }, (_, j) => [0, 1, 2].reduce((s, k) => s + a[Math.floor(j / 3) * 3 + k] * b[k * 3 + j % 3], 0));
}
/** Same evaluation of stored coefficients as film_strength_v3.ts. */
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

const [firmware, cubeDir, modelsDir, variant, label, ...pairs] = process.argv.slice(2).filter(a => a !== '--');
const engine = await Engine.open(new Uint8Array(readFileSync(firmware)));
const modelsPath = join(modelsDir, 'models.json');
const models = JSON.parse(readFileSync(modelsPath, 'utf8'));
const N = models.grid, grid = new Float64Array(N ** 3 * 3);
let at = 0;
for (let r = 0; r < N; r++) for (let g = 0; g < N; g++) for (let b = 0; b < N; b++) { grid[at++] = r / (N - 1); grid[at++] = g / (N - 1); grid[at++] = b / (N - 1); }
for (const pair of pairs) {
  const [film, file] = pair.split('=');
  const text = readFileSync(join(cubeDir, file), 'utf8');
  let fit: PresetResult, post = true;
  const refine = process.env.FIT_REFINE === '1';
  try { fit = engine.convertPreset('cube', text, undefined, { post: true, refine }); }
  catch (e) { fit = engine.convertPreset('cube', text, undefined, { post: false }); post = false; console.log(`${film}: ${(e as Error).message}; without post matrix`); }
  const native = nativeGrid(fit, engine.info.standardMatrixQ13, grid);
  const cube = parseCube(text), target = new Float32Array(grid.length);
  for (let p = 0; p < grid.length; p += 3) target.set(applyCube(cube, new Float64Array([grid[p], grid[p + 1], grid[p + 2]])), p);
  const base = models.models.find((m: { film: string }) => m.film === film);
  const index = base ? base.index : 100 + models.models.filter((m: { index: number }) => m.index >= 100).length;
  const id = `${String(index).padStart(2, '0')}-${variant}`;
  writeFileSync(join(modelsDir, id + '-native.f32'), new Uint8Array(native.buffer));
  writeFileSync(join(modelsDir, id + '-target.f32'), new Uint8Array(target.buffer));
  models.models = models.models.filter((m: { film: string; variant: string }) => !(m.film === film && m.variant === variant));
  models.models.push({ film, index, variant, label, kL: 0, kC: 0, file: id, postMatrix: post, fitMeanDE2000: fit.meanDE2000, fitP95DE2000: fit.p95DE2000 });
  console.log(`${film} ${variant}: fit ${fit.meanDE2000.toFixed(2)} / p95 ${fit.p95DE2000.toFixed(2)}`);
}
writeFileSync(modelsPath, JSON.stringify(models, null, 1));
