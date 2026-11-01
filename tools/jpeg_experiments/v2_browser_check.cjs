// Local whole-photo viewer smoke check. Optional argv[2]: Playwright package path.
const fs=require('node:fs');
const path=require('node:path');
const {chromium}=require(process.argv[2]||'playwright');
const root='C:/Users/Antoine/Pictures/GRMod-JPEG-Experiments-v2-2026-10-31';
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.goto('http://127.0.0.1:8747/',{waitUntil:'networkidle'});
 await page.locator('img').evaluateAll(images=>images.forEach(im=>im.loading='eager'));
 await page.waitForFunction(()=>Array.from(document.images).every(im=>im.complete&&im.naturalWidth>0),{},{timeout:30000});
 const count=await page.locator('article').count();
 if(count!==30)throw new Error('Expected 30 comparisons, got '+count);
 const card=page.locator('article').filter({has:page.getByRole('heading',{name:'R0000023-colour',exact:true})});
 await card.scrollIntoViewIfNeeded();
 await card.getByRole('button',{name:'Before (A)',exact:true}).click();
 if(await card.locator('.before').evaluate(el=>getComputedStyle(el).visibility)!=='visible')throw new Error('Before failed');
 await card.screenshot({path:path.join(root,'browser-colour-before.png')});
 await page.keyboard.press('b');
 if(await card.locator('.after').evaluate(el=>getComputedStyle(el).visibility)!=='visible')throw new Error('B failed');
 await card.screenshot({path:path.join(root,'browser-colour-after.png')});
 await page.keyboard.press('Space');
 if(await card.locator('.before').evaluate(el=>getComputedStyle(el).visibility)!=='visible')throw new Error('Blink failed');
 const desktop=await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth}));
 await page.setViewportSize({width:390,height:844});
 await card.scrollIntoViewIfNeeded();
 const mobile=await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth}));
 if(mobile.scrollWidth>mobile.width)throw new Error('Mobile overflow');
 if(errors.length)throw new Error(errors.join('\n'));
 fs.writeFileSync(path.join(root,'browser-checks.json'),JSON.stringify({comparisons:count,allImagesLoaded:true,
  beforeAfterButtons:true,keyboardABSpace:true,desktop,mobile,pageErrors:errors},null,2),'utf8');
 console.log('30 whole-image comparisons loaded; before/after and A/B/space verified; mobile fits.');
 await browser.close();
})().catch(e=>{console.error(e);process.exitCode=1});
