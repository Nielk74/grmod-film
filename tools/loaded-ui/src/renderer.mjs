// SPDX-License-Identifier: GPL-2.0-only
// Loaded: reference renderer. One pure function of (moment, film, frame, roll, elapsed ms, options) fills
// the pixels of a fixed set of views. Integer arithmetic only per frame, no allocation per frame (the
// buffers are created once), no randomness except hash32 of integers. Designed to be ported line by line
// to freestanding C: every primitive is in surface.mjs, every easing in fixed.mjs.
//
// Ownership rule (tier 2): every element of a moment is drawn by exactly one view.
//   shot neg/bw/cine : bands = strips and edge print; full = the frame-line gap bar (rows 44..436 only)
//   shot slide       : bands = mount borders and corners; full = side borders
//   shot instant     : tier 1: bands = print borders + milk; tier 2: full = the WHOLE print, bands draw nothing
//   load             : top band = "<FILM> LOADED"; tier 1: bottom band = cassette + leader;
//                      tier 2: full = cassette + leader, bottom band = plain film rail
//   roll             : top band = title; bottom band = cassette + racing film + text; full = contact sheet (rows 44..436)
import { ONE, prog, lerp, inOut, outCubic, inCubic, outBack, outBounce, hash32 } from './fixed.mjs';
import { Surface, toRgba, rgba } from './surface.mjs';
import { FILMS, ROLL_LENGTH } from './films.mjs';
import { VIEWS, W, H, duration, PEEK_MS } from './plan.mjs';

// ---------------------------------------------------------------- palette (one shared 29 entry layout)
export const P = { T: 0, BLK: 1, GRY: 2, EDGE: 3, WHT: 4, PAPER: 5, MID: 6, INK: 7, PANEL: 8, BAND: 9, FINK: 10,
  CINK: 11, RED: 12, SHADE: 13, BAR: 14, MILK0: 15, MILK1: 16, HOLE: 17, DIG: 18, METL: 19, METD: 20, LEAD: 21,
  BEZ: 22, MSH: 23, ISH: 24, TA: 25, TB: 26, TC: 27, UNX: 28 };
export const PALETTE_SIZE = 29;
export const HOLE_RGBA = rgba(255, 244, 214), BAR_RGBA = rgba(6, 6, 6, 230);
const mix = (a, b, k) => a + (((b - a) * k) >> 8);
const c3 = (c, a = 255) => rgba(c[0], c[1], c[2], a);

export function fillPalette(pal, film, milkLo, milkHi) {
  pal.fill(0);
  pal[P.BLK] = rgba(14, 14, 14); pal[P.GRY] = rgba(48, 48, 50);
  pal[P.EDGE] = c3(film.edge); pal[P.WHT] = rgba(250, 248, 240); pal[P.PAPER] = rgba(236, 230, 214);
  pal[P.MID] = rgba(130, 130, 134); pal[P.INK] = rgba(28, 26, 24);
  pal[P.PANEL] = c3(film.panel); pal[P.BAND] = c3(film.band); pal[P.FINK] = c3(film.ink); pal[P.CINK] = c3(film.captionInk);
  pal[P.RED] = rgba(226, 40, 40); pal[P.SHADE] = rgba(0, 0, 0, 120); pal[P.BAR] = BAR_RGBA;
  pal[P.MILK0] = rgba(238, 236, 228, milkLo); pal[P.MILK1] = rgba(238, 236, 228, milkHi);
  pal[P.HOLE] = HOLE_RGBA; pal[P.DIG] = rgba(255, 255, 255);
  pal[P.METL] = rgba(196, 198, 204); pal[P.METD] = rgba(104, 106, 114);
  pal[P.LEAD] = film.kind === 'neg' || film.kind === 'cine' ? rgba(128, 74, 36) : rgba(78, 78, 80);
  pal[P.BEZ] = rgba(176, 176, 182); pal[P.MSH] = rgba(186, 180, 164); pal[P.ISH] = rgba(212, 208, 196);
  const b = film.band;
  pal[P.TA] = rgba(mix(214, b[0], 40), mix(208, b[1], 40), mix(196, b[2], 40));
  pal[P.TB] = rgba(mix(150, b[0], 50), mix(146, b[1], 50), mix(138, b[2], 50));
  pal[P.TC] = rgba(mix(84, film.panel[0], 50), mix(82, film.panel[1], 50), mix(80, film.panel[2], 50));
  pal[P.UNX] = rgba(62, 62, 70);
}

// ---------------------------------------------------------------- film geometry and timelines (ms, px)
// One screen width is one frame: 8 perforations (pitch 90) of 44 x 20 px, backlit cream, fully opaque.
export const CELL = 720, PITCH = 90, HOLE_W = 44, HOLE_H = 20, HOLE_X0 = 23;
const CINE_PITCH = 45, CINE_HW = 26, CINE_HH = 16; // cine: 16 smaller holes per frame
const ROLL_WIN = { neg: [560, 860], bw: [560, 860], cine: [620, 920], slide: [520, 760], instant: [420, 720] };
const LOAD_ROLL = [1450, 1750];
const REWIND = [300, 2700];
const REST_CELL = 64;           // film cell the just-shot frame occupies at rest

function slideOffset(t, inEnd, outA, outB) {
  if (t < inEnd) return (44 * (ONE - outCubic(prog(t, 0, inEnd)))) >> 10;
  if (t >= outA) return (44 * inCubic(prog(t, outA, outB))) >> 10;
  return 0;
}
/** Film advance (px): back-step, then exactly one frame (720 px) with overshoot and settle. */
function negAdvance(t, last) {
  if (t < 260) return 0;
  if (t < 380) return -((24 * outCubic(prog(t, 260, 380))) >> 10);
  if (last) { // frame 36: the lever locks, the strip jerks and springs back
    if (t < 480) return lerp(-24, 30, inOut(prog(t, 380, 480)));
    if (t < 640) return lerp(30, 0, outCubic(prog(t, 480, 640)));
    return 0;
  }
  if (t < 940) return lerp(-24, 732, inOut(prog(t, 380, 940)));
  if (t < 1040) return lerp(732, CELL, outCubic(prog(t, 940, 1040)));
  return CELL;
}
/** Cine: the claw pulls the film down in four stepped pulses (one per quarter frame). */
function cineAdvance(t, last) {
  if (t < 260) return 0;
  if (t < 380) return -((24 * outCubic(prog(t, 260, 380))) >> 10);
  if (last) return negAdvance(t, true);
  if (t >= 930) return CELL;
  const k = ((t - 380) / 150) | 0, within = t - 380 - k * 150;
  return -24 + 186 * k + ((186 * inOut(prog(within, 0, 100))) >> 10);
}
const advance = (kind, t, last) => (kind === 'cine' ? cineAdvance(t, last) : negAdvance(t, last));
/** Pixels the film moves per 33 ms frame; above a third of the pitch the holes are smeared into a rail. */
function smearFor(v, pitch, cap) { return v > pitch / 3 ? (v > cap ? cap : v) : 0; }

// ---------------------------------------------------------------- film strip pieces
function holeRow(s, y, x0, pitch, scroll, hw, hh, r, smear) {
  const m = scroll % pitch;
  for (let x = x0 - m - pitch; x < W; x += pitch) s.rrect(x, y, hw + smear, hh, r, P.HOLE);
}
function bars(s, n, film, x, y, h, count) {
  for (let i = 0; i < count; i++) {
    const w = 2 + (hash32(film.index * 4099 + n, i) % 3);
    s.rect(x, y, w, h, P.EDGE);
    x += w + 2;
  }
  return x;
}
/** Edge print of one frame cell (cx = cell origin on screen). Drawn once per frame width. */
function printCell(s, top, film, n, cx, cine) {
  const ty = top ? 3 : 27;
  if (!cine) {
    if (top) { s.text(film.label, cx + 16, ty, 2, P.EDGE); s.text('>', cx + 16 + s.textWidth(film.label, 2) + 20, ty, 2, P.EDGE); }
    else {
      s.num(n, cx + 16, ty, 2, P.EDGE);
      const w = s.num(n, cx + 360, ty, 2, P.EDGE);
      s.text('A', cx + 360 + w + 6, ty, 2, P.EDGE);
      s.text(film.code, cx + 560, ty, 2, P.EDGE);
    }
  } else if (top) { // keycode: stock code, roll id, footage + frame, barcode
    let x = cx + 16;
    s.text(film.code, x, ty, 2, P.EDGE); x += s.textWidth(film.code, 2) + 14;
    x += s.num(1000 + (hash32(film.index, 7) % 9000), x, ty, 2, P.EDGE) + 14;
    x += s.num(n * 16 + 4, x, ty, 2, P.EDGE, 4) + 6;
    s.text('+', x, ty, 2, P.EDGE); x += 14;
    x += s.num((n * 5) % 16, x, ty, 2, P.EDGE, 2) + 16;
    bars(s, n, film, x, ty, 14, 16);
  } else {
    const w = s.num(n, cx + 16, ty, 2, P.EDGE);
    s.text('>', cx + 16 + w + 12, ty, 2, P.EDGE);
    bars(s, n + 99, film, cx + 360, ty, 14, 22);
    s.text(film.code, cx + 600, ty, 2, P.EDGE);
  }
}
/** Negative / b&w / cine strip band: black rebate, cream backlit holes, edge print. */
function drawStripBand(s, top, film, frame, adv, vel) {
  const cine = film.kind === 'cine', scroll = CELL * REST_CELL + adv;
  const pitch = cine ? CINE_PITCH : PITCH, smear = smearFor(vel, pitch, cine ? 36 : 66);
  s.rect(0, 0, W, 44, P.BLK);
  s.rect(0, top ? 42 : 0, W, 2, P.GRY);
  if (cine) s.rect(0, top ? 39 : 3, W, 2, P.EDGE);
  if (cine) holeRow(s, top ? 20 : 8, 10, pitch, scroll, CINE_HW, CINE_HH, 3, smear);
  else holeRow(s, top ? 19 : 5, HOLE_X0, pitch, scroll, HOLE_W, HOLE_H, 6, smear);
  const ghosts = smear ? (smear >> 2) + 1 : 1, step = 4; // fast: the print streaks instead of jumping
  for (let ci = (scroll / CELL) | 0; ci * CELL - scroll < W; ci++) {
    const cx = ci * CELL - scroll, n = frame + ci - REST_CELL;
    if (cx + CELL < 0 || n < 1 || n > ROLL_LENGTH) continue;
    for (let g = 0; g < ghosts; g++) printCell(s, top, film, n, cx + g * step, cine);
  }
}

/** A slide mount: card border; the window's rounded corners are cut into the band's inner edge. */
function drawMountBand(s, top, film, frame, date) {
  if (top) {
    s.rect(0, 0, W, 30, P.PAPER);
    s.rect(0, 0, W, 4, P.BAND);
    s.rect(0, 28, W, 2, P.MSH);
    s.rect(14, 30, W - 28, 3, P.SHADE);                       // paper edge shadow on the picture
    s.rect(0, 30, 14, 14, P.PAPER); s.disc(14, 44, 14, P.T);
    s.rect(W - 14, 30, 14, 14, P.PAPER); s.disc(W - 15, 44, 14, P.T);
    s.text(film.label, 24, 6, 3, P.INK);
    s.num(frame, W - 24 - s.numWidth(frame, 3), 6, 3, P.RED);
  } else {
    s.rect(0, 14, W, 30, P.PAPER);
    s.rect(0, 40, W, 4, P.BAND);
    s.rect(0, 14, W, 2, P.MSH);
    s.rect(14, 11, W - 28, 3, P.SHADE);
    s.rect(0, 0, 14, 14, P.PAPER); s.disc(14, 0, 14, P.T);
    s.rect(W - 14, 0, 14, 14, P.PAPER); s.disc(W - 15, 0, 14, P.T);
    let x = 24 + s.num(frame, 24, 17, 3, P.INK) + 24;
    // printed date-style stamp: month (0..11) and two-digit year come from the caller
    for (let i = 0; i < 3; i++) { s.glyph(MONTHS.charCodeAt(date.month * 3 + i), x, 17, 3, P.RED); x += 18; }
    s.num(date.year, x + 18, 17, 3, P.RED, 2);
    s.text(film.caption, W - 24 - s.textWidth(film.caption, 2), 20, 2, P.INK);
  }
}

export const DEFAULT_DATE = { month: 10, year: 26 }; // NOV 26 unless the caller passes the real date
const MONTHS = 'JANFEBMARAPRMAYJUNJULAUGSEPOCTNOVDEC';

// ---------------------------------------------------------------- instant print
const mlv = { lo: 0, hi: 0, frac: 0 };
function milk(t) { const a = (236 * (ONE - inOut(prog(t, 160, 1560)))) >> 10; mlv.lo = a & ~31; mlv.hi = mlv.lo + 32 > 255 ? 255 : mlv.lo + 32; mlv.frac = (a & 31) >> 1; }
function drawInstantBand(s, top) { // tier 1 only: white print borders, 44 px, over the review's info rows (y 8-38 and 440-470)
  if (top) { s.rect(0, 0, W, 44, P.WHT); s.rect(0, 42, W, 2, P.ISH); }
  else { s.rect(0, 0, W, 44, P.WHT); s.rect(0, 0, W, 2, P.ISH); s.text('INSTANT', 24, 12, 3, P.INK); }
}
/** Tier 2: the whole print as one object, moved by py (rise from below, eject upward). */
function drawInstantPrint(s, py) {
  s.oy = py;
  s.rect(0, 0, W, 44, P.WHT); s.rect(0, 380, W, 100, P.WHT);       // top border covers the review's top row; thick bottom
  s.rect(0, 0, 22, H, P.WHT); s.rect(W - 22, 0, 22, H, P.WHT);
  s.rect(22, 44, W - 44, 2, P.ISH); s.rect(22, 378, W - 44, 2, P.ISH);
  s.rect(22, 44, 2, 336, P.ISH); s.rect(W - 24, 44, 2, 336, P.ISH);
  s.text('INSTANT', 40, 412, 3, P.INK);                             // the counter sits in this border (no second number)
  s.ditherRect(24, 46, W - 48, 332, mlv.frac, P.MILK0, P.MILK1);
  s.oy = 0;
}

// ---------------------------------------------------------------- cassettes and leader
const CASSETTE_W = 146;
/** 35mm cassette lying on its side, filling the band height: spool knob, label in the film colours, felt lip. */
function miniCassette(s, x, film) {
  s.rect(x, 14, 10, 14, P.METD); s.rect(x, 14, 10, 3, P.METL);       // spool knob
  s.rect(x + 10, 2, 8, 40, P.METL); s.rect(x + 17, 2, 1, 40, P.METD); // left cap
  s.rect(x + 18, 2, 110, 40, P.PANEL);                               // label
  s.rect(x + 18, 2, 110, 18, P.BAND);
  s.text(film.caption, x + 18 + ((110 - s.textWidth(film.caption, 2)) >> 1), 4, 2, P.CINK);
  s.text(film.code, x + 18 + ((110 - s.textWidth(film.code, 2)) >> 1), 25, 2, P.FINK);
  s.rect(x + 18, 40, 110, 2, P.BLK);
  s.rect(x + 128, 2, 8, 40, P.METL); s.rect(x + 128, 2, 1, 40, P.METD); // right cap
  s.rect(x + 136, 6, 10, 32, P.METD);                                // felt lip
  s.rect(x + 142, 18, 4, 8, P.BLK);                                  // slot the film leaves through
}
/** Upright cassette (tier 2, centre of the screen) with its slot on the right at ty + 134 .. 146. */
function bigCassette(s, cx, ty, film) {
  s.rect(cx - 12, ty, 24, 14, P.METD); s.rect(cx - 8, ty, 16, 4, P.METL);
  s.rrect(cx - 62, ty + 12, 124, 18, 6, P.METL); s.rect(cx - 62, ty + 26, 124, 4, P.METD);
  s.rect(cx - 58, ty + 30, 116, 100, P.BLK);
  s.rect(cx - 56, ty + 30, 112, 100, P.PANEL);
  s.rect(cx - 56, ty + 30, 112, 26, P.BAND);
  s.text(film.caption, cx - (s.textWidth(film.caption, 2) >> 1), ty + 36, 2, P.CINK);
  const sc = film.code.length > 3 ? 4 : 5;
  s.text(film.code, cx - (s.textWidth(film.code, sc) >> 1), ty + 66, sc, P.FINK);
  s.rect(cx - 56, ty + 112, 112, 4, P.FINK);
  s.rrect(cx - 62, ty + 128, 124, 18, 6, P.METD); s.rect(cx - 62, ty + 128, 124, 4, P.BLK);
  s.rect(cx + 56, ty + 62, 10, 36, P.METD); s.rect(cx + 62, ty + 72, 4, 16, P.BLK);   // the felt slot, mid height
}
/** Tall leader (35mm film is nearly as tall as its cassette): 98 px, 8 holes per 720 px in two rows, edge print between. */
function drawBigLeader(s, film, startX, endX, smear) {
  for (let r = 0; r < 98; r++) {
    const d = r < 49 ? r : 97 - r, c = d < 28 ? (28 - d) * 2 : 0; // tongue: the corners taper
    if (endX - c > startX) s.rect(startX, r, endX - c - startX, 1, P.LEAD);
  }
  for (let x = endX - 84; x > startX + 8; x -= PITCH) { s.rrect(x, 8, HOLE_W + smear, 22, 6, P.HOLE); s.rrect(x, 68, HOLE_W + smear, 22, 6, P.HOLE); }
  if (endX - 420 > startX + 8) s.text(film.label, endX - 420, 39, 3, P.EDGE);
}
/** Film leader between startX and the tip at endX, drawn in 44 px band layout (holes y 5, edge print y 27). */
function drawLeader(s, film, startX, endX, smear, label) {
  for (let r = 0; r < 42; r++) { // tongue: chamfered corners, like a real leader
    const c = r < 10 ? (10 - r) * 3 : r > 31 ? (r - 31) * 3 : 0;
    if (endX - c > startX) s.rect(startX, 1 + r, endX - c - startX, 1, P.LEAD);
  }
  for (let x = endX - 84; x > startX + 8; x -= PITCH) s.rrect(x, 5, HOLE_W + smear, HOLE_H, 6, P.HOLE);
  if (label && endX - 520 > startX + 8) s.text(film.label, endX - 520, 27, 2, P.EDGE);
}

// ---------------------------------------------------------------- counter and tab (furniture)
const WHEEL_PITCH = 46;
function drawWheel(s, wx, ca, cb, e, dir) {
  s.clip(wx, 4, 30, 40);
  s.rect(wx, 4, 30, 40, P.BLK);
  const base = 7;
  if (ca === cb || e === 0) s.big(ca, wx + 4, base, 3, P.DIG);
  else {
    const off = (WHEEL_PITCH * e) >> 10;
    if (dir > 0) { s.big(ca, wx + 4, base - off, 3, P.DIG); s.big(cb, wx + 4, base + WHEEL_PITCH - off, 3, P.DIG); }
    else { s.big(ca, wx + 4, base + off, 3, P.DIG); s.big(cb, wx + 4, base - WHEEL_PITCH + off, 3, P.DIG); }
  }
  s.rect(wx, 4, 30, 3, P.SHADE); s.rect(wx, 41, 30, 3, P.SHADE);  // only outside the digit's rest rows 7..39
  s.unclip();
}
const tens = v => (v === 255 || v < 10 ? 10 : (v / 10) | 0);
const ones = v => (v === 255 ? 11 : v % 10);
/** Mechanical counter: two wheels; a wheel that changes rolls vertically, one that does not stays. */
function drawCounter(s, cs) {
  s.rrect(0, 0, 84, 48, 6, P.BEZ);
  s.rrect(2, 2, 80, 44, 5, P.BLK);
  const e = cs.linear ? cs.p : inOut(cs.p);
  drawWheel(s, 9, tens(cs.a), tens(cs.b), e, cs.dir);
  drawWheel(s, 45, ones(cs.a), ones(cs.b), e, cs.dir);
}
/** The memo holder: the torn film-box flap clipped to the camera back, in the loaded film's colours. */
function drawTab(s, film) {
  s.rect(0, 6, 10, 44, P.METD);
  s.disc(5, 14, 2, P.METL); s.disc(5, 42, 2, P.METL);
  s.rrect(8, 2, 120, 52, 8, P.BLK);
  s.rrect(10, 4, 116, 48, 6, P.PANEL);
  s.rrect(10, 4, 116, 19, 6, P.BAND); s.rect(10, 14, 116, 9, P.BAND);
  s.text(film.caption, 68 - (s.textWidth(film.caption, 2) >> 1), 6, 2, P.CINK);
  s.text(film.code, 68 - (s.textWidth(film.code, 4) >> 1), 24, 4, P.FINK);
  s.triBR(108, 34, 14, P.PAPER); s.triBR(108, 34, 3, P.GRY); // folded corner
}

// ---------------------------------------------------------------- contact sheet (tier 2), clear of the counter
export const SHEET = { stripX: 44, stripW: 632, stripH: 70, stripY0: 56, stripGap: 8, fw: 64, fh: 42, fx0: 56, fgap: 4 };
export function frameXY(i, out) {
  const r = (i / 9) | 0, c = i % 9;
  out[0] = SHEET.fx0 + c * (SHEET.fw + SHEET.fgap);
  out[1] = SHEET.stripY0 + r * (SHEET.stripH + SHEET.stripGap) + 14;
}
function pseudoAngle(dx, dy) { // 0 at 12 o'clock, clockwise, 0..4095, monotone in the true angle
  const ax = dx < 0 ? -dx : dx, ay = dy < 0 ? -dy : dy, s = ax + ay;
  if (s === 0) return 0;
  if (dx >= 0 && dy < 0) return ((ax * 1024) / s) | 0;
  if (dx >= 0) return 1024 + (((ay * 1024) / s) | 0);
  if (dy >= 0) return 2048 + (((ax * 1024) / s) | 0);
  return 3072 + (((ay * 1024) / s) | 0);
}
const xy = new Int32Array(2);
/** Red grease pencil ring, drawn progressively (pcur up to ~4600: a second, slightly larger overlap pass). */
function greasePencil(s, cx, cy, roll, pcur) {
  const rx = 48, ry = 34;
  for (let y = cy - ry - 10; y <= cy + ry + 10; y++) for (let x = cx - rx - 10; x <= cx + rx + 10; x++) {
    const dx = x - cx, dy = y - cy, pa = pseudoAngle(dx, dy);
    const wob = (hash32(roll, pa >> 7) & 3) - 1;
    for (let pass = 0; pass < 2; pass++) {
      if (pass === 0 ? pa > pcur : pcur < 4096 || pa > pcur - 4096) continue;
      const ex = pass * 4 + wob, ox = rx + ex + 2, oy = ry + ex + 2, ix = rx + ex - 2, iy = ry + ex - 2;
      if (dx * dx * oy * oy + dy * dy * ox * ox <= ox * ox * oy * oy &&
          dx * dx * iy * iy + dy * dy * ix * ix > ix * ix * iy * iy) { s.px(x, y, P.RED); break; }
    }
  }
}
function drawSheet(s, roll, t, sheetOff, circled, filled) {
  s.oy = sheetOff;
  s.rect(0, 44, W, 392, P.PAPER);
  for (let r = 0; r < 4; r++) {
    const sy = SHEET.stripY0 + r * (SHEET.stripH + SHEET.stripGap);
    s.rrect(SHEET.stripX, sy, SHEET.stripW, SHEET.stripH, 4, P.BLK);
    for (let x = SHEET.stripX + 6; x < SHEET.stripX + SHEET.stripW - 12; x += 16) { s.rect(x, sy + 3, 8, 6, P.PAPER); s.rect(x, sy + 61, 8, 6, P.PAPER); }
  }
  for (let i = 0; i < 36; i++) {
    frameXY(i, xy);
    const tf = 480 + i * 22, x = xy[0], y = xy[1];
    filled[i] = t < tf ? 0 : t < tf + 70 ? 1 : 2;
    if (filled[i] === 0) { s.rect(x, y, SHEET.fw, SHEET.fh, P.UNX); continue; }
    if (filled[i] === 1) { s.rect(x, y, SHEET.fw, SHEET.fh, P.WHT); continue; }
    const hz = 14 + (hash32(roll * 64 + i, 3) % 14);            // plain tile: film-tinted sky, ground, dark foreground
    s.rect(x, y, SHEET.fw, hz, P.TA); s.rect(x, y + hz, SHEET.fw, SHEET.fh - hz, P.TB);
    s.rect(x, y + SHEET.fh - 9 - (hash32(i, roll) % 5), SHEET.fw, 14, P.TC);
    s.num(i + 1, x + ((SHEET.fw - s.numWidth(i + 1, 2)) >> 1), y + 14, 2, P.INK);
  }
  if (t >= 1500) {
    frameXY(circled, xy);
    greasePencil(s, xy[0] + (SHEET.fw >> 1), xy[1] + (SHEET.fh >> 1), roll, (4600 * inOut(prog(t, 1500, 2000))) >> 10);
  }
  s.oy = 0;
}
const sheetOffset = t => (t < 100 ? H : t < 460 ? lerp(H, 0, outCubic(prog(t, 100, 460))) : lerp(0, H, inCubic(prog(t, 2900, 3300))));

// ---------------------------------------------------------------- load and rewind timelines
const loadCassetteX = t => lerp(-170, 6, outBack(prog(t, 100, 640)));
const loadEnd = (t, cx) => lerp(cx + 140, 764, inOut(prog(t, 700, 1400)));
const rewindTip = t => (t < 2300 ? 764 : lerp(764, 150, inOut(prog(t, 2300, 2700))));
const rewindCassetteX = t => (t < 2700 ? 6 : t < 2780 ? 6 - ((8 * inOut(prog(t, 2700, 2780))) >> 10) : 6 - 8 + ((8 * outCubic(prog(t, 2780, 2900))) >> 10));

// ---------------------------------------------------------------- the renderer
export function createRenderer({ guard = 0 } = {}) {
  const pal = new Uint32Array(32);
  const views = VIEWS.map(v => ({ ...v, surface: new Surface(v.w, v.h, guard), rgba: new Uint32Array(v.w * v.h),
    active: false, dirty: false }));
  const byId = {}; for (const v of views) byId[v.id] = v;
  const cs = { a: 1, b: 1, p: 0, dir: 1, linear: 0 };
  const filled = new Uint8Array(36);

  /** Counter wheels: a -> b, progress p (Q10), direction. 255 stands for the "S" (start) mark. */
  function counterState(moment, film, frame, t) {
    cs.a = cs.b = frame; cs.p = 0; cs.dir = 1; cs.linear = 0;
    if (moment === 'shot') {
      const w = ROLL_WIN[film.kind];
      cs.b = frame >= ROLL_LENGTH ? frame : frame + 1;
      cs.p = frame >= ROLL_LENGTH ? 0 : prog(t, w[0], w[1]);
    } else if (moment === 'load') {
      cs.a = 255; cs.b = frame; cs.p = prog(t, LOAD_ROLL[0], LOAD_ROLL[1]);
    } else if (moment === 'roll') {
      const pos = ROLL_LENGTH * ONE - (((ROLL_LENGTH - 1) * inOut(prog(t, REWIND[0], REWIND[1]))) | 0);
      const n = pos >> 10, frac = pos & 1023;
      cs.dir = -1; cs.linear = 1;
      if (frac === 0) { cs.a = cs.b = n; cs.p = 0; } else { cs.a = n + 1; cs.b = n; cs.p = ONE - frac; }
    }
    if (cs.p >= ONE) { cs.a = cs.b; cs.p = 0; }
  }
  /** 0 = shown, 1024 = slid out of its view. Peek mode: in for 180 ms, out over the last 240 of 2000 ms. */
  function hideAmount(mode, t, active, peek) {
    if (mode !== 'peek') return 0;
    let pe = peek;
    if (pe < 0 && active) pe = t;
    if (pe < 0) return ONE;
    if (active && pe >= 180) return 0;
    if (pe < 180) return ONE - outCubic(prog(pe, 0, 180));
    if (pe < PEEK_MS - 240) return 0;
    if (pe < PEEK_MS) return inCubic(prog(pe, PEEK_MS - 240, PEEK_MS));
    return ONE;
  }
  /** The tab steps aside while a moment's art would cover it (tier 2 slide/instant/load/roll). */
  function tabAside(moment, film, tier, t, dur, active) {
    if (!active) return 0;
    if (moment === 'load') { // hand-off: the tab is out while the cassette is on screen, and slides in as it leaves
      if (t < 180) return outCubic(prog(t, 0, 180));
      if (t < 1950) return ONE;
      return ONE - outCubic(prog(t, 1950, dur));
    }
    if (tier !== 2) return 0;
    if (moment === 'shot' && film.kind !== 'slide' && film.kind !== 'instant') return 0;
    if (t < 180) return outCubic(prog(t, 0, 180));                 // slides out like a peek slides in, reversed
    const back = film.kind === 'instant' && moment === 'shot' ? 110 : 240; // instant: wait for the print to leave
    if (t >= dur - back) return ONE - outCubic(prog(t, dur - back, dur)); // and back in at the end, same easing as peek
    return ONE;
  }
  function finish(v, drawn) {
    if (!drawn) { if (v.dirty) { v.rgba.fill(0); v.dirty = false; } v.active = false; return; }
    toRgba(v.surface, pal, v.rgba); v.dirty = true; v.active = true;
  }

  /**
   * moment: 'live' | 'shot' | 'load' | 'roll' | 'none' (cancelled). elapsed in ms since the moment began.
   * options: tier (1|2), tabMode ('always'|'peek'), peekElapsed (ms since the last peek trigger, or -1),
   * thumbs (36 Uint32Array of 64x42 RGBA, or null), circled (frame index to circle, default from roll).
   * Returns the shared view array; `rgba` of an inactive view is all zero.
   */
  function render(moment, filmIndex, frame, roll, elapsed, options = {}) {
    const film = FILMS[filmIndex], tier = options.tier === 2 ? 2 : 1;
    const dur = duration(moment, film);
    const active = (moment === 'shot' || moment === 'load' || moment === 'roll') && elapsed >= 0 && elapsed < dur;
    const t = elapsed < 0 ? 0 : elapsed, last = frame >= ROLL_LENGTH, kind = film.kind;
    const date = options.date || DEFAULT_DATE;
    mlv.lo = 0; mlv.hi = 0; mlv.frac = 0;
    if (active && moment === 'shot' && kind === 'instant') milk(t);
    fillPalette(pal, film, mlv.lo, mlv.hi);

    let off = 0, ox = 0, adv = 0, vel = 0, py = 0, ej = 0;
    if (active) {
      if (moment === 'shot') {
        if (kind === 'neg' || kind === 'bw' || kind === 'cine') {
          off = slideOffset(t, 260, 1200, 1500); adv = advance(kind, t, last);
          vel = adv - advance(kind, t > 33 ? t - 33 : 0, last);
        } else if (kind === 'slide') {
          off = t < 230 ? (44 * (ONE - outBounce(prog(t, 0, 230)))) >> 10 : 0;
          ox = lerp(0, W, inCubic(prog(t, 900, 1250)));
        } else {
          off = t < 240 ? (44 * (ONE - outCubic(prog(t, 0, 240)))) >> 10 : 0;
          py = t < 1560 ? lerp(H, 0, outCubic(prog(t, 0, 260))) : -lerp(0, H, inCubic(prog(t, 1560, 1800)));
          ej = t < 1560 ? 0 : lerp(0, H, inCubic(prog(t, 1560, 1800)));   // tier 1: the two bands leave upward together
        }
      } else if (moment === 'load') off = slideOffset(t, 220, 1950, 2200);
      else off = slideOffset(t, 300, 3000, 3400);
    }
    counterState(moment, film, frame, t);
    // tab and counter have their own mode ('always' | 'peek') and their own peek clock
    const pk = options.peekElapsed === undefined ? -1 : options.peekElapsed;
    const tabPk = options.tabPeekElapsed === undefined ? pk : options.tabPeekElapsed;
    const cntPk = options.counterPeekElapsed === undefined ? pk : options.counterPeekElapsed;
    const cntMode = options.counterMode === undefined ? options.tabMode : options.counterMode;
    const hideCounter = hideAmount(cntMode, t, active, cntPk);
    const hideTab = Math.max(hideAmount(options.tabMode, t, active, tabPk), tabAside(moment, film, tier, t, dur, active));

    for (const v of views) {
      if (v.tier > tier) { finish(v, false); continue; }
      const s = v.surface;
      s.clear();
      if (v.role === 'furniture') {
        const h = v.id === 'tab' ? hideTab : hideCounter;
        if (h >= ONE) { finish(v, false); continue; }
        if (v.id === 'counter') { s.ox = (108 * h) >> 10; drawCounter(s, cs); }
        else { s.ox = -((132 * h) >> 10); drawTab(s, film); }
        s.ox = 0; finish(v, true); continue;
      }
      if (!active) { finish(v, false); continue; }
      if (v.id === 'full') drawFull(s, moment, film, frame, roll, t, off, ox, adv, vel, py, options);
      else {
        const top = v.id === 'top';
        if (moment === 'shot' && kind === 'instant' && tier === 2) { finish(v, false); continue; } // the full view owns the print
        if (moment === 'load' && tier === 2 && !top) { finish(v, false); continue; }                // the full view owns the cassette and film
        s.oy = (top ? -off : off) - ej; s.ox = ox;
        if (moment === 'shot') {
          if (kind === 'slide') drawMountBand(s, top, film, frame, date);
          else if (kind === 'instant') drawInstantBand(s, top);
          else drawStripBand(s, top, film, frame, adv, vel);
        } else if (moment === 'load') drawLoadBand(s, top, film, t, tier);
        else drawRollBand(s, top, film, roll, t);
        s.ox = 0; s.oy = 0;
      }
      finish(v, true);
      if (v.id === 'full' && moment === 'roll' && options.thumbs) blitThumbs(v, options.thumbs, t);
    }
    return views;
  }

  function chip(s, film) {
    s.rrect(14, 8, 46, 28, 4, P.PANEL); s.rect(14, 26, 46, 10, P.BAND);
    s.text(film.code.length > 3 ? film.code.slice(0, 3) : film.code, 14 + ((46 - s.textWidth(film.code.length > 3 ? film.code.slice(0, 3) : film.code, 2)) >> 1), 11, 2, P.FINK);
  }

  function drawLoadBand(s, top, film, t, tier) {
    s.rect(0, 0, W, 44, P.BLK);
    s.rect(0, top ? 42 : 0, W, 2, P.GRY);
    if (top) { // "<FILM> LOADED" at 3x; in tier 2 the line stands alone (no chip)
      if (tier === 1) chip(s, film);
      const full = film.label.length, shown = ((t - 600) / 26) | 0; // letters appear one by one
      let x = tier === 1 ? 76 : 24;
      for (let i = 0; i < full + 7 && i < shown; i++) {
        if (i < full) s.glyph(film.label.charCodeAt(i), x, 11, 3, P.WHT);
        else if (i > full) s.glyph('LOADED'.charCodeAt(i - full - 1), x, 11, 3, P.EDGE);
        x += 18;
      }
      return;
    }
    // tier 1 bottom: the cassette slides in and bounces, then pulls the film leader across the band
    const cx = loadCassetteX(t), endX = loadEnd(t, cx);
    const sm = t < 700 ? 0 : smearFor(endX - loadEnd(t - 33 > 0 ? t - 33 : 0, cx), PITCH, 60);
    if (t >= 700) drawLeader(s, film, cx + 140, endX, sm, true);
    miniCassette(s, cx, film);
  }

  function drawRollBand(s, top, film, roll, t) {
    s.rect(0, 0, W, 44, P.BLK);
    s.rect(0, top ? 42 : 0, W, 2, P.GRY);
    if (top) { // all the text lives here, swapping in place: title, count, rewinding, done (3x)
      chip(s, film);
      if (t < 1000) {
        let x = 76; s.text('ROLL', x, 11, 3, P.EDGE); x += 5 * 18;
        x += s.num(roll, x, 11, 3, P.EDGE) + 36;
        s.text(film.label, x, 11, 3, P.WHT);
      } else if (t < 1800) {
        const w = s.num(ROLL_LENGTH, 76, 11, 3, P.EDGE);
        s.text('FRAMES EXPOSED.', 76 + w + 18, 11, 3, P.WHT);
      } else if (t < 2700) s.text('REWINDING.', 76, 11, 3, P.WHT);
      else s.text('FILM REWOUND.', 76, 11, 3, P.EDGE);
      return;
    }
    // bottom: the whole band is the film racing back into the cassette
    const cx = rewindCassetteX(t), tip = rewindTip(t), racing = t >= REWIND[0] && t < 2700;
    const n = ROLL_LENGTH - (((ROLL_LENGTH - 1) * inOut(prog(t, REWIND[0], REWIND[1]))) >> 10);
    if (tip > cx + 140) {
      for (let r = 0; r < 42; r++) { // film body; tail end chamfered
        const c = r < 10 ? (10 - r) * 3 : r > 31 ? (r - 31) * 3 : 0;
        s.rect(cx + 140, 1 + r, tip - c - cx - 140, 1, P.LEAD);
      }
      if (racing) { // cream rail with dark dashes streaming into the cassette (28 px per tick, never aliasing)
        s.rrect(cx + 146, 3, tip - cx - 150, 16, 6, P.HOLE);
        const sh = ((t * 28) / 33 | 0) % PITCH;
        for (let x = cx + 146 - sh; x < tip; x += PITCH) s.rect(x, 3, 16, 16, P.LEAD);
      } else if (t < REWIND[0]) holeRow(s, 3, HOLE_X0 + 160, PITCH, 0, HOLE_W, 17, 6, 0);
      // edge print: the frame number counting down at 3x, repeated along the film, with streaks between
      for (let g = 0; g < 3; g++) { const x = 200 + g * 190; if (x + 40 < tip) s.num(n, x, 21, 3, P.EDGE); }
      if (racing) { s.clip(cx + 140, 0, tip - cx - 140, 44); for (let i = 0; i < 6; i++) s.rect(190 + (hash32(i, (t / 66) | 0) % 480), 24 + (i % 3) * 7, 30 + (hash32(i, 9) % 60), 2, P.EDGE); s.unclip(); }
    }
    miniCassette(s, cx, film);
  }

  function drawFull(s, moment, film, frame, roll, t, off, ox, adv, vel, py, options) {
    const kind = film.kind;
    if (moment === 'shot') {
      if (kind === 'neg' || kind === 'bw' || kind === 'cine') { // the frame gap travels with the strip
        s.clip(0, 44, W, 392);
        const gw = (kind === 'cine' ? 32 : 40), w = t < 1000 ? gw : (gw * (ONE - inCubic(prog(t, 1000, 1100)))) >> 10;
        const x = CELL - adv;
        if (w > 0 && x < W && t >= 260) { s.rect(x - 2, 44, w + 4, 392, P.GRY); s.rect(x, 44, w, 392, P.BAR); }
        s.unclip();
      } else if (kind === 'slide') { // side borders, between the two bands
        s.clip(0, 44, W, 392);
        s.rect(ox, 0, 8, H, P.PAPER); s.rect(ox + 8, 0, 2, H, P.MSH);
        s.rect(W - 8 + ox, 0, 8, H, P.PAPER); s.rect(W - 10 + ox, 0, 2, H, P.MSH);
        s.unclip();
      } else drawInstantPrint(s, py);
    } else if (moment === 'load') { // the cassette drops in, bounces, the leader pulls out of it across the screen
      s.clip(0, 44, W, 392);
      const ty = t < 700 ? lerp(-190, 130, outBounce(prog(t, 0, 700))) : 130;
      s.ox = -lerp(0, 1000, inCubic(prog(t, 1900, 2200)));          // cassette and film slide away to the left together
      if (t < 700) s.rrect(88, 280, 124, 10, 5, P.SHADE);
      if (t >= 700) {
        const endX = lerp(212, 764, inOut(prog(t, 800, 1500)));
        const sm = t < 800 ? 0 : smearFor(endX - lerp(212, 764, inOut(prog(t - 33 > 800 ? t - 33 : 800, 800, 1500))), PITCH, 60);
        s.oy = 130 + 31;
        drawBigLeader(s, film, 212, endX, sm);
        s.oy = 0;
      }
      bigCassette(s, 150, ty, film);
      s.ox = 0; s.unclip();
    } else if (moment === 'roll') {
      s.clip(0, 44, W, 392);
      const circled = options.circled === undefined ? hash32(roll, 5) % 36 : options.circled;
      drawSheet(s, roll, t, sheetOffset(t), circled, filled);
      s.unclip();
    }
  }

  function blitThumbs(v, thumbs, t) {
    const so = sheetOffset(t);
    for (let i = 0; i < 36; i++) {
      if (filled[i] !== 2 || !thumbs[i]) continue;
      frameXY(i, xy);
      for (let r = 0; r < SHEET.fh; r++) {
        const yy = xy[1] + r + so;
        if (yy < 44 || yy >= 436) continue;
        const o = yy * W + xy[0], src = r * SHEET.fw;
        for (let c = 0; c < SHEET.fw; c++) v.rgba[o + c] = thumbs[i][src + c];
      }
    }
  }

  return { views, byId, render, guardsIntact: () => views.every(v => v.surface.guardIntact()), palette: () => pal };
}

/** Geometry and timing constants shared with the native port (native/loaded_data.h is generated from these). */
export const GEOM = { CELL, PITCH, HOLE_W, HOLE_H, HOLE_X0, CINE_PITCH, CINE_HW, CINE_HH, REST_CELL, ROLL_WIN, LOAD_ROLL, REWIND, SHEET, DEFAULT_DATE };
