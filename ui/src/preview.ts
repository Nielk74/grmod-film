/// <reference types="vite/client" />
// Before / after preview of a slot on a photograph. The picture is assumed to be what the camera's
// Standard preset produced (sRGB); the slot model is applied to it with lookup tables.
import { color, halateRgba } from '@grmod/core';
import { decodeStoredPreview, orientPreview } from './pixels';
import type { PreviewOriginal, PreviewPixels } from './pixels';

/** Sharp on high-density screens, and the 1:1 loupe shows real detail (the samples are 2400 wide). */
export const PREVIEW_MAX = 2400;

/** One source pixel per physical screen pixel; width is measured after the app's CSS scale. */
export function loupeScale(sourceWidth: number, displayedWidth: number, dpr: number): number {
  return sourceWidth > 0 && displayedWidth > 0 && dpr > 0 ? sourceWidth / (displayedWidth * dpr) : 1;
}

/** Decode a picture and scale it to at most PREVIEW_MAX pixels on the long side. */
export async function decodePreview(bytes: Uint8Array | Blob): Promise<ImageData> {
  const blob = bytes instanceof Blob ? bytes : new Blob([bytes as unknown as BlobPart]);
  const bmp = await createImageBitmap(blob, { imageOrientation: 'from-image' });
  try {
    const scale = Math.min(1, PREVIEW_MAX / Math.max(bmp.width, bmp.height));
    const w = Math.max(1, Math.round(bmp.width * scale)); const h = Math.max(1, Math.round(bmp.height * scale));
    const c = document.createElement('canvas'); c.width = w; c.height = h;
    const g = c.getContext('2d', { willReadFrequently: true })!;
    g.imageSmoothingEnabled = true; g.imageSmoothingQuality = 'high';
    // halve repeatedly first: a single large reduction aliases
    let src: CanvasImageSource = bmp; let sw = bmp.width; let sh = bmp.height;
    while (sw / 2 >= w * 1.5) {
      const t = document.createElement('canvas'); t.width = Math.round(sw / 2); t.height = Math.round(sh / 2);
      const tg = t.getContext('2d')!; tg.imageSmoothingQuality = 'high'; tg.drawImage(src, 0, 0, sw, sh, 0, 0, t.width, t.height);
      src = t; sw = t.width; sh = t.height;
    }
    g.drawImage(src, 0, 0, sw, sh, 0, 0, w, h);
    return g.getImageData(0, 0, w, h);
  } finally { bmp.close(); }
}

const TAB = 8192;
const inverseTables = new Map<boolean, Float64Array>();

/** The slot applied to every pixel of `src` (RGBA, 8 bit). */
export function applySlot(params: color.SlotParams, src: ImageData, gr3x = false): ImageData {
  const camera = gr3x ? color.GR3X_CAMERA : color;
  if (!inverseTables.has(gr3x)) inverseTables.set(gr3x, Float64Array.from({ length: 256 }, (_, i) => camera.Sinv(i / 255)));
  const sinv = inverseTables.get(gr3x)!;
  // per channel: linear value after the matrix -> 8-bit output of curve_c(S(l))
  const KN = color.KN; const n = KN.length;
  const tabs = params.ck.map((ck) => {
    const t = new Uint8ClampedArray(TAB + 1);
    for (let k = 0; k <= TAB; k++) {
      const b = camera.S(k / TAB);
      let o: number;
      if (b >= 1) o = ck[n - 1];
      else { const j = Math.min(n - 2, Math.floor(b * (n - 1))); o = ck[j] + ((ck[j + 1] - ck[j]) * (b - KN[j])) / (KN[j + 1] - KN[j]); }
      t[k] = Math.round((o < 0 ? 0 : o > 1 ? 1 : o) * 255);
    }
    return t;
  });
  const [m0, m1, m2] = params.M1;
  const a = m0[0] * TAB, b = m0[1] * TAB, c = m0[2] * TAB, d = m1[0] * TAB, e = m1[1] * TAB, f = m1[2] * TAB, g = m2[0] * TAB, h = m2[1] * TAB, i = m2[2] * TAB;
  const [tr, tg, tb] = tabs;
  const s = src.data; const out = new ImageData(src.width, src.height); const o = out.data;
  if (params.P2) return applyWithPost(params, s, out, sinv, [a, b, c, d, e, f, g, h, i]);
  for (let p = 0; p < s.length; p += 4) {
    const r = sinv[s[p]], gg = sinv[s[p + 1]], bb = sinv[s[p + 2]];
    let x = a * r + b * gg + c * bb, y = d * r + e * gg + f * bb, z = g * r + h * gg + i * bb;
    x = x < 0 ? 0 : x > TAB ? TAB : x; y = y < 0 ? 0 : y > TAB ? TAB : y; z = z < 0 ? 0 : z > TAB ? TAB : z;
    o[p] = tr[(x + 0.5) | 0]; o[p + 1] = tg[(y + 0.5) | 0]; o[p + 2] = tb[(z + 0.5) | 0]; o[p + 3] = 255;
  }
  return out;
}

/** As above, with the post-curve matrix: the curve outputs stay fractional until P2 is applied. */
function applyWithPost(params: color.SlotParams, s: Uint8ClampedArray, out: ImageData, sinv: Float64Array, m: number[]): ImageData {
  const KN = color.KN; const n = KN.length;
  const tabs = params.ck.map((ck) => {
    const t = new Float32Array(TAB + 1);
    for (let k = 0; k <= TAB; k++) {
      const b = color.S(k / TAB);
      let o: number;
      if (b >= 1) o = ck[n - 1];
      else { const j = Math.min(n - 2, Math.floor(b * (n - 1))); o = ck[j] + ((ck[j + 1] - ck[j]) * (b - KN[j])) / (KN[j + 1] - KN[j]); }
      t[k] = o < 0 ? 0 : o > 1 ? 1 : o;
    }
    return t;
  });
  const [tr, tg, tb] = tabs;
  const [q0, q1, q2] = params.P2!;
  const o = out.data;
  const clip = (v: number): number => (v <= 0 ? 0 : v >= 1 ? 255 : Math.round(v * 255));
  for (let p = 0; p < s.length; p += 4) {
    const r = sinv[s[p]], gg = sinv[s[p + 1]], bb = sinv[s[p + 2]];
    let x = m[0] * r + m[1] * gg + m[2] * bb, y = m[3] * r + m[4] * gg + m[5] * bb, z = m[6] * r + m[7] * gg + m[8] * bb;
    x = x < 0 ? 0 : x > TAB ? TAB : x; y = y < 0 ? 0 : y > TAB ? TAB : y; z = z < 0 ? 0 : z > TAB ? TAB : z;
    const vr = tr[(x + 0.5) | 0], vg = tg[(y + 0.5) | 0], vb = tb[(z + 0.5) | 0];
    o[p] = clip(q0[0] * vr + q0[1] * vg + q0[2] * vb);
    o[p + 1] = clip(q1[0] * vr + q1[1] * vg + q1[2] * vb);
    o[p + 2] = clip(q2[0] * vr + q2[1] * vg + q2[2] * vb);
    o[p + 3] = 255;
  }
  return out;
}

export interface DetailOptions {
  filmMtf: boolean; policy?: 'sensor' | 'output'; orientation: number;
  /** Opt-in only: the worker-owned input is consumed as the pre-texture colour reference. */
  reference?: 'source' | 'colour';
  halo: 0 | 1 | 2 | 3; light?: Parameters<typeof halateRgba>[4]; colour: 'red' | 'orange' | 'gold' | 'white'; grain: number;
  /** Main sensor raster is explicit; a resized/cropped JPEG cannot establish it. */
  main: { width: number; height: number };
}
export interface DetailResult { before: PreviewPixels; after: PreviewPixels; mtfApplied: boolean }

/** Full stored raster: colour → MTF → halo → grain; only then display orientation.
 * Colour reference consumes only the worker's transferred private source; default calls preserve it. */
export function renderPreviewPixels(source: PreviewPixels, params: color.SlotParams | undefined, options: DetailOptions): DetailResult {
  const out = params ? applySlot(params, new ImageData(source.data, source.width, source.height), true) : new ImageData(source.data.slice(), source.width, source.height);
  if (options.reference === 'colour' && params) source.data.set(out.data);
  const mtfApplied = options.filmMtf && color.filmMtfRgba(out.data, out.width, out.height, options.policy);
  const geometry = options.policy ? { policy: options.policy, main: options.main, picture: { width: source.width, height: source.height } } : undefined;
  if (options.halo) halateRgba(out.data, out.width, out.height, options.halo, options.light, options.colour, geometry);
  if (options.grain) color.grainRgb(out.data, out.width, out.height, options.grain, 4, out.width, geometry);
  return { before: orientPreview(source, options.orientation), after: orientPreview(out, options.orientation), mtfApplied };
}

type DetailWorker = Pick<Worker, 'postMessage' | 'terminate' | 'onmessage' | 'onerror'>;
/** One worker per current job: terminate makes cancellation responsive even inside a synchronous pixel stage. */
export function createDetailRenderer(
  decode: (original: PreviewOriginal) => Promise<PreviewPixels> = decodeStoredPreview,
  factory: () => DetailWorker = () => {
    if (import.meta.env.DEV) return new Worker(new URL('./preview.worker.ts', import.meta.url), { type: 'module' });
    return new Worker(new URL('./preview.worker.ts', import.meta.url));
  },
): { render: (original: PreviewOriginal, params: color.SlotParams | undefined, options: DetailOptions) => Promise<DetailResult>; cancel: () => void } {
  let generation = 0, worker: DetailWorker | undefined, rejectPending: ((reason: Error) => void) | undefined;
  let decodeQueue = Promise.resolve();
  const cancel = (): void => {
    generation++; worker?.terminate(); worker = undefined;
    const reject = rejectPending; rejectPending = undefined;
    if (reject) { const e = new Error('Preview cancelled'); e.name = 'AbortError'; reject(e); }
  };
  return {
    cancel,
    render(original, params, options) {
      cancel(); const token = generation;
      return new Promise<DetailResult>((resolve, reject) => {
        rejectPending = reject;
        decodeQueue = decodeQueue.then(async () => {
          // A bitmap decode already in flight cannot be aborted, but cancelled queued jobs never allocate a raster.
          if (token !== generation) return;
          const source = await decode(original);
          if (token !== generation) return;
          const current = factory(); worker = current;
          current.onmessage = (event: MessageEvent<{ result?: DetailResult; error?: string }>) => {
            if (token !== generation) return;
            current.terminate(); worker = undefined; rejectPending = undefined;
            if (event.data.result) resolve(event.data.result); else reject(new Error(event.data.error || 'Preview failed'));
          };
          current.onerror = () => { if (token === generation) { current.terminate(); worker = undefined; rejectPending = undefined; reject(new Error('Preview worker failed')); } };
          current.postMessage({ source, params, options }, [source.data.buffer as ArrayBuffer]);
        }).catch(error => { if (token === generation) { worker?.terminate(); worker = undefined; rejectPending = undefined; reject(error); } });
      });
    },
  };
}
