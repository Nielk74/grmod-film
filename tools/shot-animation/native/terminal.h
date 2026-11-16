/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef GRMOD_TERMINAL_H
#define GRMOD_TERMINAL_H
#include <stdint.h>
#define TERMINAL_W 240u
#define TERMINAL_H 176u
#define TERMINAL_PIXELS (TERMINAL_W*TERMINAL_H)
#define TERMINAL_DURATION 7600u
/* One UI task owns a player and its output. Asset data stays immutable and alive.
 * Drawing never allocates, waits or accesses a photographic image buffer. */
typedef struct {
  const uint8_t *asset;
  uint32_t bytes,indices,tracks,vectors,started,last_frame;
  uint32_t colors[256];
  uint16_t inverse_alpha[256];
  int32_t intersections[256];
  uint8_t loaded,active,sequence,previous,bag[3],cursor;
} terminal_player;
int terminal_load(terminal_player *p,const uint8_t *asset,uint32_t bytes);
int terminal_render(terminal_player *p,uint32_t sequence,uint32_t elapsed,
                    uint32_t *rgba,uint32_t stride,uint32_t capacity_pixels);
/* Replaces the previous shot. A shuffled set contains all three sequences and
 * the set boundary never repeats the preceding one. Entropy is supplied by owner. */
int terminal_shot(terminal_player *p,uint32_t now_ms,uint32_t entropy);
/* 1=new frame,0=unchanged/inactive,-1=deadline: clear owned view,-2=invalid buffer. */
int terminal_tick(terminal_player *p,uint32_t now_ms,uint32_t *rgba,
                  uint32_t stride,uint32_t capacity_pixels);
void terminal_cancel(terminal_player *p);
#endif
