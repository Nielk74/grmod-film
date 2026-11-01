// SPDX-License-Identifier: GPL-2.0-only
/**
 * Offline comparison of an sRGB CUBE with the existing GR3X matrix/curve fit.
 *
 * npx vite-node tools/jpeg_experiments/fit_compare.ts INPUT.cube OUTPUT.json
 * The output grids use NumPy C order: reshape(33, 33, 33, 3), [r,g,b,channel].
 * This deliberately normalized software reference does not calibrate firmware.
 */
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { quantizeSlot } from '../../core/src/color/camera';
import type { QuantizedSlot } from '../../core/src/color/camera';
import { applyCube, parseCube } from '../../core/src/color/cube';
import { GR3X_CAMERA } from '../../core/src/color/gr3x-camera';
import { convertGr3xCube } from '../../core/src/color/gr3x-import';
import { clamp01, deltaE2000Lab, deltaELab, lab, mean, percentile } from '../../core/src/color/math';

const GRID_SIZE = 33;
const IDENTITY_STANDARD_Q13 = [8192, 0, 0, 0, 8192, 0, 0, 0, 8192];
const IDENTITY_POST_Q9 = [512, 0, 0, 0, 512, 0, 0, 0, 512];

/** Relative coefficients: identity Standard is a declared normalization only. */
function applyQuantizedReference(q: QuantizedSlot, rgb: Float64Array): Float64Array {
  const matrix = Array.from(q.matrixQ13, v => v / 8192);
  const post = Array.from(q.postQ9 ?? IDENTITY_POST_Q9, v => v / 512);
  const out = new Float64Array(rgb.length);
  const linear = [0, 0, 0];
  const curved = [0, 0, 0];
  for (let offset = 0; offset < rgb.length; offset += 3) {
    for (let c = 0; c < 3; c++) linear[c] = GR3X_CAMERA.Sinv(rgb[offset + c]);
    for (let c = 0; c < 3; c++) {
      let value = 0;
      for (let k = 0; k < 3; k++) value += matrix[c * 3 + k] * linear[k];
      const display = GR3X_CAMERA.S(clamp01(value));
      // x_i=i*64/16383, y_i=q.curves[c][i]/16383. Constant endpoint
      // extension matches np.interp; there is no invented 257th entry.
      const position = Math.min(255, Math.max(0, display * 16383 / 64));
      const lower = Math.min(254, Math.floor(position));
      const fraction = position - lower;
      curved[c] = (q.curves[c][lower] + fraction * (q.curves[c][lower + 1] - q.curves[c][lower])) / 16383;
    }
    for (let c = 0; c < 3; c++) {
      let value = 0;
      for (let k = 0; k < 3; k++) value += post[c * 3 + k] * curved[k];
      out[offset + c] = clamp01(value);
    }
  }
  return out;
}

function comparison(got: Float64Array, target: Float64Array) {
  const gotLab = lab(got), targetLab = lab(target);
  const de76 = deltaELab(gotLab, targetLab), de00 = deltaE2000Lab(gotLab, targetLab);
  let sumSquares = 0, maximum = 0;
  for (let i = 0; i < got.length; i++) {
    const error = Math.abs(got[i] - target[i]);
    maximum = Math.max(maximum, error);
    sumSquares += error * error;
  }
  return {
    sample_count: got.length / 3,
    rgb_rmse: Math.sqrt(sumSquares / got.length),
    rgb_max_absolute: maximum,
    meanDE: mean(de76), p95DE: percentile(de76, 95),
    meanDE2000: mean(de00), p95DE2000: percentile(de00, 95),
  };
}

async function main(args: string[]): Promise<void> {
  // vite-node accepts the separator after the script; --script can preserve it
  // in process.argv. Both documented invocation forms therefore work.
  args = args.filter(value => value !== '--');
  if (args.length !== 2) {
    console.error('Usage: npx vite-node tools/jpeg_experiments/fit_compare.ts INPUT.cube OUTPUT.json');
    process.exitCode = 1;
    return;
  }
  const [inputPath, outputPath] = args.map(value => resolve(value));
  if (inputPath.toLowerCase() === outputPath.toLowerCase()) throw new Error('Input and output paths must differ.');
  const text = await readFile(inputPath, { encoding: 'utf8' });
  const cube = parseCube(text);
  console.error('Fitting the GR3X software model with post:true, refine:false.');
  const fit = convertGr3xCube(text, { post: true, refine: false });
  const q = quantizeSlot(fit.params, IDENTITY_STANDARD_Q13);
  const inputGrid = new Float64Array(GRID_SIZE ** 3 * 3);
  for (let r = 0; r < GRID_SIZE; r++) for (let g = 0; g < GRID_SIZE; g++) for (let b = 0; b < GRID_SIZE; b++) {
    const offset = ((r * GRID_SIZE + g) * GRID_SIZE + b) * 3;
    inputGrid[offset] = r / (GRID_SIZE - 1);
    inputGrid[offset + 1] = g / (GRID_SIZE - 1);
    inputGrid[offset + 2] = b / (GRID_SIZE - 1);
  }
  const floating = GR3X_CAMERA.slotApply(fit.params, inputGrid);
  const quantized = applyQuantizedReference(q, inputGrid);
  const target = applyCube(cube, inputGrid);
  for (const [name, values] of [['floating', floating], ['quantized', quantized]] as const) {
    if (values.some(value => !Number.isFinite(value) || value < 0 || value > 1)) {
      throw new Error(`${name} grid must contain finite RGB values in [0,1].`);
    }
  }

  const report = {
    schema: 1,
    source: inputPath,
    title: fit.title,
    input_encoding: 'display-srgb',
    fit_options: { post: true, refine: false },
    grid_size: GRID_SIZE,
    grid_shape: [GRID_SIZE, GRID_SIZE, GRID_SIZE, 3],
    grid_order: '[r,g,b,channel], NumPy C order; b varies fastest among colour indices',
    floating_grid: Array.from(floating),
    quantized_grid: Array.from(quantized),
    S_TAB: Array.from(GR3X_CAMERA.S_TAB),
    S_TAB_input: 'linear input x=i/256; normalized output y=native_value/16383',
    params: {
      M1: fit.params.M1.flat(),
      ck: fit.params.ck.flatMap(curve => Array.from(curve)),
      ...(fit.params.P2 ? { P2: fit.params.P2.flat() } : {}),
      shapes: { M1: [3, 3], ck: [3, 17], ...(fit.params.P2 ? { P2: [3, 3] } : {}) },
    },
    quantized: {
      standard_matrixQ13: IDENTITY_STANDARD_Q13,
      standard_matrix_basis: 'identity Standard: normalized relative software assumption, not firmware calibration',
      matrixQ13: Array.from(q.matrixQ13),
      curves: q.curves.flatMap(curve => Array.from(curve)),
      postQ9: Array.from(q.postQ9 ?? IDENTITY_POST_Q9),
      post_is_identity_fallback: q.postQ9 === undefined,
      shapes: { matrixQ13: [3, 3], curves: [3, 256], postQ9: [3, 3] },
      curve_input: 'x=i*64/16383 for i=0..255; constant extension outside the sampled range',
      evaluation: 'Sinv -> clip((matrixQ13/8192)*RGB) -> S -> interpolate(curves/16383) -> clip((postQ9/512)*RGB)',
    },
    metrics: {
      meanDE: fit.meanDE, p95DE: fit.p95DE,
      meanDE2000: fit.meanDE2000, p95DE2000: fit.p95DE2000,
      existing_fit_validation: 'Existing convertGr3xCube independent synthetic validation; not measured camera accuracy',
      grid_floating_vs_target: comparison(floating, target),
      grid_quantized_vs_target: comparison(quantized, target),
      grid_quantized_vs_floating: comparison(quantized, floating),
    },
    caveats: [
      'Offline matrix/RGB-curve approximation of a display-sRGB LUT; no firmware, camera capture, or physical calibration was evaluated.',
      'Identity Standard Q13 is explicitly assumed to isolate relative coefficient/curve quantization. Actual firmware Standard coefficients were not read.',
      'The base tone table is the existing GR3X native-code software reference, not measured camera colour calibration.',
      'Quantized coefficients are evaluated with floating-point multiply/interpolation and declared clipping; this does not reproduce every integer rounding step of native ARM processing.',
      'quantizeSlot enforces non-decreasing 256-entry curves. Differences from the floating fit include that constraint and endpoint sampling, beyond coefficient rounding.',
      'The uniform 33^3 grid measures model/LUT agreement over display RGB; it does not estimate scene frequency or camera accuracy.',
      'Flattened numerical buffers reshape using the recorded shapes in NumPy C order. The grid uses b-fastest ordering, different from red-fastest CUBE file ordering.',
      ...fit.warnings,
    ],
  };
  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(report)}\n`, { encoding: 'utf8' });
  console.log(JSON.stringify({
    output: outputPath, grid_size: GRID_SIZE,
    meanDE2000: fit.meanDE2000, p95DE2000: fit.p95DE2000,
    grid_quantized_vs_floating: report.metrics.grid_quantized_vs_floating,
  }, null, 2));
}

await main(process.argv.slice(2)).catch((error: unknown) => {
  console.error(`fit_compare: ${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 1;
});
