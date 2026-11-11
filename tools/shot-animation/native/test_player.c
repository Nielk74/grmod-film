/* SPDX-License-Identifier: GPL-2.0-only */
#include "player.h"
uint32_t checks;
#define CHECK(x) do { ++checks; if (!(x)) return __LINE__; } while (0)
static uint8_t fixture[1036];
static uint32_t draws, clears, spans, notes, stops, blocked, last_color, last_alpha, presents;
static uint32_t positions, placed_alpha, placed_sx, placed_sy;
static int32_t placed_y;
static int begin(void *u, uint32_t w, uint32_t h) { (void)u; if (w != 1u || h != 1u) return 0; ++draws; return !blocked; }
static void span(void *u, uint32_t pixel, uint32_t n, uint16_t color, uint8_t alpha) {
  (void)u; (void)pixel; (void)n; ++spans; last_color = color; last_alpha = alpha;
}
static void present(void *u) { (void)u; ++presents; }
static void clear(void *u) { (void)u; ++clears; }
static void sound(void *u, uint32_t cue) { (void)u; notes = notes * 10u + cue; }
static void stop(void *u) { (void)u; ++stops; }
static void place(void *u, int32_t y, uint8_t a, uint16_t sx, uint16_t sy) {
  (void)u; ++positions; placed_y=y; placed_alpha=a; placed_sx=sx; placed_sy=sy;
}
static void put16(uint32_t at, uint32_t n) { fixture[at] = (uint8_t)n; fixture[at+1] = (uint8_t)(n >> 8); }
static void put32(uint32_t at, uint32_t n) { put16(at, n); put16(at+2, n >> 16); }
static void crc(void) {
  uint32_t c = 0xffffffffu, n, b;
  for (n = 32; n < sizeof fixture; ++n) {
    c ^= fixture[n];
    for (b = 0; b < 8; ++b) c = (c >> 1) ^ ((c & 1u) ? 0xedb88320u : 0u);
  }
  put32(24, c ^ 0xffffffffu);
}
static void make(void) {
  uint32_t i;
  for (i = 0; i < sizeof fixture; ++i) fixture[i] = 0;
  fixture[0] = 'G'; fixture[1] = 'S'; fixture[2] = 'A'; fixture[3] = '1';
  put16(4,1); put16(6,1); put16(8,1); put16(10,20); put16(12,100);
  put32(16,5000); put32(20,sizeof fixture); put32(28,32);
  for (i = 0; i <= 100; ++i) put32(32+i*4,436+i*6);
  for (i = 0; i < 100; ++i) { put16(436+i*6,1); put16(438+i*6,i); fixture[440+i*6] = 255; }
  crc();
}

uint32_t test_all(void) {
  sa_player s;
  sa_callbacks cb = {begin, span, present, clear, sound, stop, place};
  uint32_t i, before;
  checks = draws = clears = spans = notes = stops = blocked = 0;
  make();
  CHECK(sa_load(&s,fixture,sizeof fixture,&cb,0));
  CHECK(!s.active);
  sa_shot(&s,1000,0); CHECK(s.active && draws == 1 && last_color == 0 && last_alpha == 255);
  sa_tick(&s,1049); CHECK(draws == 1);
  sa_tick(&s,1400); CHECK(draws == 2 && last_color == 1);
  sa_tick(&s,6300); CHECK(s.last_frame == 99 && s.active);
  sa_tick(&s,6700); CHECK(!s.active && clears == 1 && notes == 0);
  sa_tick(&s,99999); CHECK(draws == 3);
  sa_shot(&s,20000,1); sa_tick(&s,23300); CHECK(notes == 1);
  sa_tick(&s,23400); CHECK(notes == 1);
  sa_tick(&s,23450); CHECK(notes == 12);
  sa_tick(&s,23600); CHECK(notes == 123);
  sa_cancel(&s); CHECK(!s.active && stops == 1 && clears == 2);
  before = clears; sa_cancel(&s); CHECK(clears == before);
  notes = 0; sa_shot(&s,0,1); sa_tick(&s,3750); CHECK(notes == 3);
  sa_tick(&s,3800); CHECK(notes == 3);
  sa_shot(&s,3500,0); CHECK(s.started == 3500 && s.last_frame == 0 && s.active);
  sa_tick(&s,9200); CHECK(!s.active);
  sa_shot(&s,0xffffff00u,0); sa_tick(&s,0xffffff00u+5300u); CHECK(s.active && s.last_frame == 99);
  sa_tick(&s,0xffffff00u+5700u); CHECK(!s.active);
  sa_set_enabled(&s,0); before=draws; sa_shot(&s,0,1); CHECK(!s.active && draws == before);
  sa_set_enabled(&s,1); sa_shot(&s,0,0); CHECK(s.active);
  sa_set_enabled(&s,0); CHECK(!s.active);
  sa_set_enabled(&s,1); blocked = 1; sa_shot(&s,0,0); CHECK(!s.active);
  blocked = 0;
  for (i = 0; i < 32; ++i) {
    uint8_t saved = fixture[i]; fixture[i] ^= 0x80;
    CHECK(!sa_load(&s,fixture,sizeof fixture,&cb,0)); fixture[i] = saved;
  }
  CHECK(!sa_load(&s,fixture,sizeof fixture-1,&cb,0));
  fixture[436] = 0; crc(); CHECK(!sa_load(&s,fixture,sizeof fixture,&cb,0));
  make(); fixture[440] = 1; crc(); CHECK(!sa_load(&s,fixture,sizeof fixture,&cb,0));
  make(); fixture[441] = 1; crc(); CHECK(!sa_load(&s,fixture,sizeof fixture,&cb,0));
  make(); put32(32,0); crc(); CHECK(!sa_load(&s,fixture,sizeof fixture,&cb,0));
  make(); cb.stop_sound = 0; CHECK(!sa_load(&s,fixture,sizeof fixture,&cb,0));
  cb.sound = 0; CHECK(sa_load(&s,fixture,sizeof fixture,&cb,0));
  sa_shot(&s,0,1); sa_tick(&s,3300); CHECK(s.active && !s.audible);
  sa_cancel(&s);
  CHECK(!sa_load(0,fixture,sizeof fixture,&cb,0));
  return 0;
}

/* Exercise real exported assets with the same compiled player, validating each
 * frame's coverage and alpha through the strict loader. */
static int actual_begin(void *u, uint32_t w, uint32_t h) { (void)u; ++draws; return (w == 240 && h == 176) || (w == 128 && h == 128); }
uint32_t test_asset(const uint8_t *bytes, uint32_t length) {
  sa_player s;
  sa_callbacks cb = {actual_begin, span, present, clear, 0, 0, place};
  uint32_t i;
  CHECK(sa_load(&s, bytes, length, &cb, 0));
  sa_shot(&s, 0, 0);
  for (i = 1; i < 100; ++i) { sa_tick(&s, 350u+i * 50u); CHECK(s.last_frame == i && s.active); }
  sa_tick(&s, 5700); CHECK(!s.active);
  return 0;
}

uint32_t test_compact(const uint8_t *bytes, uint32_t length) {
  sa_player s;
  sa_callbacks cb = {actual_begin, span, present, clear, sound, stop, place};
  uint32_t i, count = (uint32_t)bytes[10] | (uint32_t)bytes[11] << 8;
  uint32_t colors = (uint32_t)bytes[12] | (uint32_t)bytes[13] << 8;
  draws = notes = 0;
  CHECK(sa_load(&s,bytes,length,&cb,0));
  CHECK(s.compact && s.width == 128 && s.height == 128);
  for (i = 0; i < 3; ++i) {
    sa_set_transition(&s,i); draws = presents = 0;
    sa_shot(&s,0,0); CHECK(draws == 1 && presents == 1);
    sa_tick(&s,100); CHECK(draws == 1 && presents == 2);
    sa_tick(&s,101); CHECK(draws == 1 && presents == 2);
    sa_cancel(&s);
  }
  sa_set_transition(&s,0); draws = notes = presents = 0;
  sa_shot(&s,0,0);
  for (i = 1; i < count; ++i) {
    const uint8_t *t = bytes + 32u + colors * 4u + i * 4u;
    uint32_t at = (uint32_t)t[0] | (uint32_t)t[1] << 8 | (uint32_t)t[2] << 16 | (uint32_t)t[3] << 24;
    sa_tick(&s,350u+at-1u); CHECK(s.last_frame == i-1u && draws == i);
    sa_tick(&s,350u+at); CHECK(s.last_frame == i && draws == i+1u);
    sa_tick(&s,350u+at+1u); CHECK(s.last_frame == i && draws == i+1u);
  }
  sa_cancel(&s); draws = notes = 0;
  sa_shot(&s,0,1);
  for (i = 50; i < 5700; i += 50) sa_tick(&s,i);
  CHECK(draws == ((uint32_t)bytes[10] | (uint32_t)bytes[11] << 8) && s.last_frame == draws - 1u && s.active);
  CHECK(notes == 123);
  sa_tick(&s,5700); CHECK(!s.active);
  CHECK(!sa_load(&s,bytes,length-1,&cb,0));
  return 0;
}

uint32_t test_motion_sample(uint32_t elapsed, uint32_t variant, int32_t *out) {
  sa_player s;
  sa_callbacks cb = {begin, span, present, clear, 0, 0, place};
  make(); CHECK(sa_load(&s,fixture,sizeof fixture,&cb,0));
  sa_set_transition(&s,variant); sa_shot(&s,0,0); sa_tick(&s,elapsed);
  out[0]=placed_y; out[1]=(int32_t)placed_alpha; out[2]=(int32_t)placed_sx; out[3]=(int32_t)placed_sy;
  sa_cancel(&s); return 0;
}
