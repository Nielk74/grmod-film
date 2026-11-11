// SPDX-License-Identifier: GPL-2.0-only
/** Experimental post-v3 installer. No public patch format/default is changed. */
import { createHash } from 'node:crypto';
import { Firmware, FRAME_SIZE, buildGrown, sum32, verifyContainer } from '../../core/src/fw/container';
import { assembleWords, branchWord, wordsToBytes } from '../../core/src/fw/aspect/arm';

export const OFFICIAL_SHA='d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4';
export const BASELINE_SHA='0eedc01b7f61cee64d6228978b0f99a01090a49491d6cb103dbfee4a3cc4fa59';
export const RTOS_SHA='8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67';
export const digest=(b:Uint8Array)=>createHash('sha256').update(b).digest('hex');
const BASE=0x53000000, JPEG=0x535047d4, CAPTURE=0x5345133c;
const hex=(n:number)=>'0x'+n.toString(16);
const assert=(ok:unknown,message:string)=>{if(!ok)throw new Error(message);};
export type Module={code:string;bytes:number;sha256:string;source_sha256:string;position_independent:boolean;entries:{face_fill:number;face_capture_clear:number}};

function liftTable():Uint8Array {
  return Uint8Array.from({length:256},(_,i)=>{
    const s=i/255,v=s<=.04045?s/12.92:((s+.055)/1.055)**2.4;
    const t=Math.min(1,Math.max(0,(v-.45)/.45)),ev=.85*(1-t*t*(3-2*t));
    const n=v*2**ev,out=n<=.0031308?12.92*n:1.055*n**(1/2.4)-.055;
    return Math.max(0,Math.min(255,Math.round(out*255))-i);
  });
}

export function installFace(baseline:Uint8Array,official:Uint8Array,module:Module,source:Uint8Array) {
  assert(digest(official)===OFFICIAL_SHA,'Requires exact pristine GR III 2.10');
  assert(digest(baseline)===BASELINE_SHA,'Requires reviewed v3 baseline with extra FilmMTF disabled');
  const native=new Firmware(official),fw=new Firmware(baseline);
  const originalRtos=native.sections().find(s=>s.name==='RTOS')!,rtos=fw.sections().find(s=>s.name==='RTOS')!;
  assert(originalRtos&&rtos,'Missing RTOS');
  assert(digest(native.decoded.subarray(originalRtos.offset,originalRtos.offset+originalRtos.size))===RTOS_SHA,'Original RTOS identity');
  const code=Uint8Array.from(Buffer.from(module.code,'base64'));
  assert(code.length===module.bytes&&digest(code)===module.sha256&&module.position_independent,'Native module identity');
  assert(digest(source)===module.source_sha256,'Regenerate native module from current source');
  assert(module.entries.face_fill===0&&Number.isInteger(module.entries.face_capture_clear)&&
    module.entries.face_capture_clear>0&&module.entries.face_capture_clear<code.length&&!(module.entries.face_capture_clear&3),'Native entry bounds');
  const at=rtos.offset+rtos.size,growth=FRAME_SIZE,address=BASE+rtos.size;
  assert(address+growth<0x55000000,'RTOS would overlap initialized RAM');
  const out=new Uint8Array(fw.decoded.length+growth);
  out.set(fw.decoded.subarray(0,at));out.set(fw.decoded.subarray(at),at+growth);
  const view=new DataView(out.buffer),read=(addr:number)=>view.getUint32(rtos.offset+addr-BASE,true);
  const writes:{purpose:string;address:string;decoded_offset:number;before:string;after:string}[]=[];
  function patch(addr:number,expected:number,replacement:number,purpose:string){
    assert(read(addr)===expected,'Instruction guard: '+purpose);
    const offset=rtos.offset+addr-BASE;
    view.setUint32(offset,replacement,true);writes.push({purpose,address:hex(addr),decoded_offset:offset,before:hex(expected),after:hex(replacement)});
  }
  const prior=read(JPEG);assert((prior>>>24)===0xea,'JPEG entry is not the v3 chain branch');
  const displacement=(prior<<8)>>6,tail=(JPEG+8+displacement)>>>0;
  assert(tail>=BASE+originalRtos.size&&tail<address,'JPEG chain target outside baseline appended code');
  assert(read(CAPTURE)===0xe1a0c00d&&read(CAPTURE+4)===0xe92ddff0,'Capture entry guard');
  const context=address+0x1000,lut=context+0x100,jpegStub=context+0x300,captureStub=context+0x380;
  assert(code.length<=0x1000,'Native module exceeds reserved slot');out.set(code,at);
  const contextWords=[0x314c4646,0x536bbc30,0x536bbcc0,0x536bbcac,lut,6000,4000,20,0];
  out.set(wordsToBytes(contextWords),at+0x1000);
  // Astia, Nostalgic Neg, Kodachrome 64, Gold 200: one-input chroma contraction.
  for(const film of [1,4,10,12])out[at+0x1000+36+film]=1;
  out.set(liftTable(),at+0x1100);
  const loadContext=`movw r0,#${context&65535}; movt r0,#${context>>>16}`;
  const prefix='push {r0-r3,ip,lr}; mrs r3,apsr; push {r2,r3};';
  const suffix='pop {r2,r3}; msr apsr_nzcvq,r3; pop {r0-r3,ip,lr};';
  const jpegCode=wordsToBytes(assembleWords(`${prefix} ldr r1,[r1,#8]; ${loadContext}; bl #${address+module.entries.face_fill}; ${suffix} b #${tail}`,jpegStub));
  // Original third stack argument is CommonProperty*. Save/restore all volatile
  // state and flags, then replay the displaced native mov ip,sp exactly once.
  const captureCode=wordsToBytes(assembleWords(`${prefix} ldr r0,[sp,#40]; bl #${address+module.entries.face_capture_clear}; ${suffix} mov ip,sp; b #${CAPTURE+4}`,captureStub));
  assert(jpegCode.length<=0x80&&captureCode.length<=0x80,'Wrapper slot overflow');
  out.set(jpegCode,at+jpegStub-address);out.set(captureCode,at+captureStub-address);
  patch(JPEG,prior,branchWord(JPEG,jpegStub),'Face JPEG wrapper before existing v3 chain');
  patch(CAPTURE,0xe1a0c00d,branchWord(CAPTURE,captureStub),'Clear current/B count before native capture');
  view.setUint32(rtos.offset-4,rtos.size+growth,true);
  view.setUint32(at+growth-4,(-sum32(out))>>>0,true);assert(sum32(out)===0,'Decoded checksum');
  // Complete byte audit: only two guarded entry words and RTOS size may change
  // in baseline bytes. Every following section is identical after the insertion.
  const changed=new Set<number>([rtos.offset-4,rtos.offset-3,rtos.offset-2,rtos.offset-1]);
  for(const w of writes)for(let j=0;j<4;j++)changed.add(w.decoded_offset+j);
  for(let i=0;i<fw.decoded.length;i++)assert(changed.has(i)||out[i+(i>=at?growth:0)]===fw.decoded[i],'Unexpected baseline byte '+hex(i));
  const built=buildGrown(fw,out,[{at,length:growth}]);verifyContainer(built.out,out);
  const reread=new Firmware(built.out),rr=reread.sections().find(s=>s.name==='RTOS')!;
  assert(rr.size===rtos.size+growth&&digest(reread.header)===digest(native.header)&&digest(reread.models)===digest(native.models),'Container readback identity');
  return {bytes:built.out,rtos:reread.decoded.slice(rr.offset,rr.offset+rr.size),report:{
    experiment:'GR III face fill + one-input skin chroma keeper',official_sha256:OFFICIAL_SHA,original_rtos_sha256:RTOS_SHA,
    baseline_sha256:BASELINE_SHA,candidate_sha256:digest(built.out),candidate_bytes:built.out.length,
    module_sha256:module.sha256,module_source_sha256:module.source_sha256,patches:writes,
    appended:{address:hex(address),decoded_offset:at,bytes:growth,module_bytes:code.length,context:hex(context),lut:hex(lut),jpeg_wrapper:hex(jpegStub),capture_wrapper:hex(captureStub),chain_tail:hex(tail)},
    jpeg_wrapper_bytes:Buffer.from(jpegCode).toString('hex'),capture_wrapper_bytes:Buffer.from(captureCode).toString('hex'),
    full_baseline_diff_audited:true,container_readback_verified:true,extra_film_mtf:false,hardware_tested:false,
    limits:['RAW development unsupported/unverified; saved face records may apply','Unsupported geometry no-ops','Hardware timing and concurrency unmeasured']}};
}
