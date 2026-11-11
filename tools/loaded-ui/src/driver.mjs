// SPDX-License-Identifier: GPL-2.0-only
// Scheduling policy as the camera would run it: a UI timer fires about every 33 ms; each tick renders the
// state for the CURRENT clock, so a slow tick simply skips the frames it missed. Nothing extends the
// deadline; at or after it (or on cancel) the moment is over and its views are cleared.
import { duration } from './plan.mjs';
import { FILMS } from './films.mjs';

export function createDriver(renderer) {
  let m = null; // { moment, film, frame, roll, start, options }
  return {
    get running() { return m !== null; },
    start(moment, film, frame, roll, nowMs, options = {}) { m = { moment, film, frame, roll, start: nowMs, options }; },
    cancel() { m = null; },
    /** Returns { elapsed, done } and renders; render of a finished/cancelled moment clears the moment views. */
    tick(nowMs) {
      if (!m) { return { elapsed: -1, done: true }; }
      const elapsed = nowMs - m.start, dur = duration(m.moment, FILMS[m.film]);
      if (elapsed >= dur) {
        renderer.render('none', m.film, m.frame, m.roll, 0, m.options);
        m = null;
        return { elapsed: dur, done: true };
      }
      renderer.render(m.moment, m.film, m.frame, m.roll, elapsed, m.options);
      return { elapsed, done: false };
    },
  };
}
