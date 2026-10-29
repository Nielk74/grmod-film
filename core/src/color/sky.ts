// SPDX-License-Identifier: GPL-2.0-only
/**
 * "Teal sky": a film's skies pushed toward teal (or back toward blue) by a step of -4..+4, folded into
 * its colour matrix. The mix is linear (light in, light out; neutrals stay neutral), so the camera's
 * film format holds it exactly: M1' = M1 . mix, applied to the colours before the film's own matrix.
 *
 * TEAL_SKY_MIX was solved (examples/gr3x/film-pack/teal_solve.py) to turn blue skies about 23 degrees
 * toward cyan (OkLCh hue ~259 -> ~236) while keeping skin and yellows where a linear mix allows (skin
 * within 3 degrees). Step k uses I + (k / 4) * (TEAL_SKY_MIX - I): +4 is that mix, negative steps go
 * the other way (bluer skies).
 */
import type { SlotParams } from './camera';

export const TEAL_SKY_MIX: readonly (readonly number[])[] = [[1.267, -0.155, -0.112], [0.076, 0.682, 0.242], [-0.075, 0.081, 0.994]];
export const TEAL_SKY_STEPS = 4;

/** The mix of step `k` (-4..+4): rows sum to 1. */
export function tealSkyMix(k: number): number[][] {
  const t = Math.max(-TEAL_SKY_STEPS, Math.min(TEAL_SKY_STEPS, Math.round(k))) / TEAL_SKY_STEPS;
  return TEAL_SKY_MIX.map((row, r) => row.map((v, c) => (r === c ? 1 : 0) + t * (v - (r === c ? 1 : 0))));
}

/**
 * The firmware's side (GR III films whose Hue is the teal sky): a film's quantised matrix `q`
 * (Q13, = M1 . M_STD, quantizeSlot) with step `k` applied as `withTealSky` would, without its fitted
 * parameters: q . M_STD^-1 . mix . M_STD, rounded, every row summing to exactly 8192 (grey stays grey).
 */
export function tealSkyQ13(q: ArrayLike<number>, mStdQ13: ArrayLike<number>, k: number): Int16Array {
  const Q = [0, 1, 2].map((r) => [0, 1, 2].map((c) => Number(q[r * 3 + c]) / 8192));
  const S = [0, 1, 2].map((r) => [0, 1, 2].map((c) => Number(mStdQ13[r * 3 + c]) / 8192));
  const mul = (a: number[][], b: number[][]) => a.map((row) => [0, 1, 2].map((c) => row[0] * b[0][c] + row[1] * b[1][c] + row[2] * b[2][c]));
  const det = S[0][0] * (S[1][1] * S[2][2] - S[1][2] * S[2][1]) - S[0][1] * (S[1][0] * S[2][2] - S[1][2] * S[2][0]) + S[0][2] * (S[1][0] * S[2][1] - S[1][1] * S[2][0]);
  const inv = [
    [S[1][1] * S[2][2] - S[1][2] * S[2][1], S[0][2] * S[2][1] - S[0][1] * S[2][2], S[0][1] * S[1][2] - S[0][2] * S[1][1]],
    [S[1][2] * S[2][0] - S[1][0] * S[2][2], S[0][0] * S[2][2] - S[0][2] * S[2][0], S[0][2] * S[1][0] - S[0][0] * S[1][2]],
    [S[1][0] * S[2][1] - S[1][1] * S[2][0], S[0][1] * S[2][0] - S[0][0] * S[2][1], S[0][0] * S[1][1] - S[0][1] * S[1][0]],
  ].map((row) => row.map((v) => v / det));
  const m = mul(mul(mul(Q, inv), tealSkyMix(k)), S);
  const out = Int16Array.from(m.flat().map((v) => Math.round(v * 8192)));
  for (let r = 0; r < 3; r++) out[r * 4] = 8192 - (out[r * 3] + out[r * 3 + 1] + out[r * 3 + 2] - out[r * 4]);
  return out;
}

/** A film's parameters with its skies moved by step `k` (the same object for 0). */
export function withTealSky(params: SlotParams, k: number): SlotParams {
  if (!k) return params;
  const m = tealSkyMix(k);
  const M1 = params.M1.map((row) => [0, 1, 2].map((c) => row[0] * m[0][c] + row[1] * m[1][c] + row[2] * m[2][c]));
  return { ...params, M1 };
}
