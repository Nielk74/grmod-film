// SPDX-License-Identifier: GPL-2.0-only
// The TypeScript reference of the film MTF module for tools/filmmtf/check.py:
//   vite-node tools/filmmtf/reference.ts -- IN_Y IN_C WIDTH HEIGHT STRIDE OUT_Y OUT_C MIX_JSON
// IN_Y, IN_C: the planes (HEIGHT rows of STRIDE bytes). Writes the planes after filmMtf() and the matrices (Q12) as JSON.
import { readFileSync, writeFileSync } from 'node:fs';
import { filmMtf, filmMtfMatrices } from '../../core/src/color/filmmtf';

const [inY, inC, w, h, stride, outY, outC, mixJson] = process.argv.slice(2).filter(a => a !== '--');
const p = { y: new Uint8Array(readFileSync(inY)), c: new Uint8Array(readFileSync(inC)), width: +w, height: +h, stride: +stride };
const A = filmMtfMatrices();
const ran = filmMtf(p, A);
writeFileSync(outY, p.y); writeFileSync(outC, p.c);
writeFileSync(mixJson, JSON.stringify({ mix: Array.from(A), ran }));
