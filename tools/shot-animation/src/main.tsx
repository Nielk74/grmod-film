import {useEffect, useLayoutEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {flushSync} from 'react-dom';
import {DURATION, experiments} from './sequences';
import {characterExperiments,experiments as earlierTransitions} from './compact';
import {ENTER_MS,ACT_DURATION_MS,FPS,phaseLabel,createTransitionPicker} from '../sequence.mjs';
import {experiments as legacyExperiments} from './mascots';
import {playSound,stopSound} from './sound';
import sample from '../../../ui/src/assets/samples/gr3-path.jpg';
import './styles.css';

declare global {interface Window {seekShot:(ms:number)=>Promise<void>;shotState:{ms:number;playing:boolean;variant:string};}}

function Icon({kind}: {kind:'play'|'pause'|'camera'|'sound'|'mute'|'reset'|'arrow'|'enter'}) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{kind==='camera'?<><path d="M4 7h4l2-3h4l2 3h4v13H4Z"/><circle cx="12" cy="13" r="4"/></>:kind==='play'?<path d="m9 5 10 7-10 7Z"/>:kind==='pause'?<path d="M8 5v14m8-14v14"/>:kind==='reset'?<><path d="M4 11a8 8 0 1 1 2 7M4 4v7h7"/></>:kind==='arrow'?<path d="M6 18 18 6M6 6h12v12"/>:kind==='enter'?<path d="M20 5v8H4m6-6-6 6 6 6"/>:<><path d="M11 5 6 9H3v6h3l5 4Z"/>{kind==='sound'?<path d="M15 8q7 4 0 8m3-11q10 7 0 14"/>:<path d="m16 9 6 6m0-6-6 6"/>}</>}</svg>;
}

function Camera({children,active}: {children:React.ReactNode;active:boolean}) {
  const ref=useRef<HTMLDivElement>(null);
  const [scale,setScale]=useState(.45);
  useLayoutEffect(()=>{
    const observer=new ResizeObserver(entries=>setScale(entries[0].contentRect.width/720));
    observer.observe(ref.current!);return ()=>observer.disconnect();
  },[]);
  return <div className="camera-shell"><div className="camera-top"><span className="camera-brand">GR</span><span className="camera-light"/> <span className="camera-mark">DIGITAL / 28mm</span></div>
    <div className="lcd" ref={ref}>
      <img className="photo" src={sample} alt="GR III sample photograph used as the LCD background"/>
      <div className="native-screen" style={{transform:`scale(${scale})`}}>
        <div className="lcd-top"><span>Av</span><span>F2.8</span><span>1/250</span><span className="battery"/></div>
        <div className="focus-bracket"/><span className="lcd-bottom">ISO 400 <span>PORTRA 400</span></span>
        <div className="overlay-slot">{children}</div>
      </div>
      <span className={`capture-dot ${active?'active':''}`} aria-hidden="true"/>
    </div>
    <div className="camera-chin"><span>RICOH</span><span className="chin-rule"/><span>III</span></div>
  </div>;
}

function App() {
  const only=new URLSearchParams(location.search).get('export');
  const [ms,setMs]=useState(ENTER_MS+3650), [playing,setPlaying]=useState(false), [sound,setSound]=useState(true);
  const [selected,setSelected]=useState('portal'),[audioError,setAudioError]=useState('');
  const [reduced,setReduced]=useState(matchMedia('(prefers-reduced-motion: reduce)').matches);
  const origin=useRef(0),raf=useRef(0);
  const picker=useRef<ReturnType<typeof createTransitionPicker>|null>(null);
  picker.current??=createTransitionPicker();
  const selectedExperiment=experiments.find(e=>e.id===selected)!;
  useEffect(()=>{
    const query=matchMedia('(prefers-reduced-motion: reduce)');
    const changed=()=>{setReduced(query.matches);setPlaying(false);stopSound();};
    query.addEventListener('change',changed);return()=>query.removeEventListener('change',changed);
  },[]);
  useEffect(()=>{
    const hidden=()=>{if(document.hidden){setPlaying(false);stopSound();}};
    document.addEventListener('visibilitychange',hidden);return()=>document.removeEventListener('visibilitychange',hidden);
  },[]);
  useEffect(()=>{
    if(!playing)return;
    const tick=(now:number)=>{
      const value=Math.min(DURATION,now-origin.current);
      setMs(value);
      if(value>=DURATION){setPlaying(false);stopSound();}else raf.current=requestAnimationFrame(tick);
    };
    raf.current=requestAnimationFrame(tick);return()=>cancelAnimationFrame(raf.current);
  },[playing]);
  useLayoutEffect(()=>{
    window.shotState={ms,playing,variant:selected};
    window.seekShot=async(value)=>{
      stopSound();flushSync(()=>{setPlaying(false);setMs(Math.max(0,Math.min(DURATION,value)));});
      await new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve())));
    };
  });
  const audio=(start:number,id=selected)=>{void playSound(id,start).catch(()=>{setSound(false);setAudioError('Audio is unavailable in this browser. The animation still works.');});};
  const shoot=(id=selected,start=0)=>{stopSound();setSelected(id);setMs(start);origin.current=performance.now()-start;setPlaying(true);if(sound)audio(start,id);};
  const randomShot=()=>shoot(picker.current!());
  const toggle=()=>{if(playing){setPlaying(false);stopSound();}else{const start=ms>=DURATION?0:ms;setMs(start);origin.current=performance.now()-start;setPlaying(true);if(sound)audio(start);}};
  const toggleSound=()=>{if(sound)stopSound();else if(playing)audio(ms);setSound(!sound);};
  const scrub=(value:number)=>{setPlaying(false);stopSound();setMs(value);};
  useEffect(()=>{
    const key=(event:KeyboardEvent)=>{
      if(event.key!=='Enter'||event.repeat||(event.target as HTMLElement).closest('button,input,a'))return;
      event.preventDefault();randomShot();
    };
    window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);
  },[sound,selected]);
  const renderedMs=ms>=DURATION?DURATION:reduced&&!only?ENTER_MS+3650:Math.floor(ms*FPS/1000)*1000/FPS;
  if(only){const e=[...experiments,...earlierTransitions,...characterExperiments,...legacyExperiments].find(e=>e.id===only);const large=new URLSearchParams(location.search).has('large');return e?<div className={`export-tile ${large?'large':''}`} style={large?{width:360,height:280}:undefined}><e.Component ms={renderedMs} large={large}/></div>:<p>Unknown experiment</p>;}
  return <main>
    <nav><a className="wordmark" href="/">GR<span>MOD</span><span className="nav-divider"/>SHUTTER STUDIES</a><a className="source-link" href="https://github.com/Maxwooow/Ricoh-GRMod">Made for the little camera <Icon kind="arrow"/></a></nav>
    <header><h1>A little computer.<br/><span>A proper entrance.</span></h1><div className="intro"><p>Your Terminal, with a running start, a portal mishap, or very enthusiastic rocket sneakers.</p><p className="preview-note">1.4s entrance + 5s routine + 1.2s exit.<br/>Pocket Lab + new SFX · volume 100%</p></div></header>
    <div className="transport">
      <button className="shoot" onClick={randomShot}><Icon kind="camera"/>Take a picture<span className="shortcut"><Icon kind="enter"/></span></button>
      <button className="icon-button" onClick={toggle} aria-label={playing?'Pause animation':'Play animation'}><Icon kind={playing?'pause':'play'}/></button>
      <input aria-label="Animation timeline" type="range" min="0" max={DURATION} step="10" value={ms} onChange={e=>scrub(Number(e.target.value))}/>
      <span className="time"><b>{(ms/1000).toFixed(2)}</b> / {(DURATION/1000).toFixed(2)}s</span>
      <button className={`sound ${sound?'on':''}`} onClick={toggleSound} aria-pressed={sound}><Icon kind={sound?'sound':'mute'}/>{sound?'Sound 100%':'Sound off'}</button>
    </div>
    <div className="sequence-controls"><span className={playing?'phase playing':'phase'}>{phaseLabel(ms)}</span><p>Random each shot · <b>{selectedExperiment.name}</b> is active.</p><button onClick={()=>shoot(selected,0)}>Replay entrance <Icon kind="reset"/></button><button onClick={()=>shoot(selected,ENTER_MS+ACT_DURATION_MS)}>Replay exit <Icon kind="arrow"/></button></div>
    {reduced&&<p className="motion-note">Reduced motion is enabled. You’re seeing the finished pose. <button onClick={()=>setReduced(false)}>Preview full motion</button></p>}
    {audioError&&<p role="status">{audioError}</p>}
    <div className="studies">
      {experiments.map((e,index)=><article key={e.id} className={selected===e.id?'selected':''}>
        <div className="study-heading"><span className="study-index">{String.fromCharCode(65+index)}</span><h2>{e.name}</h2>{e.id===selected&&<span className="pick">ACTIVE</span>}</div>
        <div className="character-preview"><div className="character-large"><e.Component ms={e.id===selected?renderedMs:ENTER_MS+3650} large/></div><span>{e.personality}</span>{ms>=DURATION&&e.id===selected&&<button className="stage-replay" onClick={()=>shoot(e.id)}><Icon kind="play"/>Replay {e.name}</button>}</div>
        <Camera active={e.id===selected&&playing&&ms<250}><e.Component ms={e.id===selected?renderedMs:ENTER_MS+3650}/></Camera>
        <div className="study-meta"><span>{e.skill}</span><span>7.6s</span></div>
        <p>{e.caption}</p>
        <button className="audition" onClick={()=>shoot(e.id)} aria-label={e.cue} aria-pressed={selected===e.id}><Icon kind="play"/><span>{e.cue}</span><span className="cue" aria-hidden="true">{selected===e.id?'SFX selected':'With sound'}</span></button>
      </article>)}
    </div>
    <section className="decision"><div><div><h2>All three. A different arrival.</h2><p>Each shot shuffles between Dash, Portal and Rocket, with no immediate repeats.<br/>Use a sequence’s Play button to inspect it directly.</p></div></div><div className="decision-detail"><span>{selectedExperiment.name}</span><p>Terminal + Pocket Lab + entrance / exit SFX.<br/>7.6 seconds. Replay either action above.</p></div></section>
    <footer><span>12 cached poses · 30 fps choreography · small, bounded effects</span><span>Animation preview · camera integration pending.</span></footer>
  </main>;
}

createRoot(document.getElementById('root')!).render(<App/>);
