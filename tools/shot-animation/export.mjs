import {chromium} from 'playwright';
import sharp from 'sharp';
import {mkdir,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import path from 'node:path';
import assert from 'node:assert/strict';
import {encodeAnimation,decodeAnimation} from './codec.mjs';

const here=path.dirname(fileURLToPath(import.meta.url));
const out=path.join(here,'out');
const url=process.env.SHOT_LAB_URL || 'http://127.0.0.1:5186';
await mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true});
const errors=[];
const page=await browser.newPage({viewport:{width:1440,height:1100},deviceScaleFactor:1});
page.on('pageerror',e=>errors.push(e.message));
const rows=[],report={durationMs:5000,fps:20,frames:100,width:240,height:176,experiments:[],checks:{}};
const stages=[350,1000,1750,2500,3300,4200];
try {
  for(const id of ['film','robot','focus']) {
    const dir=path.join(out,id);await mkdir(dir,{recursive:true});
    await page.goto(`${url}/?export=${id}`);
    await page.waitForFunction(()=>!!window.seekShot);
    const frames=[];let representative;
    for(let frame=0;frame<100;frame++) {
      await page.evaluate(ms=>window.seekShot(ms),frame*50);
      const png=await page.screenshot({omitBackground:true,clip:{x:0,y:0,width:240,height:176}});
      await writeFile(path.join(dir,`${String(frame).padStart(3,'0')}.png`),png);
      const rgba=await sharp(png).ensureAlpha().raw().toBuffer();frames.push(rgba);
      if(frame===66)representative=png;
    }
    const asset=encodeAnimation({width:240,height:176,fps:20,frames});
    const decoded=decodeAnimation(asset);
    assert.equal(decoded.frames.length,100);
    await writeFile(path.join(out,`${id}.gsa`),asset);
    await writeFile(path.join(out,`${id}-poster.png`),representative);
    const final=await sharp(decoded.frames[66],{raw:{width:240,height:176,channels:4}}).png().toBuffer();
    await writeFile(path.join(out,`${id}-camera-pixels.png`),final);
    // Check a seek backwards followed by the same timestamp is deterministic.
    await page.evaluate(()=>window.seekShot(400));await page.evaluate(()=>window.seekShot(3300));
    const repeated=await page.screenshot({omitBackground:true,clip:{x:0,y:0,width:240,height:176}});
    assert.ok(repeated.equals(representative),`${id}: non-deterministic seek`);
    await page.evaluate(()=>window.seekShot(5000));
    const ending=await sharp(await page.screenshot({omitBackground:true,clip:{x:0,y:0,width:240,height:176}})).ensureAlpha().raw().toBuffer();
    assert.ok(ending.every((n,i)=>i%4!==3||n===0),`${id}: overlay persists after 5 seconds`);
    const tiles=[];
    for(const ms of stages){tiles.push({input:path.join(dir,`${String(ms/50).padStart(3,'0')}.png`),left:stages.indexOf(ms)*240,top:0});}
    rows.push(await sharp({create:{width:1440,height:176,channels:4,background:'#eae8de'}}).composite(tiles).png().toBuffer());
    const unique=new Set(frames.map(f=>createHash('sha256').update(f).digest('hex'))).size;
    report.experiments.push({id,assetBytes:asset.length,uniqueFrames:unique,sha256:createHash('sha256').update(asset).digest('hex'),deterministicSeek:true,clearedAtFiveSeconds:true});
    console.log(`${id}: ${asset.length} bytes, ${unique} distinct frames`);
  }
  await sharp({create:{width:1440,height:528,channels:4,background:'#eae8de'}}).composite(rows.map((input,i)=>({input,left:0,top:i*176}))).png().toFile(path.join(out,'contact-sheet.png'));
  await page.goto(url);await page.waitForFunction(()=>!!window.seekShot);await page.evaluate(()=>window.seekShot(3300));
  await page.screenshot({path:path.join(out,'comparison-desktop.png'),fullPage:true});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(out,'comparison-mobile.png'),fullPage:true});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  report.checks.responsiveNoOverflow=true;
  await page.emulateMedia({reducedMotion:'reduce'});await page.reload();await page.waitForFunction(()=>!!window.seekShot);
  assert.ok(await page.getByText('Reduced motion is enabled.',{exact:false}).isVisible());
  report.checks.reducedMotion=true;
  await page.evaluate(()=>window.seekShot(5000));
  assert.ok(await page.locator('.overlay-slot').evaluateAll(nodes=>nodes.every(node=>{
    const svg=node.querySelector('svg');
    return getComputedStyle(svg).visibility==='hidden'||svg.querySelector('g')?.getAttribute('opacity')==='0';
  })));
  report.checks.reducedMotionClearsAtDeadline=true;
  await page.emulateMedia({reducedMotion:'no-preference'});await page.reload();await page.waitForFunction(()=>!!window.seekShot);
  await page.getByRole('button',{name:'Take a picture'}).click();await page.waitForTimeout(600);
  let before=await page.evaluate(()=>window.shotState.ms);assert.ok(before>0&&before<1500);
  await page.getByRole('button',{name:'Take a picture'}).click();assert.ok((await page.evaluate(()=>window.shotState.ms))<before);
  await page.getByRole('button',{name:'Pause animation'}).click();
  const paused=await page.evaluate(()=>window.shotState.ms);await page.waitForTimeout(150);
  assert.equal(await page.evaluate(()=>window.shotState.ms),paused);
  report.checks.repeatCaptureRestarts=true;report.checks.pauseFreezes=true;
  await page.getByRole('button',{name:'Sound off',exact:true}).click();
  await page.getByRole('button',{name:'Take a picture'}).click();await page.waitForTimeout(600);
  assert.ok(await page.getByRole('button',{name:'Sound on',exact:true}).isVisible());
  await page.getByRole('button',{name:'Pause animation'}).click();
  report.checks.soundOptIn=true;
  assert.deepEqual(errors,[]);report.checks.browserErrors=errors;
  await writeFile(path.join(out,'verification.json'),JSON.stringify(report,null,2)+'\n');
  console.log('Export and browser verification complete.');
} finally {await browser.close();}
