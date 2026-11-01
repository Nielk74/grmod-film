/* SPDX-License-Identifier: GPL-2.0-only
 *
 * GR Mod: film MTF for the films of GR III 2.10 / GR IIIx 1.60 (round 10).
 *
 * Called at the start of JpegEncodeMacroProcess::Execute with the process configuration, before the
 * halation (tools/halation) and the grain (tools/grain), on the YCbCr 4:2:2 pictures the JPEG encoder is
 * about to compress. When the picture's film has the film MTF (chosen per film in the build), the main
 * picture's detail is reshaped the way a negative film's dye layers do it (Kodak Portra 400's MTF
 * curves, E-4050): a boost of 8..33 pixel structures and a roll-off of the finest detail, softest in the
 * red layer. core/src/color/filmmtf.ts describes the method and is the reference this module matches
 * byte for byte (tools/filmmtf/check.py):
 *   - a three-level Laplacian pyramid of the picture (Gaussian REDUCE [1 4 6 4 1] each way, bilinear
 *     EXPAND), each band mixed by a 3x3 matrix (Q12, from the layers' gains) acting on (Y, Cb, Cr),
 *     recombined as out = A0 L0 + EXPAND(D1 L1 + EXPAND(D2 L2 + EXPAND(D3 L3)));
 *   - done in strips of 192 rows with 32 rows of margin, so it needs a few megabytes, not a picture copy;
 *   - the pictures it does not know (another format, a width under 4096 or not a multiple of 8, ...)
 *     are left alone, and so is everything if memory is short.
 *
 * Which film: `stash` (written by the development step that reads the frame's record, see
 * jpeg-stage.ts): bits 0..7 the look (film k as 32 + k), bit 16 valid. `look_map[look]` != 0: on.
 *
 * Position-independent: no global data, every address comes in through `struct ctx`. No division
 * (the module must not need a run-time library).
 */
typedef unsigned char u8;
typedef signed char s8;
typedef unsigned short u16;
typedef short s16;
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
  u32 magic;          /* 'MTF1' */
  s16 mix[36];        /* four 3x3 matrices (Q12, rows Y Cb Cr): A0, D1 = A1 - A0, D2 = A2 - A1, D3 = I - A2 (filmmtf.ts) */
  u8 look_map[64];    /* look -> 1: film MTF */
};

#define STASH_VALID 0x10000u
#define MAGIC 0x3146544du
#define STRIP 192u
#define MARGIN 32u
#define MIN_WIDTH 4096u

static int ram(const void *p) {
  u32 a = (u32)p;
  return a >= 0x40000000u && a < 0xc0000000u && (a & 3) == 0;
}

static int picture_ok(const struct picture *p) {
  u32 w = p->width, h = p->height;
  if (p->format != 1 || !ram(p->y) || !ram(p->c) || w < MIN_WIDTH || h < 64 || p->stride < w || p->c_height < h) return 0;
  return w <= 12000 && h <= 12000 && !(w & 7) && !(h & 7);
}

static u8 clamp8(s32 v) { return (u8)(v < 0 ? 0 : v > 255 ? 255 : v); }
static u32 clampi(s32 v, u32 n) { return (u32)(v < 0 ? 0 : (u32)v >= n ? (s32)n - 1 : v); }

struct work {
  u16 *ht;                   /* horizontal pass of the luma reduction: w1 x eh */
  s16 *l1[3], *l2[3], *l3[3];/* Y, Cb, Cr (sixteenths) at 1/2, 1/4, 1/8 */
  s32 *tmp;
  u8 *carry_y, *carry_c;     /* the original rows that are the next strip's top margin */
  u8 *crow;                  /* the original chroma row being written */
};

/* 5x5 REDUCE of one s16 plane (sixteenths) to half size. */
static void reduce(const s16 *src, u32 w, u32 h, s16 *dst, s32 *tmp) {
  u32 w2 = w >> 1, h2 = h >> 1, x, y;
  for (y = 0; y < h; y++) {
    const s16 *r = src + y * w;
    s32 *t = tmp + y * w2;
    t[0] = 11 * r[0] + 4 * r[1] + r[2];                             /* the three taps up to the centre repeat r[0] (1 + 4 + 6) */
    for (x = 1; x < w2 - 1; x++) t[x] = r[2 * x - 2] + 4 * r[2 * x - 1] + 6 * r[2 * x] + 4 * r[2 * x + 1] + r[2 * x + 2];
    t[w2 - 1] = r[w - 4] + 4 * r[w - 3] + 6 * r[w - 2] + 4 * r[w - 1] + r[w - 1];
  }
  for (y = 0; y < h2; y++) {
    const s32 *t0 = tmp + clampi(2 * (s32)y - 2, h) * w2, *t1 = tmp + clampi(2 * (s32)y - 1, h) * w2, *t2 = tmp + 2 * y * w2;
    const s32 *t3 = tmp + clampi(2 * (s32)y + 1, h) * w2, *t4 = tmp + clampi(2 * (s32)y + 2, h) * w2;
    s16 *d = dst + y * w2;
    for (x = 0; x < w2; x++) d[x] = (s16)((t0[x] + 4 * t1[x] + 6 * t2[x] + 4 * t3[x] + t4[x] + 128) >> 8);
  }
}

/* `m` is a local s32[9] (a copy of a matrix: stores through byte or halfword pointers must not make the compiler reload it). */
#define MIXY(m, y, b, c) ((((m)[0] * (y)) + ((m)[1] * (b)) + ((m)[2] * (c)) + 2048) >> 12)
#define MIXB(m, y, b, c) ((((m)[3] * (y)) + ((m)[4] * (b)) + ((m)[5] * (c)) + 2048) >> 12)
#define MIXC(m, y, b, c) ((((m)[6] * (y)) + ((m)[7] * (b)) + ((m)[8] * (c)) + 2048) >> 12)

/* L = D L + EXPAND(up), in place, for the three planes of a level (up: the level above, uw x uh; 0: none).
 * EXPAND of an output pixel (x, y) at (x / 2, y / 2) of the plane above: even coordinates take that sample, odd ones average it with
 * the next (the last repeats): (s00 + s01 + s10 + s11 + 2) >> 2 over the (up to) four samples. */
static void level(s16 *const l[3], u32 w, u32 h, const s16 *const up[3], u32 uw, u32 uh, const s16 *dm) {
  u32 x, y, i;
  s32 d[9];
  for (i = 0; i < 9; i++) d[i] = dm[i];
  if (!up) {
    for (y = 0; y < h; y++) {
      s16 *ra = l[0] + y * w, *rb = l[1] + y * w, *rc = l[2] + y * w;
      for (x = 0; x < w; x++) {
        s32 a = ra[x], b = rb[x], c = rc[x];
        ra[x] = (s16)MIXY(d, a, b, c); rb[x] = (s16)MIXB(d, a, b, c); rc[x] = (s16)MIXC(d, a, b, c);
      }
    }
    return;
  }
  /* two output columns (even, odd) per sample of the level above: w = 2 uw */
  for (y = 0; y < h; y++) {
    u32 y0 = y >> 1, y1 = (y & 1) ? (y0 + 1 < uh ? y0 + 1 : uh - 1) : y0, x0;
    s16 *ra = l[0] + y * w, *rb = l[1] + y * w, *rc = l[2] + y * w;
    const s16 *ua0 = up[0] + y0 * uw, *ua1 = up[0] + y1 * uw, *ub0 = up[1] + y0 * uw, *ub1 = up[1] + y1 * uw, *uc0 = up[2] + y0 * uw, *uc1 = up[2] + y1 * uw;
    for (x0 = 0; x0 < uw; x0++) {
      u32 x1 = x0 + 1 < uw ? x0 + 1 : x0;
      s32 pa = ua0[x0], qa = ua0[x1], ra1 = ua1[x0], sa = ua1[x1];
      s32 pb = ub0[x0], qb = ub0[x1], rb1 = ub1[x0], sb = ub1[x1];
      s32 pc = uc0[x0], qc = uc0[x1], rc1 = uc1[x0], sc = uc1[x1];
      s32 a = ra[2 * x0], b = rb[2 * x0], c = rc[2 * x0];
      ra[2 * x0] = (s16)(MIXY(d, a, b, c) + ((pa + ra1 + 1) >> 1));
      rb[2 * x0] = (s16)(MIXB(d, a, b, c) + ((pb + rb1 + 1) >> 1));
      rc[2 * x0] = (s16)(MIXC(d, a, b, c) + ((pc + rc1 + 1) >> 1));
      a = ra[2 * x0 + 1]; b = rb[2 * x0 + 1]; c = rc[2 * x0 + 1];
      ra[2 * x0 + 1] = (s16)(MIXY(d, a, b, c) + ((pa + qa + ra1 + sa + 2) >> 2));
      rb[2 * x0 + 1] = (s16)(MIXB(d, a, b, c) + ((pb + qb + rb1 + sb + 2) >> 2));
      rc[2 * x0 + 1] = (s16)(MIXC(d, a, b, c) + ((pc + qc + rc1 + sc + 2) >> 2));
    }
  }
}

/* Level 0 for the chroma pairs of a row: A0 (Y, Cb, Cr) + EXPAND(m1), sixteenths. The expansion of m1 on an odd row averages two rows
 * of the plane above, on an even row it is the one row (the sums below equal the four-sample form of filmmtf.ts exactly). */
static void row_chroma(u8 *crow, const u8 *yrow, const u8 *corig, u32 w1, const s32 *a, const s16 *cb0, const s16 *cb1, const s16 *cc0, const s16 *cc1, u32 odd) {
  u32 j;
  s32 a3 = a[3], a4 = a[4], a5 = a[5], a6 = a[6], a7 = a[7], a8 = a[8];
  for (j = 0; j < w1; j++) {
    s32 ybar = (yrow[2 * j] + yrow[2 * j + 1]) * 8, cb = ((s32)corig[2 * j] - 128) * 16, cc = ((s32)corig[2 * j + 1] - 128) * 16;
    s32 ecb = odd ? ((s32)cb0[j] + cb1[j] + 1) >> 1 : cb0[j], ecc = odd ? ((s32)cc0[j] + cc1[j] + 1) >> 1 : cc0[j];
    s32 cbv = ((a3 * ybar + a4 * cb + a5 * cc + 2048) >> 12) + ecb, crv = ((a6 * ybar + a7 * cb + a8 * cc + 2048) >> 12) + ecc;
    crow[2 * j] = clamp8(((cbv + 8) >> 4) + 128);
    crow[2 * j + 1] = clamp8(((crv + 8) >> 4) + 128);
  }
}

/* Level 0 for the luma of a row: A0 (Y, Cb, Cr) + EXPAND(m1), the pair's chroma shared by its two pixels. */
static void row_luma(u8 *yrow, const u8 *syrow, const u8 *corig, u32 w1, const s32 *a, const s16 *ma, const s16 *mb, u32 odd) {
  u32 j;
  s32 a0 = a[0], a1 = a[1], a2 = a[2];
  for (j = 0; j < w1; j++) {
    u32 jn = j + 1 < w1 ? j + 1 : w1 - 1;
    s32 ya = syrow[2 * j] * 16, yb = syrow[2 * j + 1] * 16, tc = a1 * (((s32)corig[2 * j] - 128) * 16) + a2 * (((s32)corig[2 * j + 1] - 128) * 16) + 2048;
    s32 ea, eb;
    if (odd) { ea = ((s32)ma[j] + mb[j] + 1) >> 1; eb = ((s32)ma[j] + ma[jn] + mb[j] + mb[jn] + 2) >> 2; }
    else { ea = ma[j]; eb = ((s32)ma[j] + ma[jn] + 1) >> 1; }
    yrow[2 * j] = clamp8((((a0 * ya + tc) >> 12) + ea + 8) >> 4);
    yrow[2 * j + 1] = clamp8((((a0 * yb + tc) >> 12) + eb + 8) >> 4);
  }
}

static void process(const struct ctx *k, const struct picture *p, struct work *wk) {
  u32 w = p->width, h = p->height, stride = p->stride, w1 = w >> 1, core0, x, y, j;
  const s16 *D1 = k->mix + 9, *D2 = k->mix + 18, *D3 = k->mix + 27;
  s32 A0[9];
  for (j = 0; j < 9; j++) A0[j] = k->mix[j];
  for (core0 = 0; core0 < h; core0 += STRIP) {
    u32 core1 = core0 + STRIP < h ? core0 + STRIP : h;
    u32 e0 = core0 > MARGIN ? core0 - MARGIN : 0, e1 = core1 + MARGIN < h ? core1 + MARGIN : h;
    u32 eh = e1 - e0, top = core0 - e0, h1 = eh >> 1, h2 = h1 >> 1, h3 = h2 >> 1, w2 = w1 >> 1, w3 = w2 >> 1, rows = core1 - core0;
    s16 *l1[3] = { wk->l1[0], wk->l1[1], wk->l1[2] }, *l2[3] = { wk->l2[0], wk->l2[1], wk->l2[2] }, *l3[3] = { wk->l3[0], wk->l3[1], wk->l3[2] };
#define YROW(i) ((i) < top ? wk->carry_y + (i) * w : p->y + (e0 + (i)) * stride)
#define CROW(i) ((i) < top ? wk->carry_c + (i) * w : p->c + (e0 + (i)) * stride)
    /* level 1: luma 5x5, chroma rows only */
    for (y = 0; y < eh; y++) {
      const u8 *r = YROW(y);
      u16 *o = wk->ht + y * w1;
      o[0] = (u16)(11 * r[0] + 4 * r[1] + r[2]);
      for (x = 1; x < w1 - 1; x++) o[x] = (u16)(r[2 * x - 2] + 4 * r[2 * x - 1] + 6 * r[2 * x] + 4 * r[2 * x + 1] + r[2 * x + 2]);
      o[w1 - 1] = (u16)(r[w - 4] + 4 * r[w - 3] + 6 * r[w - 2] + 4 * r[w - 1] + r[w - 1]);
    }
    for (y = 0; y < h1; y++) {
      u32 r0 = clampi(2 * (s32)y - 2, eh), r1 = clampi(2 * (s32)y - 1, eh), r2 = 2 * y, r3 = clampi(2 * (s32)y + 1, eh), r4 = clampi(2 * (s32)y + 2, eh);
      const u16 *t0 = wk->ht + r0 * w1, *t1 = wk->ht + r1 * w1, *t2 = wk->ht + r2 * w1, *t3 = wk->ht + r3 * w1, *t4 = wk->ht + r4 * w1;
      const u8 *c0 = CROW(r0), *c1 = CROW(r1), *c2 = CROW(r2), *c3 = CROW(r3), *c4 = CROW(r4);
      s16 *oa = l1[0] + y * w1, *ob = l1[1] + y * w1, *oc = l1[2] + y * w1;
      for (x = 0; x < w1; x++) oa[x] = (s16)((s32)((u32)t0[x] + 4 * t1[x] + 6 * t2[x] + 4 * t3[x] + t4[x] + 8) >> 4);
      for (x = 0; x < w1; x++) {
        ob[x] = (s16)(c0[2 * x] + 4 * c1[2 * x] + 6 * c2[2 * x] + 4 * c3[2 * x] + c4[2 * x] - 2048);
        oc[x] = (s16)(c0[2 * x + 1] + 4 * c1[2 * x + 1] + 6 * c2[2 * x + 1] + 4 * c3[2 * x + 1] + c4[2 * x + 1] - 2048);
      }
    }
    for (j = 0; j < 3; j++) { reduce(l1[j], w1, h1, l2[j], wk->tmp); reduce(l2[j], w2, h2, l3[j], wk->tmp); }
    /* the original rows the next strip uses as its top margin, before this strip is written */
    {
      u32 next = rows < MARGIN ? rows : MARGIN, src = top + rows - next, r, i;
      for (r = 0; r < next; r++) {
        const u8 *sy = YROW(src + r), *sc = CROW(src + r);
        for (i = 0; i < w; i++) { wk->carry_y[r * w + i] = sy[i]; wk->carry_c[r * w + i] = sc[i]; }
      }
    }
    /* top-down: m3 = D3 L3, m2 = D2 L2 + EXPAND(m3), m1 = D1 L1 + EXPAND(m2), each in place */
    level(l3, w3, h3, 0, 0, 0, D3);
    level(l2, w2, h2, (const s16 *const *)l3, w3, h3, D2);
    level(l1, w1, h1, (const s16 *const *)l2, w2, h2, D1);
    /* level 0: A0 L0 + EXPAND(m1) for the core rows */
    for (y = top; y < top + rows; y++) {
      u32 y0 = y >> 1, y1 = (y & 1) ? (y0 + 1 < h1 ? y0 + 1 : h1 - 1) : y0;
      u8 *yrow = p->y + (e0 + y) * stride, *crow = p->c + (e0 + y) * stride;
      const u8 *syrow = YROW(y);
      const s16 *ma = l1[0] + y0 * w1, *mb = l1[0] + y1 * w1;
      /* The chroma pass reads the original luma and chroma rows and writes the chroma; the luma pass then reads the luma and the saved
       * copy of the original chroma. */
      for (j = 0; j < w; j++) wk->crow[j] = crow[j];
      row_chroma(crow, syrow, wk->crow, w1, A0, l1[1] + y0 * w1, l1[1] + y1 * w1, l1[2] + y0 * w1, l1[2] + y1 * w1, y & 1);
      row_luma(yrow, syrow, wk->crow, w1, A0, ma, mb, y & 1);
    }
  }
}

static void film_mtf(const struct ctx *k, void *cache, const struct picture *p) {
  u32 w = p->width, h = p->height, w1 = w >> 1, eh = STRIP + 2 * MARGIN, j;
  struct work wk;
  u32 a = (u32)p->y & ~63u, b = ((u32)p->y + h * p->stride + 63) & ~63u;
  u32 ca = (u32)p->c & ~63u, cb = ((u32)p->c + h * p->stride + 63) & ~63u;
  u32 n1 = w1 * (eh >> 1), n2 = (w1 >> 1) * (eh >> 2), n3 = (w1 >> 2) * (eh >> 3);
  u8 *mem[16];
  u32 count = 0;
  for (j = 0; j < 16; j++) mem[j] = 0;
#define GET(var, type, n) do { var = (type)k->alloc((n) * sizeof(*var) + 8); if (!var) goto fail; mem[count++] = (u8 *)var; } while (0)
  GET(wk.ht, u16 *, w1 * eh);
  for (j = 0; j < 3; j++) { GET(wk.l1[j], s16 *, n1); GET(wk.l2[j], s16 *, n2); GET(wk.l3[j], s16 *, n3); }
  GET(wk.tmp, s32 *, (w1 >> 1) * (eh >> 1));
  GET(wk.carry_y, u8 *, MARGIN * w);
  GET(wk.carry_c, u8 *, MARGIN * w);
  GET(wk.crow, u8 *, w);
  k->invalidate(cache, a, b - a);
  k->invalidate(cache, ca, cb - ca);
  process(k, p, &wk);
  k->clean(cache, a, b - a);
  k->clean(cache, ca, cb - ca);
fail:
  for (j = 0; j < count; j++) k->release(mem[j]);
}

/* Entry: k = context, config = JpegEncodeMacroProcess configuration. */
void filmmtf(const struct ctx *k, u32 *config) {
  u32 st = *k->stash, look, i, j;
  struct picture *seen[4];
  void *cache;
  if (!(st & STASH_VALID) || !ram(config) || k->magic != MAGIC) return;
  look = st & 0xff;
  if (look >= 64 || !k->look_map[look]) return;
  cache = k->cache();
  /* One picture per buffer (another entry with the same planes describes the whole sensor). */
  for (i = 0; i < 4; i++) {
    struct picture *p = (struct picture *)config[(0x3c >> 2) + i];
    seen[i] = 0;
    if (!ram(p) || !picture_ok(p)) continue;
    for (j = 0; j < i; j++) if (seen[j] && seen[j]->y == p->y) break;
    if (j == i) seen[i] = p;
  }
  for (i = 0; i < 4; i++) if (seen[i]) film_mtf(k, cache, seen[i]);
}
