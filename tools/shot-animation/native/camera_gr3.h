/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef GRMOD_CAMERA_GR3_H
#define GRMOD_CAMERA_GR3_H
#include <stdint.h>

/* Experimental GR III 2.10 adapter, exact official RTOS SHA-256:
 * 8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67.
 * Shot, transition, draw and timer paths run on the native UI application task.
 * Audio-factory shutdown task context remains unverified; a permanent private
 * mutex drains any in-flight UI audio operation before native service deletion.
 * Hook trampolines preserve registers/flags and execute displaced instructions.
 * The link must bind grmod_adapter_state to reserved RAM 0x55804374 and the
 * shutdown latch to 0x55804378, extending startup zero-fill through 0x55804380.
 * No writable data belongs in the RTOS
 * payload. This exclusive reservation cannot coexist with another mod's state.
 */
extern void *volatile grmod_adapter_state;
extern volatile uint32_t grmod_audio_shutdown_latch;
extern const uint8_t terminal_asset_start[], terminal_asset_end[];
extern const uint8_t terminal_wav_dash_start[], terminal_wav_dash_end[];
extern const uint8_t terminal_wav_portal_start[], terminal_wav_portal_end[];
extern const uint8_t terminal_wav_rocket_start[], terminal_wav_rocket_end[];

void grmod_on_shot(void);
/* Before accepted old-controller exit at 0x5316caf8: old=r0, destination=r5.
 * Recognized shooting destinations detach and retain deadline; other IDs cancel
 * before exit can tear down audio. The trampoline passes destination in r1.
 * After new-controller entry, before displaced instruction at 0x5316cb74:
 * rebind recognized LiveView/QuickView; unsupported destinations cancel. */
void grmod_before_transition(void *old_controller, uint32_t destination_id);
void grmod_after_transition(void);
/* Before native Canvas deleting destructor 0x533918d0. */
void grmod_before_canvas_delete(void *root);
/* Before AudioServiceFactory::Shutdown at0x53568d58. Set latch, then wait on
 * the adapter's permanent private mutex to drain an in-flight UI audio call.
 * No service/UI calls occur here; native shutdown retains stop/free ownership.
 * Custom audio stays disabled until reboot, including without player state. */
void grmod_before_audio_shutdown(void);
/* Release-attempt/user cancellation: immediate visual detach, try-lock audio
 * cancellation and UI-timer retries if the audio mutex is busy. */
void grmod_cancel(void);

/* Frozen native callback ABIs, AAPCS. Draw always chains to native base Draw.
 * Timer listener is adapter-owned and persistent; native dispatch uses +8. */
void grmod_draw(void *view, void *surface);
void grmod_timer_expired(void *listener, uint32_t timer_id);
#endif
