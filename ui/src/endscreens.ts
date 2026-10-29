// GR Mod's own power-off pictures (720 x 480, drawn in code by examples/gr3x/film-pack/Pictures.cs),
// offered on the End Screen page in the order of the film pack's firmware.
import starTrails from './assets/endscreens/Star-Trails.png';
import filmStrip from './assets/endscreens/Film-Strip.png';
import contours from './assets/endscreens/Contours.png';
import aperture from './assets/endscreens/Aperture.png';
import synthwave from './assets/endscreens/Synthwave.png';
import bauhaus from './assets/endscreens/Bauhaus.png';
import greatWave from './assets/endscreens/Great-Wave.png';
import goodNight from './assets/endscreens/Good-Night.png';

export const END_SCREENS: readonly { name: string; url: string }[] = [
  { name: 'Star Trails', url: starTrails }, { name: 'Film Strip', url: filmStrip }, { name: 'Contours', url: contours }, { name: 'Aperture', url: aperture },
  { name: 'Synthwave', url: synthwave }, { name: 'Bauhaus', url: bauhaus }, { name: 'Great Wave', url: greatWave }, { name: 'Good Night', url: goodNight },
];
