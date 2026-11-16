import test from 'node:test';
import assert from 'node:assert/strict';
import {encodePoses,decodePoses} from '../poses.mjs';
import {crc32} from '../codec.mjs';

test('three shared-palette poses cost about 49 KiB at 128 square',()=>{
  const poses=Array.from({length:3},(_,p)=>new Uint8Array(128*128*4).map((_,i)=>i%4===3?255:i%4===0?p*80:0));
  const bytes=encodePoses({width:128,height:128,poses});
  assert.ok(bytes.length<50000);
  const decoded=decodePoses(bytes);
  assert.deepEqual(decoded.keyTimes,[0,1650,3350]);
  assert.equal(decoded.durationMs,5000);
  assert.equal(decoded.poses.length,3);
  assert.equal(decoded.poses[1][0],82);
  assert.equal(decoded.poses[1][3],255);
});
test('corrupt compact palettes and indices are rejected',()=>{
  const poses=Array.from({length:3},()=>new Uint8Array(4));
  const bytes=encodePoses({width:1,height:1,poses});
  const corrupt=bytes.slice();corrupt[corrupt.length-1]^=1;
  assert.throws(()=>decodePoses(corrupt),/CRC/);
  assert.throws(()=>decodePoses(bytes.slice(0,-1)),/size/);
  assert.throws(()=>encodePoses({width:1,height:1,poses:[poses[0]],keyTimes:[0,1]}),/timing/);
  const fixCRC=buffer=>new DataView(buffer.buffer).setUint32(24,crc32(buffer.subarray(32)),true);
  const badIndex=bytes.slice();badIndex[badIndex.length-1]=255;fixCRC(badIndex);
  assert.throws(()=>decodePoses(badIndex),/palette index/);
  const badAlpha=bytes.slice();badAlpha[34]=1;fixCRC(badAlpha);
  assert.throws(()=>decodePoses(badAlpha),/palette alpha/);
  const badTimes=bytes.slice();new DataView(badTimes.buffer).setUint32(36,1,true);fixCRC(badTimes);
  assert.throws(()=>decodePoses(badTimes),/key times/);
});
