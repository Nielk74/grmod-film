/* SPDX-License-Identifier: GPL-2.0-only */
/* Freestanding port of src/renderer.mjs. Every function mirrors its JS counterpart so the two can be
 * compared pixel for pixel (native/check_loaded.py). Integer arithmetic only; signed right shifts are
 * arithmetic (as JS >>); divisions are truncating (as JS / then |0). */
#include "loaded.h"
#include "loaded_data.h"
/* The roll length the counter, the "FRAMES EXPOSED" text and the rewind use. 36 always, except in the stage 5a TEST image (-DGRMOD_ROLL_LEN=3) where a roll
 * is three frames; the contact sheet itself always shows 36 frames. */
#ifdef GRMOD_ROLL_LEN
#define RLEN GRMOD_ROLL_LEN
#else
#define RLEN LD_ROLL_LENGTH
#endif

#define W 720
#define H 480
#define ONE 1024

enum { P_T, P_BLK, P_GRY, P_EDGE, P_WHT, P_PAPER, P_MID, P_INK, P_PANEL, P_BAND, P_FINK, P_CINK, P_RED, P_SHADE, P_BAR,
  P_MILK0, P_MILK1, P_HOLE, P_DIG, P_METL, P_METD, P_LEAD, P_BEZ, P_MSH, P_ISH, P_TA, P_TB, P_TC, P_UNX };
enum { K_NEG, K_BW, K_SLIDE, K_INSTANT, K_CINE };

const uint32_t loaded_state_bytes = sizeof(loaded);
const uint16_t loaded_view_rect[LOADED_VIEWS][4] = LD_VIEW_RECTS;

/* ---------------------------------------------------------------- integer helpers */
static uint32_t div_u(uint32_t n, uint32_t d) { /* no compiler division helper is linked */
  uint32_t q = 0, bit = 1;
  if (!d) return 0;
  while (d <= (n >> 1) && !(d & 0x80000000u)) { d <<= 1; bit <<= 1; }
  while (bit) { if (n >= d) { n -= d; q |= bit; } d >>= 1; bit >>= 1; }
  return q;
}
static int32_t div_i(int32_t n, int32_t d) {
  uint32_t a = n < 0 ? 0u - (uint32_t)n : (uint32_t)n, b = d < 0 ? 0u - (uint32_t)d : (uint32_t)d;
  int32_t q = (int32_t)div_u(a, b);
  return (n < 0) != (d < 0) ? -q : q;
}
static int32_t mod_i(int32_t n, int32_t d) { return n - div_i(n, d) * d; }

static int32_t prog(int32_t t, int32_t a, int32_t b) {
  if (t <= a) return 0;
  if (t >= b) return ONE;
  return (int32_t)div_u((uint32_t)(t - a) * (uint32_t)ONE, (uint32_t)(b - a));
}
static int32_t lerp(int32_t a, int32_t b, int32_t e) { return a + (((b - a) * e) >> 10); }
static int32_t in_out(int32_t t) { int32_t s2 = (t * t) >> 10; return (s2 * (3 * ONE - 2 * t)) >> 10; }
static int32_t out_cubic(int32_t t) { int32_t u = ONE - t, u2 = (u * u) >> 10; return ONE - ((u2 * u) >> 10); }
static int32_t in_cubic(int32_t t) { int32_t t2 = (t * t) >> 10; return (t2 * t) >> 10; }
static int32_t out_back(int32_t t) {
  int32_t u = t - ONE, u2 = (u * u) >> 10, u3 = (u2 * u) >> 10;
  return ONE + ((2766 * u3) >> 10) + ((1743 * u2) >> 10);
}
static int32_t out_bounce(int32_t t) {
  int32_t u;
  if (t < 372) return (7744 * ((t * t) >> 10)) >> 10;
  if (t < 744) { u = t - 558; return ((7744 * ((u * u) >> 10)) >> 10) + 768; }
  if (t < 930) { u = t - 837; return ((7744 * ((u * u) >> 10)) >> 10) + 960; }
  u = t - 977; return ((7744 * ((u * u) >> 10)) >> 10) + 1008;
}
static uint32_t hash32(uint32_t a, uint32_t b) {
  uint32_t h = (a * 0x9e3779b1u) ^ ((b + 0x7f4a7c15u) * 0x85ebca6bu);
  h ^= h >> 15; h *= 0x2c1b3c6du; h ^= h >> 12; h *= 0x297a2d39u; h ^= h >> 15;
  return h;
}
static uint32_t slen(const char *s) { uint32_t n = 0; while (s[n]) n++; return n; }
static int32_t imax(int32_t a, int32_t b) { return a > b ? a : b; }
static int32_t imin(int32_t a, int32_t b) { return a < b ? a : b; }

/* ---------------------------------------------------------------- surface (draws RGBA directly through the palette) */
typedef struct {
  uint32_t *px; int32_t stride, w, h, cx0, cy0, cx1, cy1, ox, oy; const uint32_t *pal;
} surf;

static void s_init(surf *s, uint32_t *px, uint32_t stride, int32_t w, int32_t h, const uint32_t *pal) {
  s->px = px; s->stride = (int32_t)stride; s->w = w; s->h = h; s->pal = pal;
  s->cx0 = 0; s->cy0 = 0; s->cx1 = w; s->cy1 = h; s->ox = 0; s->oy = 0;
}
static void s_clear(surf *s) {
  int32_t x, y;
  for (y = 0; y < s->h; y++) { uint32_t *q = s->px + y * s->stride; for (x = 0; x < s->w; x++) *q++ = 0; }
  s->cx0 = 0; s->cy0 = 0; s->cx1 = s->w; s->cy1 = s->h; s->ox = 0; s->oy = 0;
}
static void s_clip(surf *s, int32_t x, int32_t y, int32_t w, int32_t h) {
  x += s->ox; y += s->oy;
  s->cx0 = imax(0, x); s->cy0 = imax(0, y); s->cx1 = imin(s->w, x + w); s->cy1 = imin(s->h, y + h);
}
static void s_unclip(surf *s) { s->cx0 = 0; s->cy0 = 0; s->cx1 = s->w; s->cy1 = s->h; }
static void s_px(surf *s, int32_t x, int32_t y, uint32_t c) {
  x += s->ox; y += s->oy;
  if (x < s->cx0 || y < s->cy0 || x >= s->cx1 || y >= s->cy1) return;
  s->px[y * s->stride + x] = s->pal[c];
}
static void s_rect(surf *s, int32_t x, int32_t y, int32_t w, int32_t h, uint32_t c) {
  int32_t x0, y0, x1, y1, xx, yy; uint32_t v = s->pal[c];
  x += s->ox; y += s->oy;
  x0 = x < s->cx0 ? s->cx0 : x; y0 = y < s->cy0 ? s->cy0 : y;
  x1 = x + w > s->cx1 ? s->cx1 : x + w; y1 = y + h > s->cy1 ? s->cy1 : y + h;
  for (yy = y0; yy < y1; yy++) { uint32_t *q = s->px + yy * s->stride + x0; for (xx = x0; xx < x1; xx++) *q++ = v; }
}
static void s_rrect(surf *s, int32_t x, int32_t y, int32_t w, int32_t h, int32_t r, uint32_t c) {
  int32_t j;
  if (r <= 0) { s_rect(s, x, y, w, h, c); return; }
  s_rect(s, x, y + r, w, h - 2 * r, c);
  for (j = 0; j < r; j++) {
    int32_t d = r - j, dx = 0, inset;
    while (dx < r && (dx + 1) * (dx + 1) + d * d - d <= r * r) dx++;
    inset = r - dx;
    s_rect(s, x + inset, y + j, w - 2 * inset, 1, c);
    s_rect(s, x + inset, y + h - 1 - j, w - 2 * inset, 1, c);
  }
}
static void s_disc(surf *s, int32_t cx, int32_t cy, int32_t r, uint32_t c) {
  int32_t dy;
  for (dy = -r; dy <= r; dy++) {
    int32_t dx = 0;
    while ((dx + 1) * (dx + 1) + dy * dy <= r * r + r) dx++;
    s_rect(s, cx - dx, cy + dy, 2 * dx + 1, 1, c);
  }
}
static void s_dither(surf *s, int32_t x, int32_t y, int32_t w, int32_t h, int32_t frac, uint32_t lo, uint32_t hi) {
  int32_t x0, y0, x1, y1, xx, yy;
  x += s->ox; y += s->oy;
  x0 = x < s->cx0 ? s->cx0 : x; y0 = y < s->cy0 ? s->cy0 : y;
  x1 = x + w > s->cx1 ? s->cx1 : x + w; y1 = y + h > s->cy1 ? s->cy1 : y + h;
  for (yy = y0; yy < y1; yy++) for (xx = x0; xx < x1; xx++)
    s->px[yy * s->stride + xx] = s->pal[ld_bayer[((yy & 3) << 2) | (xx & 3)] < frac ? hi : lo];
}
static void s_tri_br(surf *s, int32_t x, int32_t y, int32_t n, uint32_t c) {
  int32_t yy;
  for (yy = 0; yy < n; yy++) s_rect(s, x + n - 1 - yy, y + yy, yy + 1, 1, c);
}
static void s_glyph(surf *s, uint32_t code, int32_t x, int32_t y, int32_t scale, uint32_t c) {
  int32_t g, row, col, gx, gy;
  g = code < 256 ? ld_font_index[code] : -1;
  if (g < 0) return;
  gx = x + s->ox; gy = y + s->oy;
  if (gx >= s->cx1 || gx + 5 * scale <= s->cx0 || gy >= s->cy1 || gy + 7 * scale <= s->cy0) return;
  for (row = 0; row < 7; row++) {
    uint32_t bits = ld_font_data[g * 7 + row];
    for (col = 0; col < 5; col++) if (bits & (16u >> col)) s_rect(s, x + col * scale, y + row * scale, scale, scale, c);
  }
}
static void s_big(surf *s, uint32_t code, int32_t x, int32_t y, int32_t scale, uint32_t c) {
  int32_t row, col;
  for (row = 0; row < 11; row++) {
    uint32_t bits = ld_counter_data[code * 11 + row];
    for (col = 0; col < 7; col++) if (bits & (64u >> col)) s_rect(s, x + col * scale, y + row * scale, scale, scale, c);
  }
}
static int32_t text_w(const char *t, int32_t scale) { int32_t n = (int32_t)slen(t); return n ? n * 6 * scale - scale : 0; }
static void s_text(surf *s, const char *t, int32_t x, int32_t y, int32_t scale, uint32_t c) {
  int32_t i; for (i = 0; t[i]; i++) s_glyph(s, (uint8_t)t[i], x + i * 6 * scale, y, scale, c);
}
static int32_t num_digits(uint32_t n, int32_t pad) {
  int32_t digits = 1; uint32_t d = 10;
  while (n >= d && digits < 9) { digits++; d *= 10; }
  if (digits < pad) digits = pad;
  return digits;
}
static int32_t num_w(uint32_t n, int32_t scale, int32_t pad) { return num_digits(n, pad) * 6 * scale - scale; }
static int32_t s_num(surf *s, uint32_t n, int32_t x, int32_t y, int32_t scale, uint32_t c, int32_t pad) {
  int32_t digits = num_digits(n, pad), i; uint32_t div = 1;
  for (i = 1; i < digits; i++) div *= 10;
  for (i = 0; i < digits; i++) {
    s_glyph(s, 48u + div_u(n, div) % 10u, x + i * 6 * scale, y, scale, c);
    div = div_u(div, 10);
  }
  return digits * 6 * scale - scale;
}

/* ---------------------------------------------------------------- palette */
static uint32_t rgba(uint32_t r, uint32_t g, uint32_t b, uint32_t a) { return (a << 24) | (b << 16) | (g << 8) | r; }
static uint32_t c3(const uint8_t *c) { return rgba(c[0], c[1], c[2], 255); }
static int32_t mixc(int32_t a, int32_t b, int32_t k) { return a + (((b - a) * k) >> 8); }

static void fill_palette(uint32_t *pal, const ld_film *f, int32_t milk_lo, int32_t milk_hi) {
  const uint8_t *b = f->band; uint32_t i;
  for (i = 0; i < 32; i++) pal[i] = 0;
  pal[P_BLK] = rgba(14, 14, 14, 255); pal[P_GRY] = rgba(48, 48, 50, 255);
  pal[P_EDGE] = c3(f->edge); pal[P_WHT] = rgba(250, 248, 240, 255); pal[P_PAPER] = rgba(236, 230, 214, 255);
  pal[P_MID] = rgba(130, 130, 134, 255); pal[P_INK] = rgba(28, 26, 24, 255);
  pal[P_PANEL] = c3(f->panel); pal[P_BAND] = c3(f->band); pal[P_FINK] = c3(f->ink); pal[P_CINK] = c3(f->cink);
  pal[P_RED] = rgba(226, 40, 40, 255); pal[P_SHADE] = rgba(0, 0, 0, 120); pal[P_BAR] = rgba(6, 6, 6, 230);
  pal[P_MILK0] = rgba(238, 236, 228, (uint32_t)milk_lo); pal[P_MILK1] = rgba(238, 236, 228, (uint32_t)milk_hi);
  pal[P_HOLE] = rgba(255, 244, 214, 255); pal[P_DIG] = rgba(255, 255, 255, 255);
  pal[P_METL] = rgba(196, 198, 204, 255); pal[P_METD] = rgba(104, 106, 114, 255);
  pal[P_LEAD] = (f->kind == K_NEG || f->kind == K_CINE) ? rgba(128, 74, 36, 255) : rgba(78, 78, 80, 255);
  pal[P_BEZ] = rgba(176, 176, 182, 255); pal[P_MSH] = rgba(186, 180, 164, 255); pal[P_ISH] = rgba(212, 208, 196, 255);
  pal[P_TA] = rgba((uint32_t)mixc(214, b[0], 40), (uint32_t)mixc(208, b[1], 40), (uint32_t)mixc(196, b[2], 40), 255);
  pal[P_TB] = rgba((uint32_t)mixc(150, b[0], 50), (uint32_t)mixc(146, b[1], 50), (uint32_t)mixc(138, b[2], 50), 255);
  pal[P_TC] = rgba((uint32_t)mixc(84, f->panel[0], 50), (uint32_t)mixc(82, f->panel[1], 50), (uint32_t)mixc(80, f->panel[2], 50), 255);
  pal[P_UNX] = rgba(62, 62, 70, 255);
}

/* ---------------------------------------------------------------- timelines */
static int32_t slide_offset(int32_t t, int32_t in_end, int32_t out_a, int32_t out_b) {
  if (t < in_end) return (44 * (ONE - out_cubic(prog(t, 0, in_end)))) >> 10;
  if (t >= out_a) return (44 * in_cubic(prog(t, out_a, out_b))) >> 10;
  return 0;
}
static int32_t neg_advance(int32_t t, int last) {
  if (t < 260) return 0;
  if (t < 380) return -((24 * out_cubic(prog(t, 260, 380))) >> 10);
  if (last) {
    if (t < 480) return lerp(-24, 30, in_out(prog(t, 380, 480)));
    if (t < 640) return lerp(30, 0, out_cubic(prog(t, 480, 640)));
    return 0;
  }
  if (t < 940) return lerp(-24, 732, in_out(prog(t, 380, 940)));
  if (t < 1040) return lerp(732, LD_CELL, out_cubic(prog(t, 940, 1040)));
  return LD_CELL;
}
static int32_t cine_advance(int32_t t, int last) {
  int32_t k, within;
  if (t < 260) return 0;
  if (t < 380) return -((24 * out_cubic(prog(t, 260, 380))) >> 10);
  if (last) return neg_advance(t, 1);
  if (t >= 930) return LD_CELL;
  k = div_i(t - 380, 150); within = t - 380 - k * 150;
  return -24 + 186 * k + ((186 * in_out(prog(within, 0, 100))) >> 10);
}
static int32_t advance(int kind, int32_t t, int last) { return kind == K_CINE ? cine_advance(t, last) : neg_advance(t, last); }
static int32_t smear_for(int32_t v, int32_t pitch, int32_t cap) { return v > div_i(pitch, 3) ? (v > cap ? cap : v) : 0; }

static int32_t sheet_offset(int32_t t) {
  return t < 100 ? H : t < 460 ? lerp(H, 0, out_cubic(prog(t, 100, 460))) : lerp(0, H, in_cubic(prog(t, 2900, 3300)));
}
static int32_t load_cassette_x(int32_t t) { return lerp(-170, 6, out_back(prog(t, 100, 640))); }
static int32_t load_end(int32_t t, int32_t cx) { return lerp(cx + 140, 764, in_out(prog(t, 700, 1400))); }
static int32_t rewind_tip(int32_t t) { return t < 2300 ? 764 : lerp(764, 150, in_out(prog(t, 2300, 2700))); }
static int32_t rewind_cassette_x(int32_t t) {
  return t < 2700 ? 6 : t < 2780 ? 6 - ((8 * in_out(prog(t, 2700, 2780))) >> 10) : 6 - 8 + ((8 * out_cubic(prog(t, 2780, 2900))) >> 10);
}

/* ---------------------------------------------------------------- film strip pieces */
static void hole_row(surf *s, int32_t y, int32_t x0, int32_t pitch, int32_t scroll, int32_t hw, int32_t hh, int32_t r, int32_t smear, uint32_t colour) {
  int32_t m = mod_i(scroll, pitch), x;
  for (x = x0 - m - pitch; x < W; x += pitch) s_rrect(s, x, y, hw + smear, hh, r, colour);
}
static int32_t bars(surf *s, int32_t n, const ld_film *f, int32_t x, int32_t y, int32_t h, int32_t count, uint32_t film_index) {
  int32_t i;
  for (i = 0; i < count; i++) {
    int32_t w = 2 + (int32_t)(hash32(film_index * 4099u + (uint32_t)n, (uint32_t)i) % 3u);
    s_rect(s, x, y, w, h, P_EDGE);
    x += w + 2;
  }
  (void)f;
  return x;
}
static void print_cell(surf *s, int top, const ld_film *f, uint32_t fi, int32_t n, int32_t cx, int cine) {
  int32_t ty = top ? 3 : 27, x, w;
  if (!cine) {
    if (top) { s_text(s, f->label, cx + 16, ty, 2, P_EDGE); s_text(s, ">", cx + 16 + text_w(f->label, 2) + 20, ty, 2, P_EDGE); }
    else {
      s_num(s, (uint32_t)n, cx + 16, ty, 2, P_EDGE, 0);
      w = s_num(s, (uint32_t)n, cx + 360, ty, 2, P_EDGE, 0);
      s_text(s, "A", cx + 360 + w + 6, ty, 2, P_EDGE);
      s_text(s, f->code, cx + 560, ty, 2, P_EDGE);
    }
  } else if (top) {
    x = cx + 16;
    s_text(s, f->code, x, ty, 2, P_EDGE); x += text_w(f->code, 2) + 14;
    x += s_num(s, 1000u + hash32(fi, 7) % 9000u, x, ty, 2, P_EDGE, 0) + 14;
    x += s_num(s, (uint32_t)(n * 16 + 4), x, ty, 2, P_EDGE, 4) + 6;
    s_text(s, "+", x, ty, 2, P_EDGE); x += 14;
    x += s_num(s, (uint32_t)mod_i(n * 5, 16), x, ty, 2, P_EDGE, 2) + 16;
    bars(s, n, f, x, ty, 14, 16, fi);
  } else {
    w = s_num(s, (uint32_t)n, cx + 16, ty, 2, P_EDGE, 0);
    s_text(s, ">", cx + 16 + w + 12, ty, 2, P_EDGE);
    bars(s, n + 99, f, cx + 360, ty, 14, 22, fi);
    s_text(s, f->code, cx + 600, ty, 2, P_EDGE);
  }
}
static void draw_strip_band(surf *s, int top, const ld_film *f, uint32_t fi, int32_t frame, int32_t adv, int32_t vel) {
  int cine = f->kind == K_CINE;
  int32_t scroll = LD_CELL * LD_REST_CELL + adv, pitch = cine ? LD_CINE_PITCH : LD_PITCH;
  int32_t smear = smear_for(vel, pitch, cine ? 36 : 66), ghosts, step = 4, ci, g;
  s_rect(s, 0, 0, W, 44, P_BLK);
  s_rect(s, 0, top ? 42 : 0, W, 2, P_GRY);
  if (cine) s_rect(s, 0, top ? 39 : 3, W, 2, P_EDGE);
  if (cine) hole_row(s, top ? 20 : 8, 10, pitch, scroll, LD_CINE_HW, LD_CINE_HH, 3, smear, P_HOLE);
  else hole_row(s, top ? 19 : 5, LD_HOLE_X0, pitch, scroll, LD_HOLE_W, LD_HOLE_H, 6, smear, P_HOLE);
  ghosts = smear ? (smear >> 2) + 1 : 1;
  for (ci = div_i(scroll, LD_CELL); ci * LD_CELL - scroll < W; ci++) {
    int32_t cx = ci * LD_CELL - scroll, n = frame + ci - LD_REST_CELL;
    if (cx + LD_CELL < 0 || n < 1 || n > LD_ROLL_LENGTH) continue;
    for (g = 0; g < ghosts; g++) print_cell(s, top, f, fi, n, cx + g * step, cine);
  }
}
static void draw_mount_band(surf *s, int top, const ld_film *f, int32_t frame, uint32_t month, uint32_t year) {
  int32_t x, i;
  if (top) {
    s_rect(s, 0, 0, W, 30, P_PAPER);
    s_rect(s, 0, 0, W, 4, P_BAND);
    s_rect(s, 0, 28, W, 2, P_MSH);
    s_rect(s, 14, 30, W - 28, 3, P_SHADE);
    s_rect(s, 0, 30, 14, 14, P_PAPER); s_disc(s, 14, 44, 14, P_T);
    s_rect(s, W - 14, 30, 14, 14, P_PAPER); s_disc(s, W - 15, 44, 14, P_T);
    s_text(s, f->label, 24, 6, 3, P_INK);
    s_num(s, (uint32_t)frame, W - 24 - num_w((uint32_t)frame, 3, 0), 6, 3, P_RED, 0);
  } else {
    s_rect(s, 0, 14, W, 30, P_PAPER);
    s_rect(s, 0, 40, W, 4, P_BAND);
    s_rect(s, 0, 14, W, 2, P_MSH);
    s_rect(s, 14, 11, W - 28, 3, P_SHADE);
    s_rect(s, 0, 0, 14, 14, P_PAPER); s_disc(s, 14, 0, 14, P_T);
    s_rect(s, W - 14, 0, 14, 14, P_PAPER); s_disc(s, W - 15, 0, 14, P_T);
    x = 24 + s_num(s, (uint32_t)frame, 24, 17, 3, P_INK, 0) + 24;
    if (month < 12) { /* month 12 = no date stamp */
      for (i = 0; i < 3; i++) { s_glyph(s, (uint8_t)ld_months[month * 3 + (uint32_t)i], x, 17, 3, P_RED); x += 18; }
      s_num(s, year, x + 18, 17, 3, P_RED, 2);
    }
    s_text(s, f->caption, W - 24 - text_w(f->caption, 2), 20, 2, P_INK);
  }
}

/* ---------------------------------------------------------------- instant print */
typedef struct { int32_t lo, hi, frac; } milk_t;
static void milk_levels(milk_t *m, int32_t t) {
  int32_t a = (236 * (ONE - in_out(prog(t, 160, 1560)))) >> 10;
  m->lo = a & ~31; m->hi = m->lo + 32 > 255 ? 255 : m->lo + 32; m->frac = (a & 31) >> 1;
}
static void draw_instant_band(surf *s, int top) {
  if (top) { s_rect(s, 0, 0, W, 44, P_WHT); s_rect(s, 0, 42, W, 2, P_ISH); }
  else { s_rect(s, 0, 0, W, 44, P_WHT); s_rect(s, 0, 0, W, 2, P_ISH); s_text(s, "INSTANT", 24, 12, 3, P_INK); }
}
static void draw_instant_print(surf *s, int32_t py, int32_t frac) {
  s->oy = py;
  s_rect(s, 0, 0, W, 44, P_WHT); s_rect(s, 0, 380, W, 100, P_WHT);
  s_rect(s, 0, 0, 22, H, P_WHT); s_rect(s, W - 22, 0, 22, H, P_WHT);
  s_rect(s, 22, 44, W - 44, 2, P_ISH); s_rect(s, 22, 378, W - 44, 2, P_ISH);
  s_rect(s, 22, 44, 2, 336, P_ISH); s_rect(s, W - 24, 44, 2, 336, P_ISH);
  s_text(s, "INSTANT", 40, 412, 3, P_INK);
  s_dither(s, 24, 46, W - 48, 332, frac, P_MILK0, P_MILK1);
  s->oy = 0;
}

/* ---------------------------------------------------------------- cassettes and leader */
static void mini_cassette(surf *s, int32_t x, const ld_film *f) {
  s_rect(s, x, 14, 10, 14, P_METD); s_rect(s, x, 14, 10, 3, P_METL);
  s_rect(s, x + 10, 2, 8, 40, P_METL); s_rect(s, x + 17, 2, 1, 40, P_METD);
  s_rect(s, x + 18, 2, 110, 40, P_PANEL);
  s_rect(s, x + 18, 2, 110, 18, P_BAND);
  s_text(s, f->caption, x + 18 + ((110 - text_w(f->caption, 2)) >> 1), 4, 2, P_CINK);
  s_text(s, f->code, x + 18 + ((110 - text_w(f->code, 2)) >> 1), 25, 2, P_FINK);
  s_rect(s, x + 18, 40, 110, 2, P_BLK);
  s_rect(s, x + 128, 2, 8, 40, P_METL); s_rect(s, x + 128, 2, 1, 40, P_METD);
  s_rect(s, x + 136, 6, 10, 32, P_METD);
  s_rect(s, x + 142, 18, 4, 8, P_BLK);
}
static void big_cassette(surf *s, int32_t cx, int32_t ty, const ld_film *f) {
  int32_t sc = slen(f->code) > 3 ? 4 : 5;
  s_rect(s, cx - 12, ty, 24, 14, P_METD); s_rect(s, cx - 8, ty, 16, 4, P_METL);
  s_rrect(s, cx - 62, ty + 12, 124, 18, 6, P_METL); s_rect(s, cx - 62, ty + 26, 124, 4, P_METD);
  s_rect(s, cx - 58, ty + 30, 116, 100, P_BLK);
  s_rect(s, cx - 56, ty + 30, 112, 100, P_PANEL);
  s_rect(s, cx - 56, ty + 30, 112, 26, P_BAND);
  s_text(s, f->caption, cx - (text_w(f->caption, 2) >> 1), ty + 36, 2, P_CINK);
  s_text(s, f->code, cx - (text_w(f->code, sc) >> 1), ty + 66, sc, P_FINK);
  s_rect(s, cx - 56, ty + 112, 112, 4, P_FINK);
  s_rrect(s, cx - 62, ty + 128, 124, 18, 6, P_METD); s_rect(s, cx - 62, ty + 128, 124, 4, P_BLK);
  s_rect(s, cx + 56, ty + 62, 10, 36, P_METD); s_rect(s, cx + 62, ty + 72, 4, 16, P_BLK);
}
static void draw_big_leader(surf *s, const ld_film *f, int32_t start_x, int32_t end_x, int32_t smear) {
  int32_t r, x;
  for (r = 0; r < 98; r++) {
    int32_t d = r < 49 ? r : 97 - r, c = d < 28 ? (28 - d) * 2 : 0;
    if (end_x - c > start_x) s_rect(s, start_x, r, end_x - c - start_x, 1, P_LEAD);
  }
  for (x = end_x - 84; x > start_x + 8; x -= LD_PITCH) { s_rrect(s, x, 8, LD_HOLE_W + smear, 22, 6, P_HOLE); s_rrect(s, x, 68, LD_HOLE_W + smear, 22, 6, P_HOLE); }
  if (end_x - 420 > start_x + 8) s_text(s, f->label, end_x - 420, 39, 3, P_EDGE);
}
static void draw_leader(surf *s, const ld_film *f, int32_t start_x, int32_t end_x, int32_t smear, int label) {
  int32_t r, x;
  for (r = 0; r < 42; r++) {
    int32_t c = r < 10 ? (10 - r) * 3 : r > 31 ? (r - 31) * 3 : 0;
    if (end_x - c > start_x) s_rect(s, start_x, 1 + r, end_x - c - start_x, 1, P_LEAD);
  }
  for (x = end_x - 84; x > start_x + 8; x -= LD_PITCH) s_rrect(s, x, 5, LD_HOLE_W + smear, LD_HOLE_H, 6, P_HOLE);
  if (label && end_x - 520 > start_x + 8) s_text(s, f->label, end_x - 520, 27, 2, P_EDGE);
}

/* ---------------------------------------------------------------- counter and tab */
typedef struct { int32_t a, b, p, dir, linear; } counter_state;
static int32_t tens_code(int32_t v) { return (v == 255 || v < 10) ? 10 : div_i(v, 10); }
static int32_t ones_code(int32_t v) { return v == 255 ? 11 : mod_i(v, 10); }
static void draw_wheel(surf *s, int32_t wx, int32_t ca, int32_t cb, int32_t e, int32_t dir) {
  int32_t base = 7, off;
  s_clip(s, wx, 4, 30, 40);
  s_rect(s, wx, 4, 30, 40, P_BLK);
  if (ca == cb || e == 0) s_big(s, (uint32_t)ca, wx + 4, base, 3, P_DIG);
  else {
    off = (46 * e) >> 10;
    if (dir > 0) { s_big(s, (uint32_t)ca, wx + 4, base - off, 3, P_DIG); s_big(s, (uint32_t)cb, wx + 4, base + 46 - off, 3, P_DIG); }
    else { s_big(s, (uint32_t)ca, wx + 4, base + off, 3, P_DIG); s_big(s, (uint32_t)cb, wx + 4, base - 46 + off, 3, P_DIG); }
  }
  s_rect(s, wx, 4, 30, 3, P_SHADE); s_rect(s, wx, 41, 30, 3, P_SHADE);
  s_unclip(s);
}
static void draw_counter(surf *s, const counter_state *c) {
  int32_t e = c->linear ? c->p : in_out(c->p);
  s_rrect(s, 0, 0, 84, 48, 6, P_BEZ);
  s_rrect(s, 2, 2, 80, 44, 5, P_BLK);
  draw_wheel(s, 9, tens_code(c->a), tens_code(c->b), e, c->dir);
  draw_wheel(s, 45, ones_code(c->a), ones_code(c->b), e, c->dir);
}
static void draw_tab(surf *s, const ld_film *f) {
  s_rect(s, 0, 6, 10, 44, P_METD);
  s_disc(s, 5, 14, 2, P_METL); s_disc(s, 5, 42, 2, P_METL);
  s_rrect(s, 8, 2, 120, 52, 8, P_BLK);
  s_rrect(s, 10, 4, 116, 48, 6, P_PANEL);
  s_rrect(s, 10, 4, 116, 19, 6, P_BAND); s_rect(s, 10, 14, 116, 9, P_BAND);
  s_text(s, f->caption, 68 - (text_w(f->caption, 2) >> 1), 6, 2, P_CINK);
  s_text(s, f->code, 68 - (text_w(f->code, 4) >> 1), 24, 4, P_FINK);
  s_tri_br(s, 108, 34, 14, P_PAPER); s_tri_br(s, 108, 34, 3, P_GRY);
}

/* ---------------------------------------------------------------- contact sheet */
static void frame_xy(int32_t i, int32_t *out) {
  int32_t r = div_i(i, 9), c = i - r * 9;
  out[0] = LD_SHEET_FX0 + c * (LD_SHEET_FW + LD_SHEET_FGAP);
  out[1] = LD_SHEET_STRIPY0 + r * (LD_SHEET_STRIPH + LD_SHEET_STRIPGAP) + 14;
}
static int32_t pseudo_angle(int32_t dx, int32_t dy) {
  int32_t ax = dx < 0 ? -dx : dx, ay = dy < 0 ? -dy : dy, sum = ax + ay;
  if (sum == 0) return 0;
  if (dx >= 0 && dy < 0) return (int32_t)div_u((uint32_t)ax * 1024u, (uint32_t)sum);
  if (dx >= 0) return 1024 + (int32_t)div_u((uint32_t)ay * 1024u, (uint32_t)sum);
  if (dy >= 0) return 2048 + (int32_t)div_u((uint32_t)ax * 1024u, (uint32_t)sum);
  return 3072 + (int32_t)div_u((uint32_t)ay * 1024u, (uint32_t)sum);
}
static void grease_pencil(surf *s, int32_t cx, int32_t cy, uint32_t roll, int32_t pcur) {
  int32_t rx = 48, ry = 34, x, y;
  for (y = cy - ry - 10; y <= cy + ry + 10; y++) for (x = cx - rx - 10; x <= cx + rx + 10; x++) {
    int32_t dx = x - cx, dy = y - cy, pa, wob, pass;
    /* quick reject: outside the largest possible ring or inside the smallest cannot be a ring pixel (same output as JS) */
    if (dx * dx * 42 * 42 + dy * dy * 56 * 56 > 56 * 56 * 42 * 42) continue;
    if (dx * dx * 31 * 31 + dy * dy * 45 * 45 <= 45 * 45 * 31 * 31) continue;
    pa = pseudo_angle(dx, dy);
    wob = (int32_t)(hash32(roll, (uint32_t)(pa >> 7)) & 3u) - 1;
    for (pass = 0; pass < 2; pass++) {
      int32_t ex, ox, oy, ix, iy;
      if (pass == 0 ? pa > pcur : (pcur < 4096 || pa > pcur - 4096)) continue;
      ex = pass * 4 + wob; ox = rx + ex + 2; oy = ry + ex + 2; ix = rx + ex - 2; iy = ry + ex - 2;
      if (dx * dx * oy * oy + dy * dy * ox * ox <= ox * ox * oy * oy &&
          dx * dx * iy * iy + dy * dy * ix * ix > ix * ix * iy * iy) { s_px(s, x, y, P_RED); break; }
    }
  }
}
static void draw_sheet(surf *s, uint32_t roll, int32_t t, int32_t sheet_off, int32_t circled, uint8_t *filled) {
  int32_t r, i, xy[2];
  s->oy = sheet_off;
  s_rect(s, 0, 44, W, 392, P_PAPER);
  for (r = 0; r < 4; r++) {
    int32_t sy = LD_SHEET_STRIPY0 + r * (LD_SHEET_STRIPH + LD_SHEET_STRIPGAP), x;
    s_rrect(s, LD_SHEET_STRIPX, sy, LD_SHEET_STRIPW, LD_SHEET_STRIPH, 4, P_BLK);
    for (x = LD_SHEET_STRIPX + 6; x < LD_SHEET_STRIPX + LD_SHEET_STRIPW - 12; x += 16) { s_rect(s, x, sy + 3, 8, 6, P_PAPER); s_rect(s, x, sy + 61, 8, 6, P_PAPER); }
  }
  for (i = 0; i < 36; i++) {
    int32_t tf, x, y, hz;
    frame_xy(i, xy);
    tf = 480 + i * 22; x = xy[0]; y = xy[1];
    filled[i] = t < tf ? 0 : t < tf + 70 ? 1 : 2;
    if (filled[i] == 0) { s_rect(s, x, y, LD_SHEET_FW, LD_SHEET_FH, P_UNX); continue; }
    if (filled[i] == 1) { s_rect(s, x, y, LD_SHEET_FW, LD_SHEET_FH, P_WHT); continue; }
    hz = 14 + (int32_t)(hash32(roll * 64u + (uint32_t)i, 3) % 14u);
    s_rect(s, x, y, LD_SHEET_FW, hz, P_TA); s_rect(s, x, y + hz, LD_SHEET_FW, LD_SHEET_FH - hz, P_TB);
    s_rect(s, x, y + LD_SHEET_FH - 9 - (int32_t)(hash32((uint32_t)i, roll) % 5u), LD_SHEET_FW, 14, P_TC);
    s_num(s, (uint32_t)(i + 1), x + ((LD_SHEET_FW - num_w((uint32_t)(i + 1), 2, 0)) >> 1), y + 14, 2, P_INK, 0);
  }
  if (t >= 1500) {
    frame_xy(circled, xy);
    grease_pencil(s, xy[0] + (LD_SHEET_FW >> 1), xy[1] + (LD_SHEET_FH >> 1), roll, (4600 * in_out(prog(t, 1500, 2000))) >> 10);
  }
  s->oy = 0;
}

/* ---------------------------------------------------------------- per-frame preparation */
typedef struct {
  const ld_film *film; uint32_t fi, moment, tier;
  int active, last, kind;
  int32_t t, dur, off, ox, adv, vel, py, ej, hide_counter, hide_tab;
  counter_state cs; milk_t milk;
} prep_t;

uint32_t loaded_duration(uint32_t film, uint32_t moment) {
  if (film >= LD_FILMS) return 0;
  if (moment == LOADED_SHOT) {
    switch (ld_films[film].kind) {
      case K_NEG: return LD_SHOT_NEG; case K_BW: return LD_SHOT_BW; case K_CINE: return LD_SHOT_CINE;
      case K_SLIDE: return LD_SHOT_SLIDE; default: return LD_SHOT_INSTANT;
    }
  }
  if (moment == LOADED_LOAD) return LD_LOAD_MS;
  if (moment == LOADED_ROLL) return LD_ROLL_MS;
  return 0;
}

static void counter_prepare(prep_t *q, uint32_t frame) {
  counter_state *c = &q->cs;
  int32_t t = q->t;
  c->a = c->b = (int32_t)frame; c->p = 0; c->dir = 1; c->linear = 0;
  if (q->moment == LOADED_SHOT) {
    c->b = frame >= RLEN ? (int32_t)frame : (int32_t)frame + 1;
    c->p = frame >= RLEN ? 0 : prog(t, ld_roll_win[q->kind][0], ld_roll_win[q->kind][1]);
  } else if (q->moment == LOADED_LOAD) {
    c->a = 255; c->b = (int32_t)frame; c->p = prog(t, LD_LOAD_ROLL_A, LD_LOAD_ROLL_B);
  } else if (q->moment == LOADED_ROLL) {
    int32_t pos = RLEN * ONE - ((RLEN - 1) * in_out(prog(t, LD_REWIND_A, LD_REWIND_B)));
    int32_t n = pos >> 10, frac = pos & 1023;
    c->dir = -1; c->linear = 1;
    if (frac == 0) { c->a = c->b = n; c->p = 0; } else { c->a = n + 1; c->b = n; c->p = ONE - frac; }
  }
  if (c->p >= ONE) { c->a = c->b; c->p = 0; }
}
static int32_t hide_amount(uint32_t mode, int32_t t, int active, int32_t peek, uint32_t held) {
  int32_t pe = peek;
  if (mode != LOADED_PEEK) return 0;
  if (pe < 0 && active) pe = t + (held ? 180 : 0);
  if (pe < 0) return ONE;
  if (active && pe >= 180) return 0;
  if (pe < 180) return ONE - out_cubic(prog(pe, 0, 180));
  if (pe < LD_PEEK_MS - 240) return 0;
  if (pe < LD_PEEK_MS) return in_cubic(prog(pe, LD_PEEK_MS - 240, LD_PEEK_MS));
  return ONE;
}
static int32_t tab_aside(uint32_t moment, int kind, uint32_t tier, int32_t t, int32_t dur, int active) {
  int32_t back;
  if (!active) return 0;
  if (moment == LOADED_LOAD) {
    if (t < 180) return out_cubic(prog(t, 0, 180));
    if (t < 1950) return ONE;
    return ONE - out_cubic(prog(t, 1950, dur));
  }
  if (tier != 2) return 0;
  if (moment == LOADED_SHOT && kind != K_SLIDE && kind != K_INSTANT) return 0;
  if (t < 180) return out_cubic(prog(t, 0, 180));
  back = (kind == K_INSTANT && moment == LOADED_SHOT) ? 110 : 240;
  if (t >= dur - back) return ONE - out_cubic(prog(t, dur - back, dur));
  return ONE;
}

static void prepare(prep_t *q, const loaded_params *p, int32_t elapsed) {
  const ld_film *f = &ld_films[p->film];
  uint32_t moment = p->moment;
  int32_t t, pk, tab_pk, cnt_pk; uint32_t cnt_mode;
  q->film = f; q->fi = p->film; q->moment = moment; q->tier = p->tier;
  q->kind = f->kind; q->dur = (int32_t)loaded_duration(p->film, moment);
  q->active = (moment == LOADED_SHOT || moment == LOADED_LOAD || moment == LOADED_ROLL) && elapsed >= 0 && elapsed < q->dur;
  t = elapsed < 0 ? 0 : elapsed; q->t = t;
  q->last = p->frame >= RLEN;
  q->milk.lo = 0; q->milk.hi = 0; q->milk.frac = 0;
  if (q->active && moment == LOADED_SHOT && q->kind == K_INSTANT) milk_levels(&q->milk, t);
  q->off = q->ox = q->adv = q->vel = q->py = q->ej = 0;
  if (q->active) {
    if (moment == LOADED_SHOT) {
      if (q->kind == K_NEG || q->kind == K_BW || q->kind == K_CINE) {
        q->off = slide_offset(t, 260, 1200, 1500); q->adv = advance(q->kind, t, q->last);
        q->vel = q->adv - advance(q->kind, t > 33 ? t - 33 : 0, q->last);
      } else if (q->kind == K_SLIDE) {
        q->off = t < 230 ? (44 * (ONE - out_bounce(prog(t, 0, 230)))) >> 10 : 0;
        q->ox = lerp(0, W, in_cubic(prog(t, 900, 1250)));
      } else {
        q->off = t < 240 ? (44 * (ONE - out_cubic(prog(t, 0, 240)))) >> 10 : 0;
        q->py = t < 1560 ? lerp(H, 0, out_cubic(prog(t, 0, 260))) : -lerp(0, H, in_cubic(prog(t, 1560, 1800)));
        q->ej = t < 1560 ? 0 : lerp(0, H, in_cubic(prog(t, 1560, 1800)));
      }
    } else if (moment == LOADED_LOAD) q->off = slide_offset(t, 220, 1950, 2200);
    else q->off = slide_offset(t, 300, 3000, 3400);
  }
  counter_prepare(q, p->frame);
  pk = p->peek_ms;
  tab_pk = p->tab_peek_ms == -2 ? pk : p->tab_peek_ms;
  cnt_pk = p->counter_peek_ms == -2 ? pk : p->counter_peek_ms;
  cnt_mode = p->counter_mode == LOADED_INHERIT ? p->tab_mode : p->counter_mode;
  q->hide_counter = hide_amount(cnt_mode, t, q->active, cnt_pk, p->hold);
  q->hide_tab = imax(hide_amount(p->tab_mode, t, q->active, tab_pk, p->hold), tab_aside(moment, q->kind, p->tier, t, q->dur, q->active));
}

/* ---------------------------------------------------------------- band and full-view drawing */
static void chip(surf *s, const ld_film *f) {
  char tmp[4]; uint32_t n = slen(f->code), i;
  if (n > 3) n = 3;
  for (i = 0; i < n; i++) tmp[i] = f->code[i];
  tmp[n] = 0;
  s_rrect(s, 14, 8, 46, 28, 4, P_PANEL); s_rect(s, 14, 26, 46, 10, P_BAND);
  s_text(s, tmp, 14 + ((46 - text_w(tmp, 2)) >> 1), 11, 2, P_FINK);
}
static void draw_load_band(surf *s, int top, const ld_film *f, int32_t t, uint32_t tier) {
  s_rect(s, 0, 0, W, 44, P_BLK);
  s_rect(s, 0, top ? 42 : 0, W, 2, P_GRY);
  if (top) {
    int32_t full = (int32_t)slen(f->label), shown = div_i(t - 600, 26), x = tier == 1 ? 76 : 24, i;
    static const char loaded_word[] = "LOADED";
    if (tier == 1) chip(s, f);
    for (i = 0; i < full + 7 && i < shown; i++) {
      if (i < full) s_glyph(s, (uint8_t)f->label[i], x, 11, 3, P_WHT);
      else if (i > full) s_glyph(s, (uint8_t)loaded_word[i - full - 1], x, 11, 3, P_EDGE);
      x += 18;
    }
    return;
  }
  {
    int32_t cx = load_cassette_x(t), end_x = load_end(t, cx);
    int32_t sm = t < 700 ? 0 : smear_for(end_x - load_end(t - 33 > 0 ? t - 33 : 0, cx), LD_PITCH, 60);
    if (t >= 700) draw_leader(s, f, cx + 140, end_x, sm, 1);
    mini_cassette(s, cx, f);
  }
}
static void draw_roll_band(surf *s, int top, const ld_film *f, uint32_t roll, int32_t t) {
  int32_t cx, tip, n, r, g, i;
  int racing;
  s_rect(s, 0, 0, W, 44, P_BLK);
  s_rect(s, 0, top ? 42 : 0, W, 2, P_GRY);
  if (top) {
    chip(s, f);
    if (t < 1000) {
      int32_t x = 76; s_text(s, "ROLL", x, 11, 3, P_EDGE); x += 5 * 18;
      x += s_num(s, roll, x, 11, 3, P_EDGE, 0) + 36;
      s_text(s, f->label, x, 11, 3, P_WHT);
    } else if (t < 1800) {
      int32_t w = s_num(s, RLEN, 76, 11, 3, P_EDGE, 0);
      s_text(s, "FRAMES EXPOSED.", 76 + w + 18, 11, 3, P_WHT);
    } else if (t < 2700) s_text(s, "REWINDING.", 76, 11, 3, P_WHT);
    else s_text(s, "FILM REWOUND.", 76, 11, 3, P_EDGE);
    return;
  }
  cx = rewind_cassette_x(t); tip = rewind_tip(t); racing = t >= LD_REWIND_A && t < 2700;
  n = RLEN - (((RLEN - 1) * in_out(prog(t, LD_REWIND_A, LD_REWIND_B))) >> 10);
  if (tip > cx + 140) {
    for (r = 0; r < 42; r++) {
      int32_t c = r < 10 ? (10 - r) * 3 : r > 31 ? (r - 31) * 3 : 0;
      s_rect(s, cx + 140, 1 + r, tip - c - cx - 140, 1, P_LEAD);
    }
    if (racing) {
      int32_t sh = mod_i(div_i(t * 28, 33), LD_PITCH), x;
      s_rrect(s, cx + 146, 3, tip - cx - 150, 16, 6, P_HOLE);
      for (x = cx + 146 - sh; x < tip; x += LD_PITCH) s_rect(s, x, 3, 16, 16, P_LEAD);
    } else if (t < LD_REWIND_A) hole_row(s, 3, LD_HOLE_X0 + 160, LD_PITCH, 0, LD_HOLE_W, 17, 6, 0, P_HOLE);
    for (g = 0; g < 3; g++) { int32_t x = 200 + g * 190; if (x + 40 < tip) s_num(s, (uint32_t)n, x, 21, 3, P_EDGE, 0); }
    if (racing) {
      s_clip(s, cx + 140, 0, tip - cx - 140, 44);
      for (i = 0; i < 6; i++)
        s_rect(s, 190 + (int32_t)(hash32((uint32_t)i, (uint32_t)div_i(t, 66)) % 480u), 24 + mod_i(i, 3) * 7,
               30 + (int32_t)(hash32((uint32_t)i, 9) % 60u), 2, P_EDGE);
      s_unclip(s);
    }
  }
  mini_cassette(s, cx, f);
}
static void draw_full(loaded *L, surf *s, const prep_t *q, const loaded_params *p) {
  const ld_film *f = q->film; int32_t t = q->t;
  if (q->moment == LOADED_SHOT) {
    if (q->kind == K_NEG || q->kind == K_BW || q->kind == K_CINE) {
      int32_t gw = q->kind == K_CINE ? 32 : 40, w, x;
      s_clip(s, 0, 44, W, 392);
      w = t < 1000 ? gw : (gw * (ONE - in_cubic(prog(t, 1000, 1100)))) >> 10;
      x = LD_CELL - q->adv;
      if (w > 0 && x < W && t >= 260) { s_rect(s, x - 2, 44, w + 4, 392, P_GRY); s_rect(s, x, 44, w, 392, P_BAR); }
      s_unclip(s);
    } else if (q->kind == K_SLIDE) {
      s_clip(s, 0, 44, W, 392);
      s_rect(s, q->ox, 0, 8, H, P_PAPER); s_rect(s, q->ox + 8, 0, 2, H, P_MSH);
      s_rect(s, W - 8 + q->ox, 0, 8, H, P_PAPER); s_rect(s, W - 10 + q->ox, 0, 2, H, P_MSH);
      s_unclip(s);
    } else draw_instant_print(s, q->py, q->milk.frac);
  } else if (q->moment == LOADED_LOAD) {
    int32_t ty = t < 700 ? lerp(-190, 130, out_bounce(prog(t, 0, 700))) : 130;
    s_clip(s, 0, 44, W, 392);
    s->ox = -lerp(0, 1000, in_cubic(prog(t, 1900, 2200)));
    if (t < 700) s_rrect(s, 88, 280, 124, 10, 5, P_SHADE);
    if (t >= 700) {
      int32_t end_x = lerp(212, 764, in_out(prog(t, 800, 1500)));
      int32_t sm = t < 800 ? 0 : smear_for(end_x - lerp(212, 764, in_out(prog(t - 33 > 800 ? t - 33 : 800, 800, 1500))), LD_PITCH, 60);
      s->oy = 130 + 31;
      draw_big_leader(s, f, 212, end_x, sm);
      s->oy = 0;
    }
    big_cassette(s, 150, ty, f);
    s->ox = 0; s_unclip(s);
  } else if (q->moment == LOADED_ROLL) {
    int32_t circled = p->circled < 0 ? (int32_t)(hash32(p->roll, 5) % 36u) : p->circled;
    s_clip(s, 0, 44, W, 392);
    draw_sheet(s, p->roll, t, sheet_offset(t), circled, L->filled);
    s_unclip(s);
  }
}
static void blit_thumbs(loaded *L, surf *s, const uint32_t *thumbs, int32_t t) {
  int32_t so = sheet_offset(t), i, r, c, xy[2];
  for (i = 0; i < 36; i++) {
    if (L->filled[i] != 2) continue;
    frame_xy(i, xy);
    for (r = 0; r < LD_SHEET_FH; r++) {
      int32_t yy = xy[1] + r + so;
      if (yy < 44 || yy >= 436) continue;
      for (c = 0; c < LD_SHEET_FW; c++) s->px[yy * s->stride + xy[0] + c] = thumbs[(uint32_t)i * LD_SHEET_FW * LD_SHEET_FH + (uint32_t)(r * LD_SHEET_FW + c)];
    }
  }
}

/* ---------------------------------------------------------------- validation and clearing */
static int buf_ok(const loaded_buffers *b, uint32_t v) {
  uint32_t w = loaded_view_rect[v][2], h = loaded_view_rect[v][3];
  if (!b->pixels[v] || ((uintptr_t)b->pixels[v] & 3u)) return 0;
  if (b->stride[v] < w || b->stride[v] > 4096u) return 0;
  return b->capacity[v] >= b->stride[v] * h;
}
static void clear_view(const loaded_buffers *b, uint32_t v) {
  uint32_t n, i, w = loaded_view_rect[v][2], h = loaded_view_rect[v][3], x, y;
  if (!b->pixels[v] || ((uintptr_t)b->pixels[v] & 3u) || b->stride[v] < w || b->stride[v] > 4096u) return;
  n = b->capacity[v];
  for (y = 0; y < h; y++) for (x = 0; x < w; x++) {
    i = y * b->stride[v] + x;
    if (i < n) b->pixels[v][i] = 0;
  }
}
static void clear_all(loaded *L, const loaded_buffers *b) {
  uint32_t v;
  if (b) for (v = 0; v < LOADED_VIEWS; v++) clear_view(b, v);
  if (L) { L->dirty = 0; L->sig_valid = 0; L->changed = (1u << LOADED_VIEWS) - 1u; }
}
static int params_ok(const loaded_params *p, int need_moment) {
  if (!p) return 0;
  if (need_moment && p->moment > LOADED_NONE) return 0;
  if (p->film >= LD_FILMS || p->frame < 1 || p->frame > LD_ROLL_LENGTH || p->roll > 999999u) return 0;
  if (p->tier != 1 && p->tier != 2) return 0;
  if (p->tab_mode > LOADED_PEEK || p->counter_mode > LOADED_INHERIT) return 0;
  if (p->month > 12 || p->year > 99) return 0;
  if (p->circled < -1 || p->circled > 35 || p->hold > 1) return 0;
  return 1;
}
static int bufs_ok(const loaded_buffers *b, uint32_t tier) {
  uint32_t v;
  if (!b) return 0;
  for (v = 1; v < LOADED_VIEWS; v++) if (!buf_ok(b, v)) return 0;
  if (tier == 2 && !buf_ok(b, LOADED_V_FULL)) return 0;
  return 1;
}

/* ---------------------------------------------------------------- render core */
static void render_core(loaded *L, const loaded_buffers *b, const loaded_params *p, const prep_t *q, uint32_t mask) {
  uint32_t v; const ld_film *f = q->film; uint32_t changed = 0;
  surf s;
  fill_palette(L->pal, f, q->milk.lo, q->milk.hi);
  for (v = 0; v < LOADED_VIEWS; v++) {
    int drawn = 0; int is_furniture = v == LOADED_V_COUNTER || v == LOADED_V_TAB;
    if (!(mask & (1u << v))) continue;
    if (v == LOADED_V_FULL && q->tier < 2) drawn = 0;
    else if (is_furniture) {
      int32_t h = v == LOADED_V_TAB ? q->hide_tab : q->hide_counter;
      drawn = h < ONE;
      if (drawn) {
        s_init(&s, b->pixels[v], b->stride[v], loaded_view_rect[v][2], loaded_view_rect[v][3], L->pal);
        s_clear(&s);
        if (v == LOADED_V_COUNTER) { s.ox = (108 * h) >> 10; draw_counter(&s, &q->cs); }
        else { s.ox = -((132 * h) >> 10); draw_tab(&s, f); }
      }
    } else if (q->active) {
      int top = v == LOADED_V_TOP;
      drawn = 1;
      if (v != LOADED_V_FULL) {
        if (q->moment == LOADED_SHOT && q->kind == K_INSTANT && q->tier == 2) drawn = 0;
        if (q->moment == LOADED_LOAD && q->tier == 2 && !top) drawn = 0;
      }
      if (drawn) {
        s_init(&s, b->pixels[v], b->stride[v], loaded_view_rect[v][2], loaded_view_rect[v][3], L->pal);
        s_clear(&s);
        if (v == LOADED_V_FULL) {
          draw_full(L, &s, q, p);
          if (q->moment == LOADED_ROLL && p->thumbs) blit_thumbs(L, &s, p->thumbs, q->t);
        } else {
          s.oy = (top ? -q->off : q->off) - q->ej; s.ox = q->ox;
          if (q->moment == LOADED_SHOT) {
            if (q->kind == K_SLIDE) draw_mount_band(&s, top, f, (int32_t)p->frame, p->month, p->year);
            else if (q->kind == K_INSTANT) draw_instant_band(&s, top);
            else draw_strip_band(&s, top, f, q->fi, (int32_t)p->frame, q->adv, q->vel);
          } else if (q->moment == LOADED_LOAD) draw_load_band(&s, top, f, q->t, q->tier);
          else draw_roll_band(&s, top, f, p->roll, q->t);
        }
      }
    }
    if (drawn) { L->dirty |= 1u << v; changed |= 1u << v; }
    else if (L->dirty & (1u << v)) { clear_view(b, v); L->dirty &= ~(1u << v); changed |= 1u << v; }
  }
  L->changed = changed;
}

void loaded_init(loaded *L) {
  uint32_t i; uint32_t *w = (uint32_t *)L;
  if (!L) return;
  for (i = 0; i < sizeof(*L) / 4u; i++) w[i] = 0;
  L->magic = 0x4c4f4144u; L->dirty = (1u << LOADED_VIEWS) - 1u; L->canary = 0xc0ffee01u;
  L->p.tier = 1; L->p.film = 0; L->p.frame = 1; L->p.peek_ms = -1; L->p.tab_peek_ms = -2; L->p.counter_peek_ms = -2;
  L->p.counter_mode = LOADED_INHERIT; L->p.month = LD_DEFAULT_MONTH; L->p.year = LD_DEFAULT_YEAR; L->p.circled = -1; L->p.hold = 0;
}

int loaded_render(loaded *L, const loaded_buffers *b, const loaded_params *p, int32_t elapsed) {
  prep_t q;
  if (!L || !params_ok(p, 1) || !bufs_ok(b, p->tier)) { clear_all(L, b); return -1; }
  prepare(&q, p, elapsed);
  render_core(L, b, p, &q, (1u << LOADED_VIEWS) - 1u);
  return 0;
}

int loaded_set(loaded *L, const loaded_params *p) {
  if (!L || !params_ok(p, 0)) return -1;
  L->p = *p; L->p.moment = LOADED_LIVE; L->sig_valid = 0; L->linger = 0;
  return 0;
}
int loaded_start(loaded *L, const loaded_params *p, uint32_t now) {
  if (!L || !params_ok(p, 1) || p->moment < LOADED_SHOT || p->moment > LOADED_ROLL) return -1;
  L->p = *p; L->moment = p->moment; L->p.moment = p->moment; L->start = now; L->active = 1; L->linger = 0;
  return 0;
}
void loaded_peek(loaded *L, uint32_t now) { if (L) { L->peek_start = now; L->peek_valid = 1; } }
void loaded_cancel(loaded *L) { if (L) { L->active = 0; L->moment = LOADED_NONE; L->linger = 0; L->peek_valid = 0; } }

static uint32_t sig_of(uint32_t a, uint32_t b2, uint32_t c, uint32_t d) { return hash32(hash32(a, b2), hash32(c, d)); }

int loaded_tick(loaded *L, const loaded_buffers *b, uint32_t now) {
  loaded_params lp; prep_t q; uint32_t mask, elapsed = 0; int32_t pe = -1;
  if (!L || L->magic != 0x4c4f4144u || !params_ok(&L->p, 0) || !bufs_ok(b, L->p.tier)) { clear_all(L, b); return -1; }
  lp = L->p;
  if (L->active) {
    elapsed = now - L->start;                       /* unsigned: survives a wrapping 32-bit clock */
    if (elapsed >= loaded_duration(lp.film, L->moment)) {
      /* the moment is over: the tab and counter keep their peek window; the counter shows the new number */
      L->linger_frame = L->moment == LOADED_ROLL ? 1u : (L->p.frame < RLEN ? L->p.frame + 1u : L->p.frame);
      L->linger = 1; L->active = 0;
      { /* the linger is the last 500 ms of a 2000 ms peek window. A roll runs 3400 ms, so it gets its own 500 ms; a shot
         * that is found over only after its whole window (a stalled UI) gets none: nothing outlives 2.0 s. */
        uint32_t pe_end = L->peek_valid ? now - L->peek_start : 0xffffffffu;
        if (L->moment == LOADED_ROLL) { if (!(pe_end >= 1500u && pe_end < (uint32_t)LD_PEEK_MS)) { L->peek_start = now - 1500u; L->peek_valid = 1; } }
        else if (pe_end < 1500u) { L->peek_start = now - 1500u; L->peek_valid = 1; }
      }
      L->moment = LOADED_NONE;
    }
  }
  if (!L->active && L->linger) lp.frame = L->linger_frame;
  lp.moment = L->active ? L->moment : LOADED_NONE;
  if (L->peek_valid) { uint32_t d = now - L->peek_start; if (d < 5000u) pe = (int32_t)d; }
  lp.peek_ms = pe; lp.tab_peek_ms = -2; lp.counter_peek_ms = -2;
  prepare(&q, &lp, L->active ? (int32_t)elapsed : -1);
  /* views whose input did not change are skipped (furniture is static most of the time) */
  mask = (1u << LOADED_V_FULL) | (1u << LOADED_V_TOP) | (1u << LOADED_V_BOTTOM);
  {
    uint32_t st = sig_of(lp.film, (uint32_t)q.hide_tab, 0x7ab, 1), sc;
    sc = sig_of((uint32_t)q.cs.a * 3u + (uint32_t)q.cs.dir + 7u, (uint32_t)q.cs.b, (uint32_t)q.cs.p * 2u + (uint32_t)q.cs.linear, (uint32_t)q.hide_counter);
    if (!(L->sig_valid & (1u << LOADED_V_TAB)) || L->sig[LOADED_V_TAB] != st) { mask |= 1u << LOADED_V_TAB; L->sig[LOADED_V_TAB] = st; }
    if (!(L->sig_valid & (1u << LOADED_V_COUNTER)) || L->sig[LOADED_V_COUNTER] != sc) { mask |= 1u << LOADED_V_COUNTER; L->sig[LOADED_V_COUNTER] = sc; }
    L->sig_valid |= (1u << LOADED_V_TAB) | (1u << LOADED_V_COUNTER);
  }
  render_core(L, b, &lp, &q, mask);
  if (!L->active && L->linger && q.hide_tab >= ONE && q.hide_counter >= ONE) L->linger = 0;   /* nothing left showing */
  return (int)(L->changed & 0x1fu) | (L->active ? 0x100 : 0) | (L->linger ? 0x200 : 0);
}
