import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
import {createServer as createViteServer} from 'vite';
import * as sound from '../src/sound.ts';

async function scoreModule(){
  try{return await import('../sfx.mjs');}
  catch(error){if(error.code!=='ERR_MODULE_NOT_FOUND')throw error;assert.fail('new sequences need an authored SFX score');}
}

test('each score has bounded entrance, unchanged Pocket Lab core, and distinct exit cues',async()=>{
  const {scoreFor}=await scoreModule();
  const entrances=[],exits=[];
  for(const id of ['dash','portal','rocket']){
    const cues=scoreFor(id);
    assert.ok(cues.length>12);
    assert.ok(cues.every(cue=>Number.isFinite(cue.at)&&cue.at>=0&&cue.duration>0&&cue.at+cue.duration<=7.600001),'no sound can outlive the visible sequence');
    const core=cues.filter(cue=>cue.phase==='core');
    assert.deepEqual(core.map(cue=>Math.round(cue.at*1000)),[1650,2600,3000,3400,3800,4350,4480,4640]);
    assert.deepEqual(core.map(cue=>cue.frequency),[330,165,196,220,262,523,659,784]);
    const entry=cues.filter(cue=>cue.phase==='entry'),exit=cues.filter(cue=>cue.phase==='exit');
    assert.ok(entry.length>=3&&exit.length>=3);
    assert.ok(entry.every(cue=>cue.at<1.4));
    assert.ok(exit.every(cue=>cue.at>=6.4));
    entrances.push(JSON.stringify(entry));exits.push(JSON.stringify(exit));
  }
  assert.equal(new Set(entrances).size,3);
  assert.equal(new Set(exits).size,3);
});

test('offline synthesis produces deterministic stereo audio with headroom and audible transitions',{timeout:45000},async t=>{
  assert.equal(typeof sound.renderSound,'function');
  const vite=await createViteServer({root:fileURLToPath(new URL('..',import.meta.url)),server:{middlewareMode:true},appType:'custom',logLevel:'silent'});
  t.after(()=>vite.close());
  const server=createServer((request,response)=>{
    const name=request.url?.split('?')[0];
    if(name==='/'){response.setHeader('Content-Type','text/html');response.end('<!doctype html><title>Offline audio verification</title>');return;}
    vite.middlewares(request,response,()=>{response.writeHead(404);response.end();});
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  t.after(()=>new Promise(resolve=>server.close(resolve)));
  const browser=await chromium.launch({headless:true});
  t.after(()=>browser.close());
  const page=await browser.newPage();
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  const report=await page.evaluate(async()=>{
    const {renderSound}=await import('/src/sound.ts');
    const results=[];
    for(const id of ['dash','portal','rocket']){
      const first=await renderSound(id),second=await renderSound(id);
      let peak=0,energy=0,difference=0,differenceAt=-1,finite=true,entryPeak=0,exitPeak=0,stereoDifference=0,onset=-1;
      for(let channel=0;channel<first.numberOfChannels;channel++){
        const data=first.getChannelData(channel),repeat=second.getChannelData(channel);
        for(let index=0;index<data.length;index++){
          const value=data[index],absolute=Math.abs(value),at=index/first.sampleRate;
          peak=Math.max(peak,absolute);energy+=value*value;finite&&=Number.isFinite(value);
          const delta=Math.abs(value-repeat[index]);
          if(delta>difference){difference=delta;differenceAt=at;}
          if(at<1.4)entryPeak=Math.max(entryPeak,absolute);
          if(at>=6.4)exitPeak=Math.max(exitPeak,absolute);
          if(channel===0&&onset<0&&absolute>0.00001)onset=at;
          if(channel===1)stereoDifference=Math.max(stereoDifference,Math.abs(value-first.getChannelData(0)[index]));
        }
      }
      results.push({id,length:first.length,sampleRate:first.sampleRate,channels:first.numberOfChannels,peak,rms:Math.sqrt(energy/(first.length*first.numberOfChannels)),difference,differenceAt,finite,entryPeak,exitPeak,stereoDifference,onset});
    }
    return results;
  });
  console.log('Offline SFX levels',JSON.stringify(report));
  const earliest={dash:.12,portal:.08,rocket:.15};
  for(const result of report){
    assert.equal(result.length,364800,result.id);
    assert.equal(result.sampleRate,48000);
    assert.equal(result.channels,2);
    assert.equal(result.finite,true);
    // Parallel WebAudio mixing accumulates tiny Float32 rounding differences.
    // This limit still catches random noise or prematurely truncated tails;
    // a separate playback test compares generated noise buffers bit for bit.
    assert.ok(result.difference<=1e-6,'synthesized layers must reproduce within float mixing precision');
    assert.ok(result.peak<.99&&result.peak>.2,`${result.id} peak ${result.peak} must be audible with headroom`);
    assert.ok(result.rms>.02,`${result.id} is too quiet`);
    assert.ok(result.entryPeak>.1&&result.exitPeak>.1,`${result.id} needs audible entrance and exit`);
    assert.ok(result.stereoDifference>.01,`${result.id} needs stereo motion`);
    assert.ok(result.onset>=earliest[result.id]&&result.onset<earliest[result.id]+.035,`${result.id} onset ${result.onset}`);
  }
});
