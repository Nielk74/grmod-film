// SPDX-License-Identifier: GPL-2.0-only
// The view plan: every view is a fixed rectangle on the 720x480 screen, decided once.
export const W = 720, H = 480, BAND = 44;

/** tier 1 = small fixed views (the path the camera already proved); tier 2 = one full-screen view (unproven). */
export const VIEWS = [
  // z-order: first = lowest. The full-screen view sits under the small views.
  { id: 'full',    tier: 2, x: 0,   y: 0,   w: 720, h: 480, role: 'moment' },
  { id: 'top',     tier: 1, x: 0,   y: 0,   w: 720, h: 44,  role: 'moment' },
  { id: 'bottom',  tier: 1, x: 0,   y: 436, w: 720, h: 44,  role: 'moment' },
  { id: 'counter', tier: 1, x: 612, y: 380, w: 108, h: 48,  role: 'furniture' },
  { id: 'tab',     tier: 1, x: 0,   y: 376, w: 128, h: 56,  role: 'furniture' },
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
 * The camera's own live-view elements, "live view (from the owner's photo, approximate)": measured from a phone
 * photo of the owner's GR III shooting screen (Av mode, snap focus distance shown), scaled to 720x480, each edge
 * good to about 6 px. One configuration only: other modes may add icons. Not part of any view; furniture keeps
 * at least 4 px clear of every rectangle (tested).
 */
export const PLACEHOLDERS = [
  { x: 6,   y: 8,   w: 196, h: 37, label: 'NATIVE ICON ROW', note: 'drive, shake reduction, AF, WB, film icon (about 164-201)' },
  { x: 373, y: 10,  w: 19,  h: 30, label: 'BT', note: 'Bluetooth' },
  { x: 545, y: 5,   w: 170, h: 30, label: 'NATIVE TOP RIGHT', note: 'size, shots remaining, card' },
  { x: 603, y: 45,  w: 115, h: 31, label: 'NATIVE SNAP', note: 'snap distance, FS' },
  { x: 272, y: 384, w: 196, h: 42, label: 'LEVEL', note: 'level indicator' },
  { x: 19,  y: 438, w: 699, h: 39, label: 'NATIVE BOTTOM ROW (OWNER PHOTO, APPROX.)', note: 'Av, shutter, aperture, ISO, battery 668-717' },
];
export const PLACEHOLDER_SET_NAME = "live view (from the owner's photo, approximate)";

/**
 * Second set, from a web photo of a GR III in PLAYBACK (not live view, not the owner's camera): one text row
 * along the top (date, size, count, card) and one along the bottom (file number, exposure, battery). An
 * approximate indication only, scaled to 720x480. Used under the shot moment (post-shot review). The opaque
 * 44 px bands cover both rows completely at rest.
 */
export const REVIEW_PLACEHOLDERS = [
  { x: 0, y: 8, w: 720, h: 30, label: 'REVIEW SCREEN ROW (REFERENCE PHOTO, APPROX.)' },
  { x: 0, y: 440, w: 720, h: 30, label: 'REVIEW SCREEN ROW (REFERENCE PHOTO, APPROX.)' },
];
