"""Compile and execute freestanding A32 trichrome core against an independent reference.

This is not a feature candidate until the native capture adapter is proved.
"""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

import numpy as np
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as r

HERE=Path(__file__).resolve().parent
OUT=HERE.parents[1]/'scratch/trichrome-firmware'
BASE=0x54300000;RAM=0x62000000;HEAP=0x68000000;STACK=0x61010000;STOP=0x61020000
CTX=RAM;STATE=RAM+0x1000;ID=RAM+0x2000;PICS=RAM+0x3000;STUB=RAM+0x4000


def compile_core():
    assert (HERE/'native/trichrome.c').exists(), 'Native trichrome implementation is missing'
    OUT.mkdir(parents=True,exist_ok=True)
    cc=[sys.executable,'-m','ziglang','cc','-target','arm-freestanding-eabi','-mcpu=cortex_a9','-marm',
        '-mfloat-abi=soft','-Os','-ffreestanding','-fno-builtin','-fno-unwind-tables',
        '-fno-asynchronous-unwind-tables','-nostdlib','-fno-jump-tables','-Wall','-Wextra','-Werror']
    subprocess.run(cc+['-c',str(HERE/'native/trichrome.c'),'-o',str(OUT/'core.o')],check=True,capture_output=True)
    subprocess.run([sys.executable,'-m','ziglang','ld.lld',f'-Ttext={BASE:#x}','--entry=tri_process',
                    '-o',str(OUT/'core.elf'),str(OUT/'core.o')],check=True,capture_output=True)
    with (OUT/'core.elf').open('rb') as f:
        e=ELFFile(f);symbols={s.name:s['st_value'] for s in e.get_section_by_name('.symtab').iter_symbols()}
        sections=[(s['sh_addr'],s.data()) for s in e.iter_sections() if s['sh_flags']&2 and s['sh_size']]
    return symbols,sections


def rgb_channels(y,c):
    cr=c[:,1::2].astype(np.int32)-128;cb=c[:,::2].astype(np.int32)-128
    cr=np.repeat(cr,2,axis=1);cb=np.repeat(cb,2,axis=1);v=y.astype(np.int32)
    red=np.clip(v+((359*cr+128)>>8),0,255)
    green=np.clip(v-((88*cb+183*cr+128)>>8),0,255)
    return red,green


def reduced(y,c):
    h,w=y.shape
    return [((a.reshape(h//4,4,w//4,4).sum(axis=(1,3))+8)>>4).astype(np.int32) for a in rgb_channels(y,c)]


def reference(frames):
    """Independent full-array formulation; native uses two-row streaming rings."""
    y,c=frames[2];h,w=y.shape
    dr=reduced(*frames[0])[0]-reduced(y,c)[0]
    dg=reduced(*frames[1])[1]-reduced(y,c)[1]
    yy,xx=np.indices((h,w))
    sx=(2*xx+1-4);sy=(2*yy+1-4)
    x0=sx//8;y0=sy//8;tx=sx%8;ty=sy%8
    x1=np.clip(x0+1,0,w//4-1);y1=np.clip(y0+1,0,h//4-1)
    x0=np.clip(x0,0,w//4-1);y0=np.clip(y0,0,h//4-1)
    def up(d):return (d[y0,x0]*(8-tx)*(8-ty)+d[y0,x1]*tx*(8-ty)+d[y1,x0]*(8-tx)*ty+d[y1,x1]*tx*ty+32)>>6
    dr=up(dr);dg=up(dg)
    dy=(77*dr+150*dg+128)>>8
    sr=dr[:,::2]+dr[:,1::2];sg=dg[:,::2]+dg[:,1::2]
    cb=(-43*sr-85*sg+256)>>9;cr=(128*sr-107*sg+256)>>9
    delta=np.empty_like(c,dtype=np.int32);delta[:,::2]=cb;delta[:,1::2]=cr
    return np.clip(y.astype(int)+dy,0,255).astype(np.uint8),np.clip(c.astype(int)+delta,0,255).astype(np.uint8)


class Machine:
    def __init__(self,symbols,sections,fail=False):
        self.s=symbols;self.mu=Uc(UC_ARCH_ARM,UC_MODE_ARM);u=self.mu
        for at,size in [(BASE,0x20000),(RAM,0x10000),(STACK-0x10000,0x11000),(STOP,0x1000)]:u.mem_map(at,size)
        for at,data in sections:u.mem_write(at,data)
        self.blocks=[];self.live={};self.allocs=[];self.cache=[];self.fail=fail
        for i in range(4):u.mem_write(STUB+i*16,struct.pack('<I',0xe12fff1e))
        u.mem_write(CTX,struct.pack('<4I',*[STUB+i*16 for i in range(4)]))
        u.mem_write(STATE,bytes(2048))
        u.hook_add(UC_HOOK_CODE,self.stub,begin=STUB,end=STUB+64)
        self.picture_info=[]

    def stub(self,u,at,size,ud):
        kind=(at-STUB)//16;a=u.reg_read(r.UC_ARM_REG_R0)
        if kind==0:
            n=a;self.allocs.append(n)
            if self.fail:u.reg_write(r.UC_ARM_REG_R0,0);return
            # Prefix and complete tail are checked; pages before/after stay unmapped.
            p=HEAP+0x1040;size=(n+128+4095)&~4095
            if self.live:raise AssertionError('Unexpected second persistent allocation')
            u.mem_map(HEAP+0x1000,size);u.mem_write(HEAP+0x1000,b'\xa7'*size)
            self.live[p]=(n,size);u.mem_write(p,b'\xa5'*n);u.reg_write(r.UC_ARM_REG_R0,p)
        elif kind==1:
            assert a in self.live,'free of unowned memory';n,size=self.live.pop(a)
            assert bytes(u.mem_read(HEAP+0x1000,64))==b'\xa7'*64,'owned prefix overwritten'
            tail=HEAP+0x1000+size-(a+n)
            assert bytes(u.mem_read(a+n,tail))==b'\xa7'*tail,'owned tail overwritten'
            u.mem_unmap(HEAP+0x1000,size)
        else:self.cache.append((kind,a,u.reg_read(r.UC_ARM_REG_R1)))

    def call(self,name,*args):
        u=self.mu;u.reg_write(r.UC_ARM_REG_SP,STACK);u.reg_write(r.UC_ARM_REG_LR,STOP)
        saved={i:0x12340000+i for i in range(4,12)}
        for i,v in saved.items():u.reg_write(getattr(r,'UC_ARM_REG_R'+str(i)),v)
        for i,v in enumerate(args):u.reg_write(getattr(r,'UC_ARM_REG_R'+str(i)),v)
        u.emu_start(self.s[name],STOP,count=20_000_000)
        assert u.reg_read(r.UC_ARM_REG_PC)==STOP and u.reg_read(r.UC_ARM_REG_SP)==STACK,name
        assert all(u.reg_read(getattr(r,'UC_ARM_REG_R'+str(i)))==v for i,v in saved.items()),name
        return u.reg_read(r.UC_ARM_REG_R0)

    def pictures(self,images):
        u=self.mu;desc=[];self.picture_info=[]
        for i,(y,c) in enumerate(images):
            h,w=y.shape;stride=w+16;ya=0x80001000+i*0x01000000;ca=ya+0x00400000
            for a,data in [(ya,y),(ca,c)]:
                size=(stride*h+4095)&~4095
                # Mapping is constant between calls. Sentinels cover every byte of row padding.
                try:u.mem_map(a,size)
                except Exception:pass
                v=np.full((h,stride),0xc7,np.uint8);v[:,:w]=data;u.mem_write(a,v.tobytes())
            desc.append(struct.pack('<4B3I6H4B',1,0,0,0,ya,ca,stride*h*2,w,h,stride,h,0,0,0,0,0,0))
            self.picture_info.append((ya,ca,w,h,stride))
        u.mem_write(PICS,b''.join(desc))

    def invoke(self,index,generation=7,settings=123,kind=1,now=None):
        self.mu.mem_write(ID,struct.pack('<5I',generation,index,settings,kind,now if now is not None else index*100))
        self.mu.mem_write(STACK,struct.pack('<I',len(self.picture_info)))
        # Fifth argument remains at original SP, as AAPCS requires.
        return self.call('tri_process',CTX,STATE,ID,PICS)

    def read(self):
        result=[]
        for ya,ca,w,h,s in self.picture_info:
            pair=[]
            for at in (ya,ca):
                a=np.frombuffer(bytes(self.mu.mem_read(at,s*h)),dtype=np.uint8).reshape(h,s)
                assert np.all(a[:,w:]==0xc7),'stride padding changed'
                pair.append(a[:,:w].copy())
            result.append(tuple(pair))
        return result


def main():
    symbols,sections=compile_core();rng=np.random.default_rng(194)
    still=[(rng.integers(20,230,(h,w),dtype=np.uint8),rng.integers(80,175,(h,w),dtype=np.uint8)) for w,h in [(128,96),(64,48),(32,24)]]
    checks=[]
    def assert_same(a,b):
        for aa,bb in zip(a,b):
            for x,y in zip(aa,bb):np.testing.assert_array_equal(x,y)
    for moving in (False,True):
        m=Machine(symbols,sections);frames=[]
        for shot in range(3):
            images=[(y.copy(),c.copy()) for y,c in still]
            if moving:
                for y,c in images:
                    x=4+shot*(y.shape[1]//4);y[8:20,x:x+8]=220;c[8:20,x:x+8]=128
            frames.append(images);m.pictures(images);result=m.invoke(shot+1)
            if shot<2:assert result==0;assert_same(m.read(),images)
        assert result==1
        expected=[reference([frames[k][i] for k in range(3)]) for i in range(3)]
        assert_same(m.read(),expected)
        if not moving:assert_same(m.read(),still)
        assert not m.live
        checks.append(dict(case='moving' if moving else 'static',allocated=m.allocs,cache_calls=len(m.cache)))
    for bad in ['single','generation','settings','out_of_order','timeout','alloc_failure','cancel','dimensions']:
        m=Machine(symbols,sections,fail=bad=='alloc_failure');m.pictures(still);m.invoke(1)
        if bad=='cancel':m.call('tri_cancel',CTX,STATE)
        if bad=='dimensions':m.pictures([(y[:80],c[:80]) if i==0 else (y,c) for i,(y,c) in enumerate(still)])
        before=m.read()
        result=m.invoke(2,generation=8 if bad=='generation' else 7,settings=124 if bad=='settings' else 123,
                        kind=0 if bad=='single' else 1,now=40000 if bad=='timeout' else 200) if bad!='out_of_order' else m.invoke(3)
        assert result==0;assert_same(m.read(),before);assert not m.live,bad
        checks.append(dict(case=bad,no_op=True,freed=True))
    for bad in ['duplicate_descriptor','same_picture_overlap','cross_picture_overlap','wrong_format','crop_change','firmware_code_plane','invalid_edge_range']:
        m=Machine(symbols,sections);m.pictures(still);m.invoke(1);m.invoke(2)
        before=m.read()
        if bad=='duplicate_descriptor':m.mu.mem_write(PICS+32,bytes(m.mu.mem_read(PICS,32)))
        if bad=='same_picture_overlap':m.mu.mem_write(PICS+8,struct.pack('<I',m.picture_info[0][0]+4))
        if bad=='cross_picture_overlap':m.mu.mem_write(PICS+32+4,struct.pack('<I',m.picture_info[0][0]+32))
        if bad=='wrong_format':m.mu.mem_write(PICS,b'\x02')
        if bad=='crop_change':m.mu.mem_write(PICS+24,struct.pack('<H',4))
        if bad=='firmware_code_plane':m.mu.mem_write(PICS+4,struct.pack('<I',0x53400000))
        if bad=='invalid_edge_range':m.mu.mem_write(PICS+4,struct.pack('<I',0xbffffff0))
        assert m.invoke(3)==0;assert_same(m.read(),before);assert not m.live
        checks.append(dict(case='phase3_'+bad,no_op=True,freed=True))
    m=Machine(symbols,sections);m.pictures(still);m.invoke(1,generation=1);m.invoke(1,generation=2)
    assert len(m.allocs)==2 and len(m.live)==1
    m.mu.mem_write(STATE,struct.pack('<I',1));m.call('tri_cancel',CTX,STATE)
    assert len(m.live)==1,'cancel must defer free while processing'
    m.mu.mem_write(STATE,struct.pack('<I',0));assert m.invoke(2,generation=2)==0;assert not m.live
    checks.append(dict(case='rearm_and_busy_cancel',owned_storage_pinned_until_safe=True,freed=True))
    state_bytes=Machine(symbols,sections).call('tri_state_bytes')
    report=dict(checks=checks,state_bytes=state_bytes,source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (HERE/'native').glob('*')},
                native_parity=True,hardware_tested=False,capture_adapter_verified=False,
                limitation='Core component checks only; adapter and actual installed hook chain are verified separately by check_camera.py and check_installed.py. No camera runtime claim.')
    (OUT/'native-core-verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
