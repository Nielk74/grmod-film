import {chromium} from 'playwright';
import sharp from 'sharp';
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {KEY_TIMES} from './timing.mjs';
import {ENTER_MS,ACT_DURATION_MS,DURATION_MS,SEQUENCE_IDS} from './sequence.mjs';
const here=path.dirname(fileURLToPath(import.meta.url)),out=path.join(here,'out');
await mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true}),errors=[];
const page=await browser.newPage({viewport:{width:1440,height:1100}});
page.on('pageerror',e=>errors.push(e.message));
const url=process.env.SHOT_LAB_URL||'http://127.0.0.1:5186';
const hash=b=>createHash('sha256').update(b).digest('hex');
try{
  const report={variants:[],checks:{}},coreFrames=[],sheet=[];
  for(const [row,id] of SEQUENCE_IDS.entries()){
    await page.goto(`${url}/?export=${id}`);await page.waitForFunction(()=>!!window.seekShot);
    const core=[];
    for(const start of KEY_TIMES){
      await page.evaluate(ms=>window.seekShot(ms),ENTER_MS+start+34);
      core.push(hash(await page.screenshot({omitBackground:true,clip:{x:0,y:0,width:240,height:176}})));
    }
    assert.equal(new Set(core).size,6);
    if(coreFrames.length)assert.deepEqual(core,coreFrames);else coreFrames.push(...core);
    const motion=[];
    for(const ms of [100,250,450,650,850,1050,1250,6450,6650,6850,7050,7250,7450]){
      await page.evaluate(ms=>window.seekShot(ms),ms);
      motion.push(hash(await page.screenshot({omitBackground:true,clip:{x:0,y:0,width:240,height:176}})));
    }
    assert.ok(new Set(motion).size>=11,`${id}: visible entry and exit choreography`);
    for(const [ms,expected] of [[400,'left'],[7000,id==='portal'?'right':'left']]){
      await page.evaluate(ms=>window.seekShot(ms),ms);
      assert.equal(await page.locator('.sequence-tile').getAttribute('data-facing'),expected,`${id} facing at ${ms}`);
    }
    await page.evaluate(()=>window.seekShot(1884));
    await page.screenshot({path:path.join(out,`blink-fixed-${id}-native.png`),omitBackground:true,clip:{x:0,y:0,width:240,height:176}});
    await page.evaluate(ms=>window.seekShot(ms),DURATION_MS);
    const rgba=await sharp(await page.screenshot({omitBackground:true,clip:{x:0,y:0,width:240,height:176}})).ensureAlpha().raw().toBuffer();
    assert.ok(rgba.every((v,i)=>i%4!==3||v===0));
    report.variants.push({id,corePoses:6,distinctActionSamples:new Set(motion).size,clearedAtMs:DURATION_MS});
    await page.goto(`${url}/?export=${id}&large=1`);await page.waitForFunction(()=>!!window.seekShot);
    if(id==='portal'){
      await page.evaluate(()=>window.seekShot(1884));
      await page.screenshot({path:path.join(out,'blink-fixed-large.png'),omitBackground:true,clip:{x:0,y:0,width:360,height:280}});
    }
    for(const [col,ms] of [250,500,750,950,1250,6500,6750,7000,7250,7500].entries()){
      await page.evaluate(ms=>window.seekShot(ms),ms);
      if(id==='rocket'&&ms===7000){
        const flames=page.locator('path[data-effect="flame"]');
        assert.equal(await flames.count(),2,'both rocket sockets must render exhaust');
        assert.ok(await flames.evaluateAll(paths=>paths.every(p=>p.getBoundingClientRect().bottom<=p.ownerSVGElement.getBoundingClientRect().bottom)), 'launch exhaust must fit the large stage');
      }
      const png=await page.screenshot({omitBackground:true,clip:{x:0,y:0,width:360,height:280}});
      sheet.push({input:await sharp(png).resize(240,187).png().toBuffer(),left:(col%5)*240,top:row*374+Math.floor(col/5)*187});
    }
  }
  await sharp({create:{width:1200,height:1122,channels:4,background:'#e8e7dd'}}).composite(sheet).png().toFile(path.join(out,'entrance-exit-filmstrip.png'));
  await page.goto(url);await page.waitForFunction(()=>!!window.seekShot);
  assert.equal(await page.locator('.sequence-controls').evaluate(e=>getComputedStyle(e).display),'flex');
  await page.evaluate(()=>window.seekShot(500));await page.screenshot({path:path.join(out,'comparison-desktop.png'),fullPage:true});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  for(const width of [1440,790,768,390]){
    await page.setViewportSize({width,height:1100});
    assert.ok(await page.locator('.character-preview').evaluateAll(stages=>stages.every(stage=>{
      const child=stage.querySelector('.character-large').getBoundingClientRect(),box=stage.getBoundingClientRect();
      return child.height<=box.height+.5&&child.width<=box.width+.5;
    })),`${width}px: preview must fit its stage`);
  }
  await page.setViewportSize({width:390,height:844});await page.evaluate(()=>window.seekShot(5000));
  await page.screenshot({path:path.join(out,'comparison-mobile.png'),fullPage:true});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  report.checks.desktopAndMobileNoOverflow=true;
  await page.emulateMedia({reducedMotion:'reduce'});await page.reload();await page.waitForFunction(()=>!!window.seekShot);
  await page.evaluate(ms=>window.seekShot(ms),DURATION_MS);
  assert.equal(await page.locator('article.selected .overlay-slot svg g').count(),0);report.checks.reducedMotionClears=true;
  await page.emulateMedia({reducedMotion:'no-preference'});await page.reload();await page.waitForFunction(()=>!!window.seekShot);
  await page.getByRole('button',{name:'Play Rocket Delivery',exact:true}).click();
  await page.waitForTimeout(550);const first=await page.evaluate(()=>window.shotState.ms);assert.ok(first>0);
  assert.equal(await page.getByRole('button',{name:'Play Rocket Delivery',exact:true}).getAttribute('aria-pressed'),'true');
  await page.getByRole('button',{name:'Take a picture'}).click();assert.ok((await page.evaluate(()=>window.shotState.ms))<first);
  await page.getByRole('button',{name:'Pause animation'}).click();const paused=await page.evaluate(()=>window.shotState.ms);
  await page.waitForTimeout(100);assert.equal(await page.evaluate(()=>window.shotState.ms),paused);
  await page.getByRole('button',{name:'Replay exit'}).click();
  assert.ok((await page.evaluate(()=>window.shotState.ms))>=ENTER_MS+ACT_DURATION_MS);
  await page.getByRole('button',{name:'Pause animation'}).click();report.checks.repeatPauseExitReplay=true;
  // Observe actual live sources; a label change cannot establish resumed audio.
  await page.evaluate(()=>{
    window.shotAudioStarts=0;
    for(const method of ['createOscillator','createBufferSource']){
      const create=AudioContext.prototype[method];
      AudioContext.prototype[method]=function(...args){
        const source=create.apply(this,args),start=source.start;
        source.start=function(...offsets){window.shotAudioStarts++;return start.apply(this,offsets);};
        return source;
      };
    }
  });
  await page.getByRole('button',{name:'Play Rocket Delivery',exact:true}).click();
  await page.waitForFunction(()=>window.shotAudioStarts>0);
  await page.waitForTimeout(350);
  await page.getByRole('button',{name:'Sound 100%',exact:true}).click();
  const mutedSources=await page.evaluate(()=>window.shotAudioStarts);
  await page.waitForTimeout(100);
  assert.equal(await page.evaluate(()=>window.shotAudioStarts),mutedSources,'muting must not schedule more voices');
  await page.getByRole('button',{name:'Sound off',exact:true}).click();
  await page.waitForFunction(previous=>window.shotAudioStarts>previous,mutedSources,{timeout:1500});
  assert.equal(await page.evaluate(()=>window.shotState.variant),'rocket','unmute must resume the selected score');
  assert.ok(await page.getByRole('button',{name:'Sound 100%',exact:true}).isVisible());
  await page.getByRole('button',{name:'Pause animation'}).click();
  await page.getByRole('button',{name:'Sound 100%',exact:true}).click();
  const pausedSources=await page.evaluate(()=>window.shotAudioStarts);
  await page.getByRole('button',{name:'Sound off',exact:true}).click();
  await page.waitForTimeout(100);
  assert.equal(await page.evaluate(()=>window.shotAudioStarts),pausedSources,'unmuting paused playback must stay silent');
  report.checks.fullVolumeControl=true;
  report.checks.unmuteResumesActiveScoreAndKeepsPausedSilent=true;
  const shots=[];
  for(let i=0;i<9;i++){
    await page.getByRole('button',{name:'Take a picture'}).click();
    shots.push(await page.evaluate(()=>window.shotState.variant));
    assert.equal(await page.locator('article.selected').count(),1);
    assert.equal(await page.locator('article:not(.selected) .overlay-slot .sequence-tile').evaluateAll(nodes=>nodes.every(n=>n.getAttribute('data-phase')==='act')),true);
  }
  // A random shutter already occurred above. Each consecutive full set still
  // contains every option; align to the following shuffle-bag boundary.
  for(let i=2;i+3<=shots.length;i+=3)assert.equal(new Set(shots.slice(i,i+3)).size,3);
  for(let i=1;i<shots.length;i++)assert.notEqual(shots[i],shots[i-1]);
  report.checks.randomShotsWithoutImmediateRepeats=shots;
  await page.getByRole('button',{name:'Pause animation'}).click();
  report.audio=[];
  for(const id of SEQUENCE_IDS){
    const audio=await page.evaluate(async id=>{
      const {renderSound}=await import('/src/sound.ts');const a=await renderSound(id);
      const data=a.getChannelData(0),regions=[[0,1.4],[1.4,6.4],[6.4,7.6]];
      const energy=regions.map(([start,end])=>{let sum=0;for(let i=Math.floor(start*a.sampleRate);i<Math.min(data.length,end*a.sampleRate);i++)sum+=data[i]*data[i];return Math.sqrt(sum/((end-start)*a.sampleRate));});
      let peak=0;for(const v of data)peak=Math.max(peak,Math.abs(v));
      return{duration:a.duration,peak,energy,channels:a.numberOfChannels};
    },id);
    assert.ok(audio.duration>=7.6&&audio.duration<8.2);assert.ok(audio.peak>.1&&audio.peak<=1);
    assert.ok(audio.energy.every(v=>v>.005),`${id} audible in entry, performance and exit`);
    report.audio.push({id,...audio});
  }
  assert.deepEqual(errors,[]);await writeFile(path.join(out,'browser-verification.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report,null,2));
}finally{await browser.close();}
