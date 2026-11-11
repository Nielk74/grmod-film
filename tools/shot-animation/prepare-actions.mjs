import sharp from 'sharp';
import {copyFile,writeFile,mkdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {neonRgba} from './palette.mjs';
const here=path.dirname(fileURLToPath(import.meta.url));
const source=process.argv[2]||path.join(here,'src/assets/terminal-actions-v5-master.png');
const target=path.join(here,'src/assets/terminal-actions-v5-master.png');
await mkdir(path.join(here,'out'),{recursive:true});
if(path.resolve(source)!==target)await copyFile(source,target);
const meta=await sharp(target).metadata();
if(!meta.hasAlpha||meta.width/meta.height!==1.5)throw Error('Expected transparent 3 × 2 square-pose atlas');
const tiles=[],masters=[];
for(let row=0;row<2;row++)for(let col=0;col<3;col++){
  const cell=await sharp(target).extract({left:col*meta.width/3,top:row*meta.height/2,width:meta.width/3,height:meta.height/2}).png().toBuffer();
  const {data,info}=await sharp(cell).ensureAlpha().raw().toBuffer({resolveWithObject:true});
  let left=info.width,top=info.height,right=0,bottom=0;
  for(let y=0;y<info.height;y++)for(let x=0;x<info.width;x++)if(data[(y*info.width+x)*4+3]>=96){
    left=Math.min(left,x);right=Math.max(right,x);top=Math.min(top,y);bottom=Math.max(bottom,y);
  }
  const crop=await sharp(cell).extract({left,top,width:right-left+1,height:bottom-top+1}).ensureAlpha().raw().toBuffer();
  const cut=await sharp(neonRgba(crop),{raw:{width:right-left+1,height:bottom-top+1,channels:4}}).png().toBuffer();
  // Keep pose proportions, put both strides and the airborne poses on the same
  // baseline as the existing art. This is sprite registration, not repainting.
  const master=await sharp({create:{width:512,height:512,channels:4,background:'#00000000'}})
    .composite([{input:cut,left:Math.round((512-(right-left+1))/2),top:500-(bottom-top+1)}]).png().toBuffer();
  masters.push(master);tiles.push(await sharp(master).resize(128,128).png().toBuffer());
}
await sharp({create:{width:1536,height:1024,channels:4,background:'#00000000'}})
  .composite(masters.map((input,i)=>({input,left:(i%3)*512,top:Math.floor(i/3)*512})))
  .png().toFile(path.join(here,'src/assets/terminal-actions-v5-normalized.png'));
const strip=await sharp({create:{width:128,height:768,channels:4,background:'#00000000'}})
  .composite(tiles.map((input,i)=>({input,left:0,top:i*128})))
  .png({palette:true,colours:64,dither:0,effort:10}).toBuffer();
await writeFile(path.join(here,'src/assets/terminal-actions-v5.png'),strip);
await sharp(path.join(here,'src/assets/terminal-actions-v5-normalized.png')).flatten({background:'#f5f2e9'}).resize(900,600).png().toFile(path.join(here,'out/actions-contact.png'));
console.log(JSON.stringify({poses:6,pngBytes:strip.length,rawIndexedBytes:128*128*6,transparent:true}));
