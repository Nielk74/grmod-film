// Writes the review sheets (PNG, 1:1 over a GR III sample photo) to out/review/.
// Usage: node make-review.mjs [photo-name]   (default gr3-path.jpg)
import { mkdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';
import { createRenderer } from './src/renderer.mjs';
import { compositeInto } from './src/compose.mjs';
import { FILMS } from './src/films.mjs';
import { PLACEHOLDERS, W, H } from './src/plan.mjs';
import { Surface, toRgba, rgba } from './src/surface.mjs';

const SAMPLES = fileURLToPath(new URL('../../ui/src/assets/samples/', import.meta.url));
const OUT = fileURLToPath(new URL('out/review/', import.meta.url));
mkdirSync(OUT, { recursive: true });
const photoName = process.argv[2] || 'gr3-path.jpg';
const rawU32 = async (name, w, h) => {
  const b = await sharp(SAMPLES + name).resize(w, h, { fit: 'cover' }).ensureAlpha().raw().toBuffer();
  return new Uint32Array(b.buffer.slice(b.byteOffset, b.byteOffset + b.length));
};
const photo = await rawU32(photoName, W, H);
const r = createRenderer();
const idx = n => FILMS.findIndex(f => f.name === n);

// ---- thumbnails for the contact sheet: 36 crops of the six samples, 70x46
const names = ['gr3-hill.jpg', 'gr3-path.jpg', 'gr3-r0000022.jpg', 'gr3-r0000023.jpg', 'gr3-sign.jpg', 'gr3-stream.jpg'];
const big = [];
for (const n of names) big.push(await rawU32(n, 420, 280));
const thumbs = [];
for (let i = 0; i < 36; i++) {
  const src = big[i % 6], ox = ((i * 37) % 6) * 28, oy = ((i * 11) % 5) * 18, t = new Uint32Array(70 * 46);
  for (let y = 0; y < 46; y++) for (let x = 0; x < 70; x++) t[y * 70 + x] = src[((oy + y * 4) % 280) * 420 + (ox + x * 4) % 420];
  thumbs.push(t);
}

// ---- helpers
const mini = new Surface(520, 22), miniPal = new Uint32Array(4);
miniPal[1] = rgba(0, 0, 0, 200); miniPal[2] = rgba(255, 255, 255);
function stamp(dst, dw, text, x, y) {
  text = text.toUpperCase();
  mini.clear(); const tw = Math.min(520, mini.textWidth(text, 2) + 8);
  mini.rect(0, 0, tw, 22, 1); mini.text(text, 4, 4, 2, 2);
  const out = new Uint32Array(520 * 22); toRgba(mini, miniPal, out);
  for (let yy = 0; yy < 22; yy++) for (let xx = 0; xx < tw; xx++) {
    const c = out[yy * 520 + xx], a = c >>> 24; if (a === 0) continue;
    const o = dst[(y + yy) * dw + x + xx], ia = 255 - a;
    const ch = s => ((((c >> s) & 255) * a + ((o >> s) & 255) * ia) / 255) | 0;
    dst[(y + yy) * dw + x + xx] = (0xff000000 | (ch(16) << 16) | (ch(8) << 8) | ch(0)) >>> 0;
  }
}
function frameAt(moment, film, frame, roll, t, opts, label) {
  const dst = new Uint32Array(photo);
  const views = r.render(moment, film, frame, roll, t, opts);
  compositeInto(dst, views);
  if (opts.placeholders) for (const p of PLACEHOLDERS) {
    for (let x = p.x; x < p.x + p.w; x++) for (const y of [p.y, p.y + p.h - 1]) dst[y * W + x] = rgba(255, 0, 255);
    for (let y = p.y; y < p.y + p.h; y++) for (const x of [p.x, p.x + p.w - 1]) dst[y * W + x] = rgba(255, 0, 255);
    stamp(dst, W, p.w > 400 ? p.label.replace('EXPOSURE INFO ROW (POSITION UNVERIFIED)', 'CAMERA INFO ROW (UNVERIFIED)') : 'PLACEHOLDER', p.x + 4, p.y + 7);
  }
  if (label) stamp(dst, W, label, 6, H - 44 - 26 - (opts.placeholders ? 44 : 0));
  return dst;
}
async function save(name, frames, cols, cw = W, ch = H) {
  const rows = Math.ceil(frames.length / cols), gap = 6, sw = cols * cw + (cols - 1) * gap, sh = rows * ch + (rows - 1) * gap;
  const sheet = new Uint32Array(sw * sh).fill(rgba(24, 24, 28));
  frames.forEach((f, i) => {
    const ox = (i % cols) * (cw + gap), oy = ((i / cols) | 0) * (ch + gap);
    for (let y = 0; y < ch; y++) sheet.set(f.subarray(y * cw, y * cw + cw), (oy + y) * sw + ox);
  });
  await sharp(Buffer.from(sheet.buffer), { raw: { width: sw, height: sh, channels: 4 } }).png().toFile(OUT + name);
  console.log(OUT + name, sw + 'x' + sh);
  return OUT + name;
}
const slug = s => s.toLowerCase().replace(/[^a-z0-9]+/g, '-');
const tn = tier => (tier === 1 ? 'tier1' : 'tier1+2');

const SHOT_T = {
  neg: [100, 300, 480, 640, 880, 1000, 1150, 1360],
  bw: [100, 300, 480, 640, 880, 1000, 1150, 1360],
  cine: [100, 300, 430, 560, 700, 880, 1150, 1360],
  slide: [60, 150, 230, 500, 650, 900, 1050, 1200],
  instant: [100, 240, 500, 900, 1300, 1560, 1650, 1760],
};
const files = [];
for (const name of ['Portra 400', 'Gold 200', 'CineStill 800T', 'Velvia', 'Instant']) {
  const fi = idx(name), f = FILMS[fi];
  for (const tier of [1, 2]) {
    const fr = SHOT_T[f.kind].map(t => frameAt('shot', fi, 17, 12, t, { tier, tabMode: 'always' }, `${f.name} shot t=${t}ms ${tn(tier)}`));
    files.push(await save(`shot_${slug(name)}_${tn(tier)}.png`, fr, 4));
  }
}
files.push(await save('shot_portra-400_frame36-lever-locks.png', [100, 300, 420, 520, 700, 1100].map(t =>
  frameAt('shot', idx('Portra 400'), 36, 12, t, { tier: 1, tabMode: 'always' }, `frame 36 t=${t}ms`)), 3));

const lt = [150, 400, 650, 900, 1150, 1500, 1700, 2100];
for (const tier of [1, 2]) for (const n of ['Portra 400', 'CineStill 800T'])
  files.push(await save(`load_${slug(n)}_${tn(tier)}.png`, lt.map(t => frameAt('load', idx(n), 1, 12, t, { tier, tabMode: 'always' }, `${n} load t=${t}ms ${tn(tier)}`)), 4));

const rt = [250, 600, 1000, 1400, 1800, 2400, 3000, 3250];
files.push(await save('roll-end_portra-400_tier1.png', rt.map(t => frameAt('roll', idx('Portra 400'), 36, 12, t, { tier: 1, tabMode: 'always' }, `Portra roll end t=${t}ms tier1`)), 4));
files.push(await save('roll-end_portra-400_tier1+2_with-thumbnails.png', rt.map(t => frameAt('roll', idx('Portra 400'), 36, 12, t, { tier: 2, tabMode: 'always', thumbs }, `Portra roll end t=${t}ms tier1+2 thumbs`)), 4));
files.push(await save('roll-end_portra-400_tier1+2_no-thumbnails.png', rt.map(t => frameAt('roll', idx('Portra 400'), 36, 12, t, { tier: 2, tabMode: 'always' }, `Portra roll end t=${t}ms tier1+2 plain`)), 4));
files.push(await save('roll-end_gold-200_tier1+2_no-thumbnails.png', [1000, 1800, 2400].map(t =>
  frameAt('roll', idx('Gold 200'), 36, 12, t, { tier: 2, tabMode: 'always' }, `Gold roll end t=${t}ms tier1+2 plain`)), 3));

// live view: always and peek, with the (unverified) camera furniture placeholders
const live = [];
for (const n of ['Portra 400', 'Gold 200', 'CineStill 800T', 'Instant']) live.push(frameAt('live', idx(n), 17, 12, 0, { tier: 1, tabMode: 'always', placeholders: true }, `live view, always, ${n}`));
for (const pe of [60, 120, 900, 1850]) live.push(frameAt('live', idx('Portra 400'), 17, 12, 0, { tier: 1, tabMode: 'peek', peekElapsed: pe, placeholders: true }, `peek ${pe}ms of 2000`));
files.push(await save('liveview_tab-and-counter.png', live, 4));

// all 20 films: tab + both bands at a legible rest pose
const tiles = [], tw = 128 + 6 + W, th = 94;
for (const f of FILMS) {
  const t = f.kind === 'slide' ? 600 : f.kind === 'instant' ? 1000 : 1100;
  const full = frameAt('shot', f.index, 17, 12, t, { tier: 1, tabMode: 'always' }, null);
  const tile = new Uint32Array(tw * th).fill(rgba(40, 40, 46));
  for (let y = 0; y < 56; y++) for (let x = 0; x < 128; x++) tile[(19 + y) * tw + x] = full[(52 + y) * W + x];
  for (let y = 0; y < 44; y++) for (let x = 0; x < W; x++) { tile[y * tw + 134 + x] = full[y * W + x]; tile[(46 + y) * tw + 134 + x] = full[(436 + y) * W + x]; }
  tiles.push(tile);
}
files.push(await save('all-20-films_tab-and-edge-print.png', tiles, 2, tw, th));
writeFileSync(OUT + 'INDEX.txt', files.join('\n') + '\n', 'utf8');
