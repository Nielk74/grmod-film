// Does the fitter's guarded CIEDE2000 refinement (convertPreset option `refine`, off in the pack builds)
// hold the v3 looks better? Fits every pack film as applied, with and without it.
//   vite-node refine_test_v3.ts -- OFFICIAL.bin
import { readFileSync } from 'node:fs';
import { Engine } from '../../core/src/app/engine';
import { LOOKS, cubeText } from '../../core/src/filmpack/looks';
import { filmResponse } from '../../examples/gr3x/film-pack-v3/response';

const COLOUR_PUSH: Record<string, [number, number]> = { 'Gold 200': [1, 0], 'Nostalgic Neg': [1, 0], Astia: [1.2, 0.048], 'Kodachrome 64': [1.1, 0.024] };
const firmware = process.argv.slice(2).filter(a => a !== '--')[0];
const engine = await Engine.open(new Uint8Array(readFileSync(firmware)));
let sumPlain = 0, sumRefined = 0, n = 0;
for (const [i, base] of LOOKS.entries()) {
  if (i === 0 || base.name === 'Aerochrome' || base.name === 'Blockbuster') continue;
  const push = COLOUR_PUSH[base.name];
  const text = cubeText({ ...base, op: filmResponse(base.op, push?.[0], push?.[1]) });
  const t0 = Date.now();
  const plain = engine.convertPreset('cube', text), t1 = Date.now();
  const refined = engine.convertPreset('cube', text, undefined, { refine: true }), t2 = Date.now();
  sumPlain += plain.meanDE2000!; sumRefined += refined.meanDE2000!; n++;
  console.log(`${base.name.padEnd(15)} mean ${plain.meanDE2000!.toFixed(2)} -> ${refined.meanDE2000!.toFixed(2)}  p95 ${plain.p95DE2000!.toFixed(2)} -> ${refined.p95DE2000!.toFixed(2)}  (${((t1 - t0) / 1000).toFixed(1)} s, ${((t2 - t1) / 1000).toFixed(1)} s)${refined.postQ9 ? '' : '  no post matrix'}`);
}
console.log(`average mean ${(sumPlain / n).toFixed(2)} -> ${(sumRefined / n).toFixed(2)}`);
