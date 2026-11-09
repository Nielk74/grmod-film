// SPDX-License-Identifier: GPL-2.0-only
// Exercise the real UI state/actions with an in-memory host. No camera or disk writes.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createHash } from 'node:crypto';
import { LANGS } from '../src/fw/names';

const mocks = vi.hoisted(() => ({
  engine: { open: vi.fn(), reset: vi.fn(), build: vi.fn(), ratio: vi.fn(), bridge: vi.fn(), script: vi.fn(), heartbeat: vi.fn() },
  host: {
    available: false, info: { token: 'test', kind: 'test' },
    storeGet: vi.fn(), storeSet: vi.fn(), pickDirectory: vi.fn(), write: vi.fn(),
    volumes: vi.fn(), sidecar: vi.fn(), join: (...p) => p.join('/'),
  },
}));
vi.mock('../../ui/src/engine', () => ({ engine: mocks.engine, EngineError: class extends Error {} }));
vi.mock('../../ui/src/host', () => ({ host: mocks.host, HostError: class extends Error {}, sha256Hex: async data => createHash('sha256').update(data).digest('hex') }));
vi.mock('../../ui/src/pixels', () => ({ ensureIconFont: vi.fn(), previewJpeg: vi.fn(() => ({ width: 6000, height: 4000, orientation: 6 })), loadBitmap: vi.fn(async () => ({ close: vi.fn() })), workingCopy: vi.fn(async () => ({ blob: new Blob([new Uint8Array([1])]) })) }));
vi.mock('../../ui/src/preview', () => ({ decodePreview: vi.fn(async () => ({ width: 2400, height: 1600 })) }));

const info = () => ({
  sha256: createHash('sha256').update(new Uint8Array([1])).digest('hex'),
  family: 'gr3x', version: '1.60', filename: 'fwdc243b.bin', models: ['GR3X_HDF'],
  capabilities: { build: true, presets: false, wallpaper: false, factoryEntry: false, bridge: false },
  features: { softFocus: 'clarity', dateStamp: false, monoUnlock: false },
  slots: [], factoryRatios: ['3:2', '1:1'], factoryEntry: { files: [] },
});
let store;
beforeEach(async () => {
  vi.resetModules(); vi.clearAllMocks(); vi.useFakeTimers();
  mocks.host.available = false;
  mocks.engine.open.mockReset().mockResolvedValue(info());
  mocks.engine.reset.mockResolvedValue(true);
  mocks.engine.ratio.mockImplementation(async ratio => ({ label: ratio, actual: ratio, sizes: [[6000, 4000]] }));
  mocks.engine.build.mockResolvedValue({ file: new Uint8Array([9, 2]), sha256: createHash('sha256').update(new Uint8Array([9, 2])).digest('hex'), decodedSha256: 'a'.repeat(64), checks: { integrity: true }, changedFrames: [], changedBytes: 0, ranges: [], ratios: [], features: {} });
  mocks.host.storeSet.mockResolvedValue();
  mocks.host.storeGet.mockReset().mockResolvedValue(null);
  mocks.host.pickDirectory.mockReset().mockResolvedValue('/chosen');
  mocks.host.write.mockImplementation(async (_p, data) => ({ size: data.length, sha256: createHash('sha256').update(data).digest('hex') }));
  mocks.host.volumes.mockResolvedValue([]);
  vi.stubGlobal('document', { hidden: true });
  store = await import('../../ui/src/store');
});
afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe('GR III folder build receipts', () => {
  const hash = data => createHash('sha256').update(data).digest('hex');
  async function prepare() {
    const current = { ...info(), version: '2.10', filename: 'fwdc239b.bin', models: ['GR3_HDF'], capabilities: { ...info().capabilities, presets: true }, features: { maxFilms: 20, softFocus: 'adj', dateStamp: true }, slots: ['CY', 'CG'].map((id, i) => ({ id, defaultName: `Film ${i + 1}`, names: Object.fromEntries(LANGS.map(l => [l, { text: `Film ${i + 1}`, capacity: 24 }])) })) };
    const raw = new Uint8Array([1]);
    mocks.engine.open.mockResolvedValue(current);
    await store.adoptFirmware('fwdc239b.bin', '2.10', raw);
    store.setLang('en'); store.setFilmCount(2); store.addRatio('4:3'); store.setTextureGeometry('sensor');
    const preset = { matrixQ13: new Int16Array([-2, 8192, 2]), curves: [new Uint16Array([0, 16383]), new Uint16Array([1, 2]), new Uint16Array([3, 4])] };
    store.getState().slots.CY.preset = { kind: 'cube', fileName: 'private-source.cube', text: 'PRIVATE SOURCE TEXT', result: preset };
    store.getState().slots.CY.icon = { mode: 'image', pixels: new Uint8Array([99, 0, 255, 88]).subarray(1, 3) };
    await vi.advanceTimersByTimeAsync(1);
    store.getState().toasts = [];
    return { current, raw, preset, icon: store.getState().slots.CY.icon.pixels };
  }
  it('exports an output-specific receipt from the same owned arguments despite picker-time mutation', async () => {
    const original = await prepare(); let choose;
    mocks.host.pickDirectory.mockImplementationOnce(() => new Promise(resolve => { choose = resolve; }));
    const exporting = store.outputFirmware({ kind: 'folder' });
    original.preset.matrixQ13[0] = 444; original.icon.fill(55); original.raw[0] = 77;
    original.current.filename = 'later.bin'; store.setTextureGeometry('output');
    choose('/chosen'); await exporting;
    const submitted = mocks.engine.build.mock.calls.at(-1);
    expect([...submitted[0][0].preset.matrixQ13]).toEqual([-2, 8192, 2]); expect([...submitted[0][0].icon]).toEqual([0, 255]);
    expect(submitted[3].textureGeometry).toBe('sensor');
    const writes = mocks.host.write.mock.calls; expect(writes).toHaveLength(2);
    expect(writes[0][0]).toBe('/chosen/fwdc239b.bin');
    expect(writes[1][0]).toBe(`/chosen/fwdc239b.${hash(new Uint8Array([9, 2]))}.grmod.json`);
    const receipt = JSON.parse(new TextDecoder().decode(writes[1][1]));
    expect(receipt.input.sha256).toBe(hash(new Uint8Array([1]))); expect(receipt.input.filename).toBe('fwdc239b.bin');
    expect(receipt.output.sha256).toBe(hash(writes[0][1])); expect(receipt.exactBuilderRevision).toBeNull();
    expect(new TextDecoder().decode(writes[1][1])).not.toContain('PRIVATE SOURCE TEXT');
    expect(store.getState().toasts.at(-1).text).toMatch(/firmware.*recipe/i);
  });
  it.each(['reject', 'size', 'hash'])('reports a verified firmware and unverified receipt after a second-write %s', async mode => {
    await prepare(); let writes = 0;
    mocks.host.write.mockImplementation(async (_path, data) => {
      if (++writes === 2) { if (mode === 'reject') throw new Error('write rejected'); return { size: mode === 'size' ? 0 : data.length, sha256: mode === 'hash' ? 'wrong' : hash(data) }; }
      return { size: data.length, sha256: hash(data) };
    });
    await store.outputFirmware({ kind: 'folder' });
    expect(mocks.host.write).toHaveBeenCalledTimes(2); expect(store.getState().busy).toBeUndefined();
    expect(store.getState().toasts.at(-1)).toMatchObject({ kind: 'error' });
    expect(store.getState().toasts.at(-1).text).toMatch(/firmware.*verified.*recipe.*not verified/i);
    expect(store.getState().toasts.some(t => t.kind === 'ok')).toBe(false);
  });
  it.each(['reject', 'size', 'hash'])('does not claim a complete pair after a first-write %s', async mode => {
    await prepare();
    mocks.host.write.mockImplementation(async (_path, data) => { if (mode === 'reject') throw new Error('write rejected'); return { size: mode === 'size' ? 0 : data.length, sha256: mode === 'hash' ? 'wrong' : hash(data) }; });
    await store.outputFirmware({ kind: 'folder' });
    expect(mocks.host.write).toHaveBeenCalledTimes(1);
    expect(store.getState().toasts.at(-1).text).toMatch(/not completely verified/i);
  });
  it('aborts a replaced source and serializes two already-open folder selections', async () => {
    await prepare(); const choices = [];
    mocks.host.pickDirectory.mockImplementation(() => new Promise(resolve => choices.push(resolve)));
    const first = store.outputFirmware({ kind: 'folder' }), second = store.outputFirmware({ kind: 'folder' });
    let finish; mocks.engine.build.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    choices[0]('/chosen'); await Promise.resolve(); choices[1]('/chosen'); await second;
    expect(mocks.engine.build).toHaveBeenCalledTimes(1);
    finish({ file: new Uint8Array([9, 2]), sha256: hash(new Uint8Array([9, 2])), decodedSha256: 'a'.repeat(64), checks: { integrity: true }, changedFrames: [], changedBytes: 0, ranges: [], ratios: [] }); await first;
    expect(mocks.host.write).toHaveBeenCalledTimes(2);
    mocks.host.write.mockClear();
    const replaced = store.outputFirmware({ kind: 'folder' }); store.getState().info = { ...store.getState().info }; choices[2]('/chosen'); await replaced;
    expect(mocks.host.write).not.toHaveBeenCalled();
  });
  it('keeps stock export as the single original firmware file', async () => {
    const { raw } = await prepare(); const output = store.outputFirmware({ kind: 'folder' }, true);
    store.answerConfirm(true); await output;
    expect(mocks.engine.build).not.toHaveBeenCalled(); expect(mocks.host.write.mock.calls).toEqual([['/chosen/fwdc239b.bin', raw]]);
  });
  it('keeps the GR III card plan as a single firmware write without a receipt or folder picker', async () => {
    await prepare();
    store.getState().volumes = [{ id: 'memory-card', root: '/memory-card' }]; store.getState().volumeId = 'memory-card';
    mocks.host.list = vi.fn(async () => []);
    const output = store.outputFirmware({ kind: 'card' }); store.answerConfirm(true); await output;
    expect(mocks.host.pickDirectory).not.toHaveBeenCalled();
    expect(mocks.host.write.mock.calls).toEqual([['/memory-card/fwdc239b.bin', new Uint8Array([9, 2])]]);
  });
});

describe('desktop film detail state', () => {
  const modern = () => ({ ...info(), capabilities: { ...info().capabilities, presets: true }, features: { maxFilms: 20, softFocus: 'adj', dateStamp: true },
    slots: ['CY', 'CG'].map((id, i) => ({ id, defaultName: `Film ${i + 1}`, names: Object.fromEntries(LANGS.map(l => [l, { text: `Film ${i + 1}`, capacity: 24 }])) })) });
  it('sends an MTF-only request and explicit geometry without altering camera defaults', async () => {
    mocks.engine.open.mockResolvedValue(modern());
    await store.adoptFirmware('fwdc243b.bin', '1.60', new Uint8Array([1]));
    store.setFilmCount(2); store.addRatio('4:3');
    store.setRecipe('CY', { filmMtf: true, sharpness: -1, clarity: 2 });
    store.setTextureGeometry('sensor');
    await vi.advanceTimersByTimeAsync(1); await store.outputFirmware({ kind: 'folder' });
    expect(mocks.engine.build.mock.calls.at(-1)[0]).toEqual([{ slot: 'CY', filmMtf: true, defaults: { sharpness: -1, clarity: 2 } }]);
    expect(mocks.engine.build.mock.calls.at(-1)[3].textureGeometry).toBe('sensor');
    store.setRecipe('CY', { filmMtf: undefined }); store.setTextureGeometry(undefined);
    expect(store.pendingChanges()[0].request).not.toHaveProperty('filmMtf');
    expect(store.getState().slots.CY.recipe).toMatchObject({ sharpness: -1, clarity: 2 });
  });
  it('restores only literal true and keeps policy and recipe in the GR III project', async () => {
    mocks.host.available = true;
    const encode = v => new TextEncoder().encode(JSON.stringify(v));
    const files = new Map([['project.json', encode({ v: 1, model: 'GR3X_HDF' })], ['project-gr3.json', encode({ v: 1, filmCount: 2, textureGeometry: 'output', slots: {
      CY: { recipe: { filmMtf: true, sharpness: 1 } }, CG: { recipe: { filmMtf: 'true', clarity: -1 } },
    } })]]);
    mocks.host.storeGet.mockImplementation(async k => files.get(k) ?? null);
    mocks.host.storeSet.mockImplementation(async (k, v) => files.set(k, typeof v === 'string' ? new TextEncoder().encode(v) : v));
    await store.init();
    expect(store.getState().textureGeometry).toBe('output');
    expect(store.recipeOf('CY')).toMatchObject({ filmMtf: true, sharpness: 1 });
    expect(store.recipeOf('CG')).not.toHaveProperty('filmMtf');
    store.setRecipe('CY', { filmMtf: undefined }); store.setTextureGeometry(undefined);
    await vi.advanceTimersByTimeAsync(401);
    const saved = JSON.parse(new TextDecoder().decode(files.get('project-gr3.json')));
    expect(saved).not.toHaveProperty('textureGeometry'); expect(saved.slots.CY.recipe).not.toHaveProperty('filmMtf');
    store.setTextureGeometry('sensor'); store.setModel('HDF');
    expect(store.getState().textureGeometry).toBeUndefined();
  });
  it('describes inspected detail flags without local build history', () => {
    const lines = store.describeCopy({ kind: 'modified', slots: [{ id: 'CY', names: { 'zh-CN': 'Film' }, filmMtf: true }], ratios: [], textureGeometry: 'sensor' });
    expect(lines.join(' ')).toMatch(/MTF/); expect(lines).toHaveLength(2);
  });
  it('keeps the original only for this source and session, without promoting the persisted proxy', async () => {
    mocks.host.available = true;
    const original = new Blob([new Uint8Array([1,2,3])]);
    await store.loadPreviewFile(original);
    expect(store.previewOriginal()).toMatchObject({ blob: original, width: 6000, height: 4000, orientation: 6 });
    expect(store.getState().previewMain).toBe(false);
    store.setPreviewMain(true); expect(store.getState().previewMain).toBe(true);
    expect(mocks.host.storeSet.mock.calls.find(([k]) => k === 'preview.jpg')[1]).toEqual(new Uint8Array([1]));
    store.setModel('GR3X_HDF');
    expect(store.previewOriginal()).toBeNull(); expect(store.getState().previewMain).toBe(false);
    vi.resetModules(); const restored = await import('../../ui/src/store'); await restored.init();
    expect(restored.previewOriginal()).toBeNull(); expect(restored.getState().previewMain).toBe(false);
  });
  it('snapshots texture policy before an asynchronous folder selection', async () => {
    mocks.engine.open.mockResolvedValue(modern());
    await store.adoptFirmware('fwdc243b.bin', '1.60', new Uint8Array([1]));
    store.setFilmCount(2); store.addRatio('4:3'); store.setTextureGeometry('sensor');
    await vi.advanceTimersByTimeAsync(1);
    let choose; mocks.host.pickDirectory.mockImplementation(() => new Promise(resolve => { choose = resolve; }));
    const output = store.outputFirmware({ kind: 'folder' });
    store.setTextureGeometry('output'); choose('/chosen'); await output;
    expect(mocks.engine.build.mock.calls.at(-1)[3].textureGeometry).toBe('sensor');
  });
});

describe('GR IIIx UI family isolation', () => {
  it('selects IIIx when opening its firmware; the page and the (empty) ratio list stay as they are', async () => {
    expect(await store.adoptFirmware('arbitrary.bin', '1.60', new Uint8Array([1]))).toBe(true);
    expect(store.getState()).toMatchObject({ model: 'GR3X_HDF', page: 'ic', fwName: 'fwdc243b.bin', ratios: [] });
  });
  it('adds no ratios by default and asks for one before building', async () => {
    await store.adoptFirmware('fwdc243b.bin', '1.60', new Uint8Array([1]));
    await vi.advanceTimersByTimeAsync(1);
    store.setSoft(true);
    await store.outputFirmware({ kind: 'folder' });
    expect(mocks.engine.build).not.toHaveBeenCalled();
    expect(mocks.host.write).not.toHaveBeenCalled();
  });
  it('blocks all unported output actions before a destination can be selected', async () => {
    await store.adoptFirmware('fwdc243b.bin', '1.60', new Uint8Array([1]));
    await store.outputBridge({ kind: 'folder' });
    expect(store.outputEntry).toBeUndefined();
    expect(store.outputWallpaper).toBeUndefined();
    store.setBridgeOpen(true);
    expect(store.getState().bridgeOpen).toBe(false);
    for (const fn of [mocks.host.pickDirectory, mocks.host.write, mocks.engine.build, mocks.engine.bridge, mocks.engine.script]) expect(fn).not.toHaveBeenCalled();
  });
  it('exports exactly the ratios added through the real build action', async () => {
    await store.adoptFirmware('fwdc243b.bin', '1.60', new Uint8Array([1]));
    for (const r of ['4:3', '16:9', '65:24', '17:6', '3:4', '7:6', '5:4']) store.addRatio(r);
    await vi.advanceTimersByTimeAsync(1);
    expect(store.getState().ratios.map(r => r.ratio)).toEqual(['4:3', '16:9', '65:24', '17:6', '3:4', '7:6', '5:4']);
    await store.outputFirmware({ kind: 'folder' });
    expect(mocks.engine.build).toHaveBeenCalledWith([], ['4:3', '16:9', '65:24', '17:6', '3:4', '7:6', '5:4'].map(ratio => ({ ratio, name: ratio })), [], { adjSoftFocus: false, dateStamp: false, monoUnlock: false });
    expect(mocks.host.write).toHaveBeenCalledWith('/chosen/fwdc243b.bin', new Uint8Array([9, 2]));
  });
  it('exports IIIx negative-clarity soft focus while preserving the ADJ function list', async () => {
    await store.adoptFirmware('fwdc243b.bin', '1.60', new Uint8Array([1]));
    store.addRatio('4:3');
    store.setSoft(true);
    store.setDateStamp(true); store.setMonoUnlock(true);
    await vi.advanceTimersByTimeAsync(1);
    expect(store.getState()).toMatchObject({ soft: true, dateStamp: false, monoUnlock: false });
    await store.outputFirmware({ kind: 'folder' });
    expect(mocks.engine.build.mock.calls[0].slice(2)).toEqual([
      [{ level: -1, strength: 'weak' }, { level: -2, strength: 'medium' }, { level: -3, strength: 'strong' }],
      { adjSoftFocus: false, dateStamp: false, monoUnlock: false },
    ]);
  });
  it('retains the selected IIIx page and soft-focus choice when reopening its firmware', async () => {
    await store.adoptFirmware('fwdc243b.bin', '1.60', new Uint8Array([1]));
    store.setPage('script'); store.setSoft(true);
    await store.adoptFirmware('fwdc243b.bin', '1.60', new Uint8Array([1]));
    expect(store.getState()).toMatchObject({ page: 'script', soft: true });
  });
  it('exports T5 film data, uniform names and replicas together with SF1 and the nine-ratio recipe', async () => {
    const current = info();
    current.capabilities.presets = true; current.features.monoUnlock = true;
    current.allowed = Object.fromEntries(LANGS.map(l => [l, ' Film1WarmDemo']));
    current.slots = ['CY','CG'].map((id, i) => ({ id, defaultName: `Film ${i+1}`,
      names: Object.fromEntries(LANGS.map(l => [l, { text: `Film ${i+1}`, capacity: 24 }])) }));
    mocks.engine.open.mockResolvedValue(current);
    await store.adoptFirmware('fwdc243b.bin', '1.60', new Uint8Array([1]));
    store.setName('CY', 'zh-CN', 'Warm Demo');
    const preset = { matrixQ13: new Int16Array(9), curves: [new Uint16Array(256),new Uint16Array(256),new Uint16Array(256)] };
    store.getState().slots.CY.preset = { fileName: 'demo.cube', kind: 'cube', text: '', result: preset };
    store.setSoft(true); store.setMonoUnlock(true);
    for (const r of ['4:3', '16:9', '65:24', '17:6', '3:4', '7:6', '5:4']) store.addRatio(r);
    await store.adoptFirmware('fwdc243b.bin', '1.60', new Uint8Array([1]));
    expect(store.getState()).toMatchObject({ soft: true, monoUnlock: true });
    await vi.advanceTimersByTimeAsync(1);
    await store.outputFirmware({ kind: 'folder' });
    const [requests, ratios, soft, options] = mocks.engine.build.mock.calls.at(-1);
    expect(requests).toHaveLength(1);
    expect(requests[0]).toMatchObject({ slot: 'CY', preset });
    expect(new Set(Object.values(requests[0].names))).toEqual(new Set(['Warm Demo']));
    expect(ratios).toHaveLength(7); expect(soft.map(s => s.level)).toEqual([-1,-2,-3]);
    expect(options).toEqual({ adjSoftFocus: false, dateStamp: false, monoUnlock: true });
    expect(mocks.host.write).toHaveBeenCalledWith('/chosen/fwdc243b.bin', new Uint8Array([9,2]));
  });
  it('exports the ninth film and suppresses retired replicas with the T6 capabilities', async () => {
    const current = info(); current.capabilities.presets = true;
    const ids = ['CY','CG','F3','F4','F5','F6','F7','F8','F9'];
    current.allowed = Object.fromEntries(LANGS.map(l => [l, 'Film 123456789CineStl80T']));
    current.slots = ids.map((id, i) => ({ id, defaultName: `Film ${i+1}`,
      names: Object.fromEntries(LANGS.map(l => [l, { text: `Film ${i+1}`, capacity: 24 }])) }));
    mocks.engine.open.mockResolvedValue(current);
    await store.adoptFirmware('fwdc243b.bin', '1.60', new Uint8Array([1]));
    store.setName('F9', 'zh-CN', 'CineStill 800T'); store.setMonoUnlock(true); store.addRatio('4:3');
    const preset = { matrixQ13: new Int16Array(9), curves: [new Uint16Array(256),new Uint16Array(256),new Uint16Array(256)] };
    store.getState().slots.F9.preset = { fileName: 'CineStill-800T.cube', kind: 'cube', text: '', result: preset };
    store.setActiveSlot('F9');
    await vi.advanceTimersByTimeAsync(1);
    await store.outputFirmware({ kind: 'folder' });
    expect(mocks.engine.build.mock.calls.at(-1)[0][0]).toMatchObject({ slot: 'F9', preset });
    expect(mocks.engine.build.mock.calls.at(-1)[3].monoUnlock).toBe(false);
    store.setModel('HDF');
    expect(store.getState().activeSlot).toBe('CY');
    expect(store.getState().slots.F9.preset).toBeUndefined();
  });
  it('keeps each camera family’s own work apart when switching or opening a different model', async () => {
    store.getState().slots.CY = { ...store.getState().slots.CY, names: { en: 'GR IV film' }, preset: { result: {} } };
    store.setModel('GR3X_HDF');
    expect(store.getState().slots.CY.preset).toBeUndefined();
    expect(store.getState().slots.CY.names).toEqual({});
    store.getState().slots.CY = { ...store.getState().slots.CY, names: { en: 'GR III film' } };
    store.setModel('HDF');
    expect(store.getState().slots.CY.names).toEqual({ en: 'GR IV film' });
    store.getState().slots.CY.preset = { result: {} };
    await store.adoptFirmware('fwdc243b.bin', '1.60', new Uint8Array([1]));
    expect(store.getState().slots.CY.preset).toBeUndefined();
    expect(store.getState().slots.CY.names).toEqual({ en: 'GR III film' });
  });
  it('saves GR IV and GR III work in their own files and brings both back after a restart', async () => {
    await store.init();
    mocks.host.available = true;
    const files = new Map();
    mocks.host.storeSet.mockImplementation(async (key, value) => { files.set(key, typeof value === 'string' ? new TextEncoder().encode(value) : value); });
    mocks.host.storeDel = vi.fn(async key => { files.delete(key); });
    mocks.host.storeGet.mockImplementation(async key => files.get(key) ?? null);
    const presets = { capabilities: { ...info().capabilities, presets: true } };
    mocks.engine.convert = vi.fn(async () => ({ matrixQ13: [] }));
    const gr4 = { ...info(), ...presets, family: 'gr4', models: ['HDF'], filename: 'fwdc248b.bin', slots: [{ id: 'CY' }, { id: 'CG' }] };
    mocks.engine.open.mockResolvedValueOnce(gr4);
    await store.adoptFirmware('fwdc248b.bin', '1.11', new Uint8Array([1]));
    store.setName('CY', 'en', 'Warm IV');
    await store.loadPresetFile('CY', { name: 'iv.cube', size: 10, arrayBuffer: async () => new TextEncoder().encode('LUT_3D_SIZE 2 four').buffer });
    store.setModel('GR3_HDF');
    store.setName('CY', 'en', 'Film III');
    await store.loadPresetFile('CY', { name: 'iii.cube', size: 10, arrayBuffer: async () => new TextEncoder().encode('LUT_3D_SIZE 2 three').buffer });
    await vi.advanceTimersByTimeAsync(401);
    expect(new TextDecoder().decode(files.get('preset-cy'))).toBe('LUT_3D_SIZE 2 four');
    expect(new TextDecoder().decode(files.get('gr3-preset-cy'))).toBe('LUT_3D_SIZE 2 three');
    const p4 = JSON.parse(new TextDecoder().decode(files.get('project.json')));
    const p3 = JSON.parse(new TextDecoder().decode(files.get('project-gr3.json')));
    expect(p4).toMatchObject({ model: 'GR3_HDF', slots: { CY: { names: { en: 'Warm IV' }, preset: { fileName: 'iv.cube' } } } });
    expect(p3).toMatchObject({ slots: { CY: { names: { en: 'Film III' }, preset: { fileName: 'iii.cube' } } } });
    // Restart on GR III, then switch to GR IV: each gets its own back.
    vi.resetModules();
    const restarted = await import('../../ui/src/store');
    await restarted.init();
    await vi.advanceTimersByTimeAsync(1);
    expect(restarted.getState()).toMatchObject({ model: 'GR3_HDF' });
    expect(restarted.getState().slots.CY).toMatchObject({ names: { en: 'Film III' }, preset: { fileName: 'iii.cube', text: 'LUT_3D_SIZE 2 three' } });
    // GR IV's official file was kept: it opens again by itself (no download).
    mocks.engine.open.mockResolvedValue(gr4);
    restarted.setModel('HDF');
    await vi.advanceTimersByTimeAsync(1);
    expect(restarted.getState().slots.CY).toMatchObject({ names: { en: 'Warm IV' }, preset: { fileName: 'iv.cube', text: 'LUT_3D_SIZE 2 four' } });
    expect(restarted.getState()).toMatchObject({ model: 'HDF', fwName: 'fwdc248b.bin' });
    expect(files.has('firmware-gr4.bin')).toBe(true);
  });
  it('takes over a GR III project of the test builds kept in project.json, presets included', async () => {
    mocks.host.available = true;
    const files = new Map([
      ['project.json', new TextEncoder().encode(JSON.stringify({ v: 1, model: 'GR3_HDF', slots: { CY: { names: { en: 'Old III' }, preset: { fileName: 'old.cube', kind: 'cube' } } }, filmCount: 20 }))],
      ['preset-cy', new TextEncoder().encode('LUT_3D_SIZE 2 old')],
    ]);
    mocks.host.storeSet.mockImplementation(async (key, value) => { files.set(key, typeof value === 'string' ? new TextEncoder().encode(value) : value); });
    mocks.host.storeGet.mockImplementation(async key => files.get(key) ?? null);
    await store.init();
    await vi.advanceTimersByTimeAsync(401);
    expect(store.getState()).toMatchObject({ model: 'GR3_HDF', filmCount: 20, slots: { CY: { names: { en: 'Old III' }, preset: { fileName: 'old.cube' } } } });
    expect(new TextDecoder().decode(files.get('gr3-preset-cy'))).toBe('LUT_3D_SIZE 2 old');
    expect(JSON.parse(new TextDecoder().decode(files.get('project-gr3.json')))).toMatchObject({ filmCount: 20, slots: { CY: { names: { en: 'Old III' } } } });
    // GR IV's part of project.json is now empty (it was GR III's).
    expect(JSON.parse(new TextDecoder().decode(files.get('project.json'))).slots).toBeUndefined();
  });
  it('exports only the unchanged original using the IIIx update filename', async () => {
    const original = new Uint8Array([1, 2, 3]);
    await store.adoptFirmware('fwdc243b.bin', '1.60', original);
    const pending = store.outputFirmware({ kind: 'folder' }, true);
    await vi.advanceTimersByTimeAsync(0);
    // the factory firmware is only written after confirming the camera's settings were reset
    expect(store.getState().confirm).toMatchObject({ reset: true });
    store.answerConfirm(true); await pending;
    expect(mocks.host.write).toHaveBeenCalledWith('/chosen/fwdc243b.bin', original);
    expect(mocks.engine.build).not.toHaveBeenCalled();
  });
  it('clears the engine and prevents output after switching to a GR IV model', async () => {
    await store.adoptFirmware('fwdc243b.bin', '1.60', new Uint8Array([1]));
    store.setModel('HDF');
    expect(store.getState()).toMatchObject({ model: 'HDF', info: undefined, raw: undefined, fwName: undefined });
    expect(mocks.engine.reset).toHaveBeenCalledOnce();
    await store.outputFirmware({ kind: 'folder' }, true);
    expect(mocks.host.write).not.toHaveBeenCalled();
  });
  it('cancels an export if the family changes while the folder picker is open', async () => {
    await store.adoptFirmware('fwdc243b.bin', '1.60', new Uint8Array([1]));
    let finish;
    mocks.host.pickDirectory.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    const pending = store.outputFirmware({ kind: 'folder' }, true);
    await vi.advanceTimersByTimeAsync(0); store.answerConfirm(true); await vi.advanceTimersByTimeAsync(0);
    store.setModel('HDF'); finish('/chosen'); await pending;
    expect(mocks.host.write).not.toHaveBeenCalled();
  });
  it('invalidates the previous firmware when opening another one fails', async () => {
    await store.adoptFirmware('fwdc243b.bin', '1.60', new Uint8Array([1]));
    mocks.engine.open.mockRejectedValueOnce(new Error('unsupported firmware'));
    vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(await store.adoptFirmware('other.bin', '1.50', new Uint8Array([2]))).toBe(false);
    expect(store.getState()).toMatchObject({ info: undefined, raw: undefined, fwName: undefined });
    await store.outputFirmware({ kind: 'folder' }, true); // nothing open: returns before asking
    expect(mocks.host.write).not.toHaveBeenCalled();
  });
  it.each(['outputBridge'])('cancels GR IV %s when the user switches to IIIx in the folder picker', async action => {
    const gr4 = { ...info(), family: 'gr4', models: ['HDF'], filename: 'fwdc248b.bin' };
    gr4.capabilities = { ...gr4.capabilities, factoryEntry: true, bridge: true };
    mocks.engine.open.mockResolvedValueOnce(gr4);
    await store.adoptFirmware('fwdc248b.bin', '1.11', new Uint8Array([1]));
    let finish;
    mocks.host.pickDirectory.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    const pending = store[action]({ kind: 'folder' });
    store.setModel('GR3X_HDF'); finish('/chosen'); await pending;
    expect(mocks.host.write).not.toHaveBeenCalled();
    expect(mocks.engine.bridge).not.toHaveBeenCalled();
  });
  it('opens GR III 2.10 as its own model in the same family and writes fwdc239b.bin', async () => {
    mocks.engine.open.mockResolvedValue({ ...info(), version: '2.10', filename: 'fwdc239b.bin', models: ['GR3_HDF'], });
    expect(await store.adoptFirmware('fwdc239b.bin', '2.10', new Uint8Array([1]))).toBe(true);
    expect(store.getState()).toMatchObject({ model: 'GR3_HDF', page: 'ic', fwName: 'fwdc239b.bin' });
    expect(store.isGr3('GR3_HDF') && store.isGr3('GR3X_HDF') && store.isGr3('GR3') && store.isGr3('GR3X') && !store.isGr3('HDF')).toBe(true);
    store.addRatio('4:3');
    await vi.advanceTimersByTimeAsync(1);
    store.setSoft(true);
    await store.outputFirmware({ kind: 'folder' });
    expect(mocks.engine.build.mock.calls.at(-1).slice(2)).toEqual([
      [{ level: -1, strength: 'weak' }, { level: -2, strength: 'medium' }, { level: -3, strength: 'strong' }],
      { adjSoftFocus: false, dateStamp: false, monoUnlock: false },
    ]);
    expect(mocks.host.write).toHaveBeenCalledWith('/chosen/fwdc239b.bin', new Uint8Array([9, 2]));
    // no bridge firmware for this family
    store.setBridgeOpen(true);
    expect(store.getState().bridgeOpen).toBe(false);
  });
  it('switching between GR III and GR IIIx closes the other camera\'s firmware', async () => {
    mocks.engine.open.mockResolvedValue({ ...info(), version: '2.10', filename: 'fwdc239b.bin', models: ['GR3_HDF'], });
    await store.adoptFirmware('fwdc239b.bin', '2.10', new Uint8Array([1]));
    store.setModel('GR3X_HDF');
    expect(store.getState()).toMatchObject({ model: 'GR3X_HDF', info: undefined, raw: undefined, fwName: undefined });
    await store.outputFirmware({ kind: 'folder' });
    expect(mocks.host.write).not.toHaveBeenCalled();
  });
  it('does not open another camera\'s kept firmware; a 0.8.x kept file moves to its camera\'s place', async () => {
    await store.init(); // no host: mark the project ready without side effects
    mocks.host.available = true;
    let saved;
    mocks.host.storeSet.mockImplementation(async (key, value) => { if (key === 'project.json') saved = value; });
    await store.adoptFirmware('fwdc243b.bin', '1.60', new Uint8Array([1]));
    store.setModel('HDF');
    await vi.advanceTimersByTimeAsync(401);
    expect(JSON.parse(saved)).toMatchObject({ model: 'HDF' });
    expect(JSON.parse(saved).fwName).toBeUndefined();
    vi.resetModules(); mocks.engine.open.mockClear();
    // 0.8.x kept the one file open last (here GR IIIx's, told apart by its size) as firmware.bin.
    const files = new Map([['project.json', new TextEncoder().encode(saved)], ['firmware.bin', new Uint8Array(30391788)], ['preview.jpg', new Uint8Array([1])]]);
    mocks.host.storeGet.mockImplementation(async key => files.get(key) ?? null);
    mocks.host.storeSet.mockImplementation(async (key, value) => { files.set(key, value); });
    mocks.host.storeDel = vi.fn(async key => { files.delete(key); });
    const restarted = await import('../../ui/src/store');
    await restarted.init();
    expect(restarted.getState().model).toBe('HDF');
    expect(restarted.getState().info).toBeUndefined();
    expect(mocks.engine.open).not.toHaveBeenCalled();
    expect(files.has('firmware.bin')).toBe(false);
    expect(files.get('firmware-gr3x.bin')?.length).toBe(30391788);
    // Back on GR IIIx: its kept file opens again without a download.
    restarted.setModel('GR3X_HDF');
    await vi.advanceTimersByTimeAsync(1);
    expect(mocks.engine.open).toHaveBeenCalledOnce();
    expect(restarted.getState()).toMatchObject({ model: 'GR3X_HDF', fwName: 'fwdc243b.bin' });
  });
  it('keeps 0.8.x\'s firmware.bin when it cannot be copied to its new place', async () => {
    mocks.host.available = true;
    const files = new Map([['project.json', new TextEncoder().encode(JSON.stringify({ v: 1, model: 'HDF' }))], ['firmware.bin', new Uint8Array(30391788)]]);
    mocks.host.storeGet.mockImplementation(async key => files.get(key) ?? null);
    mocks.host.storeSet.mockImplementation(async (key, value) => { if (key.startsWith('firmware-')) throw new Error('disk full'); files.set(key, value); });
    mocks.host.storeDel = vi.fn(async key => { files.delete(key); });
    await store.init();
    store.setModel('GR3X_HDF');
    await vi.advanceTimersByTimeAsync(1);
    expect(mocks.host.storeDel).not.toHaveBeenCalled();
    expect(files.get('firmware.bin')?.length).toBe(30391788);
  });
  it('brings back the nine films of GR III work saved before the film count was saved', async () => {
    mocks.host.available = true;
    const files = new Map([['project.json', new TextEncoder().encode(JSON.stringify({ v: 1, model: 'HDF' }))],
      ['project-gr3.json', new TextEncoder().encode(JSON.stringify({ v: 1, model: 'GR3_HDF', slots: { CY: { names: { en: 'Old III' } } } }))]]);
    mocks.host.storeGet.mockImplementation(async key => files.get(key) ?? null);
    mocks.host.storeSet.mockImplementation(async (key, value) => { files.set(key, value); });
    await store.init();
    store.setModel('GR3_HDF');
    await vi.advanceTimersByTimeAsync(401);
    expect(store.getState()).toMatchObject({ model: 'GR3_HDF', filmCount: 9, slots: { CY: { names: { en: 'Old III' } } } });
  });
  it('opens a file the user drops while the kept one is still opening', async () => {
    await store.init();
    mocks.host.available = true;
    const files = new Map([['firmware-gr3x.bin', new Uint8Array([7])]]);
    mocks.host.storeGet.mockImplementation(async key => files.get(key) ?? null);
    mocks.host.storeSet.mockImplementation(async (key, value) => { files.set(key, value); });
    let finish;
    mocks.engine.open.mockImplementationOnce(() => new Promise(r => { finish = () => r(info()); }));
    store.setModel('GR3X_HDF');
    await vi.advanceTimersByTimeAsync(1);
    expect(mocks.engine.open).toHaveBeenCalledOnce();
    const dropped = store.adoptFirmware('fwdc243b.bin', '1.60', new Uint8Array([8]));
    finish();
    expect(await dropped).toBe(true);
    expect(mocks.engine.open).toHaveBeenCalledTimes(2);
    expect(mocks.engine.open.mock.calls[1][0]).toEqual(new Uint8Array([8]));
  });
});


describe('approved Gold optional state', () => {
  beforeEach(() => { vi.stubGlobal('fetch', vi.fn(async () => ({ ok:true, arrayBuffer:async () => new ArrayBuffer(0) }))); });
  const id = 'gold-plus2-approved';
  const exact = () => ({ ...info(), version: '2.10', filename: 'fwdc239b.bin', models: ['GR3', 'GR3_HDF'], sha256: 'd6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4', bridge: false,
    standardMatrixQ13: [8116,743,-667,15,8598,-421,-244,542,7894], allowed: Object.fromEntries(LANGS.map(l => [l, Array.from({length:95},(_,i)=>String.fromCharCode(i+32)).join('')])), contentArea: { film: {}, plain: {} }, capabilities: { ...info().capabilities, presets: true }, features: { ...info().features, maxFilms: 20 }, tiles: { film: new Uint8Array(6400) },
    slots: ['CY','CG'].map((slot, i) => ({ id: slot, defaultName: `Film ${i + 1}`, names: Object.fromEntries(LANGS.map(l => [l, { text: `Film ${i + 1}`, capacity: 24 }])) })) });
  async function prepare() { mocks.engine.open.mockResolvedValue(exact()); await store.adoptFirmware('fwdc239b.bin', '2.10', new Uint8Array([1])); store.setFilmCount(2); store.addRatio('4:3'); mocks.engine.convert = vi.fn(async () => ({ title:'old', params:{} })); }
  it('selects exact owned colour without fitting and preserves independent controls', async () => {
    await prepare(); store.setRecipe('CY', { sharpness: 2, clarity: -1, sky: 3, grain: { amount: 2, size: 'large' }, filmMtf: true }); store.setHalation('CY', { on: true, preview: 2, colour: 'white' }); store.setTextureGeometry('sensor');
    const before = structuredControls(); store.useLibraryFilm('CY', id); store.useLibraryFilm('CG', id);
    expect(store.getState().slots.CY.preset?.library).toBe(id); expect(store.resolvedPresetResult('CY')).toBeDefined();
    expect(structuredControls()).toEqual(before); expect(mocks.engine.convert).not.toHaveBeenCalled();
    const a = store.getState().slots.CY.preset.result, b = store.getState().slots.CG.preset.result; a.curves[0][0]++;
    expect(store.unavailableLibraryProblem()).toBeTruthy(); expect(b.curves[0][0]).not.toBe(a.curves[0][0]);
  });
  function structuredControls() { const s = store.getState(); return JSON.parse(JSON.stringify({ recipe:s.slots.CY.recipe, halo:s.slots.CY.halation, geometry:s.textureGeometry })); }
  it('invalidates an older conversion and makes cached cross-model results unavailable until eligible open', async () => {
    await prepare(); let finish; mocks.engine.convert.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    const old = store.loadPresetFile('CY', { name:'old.cube', size:10, arrayBuffer:async () => new TextEncoder().encode('LUT_3D_SIZE 2 old').buffer }); await Promise.resolve(); await Promise.resolve();
    store.useLibraryFilm('CY', id); finish({ title:'stale', params:{} }); await old;
    expect(store.getState().slots.CY.preset?.library).toBe(id); expect(store.resolvedPresetResult('CY')).toBeDefined();
    store.setModel('GR3X_HDF'); expect(store.getState().slots.CY.preset?.library).toBe(id); expect(store.resolvedPresetResult('CY')).toBeUndefined(); expect(store.unavailableLibraryProblem()).toBeTruthy();
    store.setModel('GR3_HDF'); expect(store.resolvedPresetResult('CY')).toBeUndefined();
    await store.adoptFirmware('fwdc239b.bin','2.10',new Uint8Array([1])); expect(store.resolvedPresetResult('CY')).toBeDefined();
    mocks.engine.open.mockRejectedValueOnce(new Error('bad source')); await store.adoptFirmware('bad.bin','',new Uint8Array([1]));
    expect(store.getState().slots.CY.preset?.library).toBe(id); expect(store.resolvedPresetResult('CY')).toBeUndefined();
  });
  it('retains unavailable intent on restart without firmware and rehydrates only after matching open', async () => {
    await store.init(); mocks.host.available = true; const files = new Map(); mocks.host.storeDel = vi.fn(async key => files.delete(key));
    mocks.host.storeSet.mockImplementation(async (key, value) => files.set(key, typeof value === 'string' ? new TextEncoder().encode(value) : value)); mocks.host.storeGet.mockImplementation(async key => files.get(key) ?? null);
    await prepare(); store.useLibraryFilm('CY', id); await vi.advanceTimersByTimeAsync(401); files.delete('firmware-gr3.bin');
    expect(JSON.parse(new TextDecoder().decode(files.get('project-gr3.json'))).slots.CY.preset.library).toBe(id);
    vi.resetModules(); const restarted = await import('../../ui/src/store'); await restarted.init();
    expect(restarted.getState().slots.CY.preset?.library).toBe(id); expect(restarted.resolvedPresetResult('CY')).toBeUndefined(); expect(restarted.unavailableLibraryProblem()).toBeTruthy();
    await restarted.adoptFirmware('fwdc239b.bin','2.10',new Uint8Array([1])); expect(restarted.resolvedPresetResult('CY')).toBeDefined();
    expect(mocks.engine.convert).not.toHaveBeenCalled();
  });
  it('refuses active incomplete intent before destination/build, but allows dormant and stock output', async () => {
    await prepare(); store.setLang('en'); store.useLibraryFilm('CY',id); store.getState().slots.CY.preset.result = undefined;
    await store.outputFirmware({ kind:'folder' }); expect(mocks.host.pickDirectory).not.toHaveBeenCalled(); expect(mocks.engine.build).not.toHaveBeenCalled(); expect(store.getState().toasts.at(-1).text).toMatch(/unavailable/i);
    store.useLibraryFilm('CY',id); store.useLibraryFilm('CG',id); store.getState().slots.CG.preset.library=id+'@unknown'; store.getState().slots.CG.preset.result=undefined; store.setFilmCount(1);
    await store.outputFirmware({ kind:'folder' }); expect(mocks.engine.build).toHaveBeenCalledTimes(1);
    store.setFilmCount(2); const stock=store.outputFirmware({ kind:'folder' },true); store.answerConfirm(true); await stock; expect(mocks.engine.build).toHaveBeenCalledTimes(1);
  });
  it('copies validated request arrays and isolates the optional thumbnail from authored fitting', async () => {
    await prepare(); store.useLibraryFilm('CY',id); const request = store.pendingChanges().find(c => c.id==='CY').request;
    const old = request.preset.curves[0][0]; store.getState().slots.CY.preset.result.curves[0][0]++;
    expect(request.preset.curves[0][0]).toBe(old); expect(store.resolvedPresetResult('CY')).toBeUndefined();
    const { libraryPreview } = await import('../../ui/src/library'); const r = await libraryPreview(id, exact(), 'GR3_HDF'); expect(r?.postQ9).toHaveLength(9); expect(mocks.engine.convert).not.toHaveBeenCalled();
    expect(await libraryPreview(id, exact(), 'GR3X_HDF')).toBeUndefined();
  });
  it('rejects a delayed file read or file-store completion after a newer approved selection', async () => {
    await prepare(); let read; const importing=store.loadPresetFile('CY',{name:'late.cube',size:10,arrayBuffer:()=>new Promise(resolve=>{read=resolve;})});
    store.useLibraryFilm('CY',id); read(new TextEncoder().encode('LUT_3D_SIZE 2 late').buffer); await importing;
    expect(store.getState().slots.CY.preset?.library).toBe(id); expect(mocks.engine.convert).not.toHaveBeenCalled();
    mocks.host.available=true; let saved; mocks.host.storeSet.mockImplementationOnce(()=>new Promise(resolve=>{saved=resolve;}));
    const persisting=store.loadPresetFile('CY',{name:'late.cube',size:10,arrayBuffer:async()=>new TextEncoder().encode('LUT_3D_SIZE 2 late').buffer}); await Promise.resolve(); await Promise.resolve();
    store.useLibraryFilm('CY',id); saved(); await persisting;
    expect(store.getState().slots.CY.preset?.library).toBe(id); expect(mocks.engine.convert).not.toHaveBeenCalled();
  });
  it('clears only automatically assigned approved names when removed or replaced', async () => {
    await prepare(); store.useLibraryFilm('CY',id); expect(store.getState().slots.CY.names.en).toBe('Gold +2 EV (approved)'); store.setName('CY','en','My warm look'); store.removePreset('CY');
    expect(store.getState().slots.CY.names.en).toBe('My warm look'); expect(store.getState().slots.CY.names['zh-CN']).toBeUndefined();
    store.useLibraryFilm('CY',id); await store.loadPresetFile('CY',{name:'other.cube',size:10,arrayBuffer:async()=>new TextEncoder().encode('LUT_3D_SIZE 2 other').buffer});
    expect(Object.values(store.getState().slots.CY.names)).not.toContain('Gold +2 EV (approved)');
  });

  it('does not let an ordinary delayed restore read replace a newer approved choice', async () => {
    mocks.host.available=true; const project={v:1,model:'GR3_HDF',slots:{CY:{preset:{fileName:'old.cube',kind:'cube'},names:{}}},filmCount:2};
    let read; mocks.host.storeGet.mockImplementation(async key => key==='project.json'?new TextEncoder().encode(JSON.stringify(project)):key==='gr3-preset-cy'?new Promise(resolve=>{read=resolve;}):null);
    const restoring=store.init(); await vi.waitFor(()=>expect(read).toBeTypeOf('function'));
    store.useLibraryFilm('CY',id); read(new TextEncoder().encode('LUT_3D_SIZE 2 old')); await restoring;
    expect(store.getState().slots.CY.preset?.library).toBe(id); expect(store.getState().slots.CY.preset?.text).toBe('');
  });

  it('keeps removed built-in intent cancelled while another restore read is pending', async () => {
    mocks.host.available=true; const project={v:1,model:'GR3_HDF',slots:{CY:{preset:{fileName:'Gold +2 EV (approved)',kind:'cube',library:id},names:{en:'Gold +2 EV (approved)'}},CG:{preset:{fileName:'old.cube',kind:'cube'},names:{}}},filmCount:2};
    const files=new Map([['project.json',new TextEncoder().encode(JSON.stringify(project))]]); let read;
    mocks.host.storeGet.mockImplementation(async key=>key==='gr3-preset-cg'?new Promise(resolve=>{read=resolve;}):files.get(key)??null); mocks.host.storeSet.mockImplementation(async(key,value)=>files.set(key,typeof value==='string'?new TextEncoder().encode(value):value)); mocks.host.storeDel=vi.fn(async()=>undefined);
    const restoring=store.init(); await vi.waitFor(()=>expect(read).toBeTypeOf('function')); expect(store.getState().slots.CY.preset?.library).toBe(id);
    store.getState().ready=true; store.removePreset('CY'); await vi.advanceTimersByTimeAsync(401);
    expect(JSON.parse(new TextDecoder().decode(files.get('project-gr3.json'))).slots.CY.preset).toBeNull();
    read(new TextEncoder().encode('LUT_3D_SIZE 2 old')); await restoring; expect(store.getState().slots.CY.preset).toBeUndefined();
  });
  it('invalidates a delayed file import for moving slot IDs and fails closed on a throwing factory', async () => {
    await prepare(); store.useLibraryFilm('CG',id); let read; const pending=store.loadPresetFile('CG',{name:'moving.cube',size:10,arrayBuffer:()=>new Promise(resolve=>{read=resolve;})}); store.removeFilm('CY'); read(new TextEncoder().encode('LUT_3D_SIZE 2 moving').buffer); await pending;
    expect(store.getState().slots.CY.preset?.library).toBe(id); expect(store.getState().slots.CG.preset).toBeUndefined(); expect(mocks.engine.convert).not.toHaveBeenCalled();
    const gold=await import('../../ui/src/approved-gold'); vi.spyOn(gold,'createApprovedGold').mockImplementationOnce(()=>{throw new Error('unavailable data');}); store.useLibraryFilm('CY',id);
    await store.outputFirmware({kind:'folder'}); expect(store.getState().slots.CY.preset?.library).toBe(id); expect(store.resolvedPresetResult('CY')).toBeUndefined(); expect(mocks.host.pickDirectory).not.toHaveBeenCalled(); expect(mocks.engine.build).not.toHaveBeenCalled();
  });

  it('does not resurrect saved ordinary metadata after approved selection and removal during family loading', async () => {
    mocks.host.available=true; const project={v:1,model:'GR3_HDF',slots:{CY:{preset:{fileName:'old.cube',kind:'cube'},names:{}}},filmCount:2};
    const files=new Map([['project.json',new TextEncoder().encode(JSON.stringify(project))],['gr3-preset-cy',new TextEncoder().encode('LUT_3D_SIZE 2 old')]]);
    mocks.host.storeGet.mockImplementation(async key=>files.get(key)??null); mocks.host.storeSet.mockImplementation(async(key,value)=>files.set(key,typeof value==='string'?new TextEncoder().encode(value):value)); mocks.host.storeDel=vi.fn(async()=>undefined);
    await store.init(); expect(store.getState().slots.CY.preset?.fileName).toBe('old.cube'); store.setModel('HDF');
    let read; mocks.host.storeGet.mockImplementation(async key=>key==='gr3-preset-cy'?new Promise(resolve=>{read=resolve;}):files.get(key)??null);
    store.setModel('GR3_HDF'); await vi.waitFor(()=>expect(read).toBeTypeOf('function')); store.useLibraryFilm('CY',id); store.removePreset('CY'); await vi.advanceTimersByTimeAsync(401);
    expect(JSON.parse(new TextDecoder().decode(files.get('project-gr3.json'))).slots.CY.preset).toBeNull();
    read(new TextEncoder().encode('LUT_3D_SIZE 2 old')); await vi.advanceTimersByTimeAsync(401); expect(store.getState().slots.CY.preset).toBeUndefined();
  });

});


describe('film-order requested identity', () => {
  const builtin = 'gold-plus2-approved';
  const profile = () => ({ ...info(), version:'2.10', filename:'fwdc239b.bin', models:['GR3','GR3_HDF'], bridge:false,
    sha256:'d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4', standardMatrixQ13:[8116,743,-667,15,8598,-421,-244,542,7894],
    capabilities:{...info().capabilities,presets:true,lookLayout:true}, features:{...info().features,maxFilms:20}, tiles:{film:new Uint8Array(6400)},contentArea:{film:{},plain:{}},
    allowed:Object.fromEntries(LANGS.map(l=>[l,Array.from({length:95},(_,i)=>String.fromCharCode(i+32)).join('')])),
    slots:['CY','CG','F3'].map((id,i)=>({id,defaultName:`Film ${i+1}`,names:Object.fromEntries(LANGS.map(l=>[l,{text:`Film ${i+1}`,capacity:24}]))})) });
  async function prepare() {
    mocks.engine.open.mockResolvedValue(profile());
    mocks.engine.convert=vi.fn(async()=>({kind:'cube',title:'Gold 200',meanDE:1,p95DE:2,warnings:[],unsupported:[],params:{M1:[[1,0,0],[0,1,0],[0,0,1]],ck:[0,1,2].map(()=>Float64Array.from({length:17},(_,i)=>i/16))},matrixQ13:Int16Array.from([8192,0,0,0,8192,0,0,0,8192]),curves:[0,1,2].map(()=>Uint16Array.from({length:256},(_,i)=>Math.round(i*16383/255)))}));
    await store.adoptFirmware('fwdc239b.bin','2.10',new Uint8Array([1])); store.setFilmCount(3); store.setLang('en');
    store.useLibraryFilm('CY',builtin);store.useLibraryFilm('CG','Gold 200');store.useLibraryFilm('F3',builtin);await Promise.resolve();
    for(const id of ['CY','CG','F3'])store.setName(id,'en','Street');
  }
  beforeEach(()=>vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,arrayBuffer:async()=>new ArrayBuffer(0)}))));
  it('distinguishes duplicate aliases by joined firmware slot and immutable requested source without mutation', async () => {
    await prepare(); const state=store.getState(), before=store.pendingChanges(), calls=mocks.engine.convert.mock.calls.length;
    expect(store.lookName('g64')).toBe('Street');expect(store.lookName('g65')).toBe('Street');
    expect(store.lookIdentity('g64')).toBe('Film 1 · Gold +2 EV (approved)');expect(store.lookIdentity('g65')).toBe('Film 2 · Gold 200');expect(store.lookIdentity('g66')).toBe('Film 3 · Gold +2 EV (approved)');
    store.getState().slots.CY.preset.result.title='arbitrary import-like title';expect(store.lookIdentity('g64')).toBe('Film 1 · Gold +2 EV (approved)');store.getState().slots.CY.preset.result.title='Gold +2 EV (approved)';
    expect(store.getState()).toBe(state);expect(store.pendingChanges()).toEqual(before);expect(mocks.engine.convert).toHaveBeenCalledTimes(calls);expect(store.unavailableLibraryProblem()).toBeUndefined();
  });
  it('follows stable native keys across order/hiding and whole-slot removal without moving payloads during a menu edit', async () => {
    await prepare();const before=store.pendingChanges(), identity=store.lookIdentity('g64');
    store.moveLookTo('g64',0);store.setLookHidden('g64',true);expect(store.lookOrderNow()[0]).toBe('g64');expect(store.lookIdentity('g64')).toBe(identity);expect(store.pendingChanges()).toEqual(before);
    store.removeFilm('CY');expect(store.lookIdentity('g64')).toBe('Film 1 · Gold 200');expect(store.lookIdentity('g65')).toBe('Film 2 · Gold +2 EV (approved)');expect(store.lookName('g65')).toBe('Street');expect(store.getState().slots.CG.preset.library).toBe(builtin);expect(store.unavailableLibraryProblem()).toBeUndefined();
  });
  it('keeps imports distinct from builtins and preserves arbitrary fallback title text', async () => {
    await prepare();const sl=store.getState().slots.CG;sl.preset={...sl.preset,library:undefined,fileName:'private/folder/Gold +2 EV (approved).cube',result:{...sl.preset.result,title:'different TITLE'}};
    expect(store.lookIdentity('g65')).toBe('Film 2 · Preset · Gold +2 EV (approved).cube');
    sl.preset.fileName='';sl.preset.result.title='A\u0000B\u0001C '+ 'long'.repeat(200);
    expect(store.lookIdentity('g65')).toBe('Film 2 · Preset · '+sl.preset.result.title);
    sl.preset={fileName:'Gold +2 EV (approved)',kind:'cube',text:'',busy:false,library:builtin+'@unknown'};
    expect(store.lookIdentity('g65')).toBe('Film 2 · Gold +2 EV (approved)');expect(store.resolvedPresetResult('CG')).toBeUndefined();expect(store.unavailableLibraryProblem()).toBeTruthy();
  });
  it('does not decorate factory, dormant, missing or unsupported profile rows', async () => {
    await prepare();const state=store.getState();
    for(const key of ['g11','g63','g67','g064','f18','unknown'])expect(store.lookIdentity(key)).toBeUndefined();
    for(const changed of [{model:'GR3X_HDF'},{info:undefined},{info:{...state.info,version:'2.20'}},{info:{...state.info,sha256:'0'.repeat(64)}},{info:{...state.info,standardMatrixQ13:Array(9).fill(0)}},{info:{...state.info,capabilities:{...state.info.capabilities,lookLayout:false}}}])expect(store.lookIdentity('g64',{...state,...changed})).toBeUndefined();
    store.setFilmCount(1);expect(store.lookIdentity('g65')).toBeUndefined();expect(store.lookIdentity('g64')).toContain('Film 1');
  });
  it('re-derives slot/source metadata after project restore without altering restored build requests', async () => {
    await store.init();mocks.host.available=true;const files=new Map();mocks.host.storeGet.mockImplementation(async key=>files.get(key)??null);mocks.host.storeSet.mockImplementation(async(key,value)=>files.set(key,typeof value==='string'?new TextEncoder().encode(value):value));mocks.host.storeDel=vi.fn(async key=>files.delete(key));
    await prepare();store.moveLookTo('g65',0);store.setLookHidden('g64',true);await vi.advanceTimersByTimeAsync(401);const requests=store.pendingChanges();
    vi.resetModules();const restored=await import('../../ui/src/store');await restored.init();await Promise.resolve();
    expect(restored.lookIdentity('g64')).toBe('Film 1 · Gold +2 EV (approved)');expect(restored.lookIdentity('g65')).toBe('Film 2 · Gold 200');expect(restored.lookIdentity('g66')).toBe('Film 3 · Gold +2 EV (approved)');expect(restored.lookName('g64')).toBe('Street');expect(restored.pendingChanges()).toEqual(requests);expect(restored.lookHiddenNow()).toContain('g64');expect(restored.lookOrderNow()[0]).toBe('g65');
  });
});

describe('texture detail reuse', () => {
  const ids = ['CY', 'CG', ...Array.from({ length: 18 }, (_, i) => `F${i + 3}`)];
  let notices, unsubscribe;
  beforeEach(async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, arrayBuffer: async () => new ArrayBuffer(0) })));
    vi.doMock('react', async () => ({ ...await vi.importActual('react'), useSyncExternalStore: (subscribe, snapshot) => { unsubscribe = subscribe(() => { notices++; }); return snapshot(); } }));
    vi.resetModules(); store = await import('../../ui/src/store'); store.useStore(s => s); notices = 0;
  });
  afterEach(() => { unsubscribe?.(); vi.doUnmock('react'); });
  async function prepare(n = 3) {
    const profile = { ...info(), version: '2.10', filename: 'fwdc239b.bin', models: ['GR3', 'GR3_HDF'], bridge: false,
      sha256: 'd6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4', standardMatrixQ13: [8116,743,-667,15,8598,-421,-244,542,7894],
      capabilities: { ...info().capabilities, presets: true, lookLayout: true }, features: { ...info().features, maxFilms: 20 },
      tiles: { film: new Uint8Array(6400) }, contentArea: { film: {}, plain: {} },
      allowed: Object.fromEntries(LANGS.map(l => [l, Array.from({ length: 95 }, (_, i) => String.fromCharCode(i + 32)).join('')])),
      slots: ids.map((id, i) => ({ id, defaultName: `Film ${i + 1}`, names: Object.fromEntries(LANGS.map(l => [l, { text: `Film ${i + 1}`, capacity: 24 }])) })) };
    mocks.engine.open.mockResolvedValue(profile); await store.adoptFirmware('fwdc239b.bin', '2.10', new Uint8Array([1])); store.setFilmCount(n); store.setLang('en');
    store.useLibraryFilm('CY', 'gold-plus2-approved'); store.useLibraryFilm('CG', 'gold-plus2-approved');
    store.setName('CY', 'en', 'Street'); store.setName('CG', 'en', 'Street');
    store.setRecipe('CY', { sharpness: 2, clarity: -1, shading: 3, sky: 4, grain: { amount: 2, size: 'large' }, filmMtf: true });
    store.setHalation('CY', { preview: 2, colour: 'gold' });
    store.setRecipe('CG', { sharpness: -4, clarity: 3, shading: -2, sky: -3, grain: { amount: 1, size: 'small' } });
    store.setHalation('CG', { on: false, preview: 1, colour: 'white' }); store.setTextureGeometry('sensor'); store.setActiveSlot('CG');
  }
  const choices = target => { expect(store.textureReuseChoices, 'guarded texture reuse candidates must exist').toBeTypeOf('function'); return store.textureReuseChoices(target); };
  const from = (source = 'CY', target = 'CG') => choices(target).find(c => c.from === source);
  it('publishes one private target-only update preserving colour, sky, identity and captured objects', async () => {
    await prepare(); const before = store.getState(), source = before.slots.CY, target = before.slots.CG, neutral = JSON.stringify(store.NEUTRAL_RECIPE), requests = store.pendingChanges();
    const sourceGrain = { ...source.recipe.grain }, targetGrain = { ...target.recipe.grain }; const choice = from();
    expect(choice.label).toContain('Street'); expect(choice.label).toContain('Film 1'); expect(choice.label).toContain('Gold +2 EV (approved)');
    notices = 0; expect(store.reuseTexture(choice)).toBe(true); expect(notices).toBe(1);
    const after = store.getState(), changed = after.slots.CG;
    expect(changed.recipe).toEqual({ ...source.recipe, sky: -3 }); expect(changed.halation).toEqual({ on: false, preview: 2, colour: 'gold' });
    for (const key of ['preset', 'names', 'icon']) expect(changed[key]).toBe(target[key]);
    for (const key of ['filmCount', 'activeSlot', 'textureGeometry', 'lookOrder3', 'lookHidden3']) expect(after[key]).toBe(before[key]);
    expect(after.slots.CY).toBe(source); expect(after.slots.F3).toBe(before.slots.F3); expect(changed.recipe).not.toBe(source.recipe); expect(changed.recipe.grain).not.toBe(source.recipe.grain); expect(changed.halation).not.toBe(source.halation);
    changed.recipe.grain.amount = 3; changed.halation.colour = 'orange';
    expect(source.recipe.grain).toEqual(sourceGrain); expect(target.recipe.grain).toEqual(targetGrain); expect(source.halation.colour).toBe('gold'); expect(target.halation.colour).toBe('white');
    expect(requests.find(r => r.id === 'CG').request.grain).toEqual(targetGrain); expect(JSON.stringify(store.NEUTRAL_RECIPE)).toBe(neutral);
  });
  it('clears Off and zero values while preserving target latent children and target sky/on', async () => {
    await prepare(); store.removePreset('CY'); store.setRecipe('CY', { sharpness: 0, clarity: 0, shading: 0, grain: { amount: 0, size: 'large' }, filmMtf: undefined }); store.setHalation('CY', { preview: 0, colour: 'gold' });
    store.setRecipe('CG', { filmMtf: true }); store.setActiveSlot('CG'); expect(store.reuseTexture(from())).toBe(true);
    expect(store.recipeOf('CG')).toEqual({ sharpness: 0, clarity: 0, shading: 0, sky: -3, grain: { amount: 0, size: 'small' } });
    expect(store.getState().slots.CG.halation).toEqual({ on: false, preview: 0, colour: 'white' });
    const request = store.pendingChanges().find(r => r.id === 'CG').request; expect(request).not.toHaveProperty('filmMtf'); expect(request).not.toHaveProperty('grain'); expect(request.defaults.hue).toBe(-3);
    store.removePreset('CG'); store.setActiveSlot('CG'); expect(from()).toBeDefined(); expect(store.reuseTexture(from())).toBe(true); expect(store.getState().slots.CG.preset).toBeUndefined();
  });
  it('accepts genuinely empty active targets and neutral sources without mutating shared defaults', async () => {
    await prepare(4); const empty = store.getState().slots.F3, source = store.getState().slots.CY, neutral = JSON.stringify(store.NEUTRAL_RECIPE);
    expect(empty).not.toHaveProperty('recipe'); expect(empty).not.toHaveProperty('halation'); expect(empty).not.toHaveProperty('preset');
    store.setActiveSlot('F3'); expect(store.reuseTexture(from('CY', 'F3'))).toBe(true);
    const filled = store.getState().slots.F3; expect(filled.recipe).toEqual({ ...source.recipe, sky: 0 }); expect(filled.halation).toEqual({ on: true, preview: 2, colour: 'gold' });
    expect(filled.preset).toBeUndefined(); expect(filled.names).toBe(empty.names); expect(filled.icon).toBe(empty.icon); expect(empty).not.toHaveProperty('recipe');
    const emptySource = store.getState().slots.F4; expect(emptySource).not.toHaveProperty('recipe'); expect(emptySource).not.toHaveProperty('halation');
    store.setRecipe('CG', { filmMtf: true }); store.setActiveSlot('CG'); expect(store.reuseTexture(from('F4'))).toBe(true);
    expect(store.recipeOf('CG')).toEqual({ sharpness: 0, clarity: 0, shading: 0, sky: -3, grain: { amount: 0, size: 'small' } });
    expect(store.getState().slots.CG.halation).toEqual({ on: false, preview: 0, colour: 'white' }); expect(store.getState().slots.F4).toBe(emptySource); expect(JSON.stringify(store.NEUTRAL_RECIPE)).toBe(neutral);
  });
  it('refuses unsupported, busy, inactive and present unresolved participant intent without side effects', async () => {
    await prepare(); const good = from(), base = store.getState();
    for (const patch of [{ busy: 'working' }, { fwBusy: true }, { raw: undefined }, { info: undefined }, { model: 'GR3X_HDF' }, { info: { ...base.info, version: '2.20' } }, { filmCount: 1 }, { activeSlot: 'CY' }]) {
      Object.assign(base, patch); const state = store.getState(), count = notices; expect(store.reuseTexture(good)).toBe(false); expect(store.getState()).toBe(state); expect(notices).toBe(count); Object.assign(base, { busy: undefined, fwBusy: false, raw: good.raw, info: good.info, model: good.model, filmCount: 3, activeSlot: 'CG' });
    }
    for (const id of ['CY', 'CG']) {
      const saved = base.slots[id].preset;
      for (const preset of [{ ...saved, busy: true }, { ...saved, error: 'bad' }, { ...saved, result: undefined }, { ...saved, library: 'gold-plus2-approved@unknown' }]) {
        base.slots[id].preset = preset; const available = choices('CG');
        if (id === 'CG') expect(available).toEqual([]); else expect(available.some(c => c.from === 'CY')).toBe(false);
        expect(store.reuseTexture(good)).toBe(false);
      }
      base.slots[id].preset = saved;
    }
    mocks.host.storeSet.mockClear(); notices = 0; const state = store.getState(); expect(store.reuseTexture({ ...good, from: 'CG' })).toBe(false); expect(store.getState()).toBe(state); expect(notices).toBe(0); expect(mocks.host.storeSet).not.toHaveBeenCalled();
  });
  it('rejects stale owners, same-count remove/re-add, source replacement and model round-trips', async () => {
    await prepare(); let old = from(); store.setRecipe('CY', { clarity: 1 }); let state = store.getState(); expect(store.reuseTexture(old)).toBe(false); expect(store.getState()).toBe(state);
    old = from(); store.setRecipe('CG', { sky: 2 }); expect(store.reuseTexture(old)).toBe(false);
    old = from(); store.removeFilm('F3'); store.setFilmCount(3); store.setActiveSlot('CG'); expect(store.reuseTexture(old)).toBe(false);
    old = from(); store.setModel('GR3'); store.setModel('GR3_HDF'); expect(store.reuseTexture(old)).toBe(false);
    old = from(); await store.adoptFirmware('fwdc239b.bin', '2.10', new Uint8Array([1])); expect(store.reuseTexture(old)).toBe(false);
    expect(store.reuseTexture(from())).toBe(true);
  });
  it('uses existing active films only at zero/one/twenty and follows menu ordering without touching dormant data', async () => {
    await prepare(20); const dormant = store.getState().slots.F20; expect(choices('CG')).toHaveLength(19);
    store.moveLookTo('g64', 0); store.setLookHidden('g64', true); expect(store.reuseTexture(from())).toBe(true); expect(store.getState().filmCount).toBe(20); expect(store.getState().slots.F20).toBe(dormant);
    store.setFilmCount(1); expect(choices('CY')).toEqual([]); expect(choices('F20')).toEqual([]); store.setFilmCount(0); expect(choices('CY')).toEqual([]);
  });
  it('keeps stable firmware slot labels when the optional menu-layout label helper is unavailable', async () => {
    await prepare(); store.setName('F3', 'en', 'Street'); const state = store.getState();
    state.info = { ...state.info, capabilities: { ...state.info.capabilities, lookLayout: false } };
    expect(store.textureReuseSupported()).toBe(true); const options = choices('CG');
    expect(options.find(c => c.from === 'CY').label).toContain('Film 1'); expect(options.find(c => c.from === 'F3').label).toContain('Film 3');
    expect(new Set(options.map(c => c.label)).size).toBe(2); expect(store.reuseTexture(options.find(c => c.from === 'CY'))).toBe(true);
  });
  it('preserves approved, authored and imported requested sources without menu-layout capability', async () => {
    await prepare(4);
    const result = store.getState().slots.CY.preset.result;
    mocks.engine.convert = vi.fn(async () => ({ ...result, source: undefined, title: 'Imported title' }));
    store.useLibraryFilm('F3', 'Gold 200'); await Promise.resolve();
    await store.loadPresetFile('F4', { name: 'Gold +2 EV (approved).cube', size: 10, arrayBuffer: async () => new TextEncoder().encode('LUT_3D_SIZE 2 imported').buffer });
    store.setName('F3', 'en', 'Street'); store.setName('F4', 'en', 'Street'); store.setActiveSlot('CG');
    const labels = () => Object.fromEntries(choices('CG').map(c => [c.from, c.label]));
    const before = labels();
    expect(before.CY).toBe('Street · Film 1 · Gold +2 EV (approved)');
    expect(before.F3).toBe('Street · Film 3 · Gold 200');
    expect(before.F4).toBe('Street · Film 4 · Preset · Gold +2 EV (approved).cube');
    const state = store.getState(); state.info = { ...state.info, capabilities: { ...state.info.capabilities, lookLayout: false } };
    expect(store.lookIdentity('g64')).toBeUndefined(); expect(store.textureReuseSupported()).toBe(true);
    expect(labels()).toEqual(before);
    state.slots.F4.preset.fileName = ''; state.slots.F4.preset.result.title = 'Fallback imported title';
    expect(labels().F4).toBe('Street · Film 4 · Preset · Fallback imported title');
  });
  it('round-trips only applied existing recipe fields through the current project format', async () => {
    await store.init(); mocks.host.available = true; const files = new Map(); mocks.host.storeGet.mockImplementation(async key => files.get(key) ?? null); mocks.host.storeSet.mockImplementation(async (key, value) => files.set(key, typeof value === 'string' ? new TextEncoder().encode(value) : value)); mocks.host.storeDel = vi.fn(async key => files.delete(key));
    await prepare(); const identity = store.getState().slots.CG.preset.library; expect(store.reuseTexture(from())).toBe(true); const expected = store.recipeOf('CG'), halo = store.getState().slots.CG.halation; await vi.advanceTimersByTimeAsync(401);
    const saved = JSON.parse(new TextDecoder().decode(files.get('project-gr3.json'))); expect(saved.slots.CG.recipe).toEqual(expected); expect(saved.slots.CG.preset.library).toBe(identity); expect(Object.keys(saved).some(k => /reuse|clipboard/i.test(k))).toBe(false);
    vi.resetModules(); const restored = await import('../../ui/src/store'); await restored.init(); expect(restored.recipeOf('CG')).toEqual(expected); expect(restored.getState().slots.CG.halation).toEqual(halo); expect(restored.getState().slots.CG.preset.library).toBe(identity);
  });
});
