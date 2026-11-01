// Can the camera's matrix + curves + post matrix hold a film's cream highlights and tinted blacks? The film
// response of Portra 400 has white (255, 246, 234) and warm light greys, but the production fit lands near
// white. This fits a film's cube with extra weight on near-white (and near-black) greys, as many copies of a
// 41-step grey ramp, and compares the white and black tints and the overall error (validation set).
//   FILM="Portra 400" ENDS=white|both vite-node white_fit_v3.ts
import { applyCube, parseCube } from '../../core/src/color/cube';
import { extraFitSamples, syntheticSamples } from '../../core/src/color/convert';
import { fitSlot } from '../../core/src/color/fit';
import { deltaE2000Lab, lab, mean, percentile } from '../../core/src/color/math';
import { GR3X_CAMERA } from '../../core/src/color/gr3x-camera';
import { LOOKS, cubeText } from '../../core/src/filmpack/looks';
import { filmResponse } from '../../examples/gr3x/film-pack-v3/response';

// as applied in film pack v3 (build.ts COLOUR_PUSH)
const PUSH: Record<string, [number, number]> = { 'Gold 200': [1, 0], 'Nostalgic Neg': [1, 0], Astia: [1.2, 0.048], 'Kodachrome 64': [1.1, 0.024] };
const name = process.env.FILM ?? 'Portra 400';
const both = process.env.ENDS === 'both';
const base = LOOKS.find(l => l.name === name)!, push = PUSH[name];
const cube = parseCube(cubeText({ ...base, op: filmResponse(base.op, push?.[0], push?.[1], Number(process.env.SHOULDER ?? 0)) }));

/** `copies` of a 41-step grey ramp from `from` to `to`. */
const greys = (from: number, to: number, copies: number) => {
  const out: number[] = [];
  for (let c = 0; c < copies; c++) for (let i = 0; i <= 40; i++) { const v = from + (to - from) * i / 40; out.push(v, v, v); }
  return Float64Array.from(out);
};
const validation = syntheticSamples(1100, 161, 1);
const probes: [string, number][] = [['black', 0], ['near black', 0.04], ['dark', 0.12], ['light', 0.85], ['near white', 0.97], ['white', 1]];
const tint = (v: Float64Array) => { const l = lab(v); return `L ${l[0].toFixed(0)} a,b (${l[1].toFixed(1)},${l[2].toFixed(1)})`; };

function run(copies: number) {
  const a = syntheticSamples(2200, 160, 4), b = extraFitSamples();
  const g = copies ? [greys(0.75, 1, copies), ...(both ? [greys(0, 0.2, copies)] : [])] : [];
  const P = new Float64Array(a.length + b.length + g.reduce((s, x) => s + x.length, 0));
  P.set(a, 0); P.set(b, a.length);
  let o = a.length + b.length; for (const x of g) { P.set(x, o); o += x.length; }
  const fit = fitSlot(P, applyCube(cube, P), { camera: GR3X_CAMERA, maxIterations: 250, post: true });
  const params = fit.P2 ? { M1: fit.M1, ck: fit.ck, P2: fit.P2 } : { M1: fit.M1, ck: fit.ck };
  const de = deltaE2000Lab(lab(GR3X_CAMERA.slotApply(params, validation)), lab(applyCube(cube, validation)));
  const probe = Float64Array.from(probes.flatMap(([, v]) => [v, v, v]));
  const got = GR3X_CAMERA.slotApply(params, probe), want = applyCube(cube, probe);
  console.log(`${name}, extra grey weight x${copies}${both ? ' (both ends)' : ''}: validation mean ${mean(de).toFixed(2)}  p95 ${percentile(de, 95).toFixed(2)}`);
  probes.forEach(([label], i) => console.log(`   ${label.padEnd(10)} want ${tint(want.subarray(i * 3, i * 3 + 3))}   got ${tint(got.subarray(i * 3, i * 3 + 3))}`));
}
for (const copies of [0, 24, 48]) run(copies);
