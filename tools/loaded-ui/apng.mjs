// Minimal APNG writer (real frame timing, loops forever). Frames are full-size RGBA Uint32Array; each frame
// after the first stores only the bounding box that changed, so the files stay small.
import zlib from 'node:zlib';

const u32 = n => { const b = Buffer.alloc(4); b.writeUInt32BE(n >>> 0); return b; };
const u16 = n => { const b = Buffer.alloc(2); b.writeUInt16BE(n); return b; };
function chunk(type, data) {
  const t = Buffer.from(type, 'ascii');
  return Buffer.concat([u32(data.length), t, data, u32(zlib.crc32(Buffer.concat([t, data])))]);
}
function raw(frame, w, x, y, cw, ch, prev) {
  const out = Buffer.alloc((cw * 4 + 1) * ch);
  for (let r = 0; r < ch; r++) {
    const o = r * (cw * 4 + 1); out[o] = 0;
    for (let c = 0; c < cw; c++) {
      let p = frame[(y + r) * w + x + c];
      if (prev && prev[(y + r) * w + x + c] === p) p = 0; // unchanged: transparent, the previous frame shows through (blend OVER)
      out[o + 1 + c * 4] = p & 255; out[o + 2 + c * 4] = (p >> 8) & 255; out[o + 3 + c * 4] = (p >> 16) & 255; out[o + 4 + c * 4] = p >>> 24;
    }
  }
  return zlib.deflateSync(out, { level: 6 });
}
export function encodeApng(frames, w, h, delayMs = 33) {
  const parts = [Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])];
  parts.push(chunk('IHDR', Buffer.concat([u32(w), u32(h), Buffer.from([8, 6, 0, 0, 0])])));
  parts.push(chunk('acTL', Buffer.concat([u32(frames.length), u32(0)])));
  let seq = 0;
  const fctl = (x, y, cw, ch, i0) => chunk('fcTL', Buffer.concat([u32(seq++), u32(cw), u32(ch), u32(x), u32(y), u16(delayMs), u16(1000), Buffer.from([0, i0 ? 1 : 0])]));
  frames.forEach((f, i) => {
    let x = 0, y = 0, cw = w, ch = h;
    if (i > 0) {
      const p = frames[i - 1]; let x0 = w, y0 = h, x1 = -1, y1 = -1;
      for (let yy = 0; yy < h; yy++) for (let xx = 0; xx < w; xx++) if (f[yy * w + xx] !== p[yy * w + xx]) {
        if (xx < x0) x0 = xx; if (xx > x1) x1 = xx; if (yy < y0) y0 = yy; if (yy > y1) y1 = yy;
      }
      if (x1 < 0) { x0 = 0; y0 = 0; x1 = 0; y1 = 0; }
      x = x0; y = y0; cw = x1 - x0 + 1; ch = y1 - y0 + 1;
    }
    parts.push(fctl(x, y, cw, ch, i > 0));
    const data = raw(f, w, x, y, cw, ch, i > 0 ? frames[i - 1] : null);
    if (i === 0) parts.push(chunk('IDAT', data));
    else parts.push(chunk('fdAT', Buffer.concat([u32(seq++), data])));
  });
  parts.push(chunk('IEND', Buffer.alloc(0)));
  return Buffer.concat(parts);
}
