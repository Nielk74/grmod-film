import test from 'node:test';
import assert from 'node:assert/strict';
import sharp from 'sharp';
import {fileURLToPath} from 'node:url';
import {neonRgba} from '../palette.mjs';

test('neon grading preserves sprite geometry, alpha and the source pixels',async()=>{
  const source=new URL('../src/assets/terminal-actions-v5-master.png',import.meta.url);
  const {data,info}=await sharp(fileURLToPath(source)).ensureAlpha().raw().toBuffer({resolveWithObject:true});
  const original=Buffer.from(data),graded=neonRgba(data);
  assert.deepEqual(data,original,'the original artwork must remain reusable');
  assert.equal(graded.length,info.width*info.height*4);
  let changed=0;
  for(let i=0;i<data.length;i+=4){
    assert.equal(graded[i+3],data[i+3],`alpha changed at pixel ${i/4}`);
    if(data[i+3]===0||Math.max(...data.subarray(i,i+3))<24)
      assert.deepEqual(Buffer.from(graded.subarray(i,i+4)),data.subarray(i,i+4),'padding and black ink must survive');
    if(graded[i]!==data[i]||graded[i+1]!==data[i+1]||graded[i+2]!==data[i+2])changed++;
  }
  assert.ok(changed>10000,'the visible palette must actually change');
});

test('neon accents brighten the face, sneakers and photo while retaining charcoal and ivory',()=>{
  const input=Uint8Array.from([
    152,200,48,255, 248,96,0,255, 164,112,151,255,
    32,48,32,255, 72,64,64,255, 248,224,200,255,
  ]);
  const p=neonRgba(input),pixel=i=>Array.from(p.subarray(i*4,i*4+3));
  const [r,g,b]=pixel(0);
  assert.ok(g>=245&&g-r>=80&&b<=24,'acid lime must remain distinct from warm ivory');
  assert.ok(pixel(1)[0]>=250&&pixel(1)[1]<96,'sneakers need fluorescent orange');
  assert.ok(Math.max(...pixel(2))-Math.min(...pixel(2))>150,'the photo needs a saturated accent');
  assert.ok(Math.max(...pixel(3))<35,'dark emerald glass keeps the face legible');
  assert.deepEqual(pixel(4),[72,64,64],'the charcoal case is the identity anchor');
  assert.ok(pixel(5)[0]>=248&&pixel(5)[1]>=224&&pixel(5)[2]>=200,'ivory stays warm and light');
});
