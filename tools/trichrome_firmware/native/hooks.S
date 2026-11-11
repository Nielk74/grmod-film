/* SPDX-License-Identifier: GPL-2.0-only */
.syntax unified
.arm
.fpu neon
.text
.macro save_all
  push {r0-r12,lr}
  mrs r4,cpsr
  push {r4,ip}
  vpush {d0-d15}
  vpush {d16-d31}
  vmrs r4,fpscr
  push {r4,ip}
.endm
.macro restore_all
  pop {r4,ip}
  vmsr fpscr,r4
  vpop {d16-d31}
  vpop {d0-d15}
  pop {r4,ip}
  msr CPSR_f,r4
  pop {r0-r12,lr}
.endm
.global tri_hook_arm
.type tri_hook_arm,%function
tri_hook_arm:
  save_all
  bl tri_camera_arm
  restore_all
  mov ip,sp
  b tri_cont_arm
.global tri_hook_expose
.type tri_hook_expose,%function
tri_hook_expose:
  save_all
  bl tri_camera_expose
  restore_all
  b tri_prior_expose
.global tri_hook_jpeg
.type tri_hook_jpeg,%function
tri_hook_jpeg:
  save_all
  ldr r0,[r1,#8]
  bl tri_camera_jpeg
  restore_all
  b tri_prior_jpeg
.global tri_hook_override
.type tri_hook_override,%function
tri_hook_override:
  save_all
  bl tri_camera_override
  restore_all
  subs r3,r2,#0
  b tri_cont_override
.global tri_hook_single
.type tri_hook_single,%function
tri_hook_single:
  save_all
  bl tri_camera_cancel
  restore_all
  mov ip,sp
  b tri_cont_single
