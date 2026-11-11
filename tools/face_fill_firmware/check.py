"""Native face module checks against independent Python integer reference."""
from __future__ import annotations
import argparse,base64,hashlib,json,struct,sys
from pathlib import Path
import numpy as np
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE,UC_HOOK_MEM_WRITE
from unicorn import arm_const as reg

ROOT=Path(__file__).resolve().parents[2]
CODE=0x10000;CTX=0x60000000;CFG=0x60001000;DESC=0x60002000;REC=0x61000000
YP=0x62001000;CP=0x63001000;STACK=0x7000f000;STOP=0x71000000;CALLS=0x72000000


def table():
    result=[]
    for i in range(256):
        s=i/255;v=s/12.92 if s<=.04045 else ((s+.055)/1.055)**2.4
        t=min(1,max(0,(v-.45)/.45));ev=.85*(1-t*t*(3-2*t))
        lifted=v*2**ev;out=12.92*lifted if lifted<=.0031308 else 1.055*lifted**(1/2.4)-.055
        result.append(max(0,min(255,round(out*255))-i))
    return bytes(result)


def ref(y,c,w,h,stride,rects,fw,fh,keeper=False):
    """Independent scalar integer spec. Input/output planes include padding."""
    out=bytearray(y);colour=bytearray(c);lut=table()
    scaled=[]
    for x,yy,bw,bh in rects:
        x0=x*w//fw;y0=yy*h//fh;x1=(x+bw)*w//fw;y1=(yy+bh)*h//fh
        if x1>x0 and y1>y0:scaled.append((x0,y0,x1-x0,y1-y0))
    def weight(x,yy):
        best=0
        for a,b,bw,bh in scaled:
            nx=((2*x+1-2*a-bw)*(65536//bw))>>8
            ny=((2*yy+1-2*b-bh)*(65536//bh))>>8
            rr=nx*nx+ny*ny
            if rr>=65536:continue
            t=max(0,(rr-24576)//160)
            q=256-((t*t*(768-2*t)+32768)>>16)
            best=max(best,q)
        return best
    for yy in range(h):
        for x in range(0,w,2):
            pos=yy*stride+x;cb=c[pos];cr=c[pos+1]
            gate=max(0,min(256,(cb-72)*16,(144-cb)*16,(cr-122)*24,(196-cr)*8,(cr-cb)*24))
            weights=[]
            for j in (0,1):
                Y=y[pos+j];g=gate*max(0,min(256,(Y-4)*32))>>8
                q=weight(x+j,yy)*g>>8;weights.append(q)
                peak=max(Y+((359*(cr-128)+128)>>8),Y-((88*(cb-128)+183*(cr-128)+128)>>8),Y+((454*(cb-128)+128)>>8))
                delta=min(lut[Y]*q>>8,max(0,254-peak))
                out[pos+j]=Y+delta
            if keeper:
                k=(min(weights)*77+128)>>8
                colour[pos]=cb+(((128-cb)*k+128)>>8)
                colour[pos+1]=cr+(((128-cr)*k+128)>>8)
    return bytes(out),bytes(colour)


def run_case(module,*,rects=((14,10,48,44),),look=64,keeper=False,fw=96,fh=64,
             w=96,h=64,stride=112,invalid=None,chroma=(108,153),luma=None,screennail=False,opaque_size=None):
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    code=base64.b64decode(module['code'])
    for at,size in [(CODE,(len(code)+4095)&~4095),(CTX,0x3000),(REC,0x40000),
                    (YP,0x4000),(CP,0x4000),(STACK-0xf000,0x10000),(STOP,0x1000),(CALLS,0x1000)]:u.mem_map(at,size)
    u.mem_write(CODE,code);u.mem_write(REC,bytes(0x40000))
    u.mem_write(REC+0x77c,bytes([look]));u.mem_write(REC+0x38d50,struct.pack('<2I',fw,fh))
    u.mem_write(REC+0x38d6c,struct.pack('<H',len(rects)))
    for i,r in enumerate(rects[:10]):u.mem_write(REC+0x38ff0+i*64,struct.pack('<4I',*r))
    lut=CTX+0x100;u.mem_write(lut,table())
    keep=bytearray(20);keep[0]=int(keeper)
    context=struct.pack('<9I',0x314c4646,CALLS,CALLS+4,CALLS+8,lut,fw,fh,20,0)+keep
    u.mem_write(CTX,context)
    desc=struct.pack('<B3xIII8H',1,YP,CP,stride*h,w,h,stride,h,0,0,0,0)
    u.mem_write(DESC,desc);u.mem_write(CFG+0x34,struct.pack('<I',REC));u.mem_write(CFG+0x3c,struct.pack('<4I',DESC,DESC,0,0))
    rng=np.random.default_rng(123);yy=rng.integers(32,190,size=(h,stride),dtype=np.uint8)
    cc=np.full((h,stride),0xa5,np.uint8);cc[:,:w:2]=chroma[0];cc[:,1:w:2]=chroma[1]
    if luma is not None:yy[:,:w]=luma
    y=yy.tobytes();c=cc.tobytes();u.mem_write(YP,y);u.mem_write(CP,c)
    if invalid=='count':u.mem_write(REC+0x38d6c,struct.pack('<H',11))
    if invalid=='record-size':u.mem_write(REC+0x38d50,struct.pack('<I',0))
    if invalid=='rect':u.mem_write(REC+0x38ff0,struct.pack('<4I',fw-2,0,10,30))
    if invalid=='format':u.mem_write(DESC,b'\x02')
    if invalid=='stride':u.mem_write(DESC+20,struct.pack('<H',w-2))
    if invalid=='overlap':u.mem_write(DESC+8,struct.pack('<I',YP+32))
    if invalid=='magic':u.mem_write(CTX,bytes(4))
    if invalid=='record-align':u.mem_write(CFG+0x34,struct.pack('<I',REC+2))
    if invalid=='record-end':u.mem_write(CFG+0x34,struct.pack('<I',0xbffffffc))
    if invalid=='plane-end':u.mem_write(DESC+4,struct.pack('<I',0xbffffffc))
    if invalid=='plane-low':u.mem_write(DESC+4,struct.pack('<I',0x55001000))
    if opaque_size is not None:u.mem_write(DESC+12,struct.pack('<I',opaque_size))
    if invalid=='height':u.mem_write(DESC+22,struct.pack('<H',h-1))
    if invalid=='offset-x':u.mem_write(DESC+24,struct.pack('<H',2))
    if invalid=='offset-y':u.mem_write(DESC+26,struct.pack('<H',2))
    if invalid=='cross-picture':
        u.mem_write(DESC+64,struct.pack('<B3xIII8H',1,YP+32,CP+0x2000,stride*h,w,h,stride,h,0,0,0,0))
        u.mem_write(CFG+0x40,struct.pack('<I',DESC+64))
    ys=bytes([70])*2048;cs=bytes(chroma)*1024
    if screennail:
        u.mem_write(YP+0x2000,ys);u.mem_write(CP+0x2000,cs)
        u.mem_write(DESC+64,struct.pack('<B3xIII8H',1,YP+0x2000,CP+0x2000,2048,48,32,64,32,0,0,0,0))
        u.mem_write(CFG+0x40,struct.pack('<I',DESC+64))
    immutable=(bytes(u.mem_read(CTX,0x3000)),bytes(u.mem_read(REC,0x40000)))
    logs=[]
    def writes(cpu,access,at,size,value,_):
        if STACK-0xf000<=at and at+size<=STACK:return
        for base,ww,hh,ss in [(YP,w,h,stride),(CP,w,h,stride)]+([(YP+0x2000,48,32,64),(CP+0x2000,48,32,64)] if screennail else []):
            off=at-base
            if off>=0 and off//ss<hh and off%ss+size<=ww:return
        raise AssertionError(('write outside active image/stack',hex(at),size))
    u.hook_add(UC_HOOK_MEM_WRITE,writes)
    def hook(cpu,at,size,_):
        if CALLS<=at<CALLS+12:
            logs.append((at-CALLS,cpu.reg_read(reg.UC_ARM_REG_R1),cpu.reg_read(reg.UC_ARM_REG_R2)))
            if at==CALLS:cpu.reg_write(reg.UC_ARM_REG_R0,0x12345678)
            cpu.reg_write(reg.UC_ARM_REG_PC,cpu.reg_read(reg.UC_ARM_REG_LR))
    u.hook_add(UC_HOOK_CODE,hook,begin=CALLS,end=CALLS+8)
    u.reg_write(reg.UC_ARM_REG_CPSR,0x13);u.reg_write(reg.UC_ARM_REG_SP,STACK);u.reg_write(reg.UC_ARM_REG_LR,STOP)
    for i in range(4,12):u.reg_write(getattr(reg,'UC_ARM_REG_R'+str(i)),0x12340000+i)
    u.reg_write(reg.UC_ARM_REG_R0,CTX);u.reg_write(reg.UC_ARM_REG_R1,CFG);u.reg_write(reg.UC_ARM_REG_R2,REC)
    u.emu_start(CODE,STOP,count=12_000_000)
    assert u.reg_read(reg.UC_ARM_REG_PC)==STOP and u.reg_read(reg.UC_ARM_REG_SP)==STACK
    assert all(u.reg_read(getattr(reg,'UC_ARM_REG_R'+str(i)))==0x12340000+i for i in range(4,12))
    got=(bytes(u.mem_read(YP,len(y))),bytes(u.mem_read(CP,len(c))))
    expected=(y,c) if invalid or look<64 or look>=84 or not rects else ref(y,c,w,h,stride,rects,fw,fh,keeper)
    assert got==expected,('pixel mismatch',invalid,look,keeper,rects)
    assert all(got[0][i*stride+w:(i+1)*stride]==y[i*stride+w:(i+1)*stride] for i in range(h))
    assert immutable==(bytes(u.mem_read(CTX,0x3000)),bytes(u.mem_read(REC,0x40000)))
    if screennail:
        small=(bytes(u.mem_read(YP+0x2000,2048)),bytes(u.mem_read(CP+0x2000,2048)))
        assert small==ref(ys,cs,48,32,64,rects,fw,fh,keeper)
    if not invalid and 64<=look<84 and rects:
        assert logs[0][0]==0 and len(logs)==(9 if screennail else 5)
        for _,address,length in logs[1:]:assert not(address&63) and not(length&63)
    else:assert not logs
    return {'changed':got!=(y,c),'cache_calls':len(logs)}


def check_capture_clear(module):
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM);code=base64.b64decode(module['code'])
    for at,size in [(CODE,4096),(REC,0x40000),(STACK-0xf000,0x10000),(STOP,4096)]:u.mem_map(at,size)
    u.mem_write(CODE,code)
    for pointer in (REC,0,REC+2,0xbffffffc):
        before=bytearray([0xa5])*0x40000;u.mem_write(REC,bytes(before))
        u.reg_write(reg.UC_ARM_REG_R0,pointer);u.reg_write(reg.UC_ARM_REG_SP,STACK);u.reg_write(reg.UC_ARM_REG_LR,STOP)
        u.emu_start(CODE+module['entries']['face_capture_clear'],STOP,count=10000)
        assert u.reg_read(reg.UC_ARM_REG_PC)==STOP and u.reg_read(reg.UC_ARM_REG_SP)==STACK
        if pointer==REC:before[0x38d6c:0x38d6e]=bytes(2)
        assert bytes(u.mem_read(REC,0x40000))==bytes(before)
    return 4


def main():
    p=argparse.ArgumentParser();p.add_argument('--module',type=Path,default=Path(__file__).with_name('module-code.json'));p.add_argument('--output',type=Path,default=ROOT/'scratch/face-fill-firmware/native-check.json');a=p.parse_args()
    module=json.loads(a.module.read_text(encoding='utf-8'))
    results=[]
    for kwargs in [{},{'keeper':True},{'rects':[]},{'look':11},{'look':84},
                   {'rects':[(14,10,48,44)]*2},{'rects':[(1,2,20,30),(44,10,38,40)]},
                   {'screennail':True},
                   {'opaque_size':0},{'opaque_size':1},
                   *[{'chroma':ch,'luma':Y,'keeper':True} for ch in [(128,128),(0,255),(255,0),(110,145)] for Y in [0,8,240,255]],
                   *[{'invalid':k} for k in ['count','record-size','rect','format','stride','overlap','magic',
                                             'record-align','record-end','plane-end','plane-low','height','offset-x','offset-y','cross-picture']]]:
        results.append({'parameters':kwargs,**run_case(module,**kwargs)})
    cleared=check_capture_clear(module)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps({'module_sha256':module['sha256'],'cases':results,'capture_clear_cases':cleared,'all_passed':True},indent=2)+'\n',encoding='utf-8')
    print(len(results),'native pixel cases and',cleared,'capture-clear cases passed')


if __name__=='__main__':main()
