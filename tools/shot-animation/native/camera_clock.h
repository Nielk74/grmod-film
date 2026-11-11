/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef GRMOD_CAMERA_CLOCK_H
#define GRMOD_CAMERA_CLOCK_H
#include <stdint.h>

/* GR III 2.10 only. Returns 1 with the low 32 bits of native operating time
 * in milliseconds, or 0 with *out unchanged. A null out returns 0.
 * Compute short elapsed intervals with unsigned subtraction, including across
 * the 49.7-day wrap. Check success before using the timestamp. */
int grmod_clock_ms(uint32_t *out);
#endif
