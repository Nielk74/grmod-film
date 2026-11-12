// SPDX-License-Identifier: GPL-2.0-only
/** Add the linked Loaded stage 1 module to one exact GR III 2.10 film pack image (the method of
 * tools/shot-animation/build-firmware-filmpack.ts). Every film pack byte is kept, apart from five hook words
 * and the RTOS length, so the looks, ratios and settings guard that saved camera settings depend on stay whole.
 * Run with root vite-node; never writes a card or contacts a camera. */
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {dirname,join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {Firmware,FRAME_SIZE,buildGrown,sectionsOf,sectionData,sum32,verifyContainer,equalRange} from '../../core/src/fw/container';
import {selfCheckGrown} from '../../core/src/fw/selfcheck';
import {GR3_210} from '../../core/src/fw/gr3x/profile';
import {branchWord} from '../../core/src/fw/aspect/arm';

const here=dirname(fileURLToPath(import.meta.url)),variant=process.env.LOADED_VARIANT??'',diag=variant==='diag'||variant==='diage'||variant==='diagf'||variant==='diagg',stage=variant==='stage3aengine'||variant==='stage3afilmpack'?'3a':variant==='stage2b'?'2b':variant==='stage2a'?'2a':variant==='diagg'?'1g':variant==='diagf'?'1f':variant==='diage'?'1e':variant==='diag'?'1d':1,out=join(here,'out',variant==='stage3aengine'?'firmware-loaded-stage3a-engine':variant==='stage3afilmpack'?'firmware-loaded-stage3a-filmpack':variant==='stage2b'?'firmware-loaded-stage2b-engine':variant==='stage2a'?'firmware-loaded-stage2a':variant==='diagg'?'firmware-loaded-stage1g-diagnostic':variant==='diagf'?'firmware-loaded-stage1f-diagnostic':variant==='diage'?'firmware-loaded-stage1e-diagnostic':diag?'firmware-loaded-stage1d-diagnostic':'firmware-loaded-stage1'),build=join(out,'build');
const hash=(b:Uint8Array)=>createHash('sha256').update(b).digest('hex');
function check(condition:unknown,message:string):asserts condition{if(!condition)throw Error(`Loaded stage 1 on film pack: ${message}`);}
const [input,output=join(out,'fwdc239b.bin')]=process.argv.slice(2);
check(input,'provide the film pack fwdc239b.bin the payload was linked against');
const pack=new Uint8Array(readFileSync(resolve(input)));
const manifest=JSON.parse(readFileSync(join(build,'payload-manifest.json'),'utf8'));
const payload=new Uint8Array(readFileSync(join(build,'loaded-payload.bin')));
check(hash(pack)===manifest.packSha256,'this is not the film pack the payload was linked against');
check(manifest.schema===1&&manifest.camera==='GR III'&&manifest.silent===true&&manifest.stage===stage&&manifest.hardwareTested===false,'manifest identity');
check(hash(payload)===manifest.payloadSha256&&payload.length===manifest.payloadBytes,'linked payload changed');
for(const [path,expected] of Object.entries(manifest.sourceHashes)){
  check(hash(new Uint8Array(readFileSync(resolve(here,'..','..',path))))===expected,`source changed after link:${path}`);
}
const fw=new Firmware(pack),decoded=fw.decoded;
check(fw.project===GR3_210.project,'not a GR III image');
const sections=sectionsOf(decoded),rtos=sections.find(s=>s.name==='RTOS')!;
check(hash(sectionData(decoded,rtos))===manifest.packRtosSha256,'film pack RTOS changed');
const rtosEnd=rtos.offset+rtos.size,base=GR3_210.rtosBase+rtos.size;
check(manifest.base===base&&base%4===0,'payload does not begin at the film pack RTOS end');
const hooks=new Map([
  [0x532d55f8,{symbol:'grmod_hook_shot',link:false}],
  [0x5316caf8,{symbol:'grmod_hook_transition_before',link:true}],
  [0x5316cb74,{symbol:'grmod_hook_transition_after',link:false}],
  [0x533918d0,{symbol:'grmod_hook_canvas_delete',link:false}],
  [0x53239818,{symbol:'grmod_hook_release',link:false}],
  ...(variant==='diagf'||variant==='diagg'||variant==='stage2a'||variant==='stage2b'||variant==='stage3aengine'||variant==='stage3afilmpack'?[[0x53228ab4,{symbol:'grmod_hook_event',link:false}] as [number,{symbol:string,link:boolean}]]:[]),
]);
check(manifest.patches.length===hooks.size,`expected ${hooks.size} hooks`);
const growth=Math.ceil((payload.length+256)/FRAME_SIZE)*FRAME_SIZE;
check(GR3_210.rtosBase+rtos.size+growth<GR3_210.ramBase,'payload reaches initialized RAM');
check(rtos.size+growth<=0x4000000,'RTOS exceeds its partition');
const patches=manifest.patches.map((patch:{address:number,expected:string,symbol:string,link:boolean,reason:string})=>{
  const contract=hooks.get(patch.address);
  check(contract&&contract.symbol===patch.symbol&&contract.link===patch.link,'camera hook contract changed');
  const offset=rtos.offset+patch.address-GR3_210.rtosBase,stock=Buffer.from(patch.expected,'hex');
  check(equalRange(decoded,offset,stock,0,4),`hook site already patched at0x${patch.address.toString(16)}`);
  const target=manifest.symbols[patch.symbol];
  check(Number.isInteger(target)&&target%4===0&&target>=base&&target<base+payload.length,'hook target outside payload');
  const word=new Uint8Array(4);
  new DataView(word.buffer).setUint32(0,branchWord(patch.address,target,14,patch.link),true);
  return{...patch,target,offset,replacement:Buffer.from(word).toString('hex')};
});
const next=new Uint8Array(decoded.length+growth);
next.set(decoded.subarray(0,rtosEnd));next.set(payload,rtosEnd);next.set(decoded.subarray(rtosEnd),rtosEnd+growth);
const view=new DataView(next.buffer);
view.setUint32(rtos.offset-4,rtos.size+growth,true);
const ranges=[{what:'RTOS length',offset:rtos.offset-4,length:4},{what:'Loaded stage 1 module',offset:rtosEnd,length:growth}];
for(const patch of patches){next.set(Buffer.from(patch.replacement,'hex'),patch.offset);ranges.push({what:patch.reason,offset:patch.offset,length:4});}
const marker=new TextEncoder().encode((variant==='stage3aengine'?'GR3-HDF-210-ENGINE-T10-LOADED-STAGE3A-HARDWARE-UNTESTED\0':variant==='stage3afilmpack'?'GR3-HDF-210-ADJ9-T10-LOADED-STAGE3A-HARDWARE-UNTESTED\0':variant==='stage2b'?'GR3-HDF-210-ENGINE-T10-LOADED-STAGE2B-HARDWARE-UNTESTED\0':variant==='stage2a'?'GR3-HDF-210-ADJ9-T10-LOADED-STAGE2A-HARDWARE-UNTESTED\0':variant==='diagg'?'GR3-HDF-210-ADJ9-T10-LOADED-STAGE1G-DIAGNOSTIC-HARDWARE-UNTESTED\0':variant==='diagf'?'GR3-HDF-210-ADJ9-T10-LOADED-STAGE1F-DIAGNOSTIC-HARDWARE-UNTESTED\0':variant==='diage'?'GR3-HDF-210-ADJ9-T10-LOADED-STAGE1E-DIAGNOSTIC-HARDWARE-UNTESTED\0':'GR3-HDF-210-ADJ9-T10-LOADED-STAGE1-HARDWARE-UNTESTED\0'));
next.set(marker,rtosEnd+growth-marker.length-4);
view.setUint32(rtosEnd+growth-4,(-sum32(next))>>>0,true);
check(sum32(next)===0,'decoded checksum repair failed');
const built=buildGrown(fw,next,[{at:rtosEnd,length:growth}]);
const checks={...selfCheckGrown(pack,built.out,ranges,next),...verifyContainer(built.out,next).checks};
check(Object.values(checks).every(Boolean),'container self-check failed: '+Object.entries(checks).filter(([,ok])=>!ok).map(([k])=>k).join(', '));
const reopened=new Firmware(built.out);
check(equalRange(reopened.decoded,0,next,0,next.length),'decoded roundtrip mismatch');
check(equalRange(reopened.header,0,fw.header,0,fw.header.length)&&equalRange(reopened.models,0,fw.models,0,fw.models.length),'model/header identity changed');
const after=sectionsOf(reopened.decoded);
const sectionReport=sections.map((section,i)=>{
  const other=after[i],beforeHash=hash(sectionData(decoded,section)),afterHash=hash(sectionData(next,other));
  check(section.name===other.name&&section.v1===other.v1&&section.v2===other.v2,'section identity changed');
  check(section.name==='RTOS'||beforeHash===afterHash,`film pack section changed:${section.name}`);
  return{name:section.name,beforeBytes:sectionData(decoded,section).length,afterBytes:sectionData(next,other).length,beforeSha256:beforeHash,afterSha256:afterHash};
});
const report={schema:1,camera:'GR III',baseVersion:'2.10',filename:'fwdc239b.bin',silent:true,stage,
  packSha256:hash(pack),outputSha256:hash(built.out),outputBytes:built.out.length,decodedBytes:next.length,
  rtosGrowth:growth,payloadBytes:payload.length,rtosRuntimeEnd:base+growth,slots:manifest.slots,hardwareTested:false,versionRaised:false,
  checks,patches,sections:sectionReport};
mkdirSync(dirname(resolve(output)),{recursive:true});mkdirSync(build,{recursive:true});
writeFileSync(resolve(output),built.out);
writeFileSync(join(out,'build-report.json'),JSON.stringify(report,null,2)+'\n','utf8');
writeFileSync(join(build,'patched-rtos.bin'),sectionData(next,after.find(s=>s.name==='RTOS')!));
writeFileSync(join(build,'pack-rtos.bin'),sectionData(decoded,rtos));
writeFileSync(join(out,'SHA256SUMS.txt'),`${report.outputSha256}  fwdc239b.bin\n`,'utf8');
console.log(JSON.stringify({output:resolve(output),sha256:report.outputSha256,bytes:report.outputBytes,rtosEnd:'0x'+(base+growth).toString(16),hardwareTested:false},null,2));
