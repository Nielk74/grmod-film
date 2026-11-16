// Camera coefficients of every film of the v3 pack, fitted exactly as the pack's build does it.
// usage: npx vite-node tools/colour_engine/dump_all.ts -- OFFICIAL.bin CUBE_DIR OUT.json
import { readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { Engine } from '../../core/src';
import { GR3X_CAMERA } from '../../core/src/color/gr3x-camera';

const [fw, cubeDir, out] = process.argv.slice(2).filter(a => a !== '--');
const engine = await Engine.open(new Uint8Array(readFileSync(fw)));
const N = 4096;
const res: Record<string, unknown> = {
  S: Array.from({ length: N + 1 }, (_, i) => GR3X_CAMERA.S(i / N)),
  Sinv: Array.from({ length: 256 }, (_, i) => GR3X_CAMERA.Sinv(i / 255)),
  standardQ13: Array.from(engine.info.standardMatrixQ13),
};
for (const file of readdirSync(cubeDir).filter(f => f.endsWith('.cube')).sort()) {
  const text = readFileSync(join(cubeDir, file), 'utf8');
  const name = file.replace(/^\d+-/, '').replace(/\.cube$/, '').replaceAll('-', ' ');
  const r = engine.convertPreset('cube', text, undefined, { endGreyWeight: 24 });
  res[name] = { matrixQ13: Array.from(r.matrixQ13), curves: r.curves.map(c => Array.from(c)), postQ9: r.postQ9 ? Array.from(r.postQ9) : null, meanDE: r.meanDE2000, cube: file };
  console.log(name, r.meanDE2000?.toFixed(2), !!r.postQ9);
}
writeFileSync(out, JSON.stringify(res), { encoding: 'utf8' });
