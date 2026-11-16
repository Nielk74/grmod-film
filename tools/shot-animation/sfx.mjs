import {ENTER_MS,DURATION_MS,SEQUENCE_IDS} from './sequence.mjs';
import {ENTER_MS as LEGACY_ENTER_MS,DURATION_MS as LEGACY_DURATION_MS} from './timing.mjs';

// Times are seconds on the complete animation timeline. Plain data descriptors
// let the compact exporter include the same authored cue sheet.
const cue=(sound,at,duration,phase,extra={})=>Object.freeze({sound,at,duration,phase,...extra});
const robotNotes=[
  [.25,330,.065,'sine'],[1.2,165,.06,'triangle'],[1.6,196,.05,'triangle'],
  [2,220,.05,'triangle'],[2.4,262,.05,'triangle'],[2.95,523,.1,'sine'],
  [3.08,659,.1,'sine'],[3.24,784,.17,'sine'],
];
const notes=(events,offset)=>events.map(([at,frequency,duration,wave])=>
  cue('note',Number((at+offset).toFixed(6)),duration,'core',{frequency,wave}));
const core=notes(robotNotes,ENTER_MS/1000);
const entry=(sound,at,duration,extra)=>cue(sound,at,duration,'entry',extra);
const exit=(sound,at,duration,extra)=>cue(sound,at,duration,'exit',extra);
const scores=Object.freeze({
  dash:Object.freeze([
    ...[.12,.24,.36,.48,.60].map((at,index)=>entry('footstep',at,.075,{pitch:1+index*.05,pan:.75-index*.15})),
    entry('skid',.65,.25),entry('settle',.90,.16),...core,
    exit('crouch',6.55,.20),exit('dash-launch',6.80,.24),
    ...[6.85,6.98,7.10,7.22].map((at,index)=>exit('footstep',at,.075,{pitch:1.1+index*.08,pan:-.1-index*.22})),
  ].sort((a,b)=>a.at-b.at)),
  portal:Object.freeze([
    entry('portal-open',.08,.27),entry('portal-emerge',.30,.45),
    entry('land',.90,.14),entry('bounce',1.08,.16),...core,
    exit('portal-open',6.50,.25,{reverse:true}),exit('crouch',6.60,.15),
    exit('portal-jump',6.75,.28),exit('portal-dive',7.05,.23),
    exit('portal-close',7.35,.24),
  ].sort((a,b)=>a.at-b.at)),
  rocket:Object.freeze([
    entry('jet',.15,.55),entry('land',.84,.14),entry('bounce',1.02,.17),...core,
    exit('rocket-charge',6.55,.37),exit('rocket-ignite',6.92,.23),
    exit('rocket-launch',6.95,.50),
  ].sort((a,b)=>a.at-b.at)),
});
const legacyScores=Object.freeze({
  robot:Object.freeze(notes(robotNotes,LEGACY_ENTER_MS/1000)),
  film:Object.freeze(notes([[.45,150,.025,'triangle'],[.70,180,.025,'triangle'],[.95,210,.025,'triangle'],[1.20,240,.025,'triangle'],[1.45,270,.025,'triangle'],[2,360,.08,'sine'],[3.20,155,.09,'triangle'],[3.35,660,.12,'sine']],LEGACY_ENTER_MS/1000)),
  default:Object.freeze(notes([[.32,220,.08,'sine'],[1.45,146,.06,'triangle'],[2.7,293,.05,'triangle'],[3.3,587,.12,'sine'],[3.45,880,.12,'sine']],LEGACY_ENTER_MS/1000)),
});

/** @param {string} id */
export function scoreFor(id){
  if(Object.hasOwn(scores,id))return scores[id];
  return Object.hasOwn(legacyScores,id)?legacyScores[id]:legacyScores.default;
}
/** @param {string} id */
export function durationFor(id){return SEQUENCE_IDS.includes(id)?DURATION_MS:LEGACY_DURATION_MS;}

function seededNoise(length,seed){
  const samples=new Float32Array(length);
  let state=seed|0,pink=0;
  for(let index=0;index<length;index++){
    state^=state<<13;state^=state>>>17;state^=state<<5;
    const white=(state>>>0)/2147483648-1;
    pink=.92*pink+.08*white;
    samples[index]=white*.7+pink*.3;
  }
  return samples;
}

// Curves use normalized time and positive values for exponential interpolation.
function valueAt(points,position){
  for(let index=1;index<points.length;index++){
    const [rightAt,right]=points[index],[leftAt,left]=points[index-1];
    if(position<=rightAt){
      const progress=Math.max(0,Math.min(1,(position-leftAt)/(rightAt-leftAt)));
      return left*(right/left)**progress;
    }
  }
  return points.at(-1)[1];
}
function automate(parameter,points,start,duration,offset=0){
  parameter.setValueAtTime(valueAt(points,offset/duration),start);
  for(const [fraction,value] of points){
    const relative=fraction*duration-offset;
    if(relative>0)parameter.exponentialRampToValueAtTime(value,start+relative);
  }
}

/**
 * Shared live/offline scheduler. Every source, including long noise tails,
 * belongs to the returned cancellation handle.
 * @param {BaseAudioContext} context
 * @param {string} id
 * @param {{fromMs?:number,destination?:AudioNode}} [options]
 */
export function scheduleSound(context,id,{fromMs=0,destination=context.destination}={}){
  const modern=SEQUENCE_IDS.includes(id),from=Math.max(0,fromMs)/1000;
  const offline='startRendering' in context;
  const now=context.currentTime,origin=now-from;
  /** @type {Set<AudioScheduledSourceNode>} */
  const sources=new Set();
  /** @type {Map<AudioScheduledSourceNode,AudioNode[]>} */
  const nodes=new Map();
  /** @type {AudioNode[]} */
  const bus=[];
  let target=destination;
  if(modern){
    const mix=context.createGain(),limiter=context.createDynamicsCompressor(),master=context.createGain();
    // 100% is unity at the application master. Individual effects are staged
    // below full scale; the compressor catches brief layered transients.
    mix.gain.value=.90;master.gain.value=1;
    limiter.threshold.value=-3;limiter.knee.value=3;limiter.ratio.value=12;
    limiter.attack.value=.002;limiter.release.value=.055;
    mix.connect(limiter);limiter.connect(master);master.connect(destination);
    bus.push(mix,limiter,master);target=mix;
  }
  const disconnectBus=()=>{for(const node of bus)node.disconnect();};
  const forget=source=>{
    for(const node of nodes.get(source)??[])node.disconnect();
    nodes.delete(source);sources.delete(source);
    if(!sources.size)disconnectBus();
  };
  let voiceIndex=0;
  function voice({at,duration,peak,frequency,wave='sine',noise=false,cutoff,filter='lowpass',pan=0,attack=.006,shape,legacy=false}){
    const seed=0x51f15e+(++voiceIndex)*0x9e3779;
    if(at+duration<=from||(!modern&&at<from))return;
    const offset=Math.max(0,from-at),start=Math.max(now,origin+at),end=origin+at+duration;
    const source=noise?context.createBufferSource():context.createOscillator();
    const chain=[source],gain=context.createGain();
    let output=source;
    if(noise){
      const buffer=context.createBuffer(1,Math.ceil(duration*context.sampleRate),context.sampleRate);
      buffer.getChannelData(0).set(seededNoise(buffer.length,seed));
      source.buffer=buffer;
    }else{
      source.type=wave;
      automate(source.frequency,frequency,start,duration,offset);
    }
    if(cutoff){
      const biquad=context.createBiquadFilter();biquad.type=filter;
      biquad.Q.value=filter==='bandpass'?.8:.65;
      automate(biquad.frequency,cutoff,start,duration,offset);
      output.connect(biquad);output=biquad;chain.push(biquad);
    }
    output.connect(gain);chain.push(gain);
    if(legacy){
      gain.gain.setValueAtTime(0,start);
      gain.gain.linearRampToValueAtTime(1,start+.008);
      gain.gain.exponentialRampToValueAtTime(.0001,end);
    }else{
      const envelope=shape??[[0,.0001],[Math.min(attack/duration,.2),1],[.38,.6],[1,.0001]];
      const points=envelope.map(([fraction,multiplier])=>[fraction,Math.max(.0001,peak*multiplier)]);
      if(offset>0){
        // Resume the existing envelope and noise buffer with a short de-click
        // ramp, rather than repeating the initial impact after a seek.
        const fade=Math.min(.004,(end-start)/2);
        gain.gain.setValueAtTime(.0001,start);
        gain.gain.linearRampToValueAtTime(valueAt(points,(offset+fade)/duration),start+fade);
        for(const [fraction,value] of points)if(fraction*duration>offset+fade)
          gain.gain.exponentialRampToValueAtTime(value,start+fraction*duration-offset);
      }else{
        gain.gain.setValueAtTime(points[0][1],start);
        for(let index=1;index<points.length;index++){
          const [fraction,value]=points[index];
          if(index===1)gain.gain.linearRampToValueAtTime(value,start+fraction*duration);
          else gain.gain.exponentialRampToValueAtTime(value,start+fraction*duration);
        }
      }
    }
    if(modern){
      const panner=context.createStereoPanner();panner.pan.value=pan;
      gain.connect(panner);panner.connect(target);chain.push(panner);
    }else gain.connect(target);
    sources.add(source);nodes.set(source,chain);
    // Offline rendering runs faster than main-thread ended callbacks. Retain
    // its graph until rendering resolves so callback timing cannot cut filter
    // tails at different samples in otherwise identical exports.
    source.onended=()=>{if(!offline)forget(source);};
    if(noise)source.start(start,offset);else source.start(start);
    source.stop(end+(legacy?.01:0));
  }
  const tone=(at,duration,fromFrequency,toFrequency,peak,wave='sine',pan=0,extra={})=>
    voice({at,duration,peak,wave,pan,frequency:[[0,fromFrequency],[1,toFrequency]],...extra});
  const hiss=(at,duration,peak,fromCutoff,toCutoff,pan=0,extra={})=>
    voice({at,duration,peak,noise:true,pan,cutoff:[[0,fromCutoff],[1,toCutoff]],...extra});
  const spring=(at,duration,low,high,pan=0)=>{
    tone(at,duration,low,low*.8,.28,'sine',pan,{frequency:[[0,low],[.27,high],[1,low*.8]]});
    tone(at,duration*.75,low*2,high,.075,'triangle',pan);
  };
  const land=(at,duration,pan=0)=>{
    tone(at,duration,140,48,.40,'sine',pan,{attack:.003});
    hiss(at,.045,.25,1700,450,pan,{attack:.002});
  };
  for(const event of scoreFor(id)){
    const {at,duration,pan=0}=event;
    switch(event.sound){
      case 'note':
        tone(at,duration,event.frequency,event.frequency*.94,modern?.88:1,event.wave,0,{legacy:!modern,attack:.008});break;
      case 'footstep':
        tone(at,duration,240*event.pitch,84*event.pitch,.32,'sine',pan,{attack:.003});
        hiss(at,.033,.19,1400,550,pan,{attack:.002});break;
      case 'skid':
        hiss(at,duration,.24,3400,900,.16,{filter:'bandpass',attack:.012});
        tone(at+.015,duration-.015,780,300,.20,'sine',.16,{frequency:[[0,780],[.4,1160],[1,300]],attack:.012});break;
      case 'settle':spring(at,duration,125,205,.15);break;
      case 'crouch':
        tone(at,duration,285,100,.19,'triangle',0,{attack:.015});
        tone(at+.025,duration-.025,180,85,.09,'sine',-.1);break;
      case 'dash-launch':
        hiss(at,duration,.28,650,3200,.4,{attack:.015});
        tone(at,duration*.7,140,540,.20,'triangle',.4);break;
      case 'portal-open':
        tone(at,duration,event.reverse?160:65,event.reverse?55:220,.34,'sine',-.22,{attack:.025});
        tone(at+.025,duration-.025,310,760,.11,'triangle',.25,{attack:.02});
        hiss(at,duration,.23,450,2600,-.22,{filter:'bandpass',attack:.035});break;
      case 'portal-emerge':
        tone(at,duration,460,185,.24,'sine',.18,{frequency:[[0,460],[.35,800],[.7,320],[1,185]],attack:.025});
        hiss(at,duration,.18,2300,600,.18,{attack:.04});break;
      case 'land':land(at,duration);break;
      case 'bounce':spring(at,duration,165,380);break;
      case 'portal-jump':
        spring(at,duration,160,620,.2);
        hiss(at,duration,.14,600,2400,.2,{attack:.02});break;
      case 'portal-dive':
        tone(at,duration,820,75,.30,'sine',-.3,{attack:.012});
        hiss(at,duration,.24,2800,400,-.3,{attack:.025});break;
      case 'portal-close':
        tone(at,duration,130,760,.28,'sine',-.2,{frequency:[[0,130],[.64,55],[1,760]],attack:.02});
        hiss(at,duration,.25,2200,180,-.2,{attack:.015});
        tone(at+.16,.065,900,240,.17,'triangle',-.2,{attack:.002});break;
      case 'jet':
        hiss(at,duration,.36,650,2200,-.35,{cutoff:[[0,650],[.55,2700],[1,500]],attack:.035});
        tone(at,duration,85,120,.19,'triangle',-.35,{frequency:[[0,85],[.5,210],[1,100]],attack:.025});
        tone(at+.08,duration-.08,280,165,.10,'sine',.18,{frequency:[[0,280],[.5,580],[1,165]]});break;
      case 'rocket-charge':
        tone(at,duration,105,620,.24,'triangle',0,{attack:.025,shape:[[0,.0001],[.1,.18],[.85,1],[1,.0001]]});
        for(const [index,offset] of [0,.08,.15,.21,.26].entries())
          tone(at+offset,.055,170+index*65,230+index*90,.13,'sine',index%2?.18:-.18);
        hiss(at,duration,.16,350,2000,0,{attack:.04});break;
      case 'rocket-ignite':
        tone(at,duration,90,32,.42,'sine',0,{attack:.002});
        hiss(at,duration,.38,1900,350,0,{attack:.002});break;
      case 'rocket-launch':
        hiss(at,duration,.39,700,4600,.28,{attack:.035,shape:[[0,.0001],[.1,.25],[.6,1],[1,.0001]]});
        tone(at,duration,140,1250,.23,'triangle',.28,{attack:.035});
        tone(at+.08,duration-.08,260,1800,.10,'sine',-.2,{attack:.025});break;
    }
  }
  return{
    sources,
    stop(){
      for(const source of [...sources]){
        try{source.stop();}catch{/* A source may already have ended. */}
        forget(source);
      }
      disconnectBus();
    },
  };
}
