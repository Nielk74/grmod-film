/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef GRMOD_CAMERA_LOADED_H
#define GRMOD_CAMERA_LOADED_H
#include <stdint.h>

/* GR III 2.10, film pack only (SHA-256 cf04126f5861c3a64123f0cdc95efa5b65443b44aa0ca975854423acf0131f55).
 * The hook sites, trampolines (hooks.S), callback ABIs and the state word (grmod_adapter_state, bound by the
 * link to the film pack's spare RAM word 0x558043b8) are those of the silent Terminal build that ran on a
 * camera. Shot, transition, draw and timer paths run on the native UI application task. */
extern void *volatile grmod_adapter_state;
extern volatile uint32_t grmod_audio_shutdown_latch;   /* bound by the link (read-only word); unused here */

void grmod_on_shot(void);
void grmod_before_transition(void *old_controller,uint32_t destination_id);
void grmod_after_transition(void);
void grmod_before_canvas_delete(void *root);
void grmod_before_audio_shutdown(void);   /* unreachable: the audio hook is not patched */
void grmod_cancel(void);
void grmod_draw(void *view,void *surface);
void grmod_timer_expired(void *listener,uint32_t timer_id);

/* The film selection as the adapter reads it (exported for the emulator checks). */
uint32_t loaded_film_of_look(uint32_t look);
uint32_t loaded_selected_film(void);
#endif
