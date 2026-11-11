// Writes the review material to out/review/: key-frame sheets, motion strips (33 ms steps) and animated
// previews (APNG, 1:1, real timing), all over a GR III sample photo.
// Usage: node make-review.mjs [photo-name]   (default gr3-path.jpg)
import { mkdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';
import { createRenderer, SHEET } from './src/renderer.mjs';
import { compositeInto } from './src/compose.mjs';
import { FILMS } from './src/films.mjs';
import { PLACEHOLDERS, REVIEW_PLACEHOLDERS, duration, W, H } from './src/plan.mjs';
import { Surface, toRgba, rgba } from './src/surface.mjs';
import { encodeApng } from './apng.mjs';

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

// ---- thumbnails for the contact sheet: 36 crops of the six samples
const names = ['gr3-hill.jpg', 'gr3-path.jpg', 'gr3-r0000022.jpg', 'gr3-r0000023.jpg', 'gr3-sign.jpg', 'gr3-stream.jpg'];
const big = [];
for (const n of names) big.push(await rawU32(n, 420, 280));
const thumbs = [];
for (let i = 0; i < 36; i++) {
  const src = big[i % 6], ox = ((i * 37) % 6) * 28, oy = ((i * 11) % 5) * 18, t = new Uint32Array(SHEET.fw * SHEET.fh);
  for (let y = 0; y < SHEET.fh; y++) for (let x = 0; x < SHEET.fw; x++) t[y * SHEET.fw + x] = src[((oy + y * 4) % 280) * 420 + (ox + x * 4) % 420];
  thumbs.push(t);
}

// ---- helpers
const mini = new Surface(560, 22), miniPal = new Uint32Array(4);
miniPal[1] = rgba(0, 0, 0, 200); miniPal[2] = rgba(255, 255, 255);
function stamp(dst, dw, text, x, y) {
  text = text.toUpperCase();
  mini.clear(); const tw = Math.min(560, mini.textWidth(text, 2) + 8);
  mini.rect(0, 0, tw, 22, 1); mini.text(text, 4, 4, 2, 2);
  const out = new Uint32Array(560 * 22); toRgba(mini, miniPal, out);
  for (let yy = 0; yy < 22; yy++) for (let xx = 0; xx < tw; xx++) {
    const c = out[yy * 560 + xx], a = c >>> 24; if (a === 0) continue;
    const o = dst[(y + yy) * dw + x + xx], ia = 255 - a;
    const ch = s => ((((c >> s) & 255) * a + ((o >> s) & 255) * ia) / 255) | 0;
    dst[(y + yy) * dw + x + xx] = (0xff000000 | (ch(16) << 16) | (ch(8) << 8) | ch(0)) >>> 0;
  }
}
const MAG = rgba(255, 0, 255);
function boxes(dst, list, short) {
  for (const p of list) {
    for (let x = p.x; x < p.x + p.w; x++) for (const y of [p.y, p.y + p.h - 1]) dst[y * W + x] = MAG;
    for (let y = p.y; y < p.y + p.h; y++) for (const x of [p.x, p.x + p.w - 1]) dst[y * W + x] = MAG;
    const text = p.label.length * 12 <= p.w - 8 ? p.label : '';
    if (text) stamp(dst, W, text, p.x + 4, p.y + 4);
  }
}
/** Composite one frame over the photo. opts.review: draw the review-screen placeholder rows UNDER the overlays
 *  (so any row that peeks out during the slide shows); opts.placeholders: live-view guesses, on top. */
function frameAt(moment, film, frame, roll, t, opts, label) {
  const dst = new Uint32Array(photo);
  const rev = opts.review === undefined ? (moment === 'shot' || moment === 'roll') : opts.review;
  const live = opts.placeholders === undefined ? (moment === 'live' || moment === 'load') : opts.placeholders;
  if (rev) boxes(dst, REVIEW_PLACEHOLDERS, false);
  compositeInto(dst, r.render(moment, film, frame, roll, t, opts));
  if (live) boxes(dst, PLACEHOLDERS, false);
  if (label) stamp(dst, W, label, 6, 50);
  return dst;
}
async function savePng(name, pixels, w, h) {
  await sharp(Buffer.from(pixels.buffer, pixels.byteOffset, pixels.byteLength), { raw: { width: w, height: h, channels: 4 } }).png().toFile(OUT + name);
  console.log(OUT + name, w + 'x' + h);
  return OUT + name;
}
function grid(frames, cols, cw, ch, gap = 6) {
  const rows = Math.ceil(frames.length / cols), sw = cols * cw + (cols - 1) * gap, sh = rows * ch + (rows - 1) * gap;
  const sheet = new Uint32Array(sw * sh).fill(rgba(24, 24, 28));
  frames.forEach((f, i) => {
    const ox = (i % cols) * (cw + gap), oy = ((i / cols) | 0) * (ch + gap);
    for (let y = 0; y < ch; y++) sheet.set(f.subarray(y * cw, y * cw + cw), (oy + y) * sw + ox);
  });
  return { sheet, sw, sh };
}
const save = async (name, frames, cols, cw = W, ch = H) => { const g = grid(frames, cols, cw, ch); return savePng(name, g.sheet, g.sw, g.sh); };
const slug = s => s.toLowerCase().replace(/[^a-z0-9]+/g, '-');
const tn = tier => (tier === 1 ? 'tier1' : 'tier1+2');
const steps = (a, b, d = 33) => { const o = []; for (let t = a; t <= b; t += d) o.push(t); return o; };

// 50 percent downscale (2x2 box) for full-screen motion sheets
function half(f) {
  const o = new Uint32Array(360 * 240);
  for (let y = 0; y < 240; y++) for (let x = 0; x < 360; x++) {
    let a = 0, b = 0, g = 0;
    for (const [dx, dy] of [[0, 0], [1, 0], [0, 1], [1, 1]]) { const p = f[(2 * y + dy) * W + 2 * x + dx]; a += p & 255; b += (p >> 8) & 255; g += (p >> 16) & 255; }
    o[y * 360 + x] = (0xff000000 | ((g >> 2) << 16) | ((b >> 2) << 8) | (a >> 2)) >>> 0;
  }
  return o;
}
/** Motion strip, tier 1: both bands stacked (1:1) at 33 ms steps, with the counter and a time label beside them. */
async function bandMotion(name, moment, fi, frame, times, opts = {}) {
  const tw = W + 6 + 84, th = 90, tiles = [];
  for (const t of times) {
    const full = frameAt(moment, fi, frame, 12, t, { tier: 1, tabMode: 'always', review: moment === 'shot', ...opts }, null);
    const tile = new Uint32Array(tw * th).fill(rgba(40, 40, 46));
    for (let y = 0; y < 44; y++) for (let x = 0; x < W; x++) { tile[y * tw + x] = full[y * W + x]; tile[(46 + y) * tw + x] = full[(436 + y) * W + x]; }
    for (let y = 0; y < 48; y++) for (let x = 0; x < 84; x++) tile[(y) * tw + W + 6 + x] = full[(380 + y) * W + 612 + x];
    stamp(tile, tw, 'T ' + t, W + 6, 64);
    tiles.push(tile);
  }
  const g = grid(tiles, 1, tw, th, 2);
  return savePng(name, g.sheet, g.sw, g.sh);
}
async function fullMotion(name, moment, fi, frame, times, opts = {}, cols = 4) {
  const tiles = times.map(t => { const f = frameAt(moment, fi, frame, 12, t, { tier: 2, tabMode: 'always', review: moment === 'shot', ...opts }, null); const h = half(f); stamp(h, 360, 'T ' + t, 4, 4); return h; });
  const g = grid(tiles, cols, 360, 240, 4);
  return savePng(name, g.sheet, g.sw, g.sh);
}
async function apng(name, moment, fi, frame, tier, opts = {}) {
  const f = FILMS[fi], d = duration(moment, f), frames = [];
  for (let t = 0; t < d; t += 33) frames.push(frameAt(moment, fi, frame, 12, t, { tier, tabMode: 'always', thumbs, review: moment === 'shot', ...opts }, null));
  frames.push(frameAt('none', fi, frame, 12, 0, { tier, tabMode: 'always' }, null));
  writeFileSync(OUT + name, encodeApng(frames, W, H, 33));
  console.log(OUT + name, frames.length + ' frames');
  return OUT + name;
}

const files = [];
// ---- key frames
const SHOT_T = {
  neg: [100, 300, 440, 560, 680, 800, 1000, 1360], bw: [100, 300, 440, 560, 680, 800, 1000, 1360],
  cine: [100, 300, 440, 560, 680, 800, 1000, 1360],
  slide: [60, 150, 230, 500, 650, 900, 1050, 1200], instant: [100, 240, 500, 900, 1300, 1560, 1650, 1760],
};
for (const name of ['Portra 400', 'Gold 200', 'CineStill 800T', 'Velvia', 'Instant']) {
  const fi = idx(name), f = FILMS[fi];
  for (const tier of [1, 2])
    files.push(await save(`shot_${slug(name)}_${tn(tier)}.png`, SHOT_T[f.kind].map(t => frameAt('shot', fi, 17, 12, t, { tier, tabMode: 'always', review: true }, `${f.name} shot t=${t}ms ${tn(tier)}`)), 4));
}
files.push(await save('shot_portra-400_frame36-lever-locks.png', [100, 300, 420, 520, 700, 1100].map(t =>
  frameAt('shot', idx('Portra 400'), 36, 12, t, { tier: 1, tabMode: 'always', review: true }, `frame 36 t=${t}ms`)), 3));
const lt = [150, 400, 650, 900, 1150, 1500, 1700, 2100];
for (const tier of [1, 2]) for (const n of ['Portra 400', 'CineStill 800T', 'Gold 200'])
  files.push(await save(`load_${slug(n)}_${tn(tier)}.png`, lt.map(t => frameAt('load', idx(n), 1, 12, t, { tier, tabMode: 'always' }, `${n} load t=${t}ms ${tn(tier)}`)), 4));
const rt = [250, 600, 1000, 1400, 1800, 2400, 3000, 3250];
files.push(await save('roll-end_portra-400_tier1.png', rt.map(t => frameAt('roll', idx('Portra 400'), 36, 12, t, { tier: 1, tabMode: 'always' }, `Portra roll end t=${t}ms tier1`)), 4));
files.push(await save('roll-end_portra-400_tier1+2_with-thumbnails.png', rt.map(t => frameAt('roll', idx('Portra 400'), 36, 12, t, { tier: 2, tabMode: 'always', thumbs }, `Portra roll end t=${t}ms tier1+2 thumbs`)), 4));
files.push(await save('roll-end_portra-400_tier1+2_no-thumbnails.png', rt.map(t => frameAt('roll', idx('Portra 400'), 36, 12, t, { tier: 2, tabMode: 'always' }, `Portra roll end t=${t}ms tier1+2 plain`)), 4));
files.push(await save('roll-end_gold-200_tier1+2_no-thumbnails.png', [1000, 1800, 2400].map(t =>
  frameAt('roll', idx('Gold 200'), 36, 12, t, { tier: 2, tabMode: 'always' }, `Gold roll end t=${t}ms tier1+2 plain`)), 3));
const live = [];
for (const n of ['Portra 400', 'Gold 200', 'CineStill 800T', 'Instant']) live.push(frameAt('live', idx(n), 17, 12, 0, { tier: 1, tabMode: 'always', placeholders: true }, `live view (owner photo, approx.) / ${n}`));
for (const pe of [60, 120, 900, 1850]) live.push(frameAt('live', idx('Portra 400'), 17, 12, 0, { tier: 1, tabMode: 'peek', counterMode: 'always', peekElapsed: pe, placeholders: true }, `tab peek ${pe}ms of 2000, counter always`));
files.push(await save('liveview_tab-and-counter.png', live, 4));

// counter close-up: 17, 18, 36, 1, S and a mid-roll frame, 1:1 and 50 percent
{
  const tiles = [];
  for (const [fr, t, m] of [[17, 0, 'live'], [18, 0, 'live'], [36, 0, 'live'], [1, 0, 'live'], [1, 0, 'load'], [17, 700, 'shot'], [9, 700, 'shot'], [1, 1600, 'load']]) {
    const full = frameAt(m, idx('Portra 400'), fr, 12, t, { tier: 1, tabMode: 'always' }, null), tile = new Uint32Array(84 * 48);
    for (let y = 0; y < 48; y++) for (let x = 0; x < 84; x++) tile[y * 84 + x] = full[(380 + y) * W + 612 + x];
    tiles.push(tile);
  }
  files.push(await save('counter_17-18-36-1-S-and-rolls.png', tiles, 8, 84, 48));
}

// all 20 films: tab + both bands at a legible rest pose
{
  const tiles = [], tw = 128 + 6 + W, th = 94;
  for (const f of FILMS) {
    const t = f.kind === 'slide' ? 600 : f.kind === 'instant' ? 1000 : 1100;
    const full = frameAt('shot', f.index, 17, 12, t, { tier: 1, tabMode: 'always' }, null);
    const tile = new Uint32Array(tw * th).fill(rgba(40, 40, 46));
    for (let y = 0; y < 56; y++) for (let x = 0; x < 128; x++) tile[(19 + y) * tw + x] = full[(376 + y) * W + x];
    for (let y = 0; y < 44; y++) for (let x = 0; x < W; x++) { tile[y * tw + 134 + x] = full[y * W + x]; tile[(46 + y) * tw + 134 + x] = full[(436 + y) * W + x]; }
    tiles.push(tile);
  }
  files.push(await save('all-20-films_tab-and-edge-print.png', tiles, 2, tw, th));
}

// ---- motion strips (33 ms steps)
for (const n of ['Portra 400', 'Gold 200', 'CineStill 800T']) {
  files.push(await bandMotion(`motion_shot_${slug(n)}_tier1_advance-380-940ms.png`, 'shot', idx(n), 17, steps(380, 940)));
  files.push(await fullMotion(`motion_shot_${slug(n)}_tier1+2_advance-380-940ms_50pct.png`, 'shot', idx(n), 17, steps(380, 940, 66), {}, 3));
}
files.push(await bandMotion('motion_shot_velvia_tier1_drop-and-push-out.png', 'shot', idx('Velvia'), 17, [...steps(0, 260), ...steps(900, 1250)]));
files.push(await bandMotion('motion_shot_instant_tier1_rise-and-eject.png', 'shot', idx('Instant'), 17, [...steps(0, 260), ...steps(1560, 1800)]));
files.push(await fullMotion('motion_shot_instant_tier1+2_rise-and-eject_50pct.png', 'shot', idx('Instant'), 17, [...steps(0, 260, 66), 600, 1000, 1400, ...steps(1560, 1800, 40)], {}, 4));
for (const n of ['Portra 400', 'CineStill 800T']) {
  files.push(await bandMotion(`motion_load_${slug(n)}_tier1_a-cassette-arrives.png`, 'load', idx(n), 1, steps(100, 700)));
  files.push(await bandMotion(`motion_load_${slug(n)}_tier1_b-leader-pulled.png`, 'load', idx(n), 1, steps(700, 1420)));
}
files.push(await fullMotion('motion_load_portra-400_tier1+2_cassette-and-leader_50pct.png', 'load', idx('Portra 400'), 1, steps(0, 1500, 66), {}, 4));
files.push(await bandMotion('motion_roll_portra-400_tier1_rewind-start.png', 'roll', idx('Portra 400'), 36, steps(300, 800)));
files.push(await bandMotion('motion_roll_portra-400_tier1_tail-into-cassette.png', 'roll', idx('Portra 400'), 36, steps(2250, 2950)));
files.push(await fullMotion('motion_roll_portra-400_tier1+2_sheet-in_50pct.png', 'roll', idx('Portra 400'), 36, steps(100, 500), { thumbs }, 4));
files.push(await fullMotion('motion_roll_portra-400_tier1+2_grease-circle_50pct.png', 'roll', idx('Portra 400'), 36, steps(1500, 2030), { thumbs }, 4));

// ---- animated previews: APNG, 1:1, 33 ms per frame
for (const tier of [1, 2]) for (const n of ['Portra 400', 'Gold 200', 'CineStill 800T']) for (const m of ['shot', 'load', 'roll'])
  files.push(await apng(`anim_${m}_${slug(n)}_${tn(tier)}.apng`, m, idx(n), m === 'roll' ? 36 : m === 'load' ? 1 : 17, tier));
for (const tier of [1, 2]) for (const n of ['Velvia', 'Instant']) files.push(await apng(`anim_shot_${slug(n)}_${tn(tier)}.apng`, 'shot', idx(n), 17, tier));
writeFileSync(OUT + 'INDEX.txt', files.join('\n') + '\n', 'utf8');
