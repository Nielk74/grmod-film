/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef GRMOD_SHOT_ANIMATION_PLAYER_H
#define GRMOD_SHOT_ANIMATION_PLAYER_H
#include <stdint.h>

/* The camera adapter must call these from its UI task only. Asset bytes remain
 * immutable and alive while loaded. begin clears ONLY the owned overlay plane;
 * span fills consecutive row-major pixels, and present requests a UI redraw.
 * clear removes the owned overlay. No callbacks may sleep or wait for capture.
 * No camera addresses or photographic image buffers belong in this module. */
typedef struct {
  int (*begin)(void *user, uint32_t width, uint32_t height);
  void (*span)(void *user, uint32_t pixel, uint32_t count, uint16_t rgb565, uint8_t alpha);
  void (*present)(void *user);
  void (*clear)(void *user);
  void (*sound)(void *user, uint32_t cue); /* optional: 1,2,3 = short rising chirp */
  void (*stop_sound)(void *user);         /* required if sound is supplied */
  /* Required placement of the owned UI element, around its bottom centre.
   * scale_x/scale_y are Q8 (256 = 1); opacity is 0..255. No extra image planes. */
  void (*place)(void *user, int32_t y_offset, uint8_t opacity, uint16_t scale_x, uint16_t scale_y);
} sa_callbacks;

typedef struct {
  const uint8_t *asset;
  uint32_t bytes, started, last_frame, sound_cues;
  uint16_t width, height, palette_count;
  uint8_t active, enabled, audible, compact;
  uint8_t transition, placed, last_alpha;
  int32_t last_y;
  uint16_t last_sx, last_sy;
  sa_callbacks callbacks;
  void *user;
} sa_player;

int sa_load(sa_player *player, const uint8_t *asset, uint32_t bytes,
            const sa_callbacks *callbacks, void *user);
void sa_set_enabled(sa_player *player, int enabled);
/* 0 Soft Dock, 1 Tiny Hop, 2 CRT Boot; changing it cancels current playback. */
void sa_set_transition(sa_player *player, uint32_t transition);
/* Invoke once per successfully recorded still. Replaces an older animation.
 * camera_sound_allowed must reflect the camera's current mute/volume setting. */
void sa_shot(sa_player *player, uint32_t now_ms, int camera_sound_allowed);
void sa_tick(sa_player *player, uint32_t now_ms);
/* New shutter/half-press, MENU, playback, display change, power-off, failed shot. */
void sa_cancel(sa_player *player);
#endif
