// SPDX-License-Identifier: GPL-2.0-only
// The TypeScript reference of the colour LUT module for tools/colourlut/check.py:
//   vite-node tools/colourlut/reference.ts -- JOBS_JSON
// JOBS_JSON: [{ film, inY, inC, width, height, stride, outY, outC }, ...] (files of the planes, HEIGHT rows of STRIDE bytes).
// Writes the planes after colourLutYC() for each job and prints the list of results (true: the picture was handled).
import { readFileSync, writeFileSync } from 'node:fs';
import { colourLutValues, colourLutYC } from '../../core/src/color/colourlut';

interface Job { film: string; inY: string; inC: string; width: number; height: number; stride: number; outY: string; outC: string }
const jobs: Job[] = JSON.parse(readFileSync(process.argv.slice(2).filter(a => a !== '--')[0], 'utf8'));
const results = jobs.map(j => {
  const y = new Uint8Array(readFileSync(j.inY)), c = new Uint8Array(readFileSync(j.inC));
  const lut = colourLutValues(j.film);
  const ran = lut ? colourLutYC(y, c, j.width, j.height, j.stride, lut) : false;
  writeFileSync(j.outY, y); writeFileSync(j.outC, c);
  return ran;
});
console.log(JSON.stringify(results));
