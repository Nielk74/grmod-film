import { describe, expect, it } from 'vitest';
import { createHash } from 'node:crypto';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { Engine } from '../src';
import { encodeBuildReceipt, snapshotBuildArguments, supportsBuildReceipt } from '../../ui/src/build-receipt';

const sha = (v: Uint8Array | string) => createHash('sha256').update(v).digest('hex');
const input = new Uint8Array([1, 2, 3]);
const file = new Uint8Array([9, 2]);
const source = () => ({ model: 'GR3_HDF' as const, filename: 'fwdc239b.bin', version: '2.10', sha256: sha(input), raw: input.slice() });
const built = () => ({ file: file.slice(), sha256: sha(file), decodedSha256: 'a'.repeat(64), checks: { integrity: true }, changedFrames: [1], changedBytes: 2, ranges: [{ start: 4, end: 6 }], ratios: [], features: { factory: new Uint8Array([77]) } } as any);
const args = () => ({ requests: [{ slot: 'CY' as const, preset: { matrixQ13: new Int16Array([999, -2, 8192, 2, 777]).subarray(1, 4), curves: [new Uint16Array([0, 16383]), new Uint16Array([1, 2]), new Uint16Array([3, 4])] as [Uint16Array, Uint16Array, Uint16Array] }, icon: new Uint8Array([88, 0, 255, 99]).subarray(1, 3) }], ratios: [{ name: 'Wide', ratio: '4:3' }], softFocus: [], options: { dateStamp: false, filmCount: 1, textureGeometry: 'sensor' as const } });

// Deliberately independent of the production exporter. It decodes this pinned format for tests,
// not a product importer of untrusted receipts.
function decode(value: any): any {
  if (value === null || typeof value !== 'object') return value;
  if (value.type === 'object') return Object.fromEntries(value.entries.map(([k, v]: any[]) => [k, decode(v)]));
  if (value.type === 'array') return value.values.map(decode);
  if (value.type === 'undefined') return undefined;
  if (value.type === 'negative-zero') return -0;
  const constructors: Record<string, any> = { Uint8Array, Uint8ClampedArray, Int8Array, Uint16Array, Int16Array, Uint32Array, Int32Array, Float32Array, Float64Array };
  const C = constructors[value.type];
  if (!C) throw new Error('Unsupported test codec tag');
  return value.encoding === 'base64' ? new C(Buffer.from(value.data, 'base64')) : new C(value.values.map(decode));
}

describe('portable build receipt', () => {
  it('gates the exact official GR III 2.10 profile and model only', () => {
    const info: any = { family: 'gr3x', version: '2.10', filename: 'fwdc239b.bin', models: ['GR3', 'GR3_HDF'], bridge: false };
    expect(supportsBuildReceipt(info, 'GR3')).toBe(true);
    expect(supportsBuildReceipt(info, 'GR3_HDF')).toBe(true);
    for (const patch of [{ family: 'gr4' }, { version: '1.60' }, { filename: 'fwdc243b.bin' }, { bridge: true }, { models: ['GR3X'] }]) expect(supportsBuildReceipt({ ...info, ...patch }, 'GR3')).toBe(false);
    expect(supportsBuildReceipt(info, 'GR3X')).toBe(false);
  });
  it('owns coefficients, byte views and nested options before asynchronous mutation', () => {
    const original = args(), copy = snapshotBuildArguments(original);
    original.requests[0].preset.matrixQ13[0] = 999; original.requests[0].icon.fill(66);
    original.ratios[0].name = 'Later'; original.options.dateStamp = true;
    expect(Array.from(copy.requests[0].preset!.matrixQ13)).toEqual([-2, 8192, 2]);
    expect(Array.from(copy.requests[0].icon!)).toEqual([0, 255]);
    expect(copy.ratios[0].name).toBe('Wide'); expect(copy.options.dateStamp).toBe(false);
    expect(copy.options).not.toHaveProperty('guard');
  });
  it('encodes known integer/byte values independently and produces a deterministic recipe digest', async () => {
    const a = snapshotBuildArguments(args());
    const encoded = await encodeBuildReceipt(a, source(), built(), '0.8.6');
    const receipt = JSON.parse(new TextDecoder().decode(encoded.bytes));
    expect(receipt).toMatchObject({ format: 'grmod-build-receipt', schemaVersion: 1, requestCodecVersion: 1, applicationVersion: '0.8.6', exactBuilderRevision: null, presetSourceTextIncluded: false, rebuildVerification: 'not-performed' });
    const decoded = decode(receipt.recipe);
    expect([...decoded.requests[0].preset.matrixQ13]).toEqual([-2, 8192, 2]);
    expect([...decoded.requests[0].icon]).toEqual([0, 255]);
    expect(decoded.options).toEqual(a.options); expect(decoded.options).not.toHaveProperty('guard');
    expect(receipt.recipeSha256).toBe(sha(JSON.stringify(receipt.recipe)));
    expect(receipt.input.sha256).toBe(sha(input)); expect(receipt.output.sha256).toBe(sha(file));
    expect(encoded.filename).toBe(`fwdc239b.${sha(file)}.grmod.json`);
    expect(receipt.summary).not.toHaveProperty('features'); expect(JSON.stringify(receipt)).not.toContain('factory');
    const reversed: any = { options: a.options, softFocus: a.softFocus, ratios: a.ratios, requests: a.requests };
    expect(JSON.parse(new TextDecoder().decode((await encodeBuildReceipt(reversed, source(), built(), 'other')).bytes)).recipeSha256).toBe(receipt.recipeSha256);
  });
  it('cross-checks the source, output and successful build checks before export', async () => {
    const a = snapshotBuildArguments(args());
    await expect(encodeBuildReceipt(a, { ...source(), sha256: '0'.repeat(64) }, built(), null)).rejects.toThrow(/input/i);
    await expect(encodeBuildReceipt(a, source(), { ...built(), sha256: '0'.repeat(64) }, null)).rejects.toThrow(/output/i);
    await expect(encodeBuildReceipt(a, source(), { ...built(), checks: { integrity: false } }, null)).rejects.toThrow(/check/i);
    await expect(encodeBuildReceipt(a, source(), { ...built(), checks: {} }, null)).rejects.toThrow(/check/i);
  });
  it('preserves explicit undefined, empty arrays and signed zero without a product importer', async () => {
    const original: any = args(); original.options.guard = undefined;
    original.requests[0].preset.matrixQ13 = new Float64Array([-0, 8192, -2]);
    const encoded = await encodeBuildReceipt(snapshotBuildArguments(original), source(), built(), null);
    const decoded = decode(JSON.parse(new TextDecoder().decode(encoded.bytes)).recipe);
    expect(Object.hasOwn(decoded.options, 'guard')).toBe(true); expect(decoded.options.guard).toBeUndefined();
    expect(Object.is(decoded.requests[0].preset.matrixQ13[0], -0)).toBe(true); expect(decoded.softFocus).toEqual([]);
  });
  it('rejects unknown schema fields and unsupported values instead of dropping them', () => {
    for (const value of [NaN, Infinity, 1n, () => 1, new Date()]) expect(() => snapshotBuildArguments({ ...args(), options: { dateStamp: value } } as any)).toThrow();
    expect(() => snapshotBuildArguments({ ...args(), options: { futureOption: true } } as any)).toThrow(/unsupported/i);
    const cycle: any = args(); cycle.requests[0].defaults = cycle;
    expect(() => snapshotBuildArguments(cycle)).toThrow();
    const getter: any = args(); Object.defineProperty(getter.options, 'guard', { enumerable: true, get: () => false });
    expect(() => snapshotBuildArguments(getter)).toThrow();
    const symbol: any = args(); symbol.requests[0].icon[Symbol('hidden')] = 1;
    expect(() => snapshotBuildArguments(symbol)).toThrow();
    const extended: any = args(); Object.defineProperty(extended.ratios, 'hidden', { value: 'do not drop' });
    expect(() => snapshotBuildArguments(extended)).toThrow();
  });
  it('rejects an oversized encoded receipt before any exporter receives it', async () => {
    await expect(encodeBuildReceipt(snapshotBuildArguments(args()), source(), built(), null, 128)).rejects.toThrow(/size|large/i);
  });
});

const official = process.env.GRMOD_GR3_FIRMWARE;
it.skipIf(process.env.GRMOD_RECEIPT_REPLAY !== '1' || !official || !existsSync(official))('replays one official GR III 2.10 receipt through an independent JSON decoder', async () => {
  const raw = new Uint8Array(readFileSync(official!));
  const engine = await Engine.open(raw);
  const curves = Array.from({ length: 3 }, () => Uint16Array.from({ length: 256 }, (_, i) => Math.round(i * 16383 / 255))) as [Uint16Array, Uint16Array, Uint16Array];
  const submitted = snapshotBuildArguments({ requests: [{ slot: 'CY', names: { en: 'Receipt Control' }, preset: { matrixQ13: Int16Array.from(engine.info.standardMatrixQ13), curves }, icon: engine.info.tiles.film.slice(), defaults: { sharpness: 0 }, grain: { amount: 1, size: 'small' }, filmMtf: true }], ratios: [{ name: '4:3', ratio: '4:3' }], softFocus: [], options: { adjSoftFocus: false, dateStamp: false, monoUnlock: false, filmCount: 1, tealHue: true, grainRow: true, textureGeometry: 'sensor' } });
  const first = await engine.buildFirmware(submitted.requests, submitted.ratios, submitted.softFocus, submitted.options);
  const encoded = await encodeBuildReceipt(submitted, { model: 'GR3_HDF', filename: engine.info.filename, version: engine.info.version, sha256: engine.info.sha256, raw }, first, 'test-control');
  const receipt = JSON.parse(new TextDecoder().decode(encoded.bytes));
  const independent = decode(receipt.recipe);
  const fresh = await Engine.open(raw);
  const replay = await fresh.buildFirmware(independent.requests, independent.ratios, independent.softFocus, independent.options);
  expect(sha(replay.file)).toBe(sha(first.file)); expect(replay.sha256).toBe(receipt.output.sha256);
  expect(receipt.rebuildVerification).toBe('not-performed');
  if (process.env.GRMOD_RECEIPT_EVIDENCE === '1') {
    const out = new URL('../../research/gr3-210/wp12-build-receipt-implementation/', import.meta.url);
    writeFileSync(fileURLToPath(new URL('control-receipt.grmod.json', out)), encoded.bytes);
    writeFileSync(fileURLToPath(new URL('replay-control.json', out)), JSON.stringify({ inputSha256: sha(raw), outputSha256: sha(first.file), replaySha256: sha(replay.file), receiptSha256: sha(encoded.bytes), bytes: first.file.length, independentDecoder: 'test-only decoder; no production importer', checks: replay.checks }, null, 2) + '\n', 'utf8');
  }
}, 300000);
