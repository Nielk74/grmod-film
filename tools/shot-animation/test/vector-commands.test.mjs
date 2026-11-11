import test from 'node:test';
import assert from 'node:assert/strict';
import {pathContours,strokePolygons} from '../vector-commands.mjs';

test('separate sparkle/portal subpaths never acquire connecting strokes',()=>{
  const contours=pathContours('M174 61v12m-6-6h12M190 84v8m-4-4h8');
  assert.equal(contours.length,4);
  assert.deepEqual(contours.map(c=>c.points),[
    [[174,61],[174,73]],[[168,67],[180,67]],[[190,84],[190,92]],[[186,88],[194,88]],
  ]);
  const strokes=contours.flatMap(c=>strokePolygons(c.points,2,[],0,'butt'));
  assert.equal(strokes.length,4);
  assert.ok(strokes.every(p=>Math.max(...p.map(v=>v[0]))-Math.min(...p.map(v=>v[0]))<=12));
});

test('curved filled exhaust closes and portal dash gaps stay open',()=>{
  const contours=pathContours('M-8 0Q-12 15 0 30Q11 13.5 8 0Z');
  assert.equal(contours.length,1);
  assert.equal(contours[0].closed,true);
  assert.deepEqual(contours[0].points[0],[-8,0]);
  assert.deepEqual(contours[0].points.at(-1),[-8,0]);
  const dashed=strokePolygons([[0,0],[20,0]],2,[4,4],0,'butt');
  assert.equal(dashed.length,3);
  assert.deepEqual(dashed.map(p=>[Math.min(...p.map(v=>v[0])),Math.max(...p.map(v=>v[0]))]),[[0,4],[8,12],[16,20]]);
});
