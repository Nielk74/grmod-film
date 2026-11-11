import mint from './assets/diskette-mint-v4.png';
import amber from './assets/diskette-amber-v4.png';
import terminal from './assets/diskette-terminal-v4.png';
import master from './assets/diskette-atlas-v4.png';
import {KEY_TIMES,POSE_COUNT,DURATION_MS,motionAt} from '../timing.mjs';

export const DURATION=DURATION_MS;
export const keyTimes=KEY_TIMES;
type Props={ms:number;large?:boolean;transition?:number};
function Sprite({ms,src,label,column,large,transition=0}: Props&{src:string;label:string;column:number}) {
  const motion=motionAt(ms,transition);
  const pose=KEY_TIMES.reduce((index,start,current)=>motion.actMs>=start?current:index,0);
  return <svg xmlns="http://www.w3.org/2000/svg" width="240" height="176" viewBox="0 0 240 176" className="tile-svg mascot-tile" aria-label={label} role="img">
    <g opacity={motion.opacity} transform={`translate(120 ${168+motion.y}) scale(${motion.scaleX} ${motion.scaleY}) translate(-120 -168)`}>
      <svg x={large?36:56} y={large?6:40} width={large?168:128} height={large?168:128} viewBox={large?'0 0 512 512':'0 0 128 128'} overflow="hidden">
        {large?<image href={master} width="1536" height={POSE_COUNT*512} x={-column*512} y={-pose*512} preserveAspectRatio="none"/>:<image href={src} width="128" height={POSE_COUNT*128} y={-pose*128}/>}
      </svg>
    </g>
  </svg>;
}
const Mint=(props:Props)=><Sprite {...props} column={0} src={mint} label="Mint Diskette: warm cream CRT with mint floppy and orange sneakers"/>;
const Amber=(props:Props)=><Sprite {...props} column={1} src={amber} label="Amber Diskette: rounded cream CRT with amber screen and twin antennae"/>;
const Terminal=(props:Props)=><Sprite {...props} column={2} src={terminal} label="Terminal Diskette: charcoal CRT with green pixel face and cream floppy"/>;
export const characterExperiments=[
  {id:'mint',name:'Diskette Mint',skill:'16-colour indexed sprite',caption:'Closest to the one you picked. Cream shell, mint floppy, orange sneakers. A very proud little computer.',Component:Mint,cue:'Pocket Lab sound',color:'#83ad87',personality:'The original / warm & cheeky'},
  {id:'amber',name:'Diskette Amber',skill:'16-colour indexed sprite',caption:'A rounder cousin with twin antennae and a warm amber screen. Same attitude, a little more mellow.',Component:Amber,cue:'Pocket Lab sound',color:'#dda746',personality:'The mellow one / warm amber'},
  {id:'terminal',name:'Diskette Terminal',skill:'16-colour indexed sprite',caption:'Charcoal casing, green pixel grin, cream floppy. The one who definitely has a home server.',Component:Terminal,cue:'Pocket Lab sound',color:'#9caf66',personality:'The hacker / pixel grin'},
] as const;
const Dock=(props:Props)=><Terminal {...props} transition={0}/>;
const Hop=(props:Props)=><Terminal {...props} transition={1}/>;
const Boot=(props:Props)=><Terminal {...props} transition={2}/>;
export const experiments=[
  {id:'dock',name:'Soft Dock',skill:'Your character: Terminal',caption:'Rises into its corner with a soft settle, then gently dips away. Quiet, quick and polished.',Component:Dock,cue:'Pocket Lab · 100%',color:'#9caf66',personality:'Slide in / dip out'},
  {id:'hop',name:'Tiny Hop',skill:'Your character: Terminal',caption:'A small overshoot on arrival, a little lift before leaving. More playful, with the same six acting frames.',Component:Hop,cue:'Pocket Lab · 100%',color:'#9caf66',personality:'Pop in / hop out'},
  {id:'boot',name:'CRT Boot',skill:'Your character: Terminal',caption:'Expands from a thin scan line, performs its little routine, then collapses back into a line.',Component:Boot,cue:'Pocket Lab · 100%',color:'#9caf66',personality:'Boot up / power down'},
] as const;
