// Export the repository's authored Portra 400 target; no firmware or camera claim.
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { LOOKS } from '../../core/src/filmpack/looks';

const dest = process.argv.slice(2).filter(a => a !== '--')[0];
if (!dest) throw new Error('Usage: vite-node tools/horizon_grads/film_grid.ts OUTPUT.f32');
const look = LOOKS.find(l => l.name === 'Portra 400');
if (!look) throw new Error('Repository Portra target absent');
const size = 33, grid = new Float32Array(size ** 3 * 3);
let at = 0;
for (let r = 0; r < size; r++) for (let g = 0; g < size; g++) for (let b = 0; b < size; b++) {
  grid.set(look.op([r / (size - 1), g / (size - 1), b / (size - 1)]), at);
  at += 3;
}
writeFileSync(dest, new Uint8Array(grid.buffer));
writeFileSync(dest + '.json', JSON.stringify({ film: look.name, size, order: '[r,g,b,channel], b fastest, little-endian float32',
  source: 'core/src/filmpack/looks.ts', source_sha256: createHash('sha256').update(readFileSync('core/src/filmpack/looks.ts')).digest('hex'),
  limitation: 'Authored target applied to an already rendered JPEG; not measured Portra, not the native fitted firmware implementation, not a claim that the input was camera Standard.' }, null, 2), 'utf8');
console.log(`Exported ${look.name}: ${size} cubed grid to ${dest}`);
