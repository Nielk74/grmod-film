import {crc32} from './codec.mjs';
import {KEY_TIMES} from './timing.mjs';
const fail=message=>{throw new Error(`GSP1: ${message}`);};
// Up to twelve small poses sharing a palette and explicit irregular timings.
export function encodePoses({width,height,poses,keyTimes=poses.length===3?[0,1650,3350]:KEY_TIMES}) {
  if(!Number.isInteger(width)||!Number.isInteger(height)||width<1||height<1||width>128||height>128)fail('dimensions');
  if(poses.length<1||poses.length>12||keyTimes.length!==poses.length)fail('pose timing count');
  if(keyTimes.some((ms,i)=>!Number.isInteger(ms)||ms<0||ms>=5000||(i===0?ms!==0:ms<=keyTimes[i-1])))fail('key times');
  const palette=[],lookup=new Map(),indices=[];
  for(const pose of poses){
    if(pose.length!==width*height*4)fail('RGBA size');
    for(let p=0;p<pose.length;p+=4){
      const alpha=Math.round(pose[p+3]/17)*17;
      const color=alpha?((pose[p]>>3)<<11)|((pose[p+1]>>2)<<5)|(pose[p+2]>>3):0;
      const key=color*256+alpha;
      if(!lookup.has(key)){
        if(palette.length>=256)fail('quantize artwork to at most 256 colors before encoding');
        lookup.set(key,palette.length);palette.push([color,alpha]);
      }
      indices.push(lookup.get(key));
    }
  }
  const dataOffset=32+palette.length*4+poses.length*4;
  const bytes=new Uint8Array(dataOffset+indices.length),view=new DataView(bytes.buffer);
  bytes.set(new TextEncoder().encode('GSP1'));
  for(const [at,n] of [[4,1],[6,width],[8,height],[10,poses.length],[12,palette.length]])view.setUint16(at,n,true);
  view.setUint32(16,5000,true);view.setUint32(20,bytes.length,true);view.setUint32(28,dataOffset,true);
  palette.forEach(([color,alpha],i)=>{view.setUint16(32+i*4,color,true);bytes[34+i*4]=alpha;});
  keyTimes.forEach((ms,i)=>view.setUint32(32+palette.length*4+i*4,ms,true));
  bytes.set(indices,dataOffset);view.setUint32(24,crc32(bytes.subarray(32)),true);
  return bytes;
}
export function decodePoses(bytes) {
  if(bytes.length<32)fail('size');
  const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
  if(new TextDecoder().decode(bytes.subarray(0,4))!=='GSP1'||view.getUint16(4,true)!==1)fail('format');
  const width=view.getUint16(6,true),height=view.getUint16(8,true),count=view.getUint16(10,true),colors=view.getUint16(12,true);
  if(!width||!height||width>128||height>128)fail('dimensions');
  if(!count||count>12||view.getUint16(14,true)||view.getUint32(16,true)!==5000)fail('timing');
  if(!colors||colors>256)fail('palette');
  const offset=32+colors*4+count*4;
  if(view.getUint32(28,true)!==offset||view.getUint32(20,true)!==bytes.length||bytes.length!==offset+width*height*count)fail('size');
  if(view.getUint32(24,true)!==crc32(bytes.subarray(32)))fail('CRC');
  const keyTimes=Array.from({length:count},(_,i)=>view.getUint32(32+colors*4+i*4,true));
  keyTimes.forEach((ms,i)=>{if(ms>=5000||(i===0?ms!==0:ms<=keyTimes[i-1]))fail('key times');});
  const palette=[];
  for(let i=0;i<colors;i++){
    const color=view.getUint16(32+i*4,true),a=bytes[34+i*4];
    if(a%17||bytes[35+i*4])fail('palette alpha');
    const r=color>>>11,g=(color>>>5)&63,b=color&31;
    palette.push([(r<<3)|(r>>>2),(g<<2)|(g>>>4),(b<<3)|(b>>>2),a]);
  }
  const poses=[];
  for(let frame=0;frame<count;frame++){
    const rgba=new Uint8Array(width*height*4);
    for(let pixel=0;pixel<width*height;pixel++){
      const index=bytes[offset+frame*width*height+pixel];
      if(index>=colors)fail('palette index');
      rgba.set(palette[index],pixel*4);
    }
    poses.push(rgba);
  }
  return{width,height,keyTimes,durationMs:5000,colors,poses};
}
