// SPDX-License-Identifier: GPL-2.0-only
// Loaded: reference renderer. One pure function of (moment, film, frame, roll, elapsed ms, options) fills
// the pixels of a fixed set of views. Integer arithmetic only per frame, no allocation per frame (the
// buffers are created once), no randomness except hash32 of integers. Designed to be ported line by line
// to freestanding C: every primitive is in surface.mjs, every easing in fixed.mjs.
import { ONE, prog, lerp, inOut, outCubic, inCubic, outBack, outBounce, hash32 } from './fixed.mjs';
import { Surface, toRgba, rgba } from './surface.mjs';
import { FILMS, ROLL_LENGTH } from './films.mjs';
import { VIEWS, W, H, duration, PEEK_MS } from './plan.mjs';

// ---------------------------------------------------------------- palette (one shared 29 entry layout)
export const P = { T: 0, BLK: 1, GRY: 2, EDGE: 3, WHT: 4, PAPER: 5, MID: 6, INK: 7, PANEL: 8, BAND: 9, FINK: 10,
  CINK: 11, RED: 12, SHADE: 13, BAR: 14, MILK0: 15, METL: 19, METD: 20, LEAD: 21, BEZ: 22, MSH: 23, ISH: 24,
  TA: 25, TB: 26, TC: 27, UNX: 28 };
export const PALETTE_SIZE = 29;
const mix = (a, b, k) => a + (((b - a) * k) >> 8);
const c3 = (c, a = 255) => rgba(c[0], c[1], c[2], a);

export function fillPalette(pal, film, milk) {
  pal.fill(0);
  pal[P.BLK] = rgba(14, 14, 14); pal[P.GRY] = rgba(48, 48, 50);
  pal[P.EDGE] = c3(film.edge); pal[P.WHT] = rgba(250, 248, 240); pal[P.PAPER] = rgba(236, 230, 214);
  pal[P.MID] = rgba(130, 130, 134); pal[P.INK] = rgba(28, 26, 24);
  pal[P.PANEL] = c3(film.panel); pal[P.BAND] = c3(film.band); pal[P.FINK] = c3(film.ink); pal[P.CINK] = c3(film.captionInk);
  pal[P.RED] = rgba(226, 40, 40); pal[P.SHADE] = rgba(0, 0, 0, 120); pal[P.BAR] = rgba(6, 6, 6, 230);
  for (let k = 0; k < 4; k++) pal[P.MILK0 + k] = rgba(238, 236, 228, milk[k]);
  pal[P.METL] = rgba(196, 198, 204); pal[P.METD] = rgba(104, 106, 114);
  pal[P.LEAD] = film.kind === 'neg' || film.kind === 'cine' ? rgba(128, 74, 36) : rgba(78, 78, 80);
  pal[P.BEZ] = rgba(176, 176, 182); pal[P.MSH] = rgba(186, 180, 164); pal[P.ISH] = rgba(212, 208, 196);
  const b = film.band;
  pal[P.TA] = rgba(mix(214, b[0], 40), mix(208, b[1], 40), mix(196, b[2], 40));
  pal[P.TB] = rgba(mix(150, b[0], 50), mix(146, b[1], 50), mix(138, b[2], 50));
  pal[P.TC] = rgba(mix(84, film.panel[0], 50), mix(82, film.panel[1], 50), mix(80, film.panel[2], 50));
  pal[P.UNX] = rgba(62, 62, 70);
}

// ---------------------------------------------------------------- timelines (ms)
const ROLL_WIN = { neg: [560, 860], bw: [560, 860], cine: [620, 920], slide: [520, 760], instant: [420, 720] };
const LOAD_ROLL = [1450, 1750];
const REWIND = [300, 2700];
const REST_CELL = 64;           // film cell the just-shot frame occupies at rest
const NEG_CELL = 304, NEG_PITCH = 38, CINE_CELL = 384, CINE_PITCH = 24;

function slideOffset(t, inEnd, outA, outB) {
  if (t < inEnd) return (44 * (ONE - outCubic(prog(t, 0, inEnd)))) >> 10;
  if (t >= outA) return (44 * inCubic(prog(t, outA, outB))) >> 10;
  return 0;
}

/** Film advance (px) during a shot: anticipation back-step, ease in-out advance, small settle. */
function negAdvance(t, last) {
  if (t < 260) return 0;
  if (t < 380) return -((16 * outCubic(prog(t, 260, 380))) >> 10);
  if (last) { // frame 36: the lever locks, the strip jerks and springs back
    if (t < 480) return lerp(-16, 24, inOut(prog(t, 380, 480)));
    if (t < 640) return lerp(24, 0, outCubic(prog(t, 480, 640)));
    return 0;
  }
  if (t < 900) return lerp(-16, 314, inOut(prog(t, 380, 900)));
  if (t < 1000) return lerp(314, NEG_CELL, outCubic(prog(t, 900, 1000)));
  return NEG_CELL;
}
/** Cine: the claw pulls the film down in four stepped pulses (one per 4-perforation frame). */
function cineAdvance(t, last) {
  if (t < 260) return 0;
  if (t < 380) return -((16 * outCubic(prog(t, 260, 380))) >> 10);
  if (last) return negAdvance(t, true);
  if (t >= 380 + 4 * 135) return CINE_CELL;
  const k = ((t - 380) / 135) | 0, within = t - 380 - k * 135;
  return -16 + 100 * k + ((100 * inOut(prog(within, 0, 90))) >> 10);
}

// ---------------------------------------------------------------- shared drawing pieces
function holes(s, top, pitch, hw, hh, r, scroll, colour) {
  const hy = top ? 22 : 6, m = scroll % pitch;
  for (let x = -m + 8 - pitch; x < W; x += pitch) s.rrect(x, hy, hw, hh, r, colour);
}
function bars(s, n, film, x, y, h, count) {
  for (let i = 0; i < count; i++) {
    const w = 2 + (hash32(film.index * 4099 + n, i) % 3);
    s.rect(x, y, w, h, P.EDGE);
    x += w + 2;
  }
  return x;
}

/** Negative / b&w / cine strip. Holes are transparent: the photo shows through them. */
function drawNegBand(s, top, film, frame, adv, cine) {
  const cell = cine ? CINE_CELL : NEG_CELL, scroll = cell * REST_CELL - 40 + adv;
  s.rect(0, 0, W, 44, P.BLK);
  s.rect(0, top ? 42 : 0, W, 2, P.GRY);
  if (cine) s.rect(0, top ? 39 : 3, W, 2, P.EDGE);
  holes(s, top, cine ? CINE_PITCH : NEG_PITCH, cine ? 12 : 26, 16, cine ? 3 : 4, scroll, P.T);
  const ty = top ? 6 : 24, nameW = s.textWidth(film.label, 2);
  for (let ci = (scroll / cell) | 0; ci * cell - scroll < W; ci++) {
    const cx = ci * cell - scroll, n = frame + ci - REST_CELL;
    if (cx + cell < 0 || n < 1 || n > ROLL_LENGTH) continue;
    if (!cine) {
      if (top) {
        s.text(film.label, cx + 14, ty, 2, P.EDGE);
        s.num(n, cx + 14 + nameW + 22, ty, 2, P.EDGE);
        s.text('>', cx + 14 + nameW + 22 + 36, ty, 2, P.EDGE);
      } else {
        s.num(n, cx + 14, ty, 2, P.EDGE);
        const w = s.num(n, cx + 152, ty, 2, P.EDGE);
        s.text('A', cx + 152 + w + 6, ty, 2, P.EDGE);
        s.text(film.code, cx + 240, ty, 2, P.EDGE);
      }
    } else if (top) { // keycode: stock code, roll id, footage + frame, barcode
      let x = cx + 14;
      s.text(film.code, x, ty, 2, P.EDGE); x += s.textWidth(film.code, 2) + 12;
      x += s.num(1000 + (hash32(film.index, 7) % 9000), x, ty, 2, P.EDGE) + 12;
      x += s.num(n * 16 + 4, x, ty, 2, P.EDGE, 4) + 6;
      s.text('+', x, ty, 2, P.EDGE); x += 14;
      x += s.num((n * 5) % 16, x, ty, 2, P.EDGE, 2) + 14;
      bars(s, n, film, x, ty, 14, 14);
    } else {
      const w = s.num(n, cx + 14, ty, 2, P.EDGE);
      s.text('>', cx + 14 + w + 10, ty, 2, P.EDGE);
      bars(s, n + 99, film, cx + 130, ty, 14, 20);
      s.text(film.code, cx + 300, ty, 2, P.EDGE);
    }
  }
}

/** A slide mount: card border, with the window's rounded corners cut into the band's inner edge. */
function drawMountBand(s, top, film, frame) {
  if (top) {
    s.rect(0, 0, W, 32, P.PAPER);
    s.rect(0, 0, W, 6, P.BAND);
    s.rect(0, 30, W, 2, P.MSH);
    s.rect(0, 32, 12, 12, P.PAPER); s.disc(12, 44, 12, P.T);
    s.rect(W - 12, 32, 12, 12, P.PAPER); s.disc(W - 13, 44, 12, P.T);
    s.text(film.label, 24, 11, 2, P.INK);
    s.num(frame, W - 24 - s.numWidth(frame, 2), 11, 2, P.INK);
  } else {
    s.rect(0, 12, W, 32, P.PAPER);
    s.rect(0, 38, W, 6, P.BAND);
    s.rect(0, 12, W, 2, P.MSH);
    s.rect(0, 0, 12, 12, P.PAPER); s.disc(12, 0, 12, P.T);
    s.rect(W - 12, 0, 12, 12, P.PAPER); s.disc(W - 13, 0, 12, P.T);
    const w = s.num(frame, 24, 15, 3, P.INK);
    s.text(film.caption, 24 + w + 20, 19, 2, P.INK);
    s.text(film.code, W - 24 - s.textWidth(film.code, 2), 19, 2, P.INK);
  }
}

function drawInstantBand(s, top, frame) {
  if (top) {
    s.rect(0, 0, W, 16, P.WHT);
    s.rect(0, 16, W, 2, P.ISH);
    s.rect(0, 18, W, 26, P.MILK0);
  } else {
    s.rect(0, 0, W, 44, P.WHT);
    s.rect(0, 0, W, 2, P.ISH);
    s.text('INSTANT', 24, 12, 3, P.INK);
    s.num(frame, W - 24 - s.numWidth(frame, 3), 12, 3, P.INK);
  }
}

// ---------------------------------------------------------------- canisters
function miniCanister(s, x, film, ribShift) {
  s.rrect(x, 6, 66, 34, 4, P.BLK);
  s.rect(x + 2, 8, 8, 30, P.METD);                      // spool-end cap
  s.rect(x + 10, 8, 46, 30, P.PANEL);                   // label in the film's colours
  s.rect(x + 10, 28, 46, 10, P.BAND);
  s.text(film.code, x + 10 + ((46 - s.textWidth(film.code, 2)) >> 1), 11, 2, P.FINK);
  s.rect(x + 56, 8, 8, 30, P.METL);                     // lip
  s.rect(x + 61, 16, 3, 14, P.BLK);                     // felt slot
  s.rect(x + 22, 1, 12, 5, P.METD); s.rect(x + 24, 1, 8, 2, P.METL); // knob
  for (let i = 0; i < 3; i++) s.rect(x + 3 + ((i * 3 + ribShift) % 6), 12, 1, 22, P.MID);
}

function bigCanister(s, cx, ty, film) {
  s.rect(cx - 12, ty, 24, 14, P.METD); s.rect(cx - 8, ty, 16, 4, P.METL);
  s.rrect(cx - 62, ty + 12, 124, 18, 6, P.METL); s.rect(cx - 62, ty + 26, 124, 4, P.METD);
  s.rect(cx - 58, ty + 30, 116, 124, P.BLK);
  s.rect(cx - 56, ty + 30, 112, 124, P.PANEL);
  s.rect(cx - 56, ty + 30, 112, 26, P.BAND);
  s.text(film.caption, cx - (s.textWidth(film.caption, 2) >> 1), ty + 36, 2, P.CINK);
  s.text(film.code, cx - (s.textWidth(film.code, 5) >> 1), ty + 78, 5, P.FINK);
  s.rect(cx - 56, ty + 130, 112, 4, P.FINK);
  s.rrect(cx - 62, ty + 152, 124, 18, 6, P.METD); s.rect(cx - 62, ty + 152, 124, 4, P.BLK);
  s.rect(cx + 58, ty + 134, 32, 12, P.BLK);             // the leader leaves through the felt slot
  s.rect(cx + 58, ty + 134, 32, 2, P.LEAD);
}

// ---------------------------------------------------------------- counter and tab (furniture)
const WHEEL_PITCH = 34;
function wheelGlyph(s, code, x, y) {
  if (code === 10) return;
  s.glyph(code === 11 ? 83 : 48 + code, x + 4, y, 4, P.WHT);
}
const tens = v => (v === 255 || v < 10 ? 10 : (v / 10) | 0);
const ones = v => (v === 255 ? 11 : v % 10);
function drawWheel(s, wx, ca, cb, e, dir) {
  s.clip(wx, 4, 28, 32);
  s.rect(wx, 4, 28, 32, P.BLK);
  const base = 6;
  if (ca === cb || e === 0) wheelGlyph(s, ca, wx, base);
  else {
    const off = (WHEEL_PITCH * e) >> 10;
    if (dir > 0) { wheelGlyph(s, ca, wx, base - off); wheelGlyph(s, cb, wx, base + WHEEL_PITCH - off); }
    else { wheelGlyph(s, ca, wx, base + off); wheelGlyph(s, cb, wx, base - WHEEL_PITCH + off); }
  }
  s.rect(wx, 4, 28, 6, P.SHADE); s.rect(wx, 30, 28, 6, P.SHADE); // the drum curves away
  s.unclip();
}
/** Mechanical counter: two wheels; a wheel that changes rolls vertically, one that does not stays. */
function drawCounter(s, cs) {
  s.rrect(0, 0, 72, 40, 6, P.BEZ);
  s.rrect(2, 2, 68, 36, 5, P.BLK);
  const e = cs.linear ? cs.p : inOut(cs.p);
  drawWheel(s, 7, tens(cs.a), tens(cs.b), e, cs.dir);
  drawWheel(s, 37, ones(cs.a), ones(cs.b), e, cs.dir);
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

// ---------------------------------------------------------------- contact sheet (tier 2)
export const SHEET = { stripX: 21, stripW: 678, stripH: 76, stripY0: 73, stripGap: 10, fw: 70, fh: 46, fx0: 29, fgap: 4 };
export function frameXY(i, out) {
  const r = (i / 9) | 0, c = i % 9;
  out[0] = SHEET.fx0 + c * (SHEET.fw + SHEET.fgap);
  out[1] = SHEET.stripY0 + r * (SHEET.stripH + SHEET.stripGap) + 15;
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
  const rx = 52, ry = 37;
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
  s.rect(0, 0, W, H, P.PAPER);
  for (let r = 0; r < 4; r++) {
    const sy = SHEET.stripY0 + r * (SHEET.stripH + SHEET.stripGap);
    s.rrect(SHEET.stripX, sy, SHEET.stripW, SHEET.stripH, 4, P.BLK);
    for (let x = SHEET.stripX + 6; x < SHEET.stripX + SHEET.stripW - 10; x += 16) { s.rect(x, sy + 4, 8, 6, P.PAPER); s.rect(x, sy + 66, 8, 6, P.PAPER); }
  }
  for (let i = 0; i < 36; i++) {
    frameXY(i, xy);
    const tf = 480 + i * 22, x = xy[0], y = xy[1];
    filled[i] = t < tf ? 0 : t < tf + 70 ? 1 : 2;
    if (filled[i] === 0) { s.rect(x, y, SHEET.fw, SHEET.fh, P.UNX); continue; }
    if (filled[i] === 1) { s.rect(x, y, SHEET.fw, SHEET.fh, P.WHT); continue; }
    const hz = 16 + (hash32(roll * 64 + i, 3) % 16);            // plain tile: sky, ground, dark foreground
    s.rect(x, y, SHEET.fw, hz, P.TA); s.rect(x, y + hz, SHEET.fw, SHEET.fh - hz, P.TB);
    s.rect(x, y + SHEET.fh - 10 - (hash32(i, roll) % 6), SHEET.fw, 16, P.TC);
    s.num(i + 1, x + ((SHEET.fw - s.numWidth(i + 1, 2)) >> 1), y + 16, 2, P.INK);
  }
  if (t >= 1500) {
    frameXY(circled, xy);
    greasePencil(s, xy[0] + 35, xy[1] + 23, roll, (4600 * inOut(prog(t, 1500, 2000))) >> 10);
  }
  s.oy = 0;
}
const sheetOffset = t => (t < 460 ? lerp(H, 0, outCubic(prog(t, 100, 460))) : lerp(0, H, inCubic(prog(t, 2900, 3300))));

// ---------------------------------------------------------------- the renderer
export function createRenderer({ guard = 0 } = {}) {
  const pal = new Uint32Array(32), milk = new Int32Array(4);
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
  function finish(v, drawn) {
    if (!drawn) { if (v.dirty) { v.rgba.fill(0); v.dirty = false; } v.active = false; return; }
    toRgba(v.surface, pal, v.rgba); v.dirty = true; v.active = true;
  }

  /**
   * moment: 'live' | 'shot' | 'load' | 'roll' | 'none' (cancelled). elapsed in ms since the moment began.
   * options: tier (1|2), tabMode ('always'|'peek'), peekElapsed (ms since the last peek trigger, or -1),
   * thumbs (36 Uint32Array of 70x46 RGBA, or null), circled (frame index to circle, default from roll).
   * Returns the shared view array; `rgba` of an inactive view is all zero.
   */
  function render(moment, filmIndex, frame, roll, elapsed, options = {}) {
    const film = FILMS[filmIndex], tier = options.tier === 2 ? 2 : 1;
    const dur = duration(moment, film);
    const active = (moment === 'shot' || moment === 'load' || moment === 'roll') && elapsed >= 0 && elapsed < dur;
    const t = elapsed < 0 ? 0 : elapsed, last = frame >= ROLL_LENGTH;
    for (let k = 0; k < 4; k++) milk[k] = 0;
    if (active && moment === 'shot' && film.kind === 'instant')
      for (let k = 0; k < 4; k++) milk[k] = (236 * (ONE - inOut(prog(t, 160 + k * 110, 1160 + k * 110)))) >> 10;
    fillPalette(pal, film, milk);

    let off = 0, ox = 0, adv = 0, dy = 0;
    if (active) {
      if (moment === 'shot') {
        const k = film.kind;
        if (k === 'neg' || k === 'bw') { off = slideOffset(t, 260, 1200, 1500); adv = negAdvance(t, last); }
        else if (k === 'cine') { off = slideOffset(t, 260, 1200, 1500); adv = cineAdvance(t, last); }
        else if (k === 'slide') {
          off = t < 230 ? (44 * (ONE - outBounce(prog(t, 0, 230)))) >> 10 : 0;
          ox = lerp(0, W, inCubic(prog(t, 900, 1250)));
        } else {
          off = t < 240 ? (44 * (ONE - outCubic(prog(t, 0, 240)))) >> 10 : 0;
          dy = lerp(0, H, inCubic(prog(t, 1560, 1800)));
        }
      } else if (moment === 'load') off = slideOffset(t, 220, 1950, 2200);
      else off = slideOffset(t, 300, 3000, 3400);
    }
    counterState(moment, film, frame, t);
    const hide = hideAmount(options.tabMode, t, active, options.peekElapsed === undefined ? -1 : options.peekElapsed);

    for (const v of views) {
      if (v.tier > tier) { finish(v, false); continue; }
      const s = v.surface;
      s.clear();
      if (v.role === 'furniture') {
        if (hide >= ONE) { finish(v, false); continue; }
        if (v.id === 'counter') { s.ox = (80 * hide) >> 10; drawCounter(s, cs); }
        else { s.ox = -((132 * hide) >> 10); drawTab(s, film); }
        s.ox = 0; finish(v, true); continue;
      }
      if (!active) { finish(v, false); continue; }
      if (v.id === 'full') drawFull(s, moment, film, roll, t, off, ox, dy, options);
      else {
        const top = v.id === 'top';
        s.oy = top ? -off - dy : off - dy; s.ox = ox;
        if (moment === 'shot') {
          const k = film.kind;
          if (k === 'slide') drawMountBand(s, top, film, frame);
          else if (k === 'instant') drawInstantBand(s, top, frame);
          else drawNegBand(s, top, film, frame, adv, k === 'cine');
        } else if (moment === 'load') drawLoadBand(s, top, film, t);
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
    s.text(film.code, 14 + ((46 - s.textWidth(film.code, 2)) >> 1), 11, 2, P.FINK);
  }

  function drawLoadBand(s, top, film, t) {
    s.rect(0, 0, W, 44, P.BLK);
    s.rect(0, top ? 42 : 0, W, 2, P.GRY);
    if (top) {
      chip(s, film);
      const full = film.label.length, shown = ((t - 600) / 26) | 0; // letters appear one by one
      let x = 76;
      for (let i = 0; i < full + 7 && i < shown; i++) {
        if (i < full) s.glyph(film.label.charCodeAt(i), x, 11, 3, P.WHT);
        else if (i > full) s.glyph('LOADED'.charCodeAt(i - full - 1), x, 11, 3, P.EDGE);
        x += 18;
      }
      return;
    }
    // bottom: the canister slides in and bounces, then pulls the film leader across the band
    const cx = lerp(-80, 8, outBack(prog(t, 200, 720)));
    const endX = lerp(cx + 70, 744, inOut(prog(t, 700, 1400)));
    if (endX > cx + 70) {
      for (let r = 0; r < 36; r++) { // tapered tip
        const d = r * 2 - 35, e = (((d < 0 ? -d : d) * 24) / 35) | 0;
        s.rect(cx + 60, 4 + r, endX - e - cx - 60, 1, P.LEAD);
      }
      for (let x = endX - 36; x > cx + 70; x -= NEG_PITCH) s.rrect(x, 6, 26, 16, 4, P.BLK);
      for (let j = 0; j < 3; j++) s.text(film.label, endX - 300 - j * 330, 24, 2, P.EDGE);
    }
    miniCanister(s, cx, film, (cx + 400) % 6);
  }

  function drawRollBand(s, top, film, roll, t) {
    s.rect(0, 0, W, 44, P.BLK);
    s.rect(0, top ? 42 : 0, W, 2, P.GRY);
    if (top) { // the roll summary in edge print
      chip(s, film);
      let x = 76; s.text('ROLL', x, 11, 3, P.EDGE); x += 5 * 18;
      x += s.num(roll, x, 11, 3, P.EDGE) + 36;
      s.text(film.label, x, 11, 3, P.WHT);
      return;
    }
    const e = inOut(prog(t, REWIND[0], REWIND[1])), scroll = (1368 * e) >> 10; // one hole per frame
    for (let x = 96 - (scroll % NEG_PITCH) - NEG_PITCH; x < W; x += NEG_PITCH) s.rrect(x, 6, 26, 16, 4, P.GRY);
    miniCanister(s, 8, film, (scroll >> 3) % 6);
    const w = s.num(ROLL_LENGTH, 96, 24, 2, P.EDGE);
    s.text('FRAMES EXPOSED. REWINDING.', 96 + w + 12, 24, 2, P.EDGE);
  }

  function drawFull(s, moment, film, roll, t, off, ox, dy, options) {
    if (moment === 'shot') {
      const k = film.kind;
      if (k === 'neg' || k === 'bw' || k === 'cine') { // dark frame line sweeping across the picture
        if (t >= 380 && t < 920) {
          const x = lerp(W + 40, -60, inOut(prog(t, 380, 920))), bw = k === 'cine' ? 10 : 18;
          s.rect(x - 2, 44, bw + 4, 392, P.GRY); s.rect(x, 44, bw, 392, P.BAR);
        }
      } else if (k === 'slide') { // the mount's side borders, between the two bands
        const y0 = 44 - off, y1 = 436 + off;
        s.rect(ox, y0, 8, y1 - y0, P.PAPER); s.rect(ox + 8, y0, 2, y1 - y0, P.MSH);
        s.rect(W - 8 + ox, y0, 8, y1 - y0, P.PAPER); s.rect(W - 10 + ox, y0, 2, y1 - y0, P.MSH);
      } else { // instant: side borders, the bottom border above its band, milk over the whole picture
        const oyT = -off - dy, oyB = off - dy, hgt = 392 + oyB - oyT;
        s.rect(0, 44 + oyT, 22, hgt, P.WHT); s.rect(W - 22, 44 + oyT, 22, hgt, P.WHT);
        s.rect(22, 44 + oyT, 2, hgt, P.ISH); s.rect(W - 24, 44 + oyT, 2, hgt, P.ISH);
        s.rect(0, 436 + oyB, W, 44, P.WHT); s.rect(0, 436 + oyB, W, 2, P.ISH);
        const a = [44, 120, 240, 360, 436];
        for (let q = 0; q < 4; q++) s.rect(24, a[q], W - 48, a[q + 1] - a[q], P.MILK0 + q);
      }
    } else if (moment === 'load') { // the canister drops in from above, bounces, then falls away
      if (t < 1750) {
        const ty = t < 700 ? lerp(-190, 150, outBounce(prog(t, 0, 700))) : lerp(150, 520, inCubic(prog(t, 1300, 1750)));
        if (t < 1300) s.rrect(300, 326, 120, 10, 5, P.SHADE);
        bigCanister(s, 360, ty, film);
      }
    } else if (moment === 'roll') {
      const circled = options.circled === undefined ? hash32(roll, 5) % 36 : options.circled;
      drawSheet(s, roll, t, t < 100 ? H : sheetOffset(t), circled, filled);
    }
  }

  function blitThumbs(v, thumbs, t) {
    const so = t < 100 ? H : sheetOffset(t);
    for (let i = 0; i < 36; i++) {
      if (filled[i] !== 2 || !thumbs[i]) continue;
      frameXY(i, xy);
      for (let r = 0; r < SHEET.fh; r++) {
        const yy = xy[1] + r + so;
        if (yy < 0 || yy >= H) continue;
        const o = yy * W + xy[0], src = r * SHEET.fw;
        for (let c = 0; c < SHEET.fw; c++) v.rgba[o + c] = thumbs[i][src + c];
      }
    }
  }

  return { views, byId, render, guardsIntact: () => views.every(v => v.surface.guardIntact()), palette: () => pal };
}
