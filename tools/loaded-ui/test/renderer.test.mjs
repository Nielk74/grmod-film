import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRenderer, PALETTE_SIZE, P, SHEET } from '../src/renderer.mjs';
import { createDriver } from '../src/driver.mjs';
import { FILMS } from '../src/films.mjs';
import { VIEWS, duration, tier1Bytes, tier2Bytes, MOMENTS } from '../src/plan.mjs';
import { FONT_DATA, GLYPH_CHARS } from '../src/font.mjs';
import { ONE, prog, inOut, outCubic, inCubic, outBack, outBounce } from '../src/fixed.mjs';

const MOVING = ['shot', 'load', 'roll'];
const hashOf = views => views.map(v => v.active ? v.rgba.reduce((h, x) => (Math.imul(h ^ x, 16777619) >>> 0), 2166136261) : 0).join(',');
const stepsFor = d => { const a = []; for (let t = 0; t < d; t += 33) a.push(t); a.push(d - 1); return a; };

test('every film and moment renders in both tiers, and is non-empty mid-moment', () => {
  const r = createRenderer();
  assert.equal(FILMS.length, 22);
  for (const f of FILMS) for (const tier of [1, 2]) for (const m of MOVING) {
    const d = duration(m, f);
    let drawn = 0;
    for (let t = 0; t < d; t += 100) {
      const views = r.render(m, f.index, 17, 12, t, { tier, tabMode: 'always' });
      for (const v of views) if (v.active && v.role === 'moment' && v.rgba.some(x => x >>> 24)) drawn++;
    }
    assert.ok(drawn > 0, `${f.name} ${m} tier ${tier} drew nothing`);
  }
});

test('tier 1 never touches the full-screen view', () => {
  const r = createRenderer();
  for (const m of MOVING) {
    const views = r.render(m, 0, 5, 1, 500, { tier: 1, tabMode: 'always' });
    assert.equal(views.find(v => v.id === 'full').active, false);
    assert.ok(views.find(v => v.id === 'full').rgba.every(x => x === 0));
  }
});

test('deterministic: same inputs give identical pixels, regardless of history (a slow tick skips frames)', () => {
  const a = createRenderer(), b = createRenderer();
  for (const f of [11, 12, 13, 16, 17]) for (const m of MOVING) {
    const o = { tier: 2, tabMode: 'always' };
    const direct = hashOf(a.render(m, f, 9, 12, 700, o));
    for (const t of stepsFor(duration(m, FILMS[f]))) b.render(m, f, 9, 12, t, o);
    b.render(m, f, 9, 12, 100, o); // a different time in between
    assert.equal(hashOf(b.render(m, f, 9, 12, 700, o)), direct, `${FILMS[f].name} ${m}`);
  }
});

test('bounds: no primitive writes outside its view (canary guard ring, every film, moment, tier, 33 ms steps)', () => {
  const r = createRenderer({ guard: 48 });
  for (const f of FILMS) for (const m of MOVING) for (const frame of [1, 9, 36]) {
    for (const t of stepsFor(duration(m, f))) r.render(m, f.index, frame, 12, t, { tier: 2, tabMode: 'peek', peekElapsed: t % 2400 });
    assert.ok(r.guardsIntact(), `${f.name} ${m} frame ${frame}`);
  }
  for (const pe of [0, 50, 100, 190, 1000, 1800, 1990]) r.render('live', 3, 17, 1, 0, { tabMode: 'peek', peekElapsed: pe });
  assert.ok(r.guardsIntact());
});

test('deadline: at or after the deadline every moment view is fully transparent', () => {
  const r = createRenderer();
  for (const f of FILMS) for (const m of MOVING) {
    const d = duration(m, f);
    r.render(m, f.index, 5, 12, d - 1, { tier: 2, tabMode: 'always' });
    for (const t of [d, d + 1, d + 5000]) {
      const views = r.render(m, f.index, 5, 12, t, { tier: 2, tabMode: 'always' });
      for (const v of views) if (v.role === 'moment') { assert.equal(v.active, false); assert.ok(v.rgba.every(x => x === 0), `${f.name} ${m} ${v.id}`); }
    }
  }
});

test('durations: shot never above 1.8 s; load and end of roll documented', () => {
  for (const f of FILMS) assert.ok(duration('shot', f) <= 1800 && duration('shot', f) >= 1200, f.name);
  assert.equal(duration('load', FILMS[0]), 2200);
  assert.equal(duration('roll', FILMS[0]), 3400);
});

test('cancel clears every moment view at once (and peek-mode furniture)', () => {
  const r = createRenderer(), d = createDriver(r);
  d.start('shot', 11, 5, 1, 1000, { tier: 2, tabMode: 'peek' });
  const t1 = d.tick(1500);
  assert.equal(t1.done, false);
  assert.ok(r.views.some(v => v.active));
  d.cancel();
  r.render('none', 11, 5, 1, 0, { tier: 2, tabMode: 'peek' });
  assert.ok(r.views.every(v => !v.active && v.rgba.every(x => x === 0)));
});

test('driver: slow ticks skip stale frames and nothing extends the deadline', () => {
  const r = createRenderer(), d = createDriver(r);
  const f = FILMS.findIndex(x => x.name === 'Portra 400'), dur = duration('shot', FILMS[f]);
  d.start('shot', f, 5, 1, 10000, { tier: 1 });
  assert.equal(d.tick(10000).elapsed, 0);
  const slow = d.tick(10000 + 900);           // 900 ms stall: renders the state at 900, not frame 2
  assert.equal(slow.elapsed, 900);
  const expect = hashOf(createRenderer().render('shot', f, 5, 1, 900, { tier: 1 }));
  assert.equal(hashOf(r.views), expect);
  const end = d.tick(10000 + dur + 4000);     // very late tick: done at once, views cleared
  assert.equal(end.done, true);
  assert.ok(r.views.filter(v => v.role === 'moment').every(v => !v.active));
  assert.equal(d.running, false);
});

test('fixed-point easing: endpoints, monotone, in int32', () => {
  for (const e of [inOut, outCubic, inCubic]) {
    assert.equal(e(0), 0); assert.equal(e(ONE), ONE);
    let p = -1; for (let t = 0; t <= ONE; t++) { const v = e(t); assert.ok(v >= p - 1, 'monotone within one Q10 unit (truncation)'); assert.ok(Number.isInteger(v)); p = v; }
  }
  assert.equal(outBack(ONE), ONE);
  assert.ok(Math.max(...Array.from({ length: ONE + 1 }, (_, t) => outBack(t))) > ONE); // overshoot, then settle
  assert.ok(Math.abs(outBounce(ONE) - ONE) <= 16 && outBounce(0) === 0);
  assert.equal(prog(50, 100, 200), 0); assert.equal(prog(250, 100, 200), ONE); assert.equal(prog(150, 100, 200), 512);
});

test('no floating point in the per-frame path', () => {
  for (const f of ['fixed.mjs', 'surface.mjs', 'renderer.mjs']) {
    const src = readFileSync(new URL('../src/' + f, import.meta.url), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');
    assert.doesNotMatch(src, /Math\.(sin|cos|tan|atan2?|sqrt|pow|exp|log|random|floor|round|ceil|hypot)/, f);
    assert.doesNotMatch(src.replace(/'[^'\n]*'/g, "''"), /\b\d+\.\d+\b/, f + ' has a decimal literal');
  }
});

/** counter wheels: read the drawn counter view rows */
test('counter roll: 9 to 10 rolls both wheels, 36 to 1 holds at the end, wheels that do not change stay still', () => {
  const r = createRenderer();
  const f = FILMS.findIndex(x => x.name === 'Portra 400'), counter = () => r.byId.counter.rgba.slice();
  const at = (frame, t, m = 'shot') => { r.render(m, f, frame, 1, t, { tier: 1, tabMode: 'always' }); return counter(); };
  const before = at(9, 0), mid = at(9, 710), after = at(9, 1000);
  assert.notDeepEqual(before, mid); assert.notDeepEqual(mid, after);
  const tensRegion = a => { const o = []; for (let y = 4; y < 44; y++) for (let x = 9; x < 39; x++) o.push(a[y * 108 + x]); return o; };
  const onesRegion = a => { const o = []; for (let y = 4; y < 44; y++) for (let x = 45; x < 75; x++) o.push(a[y * 108 + x]); return o; };
  assert.notDeepEqual(tensRegion(before), tensRegion(after), 'tens wheel goes from blank to 1');
  assert.notDeepEqual(onesRegion(before), onesRegion(after));
  // 9 -> 10 must show the same pixels as a static 10
  r.render('live', f, 10, 1, 0, { tier: 1, tabMode: 'always' });
  assert.deepEqual(after, counter(), 'rolled-to 10 equals static 10');
  // 17 -> 18: the tens wheel (1) stays identical through the roll
  const a17 = at(17, 0), m17 = at(17, 710);
  assert.deepEqual(tensRegion(a17), tensRegion(m17));
  assert.notDeepEqual(onesRegion(a17), onesRegion(m17));
  // end of roll: 36 at the start, 1 at the end
  const s36 = at(36, 0, 'roll');
  r.render('live', f, 36, 1, 0, { tier: 1, tabMode: 'always' }); assert.deepEqual(s36, counter());
  const end = at(36, 3399, 'roll');
  r.render('live', f, 1, 1, 0, { tier: 1, tabMode: 'always' }); assert.deepEqual(end, counter(), 'rewind ends on 1');
  // load: S rolls to the frame number
  const l0 = at(1, 0, 'load'), l1 = at(1, 2000, 'load');
  assert.notDeepEqual(l0, l1); assert.deepEqual(l1, counter());
  // frame 36 shot: the counter does not roll (film is out)
  assert.deepEqual(at(36, 0), at(36, 1000));
});

test('peek mode: hidden by default, slides in, shown, slides out, gone; always mode always shows', () => {
  const r = createRenderer(), f = 11;
  const vis = (o) => { r.render('live', f, 5, 1, 0, o); return [r.byId.tab.active, r.byId.counter.active]; };
  assert.deepEqual(vis({ tabMode: 'peek' }), [false, false]);
  assert.deepEqual(vis({ tabMode: 'peek', peekElapsed: 600 }), [true, true]);
  assert.deepEqual(vis({ tabMode: 'peek', peekElapsed: 2000 }), [false, false]);
  assert.deepEqual(vis({ tabMode: 'always' }), [true, true]);
  r.render('live', f, 5, 1, 0, { tabMode: 'peek', peekElapsed: 0 });
  assert.equal(r.byId.tab.rgba.some(x => x >>> 24), false, 'fully slid out at the start of the peek');
  // a moment forces the counter on in peek mode
  r.render('shot', f, 5, 1, 700, { tabMode: 'peek' });
  assert.equal(r.byId.counter.active, true);
});

test('views: tier 1 memory around 300 KB, every view rectangle on the 720x480 screen', () => {
  assert.equal(tier1Bytes(), 302848);
  assert.equal(tier2Bytes(), 1382400);
  for (const v of VIEWS) assert.ok(v.x >= 0 && v.y >= 0 && v.x + v.w <= 720 && v.y + v.h <= 480, v.id);
});

test('budgets: palette <= 32 entries in every view, assets far below 256 KB', () => {
  assert.ok(PALETTE_SIZE <= 32 && Math.max(...Object.values(P)) < PALETTE_SIZE);
  const r = createRenderer();
  const used = new Map();
  for (const f of FILMS) for (const m of MOVING) for (const t of stepsFor(duration(m, f)).filter((_, i) => i % 6 === 0)) {
    r.render(m, f.index, 17, 12, t, { tier: 2, tabMode: 'always' });
    for (const v of r.views) { const { buf } = v.surface; let set = used.get(v.id) || new Set(); for (let i = 0; i < buf.length; i += 3) set.add(buf[i]); used.set(v.id, set); }
  }
  for (const [id, set] of used) assert.ok(set.size <= 32 && Math.max(...set) < PALETTE_SIZE, id + ' uses ' + set.size);
  const filmBytes = readFileSync(new URL('../src/films.gen.mjs', import.meta.url)).length;
  const total = FONT_DATA.length + filmBytes;
  assert.ok(total < 256 * 1024, 'asset bytes ' + total);
  assert.equal(FONT_DATA.length, GLYPH_CHARS.length * 7);
});

test('font: no text smaller than 14 px tall is drawn (scale >= 2 everywhere)', () => {
  const src = readFileSync(new URL('../src/renderer.mjs', import.meta.url), 'utf8');
  const calls = [...src.matchAll(/\.(?:text|num|glyph)\([^;]*?,\s*(\d)\s*,\s*P\.\w+(?:,\s*\d+)?\)/g)];
  assert.ok(calls.length > 20);
  for (const c of calls) assert.ok(Number(c[1]) >= 2, c[0]);
});

test('contact sheet: thumbnails replace tiles; without them tiles are plain; circle appears late', () => {
  const r = createRenderer(), f = 11;
  const thumbs = Array.from({ length: 36 }, () => new Uint32Array(SHEET.fw * SHEET.fh).fill(0xff00ff00));
  const withT = hashOf(r.render('roll', f, 36, 12, 1500, { tier: 2, tabMode: 'always', thumbs }));
  const without = hashOf(r.render('roll', f, 36, 12, 1500, { tier: 2, tabMode: 'always' }));
  assert.notEqual(withT, without);
  const full = r.byId.full;
  r.render('roll', f, 36, 12, 1400, { tier: 2, tabMode: 'always' });
  const red0 = full.rgba.filter(x => x === 0xff2828e2).length;
  r.render('roll', f, 36, 12, 2100, { tier: 2, tabMode: 'always' });
  const red1 = full.rgba.filter(x => x === 0xff2828e2).length;
  assert.equal(red0, 0); assert.ok(red1 > 300);
});
