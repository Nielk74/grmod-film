/* SPDX-License-Identifier: GPL-2.0-only */
#include "camera_clock.h"

int grmod_clock_ms(uint32_t *out){
  typedef int (*native_clock_fn)(uint64_t *);
  uint64_t milliseconds;
  if(!out)return 0;
  /* Native UI clock, exact GR III 2.10 RTOS SHA-256:
   * 8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67.
   * 0x536afc5c normalizes the OS {high,low} words to uint64_t and returns
   * success. LiveView uses time %1000 for its two 500 ms blink phases;
   * native View animation compares the low-word delta to its duration.
   * See out/firmware-lifecycle for bytes, callers and emulated ABI checks. */
  if(!((native_clock_fn)(uintptr_t)0x536afc5cu)(&milliseconds))return 0;
  *out=(uint32_t)milliseconds;
  return 1;
}
