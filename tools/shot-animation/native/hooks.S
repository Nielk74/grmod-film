/* SPDX-License-Identifier: GPL-2.0-only
 * A32 interposition for the exact stock GR III 2.10 instructions in the manifest.
 * The native caller's arguments, scratch registers, stack and arithmetic flags
 * survive each added callback. Native call/tail-call/entry behavior is replayed.
 */
.syntax unified
.arm
.section .text.grmod_hooks,"ax",%progbits
.balign 4

.macro save_context
  push {r0-r3, r12, lr}
  mrs r12, cpsr
  push {r12, lr}
.endm
.macro restore_context
  pop {r12, lr}
  msr APSR_nzcvqg, r12
  pop {r0-r3, r12, lr}
.endm
.macro callback name
  save_context
  bl \name
  restore_context
.endm

.global grmod_hook_shot
.type grmod_hook_shot,%function
grmod_hook_shot:
  callback grmod_on_shot
  b native_enqueue
.size grmod_hook_shot,.-grmod_hook_shot

.global grmod_hook_transition_before
.type grmod_hook_transition_before,%function
grmod_hook_transition_before:
  save_context
  /* R5 is the accepted destination factory ID, set at native5316cad8. */
  mov r1, r5
  bl grmod_before_transition
  restore_context
  bx r3
.size grmod_hook_transition_before,.-grmod_hook_transition_before

.global grmod_hook_transition_after
.type grmod_hook_transition_after,%function
grmod_hook_transition_after:
  callback grmod_after_transition
  ldrb r3, [r4, #0x154]
  b native_transition_resume
.size grmod_hook_transition_after,.-grmod_hook_transition_after

.global grmod_hook_canvas_delete
.type grmod_hook_canvas_delete,%function
grmod_hook_canvas_delete:
  callback grmod_before_canvas_delete
  mov r12, sp
  b native_canvas_delete_resume
.size grmod_hook_canvas_delete,.-grmod_hook_canvas_delete

.global grmod_hook_release
.type grmod_hook_release,%function
grmod_hook_release:
  callback grmod_cancel
  mov r12, sp
  b native_release_resume
.size grmod_hook_release,.-grmod_hook_release

.global grmod_hook_audio_shutdown
.type grmod_hook_audio_shutdown,%function
grmod_hook_audio_shutdown:
  callback grmod_before_audio_shutdown
  mov r12, sp
  b native_audio_shutdown_resume
.size grmod_hook_audio_shutdown,.-grmod_hook_audio_shutdown

.section .note.GNU-stack,"",%progbits
