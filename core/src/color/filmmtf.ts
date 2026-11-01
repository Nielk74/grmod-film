// SPDX-License-Identifier: GPL-2.0-only
/**
 * Film MTF: the sharpness of a negative film (Kodak Portra 400, from the E-4050 datasheet's MTF curves), per colour layer, on the
 * YCbCr 4:2:2 pictures the camera's JPEG step is about to compress (tools/filmmtf/filmmtf.c runs the same integer steps).
 *
 * The film's own MTF is not the lens's: each dye layer boosts detail of 8..33 pixel structures by 4..17 % (acutance, from development)
 * and rolls fine detail off. The red (cyan-dye) layer is the softest: at the pixel limit it passes about 15 %, green 30 %, blue 40 % (the
 * response of the JPEG-only reference of the 2026-11-01 study, which this reproduces within 5 % at every frequency).
 *
 * A three-level Laplacian pyramid (Gaussian REDUCE [1 4 6 4 1] each way, bilinear EXPAND) splits the picture into three bands of detail
 * and a low-pass. Each band is multiplied, per colour layer, by that layer's gain (the gains fitted to the layer's response), the layers
 * being taken from Y, Cb, Cr through the JPEG matrix, so every band is mixed with one 3x3 matrix in YCbCr (A0, A1, A2, finest first):
 *   out = A0 L0 + EXPAND(M1),  M1 = (A1 - A0) L1 + EXPAND(M2),  M2 = (A2 - A1) L2 + EXPAND(M3),  M3 = (I - A2) L3
 * (the Laplacian recombination with each band's gain, written so that each level is one matrix and one EXPAND).
 * Chroma is stored one sample per two pixels (4:2:2), so its level 0 has the pitch of level 1: only its rows are reduced.
 * The picture is done in strips of STRIP rows with a MARGIN of rows on each side (the pyramid's reach), so the module needs a few
 * megabytes, not a copy of the picture. Integer arithmetic throughout: levels in sixteenths (s16), matrices in Q12.
 */

/** The film's gain per detail band (finest first) of the red, green and blue layers: fitted to the layers' response (tools/filmmtf/fit.ts). */
export const FILM_MTF_GAINS: Readonly<Record<'R' | 'G' | 'B', readonly number[]>> = {
  R: [0.116, 0.868, 1.297],
  G: [0.269, 1.128, 1.315],
  B: [0.369, 1.042, 1.261],
};

export const FILM_MTF_BANDS = 3;
/** Rows of a strip, and of margin around it (a multiple of 8: the pyramid has three halvings). */
export const FILM_MTF_STRIP = 192;
export const FILM_MTF_MARGIN = 32;
/** Pictures narrower than this (screennail, thumbnail) are left alone: the film's response is for the 6000 pixel frame. */
export const FILM_MTF_MIN_WIDTH = 4096;

// JPEG's YCbCr <-> RGB (Cb, Cr centred on 0)
const Q: number[][] = [[1, 0, 1.402], [1, -0.344136, -0.714136], [1, 1.772, 0]];
const QI: number[][] = [[0.299, 0.587, 0.114], [-0.168736, -0.331264, 0.5], [0.5, -0.418688, -0.081312]];

/**
 * The four 3x3 matrices (Q12, row-major, rows Y Cb Cr; 36 values) the module uses: A0 (band 0 applied to the picture itself) and the
 * matrices of the three levels above it, D1 = A1 - A0, D2 = A2 - A1, D3 = I - A2, where A_b applies the layers' gains of band b to a
 * (Y, Cb, Cr) vector.
 */
export function filmMtfMatrices(gains: Readonly<Record<'R' | 'G' | 'B', readonly number[]>> = FILM_MTF_GAINS): Int16Array {
  const A: number[][] = [];
  for (let b = 0; b < FILM_MTF_BANDS; b++) {
    const g = [gains.R[b], gains.G[b], gains.B[b]], m: number[] = [];
    for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) {
      let s = 0;
      for (let k = 0; k < 3; k++) s += QI[i][k] * g[k] * Q[k][j];
      m.push(Math.round(s * 4096));
    }
    A.push(m);
  }
  const eye = [4096, 0, 0, 0, 4096, 0, 0, 0, 4096];
  return Int16Array.from([...A[0], ...A[1].map((v, i) => v - A[0][i]), ...A[2].map((v, i) => v - A[1][i]), ...eye.map((v, i) => v - A[2][i])]);
}

/** The planes of a 4:2:2 picture as the camera hands them over: Y bytes, and Cb, Cr interleaved per two pixels; `stride` for both. */
export interface Ycc422 { y: Uint8Array; c: Uint8Array; width: number; height: number; stride: number }

/** True when the module works on a picture of this size (as picture_ok in the C module). */
export const filmMtfApplies = (w: number, h: number, minWidth = FILM_MTF_MIN_WIDTH) => w >= minWidth && w <= 12000 && h >= 64 && h <= 12000 && (w & 7) === 0 && (h & 7) === 0;

interface Planes { w: number; h: number; a: Int16Array; b: Int16Array; c: Int16Array } // Y, Cb, Cr in sixteenths
const planes = (w: number, h: number): Planes => ({ w, h, a: new Int16Array(w * h), b: new Int16Array(w * h), c: new Int16Array(w * h) });
const K = [1, 4, 6, 4, 1];

/** 5x5 REDUCE of one s16 plane (sixteenths) to half size. */
function reducePlane(src: Int16Array, w: number, h: number, dst: Int16Array): void {
  const w2 = w >> 1, h2 = h >> 1, tmp = new Int32Array(w2 * h);
  for (let y = 0; y < h; y++) for (let x = 0; x < w2; x++) {
    let s = 0;
    for (let k = -2; k <= 2; k++) { let xx = 2 * x + k; xx = xx < 0 ? 0 : xx >= w ? w - 1 : xx; s += K[k + 2] * src[y * w + xx]; }
    tmp[y * w2 + x] = s;
  }
  for (let y = 0; y < h2; y++) for (let x = 0; x < w2; x++) {
    let s = 0;
    for (let k = -2; k <= 2; k++) { let yy = 2 * y + k; yy = yy < 0 ? 0 : yy >= h ? h - 1 : yy; s += K[k + 2] * tmp[yy * w2 + x]; }
    dst[y * w2 + x] = (s + 128) >> 8;
  }
}
const reduce = (p: Planes): Planes => { const o = planes(p.w >> 1, p.h >> 1); reducePlane(p.a, p.w, p.h, o.a); reducePlane(p.b, p.w, p.h, o.b); reducePlane(p.c, p.w, p.h, o.c); return o; };

/** Bilinear EXPAND of one s16 plane to double size (output pixel (x, y) at (x / 2, y / 2) of the source). */
function expandPlane(src: Int16Array, w: number, h: number, dst: Int16Array): void {
  const w2 = w * 2;
  for (let y = 0; y < h * 2; y++) {
    const y0 = y >> 1, y1 = (y & 1) ? Math.min(h - 1, y0 + 1) : y0;
    for (let x = 0; x < w2; x++) {
      const x0 = x >> 1, x1 = (x & 1) ? Math.min(w - 1, x0 + 1) : x0;
      dst[y * w2 + x] = (src[y0 * w + x0] + src[y0 * w + x1] + src[y1 * w + x0] + src[y1 * w + x1] + 2) >> 2;
    }
  }
}
const expand = (p: Planes): Planes => { const o = planes(p.w * 2, p.h * 2); expandPlane(p.a, p.w, p.h, o.a); expandPlane(p.b, p.w, p.h, o.b); expandPlane(p.c, p.w, p.h, o.c); return o; };

/** D (Q12, matrix number `at` of the four) applied to the (Y, Cb, Cr) vector at every position of `p`; plus `up` expanded, when given. */
function mix(A: Int16Array, at: number, p: Planes, up?: Planes): Planes {
  const o = at * 9, out = planes(p.w, p.h);
  const e = up ? expand(up) : null;
  for (let y = 0; y < p.h; y++) for (let x = 0; x < p.w; x++) {
    const i = y * p.w + x, v = p.a[i], b = p.b[i], c = p.c[i];
    out.a[i] = ((A[o] * v + A[o + 1] * b + A[o + 2] * c + 2048) >> 12) + (e ? e.a[i] : 0);
    out.b[i] = ((A[o + 3] * v + A[o + 4] * b + A[o + 5] * c + 2048) >> 12) + (e ? e.b[i] : 0);
    out.c[i] = ((A[o + 6] * v + A[o + 7] * b + A[o + 8] * c + 2048) >> 12) + (e ? e.c[i] : 0);
  }
  return out;
}

const clamp8 = (v: number) => (v < 0 ? 0 : v > 255 ? 255 : v);

/**
 * One strip: rows [core0, core1) of the picture, computed from the rows [e0, e1) (the strip and its margin). `yr(i)` and `cr(i)` give the
 * original luma and chroma row of extended row i (0..e1-e0-1). Returns the new luma and chroma bytes of the core rows.
 */
function strip(A: Int16Array, w: number, eh: number, yr: (i: number) => Uint8Array, cr: (i: number) => Uint8Array, coreTop: number, coreRows: number): { y: Uint8Array; c: Uint8Array } {
  const w1 = w >> 1, h1 = eh >> 1;
  // level 0 -> 1: luma 5x5, chroma rows only (its columns already have the pitch of level 1)
  const L1 = planes(w1, h1), htmp = new Int32Array(w1 * eh);
  for (let r = 0; r < eh; r++) { const row = yr(r); for (let x = 0; x < w1; x++) { let s = 0; for (let k = -2; k <= 2; k++) { let xx = 2 * x + k; xx = xx < 0 ? 0 : xx >= w ? w - 1 : xx; s += K[k + 2] * row[xx]; } htmp[r * w1 + x] = s; } }
  for (let y = 0; y < h1; y++) for (let x = 0; x < w1; x++) {
    let s = 0, sb = 0, sc = 0;
    for (let k = -2; k <= 2; k++) {
      let yy = 2 * y + k; yy = yy < 0 ? 0 : yy >= eh ? eh - 1 : yy;
      s += K[k + 2] * htmp[yy * w1 + x];
      const crow = cr(yy); sb += K[k + 2] * (crow[2 * x] - 128); sc += K[k + 2] * (crow[2 * x + 1] - 128);
    }
    L1.a[y * w1 + x] = (s + 8) >> 4; L1.b[y * w1 + x] = sb; L1.c[y * w1 + x] = sc;
  }
  const L2 = reduce(L1), L3 = reduce(L2);
  // top-down: M3 = D3 L3, M2 = D2 L2 + EXPAND(M3), M1 = D1 L1 + EXPAND(M2)
  const M1 = mix(A, 1, L1, mix(A, 2, L2, mix(A, 3, L3)));
  // level 0 for the core rows
  const outY = new Uint8Array(coreRows * w), outC = new Uint8Array(coreRows * w), o = 0;
  for (let ry = 0; ry < coreRows; ry++) {
    const y = coreTop + ry, y0 = y >> 1, y1 = (y & 1) ? Math.min(h1 - 1, y0 + 1) : y0;
    const yrow = yr(y), crow = cr(y);
    for (let j = 0; j < w1; j++) {
      const x = 2 * j, x1 = Math.min(w1 - 1, j + 1);
      const ya = yrow[x] * 16, yb = yrow[x + 1] * 16, ybar = (ya + yb) >> 1, cb = (crow[x] - 128) * 16, cc = (crow[x + 1] - 128) * 16;
      // EXPAND of M1 at the two luma pixels and the chroma pair (columns: x even -> j, x odd -> avg(j, j+1); chroma at column j)
      const m = (pl: Int16Array, cx0: number, cx1: number) => (pl[y0 * w1 + cx0] + pl[y0 * w1 + cx1] + pl[y1 * w1 + cx0] + pl[y1 * w1 + cx1] + 2) >> 2;
      const ea = m(M1.a, j, j), eb = m(M1.a, j, x1);
      const ec_b = (M1.b[y0 * w1 + j] + M1.b[y1 * w1 + j] + 1) >> 1, ec_c = (M1.c[y0 * w1 + j] + M1.c[y1 * w1 + j] + 1) >> 1;
      const ay = (A[0] * ya + A[1] * cb + A[2] * cc + 2048) >> 12, by = (A[0] * yb + A[1] * cb + A[2] * cc + 2048) >> 12;
      outY[ry * w + x] = clamp8((ay + ea + 8) >> 4); outY[ry * w + x + 1] = clamp8((by + eb + 8) >> 4);
      const cbv = ((A[3] * ybar + A[4] * cb + A[5] * cc + 2048) >> 12) + ec_b, crv = ((A[6] * ybar + A[7] * cb + A[8] * cc + 2048) >> 12) + ec_c;
      outC[ry * w + x] = clamp8(((cbv + 8) >> 4) + 128); outC[ry * w + x + 1] = clamp8(((crv + 8) >> 4) + 128);
    }
  }
  void o;
  return { y: outY, c: outC };
}

/** Apply the film MTF to a 4:2:2 picture, in place. Returns false (and changes nothing) when the picture is not one the module handles. */
export function filmMtf(p: Ycc422, A: Int16Array = filmMtfMatrices(), minWidth = FILM_MTF_MIN_WIDTH): boolean {
  const { width: w, height: h, stride } = p;
  if (!filmMtfApplies(w, h, minWidth) || p.stride < w) return false;
  const S = FILM_MTF_STRIP, M = FILM_MTF_MARGIN;
  let carryY = new Uint8Array(0), carryC = new Uint8Array(0), carryRows = 0;
  for (let core0 = 0; core0 < h; core0 += S) {
    const core1 = Math.min(h, core0 + S), e0 = Math.max(0, core0 - M), e1 = Math.min(h, core1 + M), eh = e1 - e0, top = core0 - e0;
    const yr = (i: number) => (i < top ? carryY.subarray((carryRows - top + i) * w, (carryRows - top + i + 1) * w) : p.y.subarray((e0 + i) * stride, (e0 + i) * stride + w));
    const cr = (i: number) => (i < top ? carryC.subarray((carryRows - top + i) * w, (carryRows - top + i + 1) * w) : p.c.subarray((e0 + i) * stride, (e0 + i) * stride + w));
    const out = strip(A, w, eh, yr, cr, top, core1 - core0);
    // carry the original rows the next strip uses as its top margin, then write this strip
    const nextTop = Math.min(M, core1 - core0), cy = new Uint8Array(nextTop * w), cc = new Uint8Array(nextTop * w);
    for (let r = 0; r < nextTop; r++) { cy.set(yr(top + core1 - core0 - nextTop + r), r * w); cc.set(cr(top + core1 - core0 - nextTop + r), r * w); }
    for (let r = 0; r < core1 - core0; r++) { p.y.set(out.y.subarray(r * w, (r + 1) * w), (core0 + r) * stride); p.c.set(out.c.subarray(r * w, (r + 1) * w), (core0 + r) * stride); }
    carryY = cy; carryC = cc; carryRows = nextTop;
  }
  return true;
}

/** JPEG 4:2:2 planes from 8-bit RGB (chroma averaged over each pair), and back (chroma replicated), for previews and tests. */
export function rgbToYcc422(rgb: Uint8Array, w: number, h: number): Ycc422 {
  const y = new Uint8Array(w * h), c = new Uint8Array(w * h);
  for (let r = 0; r < h; r++) for (let j = 0; j < w / 2; j++) {
    let cb = 0, cr = 0;
    for (let k = 0; k < 2; k++) {
      const i = (r * w + 2 * j + k) * 3, R = rgb[i], G = rgb[i + 1], B = rgb[i + 2], Y = 0.299 * R + 0.587 * G + 0.114 * B;
      y[r * w + 2 * j + k] = clamp8(Math.round(Y)); cb += -0.168736 * R - 0.331264 * G + 0.5 * B; cr += 0.5 * R - 0.418688 * G - 0.081312 * B;
    }
    c[r * w + 2 * j] = clamp8(Math.round(cb / 2 + 128)); c[r * w + 2 * j + 1] = clamp8(Math.round(cr / 2 + 128));
  }
  return { y, c, width: w, height: h, stride: w };
}
export function ycc422ToRgb(p: Ycc422): Uint8Array {
  const { width: w, height: h } = p, out = new Uint8Array(w * h * 3);
  for (let r = 0; r < h; r++) for (let x = 0; x < w; x++) {
    const Y = p.y[r * p.stride + x], cb = p.c[r * p.stride + (x & ~1)] - 128, cr = p.c[r * p.stride + (x & ~1) + 1] - 128, o = (r * w + x) * 3;
    out[o] = clamp8(Math.round(Y + 1.402 * cr)); out[o + 1] = clamp8(Math.round(Y - 0.344136 * cb - 0.714136 * cr)); out[o + 2] = clamp8(Math.round(Y + 1.772 * cb));
  }
  return out;
}
