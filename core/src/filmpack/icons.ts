// SPDX-License-Identifier: GPL-2.0-only
/** 40x40 film icons in the camera's own frame: a caption band and a big code, as a film-simulation badge. */
import type { Look } from './looks';

const FONT: Record<string, string[]> = {
  A: ['010', '101', '111', '101', '101'], B: ['110', '101', '110', '101', '110'], C: ['011', '100', '100', '100', '011'],
  D: ['110', '101', '101', '101', '110'], E: ['111', '100', '110', '100', '111'], F: ['111', '100', '110', '100', '100'],
  G: ['011', '100', '101', '101', '011'], H: ['101', '101', '111', '101', '101'], I: ['111', '010', '010', '010', '111'],
  J: ['001', '001', '001', '101', '010'], K: ['101', '101', '110', '101', '101'], L: ['100', '100', '100', '100', '111'],
  M: ['101', '111', '111', '101', '101'], N: ['110', '101', '101', '101', '101'], O: ['010', '101', '101', '101', '010'],
  P: ['110', '101', '110', '100', '100'], Q: ['010', '101', '101', '110', '011'], R: ['110', '101', '110', '101', '101'],
  S: ['011', '100', '010', '001', '110'], T: ['111', '010', '010', '010', '010'], U: ['101', '101', '101', '101', '111'],
  V: ['101', '101', '101', '101', '010'], W: ['101', '101', '111', '111', '101'], X: ['101', '101', '010', '101', '101'],
  Y: ['101', '101', '010', '010', '010'], Z: ['111', '001', '010', '100', '111'],
  '0': ['111', '101', '101', '101', '111'], '1': ['010', '110', '010', '010', '111'], '2': ['110', '001', '010', '100', '111'],
  '3': ['110', '001', '010', '001', '110'], '4': ['101', '101', '111', '001', '001'], '5': ['111', '100', '110', '001', '110'],
  '6': ['011', '100', '111', '101', '111'], '7': ['111', '001', '010', '010', '010'], '8': ['111', '101', '111', '101', '111'],
  '9': ['111', '101', '111', '001', '110'], '+': ['000', '010', '111', '010', '000'], ' ': ['000', '000', '000', '000', '000'],
};

/** `template`: the camera's empty film tile (6400 bytes RGBA; content area x 2..37, y 9..30). */
export function filmIcon(template: Uint8Array, look: Look): Uint8Array {
  const out = template.slice();
  const pixel = (x: number, y: number, rgb: readonly number[]) => out.set([rgb[0], rgb[1], rgb[2], 255], (y * 40 + x) * 4);
  const box = (x0: number, y0: number, x1: number, y1: number, rgb: readonly number[]) => {
    for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) pixel(x, y, rgb);
  };
  const text = (value: string, y0: number, scale: number, ink: readonly number[]) => {
    const width = value.length * (3 * scale + scale) - scale, x0 = 2 + Math.floor((36 - width) / 2);
    [...value].forEach((ch, i) => {
      const glyph = FONT[ch];
      if (!glyph) throw new Error(`no icon glyph for ${JSON.stringify(ch)} (${look.name})`);
      glyph.forEach((row, y) => [...row].forEach((on, x) => {
        if (on === '1') box(x0 + i * 4 * scale + x * scale, y0 + y * scale, x0 + i * 4 * scale + x * scale + scale - 1, y0 + y * scale + scale - 1, ink);
      }));
    });
  };
  const { panel, band, ink, captionInk } = look.colors;
  box(2, 9, 37, 30, panel);
  box(2, 9, 37, 15, band);
  if (look.caption.length * 4 - 1 > 36 || look.code.length * 8 - 2 > 36) throw new Error(`icon text too long (${look.name})`);
  text(look.caption, 10, 1, captionInk);
  text(look.code, 18, 2, ink);
  return out;
}
