import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createHash } from 'node:crypto';
import * as pixels from '../../ui/src/pixels';
import * as preview from '../../ui/src/preview';
import type { PreviewPixels } from '../../ui/src/pixels';
import { color, halateRgba } from '../src';

function jpeg(orientation: number) {
  const exif = new Uint8Array(32); exif.set([69,120,105,102,0,0,73,73,42,0,8,0,0,0,1,0,18,1,3,0,1,0,0,0,orientation,0,0,0,0,0,0,0]);
  return Uint8Array.from([255,216,255,225,0,34,...exif,255,192,0,17,8,0,3,0,2,3,1,17,0,2,17,0,3,17,0,255,218,0,2,12,34,255,217]);
}
describe('stored original JPEG geometry', () => {
  it('keeps one source pixel per device pixel at fractional displayed widths and DPR changes', () => {
    for (const source of [6000, 960]) for (const appScale of [1, .941, .788]) for (const dpr of [1, 2]) {
      const displayedWidth = 637.328125 * appScale;
      const zoom = preview.loupeScale(source, displayedWidth, dpr);
      expect(displayedWidth * zoom * dpr).toBeCloseTo(source, 8);
    }
  });
  it('reads all EXIF orientations and removes their metadata without changing encoded raster data', () => {
    for (let o = 1; o <= 8; o++) {
      const result = pixels.previewJpeg(jpeg(o));
      expect(result).toMatchObject({ width: 2, height: 3, orientation: o });
      expect([...result!.bytes]).not.toContain(69); // no Exif APP1 remains for a browser to auto-rotate
      expect([...result!.bytes].slice(-8)).toEqual([255,218,0,2,12,34,255,217]);
    }
    expect(pixels.previewJpeg(new Uint8Array([255,216,255,225,255,255]))).toBeNull();
  });
  it('maps mirrored and rotated pixels exactly, including alpha, after texture processing', () => {
    const source = { width: 2, height: 3, data: Uint8ClampedArray.from([1,2,3,4,5,6].flatMap(x => [x,0,0,x + 10])) };
    const expected = [[1,2,3,4,5,6],[2,1,4,3,6,5],[6,5,4,3,2,1],[5,6,3,4,1,2],[1,3,5,2,4,6],[5,3,1,6,4,2],[6,4,2,5,3,1],[2,4,6,1,3,5]];
    for (let o = 1; o <= 8; o++) {
      const out = pixels.orientPreview(source, o);
      expect([...out.data].filter((_, i) => i % 4 === 0)).toEqual(expected[o - 1]);
      expect([...out.data].filter((_, i) => i % 4 === 3)).toEqual(expected[o - 1].map(x => x + 10));
      expect([out.width, out.height]).toEqual(o >= 5 ? [3,2] : [2,3]);
    }
  });
});

describe('preview source ownership', () => {
  it('cancels a running worker and never submits a late decoded old source', async () => {
    const deferred: ((value: PreviewPixels) => void)[] = [];
    const workers: any[] = [];
    const renderer = preview.createDetailRenderer(() => new Promise(resolve => deferred.push(resolve)), () => {
      const worker = { postMessage: vi.fn(), terminate: vi.fn(), onmessage: null, onerror: null }; workers.push(worker); return worker;
    });
    const first = renderer.render({} as any, {} as any, {} as any).catch(e => e.name);
    await Promise.resolve(); // first decode starts before the source changes
    const second = renderer.render({} as any, {} as any, {} as any).catch(e => e.name);
    expect(deferred).toHaveLength(1); // never overlap large original decodes
    deferred[0]({ width: 2, height: 3, data: new Uint8ClampedArray(24) });
    await vi.waitFor(() => expect(deferred).toHaveLength(2));
    expect(workers).toHaveLength(0);
    deferred[1]({ width: 2, height: 3, data: new Uint8ClampedArray(24) }); await Promise.resolve();
    expect(workers).toHaveLength(1); expect(workers[0].postMessage).toHaveBeenCalledTimes(1);
    renderer.cancel(); expect(workers[0].terminate).toHaveBeenCalled();
    expect(await first).toBe('AbortError'); expect(await second).toBe('AbortError');
  });
});

describe('full raster stage contract', () => {
  it('matches colour → MTF → halo → grain in stored coordinates before EXIF rotation', () => {
    class TestImageData {
      data: Uint8ClampedArray<ArrayBuffer>; width: number; height: number;
      constructor(data: number | Uint8ClampedArray<ArrayBuffer>, w: number, h?: number) {
        this.width = typeof data === 'number' ? data : w; this.height = typeof data === 'number' ? w : h!;
        this.data = typeof data === 'number' ? new Uint8ClampedArray(data * w * 4) : data;
      }
    }
    vi.stubGlobal('ImageData', TestImageData);
    try {
      const w = 960, h = 72;
      const data = Uint8ClampedArray.from({ length: w * h * 4 }, (_, i) => i % 4 === 3 ? 255 : ((i * 7 + Math.floor(i / (w * 4)) * 29) & 255));
      const source = { width: w, height: h, data };
      const params = { M1: [[.9,.1,0],[.1,.85,.05],[0,.1,.9]], ck: [0,1,2].map(c => Float64Array.from(color.KN, x => x ** (1 + c * .12))) };
      const options: preview.DetailOptions = { filmMtf: true, policy: 'sensor', orientation: 6, halo: 1, colour: 'red', grain: 1, main: { width: w, height: h } };
      const expected = preview.applySlot(params, source as ImageData, true);
      expect(color.filmMtfRgba(expected.data, w, h, 'sensor')).toBe(true);
      const geometry = { policy: 'sensor' as const, main: options.main, picture: { width: w, height: h } };
      halateRgba(expected.data, w, h, 1, undefined, 'red', geometry); color.grainRgb(expected.data, w, h, 1, 4, w, geometry);
      const actual = preview.renderPreviewPixels(source, params, options);
      expect(actual.mtfApplied).toBe(true);
      expect(actual.after).toEqual(pixels.orientPreview(expected, 6));
      expect(actual.before).toEqual(pixels.orientPreview(source, 6));
      const wrongSource = new ImageData(data.slice(), w, h); color.filmMtfRgba(wrongSource.data, w, h, 'sensor');
      const wrongOrder = preview.applySlot(params, wrongSource, true);
      halateRgba(wrongOrder.data, w, h, 1, undefined, 'red', geometry); color.grainRgb(wrongOrder.data, w, h, 1, 4, w, geometry);
      expect(actual.after.data).not.toEqual(pixels.orientPreview(wrongOrder, 6).data);
      // The same small stored raster is excluded by the historical build, and Off changes no source bytes.
      const excluded = preview.renderPreviewPixels(source, undefined, { ...options, policy: undefined, halo: 0, grain: 0, orientation: 1 });
      expect(excluded.mtfApplied).toBe(false); expect(excluded.after.data).toEqual(data);
      expect(source.data).toEqual(data);
    } finally { vi.unstubAllGlobals(); }
  });
});


describe('approved Gold preview metadata', () => {
  const moduleUrl = new URL('../../ui/src/approved-gold.ts', import.meta.url);
  it('uses saved parameters with the existing post-matrix path and never fabricates CIE76', async () => {
    const { existsSync } = await import('node:fs'); expect(existsSync(moduleUrl), 'approved factory must exist').toBe(true);
    const gold = await import(moduleUrl.href);
    const info = { family: 'gr3x', version: '2.10', filename: 'fwdc239b.bin', models: ['GR3'], bridge: false, sha256: 'd6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4', capabilities: { build: true, presets: true }, standardMatrixQ13: [8116,743,-667,15,8598,-421,-244,542,7894] };
    const r = gold.createApprovedGold(info as any, 'GR3')!;
    const saved = {"M1":[[1.0609664581572797,-0.1236873931405216,0.06272093498324176],[0.0560144493881397,0.8473464964015793,0.0966390542102809],[0.13797423545573362,-0.07980902853238755,0.941834793076654]],"ck":[[0.0896157357467401,0.10186681865578108,0.1275010833350745,0.16835926269378026,0.21606341947486327,0.28608917156902997,0.35737156811339066,0.436805031935872,0.5278015788515321,0.6126637381905242,0.6741237730846269,0.7359538986702452,0.7759715577678598,0.8167140072018888,0.85035003278829,0.8877568210279086,0.899241661868901],[0.025493786603441204,0.06589139404379141,0.10845788327856759,0.15528898175161074,0.2128458084539915,0.27531961650663567,0.3476096931185396,0.4146862516636111,0.5046143346561357,0.5944529255640608,0.6669200469353677,0.7199554988191725,0.773146224334547,0.8134273426538644,0.8492566988244435,0.8809501064267611,0.9055369615373172],[0.11440001574401118,0.11617403260174636,0.13682385536862623,0.1672921304560454,0.21089427222481755,0.2682959517868168,0.3305544865061938,0.40043904711415673,0.46907789026519764,0.5439393474841399,0.6103610278042597,0.6614225407136135,0.7062177421416,0.7542530416281723,0.7919774829224516,0.8337094204511402,0.8413941773594036]],"P2":[[1.0845477569965989,0.09357736525447909,-0.1781251222510779],[0.13747820587674173,0.7984581039948029,0.06406369012845536],[0.01201115567272517,0.12165093430130737,0.8663379100259675]]}; const params = { ...saved, ck: saved.ck.map(c => Float64Array.from(c)) };
    class SmallImageData { data: Uint8ClampedArray; width: number; height: number; constructor(w: number, h: number) { this.width = w; this.height = h; this.data = new Uint8ClampedArray(w * h * 4); } }
    vi.stubGlobal('ImageData', SmallImageData);
    try {
      const source = { width: 4, height: 2, data: Uint8ClampedArray.from([30,80,150,255,160,40,20,255,30,180,70,255,230,190,120,255,0,0,0,255,128,128,128,255,250,250,250,255,180,50,190,255]) };
      const actual = preview.applySlot(r.params, source as ImageData, true);
      expect(actual).toEqual(preview.applySlot(params, source as ImageData, true));
      expect(actual.data).not.toEqual(preview.applySlot({ ...params, P2: undefined }, source as ImageData, true).data);
    } finally { vi.unstubAllGlobals(); }
    expect(gold.cie76Fit(r)).toBeUndefined();
    expect(gold.cie76Fit({ ...r, meanDE: 1, p95DE: 2 } as any)).toBeUndefined();
    expect(gold.cie76Fit({ meanDE: 2, p95DE: 5 } as any)).toEqual({ mean: 2, p95: 5 });
    for (const report of [{ meanDE2000: 1, p95DE2000: 2 }, { meanDE: NaN, p95DE: 2 }, { meanDE: 1, p95DE: Infinity }]) expect(gold.cie76Fit(report as any)).toBeUndefined();
  });
});


describe('same-film texture reference', () => {
  class TestImageData {
    data: Uint8ClampedArray<ArrayBuffer>; width: number; height: number;
    constructor(data: number | Uint8ClampedArray<ArrayBuffer>, w: number, h?: number) {
      this.width = typeof data === 'number' ? data : w; this.height = typeof data === 'number' ? w : h!;
      this.data = typeof data === 'number' ? new Uint8ClampedArray(data * w * 4) : data;
    }
  }
  beforeEach(() => vi.stubGlobal('ImageData', TestImageData));
  afterEach(() => vi.unstubAllGlobals());
  function fixture(w = 960, h = 64) {
    const source = { width: w, height: h, data: Uint8ClampedArray.from({ length: w * h * 4 }, (_, i) => i % 4 === 3 ? 255 : (17 + i * 7 + Math.floor(i / (w * 4)) * 29) & 255) };
    const params = color.withTealSky({ M1: [[.9,.1,0],[.05,.9,.05],[0,.1,.9]], ck: [0,1,2].map(c => Float64Array.from(color.KN, x => x ** (1 + c * .12))), P2: [[1.2,-.1,-.1],[-.1,1.2,-.1],[-.06,-.04,1.10]] }, 2);
    const options = { filmMtf: true, policy: 'output' as const, orientation: 1, halo: 1 as const, colour: 'red' as const, grain: 6, main: { width: w, height: h } };
    return { source, params, options };
  }
  const copy = (source: PreviewPixels): PreviewPixels => ({ ...source, data: source.data.slice() });
  const bytesHash = (data: Uint8ClampedArray): string => createHash('sha256').update(data).digest('hex');
  const imageKey = (image: PreviewPixels): string => `${image.width}x${image.height}:${bytesHash(image.data)}`;
  it('uses the same colour/sky/post stage for the left in EXIF 1–8 while preserving the legacy textured right', () => {
    const { source, params, options } = fixture(); const untouched = source.data.slice(), parameters = JSON.stringify(params);
    const colour = preview.applySlot(params, source as ImageData, true);
    expect(bytesHash(colour.data)).not.toBe(bytesHash(preview.applySlot({ ...params, P2: undefined }, source as ImageData, true).data));
    const expected = new ImageData(colour.data.slice(), source.width, source.height);
    expect(color.filmMtfRgba(expected.data, source.width, source.height, options.policy)).toBe(true);
    const geometry = { policy: options.policy, main: options.main, picture: { width: source.width, height: source.height } };
    halateRgba(expected.data, source.width, source.height, options.halo, undefined, options.colour, geometry);
    color.grainRgb(expected.data, source.width, source.height, options.grain, 4, source.width, geometry);
    const legacy = preview.renderPreviewPixels(source, params, options);
    expect(bytesHash(legacy.before.data)).toBe(bytesHash(untouched)); expect(bytesHash(legacy.after.data)).toBe(bytesHash(expected.data)); expect(bytesHash(source.data)).toBe(bytesHash(untouched));
    expect(bytesHash(legacy.after.data)).toBe('09fce6872da0af16daa1cc7aa91e9a00e2faf05352fd690399c148096fb2d07e');
    for (let orientation = 1; orientation <= 8; orientation++) {
      const owned = copy(source);
      const result = preview.renderPreviewPixels(owned, params, { ...options, orientation, reference: 'colour' } as preview.DetailOptions);
      expect(imageKey(result.before)).toBe(imageKey(pixels.orientPreview(colour, orientation)));
      expect(imageKey(result.after)).toBe(imageKey(pixels.orientPreview(expected, orientation))); expect(result.mtfApplied).toBe(true);
      expect(bytesHash(owned.data)).toBe(bytesHash(colour.data)); expect(result.before.data.buffer).not.toBe(result.after.data.buffer);
    }
    expect(bytesHash(source.data)).toBe(bytesHash(untouched)); expect(JSON.stringify(params)).toBe(parameters);
  });
  it('returns equal film-colour sides when all app-added textures are Off', () => {
    const { source, params, options } = fixture(8, 4), colour = preview.applySlot(params, source as ImageData, true);
    const result = preview.renderPreviewPixels(copy(source), params, { ...options, filmMtf: false, halo: 0, grain: 0, orientation: 7, reference: 'colour' } as preview.DetailOptions);
    expect(result.before).toEqual(pixels.orientPreview(colour, 7)); expect(result.before).toEqual(result.after); expect(result.mtfApplied).toBe(false);
  });
  it('consumes only the owned input colour bytes with no additional full RGBA allocation or output alias', () => {
    const { source, params, options } = fixture(16, 8), n = source.data.length;
    const expectedColour = preview.applySlot(params, source as ImageData, true).data, Native = Uint8ClampedArray;
    const allocated: Uint8ClampedArray[] = [];
    vi.stubGlobal('Uint8ClampedArray', new Proxy(Native, { construct(target, args) {
      const array = Reflect.construct(target, args) as Uint8ClampedArray;
      if (array.length === n) allocated.push(array); return array;
    } }));
    const owned = copy(source); allocated.length = 0;
    const ordinary = preview.renderPreviewPixels(source, params, { ...options, filmMtf: false });
    const ordinaryAllocations = allocated.length; allocated.length = 0;
    const result = preview.renderPreviewPixels(owned, params, { ...options, filmMtf: false, reference: 'colour' } as preview.DetailOptions);
    expect(allocated).toHaveLength(ordinaryAllocations); expect(ordinaryAllocations).toBe(3); // colour output + two existing orientation outputs
    expect(owned.data).toEqual(expectedColour); expect(source.data).not.toEqual(expectedColour);
    expect(result.after).toEqual(ordinary.after); expect(result.before.data).toEqual(expectedColour);
    expect(result.before.data.buffer).not.toBe(result.after.data.buffer); expect(result.before.data.buffer).not.toBe(owned.data.buffer);
  });
  it('keeps the omitted and explicit Source defaults pure and fails closed without colour parameters', () => {
    const { source, params, options } = fixture(16, 8), untouched = source.data.slice();
    const omitted = preview.renderPreviewPixels(source, params, { ...options, filmMtf: false });
    const explicit = preview.renderPreviewPixels(source, params, { ...options, filmMtf: false, reference: 'source' } as preview.DetailOptions);
    expect(explicit).toEqual(omitted); expect(source.data).toEqual(untouched);
    const missing = preview.renderPreviewPixels(source, undefined, { ...options, filmMtf: false, reference: 'colour' } as preview.DetailOptions);
    expect(missing.before.data).toEqual(untouched); expect(source.data).toEqual(untouched);
  });
  it('cancels obsolete mode/source/parameter jobs and transfers only the current owned decode', async () => {
    const workers: any[] = [], decode = vi.fn(async () => ({ width: 2, height: 2, data: new Uint8ClampedArray(16) }));
    const renderer = preview.createDetailRenderer(decode, () => { const worker = { postMessage: vi.fn(), terminate: vi.fn(), onmessage: null, onerror: null }; workers.push(worker); return worker; });
    const { params, options } = fixture(2, 2); const original = { blob: new Blob(['first']), width: 2, height: 2, orientation: 1 };
    const first = renderer.render(original, params, options).catch(e => e.name); await vi.waitFor(() => expect(workers).toHaveLength(1));
    const second = renderer.render(original, params, { ...options, reference: 'colour' } as preview.DetailOptions).catch(e => e.name); await vi.waitFor(() => expect(workers).toHaveLength(2));
    const final = renderer.render({ ...original, blob: new Blob(['replacement']) }, { ...params, M1: [[1,0,0],[0,1,0],[0,0,1]] }, { ...options, reference: 'colour' } as preview.DetailOptions); await vi.waitFor(() => expect(workers).toHaveLength(3));
    expect(await first).toBe('AbortError'); expect(await second).toBe('AbortError'); expect(workers[0].terminate).toHaveBeenCalledOnce(); expect(workers[1].terminate).toHaveBeenCalledOnce();
    const [message, transfer] = workers[2].postMessage.mock.calls[0]; expect(message.options.reference).toBe('colour'); expect(transfer).toEqual([message.source.data.buffer]); expect(decode).toHaveBeenCalledTimes(3);
    const result = { before: { width: 2, height: 2, data: new Uint8ClampedArray(16) }, after: { width: 2, height: 2, data: new Uint8ClampedArray(16) }, mtfApplied: false };
    workers[0].onmessage({ data: { result: { ...result, mtfApplied: true } } }); workers[1].onmessage({ data: { result: { ...result, mtfApplied: true } } }); workers[2].onmessage({ data: { result } });
    expect(await final).toBe(result); expect(workers[2].terminate).toHaveBeenCalledOnce(); expect(original.blob.size).toBe(5);
  });
  it('recovers the serialized decode queue after an error for the next reference job', async () => {
    const decode = vi.fn().mockRejectedValueOnce(new Error('bad decode')).mockResolvedValue({ width: 2, height: 2, data: new Uint8ClampedArray(16) });
    const worker: any = { postMessage: vi.fn(), terminate: vi.fn(), onmessage: null, onerror: null }, factory = vi.fn(() => worker);
    const renderer = preview.createDetailRenderer(decode, factory); const { params, options } = fixture(2, 2);
    await expect(renderer.render({} as any, params, options)).rejects.toThrow('bad decode'); expect(factory).not.toHaveBeenCalled();
    const pending = renderer.render({} as any, params, { ...options, reference: 'colour' } as preview.DetailOptions); await vi.waitFor(() => expect(worker.postMessage).toHaveBeenCalledOnce());
    const result = { before: { width: 2, height: 2, data: new Uint8ClampedArray(16) }, after: { width: 2, height: 2, data: new Uint8ClampedArray(16) }, mtfApplied: false };
    worker.onmessage({ data: { result } }); expect(await pending).toBe(result); expect(decode).toHaveBeenCalledTimes(2); expect(worker.terminate).toHaveBeenCalledOnce();
  });
});


describe('bounded comparison crop', () => {
  const moduleUrl = new URL('../../ui/src/comparison-crop.ts', import.meta.url);
  async function cropModule() {
    const { existsSync } = await import('node:fs');
    expect(existsSync(moduleUrl), 'new bounded comparison helper must exist').toBe(true);
    return import(moduleUrl.href);
  }
  const text = () => ({ title: 'Centre 100%', left: 'Film colour', right: 'Colour + texture', lines: ['Source', 'Film 1', 'Alias', 'Geometry', 'Sky', 'MTF', 'Grain', 'Halo', 'Software limits'] });
  function plane(w: number, h: number, seed = 0) {
    return { width: w, height: h, data: Uint8ClampedArray.from({ length: w * h * 4 }, (_, i) => (i * 29 + Math.floor(i / (w * 4)) * 17 + seed) & 255) };
  }
  const deferred = <T,>() => { let resolve!: (v: T) => void, reject!: (e: Error) => void; const promise = new Promise<T>((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };
  const encoded = Uint8Array.from([137,80,78,71,13,10,26,10,1,2,3]);
  const digest = (data: Uint8Array | Uint8ClampedArray) => createHash('sha256').update(data).digest('hex');
  function api() {
    return { encode: vi.fn(async () => new Blob([encoded], { type: 'image/png' })), sha256: vi.fn(async (bytes: Uint8Array) => digest(bytes)), pickDirectory: vi.fn(async () => 'C:/chosen'),
      sep: '/', join: vi.fn(function(this: { sep: string }, dir: string, name: string) { return dir + this.sep + name; }),
      write: vi.fn(async (_path: string, bytes: Uint8Array) => ({ size: bytes.length, sha256: digest(bytes) })) };
  }
  it('copies exact centred native RGBA for odd, portrait, edge and smaller shapes without aliasing or touching canaries', async () => {
    const c = await cropModule();
    for (const [w,h] of [[533,701],[721,3],[1,1],[512,512],[513,513]]) {
      const backing = new Uint8ClampedArray(w*h*4+8).fill(177), a = plane(w,h), b = plane(w,h,31); backing.set(a.data,4); a.data = backing.subarray(4,-4);
      const snapshot = c.captureComparisonCrop(a,b,text()), cw = Math.min(512,w), ch = Math.min(512,h), x = Math.floor((w-cw)/2), y = Math.floor((h-ch)/2);
      expect([snapshot.width,snapshot.height,snapshot.x,snapshot.y]).toEqual([cw,ch,x,y]);
      for (const [patch,source] of [[snapshot.before,a.data],[snapshot.after,b.data]]) {
        const expected = new Uint8ClampedArray(cw*ch*4);
        for (let row=0;row<ch;row++) for(let col=0;col<cw;col++) for(let channel=0;channel<4;channel++) expected[(row*cw+col)*4+channel]=source[((y+row)*w+x+col)*4+channel];
        expect(digest(patch)).toBe(digest(expected)); expect(patch.buffer).not.toBe(source.buffer);
      }
      expect([...backing.subarray(0,4),...backing.subarray(-4)]).toEqual(Array(8).fill(177)); const frozen=digest(snapshot.before); a.data.fill(0); expect(digest(snapshot.before)).toBe(frozen);
      const layout=c.comparisonCropLayout(snapshot); expect(layout.width*layout.height*4).toBeLessThan(4*1024*1024); expect(layout.left.y).toBeGreaterThan(200); expect(layout.right.x).toBeGreaterThanOrEqual(layout.left.x+cw);
    }
  });
  it('refuses malformed or mismatched full planes and bounds arbitrary annotation text before async use', async () => {
    const c=await cropModule(), good=plane(2,2);
    for(const bad of [{...good,width:0},{...good,width:1.5},{...good,height:NaN},{...good,width:12001},{...good,width:12000,height:12000},{...good,data:new Uint8ClampedArray(15)},{...good,data:new Uint8Array(16)}]) expect(()=>c.captureComparisonCrop(bad,good,text())).toThrow();
    expect(()=>c.captureComparisonCrop(good,plane(3,2),text())).toThrow();
    const labels=text();labels.title='Z'.repeat(10000);labels.lines=Array(100).fill('name\nwith\u0000controls '+ 'x'.repeat(10000));
    const snapshot=c.captureComparisonCrop(good,good,labels);labels.lines[0]='mutated';expect(snapshot.text.lines).toHaveLength(9);expect(snapshot.text.lines[0]).not.toMatch(/[\n\u0000]/);expect(snapshot.text.lines[0].length).toBeLessThan(200);expect(snapshot.text.title.length).toBeLessThan(200);
  });
  it('composes exact pixel patches with bounded annotations outside them and no scaled drawing', async () => {
    const c=await cropModule(), snapshot=c.captureComparisonCrop(plane(7,5),plane(7,5,90),text());
    const puts:any[]=[],draw=vi.fn(),strings:any[]=[];
    const ctx={fillStyle:'',font:'',textBaseline:'',fillRect:vi.fn(),measureText:(v:string)=>({width:v.length*7}),fillText:(...args:any[])=>strings.push(args),putImageData:(...args:any[])=>puts.push(args),drawImage:draw};
    const canvas={width:0,height:0,getContext:()=>ctx,toBlob:(cb:(blob:Blob)=>void,type:string)=>cb(new Blob([encoded],{type}))};
    class TinyImageData { constructor(public data:Uint8ClampedArray,public width:number,public height:number){} }
    vi.stubGlobal('document',{createElement:()=>canvas});vi.stubGlobal('ImageData',TinyImageData);
    try { const blob=await c.encodeComparisonCrop(snapshot),layout=c.comparisonCropLayout(snapshot);expect(blob.type).toBe('image/png');expect([canvas.width,canvas.height]).toEqual([layout.width,layout.height]);expect(draw).not.toHaveBeenCalled();expect(puts).toHaveLength(2);
      expect(puts[0].slice(1)).toEqual([layout.left.x,layout.left.y]);expect(puts[1].slice(1)).toEqual([layout.right.x,layout.right.y]);expect(digest(puts[0][0].data)).toBe(digest(snapshot.before));expect(digest(puts[1][0].data)).toBe(digest(snapshot.after));expect(strings.every((row:any[])=>row[2]<layout.left.y)).toBe(true);
    } finally { vi.unstubAllGlobals(); }
  });
  it('saves one independently verified generated PNG path and prevents concurrent actions without metadata paths', async () => {
    const c=await cropModule(), a=api(), held=deferred<Blob>();a.encode.mockImplementationOnce(()=>held.promise);const saver=c.createComparisonCropSaver(a), snapshot=c.captureComparisonCrop(plane(2,2),plane(2,2,1),text()),owner={};
    const first=saver.save(snapshot,owner,()=>true);expect(await saver.save(snapshot,owner,()=>true)).toEqual({kind:'busy'});expect(a.encode).toHaveBeenCalledOnce();held.resolve(new Blob([encoded],{type:'image/png'}));const result=await first;
    expect(result.kind).toBe('saved');expect(result.path).toMatch(/^C:\/chosen\/comparison-centre-[a-z0-9-]+\.png$/);expect(a.write).toHaveBeenCalledOnce();expect(a.join).toHaveBeenCalledOnce();expect(a.sha256).toHaveBeenCalledWith(encoded);expect(a.write.mock.calls[0][1]).toEqual(encoded);
  });
  it('rejects stale ownership after encode, blob read or digest before opening the picker', async () => {
    const c=await cropModule(), snapshot=c.captureComparisonCrop(plane(2,2),plane(2,2),text());
    for(const phase of ['encode','blob','digest']) {
      const a=api(),held=deferred<any>();let live=true;
      if(phase==='encode')a.encode.mockImplementationOnce(()=>held.promise);
      if(phase==='blob')a.encode.mockResolvedValueOnce({size:encoded.length,type:'image/png',arrayBuffer:()=>held.promise} as Blob);
      if(phase==='digest')a.sha256.mockImplementationOnce(()=>held.promise);
      const pending=c.createComparisonCropSaver(a).save(snapshot,{},()=>live);await vi.waitFor(()=>expect(phase==='digest'?a.sha256:a.encode).toHaveBeenCalledOnce());await Promise.resolve();live=false;
      held.resolve(phase==='encode'?new Blob([encoded],{type:'image/png'}):phase==='blob'?encoded.buffer:digest(encoded));expect(await pending).toEqual({kind:'stale'});expect(a.pickDirectory).not.toHaveBeenCalled();expect(a.write).not.toHaveBeenCalled();
    }
  });
  it('does not dispatch after picker cancellation, stale picker or a last synchronous owner change', async () => {
    const c=await cropModule(),snapshot=c.captureComparisonCrop(plane(2,2),plane(2,2),text());
    const cancelled=api();cancelled.pickDirectory.mockResolvedValueOnce('');expect(await c.createComparisonCropSaver(cancelled).save(snapshot,{},()=>true)).toEqual({kind:'cancelled'});expect(cancelled.write).not.toHaveBeenCalled();
    const a=api(),held=deferred<string>();let live=true;a.pickDirectory.mockImplementationOnce(()=>held.promise);const pending=c.createComparisonCropSaver(a).save(snapshot,{},()=>live);await vi.waitFor(()=>expect(a.pickDirectory).toHaveBeenCalledOnce());live=false;held.resolve('C:/chosen');expect(await pending).toEqual({kind:'stale'});expect(a.write).not.toHaveBeenCalled();
    const b=api();live=true;b.join.mockImplementationOnce(()=>{live=false;return 'C:/chosen/generated.png';});expect(await c.createComparisonCropSaver(b).save(snapshot,{},()=>live)).toEqual({kind:'stale'});expect(b.write).not.toHaveBeenCalled();
  });
  it('always verifies a dispatched captured file despite a later preview change, including wrong digest or size', async () => {
    const c=await cropModule(),snapshot=c.captureComparisonCrop(plane(2,2),plane(2,2),text());
    for(const response of [{size:encoded.length,sha256:digest(encoded)},{size:encoded.length+1,sha256:digest(encoded)},{size:encoded.length,sha256:'0'.repeat(64)}]) {
      const a=api(),held=deferred<any>();let live=true;a.write.mockImplementationOnce(()=>held.promise);const pending=c.createComparisonCropSaver(a).save(snapshot,{},()=>live);await vi.waitFor(()=>expect(a.write).toHaveBeenCalledOnce());live=false;held.resolve(response);const result=await pending;
      expect(result.kind).toBe(response.size===encoded.length&&response.sha256===digest(encoded)?'saved':'unverified');expect(result.path).toBe(a.write.mock.calls[0][0]);expect(a.sha256).toHaveBeenCalledOnce();
    }
  });
  it('reports honest preparation/write failures and releases singleflight for a fresh recovery', async () => {
    const c=await cropModule(),snapshot=c.captureComparisonCrop(plane(2,2),plane(2,2),text()),a=api(),saver=c.createComparisonCropSaver(a);
    a.encode.mockRejectedValueOnce(new Error('encode'));expect(await saver.save(snapshot,{},()=>true)).toEqual({kind:'prepare-failed'});expect(a.pickDirectory).not.toHaveBeenCalled();expect(a.write).not.toHaveBeenCalled();
    a.write.mockRejectedValueOnce(new Error('write may have reached backend'));expect((await saver.save(snapshot,{},()=>true)).kind).toBe('unverified');expect((await saver.save(snapshot,{},()=>true)).kind).toBe('saved');expect(a.write).toHaveBeenCalledTimes(2);
  });
  it('refuses null, non-PNG, oversized or inconsistently encoded data and an invalid digest without opening a picker', async () => {
    const c=await cropModule(),snapshot=c.captureComparisonCrop(plane(2,2),plane(2,2),text());
    for(const blob of [null,new Blob([encoded],{type:'image/jpeg'}),new Blob([new Uint8Array(4*1024*1024+1)],{type:'image/png'}),{type:'image/png',size:99,arrayBuffer:async()=>encoded.buffer}]){
      const a=api();a.encode.mockResolvedValueOnce(blob as Blob);expect(await c.createComparisonCropSaver(a).save(snapshot,{},()=>true)).toEqual({kind:'prepare-failed'});expect(a.pickDirectory).not.toHaveBeenCalled();expect(a.write).not.toHaveBeenCalled();
    }
    const a=api();a.sha256.mockResolvedValueOnce('not a digest');expect(await c.createComparisonCropSaver(a).save(snapshot,{},()=>true)).toEqual({kind:'prepare-failed'});expect(a.pickDirectory).not.toHaveBeenCalled();expect(a.write).not.toHaveBeenCalled();
  });
  it('keeps unrelated store updates live but refuses relevant source, recipe, main or mode transitions before paint', async () => {
    const c=await cropModule(), owner=c.createComparisonCropOwner(), snapshot=c.captureComparisonCrop(plane(2,2),plane(2,2),text());
    const relevant={photoRev:1,model:'GR3',info:{},raw:{},original:{},slot:'CY',slotState:{},result:{},main:true,policy:'sensor',lang:'en',eligible:true,mode:{},ready:{}};
    let state={...relevant,volume:1,toast:'first'};
    const read=()=>owner.sample([state.photoRev,state.model,state.info,state.raw,state.original,state.slot,state.slotState,state.result,state.main,state.policy,state.lang,state.eligible,state.mode,state.ready]);
    const first=read();state={...state,volume:2,toast:'another'};expect(read()).toBe(first);
    const a=api(),held=deferred<string>();a.pickDirectory.mockImplementationOnce(()=>held.promise);const pending=c.createComparisonCropSaver(a).save(snapshot,first,(key:object)=>read()===key);
    await vi.waitFor(()=>expect(a.pickDirectory).toHaveBeenCalledOnce());state={...state,volume:3,toast:'poll'};held.resolve('C:/chosen');expect((await pending).kind).toBe('saved');
    for(const field of ['photoRev','slotState','main','mode'] as const){
      state={...relevant,volume:1,toast:''};const key=read(),b=api(),wait=deferred<string>();b.pickDirectory.mockImplementationOnce(()=>wait.promise);
      const p=c.createComparisonCropSaver(b).save(snapshot,key,(k:object)=>read()===k);await vi.waitFor(()=>expect(b.pickDirectory).toHaveBeenCalledOnce());
      const old=state[field];state={...state,[field]:field==='photoRev'?2:field==='main'?false:{}};expect(read()).not.toBe(key);
      state={...state,[field]:old};expect(read()).not.toBe(key); // observed change and return cannot revive the old action
      wait.resolve('C:/chosen');expect(await p).toEqual({kind:'stale'});expect(b.write).not.toHaveBeenCalled();
    }
  });
  it('keeps one pending write across two saver consumer lifetimes until verification settles', async () => {
    const c=await cropModule(),a=api(),snapshot=c.captureComparisonCrop(plane(2,2),plane(2,2),text()),held=deferred<any>();
    a.write.mockImplementation(()=>held.promise);let mounted=true;const first=c.createComparisonCropSaver(a).save(snapshot,{},()=>mounted);let second:Promise<any>|undefined;
    try {
      for(let i=0;i<16;i++)await Promise.resolve();expect(a.write).toHaveBeenCalledOnce();mounted=false;
      second=c.createComparisonCropSaver(a).save(snapshot,{},()=>true);for(let i=0;i<16;i++)await Promise.resolve();
      expect(a.write).toHaveBeenCalledTimes(1); // old per-instance guard dispatches two before either settles
    } finally {held.resolve({size:encoded.length,sha256:digest(encoded)});await Promise.all([first,second]);}
    expect((await first).kind).toBe('saved');expect((await second).kind).toBe('busy');
    a.write.mockResolvedValue({size:encoded.length,sha256:digest(encoded)});expect((await c.createComparisonCropSaver(a).save(snapshot,{},()=>true)).kind).toBe('saved');
  });
  it('publishes shared busy state to a newly mounted consumer and unlocks only after the dispatched verification settles', async () => {
    const c=await cropModule(),a=api(),snapshot=c.captureComparisonCrop(plane(2,2),plane(2,2),text()),held=deferred<any>();
    expect(c.comparisonCropSaving()).toBe(false);a.write.mockImplementationOnce(()=>held.promise);const oldNotices:boolean[]=[],newNotices:boolean[]=[];
    const offOld=c.subscribeComparisonCropSaving(()=>oldNotices.push(c.comparisonCropSaving()));let offNew=()=>{};
    const pending=c.createComparisonCropSaver(a).save(snapshot,{},()=>true);
    try {
      for(let i=0;i<16;i++)await Promise.resolve();expect(a.write).toHaveBeenCalledOnce();offOld();
      expect(c.comparisonCropSaving()).toBe(true);offNew=c.subscribeComparisonCropSaving(()=>newNotices.push(c.comparisonCropSaving()));
      expect(await c.createComparisonCropSaver(a).save(snapshot,{},()=>true)).toEqual({kind:'busy'});expect(c.comparisonCropSaving()).toBe(true);expect(newNotices).toEqual([]);
    }finally{held.resolve({size:encoded.length+1,sha256:digest(encoded)});await pending;offOld();offNew();}
    expect((await pending).kind).toBe('unverified');expect(c.comparisonCropSaving()).toBe(false);expect(oldNotices).toEqual([true]);expect(newNotices).toEqual([false]);
  });
  it('refuses held pre-dispatch actions immediately on page departure, app unreadiness or layout unmount', async () => {
    const c=await cropModule(),snapshot=c.captureComparisonCrop(plane(2,2),plane(2,2),text());
    for(const change of ['page','ready','mounted']){
      const a=api(),held=deferred<string>(),owner=c.createComparisonCropOwner();let context={ready:true,page:'ic',mounted:true};
      const read=()=>owner.sample([context.ready,context.page,context.mounted,c.comparisonCropContextReady(context.ready,context.page,context.mounted)]),key=read();
      a.pickDirectory.mockImplementationOnce(()=>held.promise);const pending=c.createComparisonCropSaver(a).save(snapshot,key,(k:object)=>c.comparisonCropContextReady(context.ready,context.page,context.mounted)&&read()===k);
      try {for(let i=0;i<16;i++)await Promise.resolve();expect(a.pickDirectory).toHaveBeenCalledOnce();context={...context,[change]:change==='page'?'ratio':false};expect(c.comparisonCropContextReady(context.ready,context.page,context.mounted)).toBe(false);}
      finally{held.resolve('C:/chosen');await pending;}
      expect(await pending).toEqual({kind:'stale'});expect(a.write).not.toHaveBeenCalled();expect(c.comparisonCropSaving()).toBe(false);
    }
  });
});
