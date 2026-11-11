import {gsap} from 'gsap';
import {KEY_TIMES} from './timing.mjs';

export const ENTER_MS=1400;
export const ACT_DURATION_MS=5000;
export const LEAVE_MS=1200;
export const DURATION_MS=ENTER_MS+ACT_DURATION_MS+LEAVE_MS;
export const FPS=30;
export const SEQUENCE_IDS=Object.freeze(['dash','portal','rocket']);
const base={x:0,y:0,rotation:0,scaleX:1,scaleY:1,opacity:1,pose:0,facing:1};
const cache=new Map();
// Artwork has authored views: running, landing and crouching face left;
// the photo routine, airborne pose and flight pose face right.
const authoredFacing=Object.freeze([1,1,1,1,1,1,-1,-1,1,-1,-1,1]);
export function poseMirror(pose,facing){return (authoredFacing[pose]??1)*(facing<0?-1:1);}

export function createTransitionPicker(random=()=>Math.random()){
  let bag=[],previous;
  return()=>{
    if(!bag.length){
      bag=[...SEQUENCE_IDS];
      for(let i=bag.length-1;i>0;i--){const j=Math.floor(random()*(i+1));[bag[i],bag[j]]=[bag[j],bag[i]];}
      if(bag[0]===previous){const j=1+Math.floor(random()*(bag.length-1));[bag[0],bag[j]]=[bag[j],bag[0]];}
    }
    previous=bag.shift();return previous;
  };
}

// Paused object timelines are sampled by the shared playhead. No autonomous
// tween can outlive pause, scrub, another shutter press or a hidden page.
function choreography(id){
  const s={...base},tl=gsap.timeline({paused:true,defaults:{ease:'power2.out'}});
  const set=(at,vars)=>tl.set(s,vars,at);
  const to=(at,duration,vars)=>tl.to(s,{...vars,duration},at);
  set(0,{...base,opacity:0});
  if(id==='dash'){
    set(0,{x:185,y:0,rotation:-13,scaleX:1.04,scaleY:.96,opacity:1,pose:6,facing:-1});
    to(0,.65,{x:10,ease:'none'});
    for(let i=0;i<8;i++){
      set(i*.08,{pose:6+i%2});
      to(i*.08,.04,{y:-5,ease:'power1.out'});
      to(i*.08+.04,.04,{y:0,ease:'power1.in'});
    }
    set(.65,{pose:9});
    to(.65,.16,{x:-14,y:7,rotation:12,scaleX:1.18,scaleY:.74,ease:'power1.out'});
    set(.84,{pose:8});
    to(.84,.15,{x:4,y:-17,rotation:-8,scaleX:.94,scaleY:1.08});
    to(.99,.18,{x:0,y:0,rotation:0,scaleX:1,scaleY:1});
    to(1.17,.05,{scaleX:.18});set(1.22,{facing:1});to(1.22,.13,{scaleX:1});
    set(1.2,{pose:0});
    set(6.4,{...base,pose:5});
    to(6.4,.16,{rotation:-7,y:-3});
    to(6.4,.1,{scaleX:.18});set(6.5,{facing:-1});to(6.5,.07,{scaleX:1});
    set(6.57,{pose:10});
    to(6.57,.19,{y:6,rotation:-10,scaleY:.8,scaleX:1.1,ease:'power2.in'});
    set(6.78,{pose:6,scaleY:.97,scaleX:1.04});
    to(6.78,.54,{x:-205,y:-5,rotation:-16,ease:'power2.in'});
    for(let i=0;i<7;i++)set(6.78+i*.075,{pose:6+i%2});
  }else if(id==='portal'){
    set(0,{x:54,y:-40,rotation:-155,scaleX:.12,scaleY:.12,pose:8,opacity:0,facing:-1});
    set(.28,{opacity:1});
    to(.28,.42,{x:6,y:-68,rotation:15,scaleX:.8,scaleY:.8,ease:'power2.out'});
    to(.7,.2,{x:0,y:0,rotation:-8,scaleX:1,scaleY:1,ease:'power2.in'});
    set(.9,{pose:9});
    to(.9,.09,{y:7,rotation:3,scaleX:1.18,scaleY:.72,ease:'power1.out'});
    set(1,{pose:8});
    to(1,.14,{y:-13,rotation:-4,scaleX:.95,scaleY:1.07});
    to(1.14,.08,{y:0,rotation:0,scaleX:1,scaleY:1});
    to(1.22,.05,{scaleX:.18});set(1.27,{facing:1});to(1.27,.1,{scaleX:1});
    set(1.35,{pose:0});
    set(6.4,{...base,pose:5});
    to(6.4,.16,{rotation:7,y:-3});
    set(6.58,{pose:10});
    to(6.58,.16,{y:7,rotation:12,scaleX:1.12,scaleY:.8,ease:'power2.in'});
    set(6.75,{pose:8});
    to(6.75,.23,{x:17,y:-70,rotation:45,scaleX:.8,scaleY:.88});
    to(6.98,.29,{x:55,y:-38,rotation:125,scaleX:.12,scaleY:.12,ease:'power2.in'});
    set(7.28,{opacity:0});
  }else{
    set(0,{x:178,y:-105,rotation:-35,scaleX:.9,scaleY:1.07,pose:11,opacity:1,facing:-1});
    to(.12,.56,{x:18,y:-28,rotation:9,ease:'power2.out'});
    to(.68,.16,{x:0,y:0,rotation:-5,ease:'power1.in'});
    set(.84,{pose:9});
    to(.84,.1,{y:7,rotation:4,scaleX:1.19,scaleY:.72});
    set(.96,{pose:8});
    to(.96,.15,{y:-15,rotation:-5,scaleX:.94,scaleY:1.08});
    to(1.11,.09,{y:0,rotation:0,scaleX:1,scaleY:1});
    to(1.2,.06,{scaleX:.18});set(1.26,{facing:1});to(1.26,.11,{scaleX:1});
    set(1.35,{pose:0});
    set(6.4,{...base,pose:5});
    to(6.4,.15,{rotation:6});
    to(6.4,.08,{scaleX:.18});set(6.48,{facing:-1});to(6.48,.07,{scaleX:1});
    set(6.55,{pose:10});
    to(6.55,.35,{y:8,scaleX:1.13,scaleY:.77,rotation:-4,ease:'power2.in'});
    set(6.92,{pose:11});
    to(6.92,.08,{y:-9,scaleX:.91,scaleY:1.14,rotation:12});
    to(7,.43,{x:-95,y:-250,rotation:12,ease:'power2.in'});
  }
  set(7.6,{opacity:0});
  tl.pause(0);return{s,tl};
}

export function sequenceAt(ms,id='portal'){
  ms=Number.isFinite(ms)?Math.max(0,ms):DURATION_MS;
  if(ms>=DURATION_MS)return{...base,active:false,phase:'done',phaseMs:0,actMs:4999,opacity:0};
  const actMs=Math.max(0,Math.min(4999,ms-ENTER_MS));
  if(ms>=ENTER_MS&&ms<ENTER_MS+ACT_DURATION_MS){
    const pose=KEY_TIMES.reduce((result,time,index)=>actMs>=time?index:result,0);
    const breath=Math.sin(actMs/310)*.6;
    return{...base,active:true,phase:'act',phaseMs:actMs,actMs,pose,y:breath,rotation:Math.sin(actMs/680)*.45};
  }
  if(!SEQUENCE_IDS.includes(id))id='portal';
  if(!cache.has(id))cache.set(id,choreography(id));
  const {s,tl}=cache.get(id);tl.seek(ms/1000,true);
  const values=Object.fromEntries(Object.keys(base).map(key=>[key,Math.round(s[key]*100000)/100000]));
  return{...base,...values,active:true,phase:ms<ENTER_MS?'enter':'exit',phaseMs:ms<ENTER_MS?ms:ms-6400,actMs};
}

export function phaseLabel(ms){
  return ms<ENTER_MS?'Entrance':ms<ENTER_MS+ACT_DURATION_MS?'Five-second routine':ms<DURATION_MS?'Exit':'Finished';
}
