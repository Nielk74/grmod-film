// SPDX-License-Identifier: GPL-2.0-only
/**
 * Build the film pack firmware for GR III 2.10 (or GR IIIx 1.60: the same program).
 *
 *   powershell -File examples/gr3x/film-pack/pictures.ps1 OUT/pictures
 *   npx vite-node examples/gr3x/film-pack/build.ts OFFICIAL.bin OUT
 *
 * OUT gets the firmware (fwdc239b.bin / fwdc243b.bin), the looks as .cube files (they also load in
 * GR Mod's own UI), the fit report, an icon sheet (icons.bgr, 400x80) and the encoded pictures.
 * The firmware: twenty films with their icons and recipes (where the camera's Sharpness, Clarity,
 * Halation start, and each film's grain; each film's Hue row is its teal sky, and its grain and a gold
 * Halation are set in the camera too), eight End Screen pictures, soft focus on the ADJ lever and the date imprint (both off until chosen in the camera), the camera-tested default ratio
 * menu (GR Mod's "default seven": GR III needs at least one added ratio); GR Mod's default round 10.
 */
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { Engine } from '../../../core/src';
import type { SlotRequest } from '../../../core/src/app/engine';
import { openGr3xOfficial } from '../../../core/src/fw/gr3x/profile';
import { GR3X_FILM_IDS, gr3xLookResources } from '../../../core/src/fw/gr3x/look-resources';
import { GR3X_T4_CUSTOM } from '../../../core/src/fw/gr3x/geometry';
import { LOOKS, cubeText } from './looks';
import { filmIcon } from './icons';

const PICTURE_NAMES = ['Star Trails', 'Film Strip', 'Contours', 'Aperture', 'Synthwave', 'Bauhaus', 'Great Wave', 'Good Night'];

const [official, out] = process.argv.slice(2);
if (!official || !out) { console.error('usage: build.ts OFFICIAL.bin OUTDIR (OUTDIR/pictures from pictures.ps1)'); process.exit(2); }
const raw = new Uint8Array(readFileSync(official));
const engine = await Engine.open(raw);
if (engine.info.family !== 'gr3x' || (engine.info.features.maxFilms ?? 0) < LOOKS.length) throw new Error('needs the official GR III 2.10 or GR IIIx 1.60 file');
const { decoded } = await openGr3xOfficial(raw);
const tile = gr3xLookResources(decoded).tiles.film;

mkdirSync(join(out, 'cube'), { recursive: true });
const requests: SlotRequest[] = [];
const report: object[] = [];
const iconSheet = new Uint8Array(400 * 80 * 3);
for (const [i, look] of LOOKS.entries()) {
  const text = cubeText(look);
  writeFileSync(join(out, 'cube', `${String(i + 1).padStart(2, '0')}-${look.name.replaceAll(' ', '-')}.cube`), text);
  const r = engine.convertPreset('cube', text);
  const icon = filmIcon(tile, look);
  requests.push({ slot: GR3X_FILM_IDS[i], names: { en: look.name }, icon,
    preset: { matrixQ13: r.matrixQ13, curves: r.curves, ...(r.postQ9 ? { postQ9: r.postQ9 } : {}) },
    ...(look.recipe?.defaults ? { defaults: look.recipe.defaults } : {}), ...(look.recipe?.grain ? { grain: look.recipe.grain } : {}) });
  report.push({ film: i + 1, name: look.name, about: look.about, ...(look.recipe ? { recipe: look.recipe } : {}),
    meanDE2000: +r.meanDE2000!.toFixed(2), p95DE2000: +r.p95DE2000!.toFixed(2) });
  for (let y = 0; y < 40; y++) for (let x = 0; x < 40; x++) {
    const s = (y * 40 + x) * 4, a = icon[s + 3] / 255, X = (i % 10) * 40 + x, Y = Math.floor(i / 10) * 40 + y;
    for (let c = 0; c < 3; c++) iconSheet[(Y * 400 + X) * 3 + (2 - c)] = Math.round(icon[s + c] * a + 128 * (1 - a));
  }
  console.log(`film ${String(i + 1).padStart(2)}  ${look.name.padEnd(15)} ΔE2000 mean ${r.meanDE2000!.toFixed(2)}  p95 ${r.p95DE2000!.toFixed(2)}`);
}
writeFileSync(join(out, 'icons.bgr'), iconSheet);

const pictureDir = join(out, 'pictures');
const files = readdirSync(pictureDir).filter(f => f.endsWith('.bgr')).sort();
if (files.length !== PICTURE_NAMES.length) throw new Error(`expected ${PICTURE_NAMES.length} pictures in ${pictureDir}`);
const shutdownPictures = files.map((f, k) => {
  const bgr = readFileSync(join(pictureDir, f)), rgb = new Uint8Array(bgr.length);
  for (let i = 0; i < bgr.length; i += 3) { rgb[i] = bgr[i + 2]; rgb[i + 1] = bgr[i + 1]; rgb[i + 2] = bgr[i]; }
  const jpeg = engine.encodeMenuPicture(rgb);
  writeFileSync(join(pictureDir, f.replace(/\.bgr$/, '.camera.jpg')), jpeg);
  // A fixed identity per picture ('FP' + number): the camera's choice survives rebuilding the pack.
  return { id: 0x46500101 + k, name: PICTURE_NAMES[k], jpeg };
});

const ratios = GR3X_T4_CUSTOM.map(r => ({ ratio: r.ratio, name: r.name ?? r.ratio }));
const build = await engine.buildFirmware(requests, ratios, [], { filmCount: LOOKS.length, adjSoftFocus: true, dateStamp: true, shutdownPictures, tealHue: true, grainRow: true });
const checks = Object.entries(build.checks);
if (!checks.every(([, v]) => v === true)) throw new Error('self-check failed: ' + JSON.stringify(build.checks));
const summary = await (await Engine.open(raw)).inspect(build.file);
if (!summary.verified || summary.slots.length !== LOOKS.length || summary.slots.some((s, i) => s.names.en !== LOOKS[i].name) || summary.shutdownPictures?.length !== PICTURE_NAMES.length || !summary.tealHue || !summary.grainRow)
  throw new Error('a fresh engine does not rebuild the same file');
writeFileSync(join(out, engine.info.filename), build.file);
writeFileSync(join(out, 'SHA256SUMS.txt'), `${build.sha256}  ${engine.info.filename}\n`);
writeFileSync(join(out, 'fit-report.json'), JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify({ file: join(out, engine.info.filename), bytes: build.file.length, sha256: build.sha256, selfChecks: checks.length,
  verified: summary.verified, films: summary.slots.length, pictures: summary.shutdownPictures?.map(p => p.name), ratios: summary.ratios.map(r => r.name), adjSoftFocus: summary.adjSoftFocus, dateStamp: summary.dateStamp, tealHue: summary.tealHue, grainRow: summary.grainRow }, null, 1));
