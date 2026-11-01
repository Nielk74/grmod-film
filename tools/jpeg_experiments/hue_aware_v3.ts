// Hue-aware colour push: the applied (skin-safe) push for warm colours, a stronger one for greens, cyans and
// blues, fitted through GR Mod's Engine and added to the comparison page as variant "hueaware" (cool push
// from HUE_COOL, default 1.5). Does the camera's matrix + curves + post matrix hold a broad warm/cool split,
// where it could not hold a narrow cap on skin colours alone (skin_safe_v3.ts)?
//   HUE_COOL=1.5 vite-node hue_aware_v3.ts -- OFFICIAL.bin COMPARE_DIR
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { Engine } from '../../core/src/app/engine';
import type { PresetResult } from '../../core/src/app/engine';
import { LOOKS, cubeText } from '../../core/src/filmpack/looks';
import type { RGB } from '../../core/src/filmpack/looks';
import { GR3X_CAMERA } from '../../core/src/color/gr3x-camera';
import { filmResponse, warmCool } from '../../examples/gr3x/film-pack-v3/response';

// as applied in film pack v3 (build.ts COLOUR_PUSH): [colour push, midtone saturation]
const WARM: Record<string, [number, number]> = { 'Gold 200': [1, 0], 'Nostalgic Neg': [1, 0], Astia: [1.2, 0.048], 'Kodachrome 64': [1.1, 0.024] };
const COOL = Number(process.env.HUE_COOL ?? 1.5);
const COOL_MID = Number(process.env.HUE_COOL_MID ?? 0.12);
const REFINE = !!process.env.FIT_REFINE;

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

const [firmware, dir] = process.argv.slice(2).filter(a => a !== '--');
const engine = await Engine.open(new Uint8Array(readFileSync(firmware)));
const modelsPath = join(dir, 'models', 'models.json');
const models = JSON.parse(readFileSync(modelsPath, 'utf8'));
const N = models.grid, grid = new Float64Array(N ** 3 * 3);
let at = 0;
for (let r = 0; r < N; r++) for (let g = 0; g < N; g++) for (let b = 0; b < N; b++) { grid[at++] = r / (N - 1); grid[at++] = g / (N - 1); grid[at++] = b / (N - 1); }

for (const [name, [warm, warmMid]] of Object.entries(WARM)) {
  const base = LOOKS.find(l => l.name === name)!;
  const op = filmResponse(base.op, warmCool(warm, COOL), warmCool(warmMid, COOL_MID));
  const fit = engine.convertPreset('cube', cubeText({ ...base, op }, 33), undefined, { post: true, refine: REFINE });
  const native = nativeGrid(fit, engine.info.standardMatrixQ13, grid);
  const target = new Float32Array(grid.length);
  for (let p = 0; p < grid.length; p += 3) target.set(op([grid[p], grid[p + 1], grid[p + 2]] as RGB), p);
  const index = LOOKS.indexOf(base) + 1, file = `${String(index).padStart(2, '0')}-hueaware`;
  writeFileSync(join(dir, 'models', file + '-native.f32'), new Uint8Array(native.buffer));
  writeFileSync(join(dir, 'models', file + '-target.f32'), new Uint8Array(target.buffer));
  models.models = models.models.filter((m: { film: string; variant: string }) => !(m.film === name && m.variant === 'hueaware'));
  models.models.push({ film: name, index, variant: 'hueaware', label: 'Film response, warm colours gentle, cool colours full', kL: 0, kC: COOL, file,
    postMatrix: !!fit.postQ9, fitMeanDE2000: fit.meanDE2000, fitP95DE2000: fit.p95DE2000, hueAware: { warm, warmMid, cool: COOL, coolMid: COOL_MID, refine: REFINE } });
  console.log(`${name}: warm ${warm}, cool ${COOL} -> fit ${fit.meanDE2000!.toFixed(2)} (p95 ${fit.p95DE2000!.toFixed(2)})${fit.postQ9 ? '' : ' no post matrix'}`);
}
writeFileSync(modelsPath, JSON.stringify(models, null, 1));
