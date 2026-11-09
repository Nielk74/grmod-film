// SPDX-License-Identifier: GPL-2.0-only
/**
 * Save the four fixed GR III 2.10 research references without building firmware.
 * From the repository root:
 *   node_modules/.bin/vite-node --script tools/gr3x/research-reference.ts OFFICIAL.bin NEW_OUTDIR
 * The output must be new. Approved Gold uses its archived fit directly, without refitting.
 * Its derived data retains the attribution/licence recorded in exposure_print/README.md.
 */
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Engine } from '../../core/src';
import type { PresetResult } from '../../core/src/app/engine';
import { quantizeSlot } from '../../core/src/color/camera';
import type { QuantizedSlot, SlotParams } from '../../core/src/color/camera';
import { GR3X_CAMERA } from '../../core/src/color/gr3x-camera';
import { LOOKS, cubeText } from '../../core/src/filmpack/looks';
import { gr3xFilmPrint } from '../../core/src/fw/gr3x/image-control';
import { validateGr3xLookName } from '../../core/src/fw/gr3x/look-resources';
import { filmResponse } from '../../examples/gr3x/film-pack-v3/response';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
const OFFICIAL_SHA256 = 'd6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4';
const APPROVED_SOURCE = 'tools/jpeg_experiments/exposure_print/approved.json';
const APPROVED_PREVIEW = 'c86865ce62eaf6595e3887834a68aa57a3a88acfe70ef221ef510e674e74ec80';
const APPROVED_PAYLOAD = '91158f03a8e83fb36563c1ddc9ef8907b153ff6e47a21f8101827a6b92a7fdb6';
const V3 = [
  { id: 'v3-portra-400', name: 'Portra 400', colour: 1.5, midSaturation: 0.12,
    targetSha256: 'c24a4926e8834007beaa92cb2e091f27e31919262c7ff290cb7c30ed0cc768ca',
    payloadSha256: '890bcdf75029951d3fb3de19fcb24300f4e22ec93061a2c07c7f1b1b378e9197' },
  { id: 'v3-cinestill-800t', name: 'CineStill 800T', colour: 1.5, midSaturation: 0.12,
    targetSha256: 'c722cc708df035ebe00fd3325ff8c9524ad2afb931fa2826bf65e597138c9f15',
    payloadSha256: '249ed05a44826b00415d5555dc7160c211ec4295193209ae9409fe8fab730948' },
  { id: 'v3-gold-200', name: 'Gold 200', colour: 1, midSaturation: 0,
    targetSha256: '7801a85e3260afbe92f5c499b7ac2c99bcd948588d73af31035ff8bd8e842ec9',
    payloadSha256: '6caa69980013cd07992ed4fa2c775ca143d509350b43458cdf6ffe6a1d682894' },
] as const;
const FIT_OPTIONS = { post: true, endGreyWeight: 24, refine: false, legacyFit: false };
const SCOPE = {
  evidenceClass: 'software-model',
  input: 'camera Standard rendering, sRGB display RGB in 0..1',
  cameraModel: 'GR3X_CAMERA shared software reference; curve provenance is documented in core/src/color/gr3x-camera.ts',
  cameraRenderingVerified: false,
  realFilmAccuracyVerified: false,
  textureIncludedInColourModel: false,
  limitation: 'A fitted software rendering does not establish actual GR III rendering, film fidelity or recovery of clipped capture data.',
};
const SOURCE_FILES = [
  'tools/gr3x/research-reference.ts', 'examples/gr3x/film-pack-v3/build.ts',
  'examples/gr3x/film-pack-v3/response.ts', 'examples/gr3x/film-pack/looks.ts',
  'core/src/filmpack/looks.ts', 'core/src/app/engine.ts', 'core/src/color/camera.ts',
  'core/src/color/gr3x-camera.ts', 'core/src/color/gr3x-import.ts', 'core/src/color/cube.ts',
  'core/src/color/math.ts', 'core/src/color/fit.ts', 'core/src/color/convert.ts',
  'core/src/fw/gr3x/image-control.ts', APPROVED_SOURCE,
  'tools/jpeg_experiments/exposure_print/calibration.json',
  'tools/jpeg_experiments/exposure_print/README.md',
];
type PlainParams = { M1: number[][]; ck: number[][]; P2?: number[][] };
interface Approved {
  accepted_by: string; accepted_date: string; representation: string;
  fits: { id: string; params: PlainParams; options: object; full_grid: object }[];
  preview_hashes: Record<string, string>;
  targets: { candidate: { file: string; sha256: string } };
  controls: object; selected_physical_parameters: object[];
}
interface Artifact { path: string; bytes: number; sha256: string; kind: string; reference: string }
const sha = (bytes: Uint8Array | string) => createHash('sha256').update(bytes).digest('hex');
const jsonBytes = (value: unknown) => Buffer.from(JSON.stringify(value, null, 2) + '\n', 'utf8');
const requireHash = (actual: string, expected: string, name: string) => {
  if (actual !== expected) throw new Error(`${name} SHA-256 changed: expected ${expected}, got ${actual}`);
};
const plainParams = (p: SlotParams): PlainParams => ({ M1: p.M1.map(r => [...r]), ck: p.ck.map(c => Array.from(c)),
  ...(p.P2 ? { P2: p.P2.map(r => [...r]) } : {}) });

function quantizedData(q: QuantizedSlot) {
  const preset = { matrixQ13: Array.from(q.matrixQ13), curves: q.curves.map(c => Array.from(c)),
    ...(q.postQ9 ? { postQ9: Array.from(q.postQ9) } : {}) };
  if (preset.matrixQ13.length !== 9 || [0,1,2].some(r => preset.matrixQ13.slice(r*3,r*3+3).reduce((a,b) => a+b,0) !== 8192)
      || preset.curves.some(c => c.length !== 256 || c.some((v,i) => v < 0 || v > 16383 || (i > 0 && v < c[i-1])))
      || (preset.postQ9 && (preset.postQ9.length !== 9 || [0,1,2].some(r => preset.postQ9!.slice(r*3,r*3+3).reduce((a,b) => a+b,0) !== 512))))
    throw new Error('invalid quantized reference');
  const values = [...preset.matrixQ13, ...preset.curves.flat(), ...(preset.postQ9 ?? [])];
  const bytes = Buffer.alloc(values.length * 2);
  values.forEach((v,i) => bytes.writeUInt16LE(v & 0xffff, i * 2));
  return { preset, quantizedPayload: { bytes: bytes.length, sha256: sha(bytes),
    layout: 'little endian: signed matrixQ13[9], unsigned R[256], G[256], B[256], optional signed postQ9[9]; 16 bits per value',
    fingerprintFNV1a: gr3xFilmPrint(q.matrixQ13, q.curves, q.postQ9) } };
}

async function main() {
  const args = process.argv.slice(2).filter(a => a !== '--');
  if (args.length !== 2) throw new Error('Usage: research-reference.ts OFFICIAL.bin NEW_OUTDIR');
  const [official, destination] = args, out = resolve(destination);
  if (existsSync(out)) throw new Error('Output directory must not exist; references are never overwritten');
  const raw = readFileSync(official);
  requireHash(sha(raw), OFFICIAL_SHA256, 'official GR III 2.10 firmware');
  const engine = await Engine.open(new Uint8Array(raw));
  if (engine.info.family !== 'gr3x' || engine.info.version !== '2.10' || !engine.info.models.includes('GR3'))
    throw new Error('Expected the verified official GR III 2.10 firmware');
  const repository = {
    head: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: ROOT, encoding: 'utf8' }).trim(),
    trackedChangesPresent: execFileSync('git', ['status', '--porcelain=v1', '--untracked-files=no'], { cwd: ROOT, encoding: 'utf8' }).trim().length > 0,
    sourceSnapshot: 'Working-tree hashes below are authoritative; HEAD alone may omit uncommitted sources.',
    hashEncoding: 'sha256Lf = UTF-8 text with CRLF normalized to LF; paths relative to repository root',
    sources: SOURCE_FILES.map(path => ({ path, sha256Lf: sha(readFileSync(join(ROOT,path), 'utf8').replace(/\r\n/g, '\n')) })),
  };
  const artifacts: Artifact[] = [], outputs: { path: string; bytes: Buffer }[] = [];
  const add = (path: string, bytes: Buffer, kind: string, reference: string) => {
    outputs.push({ path, bytes }); artifacts.push({ path, bytes: bytes.length, sha256: sha(bytes), kind, reference });
  };
  const references: object[] = [];
  for (const ref of V3) {
    const look = LOOKS.find(l => l.name === ref.name);
    if (!look) throw new Error(`Missing authored look: ${ref.name}`);
    const text = cubeText({ ...look, op: filmResponse(look.op, ref.colour, ref.midSaturation, 0.03) });
    requireHash(sha(text), ref.targetSha256, `${ref.name} v3 target`);
    const fitted: PresetResult = engine.convertPreset('cube', text, undefined, FIT_OPTIONS);
    if (!Number.isFinite(fitted.meanDE2000) || fitted.meanDE2000! > 3)
      throw new Error(`${ref.name}: v3 would fall back to the authored target; this pinned reference has changed`);
    const target = `cubes/${ref.id}.cube`, coefficients = `coefficients/${ref.id}.json`;
    const data = quantizedData(fitted);
    requireHash(data.quantizedPayload.sha256, ref.payloadSha256, `${ref.name} v3 quantized payload`);
    const recipe = { defaults: { ...look.recipe?.defaults, sharpness: 0, clarity: 0 },
      ...(look.recipe?.grain ? { grain: { ...look.recipe.grain, ...(ref.name === 'Portra 400' ? { amount: 2 } : {}) } } : {}), filmMtf: true };
    const colourRecipe = { source: 'examples/gr3x/film-pack-v3/build.ts', wrapper: 'examples/gr3x/film-pack-v3/response.ts#filmResponse',
      colour: ref.colour, midSaturation: ref.midSaturation, shoulder: 0.03, cubeSize: 33, cubeOrder: 'red fastest',
      fallbackRule: 'fall back to authored look if conversion fails or meanDE2000 > 3', selected: 'film response' };
    const fit = { method: 'Engine.convertPreset', options: FIT_OPTIONS,
      reportingSet: 'syntheticSamples(1100, 161, 1), independent of fitting; core/src/color/gr3x-import.ts',
      errorsAgainstOwnTarget: { meanDE76: fitted.meanDE, p95DE76: fitted.p95DE, meanDE2000: fitted.meanDE2000, p95DE2000: fitted.p95DE2000 } };
    add(target, Buffer.from(text, 'utf8'), 'v3-target-cube', ref.id);
    add(coefficients, jsonBytes({ schema: 1, id: ref.id, name: ref.name, scope: SCOPE,
      colourRecipe, fit, recipe, params: plainParams(fitted.params), ...data,
      standardMatrixQ13: engine.info.standardMatrixQ13, dataLicense: 'GPL-2.0-only; authored repository look',
      reuse: 'preset is SlotRequest.preset; assign a film slot and record recipe/defaults independently of colour' }), 'coefficient-json', ref.id);
    references.push({ id: ref.id, name: ref.name, target, coefficients, colourRecipe, fit, quantizedPayload: data.quantizedPayload });
  }

  const approved: Approved = JSON.parse(readFileSync(join(ROOT, APPROVED_SOURCE), 'utf8'));
  const saved = approved.fits.find(f => f.id === 'candidate');
  if (!saved) throw new Error('Archived approved Gold candidate fit is missing');
  const params: SlotParams = { ...saved.params, ck: saved.params.ck.map(c => Float64Array.from(c)) };
  const grid = new Float64Array(33 ** 3 * 3);
  let at = 0;
  for (let r = 0; r < 33; r++) for (let g = 0; g < 33; g++) for (let b = 0; b < 33; b++) {
    grid[at++] = r / 32; grid[at++] = g / 32; grid[at++] = b / 32;
  }
  const rendered = GR3X_CAMERA.slotApply(params, grid), preview = Buffer.alloc(rendered.length * 4);
  rendered.forEach((v,i) => {
    if (!Number.isFinite(v) || v < 0 || v > 1) throw new Error('Invalid approved Gold preview value');
    preview.writeFloatLE(v, i * 4);
  });
  requireHash(sha(preview), APPROVED_PREVIEW, 'accepted Gold candidate preview');
  requireHash(approved.preview_hashes['candidate.f32'], APPROVED_PREVIEW, 'archived Gold preview declaration');
  const data = quantizedData(quantizeSlot(params, engine.info.standardMatrixQ13));
  requireHash(data.quantizedPayload.sha256, APPROVED_PAYLOAD, 'directly quantized approved Gold payload');
  const id = 'gold-plus2-approved', name = 'Gold +2 EV (approved)', coefficients = `coefficients/${id}.json`;
  validateGr3xLookName(name);
  const softwarePreview = { sha256: sha(preview), bytes: preview.length, size: [33,33,33,3],
    encoding: 'little-endian float32, sRGB display 0..1, blue fastest',
    representation: 'unquantized saved GR3X_CAMERA.slotApply fit, distinct from target LUT and quantized firmware data' };
  const fit = { method: 'archived-parameters-direct-quantization', source: `${APPROVED_SOURCE}#fits[candidate].params`,
    archivedFitOptions: saved.options, refitted: false, archivedOwnTargetFullGridErrors: saved.full_grid };
  const targetSource = `tools/jpeg_experiments/exposure_print/${approved.targets.candidate.file}`;
  const targetBytes = readFileSync(join(ROOT, targetSource));
  requireHash(sha(targetBytes), approved.targets.candidate.sha256, 'archived Gold candidate target');
  add(coefficients, jsonBytes({ schema: 1, id, name, scope: SCOPE, fit, params: plainParams(params), ...data,
    standardMatrixQ13: engine.info.standardMatrixQ13, softwarePreview,
    accepted: { recordedBy: approved.accepted_by, recordedDate: approved.accepted_date },
    physicalModel: { controls: approved.controls, selectedParameters: approved.selected_physical_parameters[1] },
    targetSource: { repositoryPath: targetSource, sha256: sha(targetBytes) },
    recipe: null, texturePolicy: 'The accepted colour preview includes no grain, halation or MTF; choose and record test-build texture separately.',
    dataLicense: 'CC BY-SA 4.0; Andrea Volpato / spektrafilm data, locally derived fitted look',
    attributionSource: 'tools/jpeg_experiments/exposure_print/README.md#attribution-and-licensing',
    licenseFile: 'tools/jpeg_experiments/exposure_print/SPEKTRAFILM_LICENSE.txt',
    upstreamCommit: '3bb2c2d2801ff68b92019cf1dbcbb133d60832bc',
    reuse: 'preset is SlotRequest.preset; retain current Gold separately; do not import/refit the target or apply filmResponse again' }), 'coefficient-json', id);
  references.push({ id, name, coefficients, fit, softwarePreview, quantizedPayload: data.quantizedPayload,
    targetSource: { repositoryPath: targetSource, sha256: sha(targetBytes) } });

  const manifest = { schema: 1, kind: 'grmod-gr3-210-research-references', generatedAt: new Date().toISOString(), repository,
    firmware: { model: 'GR III', version: engine.info.version, sha256: sha(raw), bytes: raw.length },
    runtime: { node: process.version, platform: process.platform, arch: process.arch }, scope: SCOPE,
    artifactPaths: 'Relative to this manifest; repositoryPath/source paths are relative to repository root',
    capacity: { maxFilms: engine.info.features.maxFilms, note: 'The complete v3 pack fills 20 slots; approved Gold is a separate comparator, not a 21st slot or replacement of current Gold.' },
    references, artifacts };
  for (const source of repository.sources) {
    const current = sha(readFileSync(join(ROOT, source.path), 'utf8').replace(/\r\n/g, '\n'));
    if (current !== source.sha256Lf) throw new Error(`Source changed during reference generation: ${source.path}; retry with a new output directory`);
  }
  // Validate every pinned reference before creating anything. Exclusive creation also closes an existsSync race.
  mkdirSync(dirname(out), { recursive: true });
  mkdirSync(out);
  for (const output of outputs) {
    const path = join(out, output.path);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, output.bytes, { flag: 'wx' });
  }
  writeFileSync(join(out, 'manifest.json'), jsonBytes(manifest), { flag: 'wx' });
  console.log(JSON.stringify({ references: references.length, artifacts: artifacts.length, repositoryHead: repository.head,
    manifestSha256: sha(jsonBytes(manifest)), approvedGoldPayloadSha256: data.quantizedPayload.sha256 }, null, 2));
}

await main().catch(error => { console.error(error instanceof Error ? error.message : String(error)); process.exitCode = 1; });
