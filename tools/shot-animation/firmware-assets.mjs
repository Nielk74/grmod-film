// SPDX-License-Identifier: GPL-2.0-only
import {sequenceAt,poseMirror} from './sequence.mjs';

export const TERMINAL_HEADER=80,TERMINAL_SAMPLE=52;
export const TERMINAL_SAMPLES=228,TERMINAL_WIDTH=240,TERMINAL_HEIGHT=176;
const IDS=['dash','portal','rocket'];
const crcTable=Uint32Array.from({length:256},(_,value)=>{
  for(let n=0;n<8;n++)value=value&1?0xedb88320^(value>>>1):value>>>1;
  return value>>>0;
});
export function crc32(bytes){let crc=0xffffffff;for(const b of bytes)crc=crcTable[(crc^b)&255]^(crc>>>8);return(crc^0xffffffff)>>>0;}
const check=(yes,reason)=>{if(!yes)throw Error(`Terminal asset: ${reason}`);};
const integer=(n,min,max)=>Number.isInteger(n)&&n>=min&&n<=max;

export function motionSample(ms,id){
  const s=sequenceAt(ms,id),angle=s.rotation*Math.PI/180,c=Math.cos(angle),n=Math.sin(angle);
  const mirror=poseMirror(s.pose,s.facing),sx=s.scaleX*mirror,sy=s.scaleY;
  const a=c/sx,b=-n/sy,d=c/sy,e=n/sx,px=120+s.x,py=168+s.y;
  const inverse=[a,b,e,d,64-a*px-e*py,128-b*px-d*py].map(v=>Math.round(v*65536));
  const corners=[[0,0],[128,0],[0,128],[128,128]].map(([u,v])=>[
    px+c*sx*(u-64)-n*sy*(v-128),py+n*sx*(u-64)+c*sy*(v-128),
  ]);
  const bounds=[Math.floor(Math.min(...corners.map(p=>p[0]))),Math.floor(Math.min(...corners.map(p=>p[1]))),
    Math.ceil(Math.max(...corners.map(p=>p[0]))),Math.ceil(Math.max(...corners.map(p=>p[1])))];
  return{pose:s.pose,opacity:Math.round(s.opacity*255),inverse,bounds,facing:s.facing};
}

function encodePolygons(polygons=[]){
  const parts=[];
  check(polygons.length<=4096,'vector command count');
  for(const {color,points} of polygons){
    check(color.length===4&&color.every(n=>integer(n,0,255)),'vector color');
    check(points.length>=3&&points.length<=256,'vector point count');
    const part=new Uint8Array(8+points.length*4),v=new DataView(part.buffer);
    part.set(color,0);v.setUint16(4,points.length,true);
    points.forEach(([x,y],i)=>{
      const qx=Math.round(x*16),qy=Math.round(y*16);
      check(integer(qx,-16384,16384)&&integer(qy,-16384,16384),'vector point bounds');
      v.setInt16(8+i*4,qx,true);v.setInt16(10+i*4,qy,true);
    });
    parts.push(part);
  }
  const out=new Uint8Array(4+parts.reduce((n,p)=>n+p.length,0)),v=new DataView(out.buffer);
  v.setUint16(0,parts.length,true);let at=4;
  for(const p of parts){out.set(p,at);at+=p.length;}
  return out;
}

export function encodeTerminalAsset({palette,indices,samples}){
  check(palette.length>=1&&palette.length<=256&&palette.every(p=>p.length===4&&p.every(n=>integer(n,0,255))),'palette');
  check(indices.length===128*128*12,'pose indices length');
  check(indices.every(n=>n<palette.length),'palette index');
  check(samples.length===3&&samples.every(a=>a.length===228),'three complete motion timelines');
  const vectorParts=[],lookup=new Map();let vectorBytes=0;
  const vectors=polygons=>{
    const bytes=encodePolygons(polygons),key=Buffer.from(bytes).toString('base64');
    if(!lookup.has(key)){lookup.set(key,[vectorBytes,bytes.length]);vectorParts.push(bytes);vectorBytes+=bytes.length;}
    return lookup.get(key);
  };
  const records=[];
  for(const track of samples)for(const s of track){
    check(integer(s.pose,0,11)&&integer(s.opacity,0,255),'pose/opacity');
    check(s.inverse.length===6&&s.inverse.every(n=>integer(n,-0x40000000,0x3fffffff)),'inverse affine');
    check(s.bounds.length===4&&s.bounds.every(n=>integer(n,-32768,32767)),'sprite bounds');
    const record=new Uint8Array(52),v=new DataView(record.buffer);
    v.setUint16(0,s.pose,true);record[2]=s.opacity;
    s.inverse.forEach((n,i)=>v.setInt32(4+i*4,n,true));
    s.bounds.forEach((n,i)=>v.setInt16(28+i*2,n,true));
    const back=vectors(s.back),front=vectors(s.front);
    [back[0],back[1],front[0],front[1]].forEach((n,i)=>v.setUint32(36+i*4,n,true));
    records.push(record);
  }
  const paletteAt=80,indicesAt=paletteAt+palette.length*4,tracksAt=indicesAt+indices.length;
  const vectorsAt=tracksAt+records.length*52,total=vectorsAt+vectorBytes;
  const out=new Uint8Array(total),v=new DataView(out.buffer);
  out.set(new TextEncoder().encode('TRM2'));
  [2,80,240,176,128,128,12,palette.length,30,3,228,52].forEach((n,i)=>v.setUint16(4+i*2,n,true));
  [7600,1400,5000,1200,paletteAt,indicesAt,tracksAt,vectorsAt,total].forEach((n,i)=>v.setUint32(28+i*4,n,true));
  palette.forEach((p,i)=>out.set(p,paletteAt+i*4));out.set(indices,indicesAt);
  records.forEach((r,i)=>out.set(r,tracksAt+i*52));let at=vectorsAt;
  for(const part of vectorParts){out.set(part,at);at+=part.length;}
  v.setUint32(64,crc32(out.subarray(80)),true);
  readTerminalAsset(out);
  return out;
}

export function readTerminalAsset(bytes){
  check(bytes.length>=80,'header length');
  const v=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength),u16=o=>v.getUint16(o,true),u32=o=>v.getUint32(o,true);
  check(String.fromCharCode(...bytes.subarray(0,4))==='TRM2'&&u16(4)===2&&u16(6)===80,'magic/version');
  check(u16(8)===240&&u16(10)===176&&u16(12)===128&&u16(14)===128&&u16(16)===12,'dimensions/poses');
  const colors=u16(18),count=u16(24),stride=u16(26),paletteAt=u32(44),indicesAt=u32(48),tracksAt=u32(52),vectorsAt=u32(56);
  check(colors>=1&&colors<=256&&u16(20)===30&&u16(22)===3&&count===228&&stride===52,'timeline layout');
  check(u32(28)===7600&&u32(32)===1400&&u32(36)===5000&&u32(40)===1200,'phase duration');
  check(u32(60)===bytes.length&&bytes.length<=4*1024*1024,'total size/length');
  check(u32(68)===0&&u32(72)===0&&u32(76)===0,'reserved header');
  check(paletteAt===80&&indicesAt===paletteAt+colors*4&&tracksAt===indicesAt+196608&&vectorsAt===tracksAt+3*count*stride&&vectorsAt+4<=bytes.length,'section offset/layout');
  check(u32(64)===crc32(bytes.subarray(80)),'CRC');
  const indices=bytes.slice(indicesAt,tracksAt),palette=Array.from({length:colors},(_,i)=>Array.from(bytes.subarray(paletteAt+i*4,paletteAt+i*4+4)));
  check(indices.every(i=>i<colors),'palette index');
  const seen=new Set();
  for(let at=tracksAt;at<vectorsAt;at+=52){
    check(u16(at)<12&&bytes[at+3]===0,'sample pose/reserved');
    for(const off of [36,44]){
      const start=u32(at+off),size=u32(at+off+4),key=`${start}:${size}`;
      check(start%4===0&&size%4===0&&size>=4&&start<=bytes.length-vectorsAt&&size<=bytes.length-vectorsAt-start,'vector extent');
      if(seen.has(key))continue;seen.add(key);
      let cursor=vectorsAt+start;const end=cursor+size,commands=u16(cursor);
      check(commands<=4096&&u16(cursor+2)===0,'vector count/reserved');cursor+=4;
      for(let n=0;n<commands;n++){
        check(cursor+8<=end,'vector command extent');const points=u16(cursor+4);
        check(points>=3&&points<=256&&u16(cursor+6)===0,'vector point count/reserved');
        check(cursor+8+points*4<=end,'vector point extent');
        for(let point=0;point<points*2;point++)check(integer(v.getInt16(cursor+8+point*2,true),-16384,16384),'vector point bounds');
        cursor+=8+points*4;
      }
      check(cursor===end,'vector trailing bytes');
    }
  }
  return{palette,indices,sampleCount:count,durationMs:7600,phases:[1400,5000,1200],trackBytes:vectorsAt-tracksAt,
    vectorBytes:bytes.length-vectorsAt,uniqueVectorStreams:seen.size,bytes:bytes.length};
}
