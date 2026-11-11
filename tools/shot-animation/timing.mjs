export const ACT_DURATION_MS=5000;
export const ENTER_MS=350;
export const LEAVE_MS=350;
export const DURATION_MS=ENTER_MS+ACT_DURATION_MS+LEAVE_MS;
export const KEY_TIMES=Object.freeze([0,450,600,1450,2950,3500]);
export const POSE_COUNT=KEY_TIMES.length;
export const FRAME_LABELS=Object.freeze(['Inspect','Blink','Double take','Delight','Thumbs-up','Smug approval']);

const roundDiv=(n,d)=>n<0?-Math.floor((-n+d/2)/d):Math.floor((n+d/2)/d);
const easeOut=p=>256-Math.floor((256-p)**3/65536);
// Quantized widget placement: native adapters use the same integer math. Scale
// values are Q8, so entry/exit reuse the six image planes without extra frames.
export function motionAt(ms,variant=0){
  if(ms>=DURATION_MS)return{active:false,actMs:4999,y:0,opacity:0,scaleX:1,scaleY:1};
  let y=0,alpha=255,sx=256,sy=256;
  const entering=ms<ENTER_MS,leaving=ms>=ENTER_MS+ACT_DURATION_MS;
  const actMs=Math.min(4999,Math.max(0,ms-ENTER_MS));
  if(entering||leaving){
    const p=Math.max(0,Math.min(256,Math.floor((entering?ms:ms-ENTER_MS-ACT_DURATION_MS)*256/350)));
    alpha=roundDiv(255*(entering?p:256-p),256);
    if(variant===1){
      if(entering){
        if(p<166)y=18-roundDiv(22*easeOut(Math.floor(p*256/166)),256);
        else {const r=256-Math.floor((p-166)*256/90);y=roundDiv(-4*r*r,65536);}
        alpha=roundDiv(255*Math.min(256,p*3),256);
      }else if(p<77)y=roundDiv(-3*easeOut(Math.floor(p*256/77)),256);
      else {const q=Math.floor((p-77)*256/179);y=-3+roundDiv(21*q*q,65536);}
    }else if(variant===2){
      if(entering){
        if(p<59){sx=51+roundDiv(205*easeOut(Math.floor(p*256/59)),256);sy=5;}
        else {sy=5+roundDiv(251*easeOut(Math.floor((p-59)*256/197)),256);}
        alpha=roundDiv(255*Math.min(256,p*4),256);
      }else if(p<197){const q=Math.floor(p*256/197);sy=256-roundDiv(251*q*q,65536);}
      else {sy=5;sx=256-roundDiv(205*Math.floor((p-197)*256/59),256);}
    }else y=entering?roundDiv(14*(256-p)**3,16777216):roundDiv(10*p*p,65536);
  }
  return{active:true,actMs,y,opacity:alpha/255,scaleX:sx/256,scaleY:sy/256};
}
