import test from 'node:test';
import assert from 'node:assert/strict';
import {encodePoses,decodePoses} from '../poses.mjs';
import {crc32} from '../codec.mjs';

const keyTimes=[0,450,600,1450,2950,3500];
test('six acting frames stay under 100 KB and preserve their irregular timing',()=>{
  const poses=Array.from({length:6},(_,p)=>new Uint8Array(128*128*4).map((_,i)=>i%4===3?255:i%4===0?p*40:0));
  const bytes=encodePoses({width:128,height:128,poses,keyTimes});
  assert.ok(bytes.length<100000);
  const decoded=decodePoses(bytes);
  assert.deepEqual(decoded.keyTimes,keyTimes);
  assert.equal(decoded.poses.length,6);
  assert.equal(decoded.durationMs,5000);
});
test('duplicate, out of order, late and mismatched pose times are rejected',()=>{
  const poses=Array.from({length:6},()=>new Uint8Array(4));
  for(const times of [[0,450],[0,450,450,1450,2950,3500],[1,450,600,1450,2950,3500],[0,450,600,1450,2950,5000]]){
    assert.throws(()=>encodePoses({width:1,height:1,poses,keyTimes:times}),/timing|key times/);
  }
  const bytes=encodePoses({width:1,height:1,poses,keyTimes});
  const view=new DataView(bytes.buffer),colors=view.getUint16(12,true);
  view.setUint32(32+colors*4+4,0,true);view.setUint32(24,crc32(bytes.subarray(32)),true);
  assert.throws(()=>decodePoses(bytes),/key times/);
});
