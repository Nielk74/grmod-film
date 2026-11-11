/** GR III2.10 isolated experimental tripod trichrome candidate. No camera I/O. */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { execFileSync } from 'node:child_process';
import { Firmware, buildGrown, sectionsOf, sha256Hex, sum32, FRAME_SIZE, verifyContainer } from '../../core/src/fw/container';
import { selfCheckGrown } from '../../core/src/fw/selfcheck';
import { branchWord } from '../../core/src/fw/aspect/arm';
import { openGr3xOfficial } from '../../core/src/fw/gr3x/profile';

const root=process.cwd(),out=resolve(root,'scratch/trichrome-firmware');mkdirSync(out,{recursive:true});
const officialPath='C:/Users/Antoine/project/grmod-film/scratch/video-firmware-high-rate-2026-11-01/original/fwdc239b.bin';
const original=new Uint8Array(readFileSync(officialPath));const {profile}=await openGr3xOfficial(original);
if(profile.id!=='gr3-hdf-2.10')throw Error('GR III2.10 only');
const baselinePath=resolve(out,'baseline-no-extra-mtf/fwdc239b.bin');
const raw=new Uint8Array(readFileSync(baselinePath));
const baselineReport=JSON.parse(readFileSync(resolve(out,'baseline-report.json'),'utf8'));
const BASELINE_SHA='0eedc01b7f61cee64d6228978b0f99a01090a49491d6cb103dbfee4a3cc4fa59';
if(await sha256Hex(raw)!==BASELINE_SHA||baselineReport.sha256!==BASELINE_SHA)throw Error('Baseline hash mismatch');
if(baselineReport.transformation!=='Only FILM_MTF set emptied; import paths adapted for scratch execution')throw Error('Wrong MTF baseline');
const fw=new Firmware(raw),official=new Firmware(original),rtos=sectionsOf(fw.decoded).find(s=>s.name==='RTOS')!;
const officialRtos=sectionsOf(official.decoded).find(s=>s.name==='RTOS')!;
const dv=new DataView(fw.decoded.buffer,fw.decoded.byteOffset),odv=new DataView(official.decoded.buffer,official.decoded.byteOffset);
const offset=(a:number)=>rtos.offset+a-profile.rtosBase;
const officialOffset=(a:number)=>officialRtos.offset+a-profile.rtosBase;
const word=(a:number)=>dv.getUint32(offset(a),true);
function prior(at:number){const w=word(at);if((w>>>24)!==0xea)throw Error(`Missing prior branch ${at.toString(16)}`);
 const displacement=(w<<8)>>6;const p=at+8+displacement;
 if(p<profile.rtosBase+officialRtos.size||p>=profile.rtosBase+rtos.size)throw Error('Prior outside baseline appended RTOS');return p;}
if(word(0x53000460)!==0x558043c0)throw Error('R10 zero-fill extent required');
const expected=new Map([[0x5342c964,0xe1a0c00d],[0x534322d8,0xe1a0c00d],[0x535047d4,0xe1a0c00d],
 [0x53510800,0xe2523000],[0x5342caec,0xe1a0c00d]]);
const native=[0x536af2a8,0x536af2e4,0x536afc5c,0x536bbc30,0x536bbcc0,0x536bbcac,
 0x53852338,0x5350e624,0x5350e114,0x5351eb6c,0x534324f0];
const guards:any[]=[];
for(const [at,w]of expected){if(odv.getUint32(officialOffset(at),true)!==(w>>>0))throw Error('Official entry differs');
 if(at!==0x534322d8&&at!==0x535047d4&&word(at)!==(w>>>0))throw Error('Baseline entry differs');
 guards.push({address:at,officialWord:w>>>0,baselineWord:word(at)});}
for(const at of native){const n=16,a=fw.decoded.slice(offset(at),offset(at)+n),b=official.decoded.slice(officialOffset(at),officialOffset(at)+n);
 if(a.some((v,i)=>v!==b[i]))throw Error(`Native API guard ${at.toString(16)}`);
 guards.push({address:at,bytes:Buffer.from(b).toString('hex')});}
const base=profile.rtosBase+rtos.size,priorExpose=prior(0x534322d8),priorJpeg=prior(0x535047d4);
writeFileSync(resolve(out,'baseline-rtos.bin'),fw.decoded.slice(rtos.offset,rtos.offset+rtos.size));
execFileSync('python',[resolve(root,'tools/trichrome_firmware/link.py'),'--out',resolve(out,'native'),
 '--base',`0x${base.toString(16)}`,'--prior-expose',`0x${priorExpose.toString(16)}`,'--prior-jpeg',`0x${priorJpeg.toString(16)}`],{encoding:'utf8'});
const linked=JSON.parse(readFileSync(resolve(out,'native/link.json'),'utf8')),module=new Uint8Array(readFileSync(resolve(out,'native/module.bin')));
if(linked.base!==base||await sha256Hex(module)!==linked.sha256)throw Error('Native module readback');
const record=new TextEncoder().encode('GR3-210-TRICHROME-TRIPOD-EXPERIMENTAL-HARDWARE-UNTESTED\0');
const growth=Math.ceil((module.length+record.length+4)/FRAME_SIZE)*FRAME_SIZE;
if(base+growth>0x55000000)throw Error('RTOS would overlap initialized data');
const end=rtos.offset+rtos.size,decoded=new Uint8Array(fw.decoded.length+growth);
decoded.set(fw.decoded.subarray(0,end));decoded.set(module,end);decoded.set(fw.decoded.subarray(end),end+growth);
const nd=new DataView(decoded.buffer);nd.setUint32(rtos.offset-4,rtos.size+growth,true);
const patches=[
 [0x5342c964,'tri_hook_arm','Arm only native continuous-release command'],
 [0x534322d8,'tri_hook_expose','Tag actual BeforeExpose record, then prior date/orientation hook'],
 [0x535047d4,'tri_hook_jpeg','Consume capture tag and composite, then prior JPEG modules'],
 [0x53510800,'tri_hook_override','Conservatively invalidate optional Common processing override'],
 [0x5342caec,'tri_hook_single','Reset on native single release'],
] as const;
const patchmap=patches.map(([address,symbol,reason])=>{const before=word(address),target=linked.symbols[symbol];
 const after=branchWord(address,target)>>>0;nd.setUint32(offset(address),after,true);
 return {address,offset:offset(address),before,after,target,symbol,reason};});
decoded.set(record,end+growth-record.length-4);nd.setUint32(end+growth-4,(-sum32(decoded))>>>0,true);
const ranges=[...patchmap.map(p=>({what:p.reason,offset:p.offset,length:4})),
 {what:'RTOS section length',offset:rtos.offset-4,length:4},{what:'Native module, record and checksum',offset:end,length:growth}];
const built=buildGrown(fw,decoded,[{at:end,length:growth}]);
const checks=selfCheckGrown(raw,built.out,ranges,decoded),verify=verifyContainer(built.out,decoded);
if(Object.values(checks).some(v=>!v)||Object.values(verify.checks).some(v=>!v))throw Error('Container self check failed');
const readback=new Firmware(built.out);if(await sha256Hex(readback.decoded)!==await sha256Hex(decoded))throw Error('Decoded readback mismatch');
for(const p of patchmap)if(new DataView(readback.decoded.buffer).getUint32(p.offset,true)!==p.after)throw Error('Patch readback mismatch');
if(readback.decoded.slice(end,end+module.length).some((v,i)=>v!==module[i]))throw Error('Native module readback mismatch');
writeFileSync(resolve(out,'fwdc239b.bin'),built.out);writeFileSync(resolve(out,'candidate-rtos.bin'),decoded.slice(rtos.offset,rtos.offset+rtos.size+growth));
const report={kind:'GR III2.10 experimental tripod trichrome manual-test candidate',hardwareTested:false,
 officialPath,officialSha256:await sha256Hex(original),baselinePath,baselineSha256:await sha256Hex(raw),
 filename:resolve(out,'fwdc239b.bin'),sha256:await sha256Hex(built.out),bytes:built.out.length,
 rtosBase:profile.rtosBase,previousRtosSize:rtos.size,rtosSize:rtos.size+growth,module:linked,
 control:'Continuous release arms one epoch; BeforeExpose tags first3 Common records; JPEG consumes once. Singles/reprocessing/unmatched jobs no-op/reset.',
 extraFilmMtfEnabled:false,handheldAlignmentEnabled:false,priorExpose,priorJpeg,reservedAnchor:0x5580438c,
 patchmap,guards,checks,verify:verify.checks,
 limits:'Actual event ordering/Common identity, native latency, heap availability and camera output require manual hardware testing. No camera was flashed.'};
writeFileSync(resolve(out,'build-report.json'),JSON.stringify(report,null,2)+'\n');
writeFileSync(resolve(out,'patchmap.json'),JSON.stringify({patchmap,guards,ranges},null,2)+'\n');
console.log(JSON.stringify({filename:report.filename,sha256:report.sha256,bytes:report.bytes,moduleBytes:module.length,checks},null,2));
