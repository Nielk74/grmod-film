import test from 'node:test';
import assert from 'node:assert/strict';
import {encodeAnimation,decodeAnimation,crc32} from '../codec.mjs';

const frame=()=>new Uint8Array([255,128,64,255, 255,128,64,255, 0,0,0,0, 0,255,0,128]);
const encode=()=>encodeAnimation({width:2,height:2,fps:20,frames:Array.from({length:100},frame)});

test('100 frames encode exactly five seconds with preserved alpha and quantized RGB',()=>{
  const bytes=encode(), decoded=decodeAnimation(bytes);
  assert.equal(decoded.durationMs,5000);assert.equal(decoded.frames.length,100);
  assert.deepEqual([...decoded.frames[0]], [255,130,66,255,255,130,66,255,0,0,0,0,0,255,0,136]);
});
test('payload corruption is rejected before decoding',()=>{
  const bytes=encode();bytes[bytes.length-1]^=1;
  assert.throws(()=>decodeAnimation(bytes),/CRC/);
});
test('truncated assets, invalid counts, offsets and runs are rejected',()=>{
  const bytes=encode();
  assert.throws(()=>decodeAnimation(bytes.slice(0,-1)),/size/);
  for(const [position,value,message] of [[4,2,/version/],[10,0,/timing/],[12,0,/timing/],[14,1,/reserved/],[28,0,/table/]]){
    const corrupt=bytes.slice();new DataView(corrupt.buffer).setUint16(position,value,true);
    assert.throws(()=>decodeAnimation(corrupt),message);
  }
  const broken=bytes.slice(),view=new DataView(broken.buffer);
  view.setUint32(32,broken.length+1,true);view.setUint32(24,crc32(broken.subarray(32)),true);
  assert.throws(()=>decodeAnimation(broken),/offset/);
  const run=bytes.slice(),rv=new DataView(run.buffer);const start=rv.getUint32(32,true);
  rv.setUint16(start,0,true);rv.setUint32(24,crc32(run.subarray(32)),true);
  assert.throws(()=>decodeAnimation(run),/run/);
});
test('malformed input dimensions and timing are rejected at export',()=>{
  assert.throws(()=>encodeAnimation({width:2,height:2,fps:20,frames:[frame()]}),/five seconds/);
  assert.throws(()=>encodeAnimation({width:0,height:2,fps:20,frames:Array.from({length:100},frame)}),/dimensions/);
  assert.throws(()=>encodeAnimation({width:2,height:2,fps:20,frames:Array.from({length:100},()=>new Uint8Array(3))}),/RGBA/);
});
test('canonical CRC32 check vector',()=>assert.equal(crc32(new TextEncoder().encode('123456789')),0xcbf43926));
