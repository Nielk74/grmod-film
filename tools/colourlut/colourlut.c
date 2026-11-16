/* SPDX-License-Identifier: GPL-2.0-only
 *
 * GR Mod: per-film 3D colour LUT for the films of GR III 2.10 / GR IIIx 1.60 (round 10).
 *
 * Called at the start of JpegEncodeMacroProcess::Execute with the process configuration, FIRST in the chain
 * (before the film MTF, the halation, the grain and the date: it is colour correction, and the texture steps
 * that follow must see the corrected colour), on the YCbCr 4:2:2 pictures the JPEG encoder is about to compress
 * (main picture, screennail, thumbnail, so playback matches the file). When the picture's film has a LUT
 * (chosen per film in the build), each horizontal pixel pair gets a colour correction from a 33 x 33 x 33 table
 * of deltas (dY, dCb, dCr) in Q4 (sixteenths of a level), by tetrahedral interpolation. It is the integer
 * algorithm of tools/colour_engine/engine.py `lut_apply_422`, byte for byte (core/src/color/colourlut.ts is the
 * TypeScript reference, tools/colourlut/check.py compares the two in an emulator):
 *   - for the pair (Y0, Y1, Cb, Cr): the lookup point is (Ym, Cb, Cr) with Ym = (Y0 + Y1 + 1) >> 1;
 *   - each value v gives the node v >> 3 and the fraction v & 7 (eighths); the highest node is 31, so the
 *     tetrahedron's far corner is at most node 32 and the table never needs a 34th node;
 *   - the tetrahedron walks the axes by descending fraction (ties in the order Y, Cb, Cr):
 *     acc = 8 v0 + (v1 - v0) f0 + (v2 - v1) f1 + (v3 - v2) f2, delta = (acc + 64) >> 7 (arithmetic shift);
 *   - dY is added to both lumas of the pair, dCb and dCr to the chroma, each clipped to 0..255.
 * Pictures it does not know (another format, an odd or implausible size, a bad pointer) are left alone.
 *
 * Which film: `stash` (written by the development step that reads the frame's record, see jpeg-stage.ts):
 * bits 0..7 the look (film k as 32 + k), bit 16 valid. `look_map[look]` is 0 (no LUT) or n: the n-th table.
 * Tables: signed 16-bit, [Y node][Cb node][Cr node][dY dCb dCr], 33 * 33 * 33 * 3 values, Q4 deltas.
 *
 * Position-independent: no global data, every address comes in through `struct ctx`. No division (the module
 * must not need a run-time library).
 */
typedef unsigned char u8;
typedef signed char s8;
typedef unsigned short u16;
typedef short s16;
typedef unsigned int u32;
typedef int s32;

struct picture {
  u8 format;          /* 1: YCbCr 4:2:2, Cb/Cr interleaved in their own plane (Cb at the even byte, Cr at the odd one) */
  u8 pad[3];
  u8 *y;
  u8 *c;
  u32 size;
  u16 width, height, stride, c_height;
  u16 x, y_off;
  u8 tail[4];
};

struct ctx {
  void *(*cache)(void);
  void (*invalidate)(void *cache, u32 addr, u32 n);
  void (*clean)(void *cache, u32 addr, u32 n);
  const volatile u32 *stash;
  u32 magic;          /* 'CLU1' */
  u8 look_map[64];    /* look -> 0: no LUT, else 1..8: lut[n - 1] */
  const s16 *lut[8];  /* 33 * 33 * 33 * 3 Q4 deltas each */
};

#define STASH_VALID 0x10000u
#define MAGIC 0x31554c43u
#define S_Y 3267       /* values between neighbouring Y nodes: 33 * 33 * 3 */
#define S_CB 99        /* ... Cb nodes: 33 * 3 */
#define S_CR 3         /* ... Cr nodes */

static int ram(const void *p) {
  u32 a = (u32)p;
  return a >= 0x40000000u && a < 0xc0000000u && (a & 3) == 0;
}

static int picture_ok(const struct picture *p) {
  u32 w = p->width, h = p->height;
  if (p->format != 1 || !ram(p->y) || !ram(p->c) || w < 64 || h < 48 || p->stride < w || p->c_height < h) return 0;
  return w <= 12000 && h <= 12000 && !(w & 1) && !(h & 1);
}

static u8 clamp8(s32 v) { return (u8)(v < 0 ? 0 : v > 255 ? 255 : v); }

static void lut_picture(const struct ctx *k, void *cache, const struct picture *p, const s16 *lut) {
  u32 w = p->width, h = p->height, x, y, a, b, ca, cb;
  a = (u32)p->y & ~63u; b = ((u32)p->y + h * p->stride + 63) & ~63u;
  ca = (u32)p->c & ~63u; cb = ((u32)p->c + h * p->stride + 63) & ~63u;
  k->invalidate(cache, a, b - a);
  k->invalidate(cache, ca, cb - ca);
  for (y = 0; y < h; y++) {
    u8 *row = p->y + y * p->stride, *crow = p->c + y * p->stride;
    for (x = 0; x < w; x += 2) {
      s32 y0 = row[x], y1 = row[x + 1], cbv = crow[x], crv = crow[x + 1];
      s32 vy = (y0 + y1 + 1) >> 1;
      s32 f0 = vy & 7, f1 = cbv & 7, f2 = crv & 7, t;
      u32 s0 = S_Y, s1 = S_CB, s2 = S_CR, u;
      const s16 *p0 = lut + ((u32)(vy >> 3) * S_Y + (u32)(cbv >> 3) * S_CB + (u32)(crv >> 3) * S_CR);
      const s16 *p1, *p2, *p3;
      s32 dy, dcb, dcr;
      /* axes by descending fraction, stable (a later axis must be strictly greater to move up); s0..s2: the table steps of the axes in that order */
      if (f1 > f0) { t = f0; f0 = f1; f1 = t; u = s0; s0 = s1; s1 = u; }
      if (f2 > f1) { t = f1; f1 = f2; f2 = t; u = s1; s1 = s2; s2 = u; }
      if (f1 > f0) { t = f0; f0 = f1; f1 = t; u = s0; s0 = s1; s1 = u; }
      p1 = p0 + s0;
      p2 = p1 + s1;
      p3 = p2 + s2;
      dy = ((p0[0] << 3) + (p1[0] - p0[0]) * f0 + (p2[0] - p1[0]) * f1 + (p3[0] - p2[0]) * f2 + 64) >> 7;
      row[x] = clamp8(y0 + dy);
      row[x + 1] = clamp8(y1 + dy);
      __asm__ volatile("" ::: "memory");   /* one channel's values at a time: the registers are few */
      dcb = ((p0[1] << 3) + (p1[1] - p0[1]) * f0 + (p2[1] - p1[1]) * f1 + (p3[1] - p2[1]) * f2 + 64) >> 7;
      crow[x] = clamp8(cbv + dcb);
      __asm__ volatile("" ::: "memory");
      dcr = ((p0[2] << 3) + (p1[2] - p0[2]) * f0 + (p2[2] - p1[2]) * f1 + (p3[2] - p2[2]) * f2 + 64) >> 7;
      crow[x + 1] = clamp8(crv + dcr);
    }
  }
  k->clean(cache, a, b - a);
  k->clean(cache, ca, cb - ca);
}

/* Entry: k = context, config = JpegEncodeMacroProcess configuration. */
void colourlut(const struct ctx *k, u32 *config) {
  u32 st = *k->stash, look, n, i, j;
  const s16 *lut;
  struct picture *seen[4];
  void *cache;
  if (!(st & STASH_VALID) || !ram(config) || !ram(k) || k->magic != MAGIC) return;
  look = st & 0xff;
  if (look >= 64) return;
  n = k->look_map[look];
  if (!n || n > 8) return;
  lut = k->lut[n - 1];
  if (!ram(lut)) return;
  cache = k->cache();
  /* One picture per buffer (another entry with the same planes describes the whole sensor). */
  for (i = 0; i < 4; i++) {
    struct picture *p = (struct picture *)config[(0x3c >> 2) + i];
    seen[i] = 0;
    if (!ram(p) || !picture_ok(p)) continue;
    for (j = 0; j < i; j++) if (seen[j] && seen[j]->y == p->y) break;
    if (j == i) seen[i] = p;
  }
  for (i = 0; i < 4; i++) if (seen[i]) lut_picture(k, cache, seen[i], lut);
}
