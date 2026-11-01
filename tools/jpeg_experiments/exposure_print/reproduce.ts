// SPDX-License-Identifier: GPL-2.0-only
// Restore the approved camera-model previews; optionally refit the archived targets.
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { GR3X_CAMERA } from '../../../core/src/color/gr3x-camera';
import { convertGr3xCube } from '../../../core/src/color/gr3x-import';
import { applyCube, parseCube } from '../../../core/src/color/cube';
import { deltaE2000Lab, lab, mean, percentile } from '../../../core/src/color/math';
import type { SlotParams } from '../../../core/src/color/camera';

const here = dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2).filter(a => a !== '--');
const refit = args.includes('--refit');
const positional = args.filter(a => a !== '--refit');
if (positional.length !== 1 || positional[0].startsWith('-'))
  throw new Error('Usage: vite-node --script reproduce.ts <new-output-directory> [--refit]');
const out = resolve(positional[0]);
if (existsSync(out)) throw new Error('Output directory must not exist; approved assets are never overwritten');
const approved = JSON.parse(readFileSync(join(here, 'approved.json'), 'utf8'));
const sha = (bytes: Uint8Array | string) => createHash('sha256').update(bytes).digest('hex');
const grid = new Float64Array(33 ** 3 * 3);
let at = 0;
for (let r = 0; r < 33; r++) for (let g = 0; g < 33; g++) for (let b = 0; b < 33; b++) {
  grid[at++] = r / 32; grid[at++] = g / 32; grid[at++] = b / 32;
}
const outputs: { file: string; bytes: Buffer }[] = [];
const checks = [];
for (const name of ['baseline', 'candidate']) {
  const targetMeta = approved.targets[name];
  const text = readFileSync(join(here, targetMeta.file), 'utf8');
  if (sha(text) !== targetMeta.sha256) throw new Error(`${name}: target hash changed`);
  const saved = approved.fits.find((f: { id: string }) => f.id === name);
  const params: SlotParams = refit
    ? convertGr3xCube(text, approved.fit_options).params
    : { ...saved.params, ck: saved.params.ck.map((c: number[]) => Float64Array.from(c)) };
  const rendered = GR3X_CAMERA.slotApply(params, grid);
  const target = applyCube(parseCube(text), grid);
  const bytes = Buffer.alloc(rendered.length * 4);
  rendered.forEach((v, i) => {
    if (!Number.isFinite(v) || v < 0 || v > 1) throw new Error(`${name}: invalid grid value`);
    bytes.writeFloatLE(v, i * 4);
  });
  if (sha(bytes) !== approved.preview_hashes[`${name}.f32`])
    throw new Error(`${name}: rendering differs from the accepted preview`);
  const de = deltaE2000Lab(lab(rendered), lab(target));
  const measured = { meanDE2000: mean(de), p95DE2000: percentile(de, 95), maxDE2000: Math.max(...de) };
  for (const [key, value] of Object.entries(measured))
    if (Math.abs(value - saved.full_grid[key]) > 1e-7) throw new Error(`${name}: ${key} changed`);
  outputs.push({ file: `${name}.f32`, bytes });
  if (name === 'candidate') {
    const targetBytes = Buffer.alloc(target.length * 4);
    target.forEach((v, i) => targetBytes.writeFloatLE(v, i * 4));
    if (sha(targetBytes) !== approved.preview_hashes['target.f32']) throw new Error('Target grid changed');
    outputs.push({ file: 'target.f32', bytes: targetBytes });
  }
  checks.push({ id: name, sha256: sha(bytes), own_target_full_cube: measured,
    fitted_middle_gray_Lab: Array.from(lab(GR3X_CAMERA.slotApply(params, Float64Array.from(approved.middle_gray_display)))) });
}
mkdirSync(out, { recursive: true });
for (const output of outputs) writeFileSync(join(out, output.file), output.bytes);
writeFileSync(join(out, 'verification.json'), JSON.stringify({ refit, checks }, null, 2) + '\n', 'utf8');
console.log(JSON.stringify({ out, refit, checks }, null, 2));
