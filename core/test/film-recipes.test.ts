// SPDX-License-Identifier: GPL-2.0-only
// GR Mod's film recipes (GR III / IIIx round 10: camera defaults and grain) and the film library.
// The build tests need the official GR III 2.10 file (GRMOD_GR3_FIRMWARE); the rest runs without it.
import { existsSync, readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
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
import { encodeGr3xLookRecipe, readGr3xLookRecipe } from '../src/fw/gr3x/look-recipe';

describe('crop texture recipe policy', () => {
  it('round trips explicit policies and refuses invalid policy values', () => {
    const base = { displayRevision: 3 as const, ownParameters: true, filmCount: 1, films: [{ name: 'Texture' }] };
    for (const textureGeometry of ['sensor', 'output'] as const) {
      expect(readGr3xLookRecipe(encodeGr3xLookRecipe({ ...base, textureGeometry }))?.textureGeometry).toBe(textureGeometry);
    }
    expect(readGr3xLookRecipe(encodeGr3xLookRecipe(base))?.textureGeometry).toBeUndefined();
    expect(() => encodeGr3xLookRecipe({ ...base, textureGeometry: 'bad' as never })).toThrow(/geometry/i);
    const malformed = encodeGr3xLookRecipe({ ...base, textureGeometry: 'sensor' });
    const bytes = Buffer.from(malformed), at = bytes.indexOf('sensor');
    bytes.write('broken', at, 'utf8');
    expect(() => readGr3xLookRecipe(bytes)).toThrow(/recipe/);
  });
});

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

  it('reconstructs the pre-WP2 R10 MTF/grain/gold fixture exactly and reads each explicit policy', async () => {
    const engine = await open();
    const requests = [{ slot: GR3X_FILM_IDS[0], names: { en: 'WP2 legacy' }, grain: { amount: 2 as const, size: 'large' as const }, filmMtf: true, defaults: { halation: { strength: 2 as const, gold: true } } }];
    const options = { filmCount: 1, adjSoftFocus: true, dateStamp: true, grainRow: true };
    const legacy = await engine.buildFirmware(requests, ratios, [], options);
    // Captured against db76c9b before any source/module changes; includes all three native payloads.
    expect(legacy.sha256).toBe('c25f45439dbd1ea3dd339bd59400bf5a1d698043dd610e2425c11f8acbc7faf1');
    expect((await engine.inspect(legacy.file)).verified).toBe(true);
    for (const textureGeometry of ['sensor', 'output'] as const) {
      const built = await engine.buildFirmware(requests, ratios, [], { ...options, textureGeometry });
      const summary = await engine.inspect(built.file);
      expect(summary.verified).toBe(true); expect(summary.textureGeometry).toBe(textureGeometry);
      expect(built.sha256).not.toBe(legacy.sha256);
    }
    await expect(engine.buildFirmware(requests, ratios, [], { ...options, textureGeometry: 'bad' as never })).rejects.toThrow(/geometry/);
    await expect(engine.buildFirmware(requests, ratios, [], { ...options, textureGeometry: 'sensor', gr3Round: 9 })).rejects.toThrow(/round 10/);
  }, 600000);

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

  it('the film MTF: put into the JPEG stage, verified, read back; a build without it differs; it needs a film count', async () => {
    const engine = await open();
    const requests = LOOKS.slice(0, 3).map((l, i) => {
      const r = engine.convertPreset('cube', cubeText(l, 17));
      return { slot: GR3X_FILM_IDS[i], preset: { matrixQ13: r.matrixQ13, curves: r.curves, ...(r.postQ9 ? { postQ9: r.postQ9 } : {}) }, ...(i === 1 ? { filmMtf: true } : {}) };
    });
    const options = { filmCount: 4, adjSoftFocus: true, dateStamp: true, tealHue: true, grainRow: true };
    const build = await engine.buildFirmware(requests, ratios, [], options);
    expect(Object.values(build.checks).every(v => v === true)).toBe(true);
    const summary = await (await open()).inspect(build.file);
    expect(summary.verified).toBe(true);
    expect(summary.slots.map(s => s.filmMtf === true)).toEqual([false, true, false, false]);
    const plain = await engine.buildFirmware(requests.map(({ filmMtf: _f, ...r }) => r), ratios, [], options);
    expect(plain.sha256).not.toBe(build.sha256);
    const s2 = await (await open()).inspect(plain.file);
    expect(s2.verified).toBe(true);
    expect(s2.slots.every(s => s.filmMtf === undefined)).toBe(true);
    await expect(engine.buildFirmware([{ slot: 'CY', filmMtf: true }], ratios, [], {})).rejects.toThrow();
  }, 600000);

  it('recipes need a film count (round 10), and only GR III / IIIx films have them', async () => {
    const engine = await open();
    await expect(engine.buildFirmware([{ slot: 'CY', defaults: { sharpness: 1 } }], ratios, [], {})).rejects.toThrow();
    await expect(engine.buildFirmware([{ slot: 'CY', grain: { amount: 1, size: 'small' } }], ratios, [], { filmCount: 2, gr3Round: 9 })).rejects.toThrow();
    await expect(engine.buildFirmware([{ slot: 'CY', defaults: { sharpness: 9 } }], ratios, [], { filmCount: 2 })).rejects.toThrow();
  }, 600000);
});


describe('approved Gold optional data', () => {
  const metadata = { family: 'gr3x', version: '2.10', filename: 'fwdc239b.bin', models: ['GR3', 'GR3_HDF'], bridge: false,
    sha256: 'd6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4', capabilities: { build: true, presets: true },
    standardMatrixQ13: [8116,743,-667,15,8598,-421,-244,542,7894] };
  const moduleUrl = new URL('../../ui/src/approved-gold.ts', import.meta.url);
  const get = async () => { expect(existsSync(moduleUrl), 'tracked approved-Gold factory is required').toBe(true); return import(moduleUrl.href); };
  const packed = (r: any) => {
    const values = [...r.matrixQ13, ...r.curves[0], ...r.curves[1], ...r.curves[2], ...r.postQ9];
    const bytes = new Uint8Array(values.length * 2), view = new DataView(bytes.buffer);
    values.forEach((v, i) => view.setUint16(i * 2, v & 65535, true)); return bytes;
  };
  it('returns the canonical compiled bytes and saved parameters, without changing the default twenty', async () => {
    const gold = await get(), r = gold.createApprovedGold(metadata as any, 'GR3_HDF')!;
    expect(r.matrixQ13).toHaveLength(9); expect(r.postQ9).toHaveLength(9); expect(r.curves).toHaveLength(3); r.curves.forEach((c: Uint16Array) => expect(c).toHaveLength(256));
    expect(r.params.M1.map((row: number[]) => row.length)).toEqual([3,3,3]); expect(r.params.ck.map((row: Float64Array) => row.length)).toEqual([17,17,17]); expect(r.params.P2!.map((row: number[]) => row.length)).toEqual([3,3,3]);
    const bytes = packed(r); expect(bytes.length).toBe(1572);
    expect(createHash('sha256').update(bytes).digest('hex')).toBe('91158f03a8e83fb36563c1ddc9ef8907b153ff6e47a21f8101827a6b92a7fdb6');
    const expected = {"M1":[[1.0609664581572797,-0.1236873931405216,0.06272093498324176],[0.0560144493881397,0.8473464964015793,0.0966390542102809],[0.13797423545573362,-0.07980902853238755,0.941834793076654]],"ck":[[0.0896157357467401,0.10186681865578108,0.1275010833350745,0.16835926269378026,0.21606341947486327,0.28608917156902997,0.35737156811339066,0.436805031935872,0.5278015788515321,0.6126637381905242,0.6741237730846269,0.7359538986702452,0.7759715577678598,0.8167140072018888,0.85035003278829,0.8877568210279086,0.899241661868901],[0.025493786603441204,0.06589139404379141,0.10845788327856759,0.15528898175161074,0.2128458084539915,0.27531961650663567,0.3476096931185396,0.4146862516636111,0.5046143346561357,0.5944529255640608,0.6669200469353677,0.7199554988191725,0.773146224334547,0.8134273426538644,0.8492566988244435,0.8809501064267611,0.9055369615373172],[0.11440001574401118,0.11617403260174636,0.13682385536862623,0.1672921304560454,0.21089427222481755,0.2682959517868168,0.3305544865061938,0.40043904711415673,0.46907789026519764,0.5439393474841399,0.6103610278042597,0.6614225407136135,0.7062177421416,0.7542530416281723,0.7919774829224516,0.8337094204511402,0.8413941773594036]],"P2":[[1.0845477569965989,0.09357736525447909,-0.1781251222510779],[0.13747820587674173,0.7984581039948029,0.06406369012845536],[0.01201115567272517,0.12165093430130737,0.8663379100259675]]};
    expect({ ...r.params, ck: r.params.ck.map((c: Float64Array) => Array.from(c)) }).toEqual(expected);
    expect(gold.matchesApprovedGold(r)).toBe(true); expect(gold.cie76Fit(r)).toBeUndefined();
    expect(r.meanDE).toBeUndefined(); expect(r.p95DE).toBeUndefined();
    expect(LOOKS.map(l => l.name)).toEqual(['Velvia','Astia','Classic Chrome','Classic Neg','Nostalgic Neg','Pro Neg Hi','Pro Neg Std','Eterna','Acros','Acros Red','Kodachrome 64','Portra 400','Gold 200','CineStill 800T','Primrose','Hasselblad Std','Aerochrome','Instant','Blockbuster','Platinum']);
    expect(createHash('sha256').update(readFileSync(new URL('../src/filmpack/looks.ts', import.meta.url),'utf8').replace(/\r\n/g,'\n')).digest('hex')).toBe('b0e551076d29234006cbd595aaa0835b74b19b5d9430faab3cf3ccccf7a364dd');
  });
  it('owns all nested arrays and rejects actual incomplete or mutated data', async () => {
    const gold = await get(); const a = gold.createApprovedGold(metadata as any, 'GR3')!, b = gold.createApprovedGold(metadata as any, 'GR3')!;
    for (const array of [a.matrixQ13, ...a.curves, a.postQ9!, ...a.params.M1, ...a.params.ck, ...a.params.P2!]) array[0] += 1;
    expect(gold.matchesApprovedGold(a)).toBe(false); expect(gold.matchesApprovedGold(b)).toBe(true);
    expect(gold.matchesApprovedGold({ ...b, curves: [b.curves[0].slice(1), ...b.curves.slice(1)] })).toBe(false);
    expect(gold.matchesApprovedGold({ ...b, postQ9: undefined })).toBe(false);
    expect(gold.matchesApprovedGold({ ...b, params: { ...b.params, P2: undefined } })).toBe(false);
    expect(gold.matchesApprovedGold({ ...b, params: { ...b.params, hue: [[1,0,0],[0,1,0],[0,0,1]] } })).toBe(false);
    expect(gold.matchesApprovedGold({ ...b, hueQ10: [1] })).toBe(false);
  });
  it('requires the exact official profile and Standard reference rather than shared-family similarity', async () => {
    const gold = await get();
    for (const [info, model] of [[undefined, 'GR3'], [metadata, 'GR3X'], [{ ...metadata, sha256: 'a'.repeat(64) }, 'GR3'], [{ ...metadata, version: '2.20' }, 'GR3'], [{ ...metadata, filename: 'other.bin' }, 'GR3'], [{ ...metadata, standardMatrixQ13: Array(9).fill(0) }, 'GR3'], [{ ...metadata, capabilities: { build: true, presets: false } }, 'GR3'], [{ ...metadata, bridge: true }, 'GR3']]) {
      expect(gold.createApprovedGold(info as any, model as any)).toBeUndefined();
    }
    expect(gold.createApprovedGold(metadata as any, 'GR3')).toBeDefined();
  });
});
