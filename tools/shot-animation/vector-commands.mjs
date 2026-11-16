// SPDX-License-Identifier: GPL-2.0-only
// Flatten only the geometric SVG effects. Character artwork stays in its12 poses.
export function pathContours(source){
  const tokens=source.match(/[a-zA-Z]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?/g)||[];
  const contours=[];let i=0,command='',x=0,y=0,current;
  const number=()=>{if(i>=tokens.length||/^[a-z]$/i.test(tokens[i]))throw Error('Incomplete SVG path');return Number(tokens[i++]);};
  const add=(px,py)=>{current??={points:[[x,y]],closed:false};current.points.push([px,py]);x=px;y=py;};
  const push=()=>{if(current?.points.length)contours.push(current);current=undefined;};
  while(i<tokens.length){
    if(/^[a-z]$/i.test(tokens[i]))command=tokens[i++];
    const relative=command===command.toLowerCase(),kind=command.toUpperCase();
    const xy=()=>{const a=number(),b=number();return[relative?x+a:a,relative?y+b:b];};
    if(kind==='M'){
      const [a,b]=xy();push();x=a;y=b;current={points:[[x,y]],closed:false};command=relative?'l':'L';
    }else if(kind==='L'){const [a,b]=xy();add(a,b);}
    else if(kind==='H'){const a=number();add(relative?x+a:a,y);}
    else if(kind==='V'){const b=number();add(x,relative?y+b:b);}
    else if(kind==='Q'||kind==='C'){
      const p0=[x,y],p1=xy(),p2=xy(),p3=kind==='C'?xy():undefined;
      const points=p3?[p0,p1,p2,p3]:[p0,p1,p2];
      const length=points.slice(1).reduce((sum,p,j)=>sum+Math.hypot(p[0]-points[j][0],p[1]-points[j][1]),0);
      const steps=Math.min(64,Math.max(4,Math.ceil(length/3)));
      for(let j=1;j<=steps;j++){
        const t=j/steps,s=1-t;
        add(...(p3?[0,1].map(k=>s*s*s*p0[k]+3*s*s*t*p1[k]+3*s*t*t*p2[k]+t*t*t*p3[k]):
          [0,1].map(k=>s*s*p0[k]+2*s*t*p1[k]+t*t*p2[k])));
      }
    }else if(kind==='Z'){
      if(current){const first=current.points[0];add(...first);current.closed=true;push();}
      command='';
    }else throw Error(`Unsupported geometric SVG command ${command}`);
  }
  push();return contours;
}

const disc=(x,y,r)=>Array.from({length:10},(_,i)=>[x+Math.cos(i*Math.PI/5)*r,y+Math.sin(i*Math.PI/5)*r]);
export function strokePolygons(points,width,dashes=[],offset=0,cap='butt'){
  let pattern=dashes.filter(n=>n>0);if(pattern.length%2)pattern=[...pattern,...pattern];
  const sum=pattern.reduce((n,v)=>n+v,0);let index=0,remaining=Infinity;
  if(sum){
    let phase=((offset%sum)+sum)%sum;
    while(phase>=pattern[index]){phase-=pattern[index];index=(index+1)%pattern.length;}
    remaining=pattern[index]-phase;
  }
  const polygons=[];
  for(let j=1;j<points.length;j++){
    const [x,y]=points[j-1],[bx,by]=points[j],dx=bx-x,dy=by-y,length=Math.hypot(dx,dy);
    if(length<1e-5)continue;
    let used=0;
    while(used<length-1e-5){
      const step=Math.min(length-used,remaining),start=used/length,end=(used+step)/length;
      if(!sum||index%2===0){
        const ax=x+dx*start,ay=y+dy*start,ex=x+dx*end,ey=y+dy*end;
        const nx=-dy/length*width/2,ny=dx/length*width/2;
        polygons.push([[ax+nx,ay+ny],[ex+nx,ey+ny],[ex-nx,ey-ny],[ax-nx,ay-ny]]);
        if(cap==='round')polygons.push(disc(ax,ay,width/2),disc(ex,ey,width/2));
      }
      used+=step;remaining-=step;
      if(remaining<1e-5&&sum){index=(index+1)%pattern.length;remaining=pattern[index];}
    }
  }
  return polygons;
}

/** Runs in the browser on the240px export SVG; returns plain portable data. */
export function captureVectorCommands(svg){
  const back=[],front=[],image=svg.querySelector('image');
  const paint=(value,alpha)=>{
    if(value==='none'||alpha<=0)return;
    const channels=value.match(/[\d.]+/g)?.map(Number);
    if(!channels||channels.length<3)throw Error(`Unsupported effect paint ${value}`);
    return[...channels.slice(0,3).map(Math.round),Math.round(255*alpha*(channels[3]??1))];
  };
  for(const element of svg.querySelectorAll('path,rect,ellipse')){
    const style=getComputedStyle(element);let opacity=1;
    for(let parent=element;parent&&parent!==svg.parentElement;parent=parent.parentElement)opacity*=Number(getComputedStyle(parent).opacity);
    if(opacity<=0||style.display==='none')continue;
    const m=element.getCTM();let contours;
    if(element.tagName==='path')contours=pathContours(element.getAttribute('d')||'');
    else if(element.tagName==='rect'){
      const x=element.x.baseVal.value,y=element.y.baseVal.value,w=element.width.baseVal.value,h=element.height.baseVal.value;
      contours=[{points:[[x,y],[x+w,y],[x+w,y+h],[x,y+h],[x,y]],closed:true}];
    }else{
      const x=element.cx.baseVal.value,y=element.cy.baseVal.value,rx=element.rx.baseVal.value,ry=element.ry.baseVal.value;
      contours=[{points:Array.from({length:41},(_,i)=>[x+Math.cos(i*Math.PI/20)*rx,y+Math.sin(i*Math.PI/20)*ry]),closed:true}];
    }
    const layer=!image||(element.compareDocumentPosition(image)&Node.DOCUMENT_POSITION_FOLLOWING)?back:front;
    const add=(points,color)=>{
      if(!color||!color[3]||points.length<3)return;
      const world=points.map(([x,y])=>[m.a*x+m.c*y+m.e,m.b*x+m.d*y+m.f]);
      if(Math.max(...world.map(p=>p[0]))<0||Math.min(...world.map(p=>p[0]))>240||
        Math.max(...world.map(p=>p[1]))<0||Math.min(...world.map(p=>p[1]))>176)return;
      layer.push({points:world,color});
    };
    const fill=paint(style.fill,opacity*Number(style.fillOpacity));
    for(const contour of contours)add(contour.points,fill);
    const stroke=paint(style.stroke,opacity*Number(style.strokeOpacity)),width=parseFloat(style.strokeWidth);
    if(stroke&&width>0){
      const dashes=style.strokeDasharray==='none'?[]:style.strokeDasharray.split(/[ ,]+/).map(parseFloat);
      for(const contour of contours)for(const p of strokePolygons(contour.points,width,dashes,parseFloat(style.strokeDashoffset)||0,style.strokeLinecap))add(p,stroke);
    }
  }
  return{back,front};
}
