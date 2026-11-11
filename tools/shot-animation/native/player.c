/* SPDX-License-Identifier: GPL-2.0-only */
#include "player.h"
#define HEADER 32u
#define FRAMES 100u
#define TABLE_END (HEADER + (FRAMES + 1u) * 4u)
#define DURATION 5000u
#define ENTER 350u
#define LEAVE 350u
#define TOTAL (ENTER + DURATION + LEAVE)
#define FRAME_MS 50u
#define MAX_BYTES (8u * 1024u * 1024u)

static uint32_t u16(const uint8_t *p) { return (uint32_t)p[0] | (uint32_t)p[1] << 8; }
static uint32_t u32(const uint8_t *p) { return u16(p) | u16(p + 2) << 16; }
static uint32_t crc32(const uint8_t *p, uint32_t bytes) {
  uint32_t crc = 0xffffffffu, i;
  while (bytes--) {
    crc ^= *p++;
    for (i = 0; i < 8; ++i) crc = (crc >> 1) ^ ((crc & 1u) ? 0xedb88320u : 0u);
  }
  return crc ^ 0xffffffffu;
}

int sa_load(sa_player *s, const uint8_t *a, uint32_t bytes, const sa_callbacks *cb, void *user) {
  uint32_t f, width, height;
  if (!s) return 0;
  /* New/uninitialized state is accepted. The owner must cancel before reload. */
  s->asset = 0; s->active = 0; s->enabled = 0; s->audible = 0;
  s->bytes = 0; s->started = 0; s->last_frame = FRAMES; s->sound_cues = 0;
  s->width = 0; s->height = 0; s->user = user;
  s->palette_count = 0; s->compact = 0;
  s->transition = 0; s->placed = 0; s->last_alpha = 0;
  s->last_y = 0; s->last_sx = s->last_sy = 256;
  if (!a || bytes < HEADER || bytes > MAX_BYTES || !cb || !cb->begin ||
      !cb->span || !cb->present || !cb->clear || !cb->place || (cb->sound && !cb->stop_sound)) return 0;
  if (a[0] == 'G' && a[1] == 'S' && a[2] == 'P' && a[3] == '1') {
    uint32_t colors = u16(a + 12), count = u16(a + 10), offset = 32u + colors * 4u + count * 4u, i, previous = 0;
    width = u16(a + 6); height = u16(a + 8);
    if (u16(a + 4) != 1 || !width || !height || width > 128 || height > 128 ||
        !count || count > 12 || !colors || colors > 256 || u16(a + 14) ||
        u32(a + 16) != DURATION || u32(a + 20) != bytes || u32(a + 28) != offset ||
        bytes != offset + width * height * count) return 0;
    if (u32(a + 24) != crc32(a + HEADER, bytes - HEADER)) return 0;
    for (i = 0; i < colors; ++i) if (a[34u + i*4u] % 17u || a[35u + i*4u]) return 0;
    for (i = 0; i < count; ++i) {
      uint32_t time = u32(a + HEADER + colors * 4u + i * 4u);
      if (time >= DURATION || (i ? time <= previous : time != 0)) return 0;
      previous = time;
    }
    for (i = offset; i < bytes; ++i) if (a[i] >= colors) return 0;
    s->asset = a; s->bytes = bytes; s->width = (uint16_t)width; s->height = (uint16_t)height;
    s->palette_count = (uint16_t)colors; s->compact = 1; s->callbacks = *cb; s->enabled = 1;
    return 1;
  }
  if (bytes < TABLE_END) return 0;
  if (a[0] != 'G' || a[1] != 'S' || a[2] != 'A' || a[3] != '1' || u16(a + 4) != 1u) return 0;
  width = u16(a + 6); height = u16(a + 8);
  if (!width || !height || width > 240u || height > 176u) return 0;
  if (u16(a + 10) != 20u || u16(a + 12) != FRAMES || u16(a + 14) ||
      u32(a + 16) != DURATION || u32(a + 20) != bytes || u32(a + 28) != HEADER) return 0;
  if (u32(a + HEADER) != TABLE_END || u32(a + HEADER + FRAMES * 4u) != bytes) return 0;
  if (u32(a + 24) != crc32(a + HEADER, bytes - HEADER)) return 0;
  for (f = 0; f < FRAMES; ++f) {
    uint32_t start = u32(a + HEADER + f * 4u), end = u32(a + HEADER + (f + 1u) * 4u), pixels = 0;
    if (start > end || end > bytes || (end - start) % 6u) return 0;
    while (start < end) {
      uint32_t count = u16(a + start);
      if (!count || count > width * height - pixels || a[start + 5] || a[start + 4] % 17u) return 0;
      pixels += count; start += 6u;
    }
    if (pixels != width * height) return 0;
  }
  s->asset = a; s->bytes = bytes; s->width = (uint16_t)width; s->height = (uint16_t)height;
  s->callbacks = *cb; s->enabled = 1;
  return 1;
}

void sa_cancel(sa_player *s) {
  if (!s || !s->active) return;
  s->active = 0;
  if (s->audible && s->callbacks.stop_sound) s->callbacks.stop_sound(s->user);
  s->callbacks.clear(s->user);
  s->audible = 0;
}

void sa_set_enabled(sa_player *s, int enabled) {
  if (!s) return;
  if (!enabled) sa_cancel(s);
  s->enabled = enabled != 0;
}

void sa_set_transition(sa_player *s, uint32_t transition) {
  if (!s) return;
  sa_cancel(s); s->transition = (uint8_t)(transition < 3 ? transition : 0);
}

void sa_shot(sa_player *s, uint32_t now, int allowed) {
  if (!s) return;
  sa_cancel(s);
  if (!s->enabled || !s->asset) return;
  s->started = now; s->last_frame = FRAMES; s->sound_cues = 0;
  s->placed = 0;
  s->audible = (uint8_t)(allowed && s->callbacks.sound != 0);
  s->active = 1;
  sa_tick(s, now);
}

static void sound_tick(sa_player *s, uint32_t elapsed) {
  /* Skip missed sounds as well as missed frames; never release a burst of cues
   * after a slow UI tick. The adapter resolves tones only if it is verified. */
  if (s->audible && elapsed >= 2950u) {
    uint32_t cue = elapsed < 3080u ? 1u : elapsed < 3240u ? 2u : elapsed < 3450u ? 3u : 0u;
    if (cue && !(s->sound_cues & (1u << cue))) {
      s->sound_cues |= (1u << (cue + 1u)) - 1u;
      s->callbacks.sound(s->user, cue);
    }
  }
}

static inline __attribute__((always_inline)) int32_t rounded(int32_t n, uint32_t d) {
  return n < 0 ? -(int32_t)(((uint32_t)-n + d/2u)/d) : (int32_t)(((uint32_t)n + d/2u)/d);
}
static uint32_t ease_out(uint32_t p) {
  uint32_t r = 256u-p; return 256u-(r*r*r/65536u);
}
static int placement(sa_player *s, uint32_t elapsed) {
  int32_t y = 0;
  uint32_t alpha = 255, sx = 256, sy = 256;
  if (elapsed < ENTER || elapsed >= ENTER+DURATION) {
    uint32_t entering = elapsed < ENTER;
    uint32_t p = (entering ? elapsed : elapsed-ENTER-DURATION)*256u/350u;
    alpha = (uint32_t)rounded((int32_t)(255u*(entering ? p : 256u-p)),256u);
    if (s->transition == 1) {
      if (entering) {
        if (p < 166u) y = 18-rounded((int32_t)(22u*ease_out(p*256u/166u)),256u);
        else { uint32_t r = 256u-(p-166u)*256u/90u; y = rounded(-4*(int32_t)(r*r),65536u); }
        alpha = (uint32_t)rounded((int32_t)(255u*(p*3u < 256u ? p*3u : 256u)),256u);
      } else if (p < 77u) y = rounded(-3*(int32_t)ease_out(p*256u/77u),256u);
      else { uint32_t q=(p-77u)*256u/179u; y=-3+rounded(21*(int32_t)(q*q),65536u); }
    } else if (s->transition == 2) {
      if (entering) {
        if (p < 59u) { sx=51u+(uint32_t)rounded((int32_t)(205u*ease_out(p*256u/59u)),256u); sy=5; }
        else sy=5u+(uint32_t)rounded((int32_t)(251u*ease_out((p-59u)*256u/197u)),256u);
        alpha=(uint32_t)rounded((int32_t)(255u*(p*4u < 256u ? p*4u : 256u)),256u);
      } else if (p < 197u) { uint32_t q=p*256u/197u; sy=256u-(uint32_t)rounded(251*(int32_t)(q*q),65536u); }
      else { sy=5; sx=256u-(uint32_t)rounded((int32_t)(205u*((p-197u)*256u/59u)),256u); }
    } else {
      uint32_t r=256u-p;
      y=entering ? rounded(14*(int32_t)(r*r*r),16777216u) : rounded(10*(int32_t)(p*p),65536u);
    }
  }
  if (!s->placed || y != s->last_y || alpha != s->last_alpha || sx != s->last_sx || sy != s->last_sy) {
    s->callbacks.place(s->user,y,(uint8_t)alpha,(uint16_t)sx,(uint16_t)sy);
    s->placed=1; s->last_y=y; s->last_alpha=(uint8_t)alpha; s->last_sx=(uint16_t)sx; s->last_sy=(uint16_t)sy;
    return 1;
  }
  return 0;
}

void sa_tick(sa_player *s, uint32_t now) {
  uint32_t elapsed, act, frame, p, end, pixel = 0;
  int moved;
  if (!s || !s->active) return;
  elapsed = now - s->started;
  if (elapsed >= TOTAL) { sa_cancel(s); return; }
  act = elapsed < ENTER ? 0u : elapsed-ENTER < DURATION ? elapsed-ENTER : DURATION-1u;
  moved = placement(s,elapsed);
  frame = act / FRAME_MS;
  if (s->compact) {
    uint32_t i, count = u16(s->asset + 10);
    frame = 0;
    for (i = 1; i < count; ++i) {
      if (act < u32(s->asset + HEADER + (uint32_t)s->palette_count * 4u + i * 4u)) break;
      frame = i;
    }
  }
  if (frame == s->last_frame) {
    if (moved) s->callbacks.present(s->user);
    sound_tick(s, act); return;
  }
  if (!s->callbacks.begin(s->user, s->width, s->height)) { sa_cancel(s); return; }
  if (s->compact) {
    uint32_t pixels = (uint32_t)s->width * s->height;
    p = u32(s->asset + 28) + frame * pixels; end = p + pixels;
    while (p < end) {
      uint32_t index = s->asset[p], count = 1;
      const uint8_t *color = s->asset + HEADER + index * 4u;
      while (p + count < end && s->asset[p + count] == index) ++count;
      if (color[2]) s->callbacks.span(s->user, pixel, count, (uint16_t)u16(color), color[2]);
      pixel += count; p += count;
    }
  } else {
    p = u32(s->asset + HEADER + frame * 4u);
    end = u32(s->asset + HEADER + (frame + 1u) * 4u);
    while (p < end) {
      uint32_t count = u16(s->asset + p);
      if (s->asset[p + 4]) s->callbacks.span(s->user, pixel, count, (uint16_t)u16(s->asset + p + 2), s->asset[p + 4]);
      pixel += count; p += 6u;
    }
  }
  s->callbacks.present(s->user); s->last_frame = frame; sound_tick(s, act);
}
