// SPDX-License-Identifier: GPL-2.0-only
/**
 * Fit the looks and draw a contact sheet of what the camera will make of some photos: one row per
 * look (the fitted film, as GR III applies it), the photos in the columns; with `ideal`, every
 * cell is split, the left half the look itself and the right half the fitted film.
 *
 *   npx vite-node examples/gr3x/film-pack/preview.ts OFFICIAL.bin PHOTO-DIR OUT-PREFIX [ideal] [sky=K] [look,look,...]
 *
 * `sky=K`: the films with the recipe's teal sky step K (-4..+4, color/sky.ts).
 *
 * PHOTO-DIR holds 720x480 BGR files (photos.ps1). Writes OUT-PREFIX.bgr (convert with bgr2img.ps1)
 * and OUT-PREFIX.json with the fit errors.
 */
import { readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { Engine } from '../../../core/src';
import { GR3X_CAMERA } from '../../../core/src/color/gr3x-camera';
import { withTealSky } from '../../../core/src/color/sky';
import { LOOKS, cubeText } from './looks';

const [official, photoDir, outPrefix, ...rest] = process.argv.slice(2);
const ideal = rest.includes('ideal');
const sky = Number(rest.find(a => a.startsWith('sky='))?.slice(4) ?? 0);
const only = rest.find(a => a !== 'ideal' && !a.startsWith('sky='))?.split(',');
const engine = await Engine.open(new Uint8Array(readFileSync(official)));
const looks = only ? LOOKS.filter(l => only.includes(l.name)) : LOOKS;

const TW = 240, TH = 160;
const photos = readdirSync(photoDir).filter(f => f.endsWith('.bgr')).sort().map(f => {
  const bgr = readFileSync(join(photoDir, f));
  const out = new Float64Array(TW * TH * 3);
  for (let y = 0; y < TH; y++) for (let x = 0; x < TW; x++) for (let c = 0; c < 3; c++) {
    let s = 0;
    for (let dy = 0; dy < 3; dy++) for (let dx = 0; dx < 3; dx++) s += bgr[((y * 3 + dy) * 720 + x * 3 + dx) * 3 + (2 - c)];
    out[(y * TW + x) * 3 + c] = s / 9 / 255;
  }
  return out;
});

const rows: Float64Array[][] = [photos];
const report: object[] = [];
for (const look of looks) {
  const t0 = Date.now();
  const r = engine.convertPreset('cube', cubeText(look));
  report.push({ name: look.name, meanDE2000: r.meanDE2000, p95DE2000: r.p95DE2000, meanDE: r.meanDE, p95DE: r.p95DE, seconds: (Date.now() - t0) / 1000 });
  console.log(`${look.name.padEnd(16)} ΔE2000 mean ${r.meanDE2000!.toFixed(2)}  p95 ${r.p95DE2000!.toFixed(2)}   (${((Date.now() - t0) / 1000).toFixed(1)} s)`);
  rows.push(photos.map(p => {
    const fitted = GR3X_CAMERA.slotApply(withTealSky(r.params, sky), p);
    if (!ideal) return fitted;
    const both = fitted.slice();
    for (let i = 0; i < p.length / 3; i++) if (i % TW < TW / 2) both.set(look.op([p[i * 3], p[i * 3 + 1], p[i * 3 + 2]]), i * 3);
    return both;
  }));
}

const GAP = 4, W = photos.length * (TW + GAP), H = rows.length * (TH + GAP);
const stride = Math.ceil((W * 3) / 4) * 4;
const sheet = new Uint8Array(stride * H);
rows.forEach((row, ry) => row.forEach((img, cx) => {
  for (let y = 0; y < TH; y++) for (let x = 0; x < TW; x++) for (let c = 0; c < 3; c++)
    sheet[(ry * (TH + GAP) + y) * stride + (cx * (TW + GAP) + x) * 3 + (2 - c)] = Math.round(Math.min(1, Math.max(0, img[(y * TW + x) * 3 + c])) * 255);
}));
writeFileSync(outPrefix + '.bgr', sheet);
writeFileSync(outPrefix + '.json', JSON.stringify({ width: W, height: H, rows: ['Standard', ...looks.map(l => l.name)], report }, null, 2));
console.log(JSON.stringify({ width: W, height: H }));
