// SPDX-License-Identifier: GPL-2.0-only
// Host build evidence only. This exporter deliberately has no untrusted receipt importer.
import type { BuildOptions, CameraModel, FirmwareBuild, FirmwareInfo, RatioSpec, SlotRequest, SoftFocusRequest } from '@grmod/core';

export interface BuildArguments {
  requests: SlotRequest[];
  ratios: RatioSpec[];
  softFocus: SoftFocusRequest[];
  options: BuildOptions;
}
export interface ReceiptSource {
  model: CameraModel;
  filename: string;
  version: string;
  sha256: string;
  raw: Uint8Array;
}
export const RECEIPT_MAX_BYTES = 256 * 1024 * 1024 - 1;
const fail = (message: string): never => { throw new Error(`Build receipt: ${message}`); };
const numericTypes = new Set(['Int8Array', 'Int16Array', 'Uint16Array', 'Int32Array', 'Uint32Array', 'Float32Array', 'Float64Array']);
type NumericView = Int8Array | Int16Array | Uint16Array | Int32Array | Uint32Array | Float32Array | Float64Array;

export function supportsBuildReceipt(info: FirmwareInfo | undefined, model: CameraModel): boolean {
  return !!info && (model === 'GR3' || model === 'GR3_HDF') && info.models.includes(model) &&
    info.family === 'gr3x' && info.version === '2.10' && info.filename === 'fwdc239b.bin' && !info.bridge;
}

function copy(value: unknown, seen = new Set<object>(), depth = 0): any {
  if (depth > 64) fail('unsupported nesting');
  if (value === null || value === undefined || typeof value === 'string' || typeof value === 'boolean') return value;
  if (typeof value === 'number') return Number.isFinite(value) ? value : fail('unsupported non-finite number');
  if (typeof value !== 'object') return fail('unsupported value');
  if (seen.has(value)) fail('unsupported cyclic value');
  if (Object.getOwnPropertySymbols(value).length) fail('unsupported symbol key');
  if (ArrayBuffer.isView(value) && Object.getOwnPropertyNames(value).length !== (value as NumericView).length) fail('unsupported typed-array property');
  if (value instanceof Uint8Array || value instanceof Uint8ClampedArray) return value.slice();
  if (ArrayBuffer.isView(value) && numericTypes.has(value.constructor.name)) {
    const view = value as NumericView;
    if (!Array.from(view).every(Number.isFinite)) fail('unsupported non-finite typed value');
    return view.slice();
  }
  if (!Array.isArray(value) && Object.getPrototypeOf(value) !== Object.prototype && Object.getPrototypeOf(value) !== null) fail('unsupported object');
  seen.add(value);
  try {
    if (Array.isArray(value)) {
      if (Object.keys(value).length !== value.length || Object.getOwnPropertyNames(value).length !== value.length + 1) fail('unsupported sparse or extended array');
      return Array.from({ length: value.length }, (_, i) => {
        const d = Object.getOwnPropertyDescriptor(value, String(i));
        if (!d || !('value' in d)) return fail('unsupported array accessor');
        return copy(d.value, seen, depth + 1);
      });
    }
    const result: Record<string, unknown> = {};
    for (const key of Object.getOwnPropertyNames(value)) {
      const d = Object.getOwnPropertyDescriptor(value, key)!;
      if (!d.enumerable || !('value' in d)) fail('unsupported object property');
      Object.defineProperty(result, key, { value: copy(d.value, seen, depth + 1), enumerable: true, writable: true, configurable: true });
    }
    return result;
  } finally { seen.delete(value); }
}
function fields(value: any, allowed: string[], name: string): void {
  if (!value || typeof value !== 'object' || Array.isArray(value) || ArrayBuffer.isView(value)) fail(`unsupported ${name}`);
  if (Object.keys(value).some(k => !allowed.includes(k))) fail(`unsupported ${name} field`);
}
function validate(args: BuildArguments): void {
  fields(args, ['requests', 'ratios', 'softFocus', 'options'], 'arguments');
  if (![args.requests, args.ratios, args.softFocus].every(Array.isArray)) fail('unsupported argument arrays');
  const preset = (p: any) => fields(p, ['matrixQ13', 'curves', 'postQ9'], 'preset');
  for (const r of args.requests) {
    fields(r, ['slot', 'preset', 'icon', 'names', 'halation', 'defaults', 'grain', 'filmMtf'], 'slot');
    if (r.preset !== undefined) preset(r.preset);
    if (r.defaults !== undefined) {
      fields(r.defaults, ['saturation', 'hue', 'key', 'contrast', 'highlight', 'shadow', 'sharpness', 'shading', 'clarity', 'halation'], 'defaults');
      if (r.defaults.halation !== undefined) fields(r.defaults.halation, ['strength', 'white', 'gold', 'orange'], 'halation defaults');
    }
    if (r.grain !== undefined) fields(r.grain, ['amount', 'size'], 'grain');
  }
  args.ratios.forEach(r => fields(r, ['name', 'ratio'], 'ratio'));
  args.softFocus.forEach(r => fields(r, ['level', 'strength'], 'soft focus'));
  fields(args.options, ['textureGeometry', 'adjSoftFocus', 'dateStamp', 'monoUnlock', 'extraSlots', 'lookLayout', 'gr3Round', 'shutdownPictures', 'directFlash', 'guard', 'dateStampFixed', 'dateStampDiag', 'filmCount', 'tealHue', 'grainRow'], 'option');
  for (const r of args.options.extraSlots ?? []) fields(r, ['name', 'matrixQ13', 'curves', 'postQ9', 'hueQ10', 'icon', 'halation'], 'extra slot');
  for (const p of args.options.shutdownPictures ?? []) fields(p, ['id', 'name', 'jpeg'], 'picture');
  if (args.options.lookLayout !== undefined) fields(args.options.lookLayout, ['order', 'hidden'], 'look layout');
}

/** Synchronous private copies, taken before any confirmation/directory await. */
export function snapshotBuildArguments(args: BuildArguments): BuildArguments {
  const owned = copy(args) as BuildArguments;
  validate(owned);
  return owned;
}

async function digest(bytes: Uint8Array): Promise<string> {
  const hash = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes as unknown as BufferSource));
  return Array.from(hash, b => b.toString(16).padStart(2, '0')).join('');
}
function portable(value: any, maxBytes: number): any {
  if (value === undefined) return { type: 'undefined' };
  if (typeof value === 'number' && Object.is(value, -0)) return { type: 'negative-zero' };
  if (value === null || typeof value !== 'object') return value;
  if (value instanceof Uint8Array || value instanceof Uint8ClampedArray) {
    if (4 * Math.ceil(value.length / 3) > maxBytes) fail('encoded size is too large');
    let binary = '';
    for (let p = 0; p < value.length; p += 8192) binary += String.fromCharCode(...value.subarray(p, p + 8192));
    return { type: value instanceof Uint8ClampedArray ? 'Uint8ClampedArray' : 'Uint8Array', encoding: 'base64', length: value.length, data: btoa(binary) };
  }
  if (ArrayBuffer.isView(value)) return { type: value.constructor.name, values: Array.from(value as NumericView, v => portable(v, maxBytes)) };
  if (Array.isArray(value)) return { type: 'array', values: value.map(v => portable(v, maxBytes)) };
  return { type: 'object', entries: Object.keys(value).sort().map(key => [key, portable(value[key], maxBytes)]) };
}

/** Encode after building, before either export write. No original preset/official bytes are emitted. */
export async function encodeBuildReceipt(args: BuildArguments, source: ReceiptSource, built: FirmwareBuild, applicationVersion: string | null,
  maxBytes = RECEIPT_MAX_BYTES): Promise<{ bytes: Uint8Array; filename: string; sha256: string; firmware: Uint8Array }> {
  if (!Number.isSafeInteger(maxBytes) || maxBytes < 1 || maxBytes > RECEIPT_MAX_BYTES) fail('unsupported size limit');
  if ((source.model !== 'GR3' && source.model !== 'GR3_HDF') || source.filename !== 'fwdc239b.bin' || source.version !== '2.10') fail('unsupported source');
  const recipe = portable(snapshotBuildArguments(args), maxBytes);
  const summary = copy({ reportedSha256: built.sha256, decodedSha256: built.decodedSha256, checks: built.checks,
    changedFrames: built.changedFrames, changedBytes: built.changedBytes, ranges: built.ranges,
    ratios: built.ratios?.map(r => ({ id: r.id, name: r.name, ratio: r.ratio, actual: r.actual, sizes: r.sizes })) });
  if (!summary.checks || !Object.keys(summary.checks).length || !Object.values(summary.checks).every(v => v === true)) fail('build checks did not pass');
  const raw = source.raw.slice(), firmware = built.file.slice();
  const inputHash = await digest(raw);
  if (inputHash !== source.sha256) fail('input hash mismatch');
  const outputHash = await digest(firmware);
  if (outputHash !== built.sha256) fail('output hash mismatch');
  const recipeSha256 = await digest(new TextEncoder().encode(JSON.stringify(recipe)));
  const receipt = {
    format: 'grmod-build-receipt', schemaVersion: 1, requestCodecVersion: 1,
    applicationVersion, exactBuilderRevision: null, presetSourceTextIncluded: false, rebuildVerification: 'not-performed',
    input: { filename: source.filename, firmwareVersion: source.version, model: source.model, sha256: inputHash, bytes: raw.length },
    recipe, recipeSha256,
    output: { filename: source.filename, sha256: outputHash, bytes: firmware.length }, summary,
    claims: { hostBuildEvidenceOnly: true, signed: false, installationProven: false, photographProvenanceProven: false },
  };
  const bytes = new TextEncoder().encode(JSON.stringify(receipt, null, 2) + '\n');
  if (bytes.length > maxBytes) fail('encoded size is too large');
  return { bytes, filename: `fwdc239b.${outputHash}.grmod.json`, sha256: await digest(bytes), firmware };
}
