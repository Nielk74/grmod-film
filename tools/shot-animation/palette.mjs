// Color roles are shared by the baked sprite exporter and geometric effects.
// No shader, extra sprite, glow pass or runtime image filtering is required.
export const NEON=Object.freeze({
  phosphor:'#9bff19',flash:'#d5ff5b',glass:'#061b12',portalDepth:'#103d25',
  portalRim:'#112c20',orange:'#ff510a',lemon:'#fff52b',hot:'#f3ffed',
  magenta:'#ff39d4',ivory:'#fff0d2',ink:'#20251f',shadow:'#303a2c',
});

function hsv(r,g,b){
  const max=Math.max(r,g,b),min=Math.min(r,g,b),delta=max-min;
  let h=delta===0?0:max===r?60*((g-b)/delta%6):max===g?60*((b-r)/delta+2):60*((r-g)/delta+4);
  if(h<0)h+=360;
  return[h,max===0?0:delta/max,max/255];
}

function rgb(h,s,v){
  const c=v*s,x=c*(1-Math.abs(h/60%2-1)),m=v-c;
  const p=h<60?[c,x,0]:h<120?[x,c,0]:h<180?[0,c,x]:h<240?[0,x,c]:h<300?[x,0,c]:[c,0,x];
  return p.map(n=>Math.round((n+m)*255));
}

/** Grade only the color channels; keep the original registration and alpha. */
export function neonRgba(source){
  const result=new Uint8Array(source);
  for(let i=0;i<source.length;i+=4){
    const r=source[i],g=source[i+1],b=source[i+2];
    if(source[i+3]===0||Math.max(r,g,b)<24)continue;
    const [h,s,v]=hsv(r,g,b);
    let color;
    if(h>=65&&h<=135&&s>.45&&v>.35){
      color=rgb(85,.94,.94+.06*(v-.35)/.65);
    }else if(h>=85&&h<=165&&s>.15&&v<.42){
      color=[Math.round(r*.23),Math.round(g*.45),Math.round(b*.35)];
    }else if(h>=12&&h<=48&&s>.65){
      color=rgb(16,.98,v+.45*(1-v));
    }else if(h>=265&&h<=345&&s>.18&&v>.24){
      color=rgb(h<295?278:315,.88,.78+.22*v);
    }else if(h>=200&&h<265&&s>.3&&v>.24){
      color=rgb(235,.94,.8+.2*v);
    }else if(h>=20&&h<=65&&s<.36&&v>.65){
      color=[r,Math.round(g+(255-g)*.22),Math.round(b+(255-b)*.18)];
    }
    if(color)result.set(color,i);
  }
  return result;
}
