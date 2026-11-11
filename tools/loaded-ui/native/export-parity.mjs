// Writes the parity cases and the JS reference hashes (CRC-32 of each view's RGBA bytes) for native/check_loaded.py.
//   node native/export-parity.mjs                 -> out/native/parity.json, out/native/thumbs.bin
//   node native/export-parity.mjs --dump <index>  -> out/native/dump-<index>.bin (the five views' pixels for one case)
import { mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import zlib from 'node:zlib';
import { createRenderer, SHEET } from '../src/renderer.mjs';
import { FILMS } from '../src/films.mjs';
import { VIEWS, duration } from '../src/plan.mjs';
import { hash32 } from '../src/fixed.mjs';

const OUT = fileURLToPath(new URL('../out/native/', import.meta.url));
mkdirSync(OUT, { recursive: true });
const idx = n => FILMS.findIndex(f => f.name === n);
const FOCUS = ['Portra 400', 'Gold 200', 'CineStill 800T'].map(idx);

// 36 deterministic thumbnails (hash-based colours with a gradient), shared with the emulator through thumbs.bin
export function makeThumbs() {
  const n = SHEET.fw * SHEET.fh, all = new Uint32Array(36 * n);
  for (let i = 0; i < 36; i++) for (let y = 0; y < SHEET.fh; y++) for (let x = 0; x < SHEET.fw; x++) {
    const h = hash32(i * 977 + x, y * 31 + 5), r = (h & 255), g = ((h >> 8) & 255) ^ (y * 5), b = ((h >> 16) & 255) ^ (x * 3);
    all[i * n + y * SHEET.fw + x] = (0xff000000 | ((b & 255) << 16) | ((g & 255) << 8) | (r & 255)) >>> 0;
  }
  return all;
}
const thumbsAll = makeThumbs();
const thumbViews = Array.from({ length: 36 }, (_, i) => thumbsAll.subarray(i * SHEET.fw * SHEET.fh, (i + 1) * SHEET.fw * SHEET.fh));

const base = { tier: 1, tabMode: 0, counterMode: 2, peek: -1, tabPeek: -2, counterPeek: -2, month: 10, year: 26, thumbs: 0, circled: -1, roll: 12 };
const cases = [];
const add = c => cases.push({ ...base, ...c });
const steps = (a, b, d) => { const o = []; for (let t = a; t <= b; t += d) o.push(t); return o; };
const FRAME = { shot: 17, load: 1, roll: 36 };

// 1. focus films: every 33 ms of every moment, both tiers (roll tier 2 also with thumbnails)
for (const f of FOCUS) for (const tier of [1, 2]) for (const m of ['shot', 'load', 'roll']) {
  const d = duration(m, FILMS[f]);
  for (const t of [...steps(0, d - 1, 33), d - 1, d, d + 40]) {
    add({ moment: m, film: f, frame: FRAME[m], tier, t, key: `focus ${m} ${f} ${tier} ${t}` });
    if (m === 'roll' && tier === 2) add({ moment: m, film: f, frame: 36, tier, t, thumbs: 1 });
  }
}
// 2. every other film: shot every 100 ms, load and roll at a few times, both tiers
for (let f = 0; f < FILMS.length; f++) if (!FOCUS.includes(f)) for (const tier of [1, 2]) {
  for (const t of steps(0, duration('shot', FILMS[f]), 100)) add({ moment: 'shot', film: f, frame: 17, tier, t });
  for (const t of [0, 300, 700, 1000, 1500, 2000, 2150]) add({ moment: 'load', film: f, frame: 1, tier, t });
  for (const t of [0, 300, 900, 1600, 2100, 2750, 3300]) add({ moment: 'roll', film: f, frame: 36, tier, t, thumbs: tier === 2 ? 1 : 0 });
}
// 3. live view, tab and counter modes including the peek slides (tab mode, counter mode; 0 always, 1 peek)
for (const [tm, cm] of [[0, 0], [1, 1], [1, 0], [0, 1], [1, 2]]) for (const pe of [-1, 0, 60, 120, 179, 180, 500, 1759, 1760, 1850, 1999, 2000, 4000])
  for (const frame of [1, 9, 10, 17, 35, 36]) add({ moment: 'live', film: frame === 17 ? idx('Portra 400') : idx('Gold 200'), frame, tier: 1, tabMode: tm, counterMode: cm, peek: pe, t: 0 });
for (const pe of [-1, 90, 600]) for (const tp of [-1, 60, 900]) add({ moment: 'live', film: 3, frame: 5, tier: 1, tabMode: 1, counterMode: 1, peek: pe, tabPeek: tp, counterPeek: 1900, t: 0 });
// 4. frame numbers 1, 9, 10, 35, 36 through shots (counter rolls, strip numbers, lever lock), both tiers
for (const f of [idx('Portra 400'), idx('Velvia'), idx('Eterna'), idx('Instant')]) for (const frame of [1, 9, 10, 35, 36]) for (const tier of [1, 2])
  for (const t of [0, 150, 300, 420, 560, 700, 860, 1000, 1250, 1400]) add({ moment: 'shot', film: f, frame, tier, t, key: `fn ${f} ${frame} ${tier} ${t}` });
for (const f of [idx('Portra 400'), idx('CineStill 800T')]) for (const t of steps(260, 700, 33)) add({ moment: 'shot', film: f, frame: 36, tier: 1, t });
// 5. date stamp on the slide mount, roll numbers and circled frames on the sheet
for (const f of [idx('Velvia'), idx('Kodachrome 64')]) for (const [month, year] of [[0, 0], [5, 26], [11, 99], [9, 7]]) for (const t of [300, 700]) add({ moment: 'shot', film: f, frame: 17, tier: 1, t, month, year });
for (const roll of [0, 1, 12, 999999]) for (const circled of [-1, 0, 17, 35]) for (const t of [1600, 1900, 2300]) add({ moment: 'roll', film: idx('Portra 400'), frame: 36, tier: 2, t, roll, circled, thumbs: roll === 12 ? 1 : 0 });
// 6. furniture hidden/shown through the moments in peek modes (tab aside, hand-off)
for (const [tm, cm] of [[0, 0], [1, 1]]) for (const m of ['shot', 'load', 'roll']) for (const f of [idx('Instant'), idx('Velvia'), idx('Portra 400')]) for (const tier of [1, 2])
  for (const t of [0, 90, 200, 1000, 1700, 1950, 2100, 2190]) add({ moment: m, film: f, frame: FRAME[m], tier, t, tabMode: tm, counterMode: cm, peek: t < 1500 ? t : -1 });

const r = createRenderer();
const HASHES = (c, dump) => {
  const views = r.render(c.moment, c.film, c.frame, c.roll, c.t, { tier: c.tier,
    tabMode: c.tabMode === 1 ? 'peek' : 'always', counterMode: c.counterMode === 2 ? undefined : (c.counterMode === 1 ? 'peek' : 'always'),
    peekElapsed: c.peek, tabPeekElapsed: c.tabPeek === -2 ? undefined : c.tabPeek, counterPeekElapsed: c.counterPeek === -2 ? undefined : c.counterPeek,
    date: { month: c.month, year: c.year }, thumbs: c.thumbs ? thumbViews : null, circled: c.circled < 0 ? undefined : c.circled });
  if (dump) return views;
  return views.map(v => zlib.crc32(Buffer.from(v.rgba.buffer, v.rgba.byteOffset, v.rgba.byteLength)));
};
const MOMENT_ID = { live: 0, shot: 1, load: 2, roll: 3, none: 4 };

if (process.argv[2] === '--dump') {
  const c = JSON.parse(readFileSync(OUT + 'parity.json', 'utf8')).cases[+process.argv[3]];
  const views = HASHES(c, true), total = views.reduce((n, v) => n + v.rgba.byteLength, 0), out = Buffer.alloc(total);
  let o = 0; for (const v of views) { Buffer.from(v.rgba.buffer, v.rgba.byteOffset, v.rgba.byteLength).copy(out, o); o += v.rgba.byteLength; }
  writeFileSync(OUT + `dump-${process.argv[3]}.bin`, out);
} else {
  for (const c of cases) { c.momentId = MOMENT_ID[c.moment]; c.hashes = HASHES(c, false); }
  writeFileSync(OUT + 'parity.json', JSON.stringify({ views: VIEWS.map(v => [v.x, v.y, v.w, v.h]), cases }), 'utf8');
  writeFileSync(OUT + 'thumbs.bin', Buffer.from(thumbsAll.buffer, thumbsAll.byteOffset, thumbsAll.byteLength));
  console.log('cases', cases.length, '->', OUT + 'parity.json');
}
