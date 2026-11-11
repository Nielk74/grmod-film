// SPDX-License-Identifier: GPL-2.0-only
// The 20 films: packaging-inspired colours from core/src/filmpack/looks.ts (same ones the film icons use),
// the moment format (what the shot looks like) and the edge-print colour. Plain text names only.
import { LOOKS } from './films.gen.mjs';

/** Shot format by film: neg (colour negative), bw (black-and-white negative), slide, instant, cine. */
const KIND = {
  'Velvia': 'slide', 'Astia': 'slide', 'Classic Chrome': 'slide', 'Kodachrome 64': 'slide', 'Aerochrome': 'slide',
  'Acros': 'bw', 'Acros Red': 'bw', 'Platinum': 'bw',
  'Instant': 'instant',
  'CineStill 800T': 'cine', 'Eterna': 'cine', 'Blockbuster': 'cine',
};
/** Edge-print colour; defaults: amber for colour negative, white for b&w, ink colour otherwise. */
const EDGE = {
  'Portra 400': [255, 206, 64], 'Gold 200': [255, 176, 32], 'CineStill 800T': [255, 84, 60],
  'Eterna': [255, 150, 60], 'Blockbuster': [255, 178, 70],
};
/** Tab and cassette text: the 40 px icon captions are not a constraint here. */
const TEXT = { 'CineStill 800T': { caption: 'CINESTILL', code: '800T' } };
export const FILMS = LOOKS.map((l, i) => {
  const kind = KIND[l.name] || 'neg';
  const edge = EDGE[l.name] || (kind === 'bw' ? [236, 236, 230] : kind === 'neg' ? [255, 190, 60] : l.ink);
  return { index: i, name: l.name, group: l.group, caption: (TEXT[l.name] || l).caption, code: (TEXT[l.name] || l).code, kind, edge,
    panel: l.panel, band: l.band, ink: l.ink, captionInk: l.captionInk, label: l.name.toUpperCase() };
});
/** The camera's own looks (Standard, Vivid, ...) and any film this table does not know: a neutral negative strip. */
FILMS.push({ index: FILMS.length, name: 'GR III', group: 'camera', caption: 'GR III', code: 'STD', kind: 'neg', edge: [236, 236, 230],
  panel: [58, 60, 66], band: [150, 152, 158], ink: [255, 255, 255], captionInk: [24, 24, 28], label: 'GR III' });
export const NEUTRAL_FILM = FILMS.length - 1;
export const FOCUS = ['Portra 400', 'Gold 200', 'CineStill 800T'].map(n => FILMS.findIndex(f => f.name === n));
export const ROLL_LENGTH = 36;
