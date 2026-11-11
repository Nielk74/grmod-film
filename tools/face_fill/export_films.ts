// SPDX-License-Identifier: GPL-2.0-only
// Authored full-strength target, not an ISP render or inverse of camera JPEG.
import { mkdirSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { LOOKS } from '../../core/src/filmpack/looks';
import { filmResponse } from '../../examples/gr3x/film-pack-v3/response';

const dir = process.argv.slice(2).filter(x => x !== '--')[0];
if (!dir) throw new Error('Pass output model directory');
for (const source of ['C:/Users/Antoine/Pictures/Ricoh', 'C:/Users/Antoine/Pictures/Ricoh2']) {
  const target = resolve(dir).toLowerCase(), root = resolve(source).toLowerCase();
  if (target === root || target.startsWith(root + '\\')) throw new Error('Output must stay outside original folders');
}
mkdirSync(dir, { recursive: true });
const n = 33;
const names = ['Gold 200', 'Nostalgic Neg', 'Astia', 'Kodachrome 64'];
const records = [];
for (const name of names) {
  const base = LOOKS.find(x => x.name === name)!;
  // Default x1.5 colour, +.12 mid saturation before 95ba6de. No later
  // highlight shoulder, MTF, grain, native matrix/curve approximation.
  const op = filmResponse(base.op, 1.5, .12, 0);
  const grid = new Float32Array(n ** 3 * 3);
  let at = 0;
  for (let r = 0; r < n; r++) for (let g = 0; g < n; g++) for (let b = 0; b < n; b++) {
    grid.set(op([r/(n-1), g/(n-1), b/(n-1)]), at); at += 3;
  }
  const file = name.toLowerCase().replaceAll(' ', '-') + '.f32';
  writeFileSync(join(dir,file), new Uint8Array(grid.buffer));
  records.push({name,file,grid:n,colourPush:1.5,midSaturation:.12,shoulder:0,
    basis:'Authored full-strength display-sRGB target, pre-95ba6de parameters; actual JPEG input may already be stylized'});
}
writeFileSync(join(dir,'films.json'), JSON.stringify(records,null,2), 'utf8');
