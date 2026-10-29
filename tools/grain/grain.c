/* SPDX-License-Identifier: GPL-2.0-only
 *
 * GR Mod: film grain for the films of GR III 2.10 / GR IIIx 1.60 (round 10).
 *
 * Called at the start of JpegEncodeMacroProcess::Execute with the process configuration, after the
 * halation (tools/halation/halation.c) and before the date imprint, on the YCbCr 4:2:2 pictures the
 * JPEG encoder is about to compress (main picture, screennail, thumbnail). When the picture's film
 * has grain (chosen per film in GR Mod and fixed in the build), its brightness gets film grain:
 *   1. noise: a lattice of random values (two random bytes summed: a soft, bell-like spread) laid
 *      over the picture with a spacing relative to a 6000-pixel-wide main picture (the size of the
 *      grain), and read between its points (bilinear): soft clumps rather than pixel noise. On a
 *      picture smaller than the lattice (screennail, thumbnail) the lattice is one pixel and the
 *      noise is weakened by the same factor, as averaging the full-size grain would;
 *   2. strength by brightness: a table (256 values, made by GR Mod) shapes the grain like film's,
 *      strongest in the midtones, little in deep shadows and clipped highlights;
 *   3. only the brightness changes (Y); the colour (Cb, Cr) is left as it is.
 * Each picture gets its own random seed from a few of its pixels, so no two photos share a pattern.
 * GR Mod's preview runs the same integer steps (core/src/color/grain.ts).
 *
 * Which film: `stash` (written by the development step that reads the frame's record, see
 * jpeg-stage.ts): bits 0..7 the look (film k as 32 + k), bit 16 valid. `look_map[look]` is the
 * film's grain: 0 none, else amount (1 weak, 2 medium, 3 strong) | size << 2 (0 small, 1 large).
 *
 * Position-independent: no global data, every address comes in through `struct ctx`. No division
 * (the module must not need a run-time library).
 */
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef int s32;
typedef short s16;

struct picture {
  u8 format;          /* 1: YCbCr 4:2:2, Cb/Cr interleaved in their own plane */
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
  void *(*alloc)(u32 n);
  void (*release)(void *p);
  const volatile u32 *stash;
  const u8 *tone;     /* 3 x 256: strength by brightness (0..255) for weak, medium, strong */
  u16 amount[3];      /* noise gain of weak, medium, strong (of 256) */
  u16 cell[2];        /* lattice spacing of small and large grain, in 1/256 pixel of a 6000-wide picture */
  u32 magic;          /* 'GRN1' */
  u8 look_map[64];    /* look -> amount | size << 2, 0: no grain */
};

#define STASH_VALID 0x10000u
#define FULL_WIDTH 6000u

static int ram(const void *p) {
  u32 a = (u32)p;
  return a >= 0x40000000u && a < 0xc0000000u && (a & 3) == 0;
}

static int picture_ok(const struct picture *p) {
  u32 w = p->width, h = p->height;
  if (p->format != 1 || !ram(p->y) || !ram(p->c) || w < 64 || h < 48 || p->stride < w || p->c_height < h) return 0;
  return w <= 12000 && h <= 12000;
}

/* n / d, by shift and subtract. */
static u32 udiv(u32 n, u32 d) {
  u32 q = 0, r = 0;
  s32 i;
  if (!d) return 0;
  for (i = 31; i >= 0; i--) {
    r = (r << 1) | ((n >> i) & 1);
    if (r >= d) { r -= d; q |= 1u << i; }
  }
  return q;
}

/* A lattice point's value: -255..255, two random bytes summed (a triangular spread). */
static s32 noise(u32 i, u32 j, u32 seed) {
  u32 h = i * 0x9e3779b1u ^ j * 0x85ebca77u ^ seed;
  h ^= h >> 15; h *= 0x2c1b3c6du; h ^= h >> 12; h *= 0x297a2d39u; h ^= h >> 15;
  return (s32)(h & 0xff) + (s32)((h >> 8) & 0xff) - 255;
}

static void lattice_row(s16 *row, u32 n, u32 j, u32 seed) {
  u32 i;
  for (i = 0; i < n; i++) row[i] = (s16)noise(i, j, seed);
}

static void grain_picture(const struct ctx *k, void *cache, const struct picture *p, u32 setting) {
  u32 w = p->width, h = p->height, amount = setting & 3, size = (setting >> 2) & 1;
  u32 cell, att = 256, step, nx, x, y, j0, seed, a, b;
  s32 gain;
  s16 *ra = 0, *rb = 0;
  s32 *mix = 0;
  const u8 *tone = k->tone + (amount - 1) * 256;
  /* Lattice spacing on this picture, 8.8 pixels: the full-size spacing scaled to the width. */
  cell = udiv((u32)k->cell[size] * w, FULL_WIDTH);
  if (cell < 256) { att = cell; cell = 256; }
  gain = (s32)((k->amount[amount - 1] * att) >> 8);
  if (!gain) return;
  step = udiv(256u << 16, cell);          /* lattice units per pixel, 16.16 */
  nx = ((w * step) >> 16) + 3;
  ra = (s16 *)k->alloc(nx * 2);
  rb = (s16 *)k->alloc(nx * 2);
  mix = (s32 *)k->alloc(nx * 4);
  if (!ra || !rb || !mix) goto out;
  a = (u32)p->y & ~63u; b = ((u32)p->y + h * p->stride + 63) & ~63u;
  k->invalidate(cache, a, b - a);
  /* The seed: the picture's size and a few of its pixels. */
  seed = w * 0x10001u + h;
  for (y = 0; y < 8; y++) seed = seed * 0x01000193u ^ p->y[((h * y) >> 3) * p->stride + ((w * (7 - y)) >> 3)];
  j0 = 0;
  lattice_row(ra, nx, 0, seed);
  lattice_row(rb, nx, 1, seed);
  for (y = 0; y < h; y++) {
    u32 py = y * step, j = py >> 16, fy = (py >> 8) & 255, i, px;
    u8 *row = p->y + y * p->stride;
    while (j0 < j) {
      s16 *t = ra; ra = rb; rb = t;
      j0++;
      lattice_row(rb, nx, j0 + 1, seed);
    }
    for (i = 0; i < nx; i++) mix[i] = (s32)ra[i] * 256 + ((s32)rb[i] - (s32)ra[i]) * (s32)fy;   /* x 256 */
    for (x = 0, px = 0; x < w; x++, px += step) {
      u32 li = px >> 16, fx = (px >> 8) & 255;
      s32 v = (mix[li] * (256 - (s32)fx) + mix[li + 1] * (s32)fx) >> 16;      /* -255..255 */
      s32 Y = row[x];
      s32 d = (v * gain * (s32)tone[Y]) >> 16;
      Y += d;
      row[x] = (u8)(Y < 0 ? 0 : Y > 255 ? 255 : Y);
    }
  }
  k->clean(cache, a, b - a);
out:
  if (ra) k->release(ra);
  if (rb) k->release(rb);
  if (mix) k->release(mix);
}

/* Entry: k = context, config = JpegEncodeMacroProcess configuration. */
void grain(const struct ctx *k, u32 *config) {
  u32 st = *k->stash, look, setting, i, j;
  struct picture *seen[4];
  void *cache;
  if (!(st & STASH_VALID) || !ram(config) || !ram(k->tone) || k->magic != 0x314e5247u) return;
  look = st & 0xff;
  if (look >= 64) return;
  setting = k->look_map[look];
  if (!(setting & 3)) return;
  cache = k->cache();
  /* One picture per buffer (another entry with the same planes describes the whole sensor). */
  for (i = 0; i < 4; i++) {
    struct picture *p = (struct picture *)config[(0x3c >> 2) + i];
    seen[i] = 0;
    if (!ram(p) || !picture_ok(p)) continue;
    for (j = 0; j < i; j++) if (seen[j] && seen[j]->y == p->y) break;
    if (j == i) seen[i] = p;
  }
  for (i = 0; i < 4; i++) if (seen[i]) grain_picture(k, cache, seen[i], setting);
}
