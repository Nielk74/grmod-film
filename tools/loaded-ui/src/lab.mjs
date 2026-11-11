import { createRenderer, SHEET } from './renderer.mjs';
import { compositeInto } from './compose.mjs';
import { FILMS, ROLL_LENGTH } from './films.mjs';
import { PLACEHOLDERS, PLACEHOLDER_SET_NAME, REVIEW_PLACEHOLDERS, duration, W, H } from './plan.mjs';
import credits from '../../../ui/src/assets/samples/CREDITS.md?raw';

const photos = import.meta.glob('../../../ui/src/assets/samples/*.jpg', { eager: true, query: '?url', import: 'default' });
const $ = id => document.getElementById(id);
const canvas = $('screen'), ctx = canvas.getContext('2d');
// 1:1 truth: one canvas pixel per device pixel, whatever the devicePixelRatio.
const fit = () => { const z = $('zoom').checked ? 2 : 1; canvas.style.width = (W * z / devicePixelRatio) + 'px'; canvas.style.height = (H * z / devicePixelRatio) + 'px'; };
$('credits').textContent = credits;
for (const f of FILMS) $('film').add(new Option(`${f.name} (${f.kind})`, f.index));
$('film').value = FILMS.findIndex(f => f.name === 'Portra 400');
const urls = Object.entries(photos);
for (const [p, u] of urls) $('photo').add(new Option(p.split('/').pop(), u));

const r = createRenderer();
const base = new Uint32Array(W * H), buf = new Uint32Array(W * H), thumbs = [];
const off = document.createElement('canvas'); off.width = W; off.height = H;
const octx = off.getContext('2d', { willReadFrequently: true });
const image = new ImageData(new Uint8ClampedArray(buf.buffer), W, H);

async function cover(url, w, h) {
  const img = new Image(); img.src = url; await img.decode();
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const g = c.getContext('2d', { willReadFrequently: true }), s = Math.max(w / img.width, h / img.height);
  g.drawImage(img, (w - img.width * s) / 2, (h - img.height * s) / 2, img.width * s, img.height * s);
  return new Uint32Array(g.getImageData(0, 0, w, h).data.buffer);
}
async function loadPhoto(url) {
  base.set(await cover(url, W, H));
  if (thumbs.length) return;
  const all = await Promise.all(urls.map(([, u]) => cover(u, 420, 280)));
  for (let i = 0; i < ROLL_LENGTH; i++) {
    const src = all[i % all.length], t = new Uint32Array(SHEET.fw * SHEET.fh), ox = ((i * 37) % 6) * 28, oy = ((i * 11) % 5) * 18;
    for (let y = 0; y < SHEET.fh; y++) for (let x = 0; x < SHEET.fw; x++) t[y * SHEET.fw + x] = src[((oy + y * 4) % 280) * 420 + (ox + x * 4) % 420];
    thumbs.push(t);
  }
}

const st = { moment: 'live', start: 0, frame: 1, roll: 12, paused: false, pausedAt: 0, peekStart: performance.now() };
const clock = () => performance.now();
function startMoment(m) {
  const f = FILMS[+$('film').value];
  st.moment = m; st.start = clock(); st.paused = false; $('pause').textContent = 'Pause';
  if (m === 'roll') st.frame = ROLL_LENGTH;
  if (m === 'load') st.frame = 1;
  st.peekStart = clock();
  $('scrub').max = duration(m, f);
}
function finishMoment() {
  if (st.moment === 'shot' && st.frame < ROLL_LENGTH) st.frame++;
  if (st.moment === 'roll') { st.frame = 1; st.roll++; }
  st.moment = 'live';
}
$('load').onclick = () => startMoment('load');
$('shot').onclick = () => { if (st.moment !== 'live') finishMoment(); startMoment('shot'); }; // a new shutter cancels the running moment instantly
$('roll').onclick = () => startMoment('roll');
$('wake').onclick = () => { st.peekStart = clock(); };
$('film').onchange = () => { st.moment = 'live'; st.peekStart = clock(); };
$('photo').onchange = () => loadPhoto($('photo').value);
$('zoom').onchange = fit;
$('pause').onclick = () => {
  st.paused = !st.paused; $('pause').textContent = st.paused ? 'Resume' : 'Pause';
  if (st.paused) st.pausedAt = clock() - st.start; else st.start = clock() - st.pausedAt;
};
$('scrub').oninput = () => { if (st.moment === 'live') return; st.paused = true; $('pause').textContent = 'Resume'; st.pausedAt = +$('scrub').value; };

function tick() {
  const f = FILMS[+$('film').value], n = clock();
  let el = st.moment === 'live' ? 0 : (st.paused ? st.pausedAt : n - st.start);
  if (st.moment !== 'live' && el >= duration(st.moment, f)) { finishMoment(); el = 0; }
  if (st.moment !== 'live' && !st.paused) $('scrub').value = el;
  const pe = n - st.peekStart;
  const d = new Date(), opts = { tier: +$('tier').value, tabMode: $('tabmode').value, counterMode: $('cntmode').value, date: { month: d.getMonth(), year: d.getFullYear() % 100 }, peekElapsed: pe < 5000 ? pe : -1,
    thumbs: $('thumbs').value === '1' ? thumbs : null };
  buf.set(base);
  if ($('ph').checked && (st.moment === 'shot' || st.moment === 'roll')) for (const p of REVIEW_PLACEHOLDERS) { /* under the overlays, so a row that peeks out during the slide shows */ for (let x = p.x; x < p.x + p.w; x++) { buf[p.y * W + x] = 0xffff00ff; buf[(p.y + p.h - 1) * W + x] = 0xffff00ff; } for (let y = p.y; y < p.y + p.h; y++) { buf[y * W + p.x] = 0xffff00ff; buf[y * W + p.x + p.w - 1] = 0xffff00ff; } }
  compositeInto(buf, r.render(st.moment, f.index, st.frame, st.roll, el, opts));
  octx.putImageData(image, 0, 0);
  ctx.drawImage(off, 0, 0);
  if ($('ph').checked && st.moment !== 'shot' && st.moment !== 'roll') {
    ctx.strokeStyle = '#f0f'; ctx.fillStyle = '#f0f'; ctx.font = '12px monospace';
    for (const p of PLACEHOLDERS) {
      ctx.strokeRect(p.x + .5, p.y + .5, p.w - 1, p.h - 1);
      if (p.label.length * 7 < p.w) ctx.fillText(p.label, p.x + 4, p.y + 14);
    }
  }
  const set = !$('ph').checked ? '' : (st.moment === 'shot' || st.moment === 'roll') ? '  [placeholders: review screen, reference photo, approx.]' : `  [placeholders: ${PLACEHOLDER_SET_NAME}]`;
  $('status').textContent = `${st.moment} ${Math.round(el)} ms  frame ${st.frame}  roll ${st.roll}  ${f.name}${set}`;
  requestAnimationFrame(tick);
}
fit(); addEventListener('resize', fit);
loadPhoto(urls[0][1]).then(() => { $('photo').value = urls[0][1]; requestAnimationFrame(tick); });
