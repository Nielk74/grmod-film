// SPDX-License-Identifier: GPL-2.0-only
// Lab-side compositing (not part of the camera port): straight-alpha source-over of each active view onto
// a 720x480 photo, exactly as the camera is assumed to blend an RGBA view over the picture.
import { W } from './plan.mjs';

export function compositeInto(dst, views) {
  for (const v of views) {
    if (!v.active) continue;
    const src = v.rgba;
    for (let y = 0; y < v.h; y++) {
      let d = (v.y + y) * W + v.x, s = y * v.w;
      for (let x = 0; x < v.w; x++, d++, s++) {
        const c = src[s], a = c >>> 24;
        if (a === 0) continue;
        if (a === 255) { dst[d] = c; continue; }
        const o = dst[d], ia = 255 - a;
        const r = (((c & 255) * a + (o & 255) * ia + 127) / 255) | 0;
        const g = ((((c >> 8) & 255) * a + ((o >> 8) & 255) * ia + 127) / 255) | 0;
        const b = ((((c >> 16) & 255) * a + ((o >> 16) & 255) * ia + 127) / 255) | 0;
        dst[d] = (0xff000000 | (b << 16) | (g << 8) | r) >>> 0;
      }
    }
  }
}
