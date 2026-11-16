import {coreArt} from './core-art';
import actions from './assets/terminal-actions-v5.png';
import actionMaster from './assets/terminal-actions-v5-normalized.png';
import {sequenceAt,poseMirror,DURATION_MS} from '../sequence.mjs';
import {NEON} from '../palette.mjs';

export const DURATION=DURATION_MS;
type Props={ms:number;large?:boolean};
const clamp=(n:number)=>Math.max(0,Math.min(1,n));
const out=(n:number)=>1-(1-clamp(n))**3;

function Art({pose,large=false}:{pose:number;large?:boolean}){
  const action=pose>=6,index=action?pose-6:pose;
  return <svg x={56} y={40} width={128} height={128} viewBox={large?'0 0 512 512':'0 0 128 128'} overflow="hidden">
    {!action?<image href={(large?coreArt.large:coreArt.small)[index]} width={large?512:128} height={large?512:128}/>:
      large?<image href={actionMaster} width="1536" height="1024" x={-(index%3)*512} y={-Math.floor(index/3)*512} preserveAspectRatio="none"/>:
      <image href={actions} width="128" height="768" y={-index*128}/>}
  </svg>;
}

function Dust({ms,at,x=120,amount=9}:{ms:number;at:number;x?:number;amount?:number}){
  const p=(ms-at)/500;
  if(p<0||p>=1)return null;
  return <g opacity={(1-p)**1.4} fill={NEON.ivory} stroke={NEON.ink} strokeWidth=".7">
    {Array.from({length:amount},(_,i)=>{
      const side=i%2?-1:1,travel=(12+(i%5)*7)*out(p);
      const lift=Math.sin(p*Math.PI)*(6+(i%4)*5);
      return <ellipse key={i} cx={x+side*travel} cy={164-lift+(i%3)*2} rx={(3+(i%3)*2)*(1-p*.5)} ry={(2+(i%4))*(1-p*.5)}/>;
    })}
  </g>;
}

function Pixels({ms,at,x=172,y=106,color=NEON.phosphor}:{ms:number;at:number;x?:number;y?:number;color?:string}){
  const p=(ms-at)/650;
  if(p<0||p>=1)return null;
  return <g fill={color} opacity={1-p}>
    {Array.from({length:10},(_,i)=>{
      const a=i*Math.PI*.2,r=10+(15+i%3*8)*out(p),size=(i%3+1)*1.5;
      return <rect key={i} x={x+Math.cos(a)*r-size/2} y={y+Math.sin(a)*r*.8-size/2} width={size} height={size} transform={`rotate(${i*23+p*90} ${x+Math.cos(a)*r} ${y+Math.sin(a)*r*.8})`}/>;
    })}
  </g>;
}

function portalSize(ms:number){
  if(ms<80)return 0;
  if(ms<310)return out((ms-80)/230);
  if(ms<690)return 1;
  if(ms<1120)return 1-out((ms-690)/430);
  if(ms<6480)return 0;
  if(ms<6780)return out((ms-6480)/300);
  if(ms<7280)return 1;
  return 1-out((ms-7280)/300);
}

function Portal({ms,front=false}:{ms:number;front?:boolean}){
  const size=portalSize(ms);
  if(size<.005)return null;
  const dash=ms*.07;
  return <g transform={`translate(173 102) scale(${size} ${size})`}>
    {!front&&<><ellipse rx="25" ry="44" fill={NEON.glass} stroke={NEON.portalRim} strokeWidth="7"/>
      <ellipse rx="21" ry="39" fill={NEON.portalDepth}/><ellipse rx="15" ry="32" fill={NEON.glass}/>
      <path d="M-9-26v15h11v12h-8v15h10" fill="none" stroke={NEON.phosphor} strokeWidth="2" opacity=".75"/>
      <ellipse rx="25" ry="44" fill="none" stroke={NEON.phosphor} strokeWidth="3" strokeDasharray="9 5 3 5" strokeDashoffset={-dash}/></>}
    {front&&<><path d="M0-44C-34-44-34 44 0 44" fill="none" stroke={NEON.portalRim} strokeWidth="9"/>
      <path d="M0-44C-34-44-34 44 0 44" fill="none" stroke={NEON.phosphor} strokeWidth="4" strokeDasharray="13 4" strokeDashoffset={dash}/>
      <path d="M-29-18h7m-10 13h8m-7 16h7" stroke={NEON.flash} strokeWidth="2"/></>}
  </g>;
}

function Flame({ms,pose}:{ms:number;pose:number}){
  const entering=ms>=120&&ms<750,charging=ms>=6550&&ms<6920,launch=ms>=6920&&ms<7450;
  if(!entering&&!charging&&!launch)return null;
  const flicker=(Math.floor(ms/45)%3)/2;
  const length=entering?20+flicker*10:charging?7+flicker*9:24+flicker*8;
  const sockets=pose===11?[[90,161,25],[111,151,25]]:[[98,164,0],[147,164,0]];
  return <g>
    {sockets.map(([x,y,angle],i)=><g key={i} transform={`translate(${x} ${y}) rotate(${angle})`}>
      <path data-effect="flame" d={`M-8 0Q-12 ${length*.5} 0 ${length}Q11 ${length*.45} 8 0Z`} fill={NEON.orange} stroke={NEON.ink} strokeWidth="1.3"/>
      <path d={`M-4 0Q-6 ${length*.45} 0 ${length*.77}Q5 ${length*.4} 4 0Z`} fill={NEON.lemon}/>
      <path d="M-3-1Q-4 7 0 11Q4 6 3-1Z" fill={NEON.hot}/>
    </g>)}
  </g>;
}

function Speed({ms,id,x,y}:{ms:number;id:string;x:number;y:number}){
  const visible=id==='dash'&&(ms<650||ms>6800&&ms<7310)||id==='rocket'&&(ms>120&&ms<700||ms>6950&&ms<7410);
  if(!visible)return null;
  const flying=id==='rocket',pulse=Math.floor(ms/60)%3;
  return <g stroke={flying?NEON.orange:NEON.phosphor} strokeWidth="2" strokeLinecap="round" opacity=".8">
    {[0,1,2].map(i=><path key={i} d={flying&&ms>6400?`M${130+x+i*9} ${142+y+i*10}l${8+i*4} ${26+i*8}`:
      `M${168+x+i*4} ${91+y+i*18}h${16+i*4+pulse*3}`}/>)}
  </g>;
}

function Sparkle({ms}:{ms:number}){
  const act=ms-1400,p=(act-2950)/600;
  if(p<0||p>=1)return null;
  return <g stroke={NEON.flash} strokeWidth="2" strokeLinecap="round" opacity={Math.sin(p*Math.PI)}>
    <path d="M174 61v12m-6-6h12M190 84v8m-4-4h8"/>
  </g>;
}

export function Sequence({ms,large=false,id='portal'}:Props&{id?:string}){
  const s=sequenceAt(ms,id);
  if(!s.active)return <svg xmlns="http://www.w3.org/2000/svg" width="240" height="176" className="tile-svg sequence-tile" aria-label="Animation finished"/>;
  const shadowOpacity=s.opacity*.16*Math.max(0,1-Math.abs(s.y)/110)*Math.max(0,1-Math.abs(s.x)/130);
  const landing=id==='dash'?650:id==='portal'?900:840;
  return <svg xmlns="http://www.w3.org/2000/svg" width="240" height="176" viewBox={large?'-10 -50 260 248':'0 0 240 176'} className="tile-svg sequence-tile" role="img" aria-label={`Terminal ${id}: ${s.phase}`} data-pose={s.pose} data-phase={s.phase} data-facing={s.facing<0?'left':'right'}>
    <g aria-hidden="true">
      <ellipse cx={120+s.x*.2} cy="166" rx={36+Math.min(0,s.y*.12)} ry="3" fill={NEON.shadow} opacity={shadowOpacity}/>
      {id==='portal'&&<Portal ms={ms}/>}
      <Speed ms={ms} id={id} x={s.x} y={s.y}/>
      <Dust ms={ms} at={landing}/>
      <Dust ms={ms} at={id==='dash'?6790:id==='portal'?6760:6930}/>
      {id==='portal'&&<><Pixels ms={ms} at={200}/><Pixels ms={ms} at={7280}/></>}
    </g>
    <g opacity={s.opacity} transform={`translate(${120+s.x} ${168+s.y}) rotate(${s.rotation}) scale(${s.scaleX} ${s.scaleY}) translate(-120 -168)`}>
      <g transform={`translate(120 0) scale(${poseMirror(s.pose,s.facing)} 1) translate(-120 0)`}>
        {id==='rocket'&&<Flame ms={ms} pose={s.pose}/>}
        <Art pose={s.pose} large={large}/>
      </g>
    </g>
    <g aria-hidden="true">{id==='portal'&&<Portal ms={ms} front/>}<Sparkle ms={ms}/>
      {id==='rocket'&&<><Pixels ms={ms} at={6930} x={120} y={156} color={NEON.magenta}/><Dust ms={ms} at={7080} amount={6}/></>}
    </g>
  </svg>;
}

const Dash=(p:Props)=><Sequence {...p} id="dash"/>;
const PortalHop=(p:Props)=><Sequence {...p} id="portal"/>;
const Rocket=(p:Props)=><Sequence {...p} id="rocket"/>;
export const experiments=[
  {id:'dash',name:'Disk Dash',Component:Dash,personality:'Run. Skid. Nailed it.',skill:'Footsteps / rubber skid / dash',caption:'Sprints in, hits the brakes and rebounds. After the photo inspection, a crouch, a heel kick and a sprint out.',cue:'Play Disk Dash'},
  {id:'portal',name:'Pixel Portal',Component:PortalHop,personality:'A small interdimensional incident.',skill:'Portal hum / landing / pixel snap',caption:'Tumbles through a pixel portal, lands with a squash and catches its balance. Then winds up, dives back in and zips the portal shut.',cue:'Play Pixel Portal'},
  {id:'rocket',name:'Rocket Delivery',Component:Rocket,personality:'Express delivery. Excessive enthusiasm.',skill:'Jet whoosh / impact / blast-off',caption:'Flies in on rocket sneakers, brakes and bounces into place. Then crouches, charges the boots and blasts out with a trail of sparks.',cue:'Play Rocket Delivery'},
] as const;
