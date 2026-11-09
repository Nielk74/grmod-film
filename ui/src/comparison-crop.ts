/** Bounded export of an already rendered pair. No renderer, store or full-raster cache. */
export interface CropPlane { width: number; height: number; data: Uint8ClampedArray }
export interface CropText { title: string; left: string; right: string; lines: readonly string[] }
export interface ComparisonCrop {
  width: number; height: number; x: number; y: number; displayWidth: number; displayHeight: number;
  before: Uint8ClampedArray<ArrayBuffer>; after: Uint8ClampedArray<ArrayBuffer>; text: CropText;
}
const MAX_BYTES = 4 * 1024 * 1024;
const boundedText = (value: string): string => {
  const prefix = String(value).slice(0, 720).replace(/[\u0000-\u001f\u007f-\u009f]/g, ' ');
  const chars = Array.from(prefix);
  return chars.length > 180 ? chars.slice(0, 179).join('') + '…' : prefix;
};
function validPlane(p: CropPlane): boolean {
  return Number.isInteger(p.width) && Number.isInteger(p.height) && p.width > 0 && p.height > 0 &&
    p.width <= 12000 && p.height <= 12000 && p.width * p.height <= 24000000 &&
    p.data instanceof Uint8ClampedArray && p.data.length === p.width * p.height * 4;
}
export function captureComparisonCrop(before: CropPlane, after: CropPlane, text: CropText): ComparisonCrop {
  if (!validPlane(before) || !validPlane(after) || before.width !== after.width || before.height !== after.height) throw new Error('Invalid comparison planes');
  const width = Math.min(512, before.width), height = Math.min(512, before.height);
  const x = Math.floor((before.width - width) / 2), y = Math.floor((before.height - height) / 2);
  const copy = (p: CropPlane): Uint8ClampedArray<ArrayBuffer> => {
    const out = new Uint8ClampedArray(width * height * 4);
    for (let row = 0; row < height; row++) {
      const start = ((y + row) * p.width + x) * 4;
      out.set(p.data.subarray(start, start + width * 4), row * width * 4);
    }
    return out;
  };
  return { width, height, x, y, displayWidth: before.width, displayHeight: before.height, before: copy(before), after: copy(after),
    text: { title: boundedText(text.title), left: boundedText(text.left), right: boundedText(text.right), lines: text.lines.slice(0, 9).map(boundedText) } };
}
export function comparisonCropLayout(crop: ComparisonCrop): { width: number; height: number; left: { x: number; y: number }; right: { x: number; y: number } } {
  const { width: w, height: h } = crop;
  if (!Number.isInteger(w) || !Number.isInteger(h) || w < 1 || h < 1 || w > 512 || h > 512 ||
    !(crop.before instanceof Uint8ClampedArray) || !(crop.after instanceof Uint8ClampedArray) || crop.before.length !== w * h * 4 || crop.after.length !== w * h * 4) throw new Error('Invalid bounded crop');
  const width = Math.max(720, 2 * w + 48), height = 240 + h + 16;
  return { width, height, left: { x: 16, y: 240 }, right: { x: 32 + (width - 48) / 2, y: 240 } };
}
export async function encodeComparisonCrop(crop: ComparisonCrop): Promise<Blob> {
  const layout = comparisonCropLayout(crop), canvas = document.createElement('canvas');
  canvas.width = layout.width; canvas.height = layout.height;
  const ctx = canvas.getContext('2d');
  if (!ctx || layout.width * layout.height * 4 >= MAX_BYTES) throw new Error('Crop canvas unavailable');
  ctx.fillStyle = '#161c23'; ctx.fillRect(0, 0, layout.width, layout.height); ctx.textBaseline = 'alphabetic'; ctx.fillStyle = '#f4f6f8';
  const line = (value: string, x: number, y: number, width: number): void => {
    let text = boundedText(value);
    if (ctx.measureText(text).width > width) {
      while (text.length && ctx.measureText(text + '…').width > width) text = Array.from(text).slice(0, -1).join('');
      text += '…';
    }
    ctx.fillText(text, x, y);
  };
  ctx.font = '600 16px sans-serif'; line(crop.text.title, 16, 24, layout.width - 32);
  ctx.font = '14px sans-serif'; crop.text.lines.slice(0, 9).forEach((v, i) => line(v, 16, 44 + i * 18, layout.width - 32));
  ctx.font = '600 14px sans-serif'; const column = (layout.width - 48) / 2;
  line(crop.text.left, layout.left.x, 224, column); line(crop.text.right, layout.right.x, 224, column);
  ctx.putImageData(new ImageData(crop.before, crop.width, crop.height), layout.left.x, layout.left.y);
  ctx.putImageData(new ImageData(crop.after, crop.width, crop.height), layout.right.x, layout.right.y);
  return new Promise((resolve, reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('PNG encoding failed')), 'image/png'));
}

/** Observe only the caller's relevant projection; object identities never become strong references. */
export function createComparisonCropOwner(): { sample: (values: readonly (object | string | number | boolean | null | undefined)[]) => object } {
  const ids = new WeakMap<object, number>(); let next = 0, previous = '', token = {};
  return { sample(values) {
    const key = JSON.stringify(values.map(value => {
      if (value !== null && typeof value === 'object') { let id = ids.get(value); if (id === undefined) { id = ++next; ids.set(value, id); } return ['object', id]; }
      return [typeof value, value];
    }));
    if (key !== previous) { previous = key; token = {}; }
    return token;
  } };
}
export interface ComparisonCropSaveApi {
  encode(crop: ComparisonCrop): Promise<Blob>;
  sha256(bytes: Uint8Array): Promise<string>;
  pickDirectory(): Promise<string>;
  join(root: string, name: string): string;
  write(path: string, bytes: Uint8Array): Promise<{ size: number; sha256: string }>;
}
export type CropSaveResult = { kind: 'saved' | 'unverified'; path: string } | { kind: 'busy' | 'stale' | 'cancelled' | 'prepare-failed' };
// Document/module lifetime: leaving PhotoCompare cannot unlock an irrevocable pending write.
let saving = false;
const saveListeners = new Set<() => void>();
export const comparisonCropSaving = (): boolean => saving;
export const subscribeComparisonCropSaving = (listener: () => void): (() => void) => {
  saveListeners.add(listener); return () => { saveListeners.delete(listener); };
};
const setSaving = (value: boolean): void => { saving = value; saveListeners.forEach(listener => listener()); };
export const comparisonCropContextReady = (ready: boolean, page: string, mounted: boolean): boolean => ready && page === 'ic' && mounted;
export function createComparisonCropSaver(api: ComparisonCropSaveApi): { save: (crop: ComparisonCrop, owner: object, current: (key: object) => boolean) => Promise<CropSaveResult> } {
  return { async save(crop, owner, current) {
    if (saving) return { kind: 'busy' };
    setSaving(true); let dispatched = false, path = '';
    try {
      if (!current(owner)) return { kind: 'stale' };
      const blob = await api.encode(crop);
      if (!current(owner)) return { kind: 'stale' };
      if (blob.type !== 'image/png' || blob.size < 1 || blob.size > MAX_BYTES) throw new Error('Invalid encoded PNG');
      const bytes = new Uint8Array(await blob.arrayBuffer());
      if (!current(owner)) return { kind: 'stale' };
      if (bytes.length !== blob.size || bytes.length > MAX_BYTES) throw new Error('Invalid encoded PNG size');
      const digest = (await api.sha256(bytes)).toLowerCase();
      if (!current(owner)) return { kind: 'stale' };
      if (!/^[a-f0-9]{64}$/.test(digest)) throw new Error('Invalid PNG digest');
      const dir = await api.pickDirectory();
      if (!current(owner)) return { kind: 'stale' };
      if (!dir) return { kind: 'cancelled' };
      const random = Array.from(crypto.getRandomValues(new Uint32Array(2)), n => n.toString(36)).join('-');
      path = api.join(dir, `comparison-centre-${Date.now().toString(36)}-${random}.png`);
      if (!current(owner)) return { kind: 'stale' };
      dispatched = true; // From here even an error may have left a file; ownership cannot revoke this write.
      const written = await api.write(path, bytes);
      return { kind: written.size === bytes.length && written.sha256.toLowerCase() === digest ? 'saved' : 'unverified', path };
    } catch {
      return dispatched ? { kind: 'unverified', path } : { kind: 'prepare-failed' };
    } finally { setSaving(false); }
  } };
}
