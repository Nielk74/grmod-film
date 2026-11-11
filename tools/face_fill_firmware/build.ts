// SPDX-License-Identifier: GPL-2.0-only
import { readFileSync,writeFileSync,mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { installFace } from './install';
const root=resolve(import.meta.dirname,'../..'),out=resolve(root,'scratch/face-fill-firmware');
const args=process.argv.slice(2).filter(a=>a!=='--');
if(args.length!==1)throw new Error('Usage: vite-node tools/face_fill_firmware/build.ts -- PRISTINE_GR_III_210');
const source=Buffer.from(readFileSync(resolve(root,'tools/face_fill_firmware/module.c'),'utf8').replace(/\r\n/g,'\n'),'utf8');
const result=installFace(readFileSync(resolve(out,'baseline-no-extra-mtf/fwdc239b.bin')),readFileSync(args[0]),
  JSON.parse(readFileSync(resolve(root,'tools/face_fill_firmware/module-code.json'),'utf8')),source);
mkdirSync(out,{recursive:true});writeFileSync(resolve(out,'fwdc239b.bin'),result.bytes);
writeFileSync(resolve(out,'candidate-rtos.bin'),result.rtos);
writeFileSync(resolve(out,'build-report.json'),JSON.stringify(result.report,null,2)+'\n','utf8');
console.log(JSON.stringify(result.report,null,2));
