import test from 'node:test';
import assert from 'node:assert/strict';
import * as sequence from '../sequence.mjs';

test('every shuffled set contains all three transitions, without back-to-back repeats',()=>{
  assert.equal(typeof sequence.createTransitionPicker,'function');
  for(const draw of [0,.18,.55,.999999]){
    const next=sequence.createTransitionPicker(()=>draw),shots=Array.from({length:90},()=>next());
    for(let i=0;i<shots.length;i+=3)assert.deepEqual([...shots.slice(i,i+3)].sort(),[...sequence.SEQUENCE_IDS].sort());
    for(let i=1;i<shots.length;i++)assert.notEqual(shots[i],shots[i-1]);
  }
});

test('the random source controls the order rather than a fixed cycle',()=>{
  assert.equal(typeof sequence.createTransitionPicker,'function');
  const a=sequence.createTransitionPicker(()=>0),b=sequence.createTransitionPicker(()=>.999999);
  assert.notDeepEqual(Array.from({length:3},()=>a()),Array.from({length:3},()=>b()));
});
