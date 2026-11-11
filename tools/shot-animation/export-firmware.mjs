// SPDX-License-Identifier: GPL-2.0-only
import {chromium} from 'playwright';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {encodeTerminalAsset,readTerminalAsset,motionSample} from './firmware-assets.mjs';
const root=new URL('./',import.meta.url),file=s=>fileURLToPath(new URL(s,root));
await mkdir(file('out/firmware'),{recursive:true});
const palette=JSON.parse(await readFile(file('out/terminal-pose-bank.palette.json'),'utf8'));
const indices=new Uint8Array(await readFile(file('out/terminal-pose-bank.indices')));
const browser=await chromium.launch({headless:true}),page=await browser.newPage({viewport:{width:240,height:176}});
const samples=[],url=process.env.SHOT_LAB_URL||'http://127.0.0.1:5186';
try{
  for(const id of ['dash','portal','rocket']){
    await page.goto(`${url}/?export=${id}`);await page.waitForFunction(()=>!!window.seekShot);
    const track=[];
    for(let frame=0;frame<228;frame++){
      // Use a tiny positive epsilon to avoid floating-point floor landing in the preceding frame.
      const ms=frame*1000/30+.00001;
      await page.evaluate(ms=>window.seekShot(ms),ms);
      const vectors=await page.evaluate(async()=>{
        const {captureVectorCommands}=await import('/vector-commands.mjs');
        return captureVectorCommands(document.querySelector('.sequence-tile'));
      });
      track.push({...motionSample(frame*1000/30,id),...vectors});
    }
    samples.push(track);console.log(`${id}:228 fixed-point samples, geometric effects extracted`);
    for(const ms of [400,900,1900,4400,6750,7000]){
      await page.evaluate(ms=>window.seekShot(ms+.00001),ms);
      await page.screenshot({path:file(`out/firmware/browser-${id}-${ms}.png`),omitBackground:true});
    }
  }
}finally{await browser.close();}
const asset=encodeTerminalAsset({palette,indices,samples}),report=readTerminalAsset(asset);
await writeFile(file('out/firmware/terminal-native.trm'),asset);
await writeFile(file('out/firmware/asset-report.json'),JSON.stringify({...report,palette:report.palette,indices:undefined,
  rasterPoseBytes:indices.length,vectorRasterFrames:0,rgbaFrameBytes:240*176*4,hardwareTested:false},null,2)+'\n');
console.log(JSON.stringify({...report,palette:undefined,indices:undefined},null,2));
