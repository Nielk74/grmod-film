import {useLayoutEffect, useMemo, useRef} from 'react';
import {gsap} from 'gsap';
import {Player, type PlayerRef} from '@remotion/player';
import {Easing, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';
import {Badge, cream, gold, ink, mint, coral, Print, Robot, Spark, Tile} from './artwork';

export const DURATION = 5000;
export const FPS = 20;
export const FRAME_COUNT = 100;
const clamp = (v:number) => Math.max(0, Math.min(1,v));
const fade = (ms:number) => clamp(ms/280) * clamp((5000-ms)/350);

// Experiment A: actual seekable GSAP timeline. No wall clock or random particles.
export function FilmTransport({ms}: {ms:number}) {
  const animation = useMemo(() => {
    const state = {reel:0, film:0, printY:93, printA:0, stamp:0, latch:0};
    const timeline = gsap.timeline({paused:true});
    timeline.to(state,{reel:360, film:36, duration:1.8,ease:'power2.inOut'},.35)
      .to(state,{printA:1,duration:.12},1.8)
      .to(state,{printY:52,duration:1.1,ease:'power3.out'},1.85)
      .to(state,{stamp:1,duration:.18,ease:'power3.in'},3.05)
      .to(state,{stamp:0,duration:.35,ease:'power3.out'},3.23)
      .to(state,{latch:1,duration:.25,ease:'power3.out'},3.3)
      .to({}, {duration:.1},4.9);
    return {state,timeline};
  },[]);
  useLayoutEffect(() => () => {animation.timeline.kill();},[animation]);
  animation.timeline.time(ms/1000, false);
  const s=animation.state;
  return <Tile label="Film Transport: tiny mechanical film processor">
    <g opacity={fade(ms)} transform={`translate(0 ${10*(1-fade(ms))})`}>
      <ellipse cx="121" cy="153" rx="88" ry="6" fill={ink} opacity=".18"/>
      <rect x="35" y="62" width="171" height="80" rx="14" fill="url(#metal)" stroke="#131e20" strokeWidth="2"/>
      <path d="M46 68h146" stroke="#65746c" strokeWidth="2" strokeLinecap="round"/>
      <rect x="47" y="78" width="147" height="33" rx="4" fill="#111c1e"/>
      <g transform={`translate(${-s.film%12} 0)`}>{Array.from({length:14},(_,i)=><g key={i}><rect x={48+i*12} y="82" width="6" height="4" rx="1" fill={gold}/><rect x={48+i*12} y="102" width="6" height="4" rx="1" fill={gold}/></g>)}</g>
      {[67,174].map(x=><g key={x} transform={`rotate(${s.reel} ${x} 94)`}><circle cx={x} cy="94" r="22" fill={cream} stroke={ink} strokeWidth="3"/><circle cx={x} cy="94" r="5" fill={ink}/>{[0,120,240].map(a=><circle key={a} cx={x} cy="81" r="5" fill={ink} transform={`rotate(${a} ${x} 94)`}/>)}</g>)}
      <rect x="94" y="83" width="50" height="10" rx="3" fill="#070f10"/>
      <Print x={120} y={s.printY} scale={.8} opacity={s.printA}/>
      <rect x="94" y="93" width="50" height="9" rx="2" fill={ink}/>
      <path d="M54 123h40" stroke={cream} strokeWidth="3" strokeLinecap="round"/>
      <text x="54" y="135" fill="#a4b8ad" fontFamily="Arial" fontSize="6" letterSpacing="1.7">PHOTON DEPT.</text>
      <circle cx="183" cy="125" r="5" fill={s.latch ? mint : coral}/>
      <g transform={`translate(0 ${-17+17*s.stamp})`} opacity={ms>2800 ? 1:0}><rect x="145" y="39" width="35" height="10" rx="3" fill={coral} stroke={ink} strokeWidth="2"/><path d="M161 49v12" stroke={ink} strokeWidth="5"/><rect x="144" y="58" width="37" height="7" rx="2" fill={ink}/></g>
      <Badge y={21} opacity={clamp((ms-3370)/200)}>GRAIN APPROVED</Badge>
      <Spark x={202} y={48} size={5*s.latch}/><Spark x={48} y={39} size={3*s.latch}/>
    </g>
  </Tile>;
}

// Experiment B: Remotion frame-derived animation; the Player and exports share this component.
export function PocketLabComposition() {
  const frame=useCurrentFrame();
  const {fps}=useVideoConfig();
  const ms=frame/fps*1000;
  const i=(a:number,b:number,x:number,y:number) => interpolate(frame,[a*fps,b*fps],[x,y],{extrapolateLeft:'clamp',extrapolateRight:'clamp',easing:Easing.bezier(.16,1,.3,1)});
  const entrance=i(0,.45,16,0);
  const eject=i(1.1,2.65,0,1);
  const peek=Math.sin(clamp((ms-450)/650)*Math.PI)*-7;
  const nod=ms>2850 && ms<3550 ? Math.sin((ms-2850)/700*Math.PI*2)*3:0;
  return <Tile label="Pocket Lab: a bespectacled robot prints and approves your photograph">
    <g opacity={fade(ms)} transform={`translate(0 ${entrance})`}>
      <Badge y={18} opacity={i(3,3.2,0,1)}>NICE PHOTONS.</Badge>
      <Robot tilt={peek+nod} happy={ms>2850} blink={(ms>780&&ms<880)||(ms>4100&&ms<4200)} arm={i(2.8,3.25,0,28)}/>
      <g><defs><clipPath id="paper-slot"><rect x="94" y={ms<2300?114:20} width="127" height="156"/></clipPath></defs>
        <g clipPath="url(#paper-slot)"><Print x={122+i(2.05,2.85,0,60)} y={96+eject*34} scale={.7} rotate={i(2.3,3,0,-8)} opacity={i(1.1,1.3,0,1)}/></g>
        <rect x="96" y="110" width="52" height="4" rx="2" fill="#56635b"/>
      </g>
      <g opacity={i(2.75,3,0,1)} transform={`translate(0 ${i(2.7,3.2,8,0)})`}>
        <circle cx="197" cy="105" r="12" fill={coral} stroke={ink} strokeWidth="2"/>
        <path d="m191 105 4 4 8-9" fill="none" stroke={cream} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/>
      </g>
      <Spark x={67} y={37} size={i(2.85,3.2,0,6)} opacity={i(4,4.5,1,0)}/>
      <Spark x={181} y={46} size={i(3,3.4,0,4)} opacity={i(4.1,4.5,1,0)}/>
      <g opacity={1-i(2.1,2.5,0,1)}><circle cx="180" cy="65" r="2" fill={cream}/><circle cx="188" cy="54" r="3" fill={cream} opacity={clamp((ms-1100)/400)}/><path d="M194 41h12m-6-6v12" stroke={gold} strokeWidth="2" opacity={clamp((ms-1500)/400)}/></g>
    </g>
  </Tile>;
}

export function PocketLab({ms}: {ms:number}) {
  const player=useRef<PlayerRef>(null);
  useLayoutEffect(() => {player.current?.seekTo(Math.min(99,Math.floor(ms/50)));},[ms]);
  return <Player ref={player} component={PocketLabComposition} durationInFrames={FRAME_COUNT} fps={FPS} compositionWidth={240} compositionHeight={176} controls={false} autoPlay={false} style={{width:240,height:176,background:'transparent',visibility:ms>=5000?'hidden':'visible'}}/>;
}

// Experiment C: browser-native animation, following Impeccable's authored focal moment.
// Paused WAAPI animations make scrubbing and frame exports independent of wall time.
export function FocusLock({ms}: {ms:number}) {
  const root=useRef<SVGGElement>(null);
  const animations=useRef<Animation[]>([]);
  useLayoutEffect(() => {
    const animate=(selector:string,frames:Keyframe[],options:KeyframeAnimationOptions) => {
      root.current!.querySelectorAll(selector).forEach(node=>{
        const a=node.animate(frames,{duration:5000,fill:'both',...options});a.pause();animations.current.push(a);
      });
    };
    animate('.rotor',[{transform:'rotate(-70deg)',offset:0},{transform:'rotate(0deg)',offset:.13},{transform:'rotate(120deg)',offset:.50},{transform:'rotate(120deg)',offset:1}],{easing:'cubic-bezier(.16,1,.3,1)'});
    animate('.iris',[{transform:'scale(1)',offset:0},{transform:'scale(.38)',offset:.3},{transform:'scale(.38)',offset:.4},{transform:'scale(1)',offset:.64},{transform:'scale(1)',offset:1}],{easing:'cubic-bezier(.76,0,.24,1)'});
    animate('.focus-print',[{opacity:0,transform:'translateY(8px) scale(.8)',offset:0},{opacity:0,transform:'translateY(8px) scale(.8)',offset:.53},{opacity:1,transform:'translateY(0) scale(1)',offset:.69},{opacity:1,transform:'translateY(0) scale(1)',offset:1}],{});
    return ()=>{animations.current.forEach(a=>a.cancel());animations.current=[];};
  },[]);
  useLayoutEffect(()=>{animations.current.forEach(a=>{a.currentTime=ms;});},[ms]);
  return <Tile label="Focus Lock: aperture blades align around a tiny saved photograph">
    <g ref={root} opacity={fade(ms)}>
      <ellipse cx="120" cy="151" rx="61" ry="5" fill={ink} opacity=".18"/>
      <circle cx="120" cy="86" r="60" fill="url(#metal)" stroke={ink} strokeWidth="3"/>
      <circle cx="120" cy="86" r="52" fill="none" stroke="#789287" strokeWidth="1"/>
      {Array.from({length:36},(_,i)=><path key={i} d={`M120 ${i%3===0?31:33}v${i%3===0?6:3}`} stroke={i%3===0?cream:'#80948a'} strokeWidth="1" transform={`rotate(${i*10} 120 86)`}/>)}
      <g className="rotor" style={{transformOrigin:'120px 86px'}}>
        {[0,60,120,180,240,300].map((a,i)=><path key={a} d="M120 43 157 64 145 112 120 129 99 94Z" fill={[mint,'#85b7a3','#69988b','#c5d6b5',gold,'#d9c391'][i]} stroke={ink} strokeWidth="1" transform={`rotate(${a} 120 86)`}/>)}
      </g>
      <g className="iris" style={{transformOrigin:'120px 86px'}}><circle cx="120" cy="86" r="27" fill={ink}/><circle cx="120" cy="86" r="20" fill="#3c6259"/><path d="M110 78h8m7 0h8" stroke={cream} strokeWidth="2"/><path d="M117 94q4 3 8 0" fill="none" stroke={cream} strokeWidth="2"/></g>
      <g className="focus-print" style={{transformOrigin:'120px 86px'}}><Print x={120} y={82} scale={.76}/></g>
      <Badge y={157} opacity={clamp((ms-3250)/200)}>FOCUS. CLICK. KEEP.</Badge>
      <Spark x={184} y={36} size={5*clamp((ms-3200)/300)}/><Spark x={52} y={55} size={3*clamp((ms-3300)/300)}/>
    </g>
  </Tile>;
}

export const experiments = [
  {id:'film',name:'Film Transport',skill:'GSAP · official',caption:'A film advance, a soft mechanical stop, a tiny quality-control stamp.',Component:FilmTransport,cue:'Ratchet → stamp',color:gold},
  {id:'robot',name:'Pocket Lab',skill:'Remotion · official',caption:'A pocket-sized lab nerd develops your photons. Then looks very pleased.',Component:PocketLab,cue:'Print → happy chirp',color:mint},
  {id:'focus',name:'Focus Lock',skill:'Impeccable · animate',caption:'Six aperture blades glide into place and release a little keepsake.',Component:FocusLock,cue:'Iris → soft click',color:coral},
] as const;
