// SPDX-License-Identifier: GPL-2.0-only
/** Reproducible offline GR III 2.10 crop-texture candidate. Never writes a device.
 * npx vite-node tools/gr3x/build-t-texture.mts OFFICIAL CURRENT_PACK REFERENCES OUT PYTHON CODEC [sensor|output]
 * The historical v3 spatial profile must be declared before opening a fresh Engine.
 */
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { Engine } from '../../core/src/app/engine';
import { Firmware, sectionsOf } from '../../core/src/fw/container';
import { GR3X_160 } from '../../core/src/fw/gr3x/profile';
import { encodeGr3xLookRecipe, readGr3xLookRecipe } from '../../core/src/fw/gr3x/look-recipe';
import { readGr3xBuildRecipe } from '../../core/src/fw/gr3x/ratio-recipe';
import { buildGr3xTestFirmware } from '../../core/src/fw/gr3x/research-package';
import { planGr3xMenu } from '../../core/src/fw/gr3x/geometry';
import { readRes, resFile } from '../../core/src/fw/aspect/res';
import { gr3xPicturePath } from '../../core/src/fw/gr3x/shutdown';
import { HALATION } from '../../core/src/fw/aspect/halation';
import type { Gr3xFilmLook } from '../../core/src/fw/gr3x/image-control';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const OFFICIAL = 'd6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4';
const CURRENT = 'cf04126f5861c3a64123f0cdc95efa5b65443b44aa0ca975854423acf0131f55';
const CODEC = '0c15c8f9a97b464ac23ab1641740a8263e0068b0';
const REFERENCES = '49ac27de2266575936c6f562901ed1b784c9d5f74d577fd1e93bd36e242b2c97';
const PINS: Record<string, string> = {
  'v3-portra-400': '890bcdf75029951d3fb3de19fcb24300f4e22ec93061a2c07c7f1b1b378e9197',
  'v3-cinestill-800t': '249ed05a44826b00415d5555dc7160c211ec4295193209ae9409fe8fab730948',
  'v3-gold-200': '6caa69980013cd07992ed4fa2c775ca143d509350b43458cdf6ffe6a1d682894',
  'gold-plus2-approved': '91158f03a8e83fb36563c1ddc9ef8907b153ff6e47a21f8101827a6b92a7fdb6',
};
const sha = (b: Uint8Array | string) => createHash('sha256').update(b).digest('hex');
function requireThat(value: unknown, message: string): asserts value { if (!value) throw new Error(message); }
function payload(film: Gr3xFilmLook): string {
  const p = film.preset; requireThat(p, `Missing exact quantized preset: ${film.name}`);
  const data = [...Array.from(p.matrixQ13), ...p.curves.flatMap(c => Array.from(c)), ...Array.from(p.postQ9 ?? [])];
  const b = Buffer.alloc(data.length * 2); data.forEach((x, i) => b.writeUInt16LE(x & 65535, i * 2));
  return sha(b);
}
function recipes(raw: Uint8Array) {
  const decoded = new Firmware(raw).decoded, rt = sectionsOf(decoded).find(s => s.name === 'RTOS');
  requireThat(rt && rt.size > GR3X_160.rtosLength, 'Missing extended RTOS');
  const app = decoded.subarray(rt.offset + GR3X_160.rtosLength, rt.offset + rt.size);
  const looks = readGr3xLookRecipe(app), features = readGr3xBuildRecipe(app);
  requireThat(looks && features, 'Missing self-describing recipes');
  return { decoded, looks, features };
}
function sourceSnapshot() {
  const files = execFileSync('git', ['ls-files', '--cached', '--others', '--exclude-standard', '--', 'core/src', 'tools/gr3x/build-t-texture.mts', 'tools/gr3x/package_probe.py', 'tools/gr3x/identity.py', 'tools/gr3x/ratio_menu.py'], { cwd: ROOT, encoding: 'utf8' }).trim().split(/\r?\n/).filter(Boolean);
  return [...new Set(files)].sort().map(path => ({ path, sha256Lf: sha(readFileSync(join(ROOT, path), 'utf8').replace(/\r\n/g, '\n')) }));
}

const args = process.argv.slice(2).filter(a => a !== '--');
if (args.length < 6 || args.length > 7) throw new Error('usage: build-t-texture.mts OFFICIAL CURRENT_PACK REFERENCES OUT PYTHON CODEC [sensor|output]');
const [officialPath, currentPath, referencesPath, out, python, codec] = args.slice(0, 6).map(p => resolve(p));
const policy = args[6] ?? 'sensor';
requireThat(policy === 'sensor' || policy === 'output', 'texture policy must be sensor or output');
requireThat(!existsSync(out), 'Output directory already exists; choose a fresh path');
const official = new Uint8Array(readFileSync(officialPath)), current = new Uint8Array(readFileSync(currentPath));
requireThat(sha(official) === OFFICIAL, 'Official GR III 2.10 SHA-256 mismatch');
requireThat(sha(current) === CURRENT, 'Current all-film MTF pack SHA-256 mismatch');
requireThat(resolve(execFileSync('git', ['rev-parse', '--show-toplevel'], { cwd: codec, encoding: 'utf8' }).trim()).toLowerCase() === codec.toLowerCase(), 'Codec must be its own checkout');
requireThat(execFileSync('git', ['rev-parse', 'HEAD'], { cwd: codec, encoding: 'utf8' }).trim() === CODEC, 'Independent codec commit mismatch');
requireThat(!execFileSync('git', ['status', '--porcelain', '--untracked-files=no'], { cwd: codec, encoding: 'utf8' }).trim(), 'Independent codec tracked files are modified');
const refManifestBytes = readFileSync(join(referencesPath, 'manifest.json'));
requireThat(sha(refManifestBytes) === REFERENCES, 'Pinned reference manifest SHA-256 mismatch');
const refManifest = JSON.parse(refManifestBytes.toString('utf8'));
const refs = new Map<string, Gr3xFilmLook>();
for (const [id, pin] of Object.entries(PINS)) {
  const ref = refManifest.references.find((r: { id: string }) => r.id === id);
  requireThat(ref, `Missing reference ${id}`);
  const artifact = refManifest.artifacts.find((a: { path: string }) => a.path === ref.coefficients);
  requireThat(artifact && ref.coefficients === `coefficients/${id}.json`, `Invalid reference path ${id}`);
  const bytes = readFileSync(join(referencesPath, ref.coefficients));
  requireThat(sha(bytes) === artifact.sha256, `Coefficient artifact hash mismatch ${id}`);
  const data = JSON.parse(bytes.toString('utf8')) as Gr3xFilmLook;
  requireThat(payload(data) === pin, `Quantized payload mismatch ${id}`); refs.set(id, data);
}
const sources = sourceSnapshot();
// v3 profile is process-local and explicit: this tool never mutates a shared Engine after caching.
const h = HALATION as unknown as { start: number; narrow: number; wide: number; mix: number; gain: number[] };
const shippedGains = [...h.gain];
h.start = 228; h.narrow = .006; h.wide = .035; h.mix = .3; h.gain = shippedGains.map(g => +(g * .78).toFixed(2));
const spatialProfile = { start: h.start, narrow: h.narrow, wide: h.wide, mix: h.mix, gain: [...h.gain] };
const originalSummary = await (await Engine.open(official)).inspect(current);
requireThat(originalSummary.verified, 'Fresh Engine did not exactly reconstruct the return pack under declared v3 profile');
const { decoded, looks, features } = recipes(current);
requireThat(looks.filmCount === 20 && looks.films?.length === 20 && looks.films.every(f => f.filmMtf === true), 'Expected twenty-film MTF pack');
requireThat(looks.textureGeometry === undefined && looks.grainRow && looks.tealHue && features.round10 && features.adjSoftFocus, 'Unexpected return pack features');
for (const id of ['v3-portra-400', 'v3-cinestill-800t', 'v3-gold-200']) {
  const ref = refs.get(id)!;
  requireThat(looks.films.find(f => f.name === ref.name && payload(f) === PINS[id]), `Current pack differs from ${id}`);
}
const displaced = looks.films[0]; requireThat(displaced.name === 'Pro 400H', 'Unexpected slot64; refusing implicit replacement');
const gold = looks.films.find(f => f.name === 'Gold 200')!;
const approved = refs.get('gold-plus2-approved')!;
requireThat(approved.name === 'Gold +2 EV (approved)', 'Approved comparator label mismatch');
const films = looks.films.map((film, i) => i ? film : {
  ...gold, name: approved.name, names: { en: approved.name }, preset: approved.preset,
});
const dir = readRes(decoded);
const pictures = features.pictures.map((name, k) => {
  const jpeg = resFile(decoded, gr3xPicturePath(k), dir); requireThat(jpeg, `Missing return-pack picture ${k}`);
  return { name, jpeg, id: features.pictureIds[k] };
});
const built = await buildGr3xTestFirmware(official, [], { ...looks, films, textureGeometry: policy }, planGr3xMenu(features.ratios), { ...features, pictures });
requireThat(Object.values(built.report.checks).every(v => v === true), 'Container self-check failed');
const summary = await (await Engine.open(official)).inspect(built.bytes);
requireThat(summary.verified && summary.textureGeometry === policy && summary.slots.length === 20, 'Fresh Engine candidate reconstruction failed');
const roundtrip = recipes(built.bytes);
requireThat(JSON.stringify(roundtrip.features) === JSON.stringify(features), 'Ratios, guard or ADJ feature recipe changed');
requireThat(Buffer.from(encodeGr3xLookRecipe(roundtrip.looks)).equals(Buffer.from(encodeGr3xLookRecipe({ ...looks, films, textureGeometry: policy }))), 'Canonical film recipe preservation failed');
requireThat(payload(roundtrip.looks.films![0]) === PINS['gold-plus2-approved'], 'Approved Gold changed in candidate');
for (const source of sources) requireThat(sha(readFileSync(join(ROOT, source.path), 'utf8').replace(/\r\n/g, '\n')) === source.sha256Lf, `Source changed during generation: ${source.path}`);
mkdirSync(out, { recursive: true });
const writeJson = (path: string, obj: unknown) => writeFileSync(join(out, path), JSON.stringify(obj, null, 2) + '\n', { encoding: 'utf8', flag: 'wx' });
const candidateName = 'T-TEXTURE-UNVALIDATED.bin';
writeFileSync(join(out, candidateName), built.bytes, { flag: 'wx' });
writeFileSync(join(out, 'RETURN-CURRENT-MTF.bin'), current, { flag: 'wx' });
writeJson('patch-manifest.json', built.manifest); writeJson('build-report.json', built.report);
execFileSync(python, [join(ROOT, 'tools/gr3x/package_probe.py'), '--official', officialPath, '--container', join(out, candidateName), '--manifest', join(out, 'patch-manifest.json'), '--build-report', join(out, 'build-report.json'), '--reference', codec, '--report', join(out, 'independent-verification.json')], { cwd: ROOT, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
const independent = JSON.parse(readFileSync(join(out, 'independent-verification.json'), 'utf8'));
requireThat(independent.output_sha256 === sha(built.bytes), 'Independent verification identity mismatch');
const report = {
  schema: 1, kind: 'GR3-TTEXTURE-1', status: 'HOST-VERIFIED-REVIEW-PENDING', camera: 'GR III', firmware: '2.10', hardwareTested: false,
  officialSha256: OFFICIAL, returnSha256: CURRENT, candidate: { file: candidateName, sha256: sha(built.bytes), bytes: built.bytes.length },
  return: { file: 'RETURN-CURRENT-MTF.bin', sha256: CURRENT, installedIdentityEstablished: false },
  textureGeometry: policy, spatialProfile, recipeRebuildVerified: summary.verified, independentCodec: { commit: CODEC, result: 'independent-verification.json' },
  colour: { existingFilmsPreserved: 19, approvedGoldId: 64, approvedGold: PINS['gold-plus2-approved'], oldGoldRetained: true, portraUnchanged: true,
    displaced: { id: 64, name: displaced.name, payloadSha256: payload(displaced) },
    comparatorTexture: 'Copies current Gold defaults/grain/MTF/icon, separately from the approved colour fit; this is not an approved texture treatment.' },
  slots: films.map((f, i) => ({ id: 64 + i, name: f.name, payloadSha256: payload(f), filmMtf: f.filmMtf === true, defaults: f.defaults, grain: f.grain })),
  ratios: features.ratios, guard: 'round10 retained', adjChoice: 'Keep existing Soft Focus; ADJ Grain not included because its shared function requires an explicit tradeoff.',
  limitations: ['Not camera tested or flashed.', 'Sensor policy assumes retained sensor pixel pitch; there is no verified per-shot crop provenance.', 'MTF excludes custom mains narrower than960, including640x1280.', 'RAW-development texture control route remains a separate hardware-session gate.', 'Full section5 reset required for changed film library and return.', 'Candidate retains explicit historical v3 spatial profile; use this declared profile when reconstructing.'],
  repository: { head: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: ROOT, encoding: 'utf8' }).trim(), hashEncoding: 'UTF-8 with CRLF normalized to LF', sources },
};
writeJson('research-manifest.json', report);
writeFileSync(join(out, 'SHA256SUMS.txt'), `${sha(built.bytes)}  ${candidateName}\n${CURRENT}  RETURN-CURRENT-MTF.bin\n`, { encoding: 'utf8', flag: 'wx' });
console.log(JSON.stringify({ ...report, slots: report.slots.map(s => `${s.id} ${s.name}`), repository: { ...report.repository, sources: `${sources.length} hashed source files` } }, null, 2));
