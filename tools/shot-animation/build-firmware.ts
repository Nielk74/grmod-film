// SPDX-License-Identifier: GPL-2.0-only
/** Package the linked Terminal module into the exact official GR III2.10 image.
 * Run with root vite-node; never writes a card or contacts a camera. */
import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {dirname,join,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {Firmware,FRAME_SIZE,buildGrown,sectionsOf,sectionData,sum32,verifyContainer,equalRange} from '../../core/src/fw/container';
import {selfCheckGrown} from '../../core/src/fw/selfcheck';
import {GR3_210,openGr3xOfficial} from '../../core/src/fw/gr3x/profile';
import {branchWord} from '../../core/src/fw/aspect/arm';

const here=dirname(fileURLToPath(import.meta.url)),out=join(here,'out','firmware');
const hash=(b:Uint8Array)=>createHash('sha256').update(b).digest('hex');
function check(condition:unknown,message:string):asserts condition{if(!condition)throw Error(`Terminal firmware: ${message}`);}
const [input,output=join(out,'fwdc239b.bin')]=process.argv.slice(2);
check(input,'provide the exact official GR III2.10 fwdc239b.bin');
const original=new Uint8Array(readFileSync(resolve(input)));
const {fw,decoded,profile}=await openGr3xOfficial(original);
check(profile===GR3_210,'this build supports GR III2.10 only');
const manifest=JSON.parse(readFileSync(join(out,'payload-manifest.json'),'utf8'));
const payload=new Uint8Array(readFileSync(join(out,'terminal-payload.bin')));
check(manifest.schema===1&&manifest.camera==='GR III'&&manifest.rtosSha256===profile.rtosSha256,'payload target identity');
check(manifest.payloadSha256===hash(payload)&&manifest.payloadBytes===payload.length,'linked payload changed');
check(manifest.hardwareTested===false,'hardware status must be explicit');
const sections=sectionsOf(decoded),rtos=sections.find(s=>s.name==='RTOS')!;
const rtosEnd=rtos.offset+rtos.size,base=profile.rtosBase+rtos.size;
check(manifest.base===base&&base%4===0,'payload does not begin at RTOS end');
const hookContracts=new Map([
  [0x532d55f8,{symbol:'grmod_hook_shot',link:false}],
  [0x5316caf8,{symbol:'grmod_hook_transition_before',link:true}],
  [0x5316cb74,{symbol:'grmod_hook_transition_after',link:false}],
  [0x533918d0,{symbol:'grmod_hook_canvas_delete',link:false}],
  [0x53239818,{symbol:'grmod_hook_release',link:false}],
  [0x53568d58,{symbol:'grmod_hook_audio_shutdown',link:false}],
]);
check(Array.isArray(manifest.patches)&&manifest.patches.length===7,'missing camera hooks/RAM reservation');
check(manifest.reservedRam?.address===0x55804374&&manifest.reservedRam.bytes===8&&manifest.reservedRam.audioShutdownLatch===0x55804378&&manifest.reservedRam.zeroFillEnd===0x55804380,'invalid writable adapter anchor/latch');
for(const [path,expected] of Object.entries(manifest.sourceHashes ?? {})){
  const source=resolve(here,'..','..',path);
  check(hash(new Uint8Array(readFileSync(source)))===expected,`source changed after link:${path}`);
}
const growth=Math.ceil((payload.length+256)/FRAME_SIZE)*FRAME_SIZE;
check(profile.rtosBase+rtos.size+growth<profile.ramBase,'payload reaches initialized RAM');
check(rtos.size+growth<=0x4000000,'RTOS exceeds its partition');
const occupied=new Set<number>(),patches=[];
for(const patch of manifest.patches){
  const address=patch.address,offset=rtos.offset+address-profile.rtosBase;
  check(Number.isInteger(address)&&address%4===0&&offset>=rtos.offset&&offset+4<=rtosEnd,'hook outside stock RTOS');
  check(!occupied.has(address),'overlapping camera hooks');occupied.add(address);
  const stock=Buffer.from(patch.expected,'hex');
  check(stock.length===4&&equalRange(decoded,offset,stock,0,4),`stock signature mismatch at0x${address.toString(16)}`);
  const replacement=new Uint8Array(4);
  let target:number|undefined;
  if(address===0x53000460){
    check(patch.expected==='74438055'&&patch.replacement==='80438055'&&!patch.symbol,'invalid startup RAM reservation');
    replacement.set(Buffer.from(patch.replacement,'hex'));
  }else{
    const contract=hookContracts.get(address);
    check(contract&&patch.symbol===contract.symbol&&patch.link===contract.link,'camera hook contract changed');
    target=manifest.symbols[patch.symbol];
    check(typeof target==='number'&&Number.isInteger(target)&&target%4===0&&target>=base&&target<base+payload.length,'hook target outside payload');
    new DataView(replacement.buffer).setUint32(0,branchWord(address,target,14,patch.link===true),true);
  }
  patches.push({...patch,target,offset,replacement:Buffer.from(replacement).toString('hex')});
}
// Every service body used by the adapter is also guarded against the known image.
check(Array.isArray(manifest.serviceGuards)&&manifest.serviceGuards.length>=12,'missing native service guards');
for(const guard of manifest.serviceGuards){
  const offset=rtos.offset+guard.address-profile.rtosBase,expected=Buffer.from(guard.expected,'hex');
  check(expected.length>=4&&offset>=rtos.offset&&offset+expected.length<=rtosEnd&&equalRange(decoded,offset,expected,0,expected.length),
    `native ABI signature mismatch at0x${guard.address.toString(16)}`);
}
const next=new Uint8Array(decoded.length+growth);
next.set(decoded.subarray(0,rtosEnd));next.set(payload,rtosEnd);next.set(decoded.subarray(rtosEnd),rtosEnd+growth);
const view=new DataView(next.buffer);
view.setUint32(rtos.offset-4,rtos.size+growth,true);
const ranges=[{what:'Terminal RTOS length',offset:rtos.offset-4,length:4},
  {what:'Terminal ARM, immutable poses/vectors/WAV and state',offset:rtosEnd,length:growth}];
for(const patch of patches){next.set(Buffer.from(patch.replacement,'hex'),patch.offset);ranges.push({what:patch.reason,offset:patch.offset,length:4});}
const marker=new TextEncoder().encode('GR3-210-NEON-TERMINAL-HARDWARE-UNTESTED\0');
next.set(marker,rtosEnd+growth-marker.length-4);
view.setUint32(rtosEnd+growth-4,(-sum32(next))>>>0,true);
check(sum32(next)===0,'decoded checksum repair failed');
const built=buildGrown(fw,next,[{at:rtosEnd,length:growth}]);
const checks={...selfCheckGrown(original,built.out,ranges,next),...verifyContainer(built.out,next).checks};
check(Object.values(checks).every(Boolean),'container self-check failed: '+Object.entries(checks).filter(([,ok])=>!ok).map(([k])=>k).join(', '));
const reopened=new Firmware(built.out);
check(equalRange(reopened.decoded,0,next,0,next.length),'decoded roundtrip mismatch');
check(equalRange(reopened.header,0,fw.header,0,fw.header.length)&&equalRange(reopened.models,0,fw.models,0,fw.models.length),'model/header identity changed');
const after=sectionsOf(reopened.decoded);
const sectionReport=sections.map((section,i)=>{
  const changed=section.name==='RTOS',other=after[i];
  check(section.name===other.name&&section.v1===other.v1&&section.v2===other.v2,'section identity changed');
  const beforeHash=hash(sectionData(decoded,section)),afterHash=hash(sectionData(next,other));
  check(changed||beforeHash===afterHash,`unrelated section changed:${section.name}`);
  return{name:section.name,beforeBytes:sectionData(decoded,section).length,afterBytes:sectionData(next,other).length,beforeSha256:beforeHash,afterSha256:afterHash};
});
const report={schema:1,camera:'GR III',baseVersion:'2.10',filename:'fwdc239b.bin',
  inputSha256:hash(original),outputSha256:hash(built.out),outputBytes:built.out.length,decodedSha256:hash(next),
  rtosGrowth:growth,payloadBytes:payload.length,rtosRuntimeEnd:profile.rtosBase+rtos.size+growth,
  phasesMs:[1400,5000,1200],sequences:['Disk Dash','Pixel Portal','Rocket Delivery'],randomSelection:true,
  spritePoses:12,spriteDimensions:[128,128],photographicImagePipelineModified:false,
  modelProject:fw.project,hardwareTested:false,versionRaised:false,checks,patches,sections:sectionReport,
  reservedRam:manifest.reservedRam,sourceHashes:manifest.sourceHashes,evidence:manifest.evidence,limits:manifest.limits};
mkdirSync(dirname(resolve(output)),{recursive:true});
check(!existsSync(resolve(output))||hash(new Uint8Array(readFileSync(resolve(output))))===hash(built.out),'refusing to replace a different existing firmware output');
writeFileSync(resolve(output),built.out);
writeFileSync(join(out,'build-report.json'),JSON.stringify(report,null,2)+'\n','utf8');
writeFileSync(join(out,'patched-rtos.bin'),sectionData(next,after.find(s=>s.name==='RTOS')!));
writeFileSync(join(out,'SHA256SUMS.txt'),`${report.outputSha256}  fwdc239b.bin\n`,'utf8');
console.log(JSON.stringify({output:resolve(output),sha256:report.outputSha256,bytes:report.outputBytes,checks,hardwareTested:false},null,2));
