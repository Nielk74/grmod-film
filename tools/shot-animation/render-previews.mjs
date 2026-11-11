import {chromium} from 'playwright';
import sharp from 'sharp';
import {mkdir,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {DURATION_MS,SEQUENCE_IDS} from './sequence.mjs';
const here=path.dirname(fileURLToPath(import.meta.url)),out=path.join(here,'out');
await mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true,args:['--autoplay-policy=no-user-gesture-required']});
const page=await browser.newPage({viewport:{width:360,height:280}});
const url=process.env.SHOT_LAB_URL||'http://127.0.0.1:5186';
try{
  for(const id of process.argv.length>2?process.argv.slice(2).filter(id=>SEQUENCE_IDS.includes(id)):SEQUENCE_IDS){
    await page.goto(`${url}/?export=${id}&large=1`);await page.waitForFunction(()=>!!window.seekShot);
    const frames=[],raw=[];
    for(let ms=0;ms<DURATION_MS;ms+=50){
      await page.evaluate(ms=>window.seekShot(ms),ms);
      const png=await page.screenshot({omitBackground:true,clip:{x:0,y:0,width:360,height:280}});
      frames.push(png.toString('base64'));raw.push(await sharp(png).flatten({background:'#e8e7dd'}).ensureAlpha().raw().toBuffer());
    }
    await sharp(Buffer.concat(raw),{raw:{width:360,height:280*raw.length,channels:4,pageHeight:280}})
      .gif({loop:0,delay:Array(raw.length).fill(50),colours:64,effort:7}).toFile(path.join(out,`terminal-${id}.gif`));
    console.log(`${id}: animated GIF rendered (${raw.length} frames)`);
    const recording=await page.evaluate(async({id,frames,duration})=>{
      const {renderSound}=await import('/src/sound.ts'),pcm=await renderSound(id);
      const wav=new ArrayBuffer(44+pcm.length*pcm.numberOfChannels*2),view=new DataView(wav);
      const label=(at,s)=>{for(let i=0;i<s.length;i++)view.setUint8(at+i,s.charCodeAt(i));};
      label(0,'RIFF');view.setUint32(4,wav.byteLength-8,true);label(8,'WAVE');label(12,'fmt ');view.setUint32(16,16,true);
      view.setUint16(20,1,true);view.setUint16(22,pcm.numberOfChannels,true);view.setUint32(24,pcm.sampleRate,true);
      view.setUint32(28,pcm.sampleRate*pcm.numberOfChannels*2,true);view.setUint16(32,pcm.numberOfChannels*2,true);view.setUint16(34,16,true);
      label(36,'data');view.setUint32(40,wav.byteLength-44,true);
      const channels=Array.from({length:pcm.numberOfChannels},(_,i)=>pcm.getChannelData(i));
      for(let i=0;i<pcm.length;i++)for(let c=0;c<channels.length;c++)view.setInt16(44+(i*channels.length+c)*2,Math.round(Math.max(-1,Math.min(1,channels[c][i]))*32767),true);
      const base64=blob=>new Promise(resolve=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.readAsDataURL(blob);});
      const images=await Promise.all(frames.map(frame=>new Promise(resolve=>{const img=new Image();img.onload=()=>resolve(img);img.src=`data:image/png;base64,${frame}`;})));
      const canvas=document.createElement('canvas');canvas.width=480;canvas.height=400;
      const ctx=canvas.getContext('2d'),audio=new AudioContext({sampleRate:48000}),dest=audio.createMediaStreamDestination();
      await audio.resume();const voice=audio.createBufferSource();voice.buffer=pcm;voice.connect(dest);
      const stream=canvas.captureStream(30);for(const track of dest.stream.getAudioTracks())stream.addTrack(track);
      const mimeType=MediaRecorder.isTypeSupported('video/webm;codecs=vp9,opus')?'video/webm;codecs=vp9,opus':'video/webm';
      const recorder=new MediaRecorder(stream,{mimeType,videoBitsPerSecond:1500000,audioBitsPerSecond:128000}),chunks=[];
      recorder.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};
      const stopped=new Promise(resolve=>recorder.onstop=resolve);
      const names={dash:'Disk Dash',portal:'Pixel Portal',rocket:'Rocket Delivery'};
      let started=0,raf=0;
      const draw=now=>{
        const elapsed=now-started,index=Math.min(images.length-1,Math.floor(Math.max(0,elapsed)/50));
        ctx.fillStyle='#e8e7dd';ctx.fillRect(0,0,480,400);ctx.drawImage(images[index],0,0,480,373);
        ctx.fillStyle='#25312f';ctx.font='14px Arial';ctx.textAlign='center';ctx.fillText(`${names[id]} · Pocket Lab + SFX`,240,386);
        if(elapsed<duration)raf=requestAnimationFrame(draw);
      };
      started=performance.now();draw(started);recorder.start();voice.start();
      await new Promise(resolve=>setTimeout(resolve,duration+80));recorder.stop();voice.stop();cancelAnimationFrame(raf);await stopped;
      for(const track of stream.getTracks())track.stop();await audio.close();
      return{webm:await base64(new Blob(chunks,{type:'video/webm'})),wav:await base64(new Blob([wav],{type:'audio/wav'}))};
    },{id,frames,duration:DURATION_MS});
    await writeFile(path.join(out,`terminal-${id}.webm`),Buffer.from(recording.webm,'base64'));
    await writeFile(path.join(out,`terminal-${id}.wav`),Buffer.from(recording.wav,'base64'));
    console.log(`${id}: video with synchronized stereo SFX + WAV saved`);
  }
}finally{await browser.close();}
