import test from 'node:test';
import assert from 'node:assert/strict';
import sharp from 'sharp';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const root=path.dirname(path.dirname(fileURLToPath(import.meta.url)));

test('blink padding is transparent above the antenna, without removing the antenna',async()=>{
  const frame=await sharp(path.join(root,'src/assets/diskette-terminal-v4.png'))
    .extract({left:0,top:128,width:128,height:128}).ensureAlpha().raw().toBuffer();
  const alphaAt=(x,y)=>frame[(y*128+x)*4+3];
  for(let y=0;y<3;y++)for(let x=0;x<128;x++)assert.equal(alphaAt(x,y),0,`neighboring shoe pixel at ${x},${y}`);
  assert.ok(Array.from({length:128*15},(_,i)=>alphaAt(i%128,3+Math.floor(i/128))).some(a=>a>128),'the antenna must remain visible');
  const large=await sharp(path.join(root,'src/assets/terminal-core-v5/core-1-512.png')).ensureAlpha().raw().toBuffer();
  for(let i=0;i<512*12;i++)assert.equal(large[i*4+3],0,'high-resolution frame padding must also be isolated');
});
