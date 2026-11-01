/* SPDX-License-Identifier: GPL-2.0-only
 *
 * GR Mod: film grain for the films of GR III 2.10 / GR IIIx 1.60 (round 10), version 2.
 *
 * Called at the start of JpegEncodeMacroProcess::Execute with the process configuration, after the
 * halation (tools/halation/halation.c) and before the date imprint, on the YCbCr 4:2:2 pictures the
 * JPEG encoder is about to compress (main picture, screennail, thumbnail). When the picture's film
 * has grain (chosen per film in GR Mod and fixed in the build, or the camera's Grain row), the
 * picture gets film grain:
 *   1. grain from a tile: film grain is dye clouds, crisp and of several sizes, formed largely
 *      independently in each colour layer. GR Mod cuts a 128 x 128 tile of it per grain size from
 *      the Boolean film grain model (tools/grain/tiles.py): a luma tile and a colour tile of (Cb, Cr)
 *      pairs, one per two pixels as 4:2:2 stores them. The tile is laid over the picture in 32-pixel
 *      blocks, each at a random offset in the tile (as AV1's film grain synthesis), so it does not
 *      repeat; its scale is relative to a 6000-pixel-wide main picture: on a smaller picture
 *      (screennail, thumbnail) the tile is read with a stride and the grain weakened by the same
 *      factor, as averaging the full-size grain would;
 *   2. strength by brightness: a table per size (GR Mod's, measured on the model over real
 *      photographs) makes the grain strongest in the shadows and lower midtones, fading towards the
 *      highlights, none at black and white;
 *   3. brightness (Y) and, about a third as strong, colour (Cb, Cr) change, both by the brightness of
 *      the pixel (of the pair's first pixel for the colour). Steps are rounded to nearest.
 * Each picture gets its own random offsets from a seed made of a few of its pixels, so no two photos
 * share a pattern. GR Mod's preview runs the same integer steps (core/src/color/grain.ts).
 *
 * Version 1 (an interpolated lattice of random values, brightness only) is in the history.
 *
 * Which film: `stash` (written by the development step that reads the frame's record, see
 * jpeg-stage.ts): bits 0..7 the look (film k as 32 + k), bit 16 valid. `look_map[look]` is the
 * film's grain: 0 none, else amount (1 weak, 2 medium, 3 strong) | size << 2 (0 small, 1 large).
 *
 * Position-independent: no global data, every address comes in through `struct ctx`. No division
 * (the module must not need a run-time library).
 */
typedef unsigned char u8;
typedef signed char s8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef int s32;

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
  const u8 *tone;     /* 2 x 256: strength by brightness of small, large grain (128: as at mid grey) */
  u16 gain[3];        /* weak, medium, strong: the grain's luma RMS at mid grey, x 16 */
  u16 pad;
  u32 magic;          /* 'GRN2' */
  u8 look_map[64];    /* look -> amount | size << 2, 0: no grain */
  const s8 *luma[2];  /* 128 x 128 luma tiles of small, large grain (standard deviation 32) */
  const s8 *colour[2]; /* 128 rows of 64 (Cb, Cr) pairs, the same scale */
};

#define STASH_VALID 0x10000u
#define FULL_WIDTH 6000u
#define MAGIC 0x324e5247u
#define T 128u              /* tile size */
#define B 5                 /* block size: 32 pixels */

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

/* A block's offset in the tile: x in bits 0..6, y in bits 8..14. */
static u32 offset(u32 i, u32 j, u32 seed) {
  u32 h = i * 0x9e3779b1u ^ j * 0x85ebca77u ^ seed;
  h ^= h >> 15; h *= 0x2c1b3c6du; h ^= h >> 12; h *= 0x297a2d39u; h ^= h >> 15;
  return h & 0x7f7fu;
}

static u8 clamp8(s32 v) { return (u8)(v < 0 ? 0 : v > 255 ? 255 : v); }

static void grain_picture(const struct ctx *k, void *cache, const struct picture *p, u32 setting) {
  u32 w = p->width, h = p->height, amount = setting & 3, size = (setting >> 2) & 1;
  u32 step, att = 256, nbx, x, y, seed, a, b, ca, cb;
  s32 gain;
  u16 *offs;
  const u8 *tone = k->tone + size * 256;
  const s8 *lt = k->luma[size], *ct = k->colour[size];
  /* Tile pixels per picture pixel, 8.8: 1 on the full-size picture, more on smaller ones. */
  step = udiv(FULL_WIDTH << 8, w);
  if (step > 256) att = udiv(65536u, step);
  gain = (s32)((k->gain[amount - 1] * att) >> 8);
  if (!gain || !ram(lt) || !ram(ct)) return;
  nbx = (w + 31) >> B;
  offs = (u16 *)k->alloc(nbx * 2);
  if (!offs) return;
  a = (u32)p->y & ~63u; b = ((u32)p->y + h * p->stride + 63) & ~63u;
  ca = (u32)p->c & ~63u; cb = ((u32)p->c + h * p->stride + 63) & ~63u;
  k->invalidate(cache, a, b - a);
  k->invalidate(cache, ca, cb - ca);
  /* The seed: the picture's size and a few of its pixels. */
  seed = w * 0x10001u + h;
  for (y = 0; y < 8; y++) seed = seed * 0x01000193u ^ p->y[((h * y) >> 3) * p->stride + ((w * (7 - y)) >> 3)];
  for (y = 0; y < h; y++) {
    u8 *row = p->y + y * p->stride, *crow = p->c + y * p->stride;
    u32 ty0 = ((y & 31) * step) >> 8;
    if (!(y & 31)) for (x = 0; x < nbx; x++) offs[x] = (u16)offset(x, y >> B, seed);
    for (x = 0; x < w; x++) {
      u32 o = offs[x >> B];
      u32 ty = ((o >> 8) + ty0) & (T - 1);
      u32 tx = (o + ((((x & 31) * step) >> 8))) & (T - 1);
      s32 Y = row[x], t = tone[Y];
      s32 f = gain * t;
      row[x] = clamp8(Y + ((lt[ty * T + tx] * f + 32768) >> 16));
      if (!(x & 1) && x + 1 < w) {
        const s8 *c = ct + ty * T + (tx & ~1u);
        crow[x] = clamp8(crow[x] + ((c[0] * f + 32768) >> 16));
        crow[x + 1] = clamp8(crow[x + 1] + ((c[1] * f + 32768) >> 16));
      }
    }
  }
  k->clean(cache, a, b - a);
  k->clean(cache, ca, cb - ca);
  k->release(offs);
}

/* Entry: k = context, config = JpegEncodeMacroProcess configuration. */
void grain(const struct ctx *k, u32 *config) {
  u32 st = *k->stash, look, setting, i, j;
  struct picture *seen[4];
  void *cache;
  if (!(st & STASH_VALID) || !ram(config) || !ram(k->tone) || k->magic != MAGIC) return;
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
