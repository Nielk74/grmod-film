import test from 'node:test';
import assert from 'node:assert/strict';
import { createRenderer, HOLE_RGBA } from '../src/renderer.mjs';
import { FILMS } from '../src/films.mjs';
import { duration } from '../src/plan.mjs';

const MOVING = ['shot', 'load', 'roll'];
const idxOf = n => FILMS.findIndex(f => f.name === n);
const bandAt = (r, film, frame, t, tier = 1) => {
  const v = r.render('shot', film, frame, 12, t, { tier, tabMode: 'always' });
  return { top: v.find(x => x.id === 'top').rgba.slice(), bottom: v.find(x => x.id === 'bottom').rgba.slice() };
};

test('negative strip: exactly 8 opaque cream holes across one 720 px frame, 44 x 20, on every negative and b&w film', () => {
  const r = createRenderer();
  for (const f of FILMS.filter(x => x.kind === 'neg' || x.kind === 'bw')) {
    const { top, bottom } = bandAt(r, f.index, 17, 1100);
    for (const [band, y] of [[top, 28], [bottom, 14]]) {
      let runs = 0, prev = false;
      for (let x = 0; x < 720; x++) { const c = band[y * 720 + x] === HOLE_RGBA; if (c && !prev) runs++; prev = c; }
      assert.equal(runs, 8, f.name);
      let h = 0; for (let yy = 0; yy < 44; yy++) if (band[yy * 720 + 45] === HOLE_RGBA) h++;
      assert.equal(h, 20, f.name);
      assert.equal(band[y * 720 + 45] >>> 24, 255);
    }
  }
});

test('strips are fully opaque (holes included) on every neg, b&w and cine film at every sampled time', () => {
  const r = createRenderer();
  for (const f of FILMS.filter(x => ['neg', 'bw', 'cine'].includes(x.kind))) for (let t = 300; t < 1200; t += 50) {
    const { top, bottom } = bandAt(r, f.index, 17, t);
    for (const band of [top, bottom]) for (let i = 0; i < band.length; i++) assert.ok(band[i] >>> 24 === 255, `${f.name} t=${t}: transparent pixel inside a strip`);
  }
});

test('advance is exactly one frame (720 px): the strip after the shot of 17 equals frame 18 at rest', () => {
  const r = createRenderer();
  for (const name of ['Portra 400', 'Gold 200', 'CineStill 800T', 'Eterna', 'Acros']) {
    const after = bandAt(r, idxOf(name), 17, 1100), rest = bandAt(r, idxOf(name), 18, 261), before = bandAt(r, idxOf(name), 17, 261);
    assert.deepEqual(after.top, rest.top, name + ' top');
    assert.deepEqual(after.bottom, rest.bottom, name + ' bottom');
    assert.notDeepEqual(before.bottom, after.bottom);
  }
});

test('the advance moves on every 33 ms step, and at peak speed the holes smear into a rail', () => {
  const r = createRenderer(), f = idxOf('Portra 400');
  let moved = 0;
  for (let t = 400; t < 940; t += 33) {
    const a = bandAt(r, f, 17, t).top, b = bandAt(r, f, 17, t + 33).top;
    if (a.some((x, i) => x !== b[i])) moved++;
  }
  assert.ok(moved >= 16);
  const longest = band => { let best = 0, run = 0; for (let x = 0; x < 720; x++) { run = band[28 * 720 + x] === HOLE_RGBA ? run + 1 : 0; if (run > best) best = run; } return best; };
  let peak = 0; for (let t = 380; t < 940; t += 33) peak = Math.max(peak, longest(bandAt(r, f, 17, t).top));
  assert.ok(peak > 60, 'peak run ' + peak);
});

test('tier 1+2: no screen pixel is drawn by both the full view and a band (single ownership)', () => {
  const r = createRenderer();
  for (const f of FILMS) for (const m of MOVING) {
    for (let t = 0; t < duration(m, f); t += 70) {
      const v = r.render(m, f.index, 17, 12, t, { tier: 2, tabMode: 'always' });
      const full = v.find(x => x.id === 'full');
      if (!full.active) continue;
      for (const b of v.filter(x => x.id === 'top' || x.id === 'bottom')) {
        if (!b.active) continue;
        for (let y = 0; y < b.h; y++) for (let x = 0; x < b.w; x++)
          if (b.rgba[y * b.w + x] >>> 24 && full.rgba[(b.y + y) * 720 + b.x + x] >>> 24) assert.fail(`${f.name} ${m} t=${t} double-drawn at ${x},${b.y + y}`);
      }
    }
  }
});

test('tier 1+2 instant: the bands draw nothing, the full view draws the whole print', () => {
  const r = createRenderer(), f = idxOf('Instant');
  const v = r.render('shot', f, 17, 12, 1000, { tier: 2, tabMode: 'always' });
  assert.equal(v.find(x => x.id === 'top').active, false);
  assert.equal(v.find(x => x.id === 'bottom').active, false);
  const full = v.find(x => x.id === 'full').rgba;
  assert.ok(full[5 * 720 + 300] >>> 24 === 255 && full[470 * 720 + 300] >>> 24 === 255 && full[200 * 720 + 5] >>> 24 === 255, 'top, bottom and side borders');
});

test('instant development is a uniform dithered fade (no horizontal banding)', () => {
  const r = createRenderer(), f = idxOf('Instant');
  const full = r.render('shot', f, 17, 12, 700, { tier: 2, tabMode: 'always' }).find(x => x.id === 'full').rgba;
  const meanAlpha = y => { let s = 0; for (let x = 100; x < 600; x++) s += full[y * 720 + x] >>> 24; return s / 500; };
  const rows = [60, 150, 250, 350, 420].map(meanAlpha);
  assert.ok(Math.max(...rows) - Math.min(...rows) < 4, 'row mean alphas ' + rows.join(','));
});

test('furniture does not cover moment art (counter; tab while shown), except the frame-gap bar sweeping under the counter', () => {
  const r = createRenderer();
  const milk = c => (c & 0xffffff) === 0xe4ecee || c === 0xffd6e6ec; // milk layer and the sheet's paper backdrop are not art
  for (const f of FILMS) for (const m of MOVING) for (const tier of [1, 2]) {
    for (let t = 0; t < duration(m, f); t += 40) {
      if (tier === 2 && m === 'shot' && ['neg', 'bw', 'cine'].includes(f.kind) && t >= 260 && t < 1150) continue;
      if (tier === 2 && m === 'shot' && f.kind === 'instant' && (t < 260 || t >= 1560)) continue; // the whole print rises and ejects across the counter
      if (tier === 2 && m === 'shot' && f.kind === 'slide' && t >= 900) continue; // the mount's side borders push out sideways, across the counter
      const v = r.render(m, f.index, 17, 12, t, { tier, tabMode: 'always' });
      for (const fur of v.filter(x => x.role === 'furniture' && x.active)) for (const mv of v.filter(x => x.role === 'moment' && x.active)) {
        for (let y = 0; y < fur.h; y++) for (let x = 0; x < fur.w; x++) {
          const sx = fur.x + x - mv.x, sy = fur.y + y - mv.y;
          if (sx < 0 || sy < 0 || sx >= mv.w || sy >= mv.h) continue;
          const c = mv.rgba[sy * mv.w + sx];
          if ((c >>> 24) >= 128 && !milk(c) && fur.rgba[y * fur.w + x] >>> 24) assert.fail(`${f.name} ${m} tier ${tier} t=${t}: ${fur.id} over ${mv.id} at ${fur.x + x},${fur.y + y}`);
        }
      }
    }
  }
});

test('counter digits at rest are pure white on black, nothing grey crosses them (17, 18, 36, 1)', () => {
  const r = createRenderer(), f = idxOf('Portra 400');
  for (const fr of [17, 18, 36, 1]) {
    r.render('live', f, fr, 1, 0, { tabMode: 'always' });
    const c = r.byId.counter.rgba;
    let white = 0, grey = 0;
    for (let y = 7; y < 40; y++) for (let x = 9; x < 75; x++) { const p = c[y * 84 + x]; if (p === 0xffffffff) white++; else if (p !== 0xff0e0e0e) grey++; }
    assert.ok(white > 100, 'digits drawn');
    assert.equal(grey, 0, `frame ${fr}`);
  }
});
