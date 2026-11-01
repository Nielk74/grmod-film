// SPDX-License-Identifier: GPL-2.0-only
/**
 * The film pack, v3 (experimental, from the 2026-10-31 study): the same firmware as ../film-pack
 * (twenty films with recipes, Teal Sky and Grain rows, End Screen pictures, soft focus, date imprint,
 * default ratios), with
 *  - every film pushed by "film response" (response.ts) instead of shipped as authored; a film whose
 *    pushed version the camera cannot hold (fit mean over 3 dE2000, or a post matrix beyond 12 bits)
 *    stays as authored;
 *  - film 1 (Velvia, which the user dropped) replaced by "Pro 400H": Fujifilm Pro 400H on Fujicolor
 *    Crystal Archive paper, from stock datasheet data through tools/jpeg_experiments/film_datasheet_v3.py
 *    (the data is spektrafilm's, CC BY-SA 4.0: this .cube is not part of the repository). An earlier
 *    v3 had "Portra Print" here; the user prefers Portra 400's film response (film 12);
 *  - halation reshaped: a wider, softer glow (spread 0.6 % and 3.5 % of the width, mostly the wide
 *    one) that starts near clipping (level 228: a first v3 started at 200 and washed large lit areas,
 *    tools/jpeg_experiments/halation_v3.py PROPOSED2), gains lowered to keep its strength; its colour
 *    stays the camera's choice (red, orange, gold, white);
 *  - grain v2 (tools/grain/grain.c: tiles from the Boolean film grain model, colour grain, strongest in
 *    the shadows and lower midtones), Portra 400 one step up (Medium, as Kodak's Print Grain Index
 *    suggests);
 *  - film sharpness (MTF) through the camera's own controls: Sharpness at most -1 (less of the camera's
 *    sharpening), Clarity +1 where a film does not set it (development's edge effects). The controls'
 *    exact response is not checked on a camera.
 * Not in the firmware: shoot films with Highlight Correction (D-Range) on in contrasty light; it is the
 * camera's own film latitude (one stop less exposure, pushed back in the JPEG) and a camera-wide setting.
 *
 *   npx vite-node examples/gr3x/film-pack-v3/build.ts OFFICIAL.bin PRO_400H.cube PICTURES_DIR OUT
 *
 * PICTURES_DIR: the End Screen pictures (.bgr) from ../film-pack/pictures.ps1.
 */
import { mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { Engine } from '../../../core/src';
import type { SlotRequest } from '../../../core/src/app/engine';
import type { PresetResult } from '../../../core/src/app/engine';
import { openGr3xOfficial } from '../../../core/src/fw/gr3x/profile';
import { GR3X_FILM_IDS, gr3xLookResources } from '../../../core/src/fw/gr3x/look-resources';
import { GR3X_T4_CUSTOM } from '../../../core/src/fw/gr3x/geometry';
import { HALATION, paramBytes, halationGains } from '../../../core/src/fw/aspect/halation';
import { LOOKS, cubeText } from '../film-pack/looks';
import type { Look } from '../film-pack/looks';
import { filmIcon } from '../film-pack/icons';
import { filmResponse } from './response';

const PICTURE_NAMES = ['Star Trails', 'Film Strip', 'Contours', 'Aperture', 'Synthwave', 'Bauhaus', 'Great Wave', 'Good Night'];
const MAX_FIT = 3.0;

const [official, film1Cube, pictureDir, out] = process.argv.slice(2).filter(a => a !== '--');
if (!official || !film1Cube || !pictureDir || !out) {
  console.error('usage: build.ts OFFICIAL.bin PRO_400H.cube PICTURES_DIR OUT'); process.exit(2);
}

// Halation, reshaped for this build only (the shared constants are read when the firmware is built).
const H = HALATION as unknown as { start: number; narrow: number; wide: number; mix: number; gain: number[] };
const shipped = { start: H.start, narrow: H.narrow, wide: H.wide, mix: H.mix, gain: [...H.gain] };
H.start = 228; H.narrow = 0.006; H.wide = 0.035; H.mix = 0.3;
H.gain = shipped.gain.map(g => +(g * 0.78).toFixed(2));
console.log('halation', JSON.stringify({ shipped, v3: { start: H.start, narrow: H.narrow, wide: H.wide, mix: H.mix, gain: H.gain } }));

const raw = new Uint8Array(readFileSync(official));
const engine = await Engine.open(raw);
if (engine.info.family !== 'gr3x' || (engine.info.features.maxFilms ?? 0) < LOOKS.length) throw new Error('needs the official GR III 2.10 or GR IIIx 1.60 file');
const { decoded } = await openGr3xOfficial(raw);
const tile = gr3xLookResources(decoded).tiles.film;

const proNegHi = LOOKS.find(l => l.name === 'Pro Neg Hi')!;
const film1: Look = { ...proNegHi, name: 'Pro 400H', caption: 'PRO 400H', code: '4H',
  about: 'Fujifilm Pro 400H on Crystal Archive paper, from the stocks\' datasheets: cyan-teal skies, slightly green highlights, dense greens.',
  recipe: { defaults: { sharpness: -1 }, grain: { amount: 1, size: 'small' } } };

/** v3's recipe changes: Portra 400 one grain step up (Kodak's Print Grain Index), and film sharpness:
 * Sharpness at most -1, Clarity +1 where the film does not set it. */
function v3Recipe(look: Look): NonNullable<Look['recipe']> {
  const r = look.recipe ?? {}, d = r.defaults ?? {};
  const grain = look.name === 'Portra 400' && r.grain ? { ...r.grain, amount: 2 as const } : r.grain;
  return { ...r, defaults: { ...d, sharpness: Math.min(d.sharpness ?? 0, -1), clarity: d.clarity ?? 1 }, ...(grain ? { grain } : {}) };
}

function fit(text: string): PresetResult | null {
  try { return engine.convertPreset('cube', text); } catch { return null; }
}

mkdirSync(join(out, 'cube'), { recursive: true });
const requests: SlotRequest[] = [];
const report: object[] = [];
const iconSheet = new Uint8Array(400 * 80 * 3);
const films: Look[] = [];
for (const [i, base] of LOOKS.entries()) {
  let look: Look, text: string, r: PresetResult | null, how: string;
  if (i === 0) {
    look = film1; text = readFileSync(film1Cube, 'utf8'); r = fit(text); how = 'datasheet print';
    if (!r) throw new Error('Pro 400H does not fit');
  } else {
    const pushed: Look = { ...base, op: filmResponse(base.op) };
    text = cubeText(pushed); r = fit(text); look = pushed; how = 'film response';
    if (!r || r.meanDE2000! > MAX_FIT) {
      console.log(`film ${i + 1} ${base.name}: film response ${r ? `fits at ${r.meanDE2000!.toFixed(2)}` : 'does not fit'}; kept as authored`);
      look = base; text = cubeText(base); r = fit(text)!; how = 'as authored';
    }
  }
  look = { ...look, recipe: v3Recipe(look) };
  films.push(look);
  writeFileSync(join(out, 'cube', `${String(i + 1).padStart(2, '0')}-${look.name.replaceAll(' ', '-')}.cube`), text);
  const icon = filmIcon(tile, look);
  requests.push({ slot: GR3X_FILM_IDS[i], names: { en: look.name }, icon,
    preset: { matrixQ13: r.matrixQ13, curves: r.curves, ...(r.postQ9 ? { postQ9: r.postQ9 } : {}) },
    ...(look.recipe?.defaults ? { defaults: look.recipe.defaults } : {}), ...(look.recipe?.grain ? { grain: look.recipe.grain } : {}) });
  report.push({ film: i + 1, name: look.name, version: how, about: look.about, ...(look.recipe ? { recipe: look.recipe } : {}),
    meanDE2000: +r.meanDE2000!.toFixed(2), p95DE2000: +r.p95DE2000!.toFixed(2), postMatrix: !!r.postQ9 });
  for (let y = 0; y < 40; y++) for (let x = 0; x < 40; x++) {
    const s = (y * 40 + x) * 4, a = icon[s + 3] / 255, X = (i % 10) * 40 + x, Y = Math.floor(i / 10) * 40 + y;
    for (let c = 0; c < 3; c++) iconSheet[(Y * 400 + X) * 3 + (2 - c)] = Math.round(icon[s + c] * a + 128 * (1 - a));
  }
  console.log(`film ${String(i + 1).padStart(2)}  ${look.name.padEnd(15)} ${how.padEnd(16)} ΔE2000 mean ${r.meanDE2000!.toFixed(2)}  p95 ${r.p95DE2000!.toFixed(2)}`);
}
writeFileSync(join(out, 'icons.bgr'), iconSheet);

const files = readdirSync(pictureDir).filter(f => f.endsWith('.bgr')).sort();
if (files.length !== PICTURE_NAMES.length) throw new Error(`expected ${PICTURE_NAMES.length} pictures in ${pictureDir}`);
const shutdownPictures = files.map((f, k) => {
  const bgr = readFileSync(join(pictureDir, f)), rgb = new Uint8Array(bgr.length);
  for (let i = 0; i < bgr.length; i += 3) { rgb[i] = bgr[i + 2]; rgb[i + 1] = bgr[i + 1]; rgb[i + 2] = bgr[i]; }
  return { id: 0x46500101 + k, name: PICTURE_NAMES[k], jpeg: engine.encodeMenuPicture(rgb) };
});

const ratios = GR3X_T4_CUSTOM.map(r => ({ ratio: r.ratio, name: r.name ?? r.ratio }));
const build = await engine.buildFirmware(requests, ratios, [], { filmCount: LOOKS.length, adjSoftFocus: true, dateStamp: true, shutdownPictures, tealHue: true, grainRow: true });
const checks = Object.entries(build.checks);
if (!checks.every(([, v]) => v === true)) throw new Error('self-check failed: ' + JSON.stringify(build.checks));
const summary = await (await Engine.open(raw)).inspect(build.file);
if (!summary.verified || summary.slots.length !== LOOKS.length || summary.slots.some((s, i) => s.names.en !== films[i].name) || summary.shutdownPictures?.length !== PICTURE_NAMES.length || !summary.tealHue || !summary.grainRow)
  throw new Error('a fresh engine does not rebuild the same file');

// The reshaped halation must be in the file: its parameter block and its gains.
const params = paramBytes(), gains = new Uint8Array(new Uint16Array([...halationGains(), 0]).buffer);
const has = (hay: Uint8Array, needle: Uint8Array) => { outer: for (let i = 0; i + needle.length <= hay.length; i++) { for (let j = 0; j < needle.length; j++) if (hay[i + j] !== needle[j]) continue outer; return true; } return false; };
const rebuilt = (await openGr3xOfficial(raw)).decoded;
const mine = new (await import('../../../core/src/fw/container')).Firmware(build.file).decoded;
if (!has(mine, params.subarray(0, 6)) || !has(mine, gains)) throw new Error('the reshaped halation is not in the file');
if (has(rebuilt, params.subarray(0, 6))) console.log('note: the halation parameter bytes also occur in the official file');

writeFileSync(join(out, engine.info.filename), build.file);
writeFileSync(join(out, 'SHA256SUMS.txt'), `${build.sha256}  ${engine.info.filename}\n`);
writeFileSync(join(out, 'fit-report.json'), JSON.stringify({ halation: { shipped, v3: { start: H.start, narrow: H.narrow, wide: H.wide, mix: H.mix, gain: H.gain } }, films: report }, null, 2) + '\n');
console.log(JSON.stringify({ file: join(out, engine.info.filename), bytes: build.file.length, sha256: build.sha256, selfChecks: checks.length,
  verified: summary.verified, films: summary.slots.map(s => s.names.en), tealHue: summary.tealHue, grainRow: summary.grainRow }, null, 1));
