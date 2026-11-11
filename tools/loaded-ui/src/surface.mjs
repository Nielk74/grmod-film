// SPDX-License-Identifier: GPL-2.0-only
// An indexed (8 bit) drawing surface for one view. Every primitive clips to the view rectangle, so no
// write can leave it. The buffer is allocated once with an optional guard ring (filled with a canary
// by the tests) to prove that. Index 0 is always fully transparent.
import { FONT_DATA, FONT_INDEX, GLYPH_H } from './font.mjs';

export const CANARY = 0xfe;

export class Surface {
  constructor(w, h, guard = 0) {
    this.w = w; this.h = h; this.guard = guard;
    this.stride = w + 2 * guard;
    this.buf = new Uint8Array(this.stride * (h + 2 * guard));
    this.origin = guard * this.stride + guard;
    if (guard) this.buf.fill(CANARY);
    // Clip rectangle (inclusive-exclusive), always inside the view.
    this.cx0 = 0; this.cy0 = 0; this.cx1 = w; this.cy1 = h;
    this.ox = 0; this.oy = 0; // drawing translation, applied before clipping
    this.clear();
  }
  clear() {
    const { w, h, stride, buf } = this;
    for (let y = 0; y < h; y++) {
      const o = this.origin + y * stride;
      for (let x = 0; x < w; x++) buf[o + x] = 0;
    }
    this.resetClip();
  }
  resetClip() { this.cx0 = 0; this.cy0 = 0; this.cx1 = this.w; this.cy1 = this.h; this.ox = 0; this.oy = 0; }
  /** Intersect the clip with a rectangle (the surface keeps the previous one if you pass `keep`). */
  clip(x, y, w, h) {
    x += this.ox; y += this.oy;
    this.cx0 = Math.max(0, x); this.cy0 = Math.max(0, y);
    this.cx1 = Math.min(this.w, x + w); this.cy1 = Math.min(this.h, y + h);
  }
  unclip() { this.cx0 = 0; this.cy0 = 0; this.cx1 = this.w; this.cy1 = this.h; }
  px(x, y, c) {
    x += this.ox; y += this.oy;
    if (x < this.cx0 || y < this.cy0 || x >= this.cx1 || y >= this.cy1) return;
    this.buf[this.origin + y * this.stride + x] = c;
  }
  rect(x, y, w, h, c) {
    x += this.ox; y += this.oy;
    let x0 = x < this.cx0 ? this.cx0 : x, y0 = y < this.cy0 ? this.cy0 : y;
    let x1 = x + w > this.cx1 ? this.cx1 : x + w, y1 = y + h > this.cy1 ? this.cy1 : y + h;
    for (let yy = y0; yy < y1; yy++) {
      const o = this.origin + yy * this.stride;
      for (let xx = x0; xx < x1; xx++) this.buf[o + xx] = c;
    }
  }
  /** Rounded rectangle, corner radius r (r = 0 is a plain rectangle). */
  rrect(x, y, w, h, r, c) {
    if (r <= 0) return this.rect(x, y, w, h, c);
    this.rect(x, y + r, w, h - 2 * r, c);
    for (let j = 0; j < r; j++) {
      const d = r - j; // rows from the corner circle's centre line
      let dx = 0;
      while (dx < r && (dx + 1) * (dx + 1) + d * d - d <= r * r) dx++;
      const inset = r - dx;
      this.rect(x + inset, y + j, w - 2 * inset, 1, c);
      this.rect(x + inset, y + h - 1 - j, w - 2 * inset, 1, c);
    }
  }
  disc(cx, cy, r, c) {
    for (let dy = -r; dy <= r; dy++) {
      let dx = 0;
      while ((dx + 1) * (dx + 1) + dy * dy <= r * r + r) dx++;
      this.rect(cx - dx, cy + dy, 2 * dx + 1, 1, c);
    }
  }
  /** Triangle-free diagonal helper: fill the part of rect (x,y,w,h) where (px-x)*a + (py-y)*b < k. */
  halfPlane(x, y, w, h, a, b, k, c) {
    for (let yy = 0; yy < h; yy++) for (let xx = 0; xx < w; xx++) if (xx * a + yy * b < k) this.px(x + xx, y + yy, c);
  }
  textWidth(s, scale) { return s.length ? s.length * 6 * scale - scale : 0; }
  text(s, x, y, scale, c) {
    for (let i = 0; i < s.length; i++) this.glyph(s.charCodeAt(i), x + i * 6 * scale, y, scale, c);
  }
  /** Unsigned integer without building a string; `pad` = minimum digits. Returns the width drawn. */
  num(n, x, y, scale, c, pad = 0) {
    let digits = 1, d = 10;
    while (n >= d) { digits++; d *= 10; }
    if (digits < pad) digits = pad;
    let div = 1;
    for (let i = 1; i < digits; i++) div *= 10;
    for (let i = 0; i < digits; i++) {
      this.glyph(48 + (((n / div) | 0) % 10), x + i * 6 * scale, y, scale, c);
      div = (div / 10) | 0;
    }
    return digits * 6 * scale - scale;
  }
  numWidth(n, scale, pad = 0) {
    let digits = 1, d = 10;
    while (n >= d) { digits++; d *= 10; }
    if (digits < pad) digits = pad;
    return digits * 6 * scale - scale;
  }
  /** Fills the lower-right triangle (xx + yy >= n - 1) of an n x n box: a folded corner. */
  triBR(x, y, n, c) {
    for (let yy = 0; yy < n; yy++) this.rect(x + n - 1 - yy, y + yy, yy + 1, 1, c);
  }
  glyph(code, x, y, scale, c) {
    const g = code < 256 ? FONT_INDEX[code] : -1;
    if (g < 0) return;
    const gx = x + this.ox, gy = y + this.oy;
    if (gx >= this.cx1 || gx + 5 * scale <= this.cx0 || gy >= this.cy1 || gy + GLYPH_H * scale <= this.cy0) return;
    for (let row = 0; row < GLYPH_H; row++) {
      const bits = FONT_DATA[g * GLYPH_H + row];
      for (let col = 0; col < 5; col++) if (bits & (16 >> col)) this.rect(x + col * scale, y + row * scale, scale, scale, c);
    }
  }
  guardIntact() {
    if (!this.guard) return true;
    const { w, h, stride, buf, guard } = this;
    for (let y = 0; y < h + 2 * guard; y++) {
      const inside = y >= guard && y < h + guard;
      for (let x = 0; x < stride; x++) {
        if (inside && x >= guard && x < w + guard) continue;
        if (buf[y * stride + x] !== CANARY) return false;
      }
    }
    return true;
  }
}

/** Converts the indices to RGBA (little-endian 0xAABBGGRR words, straight alpha). */
export function toRgba(surface, palette, out) {
  const { w, h, stride, buf, origin } = surface;
  let i = 0;
  for (let y = 0; y < h; y++) {
    const o = origin + y * stride;
    for (let x = 0; x < w; x++) out[i++] = palette[buf[o + x]];
  }
}
export const rgba = (r, g, b, a = 255) => ((a << 24) | (b << 16) | (g << 8) | r) >>> 0;
