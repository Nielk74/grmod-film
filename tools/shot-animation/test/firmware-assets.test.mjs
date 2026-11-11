import test from 'node:test';
import assert from 'node:assert/strict';
import {encodeTerminalAsset,readTerminalAsset,motionSample,crc32} from '../firmware-assets.mjs';

function fixture(){
  const palette=[[0,0,0,0],[155,255,25,255],[255,81,10,120]];
  const indices=new Uint8Array(128*128*12);
  for(let pose=0;pose<12;pose++)indices[pose*16384+128*64+64]=1+pose%2;
  const polygon={color:[155,255,25,180],points:[[100,100],[108,100],[104,108]]};
  const samples=['dash','portal','rocket'].map(id=>Array.from({length:228},(_,frame)=>({
    ...motionSample(frame*1000/30,id),back:frame%3?[polygon]:[],front:[],
  })));
  return{palette,indices,samples};
}

test('firmware assets share twelve original indexed poses and all three complete timelines',()=>{
  const source=fixture(),before=source.indices.slice();
  const a=encodeTerminalAsset(source),decoded=readTerminalAsset(a);
  assert.deepEqual(source.indices,before);
  assert.deepEqual(decoded.indices,source.indices);
  assert.deepEqual(decoded.palette,source.palette);
  assert.equal(decoded.sampleCount,228);
  assert.equal(decoded.durationMs,7600);
  assert.deepEqual(decoded.phases,[1400,5000,1200]);
  assert.equal(decoded.trackBytes,3*228*52);
  assert.ok(a.length<235000,'shared geometry must not become stored raster frames');
  assert.deepEqual(encodeTerminalAsset(source),a,'the build must be deterministic');
});

test('inverse motion retains the approved travel and pose facing',()=>{
  const dash=motionSample(400,'dash');
  assert.equal(dash.pose,7);
  // Hand-checked:120+185-175*(400/650), at the start of its fifth stride.
  const [a,b,c,d,tx,ty]=dash.inverse;
  assert.ok(Math.abs((a*197.307692+c*168+tx)/65536-64)<.02);
  assert.ok(Math.abs((b*197.307692+d*168+ty)/65536-128)<.02);
  for(const id of ['dash','portal','rocket']){
    const p=motionSample(7000,id);
    assert.equal(p.facing,id==='portal'?1:-1);
    assert.ok(p.bounds.every(Number.isInteger));
    assert.ok(p.inverse.every(Number.isInteger));
  }
});

test('corrupt native offsets, palettes and vector extents fail before rendering',()=>{
  const good=encodeTerminalAsset(fixture());
  const change=edit=>{const b=good.slice();const v=new DataView(b.buffer);edit(b,v);v.setUint32(64,crc32(b.subarray(80)),true);return b;};
  assert.throws(()=>readTerminalAsset(good.subarray(0,good.length-1)),/length|size/);
  const broken=good.slice();broken[broken.length-1]^=1;
  assert.throws(()=>readTerminalAsset(broken),/CRC/);
  assert.throws(()=>readTerminalAsset(change((b,v)=>v.setUint32(52,0xfffffff0,true))),/offset|layout/);
  assert.throws(()=>readTerminalAsset(change((b,v)=>{b[v.getUint32(48,true)]=254;})),/palette index/);
  assert.throws(()=>readTerminalAsset(change((b,v)=>{v.setUint32(v.getUint32(52,true)+36,0xfffffff0,true);})),/vector/);
  assert.throws(()=>encodeTerminalAsset({...fixture(),indices:new Uint8Array(2)}),/indices|pose/);
});
