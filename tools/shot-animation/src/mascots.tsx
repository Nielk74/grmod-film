import {useLayoutEffect,useMemo,useRef} from 'react';
import {gsap} from 'gsap';
import {Player,type PlayerRef} from '@remotion/player';
import {Easing,interpolate,useCurrentFrame,useVideoConfig} from 'remotion';
import atlas from './assets/nerd-atlas-v2.png';

export const DURATION=5000;
export const FPS=20;
export const FRAME_COUNT=100;
const clamp=(value:number)=>Math.max(0,Math.min(1,value));
const alpha=(ms:number)=>clamp(ms/250)*clamp((5000-ms)/350);
const pose=(ms:number)=>ms<1450?0:ms<2350?1:ms<3350?2:3;

function Character({column,ms,y=0,rotation=0,scale=1}: {column:number;ms:number;y?:number;rotation?:number;scale?:number}) {
  const row=pose(ms);
  return <svg className="tile-svg mascot-tile" xmlns="http://www.w3.org/2000/svg" width="240" height="176" viewBox="0 0 240 176" role="img" aria-label={['Eccentric scientist inspecting and approving your photo','Retro CRT creature inspecting and approving your photo','Tactile purple nerd inspecting and approving your photo'][column]}>
    <g opacity={alpha(ms)} transform={`translate(120 ${166+y}) rotate(${rotation}) scale(${scale}) translate(-120 -166)`}>
      <svg x="38" y="7" width="164" height="164" viewBox="0 0 512 512" overflow="hidden">
        <image href={atlas} x={-column*512} y={-row*512} width="1536" height="2048" preserveAspectRatio="none"/>
      </svg>
    </g>
  </svg>;
}

// A: GSAP's actual playhead controls an asymmetric squash, recoil and settle.
function Scientist({ms}: {ms:number}) {
  const a=useMemo(()=>{
    const values={y:18,rotation:-7,scale:.93};
    const timeline=gsap.timeline({paused:true});
    timeline.to(values,{y:0,rotation:0,scale:1,duration:.5,ease:'power3.out'},0)
      .to(values,{rotation:-3,y:2,duration:.65,ease:'sine.inOut'},.65)
      .to(values,{y:-3,rotation:3,scale:1.015,duration:.17,ease:'power3.out'},1.45)
      .to(values,{y:0,rotation:0,scale:1,duration:.35,ease:'power2.out'},1.62)
      .to(values,{y:3,rotation:-2,duration:.25,ease:'power2.in'},2.1)
      .to(values,{y:-3,rotation:2,scale:1.015,duration:.24,ease:'power3.out'},2.35)
      .to(values,{y:0,rotation:0,scale:1,duration:.45,ease:'power3.out'},2.59)
      .to(values,{rotation:-2,duration:.3,ease:'sine.inOut'},3.35)
      .to(values,{rotation:0,duration:.3,ease:'sine.inOut'},3.65)
      .to(values,{y:8,scale:.98,duration:.35,ease:'power2.in'},4.65);
    return {values,timeline};
  },[]);
  useLayoutEffect(()=>()=>{a.timeline.kill();},[a]);
  a.timeline.time(ms/1000,false);
  return <Character column={0} ms={ms} {...a.values}/>;
}

// B: Remotion derives the complete performance from the current exported frame.
function CRTComposition() {
  const frame=useCurrentFrame(),{fps}=useVideoConfig(),ms=frame/fps*1000;
  return <Character column={1} ms={ms}
    y={interpolate(frame,[0,.5*fps,1.45*fps,1.65*fps,2.15*fps,2.35*fps,2.6*fps,3.1*fps,4.65*fps,5*fps],[16,0,0,-2,0,3,-3,0,0,7],{extrapolateLeft:'clamp',extrapolateRight:'clamp',easing:Easing.bezier(.16,1,.3,1)})}
    rotation={interpolate(frame,[0,.5*fps,1.2*fps,1.45*fps,1.8*fps,2.35*fps,2.7*fps,3.35*fps,3.7*fps,4.1*fps],[-5,0,-3,3,0,-3,2,0,-2,0],{extrapolateLeft:'clamp',extrapolateRight:'clamp',easing:Easing.bezier(.16,1,.3,1)})}
    scale={interpolate(frame,[0,.5*fps,1.45*fps,1.7*fps,2.35*fps,2.6*fps,3*fps],[.94,1,1.015,1,.97,1.015,1],{extrapolateLeft:'clamp',extrapolateRight:'clamp',easing:Easing.bezier(.16,1,.3,1)})}/>;
}
function CRT({ms}: {ms:number}) {
  const ref=useRef<PlayerRef>(null);
  useLayoutEffect(()=>{ref.current?.seekTo(Math.min(99,Math.floor(ms/50)));},[ms]);
  return <Player ref={ref} component={CRTComposition} durationInFrames={100} fps={20} compositionWidth={240} compositionHeight={176} controls={false} autoPlay={false} style={{width:240,height:176,background:'transparent',visibility:ms>=5000?'hidden':'visible'}}/>;
}

// C: Impeccable's single focal beat, implemented with a seekable native animation.
function Toy({ms}: {ms:number}) {
  const root=useRef<HTMLDivElement>(null),animation=useRef<Animation>();
  useLayoutEffect(()=>{
    const a=root.current!.animate([
      {transform:'translateY(16px) rotate(-5deg) scale(.94)',offset:0},
      {transform:'translateY(0) rotate(0) scale(1)',offset:.1},
      {transform:'translateY(2px) rotate(-2deg) scale(1)',offset:.27},
      {transform:'translateY(-2px) rotate(3deg) scale(1.015)',offset:.31},
      {transform:'translateY(0) rotate(0) scale(1)',offset:.39},
      {transform:'translateY(3px) rotate(-2deg) scale(.98)',offset:.46},
      {transform:'translateY(-3px) rotate(2deg) scale(1.015)',offset:.51},
      {transform:'translateY(0) rotate(0) scale(1)',offset:.62},
      {transform:'translateY(0) rotate(-2deg) scale(1)',offset:.7},
      {transform:'translateY(0) rotate(0) scale(1)',offset:.79},
      {transform:'translateY(0) rotate(0) scale(1)',offset:.93},
      {transform:'translateY(8px) rotate(0) scale(.98)',offset:1}
    ],{duration:5000,fill:'both',easing:'cubic-bezier(.16,1,.3,1)'});
    a.pause();animation.current=a;return()=>a.cancel();
  },[]);
  useLayoutEffect(()=>{if(animation.current)animation.current.currentTime=ms;},[ms]);
  return <div ref={root} style={{width:240,height:176,transformOrigin:'50% 95%'}}><Character column={2} ms={ms}/></div>;
}

export const experiments=[
  {id:'film',name:'Professor Halide',skill:'GSAP · Ink Sketch',caption:'A wild-haired darkroom obsessive. Suspicious of every photon. Ridiculously proud of this one.',Component:Scientist,cue:'Pocket Lab sound',color:'#ef8e3c',personality:'Eccentric / hand-inked'},
  {id:'robot',name:'Diskette',skill:'Remotion · Bold Pop',caption:'A little CRT with a big opinion. Inspects the evidence, then delivers a very smug thumbs-up.',Component:CRT,cue:'Pocket Lab sound',color:'#83ad87',personality:'Deadpan / retro computer'},
  {id:'focus',name:'Grain Goblin',skill:'WAAPI · tactile 3D',caption:'An overcaffeinated photo gremlin. Huge glasses, tiny teeth, and absolutely no chill.',Component:Toy,cue:'Pocket Lab sound',color:'#9f7da2',personality:'Mischievous / vinyl toy'},
] as const;
