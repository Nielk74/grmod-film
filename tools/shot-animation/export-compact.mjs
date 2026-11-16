import sharp from 'sharp';
import {mkdir,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {encodePoses,decodePoses} from './poses.mjs';
import {KEY_TIMES,POSE_COUNT,ENTER_MS,LEAVE_MS,DURATION_MS} from './timing.mjs';
import {neonRgba} from './palette.mjs';

const here=path.dirname(fileURLToPath(import.meta.url)),out=path.join(here,'out');
const artwork=path.join(here,'src/assets');
await mkdir(out,{recursive:true});
const coreFrames=path.join(artwork,'terminal-core-v5');
await mkdir(coreFrames,{recursive:true});
const source=path.join(artwork,'diskette-atlas-v4.png');
const metadata=await sharp(source).metadata();
const report={performanceMs:5000,enterMs:ENTER_MS,leaveMs:LEAVE_MS,durationMs:DURATION_MS,width:128,height:128,poses:POSE_COUNT,keyTimes:KEY_TIMES,spriteUploads:POSE_COUNT,variants:[]};
for(const [column,name] of ['mint','amber','terminal'].entries()){
  const inputs=[];
  for(let row=0;row<POSE_COUNT;row++){
    const left=Math.round(column*metadata.width/3),top=Math.round(row*metadata.height/POSE_COUNT);
    const right=Math.round((column+1)*metadata.width/3),bottom=Math.round((row+1)*metadata.height/POSE_COUNT);
    let frame=await sharp(source).extract({left,top,width:right-left,height:bottom-top}).png().toBuffer();
    if(name==='terminal'&&row===1){
      // The source blink cell includes the preceding pose's shoe edges. Its
      // first three native-pixel rows are padding, before the antenna starts.
      const guard=Math.ceil((bottom-top)*3/128);
      frame=await sharp(frame).extract({left:0,top:guard,width:right-left,height:bottom-top-guard})
        .extend({top:guard,bottom:0,left:0,right:0,background:'#00000000'}).png().toBuffer();
    }
    if(name==='terminal'){
      const {data,info}=await sharp(frame).ensureAlpha().raw().toBuffer({resolveWithObject:true});
      frame=await sharp(neonRgba(data),{raw:{width:info.width,height:info.height,channels:4}}).png().toBuffer();
      await sharp(frame).resize(512,512).png().toFile(path.join(coreFrames,`core-${row}-512.png`));
    }
    inputs.push(await sharp(frame).resize(128,128,{fit:'contain',background:{r:0,g:0,b:0,alpha:0}}).png().toBuffer());
  }
  const strip=await sharp({create:{width:128,height:128*POSE_COUNT,channels:4,background:{r:0,g:0,b:0,alpha:0}}})
    .composite(inputs.map((input,row)=>({input,left:0,top:row*128})))
    .png({palette:true,colours:64,dither:0,effort:10}).toBuffer();
  const rgba=await sharp(strip).ensureAlpha().raw().toBuffer();
  const poses=Array.from({length:POSE_COUNT},(_,row)=>rgba.subarray(row*128*128*4,(row+1)*128*128*4));
  const bytes=encodePoses({width:128,height:128,poses,keyTimes:KEY_TIMES}),decoded=decodePoses(bytes);
  const quantized=Buffer.concat(decoded.poses.map(p=>Buffer.from(p)));
  await sharp(quantized,{raw:{width:128,height:128*POSE_COUNT,channels:4}}).png({palette:true,colours:64,dither:0,effort:10}).toFile(path.join(artwork,`diskette-${name}-v4.png`));
  if(name==='terminal')for(let row=0;row<POSE_COUNT;row++)await sharp(decoded.poses[row],{raw:{width:128,height:128,channels:4}})
    .png().toFile(path.join(coreFrames,`core-${row}-128.png`));
  await writeFile(path.join(out,`diskette-${name}.gsp`),bytes);
  await sharp(decoded.poses[POSE_COUNT-1],{raw:{width:128,height:128,channels:4}}).png().toFile(path.join(out,`diskette-${name}-poster.png`));
  report.variants.push({name,assetBytes:bytes.length,paletteColors:decoded.colors,posePixels:128*128*POSE_COUNT,
    reductionFromPreviousDiskettePercent:Math.round((1-bytes.length/6679126)*10000)/100});
}
await writeFile(path.join(out,'compact-verification.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
