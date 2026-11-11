import test from 'node:test';
import assert from 'node:assert/strict';
import {playSound, stopSound} from '../src/sound.ts';
import * as sound from '../src/sound.ts';

test('a pending audio resume cannot play after cancellation',async()=>{
  let resume, starts=0, stops=0;const peaks=[];
  const parameter={setValueAtTime(){},exponentialRampToValueAtTime(){},linearRampToValueAtTime(value){peaks.push(value);}};
  class Context {
    currentTime=0;destination={};
    resume(){return new Promise(resolve=>{resume=resolve;});}
    createOscillator(){return{frequency:parameter,connect(){},disconnect(){},start(){starts++;},stop(){stops++;}};}
    createGain(){return{gain:parameter,connect(){},disconnect(){}};}
  }
  globalThis.AudioContext=Context;
  const pending=playSound('robot');stopSound();resume();await pending;
  assert.equal(starts,0);
  const next=playSound('robot');resume();await next;
  assert.equal(starts,8);
  assert.deepEqual(peaks,Array(8).fill(1));
  stopSound();assert.equal(stops,16); // scheduled ends plus explicit cancellation
  delete globalThis.AudioContext;
});

let fixtureId=0;
async function audioFixture(t) {
  const instances=[];
  class Parameter {
    value=0; events=[];
    setValueAtTime(value,at){assert.ok(at>=0);this.events.push({value,at,method:'set'});}
    linearRampToValueAtTime(value,at){assert.ok(at>=0);this.events.push({value,at,method:'linear'});}
    exponentialRampToValueAtTime(value,at){assert.ok(value>0);assert.ok(at>=0);this.events.push({value,at,method:'exponential'});}
  }
  class Node {
    connections=[];disconnected=false;
    connect(node){this.connections.push(node);return node;}
    disconnect(){this.disconnected=true;this.connections=[];}
  }
  class Source extends Node {
    frequency=new Parameter();playbackRate=new Parameter();starts=[];stops=[];
    constructor(kind){super();this.kind=kind;}
    start(at,offset=0){assert.ok(at>=0);this.starts.push({at,offset});}
    stop(at){this.stops.push(at);}
  }
  class Context {
    currentTime=10;sampleRate=24000;destination=new Node();sources=[];resumes=[];gains=[];
    constructor(){instances.push(this);}
    resume(){return new Promise((resolve,reject)=>this.resumes.push({resolve,reject}));}
    createOscillator(){const source=new Source('tone');this.sources.push(source);return source;}
    createBufferSource(){const source=new Source('noise');this.sources.push(source);return source;}
    createBuffer(channels,length,sampleRate){const data=Array.from({length:channels},()=>new Float32Array(length));return{numberOfChannels:channels,length,sampleRate,getChannelData:channel=>data[channel]};}
    createGain(){const node=new Node();node.gain=new Parameter();this.gains.push(node);return node;}
    createBiquadFilter(){const node=new Node();node.frequency=new Parameter();node.Q=new Parameter();return node;}
    createStereoPanner(){const node=new Node();node.pan=new Parameter();return node;}
    createDynamicsCompressor(){const node=new Node();for(const name of ['threshold','knee','ratio','attack','release'])node[name]=new Parameter();return node;}
  }
  const original=globalThis.AudioContext;
  globalThis.AudioContext=Context;
  const module=await import(`../src/sound.ts?audio-test=${++fixtureId}`);
  t.after(()=>{module.stopSound();if(original)globalThis.AudioContext=original;else delete globalThis.AudioContext;});
  return{module,instances};
}

// A default/legacy melody substituted for a new score loses both the noisy
// entrance and the precisely timed exit; these checks catch that regression.
test('dash authors noise and footsteps across its entrance and exit',async t=>{
  const {module,instances}=await audioFixture(t);
  const pending=module.playSound('dash'),context=instances[0];
  context.resumes[0].resolve();await pending;
  assert.ok(context.sources.some(source=>source.kind==='noise'),'dash needs synthesized texture');
  const onsets=context.sources.flatMap(source=>source.starts.map(start=>start.at));
  assert.ok(onsets.some(at=>Math.abs(at-10.12)<1e-6),'first footstep follows the visual at 120ms');
  assert.ok(onsets.some(at=>Math.abs(at-17.22)<1e-6),'last departing footstep follows the visual at 7220ms');
});

test('stopSound cancels pending new sequence resumes before creating any source',async t=>{
  const {module,instances}=await audioFixture(t);
  const pending=module.playSound('portal'),context=instances[0];
  module.stopSound();context.resumes[0].resolve();await pending;
  assert.equal(context.sources.length,0);
});

test('a newer play request supersedes an older pending resume',async t=>{
  const {module,instances}=await audioFixture(t);
  const old=module.playSound('dash'),context=instances[0];
  const current=module.playSound('portal');
  context.resumes[0].resolve();await old;
  assert.equal(context.sources.length,0);
  context.resumes[1].resolve();await current;
  const first=Math.min(...context.sources.flatMap(source=>source.starts.map(start=>start.at)));
  assert.ok(Math.abs(first-10.08)<1e-6,'only the portal opening at 80ms is scheduled');
});

test('mute or hidden cancellation stops buffer noise as well as oscillators',async t=>{
  const {module,instances}=await audioFixture(t);
  const pending=module.playSound('rocket'),context=instances[0];
  context.resumes[0].resolve();await pending;
  assert.ok(context.sources.some(source=>source.kind==='noise'));
  module.stopSound();
  for(const source of context.sources){
    assert.equal(source.stops.length,2,'a scheduled end and immediate cancellation are both registered');
    assert.equal(source.stops.at(-1),undefined);
    assert.equal(source.disconnected,true);
  }
  module.stopSound();
  assert.ok(context.sources.every(source=>source.stops.length===2),'repeated cancellation is harmless');
});

test('seeking schedules future footsteps at their remaining offsets',async t=>{
  const {module,instances}=await audioFixture(t);
  const pending=module.playSound('dash',7000),context=instances[0];
  context.resumes[0].resolve();await pending;
  const onsets=context.sources.flatMap(source=>source.starts.map(start=>start.at));
  assert.ok(onsets.every(at=>at>=10),'seeking never schedules a source in the past');
  assert.ok(onsets.some(at=>Math.abs(at-10.10)<1e-6));
  assert.ok(onsets.some(at=>Math.abs(at-10.22)<1e-6));
  assert.ok(onsets.every(at=>at<10.61),'old entrance/core cues are not replayed');
});

test('seeking within the rocket flight retains its already running jet',async t=>{
  const {module,instances}=await audioFixture(t);
  const pending=module.playSound('rocket',7200),context=instances[0];
  context.resumes[0].resolve();await pending;
  const noise=context.sources.filter(source=>source.kind==='noise');
  assert.ok(noise.some(source=>Math.abs(source.starts[0].at-10)<1e-6&&source.starts[0].offset>0),'resume the noise tail without replaying its attack');
});

test('replaying a score recreates exactly the same synthesized noise buffers',async t=>{
  const {module,instances}=await audioFixture(t);
  const first=module.playSound('rocket'),context=instances[0];
  context.resumes[0].resolve();await first;
  const buffers=context.sources.filter(source=>source.kind==='noise').map(source=>source.buffer.getChannelData(0));
  assert.ok(buffers.length>0);
  const nextIndex=context.sources.length;
  const second=module.playSound('rocket');context.resumes[1].resolve();await second;
  const replay=context.sources.slice(nextIndex).filter(source=>source.kind==='noise').map(source=>source.buffer.getChannelData(0));
  assert.deepEqual(replay,buffers);
});

test('an ended sequence never requests an audio resume',async t=>{
  const {module,instances}=await audioFixture(t);
  const pending=module.playSound('rocket',7600);
  instances[0]?.resumes[0].resolve();await pending;
  assert.equal(instances.length,0);
});

test('a rejected resume from a cancelled request cannot fail a newer playback',async t=>{
  const {module,instances}=await audioFixture(t);
  const stale=module.playSound('dash'),context=instances[0];
  const current=module.playSound('rocket');
  context.resumes[0].reject(new Error('old resume failed'));
  await assert.doesNotReject(stale);
  context.resumes[1].resolve();await current;
  assert.ok(context.sources.length>0);
});

test('a tab hidden during resume cannot start sources after resume completes',async t=>{
  const {module,instances}=await audioFixture(t);
  const original=globalThis.document;
  t.after(()=>{if(original)globalThis.document=original;else delete globalThis.document;});
  globalThis.document={hidden:false};
  const pending=module.playSound('portal'),context=instances[0];
  globalThis.document.hidden=true;
  context.resumes[0].resolve();await pending;
  assert.equal(context.sources.length,0);
});

test('unknown legacy sound names retain the default melody even for inherited object keys',async t=>{
  const {module,instances}=await audioFixture(t);
  const pending=module.playSound('toString'),context=instances[0];
  context.resumes[0].resolve();await assert.doesNotReject(pending);
  assert.equal(context.sources.length,5);
});

test('offline export is available for the same sounds used by playback',()=>{
  assert.equal(typeof sound.renderSound,'function');
});
