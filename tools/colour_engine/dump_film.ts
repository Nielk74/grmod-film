// Dump the fitted camera coefficients (what the camera does today) of the v3 films as JSON.
// usage: npx vite-node tools/colour_engine/dump_film.ts -- OFFICIAL.bin OUT.json
import { readFileSync, writeFileSync } from 'node:fs';
import { Engine } from '../../core/src';
import { GR3X_CAMERA } from '../../core/src/color/gr3x-camera';
import { LOOKS, cubeText } from '../../examples/gr3x/film-pack/looks';
import { filmResponse } from '../../examples/gr3x/film-pack-v3/response';

const [fw, out] = process.argv.slice(2).filter(a => a !== '--');
const engine = await Engine.open(new Uint8Array(readFileSync(fw)));
const COLOUR_PUSH: Record<string, [number, number]> = { 'Gold 200': [1, 0], 'Nostalgic Neg': [1, 0], Astia: [1.2, 0.048], 'Kodachrome 64': [1.1, 0.024] };
const SHOULDER: Record<string, number> = { 'Portra 400': 0.03, 'CineStill 800T': 0.03, 'Gold 200': 0.03 };
const res: Record<string, unknown> = {};
const N = 4096;
res.S = Array.from({ length: N + 1 }, (_, i) => GR3X_CAMERA.S(i / N));
res.Sinv = Array.from({ length: 256 }, (_, i) => GR3X_CAMERA.Sinv(i / 255));
res.standardQ13 = Array.from(engine.info.standardMatrixQ13);
for (const name of ['Portra 400', 'CineStill 800T', 'Gold 200', 'Kodachrome 64']) {
  const base = LOOKS.find(l => l.name === name)!;
  const push = COLOUR_PUSH[name];
  const look = { ...base, op: filmResponse(base.op, push?.[0], push?.[1], SHOULDER[name]) };
  const r = engine.convertPreset('cube', cubeText(look), undefined, { endGreyWeight: 24 });
  console.log(name, r.meanDE2000, !!r.postQ9);
  res[name] = { matrixQ13: Array.from(r.matrixQ13), curves: r.curves.map(c => Array.from(c)), postQ9: r.postQ9 ? Array.from(r.postQ9) : null, meanDE: r.meanDE2000 };
}
writeFileSync(out, JSON.stringify(res), { encoding: 'utf8' });
