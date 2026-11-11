/* SPDX-License-Identifier: GPL-2.0-only */
/* Loaded: freestanding C port of the JS reference renderer (src/renderer.mjs). No libc, no floating point,
 * no allocation, no writable globals: all state is in the caller's `loaded` struct and the caller's buffers.
 * Pixels are 32-bit words 0xAABBGGRR (R in the low byte), STRAIGHT (non-premultiplied) alpha, row stride in
 * pixels: the layout terminal.c hands to the native bitmap copy. */
#ifndef GRMOD_LOADED_H
#define GRMOD_LOADED_H
#include <stdint.h>

/* views, lowest z-order first (same order as the JS view plan) */
enum { LOADED_V_FULL = 0, LOADED_V_TOP, LOADED_V_BOTTOM, LOADED_V_COUNTER, LOADED_V_TAB, LOADED_VIEWS };
/* moments */
enum { LOADED_LIVE = 0, LOADED_SHOT, LOADED_LOAD, LOADED_ROLL, LOADED_NONE };
/* tab / counter modes */
enum { LOADED_ALWAYS = 0, LOADED_PEEK = 1, LOADED_INHERIT = 2 /* counter only: same as the tab */ };

#define LOADED_THUMB_W 64u
#define LOADED_THUMB_H 42u
#define LOADED_ROLL_FRAMES 36u

/* Per view: where to draw. `pixels` may be NULL only for the full-screen view (tier 1). */
typedef struct {
  uint32_t *pixels[LOADED_VIEWS];
  uint32_t stride[LOADED_VIEWS];    /* pixels per row, >= view width */
  uint32_t capacity[LOADED_VIEWS];  /* words available at `pixels`, >= stride * view height */
} loaded_buffers;

typedef struct {
  uint32_t moment;        /* LOADED_LIVE..LOADED_NONE (render only; start/tick use their own) */
  uint32_t film;          /* 0..19 */
  uint32_t frame;         /* 1..36: the number on the counter */
  uint32_t roll;          /* 0..999999 */
  uint32_t tier;          /* 1 = small views only, 2 = also the full-screen view */
  uint32_t tab_mode;      /* LOADED_ALWAYS | LOADED_PEEK */
  uint32_t counter_mode;  /* LOADED_ALWAYS | LOADED_PEEK | LOADED_INHERIT */
  int32_t peek_ms;        /* ms since the last peek trigger, -1 = none (render only; tick derives it) */
  int32_t tab_peek_ms;    /* -2 = use peek_ms */
  int32_t counter_peek_ms;/* -2 = use peek_ms */
  uint32_t month;         /* 0..11 for the slide mount's date stamp, 12 = no stamp */
  uint32_t year;          /* 0..99 */
  const uint32_t *thumbs; /* 36 contiguous 64x42 RGBA thumbnails, or NULL for plain tiles */
  int32_t circled;        /* frame index (0..35) to ring with grease pencil, -1 = derived from the roll */
} loaded_params;

typedef struct {
  uint32_t magic;
  loaded_params p;            /* configuration */
  uint32_t moment, active, start, peek_start, peek_valid;
  uint32_t dirty;             /* views whose buffer may hold non-transparent pixels */
  uint32_t sig_valid, sig[LOADED_VIEWS];
  uint32_t changed;           /* views drawn or cleared by the last render/tick */
  uint32_t pal[32];
  uint8_t filled[36];
  uint32_t canary;
} loaded;

/* Returns 0, or a negative error: -1 invalid parameters or buffers. On error every provided buffer is
 * cleared to transparent (inside its claimed capacity) and nothing is written outside it. */
void loaded_init(loaded *L);
/* Pure render of one state into the buffers (the JS render(moment, film, frame, roll, elapsedMs, options)). */
int loaded_render(loaded *L, const loaded_buffers *b, const loaded_params *p, int32_t elapsed_ms);

/* Lifecycle (the JS driver): configure, start a moment, tick from a millisecond clock, cancel. */
int loaded_set(loaded *L, const loaded_params *p);                  /* configuration only (live furniture) */
int loaded_start(loaded *L, const loaded_params *p, uint32_t now);  /* p->moment in SHOT..ROLL; replaces any running one */
void loaded_peek(loaded *L, uint32_t now);                           /* start the peek clock (power-on, film change, shot) */
void loaded_cancel(loaded *L);                                       /* the next tick clears the moment views */
/* Renders for the CURRENT clock (stale frames are skipped, the deadline never extends). Returns a negative
 * error or: bits 0..4 = views whose pixels changed this tick, bit 8 = a moment is still running. */
int loaded_tick(loaded *L, const loaded_buffers *b, uint32_t now);

extern const uint32_t loaded_state_bytes;   /* sizeof(loaded) */
extern const uint16_t loaded_view_rect[LOADED_VIEWS][4];   /* x, y, w, h on the 720x480 screen */
uint32_t loaded_duration(uint32_t film, uint32_t moment);

#endif
