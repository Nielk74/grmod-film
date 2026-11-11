// SPDX-License-Identifier: GPL-2.0-only
// The view plan: every view is a fixed rectangle on the 720x480 screen, decided once.
export const W = 720, H = 480, BAND = 44;

/** tier 1 = small fixed views (the path the camera already proved); tier 2 = one full-screen view (unproven). */
export const VIEWS = [
  // z-order: first = lowest. The full-screen view sits under the small views.
  { id: 'full',    tier: 2, x: 0,   y: 0,   w: 720, h: 480, role: 'moment' },
  { id: 'top',     tier: 1, x: 0,   y: 0,   w: 720, h: 44,  role: 'moment' },
  { id: 'bottom',  tier: 1, x: 0,   y: 436, w: 720, h: 44,  role: 'moment' },
  { id: 'counter', tier: 1, x: 648, y: 52,  w: 72,  h: 40,  role: 'furniture' },
  { id: 'tab',     tier: 1, x: 0,   y: 52,  w: 128, h: 56,  role: 'furniture' },
];
export const rgbaBytes = v => v.w * v.h * 4;
export const tierBytes = tier => VIEWS.filter(v => v.tier <= tier).reduce((n, v) => n + rgbaBytes(v), 0);
export const tier1Bytes = () => VIEWS.filter(v => v.tier === 1).reduce((n, v) => n + rgbaBytes(v), 0);
export const tier2Bytes = () => VIEWS.filter(v => v.tier === 2).reduce((n, v) => n + rgbaBytes(v), 0);

/** Moment lengths in ms. Nothing ever runs longer; at the deadline every moment view is transparent. */
export const SHOT_MS = { neg: 1500, bw: 1500, cine: 1500, slide: 1300, instant: 1800 };
export const LOAD_MS = 2200;
export const ROLL_MS = 3400;
export const PEEK_MS = 2000;
export const MOMENTS = ['live', 'shot', 'load', 'roll'];
export function duration(moment, film) {
  if (moment === 'shot') return SHOT_MS[film.kind];
  if (moment === 'load') return LOAD_MS;
  if (moment === 'roll') return ROLL_MS;
  return 0;
}

/**
 * Placeholder for the camera's own live-view furniture. NOT ESTABLISHED: nothing in this repository
 * records where the GR III's native exposure row and icons sit. These rectangles are guesses used only by
 * the lab to judge collisions, drawn labelled as placeholders. They are not part of any view.
 */
export const PLACEHOLDERS = [
  { x: 0, y: 440, w: 720, h: 36, label: 'PLACEHOLDER: EXPOSURE INFO ROW (POSITION UNVERIFIED)' },
  { x: 560, y: 4, w: 156, h: 30, label: 'PLACEHOLDER: STATUS ICONS' },
  { x: 4, y: 4, w: 150, h: 30, label: 'PLACEHOLDER: MODE ICONS' },
];
