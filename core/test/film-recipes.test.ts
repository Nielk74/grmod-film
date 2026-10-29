// SPDX-License-Identifier: GPL-2.0-only
// GR Mod's film recipes (GR III / IIIx round 10: camera defaults and grain) and the film library.
// The build tests need the official GR III 2.10 file (GRMOD_GR3_FIRMWARE); the rest runs without it.
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { Engine } from '../src';
import { convertGr3xCube } from '../src/color/gr3x-import';
import { filmIcon } from '../src/filmpack/icons';
import { LOOKS, cubeText } from '../src/filmpack/looks';
import { GR3X_NEUTRAL_PARAMETERS, gr3xCanonicalDefaults, gr3xFilmDefaultBytes, gr3xHasDefaults, gr3xRecipePrint, validateGr3xFilmDefaults } from '../src/fw/gr3x/film-recipe';
import { GR3X_FILMS_DEFAULTS_MODULE } from '../src/fw/gr3x/films-defaults-native';
import { GR3X_FILMS_GRAIN_MODULE } from '../src/fw/gr3x/films-grain-native';
import { GR3X_FILM_IDS } from '../src/fw/gr3x/look-resources';
import { GR3X_T4_CUSTOM } from '../src/fw/gr3x/geometry';

describe('film recipes: the starting values', () => {
  it('encodes the parameters as films.c reads them (order, scales, Halation states)', () => {
    expect(Array.from(gr3xFilmDefaultBytes(undefined))).toEqual([...GR3X_NEUTRAL_PARAMETERS]);
    expect(Array.from(gr3xFilmDefaultBytes({ saturation: 3, hue: -4, key: 1, contrast: 4, highlight: -2, shadow: 2, sharpness: -1, shading: -3, clarity: 2 })))
      .toEqual([7, 0, 5, 8, 2, 6, 3, 0, 1, 6]);
    // GR IV's Toning states: on red 1 / 3 / 2, on white 4 / 5 / 6, off 0, off remembering white 9.
    const toning = (h: { strength: 0 | 1 | 2 | 3; white?: boolean }) => gr3xFilmDefaultBytes({ halation: h })[7];
    expect([1, 2, 3].map(s => toning({ strength: s as 1 | 2 | 3 }))).toEqual([1, 3, 2]);
    expect([1, 2, 3].map(s => toning({ strength: s as 1 | 2 | 3, white: true }))).toEqual([4, 5, 6]);
    expect(toning({ strength: 0 })).toBe(0);
    expect(toning({ strength: 0, white: true })).toBe(9);
  });

  it('the Grain row: gold and orange Halation states and the grain amount in the Toning byte (h + 24 g)', () => {
    const toning = (h: { strength: 0 | 1 | 2 | 3; white?: boolean; gold?: boolean; orange?: boolean } | undefined, g = 0) => gr3xFilmDefaultBytes(h ? { halation: h } : undefined, g)[7];
    expect([1, 2, 3].map(s => toning({ strength: s as 1 | 2 | 3, gold: true }))).toEqual([12, 13, 14]);
    expect(toning({ strength: 0, gold: true })).toBe(15);
    expect([0, 1, 2, 3].map(g => toning(undefined, g))).toEqual([0, 24, 48, 72]);
    expect(toning({ strength: 3, gold: true }, 3)).toBe(86);
    expect([1, 2, 3].map(s => toning({ strength: s as 1 | 2 | 3, orange: true }))).toEqual([18, 19, 20]);
    expect(toning({ strength: 0, orange: true }, 3)).toBe(93);
    expect(toning({ strength: 2, white: true }, 1)).toBe(29);
    expect(() => validateGr3xFilmDefaults({ halation: { strength: 1, white: true, gold: true } })).toThrow();
    expect(() => gr3xFilmDefaultBytes(undefined, 4)).toThrow();
    // The grain a film starts from is part of its fingerprint (another start: the film starts again).
    expect(gr3xRecipePrint(0x12345678, undefined, 2)).not.toBe(gr3xRecipePrint(0x12345678, undefined, 1));
    expect(gr3xRecipePrint(0x12345678, undefined, 0)).toBe(0x12345678);
    expect(GR3X_FILMS_GRAIN_MODULE.bindings).toContain('film_defaults');
    for (let n = 1; n <= 20; n++) expect(GR3X_FILMS_GRAIN_MODULE.variants[n].exports).toHaveProperty('sp_grain_put');
  });

  it('refuses values the camera does not have', () => {
    expect(() => validateGr3xFilmDefaults({ sharpness: 5 })).toThrow();
    expect(() => validateGr3xFilmDefaults({ clarity: 1.5 })).toThrow();
    expect(() => validateGr3xFilmDefaults({ halation: { strength: 4 as 3 } })).toThrow();
    expect(() => validateGr3xFilmDefaults({ grain: 1 } as never)).toThrow();
    expect(() => validateGr3xFilmDefaults({ sharpness: -4, clarity: 4, halation: { strength: 3, white: true } })).not.toThrow();
  });

  it('a film without starting values keeps its colour fingerprint (older builds unchanged)', () => {
    expect(gr3xHasDefaults({ sharpness: 0, halation: { strength: 0 } })).toBe(false);
    expect(gr3xCanonicalDefaults({ sharpness: 0 })).toBeUndefined();
    expect(gr3xRecipePrint(0x12345678, undefined)).toBe(0x12345678);
    expect(gr3xRecipePrint(0x12345678, { sharpness: 0 })).toBe(0x12345678);
    const a = gr3xRecipePrint(0x12345678, { sharpness: 1 }), b = gr3xRecipePrint(0x12345678, { sharpness: 2 });
    expect(a).not.toBe(0x12345678);
    expect(a).not.toBe(b);
    expect(gr3xCanonicalDefaults({ sharpness: 1, clarity: 0, halation: { strength: 0, white: true } })).toEqual({ sharpness: 1, halation: { strength: 0, white: true } });
  });

  it('the recipe module exists for every film count, with the recipes bound', () => {
    expect(GR3X_FILMS_DEFAULTS_MODULE.bindings).toContain('film_defaults');
    for (let n = 1; n <= 20; n++) expect(GR3X_FILMS_DEFAULTS_MODULE.variants[n]).toBeDefined();
  });
});

describe('the film library', () => {
  it('has twenty films with names the camera takes, in four groups, with valid recipes', () => {
    expect(LOOKS.length).toBe(20);
    expect(new Set(LOOKS.map(l => l.name)).size).toBe(20);
    for (const l of LOOKS) {
      expect(l.name.length).toBeLessThanOrEqual(24);
      expect(/^[\x20-\x7e]+$/.test(l.name)).toBe(true);
      expect(['fujifilm', 'stock', 'oppo', 'creative']).toContain(l.group);
      expect(() => validateGr3xFilmDefaults(l.recipe?.defaults)).not.toThrow();
      if (l.recipe?.grain) expect([1, 2, 3]).toContain(l.recipe.grain.amount);
    }
  });

  it('every film fits GR III\'s format closely and draws its icon', () => {
    const tile = new Uint8Array(6400);
    for (let i = 0; i < 6400; i += 4) tile.set([53, 53, 54, 255], i);
    for (const l of LOOKS) {
      const c = convertGr3xCube(cubeText(l, 17), { post: true });
      expect(c.meanDE2000!, l.name).toBeLessThan(3.5);
      const icon = filmIcon(tile, l);
      expect(icon.length).toBe(6400);
      expect(icon.some((v, i) => v !== tile[i])).toBe(true);
    }
  }, 120000);
});

const firmware = process.env.GRMOD_GR3_FIRMWARE;
describe.skipIf(!firmware)('film recipes in a GR III 2.10 build', () => {
  const ratios = GR3X_T4_CUSTOM.map(r => ({ ratio: r.ratio, name: r.name ?? r.ratio }));
  const open = async () => Engine.open(new Uint8Array(readFileSync(firmware!)));

  it('builds, verifies and reads back every film\'s recipe; a build without recipes stays as before', async () => {
    const engine = await open();
    const requests = LOOKS.slice(0, 6).map((l, i) => {
      const r = engine.convertPreset('cube', cubeText(l, 17));
      return { slot: GR3X_FILM_IDS[i], names: { en: l.name }, preset: { matrixQ13: r.matrixQ13, curves: r.curves, ...(r.postQ9 ? { postQ9: r.postQ9 } : {}) },
        ...(l.recipe?.defaults ? { defaults: l.recipe.defaults } : {}), ...(l.recipe?.grain ? { grain: l.recipe.grain } : {}) };
    });
    const withRecipes = await engine.buildFirmware(requests, ratios, [], { filmCount: 6, adjSoftFocus: true, dateStamp: true });
    expect(Object.values(withRecipes.checks).every(v => v === true)).toBe(true);
    const summary = await (await open()).inspect(withRecipes.file);
    expect(summary.verified).toBe(true);
    summary.slots.forEach((s, i) => {
      expect(s.defaults ?? null).toEqual(gr3xCanonicalDefaults(LOOKS[i].recipe?.defaults) ?? null);
      expect(s.grain ?? null).toEqual(LOOKS[i].recipe?.grain ?? null);
    });
    // The same films without recipes: another file, verified, with no recipe in it.
    const plain = await engine.buildFirmware(requests.map(({ defaults: _d, grain: _g, ...r }) => r), ratios, [], { filmCount: 6, adjSoftFocus: true, dateStamp: true });
    expect(plain.sha256).not.toBe(withRecipes.sha256);
    const s2 = await (await open()).inspect(plain.file);
    expect(s2.verified).toBe(true);
    expect(s2.slots.every(s => !s.defaults && !s.grain)).toBe(true);
  }, 600000);

  it('the films\' Hue as their teal sky: verified, read back, and a build without it unchanged', async () => {
    const engine = await open();
    const requests = LOOKS.slice(0, 3).map((l, i) => {
      const r = engine.convertPreset('cube', cubeText(l, 17));
      return { slot: GR3X_FILM_IDS[i], preset: { matrixQ13: r.matrixQ13, curves: r.curves, ...(r.postQ9 ? { postQ9: r.postQ9 } : {}) }, ...(i === 1 ? { defaults: { hue: 2 } } : {}) };
    });
    // A film without a preset (Standard's colour) has its teal sky too.
    const options = { filmCount: 4, adjSoftFocus: true };
    const teal = await engine.buildFirmware(requests, ratios, [], { ...options, tealHue: true });
    expect(Object.values(teal.checks).every(v => v === true)).toBe(true);
    const summary = await (await open()).inspect(teal.file);
    expect(summary.verified).toBe(true);
    expect(summary.tealHue).toBe(true);
    expect(summary.slots[1].defaults).toEqual({ hue: 2 });
    const plain = await engine.buildFirmware(requests, ratios, [], options);
    expect(plain.sha256).not.toBe(teal.sha256);
    const s2 = await (await open()).inspect(plain.file);
    expect(s2.verified).toBe(true);
    expect(s2.tealHue).toBeUndefined();
    await expect(engine.buildFirmware(requests.slice(0, 1).map(({ defaults: _d, ...r }) => ({ ...r, slot: 'CY' as const })), ratios, [], { tealHue: true })).rejects.toThrow();
  }, 600000);

  it('the Grain row and gold Halation: verified, read back; they need a film count', async () => {
    const engine = await open();
    const requests = LOOKS.slice(0, 3).map((l, i) => {
      const r = engine.convertPreset('cube', cubeText(l, 17));
      return { slot: GR3X_FILM_IDS[i], preset: { matrixQ13: r.matrixQ13, curves: r.curves, ...(r.postQ9 ? { postQ9: r.postQ9 } : {}) },
        grain: { amount: i as 0 | 1 | 2, size: 'large' as const }, ...(i === 2 ? { defaults: { halation: { strength: 2 as const, gold: true } } } : {}) };
    });
    const options = { filmCount: 4, adjSoftFocus: true, dateStamp: true, tealHue: true };
    const build = await engine.buildFirmware(requests, ratios, [], { ...options, grainRow: true });
    expect(Object.values(build.checks).every(v => v === true)).toBe(true);
    const summary = await (await open()).inspect(build.file);
    expect(summary.verified).toBe(true);
    expect(summary.grainRow).toBe(true);
    expect(summary.slots[2].defaults).toEqual({ halation: { strength: 2, gold: true } });
    expect(summary.slots[1].grain).toEqual({ amount: 1, size: 'large' });
    // Gold needs the Grain row; the Grain row needs a film count.
    await expect(engine.buildFirmware(requests.slice(2), ratios, [], options)).rejects.toThrow(/gold/);
    await expect(engine.buildFirmware(requests.slice(0, 1).map(({ grain: _g, ...r }) => ({ ...r, slot: 'CY' as const })), ratios, [], { grainRow: true })).rejects.toThrow(/film count/);
  }, 600000);

  it('recipes need a film count (round 10), and only GR III / IIIx films have them', async () => {
    const engine = await open();
    await expect(engine.buildFirmware([{ slot: 'CY', defaults: { sharpness: 1 } }], ratios, [], {})).rejects.toThrow();
    await expect(engine.buildFirmware([{ slot: 'CY', grain: { amount: 1, size: 'small' } }], ratios, [], { filmCount: 2, gr3Round: 9 })).rejects.toThrow();
    await expect(engine.buildFirmware([{ slot: 'CY', defaults: { sharpness: 9 } }], ratios, [], { filmCount: 2 })).rejects.toThrow();
  }, 600000);
});
