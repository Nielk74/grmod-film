// Actual GR Mod film targets -> Engine fit -> firmware-quantized software reference.
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { Engine } from '../../core/src/app/engine';
import { LOOKS, cubeText, bands, saturationByTone } from '../../core/src/filmpack/looks';
import type { Look, RGB, Op } from '../../core/src/filmpack/looks';
import { GR3X_CAMERA } from '../../core/src/color/gr3x-camera';
import type { PresetResult } from '../../core/src/app/engine';

function inverse(a: number[]): number[] {
  const [a0,b,c,d,e,f,g,h,i] = a;
  const det=a0*(e*i-f*h)-b*(d*i-f*g)+c*(d*h-e*g);
  if (Math.abs(det)<1e-12) throw new Error('Singular Standard matrix');
  return [(e*i-f*h)/det,(c*h-b*i)/det,(b*f-c*e)/det,(f*g-d*i)/det,(a0*i-c*g)/det,(c*d-a0*f)/det,(d*h-e*g)/det,(b*g-a0*h)/det,(a0*e-b*d)/det];
}

function product(a: number[], b: number[]): number[] {
  return Array.from({length:9},(_,j)=>[0,1,2].reduce((s,k)=>s+a[Math.floor(j/3)*3+k]*b[k*3+j%3],0));
}

/** Declared reference of stored coefficients, not complete ISP emulation. */
function nativeGrid(fit: PresetResult, standard: number[], grid: Float64Array): Float32Array {
  const matrix=product(Array.from(fit.matrixQ13,v=>v/8192),inverse(standard.map(v=>v/8192)));
  const post=fit.postQ9 ? Array.from(fit.postQ9,v=>v/512) : [1,0,0,0,1,0,0,0,1];
  const out=new Float32Array(grid.length), lin=[0,0,0], curved=[0,0,0];
  for(let p=0;p<grid.length;p+=3){
    for(let c=0;c<3;c++) lin[c]=GR3X_CAMERA.Sinv(grid[p+c]);
    for(let c=0;c<3;c++){
      const l=matrix[c*3]*lin[0]+matrix[c*3+1]*lin[1]+matrix[c*3+2]*lin[2];
      const display=GR3X_CAMERA.S(Math.max(0,Math.min(1,l)));
      const position=Math.max(0,Math.min(255,display*16383/64));
      const low=Math.min(254,Math.floor(position)), t=position-low;
      curved[c]=(fit.curves[c][low]*(1-t)+fit.curves[c][low+1]*t)/16383;
    }
    for(let c=0;c<3;c++) out[p+c]=Math.max(0,Math.min(1,post[c*3]*curved[0]+post[c*3+1]*curved[1]+post[c*3+2]*curved[2]));
  }
  return out;
}

function change(kind:string,strength:number):Op {
  if(kind==='combined') {
    const hue=change('hue',strength), density=change('density',.6*strength);
    return c=>density(hue(c));
  }
  if(kind==='hue') return bands(
    {hue:140,width:65,shift:-30*strength,sat:1+0.12*strength,light:Math.max(.5,1-.06*strength)},
    {hue:255,width:65,shift:-30*strength,sat:1+0.06*strength,light:Math.max(.5,1-.10*strength)},
    {hue:25,width:28,shift:17*strength,sat:1+0.06*strength});
  const density=bands(
    {hue:25,width:38,light:Math.max(.45,1-.17*strength),sat:1+.16*strength},
    {hue:140,width:55,light:Math.max(.45,1-.20*strength),sat:1+.16*strength},
    {hue:255,width:60,light:Math.max(.45,1-.20*strength),sat:1+.10*strength});
  const tone=saturationByTone(1+.06*strength,1,Math.max(.3,1-.12*strength));
  return c=>tone(density(c));
}

const [firmware,outDir]=process.argv.slice(2).filter(a=>a!=='--');
if(!firmware||!outDir) throw new Error('Usage: film_pipeline_v2.ts OFFICIAL.bin OUT-DIR');
mkdirSync(outDir,{recursive:true});
const engine=await Engine.open(new Uint8Array(readFileSync(firmware)));
const size=33, grid=new Float64Array(size**3*3);
let at=0;
for(let r=0;r<size;r++)for(let g=0;g<size;g++)for(let b=0;b<size;b++){
  grid[at++]=r/(size-1);grid[at++]=g/(size-1);grid[at++]=b/(size-1);
}
const combinedOnly=process.argv.includes('--combined-only');
const reports:object[]=combinedOnly ? JSON.parse(readFileSync(join(outDir,'models.json'),'utf8')).models.filter((m:{kind:string})=>m.kind!=='combined') : [];
for(const name of ['Classic Chrome','Astia','Classic Neg']){
  const base=LOOKS.find(l=>l.name===name)!;
  const specs=combinedOnly ? [{kind:'combined',strength:1}] : [{kind:'base',strength:0},...['hue','density'].flatMap(kind=>[.5,1,1.75,2.5].map(strength=>({kind,strength}))),{kind:'combined',strength:1}];
  for(const spec of specs){
    const op=spec.kind==='base'?base.op:((adjust:Op):Op=>c=>adjust(base.op(c)))(change(spec.kind,spec.strength));
    const id=name.toLowerCase().replaceAll(' ','-')+'-'+spec.kind+'-'+Math.round(spec.strength*100);
    const look:Look={...base,name:id,op};
    const cube=cubeText(look,33), fit=engine.convertPreset('cube',cube,undefined,{post:true});
    const target=new Float32Array(grid.length);
    for(let p=0;p<grid.length;p+=3) target.set(op([grid[p],grid[p+1],grid[p+2]] as RGB),p);
    const quantized=nativeGrid(fit,engine.info.standardMatrixQ13,grid);
    writeFileSync(join(outDir,id+'.cube'),cube,{encoding:'utf8'});
    writeFileSync(join(outDir,id+'-target.f32'),new Uint8Array(target.buffer));
    writeFileSync(join(outDir,id+'-native.f32'),new Uint8Array(quantized.buffer));
    const report={id,film:name,...spec,grid_size:size,grid_order:'[r,g,b,channel], b-fastest, little-endian float32',
      target:id+'-target.f32',native:id+'-native.f32',cube:id+'.cube',
      fit_mean_de00:fit.meanDE2000,fit_p95_de00:fit.p95DE2000,
      parameters:{M1:fit.params.M1,ck:fit.params.ck.map(c=>Array.from(c)),P2:fit.params.P2},
      firmware_coefficients:{matrixQ13:Array.from(fit.matrixQ13),curves:fit.curves.map(c=>Array.from(c)),postQ9:fit.postQ9?Array.from(fit.postQ9):null}};
    reports.push(report);
    console.log(`${id}: fit mean dE00 ${fit.meanDE2000.toFixed(2)}`);
  }
}
writeFileSync(join(outDir,'models.json'),JSON.stringify({firmware:{path:firmware,sha256:engine.info.sha256,version:engine.info.version,standardMatrixQ13:engine.info.standardMatrixQ13},models:reports,
  limitations:['Input must be camera Standard for the relative look model. User R0000022/23 are documented Standard photographs.',
    'The grids evaluate actual Engine fit and stored quantized coefficients, with Standard matrix read from official firmware. Full ISP arithmetic and physical camera behaviour remain unverified.',
    'Hue variants currently use the supported matrix/curve path. They do not pretend that GR IV native hue sectors have been ported to GR III.']},null,2),{encoding:'utf8'});
