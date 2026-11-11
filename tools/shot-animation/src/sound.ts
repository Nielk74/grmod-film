// Locally synthesized effects. Playback and audio export share the same score.
import {durationFor,scheduleSound} from '../sfx.mjs';
export {scoreFor} from '../sfx.mjs';

let context:AudioContext|undefined;
let playback:ReturnType<typeof scheduleSound>|undefined;
let generation=0;

export function stopSound(){
  generation++;
  playback?.stop();
  playback=undefined;
}

export async function playSound(kind:string,fromMs=0){
  stopSound();
  const offset=Number.isFinite(fromMs)?Math.max(0,fromMs):0;
  if(offset>=durationFor(kind))return;
  const requestedGeneration=generation;
  context??=new AudioContext();
  try{await context.resume();}
  catch(error){if(requestedGeneration===generation)throw error;return;}
  if(requestedGeneration!==generation)return;
  if(typeof document!=='undefined'&&document.hidden)return;
  playback=scheduleSound(context,kind,{fromMs:offset});
}

/** Stereo PCM at 48kHz, suitable for WAV encoding or video export. */
export async function renderSound(kind:string):Promise<AudioBuffer>{
  const sampleRate=48000;
  const offline=new OfflineAudioContext(2,Math.ceil(durationFor(kind)*sampleRate/1000),sampleRate);
  const scheduled=scheduleSound(offline,kind);
  try{return await offline.startRendering();}
  finally{scheduled.stop();}
}
