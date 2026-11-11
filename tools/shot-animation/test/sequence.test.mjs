import test from 'node:test';
import assert from 'node:assert/strict';
import {sequenceAt,ENTER_MS,LEAVE_MS,DURATION_MS,ACT_DURATION_MS,SEQUENCE_IDS} from '../sequence.mjs';

test('travel faces its destination, including turning toward the return portal',()=>{
  for(const ms of [100,400,700])assert.equal(sequenceAt(ms,'dash').facing,-1);
  for(const ms of [100,400,700,6650,7000,7200])assert.equal(sequenceAt(ms,'rocket').facing,-1);
  for(const ms of [400,700])assert.equal(sequenceAt(ms,'portal').facing,-1);
  for(const ms of [6650,6800,7000,7200])assert.equal(sequenceAt(ms,'portal').facing,1);
  for(const ms of [6650,7000,7200])assert.equal(sequenceAt(ms,'dash').facing,-1);
  for(const id of SEQUENCE_IDS)assert.equal(sequenceAt(1400,id).facing,1);
});

test('authored actions surround an uninterrupted five-second performance',()=>{
  assert.equal(ACT_DURATION_MS,5000);
  assert.equal(ENTER_MS,1400);assert.equal(LEAVE_MS,1200);assert.equal(DURATION_MS,7600);
  for(const id of SEQUENCE_IDS){
    assert.equal(sequenceAt(ENTER_MS,id).phase,'act');
    assert.equal(sequenceAt(ENTER_MS+4999,id).phase,'act');
    assert.equal(sequenceAt(ENTER_MS+5000,id).phase,'exit');
    assert.equal(sequenceAt(DURATION_MS,id).active,false);
  }
});

test('entering and leaving use illustrated action poses and visible travel',()=>{
  for(const id of SEQUENCE_IDS){
    const entry=Array.from({length:42},(_,i)=>sequenceAt(i*1000/30,id));
    const exit=Array.from({length:36},(_,i)=>sequenceAt(6400+i*1000/30,id));
    assert.ok(new Set(entry.map(s=>s.pose)).size>=3,`${id} entry poses`);
    assert.ok(new Set(exit.map(s=>s.pose)).size>=3,`${id} exit poses`);
    assert.ok(entry.some(s=>Math.abs(s.x)>80||Math.abs(s.y)>60),`${id} entry travel`);
    assert.ok(exit.some(s=>Math.abs(s.x)>80||Math.abs(s.y)>60),`${id} exit travel`);
    assert.ok(entry.some(s=>s.scaleY<.85),`${id} landing squash`);
  }
});

test('seeking backwards or across variants gives the same frame and core acting',()=>{
  for(const id of SEQUENCE_IDS){
    const first=sequenceAt(760,id);
    sequenceAt(7200,id);sequenceAt(0,id);
    assert.deepEqual(sequenceAt(760,id),first);
  }
  for(const t of [1400,1850,2000,2850,4350,4900,6399]){
    const frames=SEQUENCE_IDS.map(id=>sequenceAt(t,id));
    for(const frame of frames.slice(1))assert.deepEqual(frame,frames[0]);
  }
});

test('all timeline samples have finite transforms and a valid cached pose',()=>{
  for(const id of SEQUENCE_IDS)for(let ms=0;ms<=DURATION_MS;ms+=25){
    const s=sequenceAt(ms,id);
    for(const key of ['x','y','rotation','scaleX','scaleY','opacity'])assert.ok(Number.isFinite(s[key]),`${id}:${ms}:${key}`);
    assert.ok(s.pose>=0&&s.pose<12&&Number.isInteger(s.pose));
    assert.ok(s.opacity>=0&&s.opacity<=1);
    assert.ok(s.scaleX>0&&s.scaleY>0);
  }
});
