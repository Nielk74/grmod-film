// GSA1 v1: little-endian header, absolute frame offsets, RGB565 + 8-bit alpha RLE.
// Alpha is quantized to 17 levels; transparent pixels have canonical zero color.
export function crc32(bytes) {
  let crc=0xffffffff;
  for(const byte of bytes){crc^=byte;for(let bit=0;bit<8;bit++)crc=(crc>>>1)^((crc&1)?0xedb88320:0);}
  return (crc^0xffffffff)>>>0;
}
const fail=message=>{throw new Error(`GSA1: ${message}`);};
export function encodeAnimation({width,height,fps,frames}) {
  if(!Number.isInteger(width)||!Number.isInteger(height)||width<1||height<1||width>240||height>176)fail('dimensions');
  if(fps!==20||frames.length!==100)fail('expected five seconds at 20 fps');
  const chunks=[],offsets=[];
  let cursor=32+(frames.length+1)*4;
  for(const frame of frames){
    if(frame.length!==width*height*4)fail('RGBA frame size');
    offsets.push(cursor);
    const runs=[];
    let priorColor=-1,priorAlpha=-1,count=0;
    const flush=()=>{if(count)runs.push(count&255,count>>>8,priorColor&255,priorColor>>>8,priorAlpha,0);};
    for(let p=0;p<frame.length;p+=4){
      const alpha=Math.round(frame[p+3]/17)*17;
      const color=alpha?((frame[p]>>3)<<11)|((frame[p+1]>>2)<<5)|(frame[p+2]>>3):0;
      if(count && (color!==priorColor||alpha!==priorAlpha||count===65535)){flush();count=0;}
      priorColor=color;priorAlpha=alpha;count++;
    }
    flush();const chunk=new Uint8Array(runs);chunks.push(chunk);cursor+=chunk.length;
  }
  offsets.push(cursor);
  if(cursor>8*1024*1024)fail('size exceeds 8 MiB');
  const bytes=new Uint8Array(cursor),view=new DataView(bytes.buffer);
  bytes.set(new TextEncoder().encode('GSA1'));
  for(const [at,value] of [[4,1],[6,width],[8,height],[10,fps],[12,frames.length]])view.setUint16(at,value,true);
  view.setUint32(16,5000,true);view.setUint32(20,cursor,true);view.setUint32(28,32,true);
  offsets.forEach((offset,index)=>view.setUint32(32+index*4,offset,true));
  chunks.forEach((chunk,index)=>bytes.set(chunk,offsets[index]));
  view.setUint32(24,crc32(bytes.subarray(32)),true);
  return bytes;
}

export function decodeAnimation(input) {
  const bytes=input instanceof Uint8Array?input:new Uint8Array(input);
  if(bytes.length<32||bytes.length>8*1024*1024)fail('size');
  const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
  if(new TextDecoder().decode(bytes.subarray(0,4))!=='GSA1')fail('magic');
  if(view.getUint16(4,true)!==1)fail('version');
  const width=view.getUint16(6,true),height=view.getUint16(8,true),fps=view.getUint16(10,true),count=view.getUint16(12,true);
  if(!width||!height||width>240||height>176)fail('dimensions');
  if(fps!==20||count!==100||view.getUint32(16,true)!==5000)fail('timing');
  if(view.getUint16(14,true)!==0)fail('reserved');
  if(view.getUint32(20,true)!==bytes.length)fail('size');
  if(view.getUint32(28,true)!==32||bytes.length<32+(count+1)*4)fail('table');
  if(view.getUint32(24,true)!==crc32(bytes.subarray(32)))fail('CRC mismatch');
  if(view.getUint32(32,true)!==32+(count+1)*4||view.getUint32(32+count*4,true)!==bytes.length)fail('offset bounds');
  const frames=[];
  for(let frame=0;frame<count;frame++){
    const start=view.getUint32(32+frame*4,true),end=view.getUint32(36+frame*4,true);
    if(start>end||end>bytes.length||(end-start)%6)fail('offset bounds');
    const rgba=new Uint8Array(width*height*4);let position=0;
    for(let p=start;p<end;p+=6){
      const run=view.getUint16(p,true),color=view.getUint16(p+2,true),alpha=bytes[p+4];
      if(!run||position+run>width*height||bytes[p+5]||alpha%17)fail('invalid run');
      const r=color>>>11,g=(color>>>5)&63,b=color&31;
      for(let n=0;n<run;n++){rgba.set([(r<<3)|(r>>>2),(g<<2)|(g>>>4),(b<<3)|(b>>>2),alpha],position++*4);}
    }
    if(position!==width*height)fail('incomplete run coverage');
    frames.push(rgba);
  }
  return {width,height,fps,durationMs:5000,frames};
}
