// The preview's sample photographs (assets/samples, credits in CREDITS.md there): genuine RICOH GR III
// JPEGs straight from the camera, shot with Image Control Standard, the rendering films are applied to.
import montmartre from './assets/samples/gr3-r0000023.jpg';
import basilica from './assets/samples/gr3-r0000022.jpg';
import path from './assets/samples/gr3-path.jpg';
import hill from './assets/samples/gr3-hill.jpg';
import stream from './assets/samples/gr3-stream.jpg';
import sign from './assets/samples/gr3-sign.jpg';
import type { Key } from './i18n';

/** `credit`: who took it and under which licence (shown over the preview). */
export interface Sample { id: string; url: string; label: Key; credit: string }

const COMMONS = 'Stephan van Helden · CC BY-SA 4.0';
export const SAMPLES: readonly Sample[] = [
  { id: 'gr3-montmartre', url: montmartre, label: 'sampleSteps', credit: 'GR Mod' },
  { id: 'gr3-basilica', url: basilica, label: 'sampleBasilica', credit: 'GR Mod' },
  { id: 'gr3-path', url: path, label: 'sampleForest', credit: COMMONS },
  { id: 'gr3-hill', url: hill, label: 'sampleHill', credit: COMMONS },
  { id: 'gr3-stream', url: stream, label: 'sampleStream', credit: COMMONS },
  { id: 'gr3-sign', url: sign, label: 'sampleSign', credit: COMMONS },
];
