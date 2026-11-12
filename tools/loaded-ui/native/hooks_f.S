/* SPDX-License-Identifier: GPL-2.0-only
 * Stage 1f diagnostic only: a sixth interposition, at the first instruction of the UI event dispatcher (0x53228ab4, `ldrh r2,[r1]`).
 * The callback sees the native arguments (r0 application, r1 event pointer); arguments, scratch registers, stack and flags survive;
 * the displaced instruction is replayed and the native body continues at 0x53228ab8. */
.syntax unified
.arm
.section .text.grmod_hooks_f,"ax",%progbits
.balign 4

.global grmod_hook_event
.type grmod_hook_event,%function
grmod_hook_event:
  push {r0-r3, r12, lr}
  mrs r12, cpsr
  push {r12, lr}
  bl grmod_on_event
  pop {r12, lr}
  msr APSR_nzcvqg, r12
  pop {r0-r3, r12, lr}
  ldrh r2, [r1]
  b native_event_resume
.size grmod_hook_event,.-grmod_hook_event

.section .note.GNU-stack,"",%progbits
