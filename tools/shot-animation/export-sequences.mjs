import sharp from 'sharp';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {SEQUENCE_IDS,ENTER_MS,ACT_DURATION_MS,LEAVE_MS,DURATION_MS,FPS,sequenceAt,poseMirror} from './sequence.mjs';
import {scoreFor} from './sfx.mjs';
const here=path.dirname(fileURLToPath(import.meta.url)),out=path.join(here,'out');
await mkdir(out,{recursive:true});
const core=await readFile(path.join(here,'src/assets/diskette-terminal-v4.png'));
const action=await readFile(path.join(here,'src/assets/terminal-actions-v5.png'));
const bank=await sharp({create:{width:128,height:1536,channels:4,background:'#00000000'}})
  .composite([{input:core,left:0,top:0},{input:action,left:0,top:768}])
  .png({palette:true,colours:64,dither:0,effort:10}).toBuffer();
await writeFile(path.join(out,'terminal-pose-bank.png'),bank);
const raw=await sharp(bank).ensureAlpha().raw().toBuffer(),palette=[],lookup=new Map(),indices=Buffer.alloc(128*128*12);
for(let i=0;i<indices.length;i++){
  const p=Array.from(raw.subarray(i*4,i*4+4)),key=p.join(',');
  if(!lookup.has(key)){lookup.set(key,palette.length);palette.push(p);}
  indices[i]=lookup.get(key);
}
if(palette.length>256)throw Error('Palette exceeded one-byte indices');
await writeFile(path.join(out,'terminal-pose-bank.indices'),indices);
await writeFile(path.join(out,'terminal-pose-bank.palette.json'),JSON.stringify(palette));
const tracks=Object.fromEntries(SEQUENCE_IDS.map(id=>[id,Array.from({length:Math.ceil(DURATION_MS*FPS/1000)+1},(_,i)=>{
  const ms=Math.min(DURATION_MS,i*1000/FPS),s=sequenceAt(ms,id);
  return{ms:Math.round(ms),pose:s.pose,x:Math.round(s.x*256),y:Math.round(s.y*256),rotation:Math.round(s.rotation*256),scaleX:Math.round(s.scaleX*256),scaleY:Math.round(s.scaleY*256),opacity:Math.round(s.opacity*255),facing:s.facing,mirrorX:poseMirror(s.pose,s.facing)};
})]));
await writeFile(path.join(out,'terminal-motion-tracks.json'),JSON.stringify({format:'Terminal motion study v1',units:'Q8 pixel/degree/scales; opacity u8',tracks}));
await writeFile(path.join(out,'terminal-sound-cues.json'),JSON.stringify(Object.fromEntries(SEQUENCE_IDS.map(id=>[id,scoreFor(id)])),null,2));
const report={character:'Terminal',sequences:SEQUENCE_IDS,selection:'random shuffled sets of three; no immediate repeats',enterMs:ENTER_MS,performanceMs:ACT_DURATION_MS,leaveMs:LEAVE_MS,durationMs:DURATION_MS,fps:FPS,cachedPoses:12,width:128,height:128,pngBytes:bank.length,paletteColors:palette.length,indexedSpriteBytes:indices.length+palette.length*4,renderedVideoFramesStored:0,cameraAdapterVerified:false,nativePrototype:'Earlier 350 ms transitions only; does not implement the new action choreography.'};
await writeFile(path.join(out,'sequence-export.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
