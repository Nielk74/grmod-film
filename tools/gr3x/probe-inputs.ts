// SPDX-License-Identifier: GPL-2.0-only
/**
 * Development tool: build a GR III / IIIx firmware through the Engine and write what the native
 * probes read (the decoded RTOS section, the patch manifest, the build report), e.g. to run
 * films_probe.py or films_r10_verify.py on a build with GR Mod's film recipes.
 *
 *   npx vite-node tools/gr3x/probe-inputs.ts OFFICIAL.bin OUT-DIR REQUESTS.json [OPTIONS.json]
 *
 * REQUESTS.json: the Engine's SlotRequest list (presets as {matrixQ13, curves, postQ9} arrays);
 * OPTIONS.json: BuildOptions (default: the film count of the requests). Writes OUT-DIR/rtos.bin,
 * manifest.json, report.json and firmware.bin, and checks that the Engine's own build is the same file.
 */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { Engine } from '../../core/src';
import { buildGr3xTestFirmware } from '../../core/src/fw/gr3x/research-package';
import { GR3X_FILM_IDS, GR3X_FILM_NAMES } from '../../core/src/fw/gr3x/look-resources';
import { GR3X_T4_CUSTOM, GR3X_T4_MENU } from '../../core/src/fw/gr3x/geometry';
import { sectionsOf } from '../../core/src/fw/container';
import { Firmware } from '../../core/src/fw';

const [official, out, requestsFile, optionsFile] = process.argv.slice(2);
const raw = new Uint8Array(readFileSync(official));
const requests = JSON.parse(readFileSync(requestsFile, 'utf8'));
const filmCount = requests.length;
const options = optionsFile ? JSON.parse(readFileSync(optionsFile, 'utf8')) : { filmCount };
const engine = await Engine.open(raw);
const built = await engine.buildFirmware(requests, GR3X_T4_CUSTOM.map(x => ({ ratio: x.ratio, name: x.name ?? x.ratio })), [], options);
// The same build through the research builder, for its manifest (as Engine.fixedGr3x does, round 10).
const looks = { displayRevision: 3 as const, monoReplicas: false, ownParameters: true, filmCount: options.filmCount, ...(options.tealHue ? { tealHue: true } : {}), ...(options.grainRow ? { grainRow: true } : {}),
  films: GR3X_FILM_IDS.slice(0, options.filmCount).map((id, i) => {
    const r = requests.find((q: { slot: string }) => q.slot === id);
    return { name: r?.names?.en ?? GR3X_FILM_NAMES[i], ...(r?.preset ? { preset: r.preset } : {}), ...(r?.defaults ? { defaults: r.defaults } : {}), ...(r?.grain?.amount ? { grain: r.grain } : {}) };
  }) };
const features = { adjSoftFocus: !!options.adjSoftFocus, ...(options.dateStamp ? { dateImprint: true, dateMenu: 'submenu' as const } : {}), round7: true, round8: true, round9: true, round10: true };
const r = await buildGr3xTestFirmware(raw, [], looks, GR3X_T4_MENU, features);
if (r.report.outputSha256 !== built.sha256) throw new Error('the research build is not the Engine build');
mkdirSync(out, { recursive: true });
const decoded = new Firmware(r.bytes).decoded;
const rtos = sectionsOf(decoded).find(s => s.name === 'RTOS')!;
writeFileSync(join(out, 'rtos.bin'), decoded.subarray(rtos.offset, rtos.offset + rtos.size));
writeFileSync(join(out, 'manifest.json'), JSON.stringify(r.manifest));
writeFileSync(join(out, 'report.json'), JSON.stringify(r.report));
writeFileSync(join(out, 'firmware.bin'), r.bytes);
// The halation module's expected result on picture_stage_probe.py's synthetic picture, per film, at
// strength 1 + k % 3, red for even films and white for odd ones (as build-t6.mjs).
const { halateYcc, halationLight } = await import('../../core/src/fw/aspect/halation');
const W = 320, H = 240, parts: Uint8Array[] = [];
for (let k = 0; k < options.filmCount; k++) {
  const level = 1 + (k % 3), white = k % 2 === 1;
  const Y = new Uint8Array(W * H), C = new Uint8Array(W * H);
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    Y[y * W + x] = 140 < x && x < 180 && 100 < y && y < 140 ? 252 : 16 + ((x * 3 + y * 5) % 220);
    C[y * W + x] = 128 + ((Math.floor(x / 2) + y) % 40) - 20;
  }
  const look = (r.manifest as any).addedLooks[k];
  halateYcc(Y, C, W, H, level as 1 | 2 | 3, look.quantizedCurves ? halationLight(look.quantizedCurves, look.postQ9) : halationLight(), white ? 'white' : 'red');
  const head = new Uint8Array(4); new DataView(head.buffer).setUint32(0, (32 + k) | level << 8 | (white ? 0x20000 : 0), true);
  parts.push(head, Y, C);
}
// The Grain row's builds: gold (stash bit 18) and orange (bit 21) too, every film at strength 1 + k % 3.
if (options.grainRow) for (const [colour, bit] of [['gold', 0x40000], ['orange', 0x200000]] as const) for (let k = 0; k < options.filmCount; k++) {
  const level = 1 + (k % 3);
  const Y = new Uint8Array(W * H), C = new Uint8Array(W * H);
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    Y[y * W + x] = 140 < x && x < 180 && 100 < y && y < 140 ? 252 : 16 + ((x * 3 + y * 5) % 220);
    C[y * W + x] = 128 + ((Math.floor(x / 2) + y) % 40) - 20;
  }
  const look = (r.manifest as any).addedLooks[k];
  halateYcc(Y, C, W, H, level as 1 | 2 | 3, look.quantizedCurves ? halationLight(look.quantizedCurves, look.postQ9) : halationLight(), colour);
  const head = new Uint8Array(4); new DataView(head.buffer).setUint32(0, (32 + k) | level << 8 | bit, true);
  parts.push(head, Y, C);
}
writeFileSync(join(out, 'halation-reference.bin'), Buffer.concat(parts.map(p => Buffer.from(p))));
console.log(JSON.stringify({ sha256: built.sha256, films: options.filmCount }));
