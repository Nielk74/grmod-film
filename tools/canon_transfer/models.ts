// SPDX-License-Identifier: GPL-2.0-only
// Review prototype: Canon-authored colour targets fitted to the existing GR III format.
// Run from the repository root with vite-node --script tools/canon_transfer/models.ts OUT.
import { readFileSync, writeFileSync, mkdirSync, copyFileSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { createHash } from 'node:crypto';
import { LOOKS, cubeText } from '../../core/src/filmpack/looks';
import { filmResponse } from '../../examples/gr3x/film-pack-v3/response';
import { convertGr3xCube } from '../../core/src/color/gr3x-import';
import { quantizeSlot } from '../../core/src/color/camera';
import { GR3X_CAMERA } from '../../core/src/color/gr3x-camera';
import { applyCube, parseCube } from '../../core/src/color/cube';
import { syntheticSamples } from '../../core/src/color/convert';
import { deltaE2000Lab, lab, mean, percentile } from '../../core/src/color/math';
import { GRAIN_LUMA_TILES, GRAIN_COLOUR_TILES, GRAIN_TONES } from '../../core/src/color/grain-tables';
import { grainRgb } from '../../core/src/color/grain';

const root = resolve('.'), out = resolve(process.argv[2] ?? 'scratch/canon-transfer-2026-11-04');
mkdirSync(join(out, 'models'), { recursive: true });
const sha = (b: Uint8Array | string) => createHash('sha256').update(b).digest('hex');
const identity = [8192,0,0,0,8192,0,0,0,8192];
const grid = new Float64Array(33**3*3);
let at=0;
for(let r=0;r<33;r++)for(let g=0;g<33;g++)for(let b=0;b<33;b++) grid.set([r/32,g/32,b/32],at),at+=3;
const validation=syntheticSamples(18000,20261104,1);
const clamp=(x:number)=>Math.max(0,Math.min(1,x));

function evaluate(q:ReturnType<typeof quantizeSlot>, rgb:Float64Array):Float32Array {
  const result=new Float32Array(rgb.length);
  for(let i=0;i<rgb.length;i+=3) {
    const l=[0,1,2].map(c=>GR3X_CAMERA.Sinv(rgb[i+c])), curves:number[]=[];
    for(let c=0;c<3;c++) {
      const d=GR3X_CAMERA.S(clamp((q.matrixQ13[c*3]*l[0]+q.matrixQ13[c*3+1]*l[1]+q.matrixQ13[c*3+2]*l[2])/8192));
      const x=Math.min(255,Math.max(0,d*16383/64)), j=Math.min(254,Math.floor(x)), f=x-j;
      curves.push((q.curves[c][j]+f*(q.curves[c][j+1]-q.curves[c][j]))/16383);
    }
    for(let c=0;c<3;c++) result[i+c]=clamp(q.postQ9 ? (q.postQ9[c*3]*curves[0]+q.postQ9[c*3+1]*curves[1]+q.postQ9[c*3+2]*curves[2])/512 : curves[c]);
  }
  return result;
}
const report=[];
for(const [key,name,size] of [['portra400','Portra 400','small'],['gold200','Gold 200','small'],['cinestill800t','CineStill 800T','large']] as const) {
  const base=LOOKS.find(x=>x.name===name)!;
  // Same colour settings as examples/gr3x/film-pack-v3/build.ts, current committed v3.
  const current=cubeText({...base,op:filmResponse(base.op,name==='Gold 200'?1:1.5,name==='Gold 200'?0:0.12,0.03)});
  const source=join(root,'scratch/canon-feasibility-2026-11-04',key==='portra400'?'portra400-shadow-corrected.cube':`${key}.cube`);
  const candidate=readFileSync(source,'utf8');
  const modelReports:any={key,name,grain:{amount:2,size},sourceCubeSha256:sha(candidate)};
  for(const [variant,text] of [['current',current],['candidate',candidate]] as const) {
    const cube=parseCube(text), fit=convertGr3xCube(text,{post:true,endGreyWeight:24});
    const q=quantizeSlot(fit.params,identity), evaluated=evaluate(q,grid);
    const path=`models/${key}-${variant}.f32`;
    writeFileSync(join(out,path),new Uint8Array(evaluated.buffer));
    writeFileSync(join(out,'models',`${key}-${variant}.cube`),text,'utf8');
    const errors=deltaE2000Lab(lab(Float64Array.from(evaluate(q,validation))),lab(applyCube(cube,validation)));
    modelReports[variant]={grid:path,gridSha256:sha(new Uint8Array(evaluated.buffer)),meanDE2000:mean(errors),p95DE2000:percentile(errors,95),
      params:{M1:fit.params.M1,ck:fit.params.ck.map(c=>Array.from(c)),P2:fit.params.P2},
      relativeQuantized:{matrixQ13:Array.from(q.matrixQ13),postQ9:Array.from(q.postQ9!),curves:q.curves.map(c=>Array.from(c))}};
    if(variant==='candidate') {
      const target=Float32Array.from(applyCube(cube,grid));
      writeFileSync(join(out,'models',`${key}-target.f32`),new Uint8Array(target.buffer));
    }
  }
  report.push(modelReports);
  console.log(`${name}: current ${modelReports.current.meanDE2000.toFixed(2)}, candidate ${modelReports.candidate.meanDE2000.toFixed(2)} mean fit DE00`);
}

const grain=Buffer.concat([0,1].flatMap(i=>[Buffer.from(GRAIN_LUMA_TILES[i]),Buffer.from(GRAIN_COLOUR_TILES[i]),Buffer.from(GRAIN_TONES[i])]));
writeFileSync(join(out,'models','grain-current.bin'),grain);
const canonPath=resolve(root,'../canon/ml-dev/films/eos_r/grain.bin');
const canon=readFileSync(canonPath), candidate=Buffer.from(canon), set=2*128*128+256, stats=[];
if(canon.length!==2*set) throw new Error('Unexpected Canon grain format');
for(let s=0;s<2;s++) {
  const start=s*set, signed=(i:number)=>(canon[i]<<24)>>24;
  const values=Array.from({length:16384},(_,i)=>signed(start+i));
  const avg=values.reduce((a,b)=>a+b,0)/values.length;
  const std=Math.sqrt(values.reduce((a,b)=>a+(b-avg)**2,0)/values.length), factor=32/std;
  // Canon reduces Cb/Cr to 90/256 of luma's gain in fos_dev.c. Fold it into
  // the tiles for GR Mod's existing module. Match luma RMS to compare texture fairly.
  for(let i=0;i<32768;i++) {
    const v=Math.max(-127,Math.min(127,Math.round(signed(start+i)*factor*(i>=16384?90/256:1))));
    candidate[start+i]=v&255;
  }
  stats.push({size:s===0?'small':'large',originalCanonLumaStd:std,lumaNormalization:factor,chromaMultiplier:90/256});
}
writeFileSync(join(out,'models','grain-candidate.bin'),candidate);
// Fixed vectors allow the NumPy renderer to check its implementation against
// the actual current TypeScript grain implementation for both sets of tiles.
const w=144,h=96, test=Uint8Array.from({length:w*h*3},(_,i)=>(i*37+(i>>>7)*13)&255);
writeFileSync(join(out,'models','grain-test-input.rgb'),test);
for(const [kind,bytes] of [['current',grain],['candidate',candidate]] as const) {
  for(let s=0;s<2;s++) {
    GRAIN_LUMA_TILES[s].set(bytes.subarray(s*set,s*set+16384));
    GRAIN_COLOUR_TILES[s].set(bytes.subarray(s*set+16384,s*set+32768));
    GRAIN_TONES[s].set(bytes.subarray(s*set+32768,(s+1)*set));
  }
  for(const setting of [1,2,3,5,6,7]) {
    const rgb=test.slice();grainRgb(rgb,w,h,setting,3,w);
    writeFileSync(join(out,'models',`grain-test-${kind}-${setting}.rgb`),rgb);
  }
}
// Module globals are process-local; no repository source or shipped table is written.
const metadata={schema:1,grid:33,order:'[r,g,b,channel], blue fastest, little-endian float32',films:report,
  baseline:'Current committed film-pack-v3 colour recipe, post=true, endGreyWeight=24; Medium grain for the three focus films.',
  grain:{source:canonPath,sourceSha256:sha(canon),normalization:'Candidate luma RMS matched to 32; Canon chroma gain folded into tiles; same Ricoh amount and scale',stats},
  limitations:['Software reference of stored Q13/Q9 matrices and 256-entry curves, using identity Standard normalization; not actual firmware ISP arithmetic.',
    '33-cube interpolation approximates those reference equations between grid vertices.',
    'Halation, extra softness and denoising are held off in all variants to isolate colour and grain.',
    'The unfitted target is an offline comparison and is not the image the matrix/curve camera fit will produce.']};
writeFileSync(join(out,'models.json'),JSON.stringify(metadata,null,2)+'\n','utf8');
copyFileSync(resolve(root,'tools/canon_transfer/viewer.html'),join(out,'index.html'));
console.log(out);
