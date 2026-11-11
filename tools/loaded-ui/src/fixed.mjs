// SPDX-License-Identifier: GPL-2.0-only
// Fixed-point helpers (Q10: 1024 = 1.0). Integer arithmetic only, every intermediate fits in int32,
// so the C port is a line-for-line copy (use arithmetic right shift for negative values).
export const ONE = 1024;

/** Progress of `t` inside [a, b] as Q10, clamped to 0..1024. */
export function prog(t, a, b) {
  if (t <= a) return 0;
  if (t >= b) return ONE;
  return (((t - a) * ONE) / (b - a)) | 0;
}
/** a + (b - a) * e, e in Q10. |b-a| must stay below 2^20. */
export const lerp = (a, b, e) => a + (((b - a) * e) >> 10);

/** smoothstep, ease in-out: 3t^2 - 2t^3 */
export function inOut(t) {
  const s2 = (t * t) >> 10;
  return (s2 * (3 * ONE - 2 * t)) >> 10;
}
export function outCubic(t) {
  const u = ONE - t, u2 = (u * u) >> 10;
  return ONE - ((u2 * u) >> 10);
}
export function inCubic(t) {
  const t2 = (t * t) >> 10;
  return (t2 * t) >> 10;
}
/** Overshoots by about 10 percent, then settles (the small bounce where something lands). */
export function outBack(t) {
  const u = t - ONE, u2 = (u * u) >> 10, u3 = (u2 * u) >> 10;
  return ONE + ((2766 * u3) >> 10) + ((1743 * u2) >> 10);
}
/** Dropped object: bounces three times (coefficients 7.5625 and 0.75/0.9375/0.984375). */
export function outBounce(t) {
  // Q10 version of the standard piecewise parabola; 7.5625 = 7744/1024.
  let u;
  if (t < 372) return (7744 * ((t * t) >> 10)) >> 10;
  if (t < 744) { u = t - 558; return ((7744 * ((u * u) >> 10)) >> 10) + 768; }
  if (t < 930) { u = t - 837; return ((7744 * ((u * u) >> 10)) >> 10) + 960; }
  u = t - 977; return ((7744 * ((u * u) >> 10)) >> 10) + 1008;
}
export const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);

/** Stateless integer hash: the only "randomness". Same inputs, same output, everywhere. */
export function hash32(a, b = 0) {
  let h = Math.imul(a | 0, 0x9e3779b1) ^ Math.imul((b | 0) + 0x7f4a7c15, 0x85ebca6b);
  h ^= h >>> 15; h = Math.imul(h, 0x2c1b3c6d); h ^= h >>> 12; h = Math.imul(h, 0x297a2d39); h ^= h >>> 15;
  return h >>> 0;
}
