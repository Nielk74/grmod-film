"""Actual ARM YCbCr module on the three private JPEGs; no metadata copied.

The source portraits have empty camera face lists, so recorded real YuNet
detections stand in for the current/B list. This tests actual native pixels,
not a claim that the old shots carried camera detections.
"""
from __future__ import annotations
import base64,json,math,struct,sys
from pathlib import Path
import cv2,numpy as np
from PIL import Image,ImageOps
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn import arm_const as reg
from check import table
ROOT=Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT/'tools/face_fill'))
from audit import sha
from run import strip,save


def exposure_metrics(before,after,core):
    """Linear sRGB luminance on an independently defined original skin core."""
    ev=[];new_clips=0
    for start in range(0,before.height,64):
        a=np.asarray(before.crop((0,start,before.width,min(start+64,before.height))),np.float32)/255
        b=np.asarray(after.crop((0,start,after.width,min(start+64,after.height))),np.float32)/255
        linear=lambda x:np.where(x<=.04045,x/12.92,((x+.055)/1.055)**2.4)
        ya=linear(a)@np.array([.2126,.7152,.0722]);yb=linear(b)@np.array([.2126,.7152,.0722])
        selected=core[start:start+len(a)]&(ya>1e-6)
        ev.extend(np.log2(np.maximum(yb[selected],1e-9)/ya[selected]).tolist())
        new_clips+=int((((b>=1).any(2))&~((a>=1).any(2))).sum())
    return {'p10_ev':float(np.percentile(ev,10)),'median_ev':float(np.median(ev)),
            'p90_ev':float(np.percentile(ev,90)),'core_pixels':len(ev),'new_rgb_clip_pixels':new_clips}


def reference(Y,C,rects,keeper):
    h,w=Y.shape;out=Y.copy();colour=C.copy();lut=np.frombuffer(table(),np.uint8).astype(np.int32)
    x=np.arange(w,dtype=np.int32)[None,:]
    for start in range(0,h,64):
        yy=np.arange(start,min(h,start+64),dtype=np.int32)[:,None];mask=np.zeros((len(yy),w),np.int32)
        for a,b,bw,bh in rects:
            nx=((2*x+1-2*a-bw)*(65536//bw))>>8;ny=((2*yy+1-2*b-bh)*(65536//bh))>>8
            rr=nx*nx+ny*ny;t=np.maximum(0,(rr-24576)//160)
            t=np.minimum(t,256);q=256-((t*t*(768-2*t)+32768)>>16)
            q=np.where((abs(nx)<256)&(abs(ny)<256)&(rr<65536),q,0);np.maximum(mask,q,out=mask)
        sl=slice(start,start+len(yy));y=Y[sl].astype(np.int32)
        cb=np.repeat(C[sl,::2],2,axis=1).astype(np.int32);cr=np.repeat(C[sl,1::2],2,axis=1).astype(np.int32)
        gate=np.maximum(0,np.minimum.reduce([np.full(y.shape,256), (cb-72)*16,(144-cb)*16,(cr-122)*24,(196-cr)*8,(cr-cb)*24]))
        weights=mask*(gate*np.clip((y-4)*32,0,256)>>8)>>8
        peak=np.maximum.reduce([y+((359*(cr-128)+128)>>8),y-((88*(cb-128)+183*(cr-128)+128)>>8),y+((454*(cb-128)+128)>>8)])
        out[sl]=(y+np.minimum(lut[y]*weights>>8,np.maximum(0,254-peak))).astype(np.uint8)
        if keeper:
            k=(np.minimum(weights[:,::2],weights[:,1::2])*77+128)>>8
            for off in (0,1):
                old=C[sl,off::2].astype(np.int32);colour[sl,off::2]=(old+(((128-old)*k+128)>>8)).astype(np.uint8)
    return out,colour


def native(Y,C,rects,keeper,module):
    h,w=Y.shape;stride=(w+127)&~127;total=stride*h
    y=np.zeros((h,stride),np.uint8);c=y.copy();y[:,:w]=Y;c[:,:w]=C
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM);code=base64.b64decode(module['code'])
    code_at,ctx,cfg,desc,record,yp,cp,stack,stop,calls=0x10000,0x60000000,0x60001000,0x60002000,0x61000000,0x62001000,0x66001000,0x7000f000,0x71000000,0x72000000
    for at,size in [(code_at,(len(code)+4095)&~4095),(ctx,0x3000),(record,0x40000),(yp,(total+4095)&~4095),(cp,(total+4095)&~4095),(stack-0xf000,0x10000),(stop,4096),(calls,4096)]:u.mem_map(at,size)
    u.mem_write(code_at,code);u.mem_write(yp,y.tobytes());u.mem_write(cp,c.tobytes())
    u.mem_write(record+0x77c,b'\x40');u.mem_write(record+0x38d50,struct.pack('<2I',w,h));u.mem_write(record+0x38d6c,struct.pack('<H',len(rects)))
    for i,rect in enumerate(rects):u.mem_write(record+0x38ff0+i*64,struct.pack('<4I',*rect))
    u.mem_write(ctx,struct.pack('<9I',0x314c4646,calls,calls+4,calls+8,ctx+0x100,w,h,20,0)+bytes([int(keeper)])+bytes(19));u.mem_write(ctx+0x100,table())
    u.mem_write(desc,struct.pack('<B3xIII8H',1,yp,cp,total,w,h,stride,h,0,0,0,0));u.mem_write(cfg+0x34,struct.pack('<I',record));u.mem_write(cfg+0x3c,struct.pack('<I',desc))
    def hook(cpu,at,size,_):
        if at==calls:cpu.reg_write(reg.UC_ARM_REG_R0,1)
        cpu.reg_write(reg.UC_ARM_REG_PC,cpu.reg_read(reg.UC_ARM_REG_LR))
    u.hook_add(UC_HOOK_CODE,hook,begin=calls,end=calls+8)
    u.reg_write(reg.UC_ARM_REG_SP,stack);u.reg_write(reg.UC_ARM_REG_LR,stop);u.reg_write(reg.UC_ARM_REG_R0,ctx);u.reg_write(reg.UC_ARM_REG_R1,cfg);u.reg_write(reg.UC_ARM_REG_R2,record)
    u.emu_start(code_at,stop,count=6_000_000_000)
    assert u.reg_read(reg.UC_ARM_REG_PC)==stop
    oy=np.frombuffer(bytes(u.mem_read(yp,total)),np.uint8).reshape(h,stride)[:,:w].copy()
    oc=np.frombuffer(bytes(u.mem_read(cp,total)),np.uint8).reshape(h,stride)[:,:w].copy()
    return oy,oc


def rgb_image(Y,C,orientation):
    ycc=np.stack([Y,np.repeat(C[:,1::2],2,1),np.repeat(C[:,::2],2,1)],axis=-1)
    im=Image.fromarray(cv2.cvtColor(ycc,cv2.COLOR_YCrCb2RGB));im.getexif()[274]=orientation
    return ImageOps.exif_transpose(im)


def main():
    output=ROOT/'scratch/face-fill-firmware/photos';output.mkdir(parents=True,exist_ok=True)
    module=json.loads(Path(__file__).with_name('module-code.json').read_text(encoding='utf-8'))
    summary=json.loads((ROOT/'scratch/face-fill/summary.json').read_text(encoding='utf-8'));results=[]
    for row in summary['records'][:3]:
        path=Path(row['source']);before=sha(path);orientation=row['metadata']['orientation']
        with Image.open(path) as source:rgb=np.asarray(source.convert('RGB'));w,h=source.size
        rects=[]
        for face in row['detector']['accepted']:
            x,y,bw,bh=face['box']
            if orientation==6:x,y,bw,bh=y,h-x-bw,bh,bw
            elif orientation==8:x,y,bw,bh=w-y-bh,x,bh,bw
            x0=max(0,round(x));y0=max(0,round(y));x1=min(w,round(x+bw));y1=min(h,round(y+bh));rects.append([x0,y0,x1-x0,y1-y0])
        ycc=cv2.cvtColor(rgb,cv2.COLOR_RGB2YCrCb);Y=ycc[:,:,0].copy();C=Y.copy()
        C[:,::2]=((ycc[:,::2,2].astype(np.uint16)+ycc[:,1::2,2]+1)//2).astype(np.uint8)
        C[:,1::2]=((ycc[:,::2,1].astype(np.uint16)+ycc[:,1::2,1]+1)//2).astype(np.uint8)
        out=native(Y,C,rects,True,module);ref=reference(Y,C,rects,True)
        assert np.array_equal(out[0],ref[0]) and np.array_equal(out[1],ref[1])
        original=rgb_image(Y,C,orientation);processed=rgb_image(*out,orientation)
        with Image.open(ROOT/'scratch/face-fill'/('Ricoh-'+path.stem)/'mask.png') as m:
            core=np.asarray(m)>166
        metrics=exposure_metrics(original,processed,core)
        with Image.open(ROOT/'scratch/face-fill'/('Ricoh-'+path.stem)/'fill.jpg') as f:desktop=f.copy()
        save(strip([original,processed,desktop],['YCbCr422 basis','Actual ARM fill + keeper','Earlier RGB desktop fill']),output/(path.stem+'-native-sheet.jpg'))
        crop=tuple(row['crop_xyxy']);edge=crop[2]-crop[0]
        save(strip([i.crop(crop) for i in [original,processed,desktop]],['YCbCr422 basis 100%','ARM 100%','RGB desktop 100%'],edge,edge),output/(path.stem+'-native-crop-100.jpg'))
        save(processed,output/(path.stem+'-native.jpg'))
        assert sha(path)==before
        results.append({'file':path.name,'source_sha256':before,'rectangles_encoded':rects,'native_equals_reference':True,
                        'changed_y_pixels':int((out[0]!=Y).sum()),'changed_chroma_bytes':int((out[1]!=C).sum()),
                        'core_exposure':metrics,'core_definition':'Prior desktop original-image skin mask >166/255, unchanged selection',
                        'basis':'Source JPEG converted to full-range BT.601-like YCbCr422; YuNet current/B stand-in; no actual camera capture claim'})
        print(path.name,'ARM pixels equal independent reference;',metrics,flush=True)
    (output/'report.json').write_text(json.dumps({'module_sha256':module['sha256'],'results':results},indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
