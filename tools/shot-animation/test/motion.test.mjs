import test from 'node:test';
import assert from 'node:assert/strict';
import {motionAt,DURATION_MS,ACT_DURATION_MS,ENTER_MS,LEAVE_MS} from '../timing.mjs';

test('entrance and exit extend the five-second performance to 5.7 seconds',()=>{
  assert.equal(ACT_DURATION_MS,5000);assert.equal(ENTER_MS,350);assert.equal(LEAVE_MS,350);assert.equal(DURATION_MS,5700);
  assert.deepEqual(motionAt(0),{active:true,actMs:0,y:14,opacity:0,scaleX:1,scaleY:1});
  assert.deepEqual(motionAt(350),{active:true,actMs:0,y:0,opacity:1,scaleX:1,scaleY:1});
  const exit=motionAt(5350);assert.equal(exit.active,true);assert.equal(exit.actMs,4999);assert.equal(exit.opacity,1);
  assert.equal(motionAt(5525).opacity,128/255);assert.ok(motionAt(5525).y>0);
  assert.equal(motionAt(5700).active,false);assert.equal(motionAt(5700).opacity,0);
});
test('three transition suggestions share exactly the same five-second acting window',()=>{
  for(const variant of [0,1,2])for(const ms of [350,800,950,1800,3300,3850,5349]){
    const state=motionAt(ms,variant);
    assert.equal(state.actMs,ms-350);assert.equal(state.y,0);assert.equal(state.opacity,1);
    assert.equal(state.scaleX,1);assert.equal(state.scaleY,1);
  }
  assert.ok(motionAt(225,1).y<0);
  assert.ok(motionAt(50,2).scaleY<.1);
  for(const variant of [0,1,2])assert.equal(motionAt(5700,variant).active,false);
});
