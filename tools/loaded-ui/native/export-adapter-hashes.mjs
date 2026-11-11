// JS reference hashes for the adapter checks: reads a JSON array of cases on stdin, prints per-view CRC-32s.
// A case: { moment, film, frame, roll, t, tabMode, counterMode, month (12 = none), year }
import { readFileSync } from 'node:fs';
import zlib from 'node:zlib';
import { createRenderer } from '../src/renderer.mjs';
const r = createRenderer();
const cases = JSON.parse(readFileSync(0, 'utf8'));
const out = cases.map(c => r.render(c.moment, c.film, c.frame, c.roll, c.t, { tier: 1, tabMode: c.tabMode ? 'peek' : 'always', counterMode: c.counterMode ? 'peek' : 'always',
  peekElapsed: -1, date: c.month === 12 ? null : { month: c.month, year: c.year } }).map(v => zlib.crc32(Buffer.from(v.rgba.buffer, v.rgba.byteOffset, v.rgba.byteLength))));
console.log(JSON.stringify(out));
