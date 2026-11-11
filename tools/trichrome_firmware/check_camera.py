"""Execute native adapter/hooks with substituted allocator, cache and OS clock.

Exposure and JPEG objects are synthetic. This tests the installed control logic
without claiming actual firmware event ordering or successful camera startup.
"""
import json
from pathlib import Path
import struct

import numpy as np
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as r

from check import Machine, reference, RAM, PICS, STACK, STOP, STATE
from link import build

OUT=Path(__file__).resolve().parents[2]/'scratch/trichrome-firmware'
BASE=0x54300000;PRIOR=0x54310000;ANCHOR=0x5580438c
CFG=RAM+0x8000;ARGS=RAM+0x8100;COMMAND=RAM+0x9000
COMMON=[RAM+0x10000+i*0x80000 for i in range(4)]
ALLOC=0x536af2a8;FREE=0x536af2e4;CLOCK=0x536afc5c
CACHE=0x536bbc30;INVALIDATE=0x536bbcc0;CLEAN=0x536bbcac


class Camera(Machine):
    def __init__(self,mod,fail_at=0):
        self.s=mod['symbols'];self.mu=Uc(UC_ARCH_ARM,UC_MODE_ARM);u=self.mu
        for at,n in [(BASE,0x20000),(RAM,0x300000),(STACK-0x10000,0x11000),(STOP,0x1000),
                     (0x536af000,0x1000),(0x536bb000,0x1000),(0x55804000,0x1000)]:u.mem_map(at,n)
        u.mem_write(BASE,(OUT/'adapter-test/module.bin').read_bytes())
        for at in [ALLOC,FREE,CLOCK,CACHE,INVALIDATE,CLEAN]:u.mem_write(at,struct.pack('<I',0xe12fff1e))
        self.live={};self.allocs=[];self.freed=[];self.cache=[];self.next_heap=0x68000000
        self.now=100;self.clock_ok=True;self.fail_at=fail_at;self.picture_info=[]
        u.reg_write(r.UC_ARM_REG_C1_C0_2,0xf<<20);u.reg_write(r.UC_ARM_REG_FPEXC,0x40000000)
        for common in COMMON:u.mem_write(common+0x6f4,b'\x02');u.mem_write(common+0x77c,b'\x40')
        u.mem_write(ARGS+8,struct.pack('<I',CFG))
        for i in range(3):u.mem_write(CFG+0x3c+i*4,struct.pack('<I',PICS+i*32))
        u.hook_add(UC_HOOK_CODE,self.native_stub,begin=0x536af000,end=0x536bffff)
    def rd(self,at):return struct.unpack('<I',self.mu.mem_read(at,4))[0]
    def native_stub(self,u,at,n,ud):
        a=u.reg_read(r.UC_ARM_REG_R0)
        if at==ALLOC:
            self.allocs.append(a)
            if len(self.allocs)==self.fail_at:u.reg_write(r.UC_ARM_REG_R0,0);return
            size=(a+128+4095)&~4095;base=self.next_heap+0x1000;p=base+64
            self.next_heap=base+size+0x1000;u.mem_map(base,size);u.mem_write(base,b'\xa7'*size)
            self.live[p]=(base,a,size);u.reg_write(r.UC_ARM_REG_R0,p)
        elif at==FREE:
            assert a in self.live;start,n,size=self.live.pop(a)
            assert bytes(u.mem_read(start,64))==b'\xa7'*64
            assert bytes(u.mem_read(a+n,start+size-a-n))==b'\xa7'*(start+size-a-n)
            u.mem_unmap(start,size);self.freed.append(n)
        elif at==CLOCK:
            if self.clock_ok:u.mem_write(a,struct.pack('<Q',self.now))
            u.reg_write(r.UC_ARM_REG_R0,int(self.clock_ok))
        elif at==CACHE:u.reg_write(r.UC_ARM_REG_R0,0x63000000)
        elif at in [INVALIDATE,CLEAN]:self.cache.append((at,u.reg_read(r.UC_ARM_REG_R1),u.reg_read(r.UC_ARM_REG_R2)))
        else:return
        u.reg_write(r.UC_ARM_REG_PC,u.reg_read(r.UC_ARM_REG_LR))
    def run(self,name,*args,hook=False):
        u=self.mu;expected={i:0x12340000+i for i in range(13)}
        for i,v in enumerate(args):expected[i]=v
        for i,v in expected.items():u.reg_write(getattr(r,f'UC_ARM_REG_R{i}'),v)
        fp={i:0x0102030405060708+i for i in range(32)}
        for i,v in fp.items():u.reg_write(getattr(r,f'UC_ARM_REG_D{i}'),v)
        u.reg_write(r.UC_ARM_REG_SP,STACK);u.reg_write(r.UC_ARM_REG_LR,STOP)
        u.reg_write(r.UC_ARM_REG_CPSR,0xa0000013);u.reg_write(r.UC_ARM_REG_FPSCR,0x00400000)
        end={'tri_hook_arm':0x5342c968,'tri_hook_single':0x5342caf0,'tri_hook_override':0x53510804}.get(name,PRIOR if hook else STOP)
        u.emu_start(self.s[name],end,count=50_000_000)
        assert u.reg_read(r.UC_ARM_REG_PC)==end,(name,hex(u.reg_read(r.UC_ARM_REG_PC)))
        assert u.reg_read(r.UC_ARM_REG_SP)==STACK,name
        if hook:
            if name in ['tri_hook_arm','tri_hook_single']:expected[12]=STACK
            if name=='tri_hook_override':expected[3]=expected[2]
            assert all(u.reg_read(getattr(r,f'UC_ARM_REG_R{i}'))==v for i,v in expected.items()),name
            assert all(u.reg_read(getattr(r,f'UC_ARM_REG_D{i}'))==v for i,v in fp.items()),name
            assert u.reg_read(r.UC_ARM_REG_FPSCR)==0x00400000,name
            if name!='tri_hook_override':assert u.reg_read(r.UC_ARM_REG_CPSR)&0xf8000000==0xa0000000,name
        else:
            assert all(u.reg_read(getattr(r,f'UC_ARM_REG_R{i}'))==expected[i] for i in range(4,12)),name
        return u.reg_read(r.UC_ARM_REG_R0)
    def arm(self):self.run('tri_hook_arm',RAM,COMMAND,hook=True)
    def expose(self,k):self.run('tri_hook_expose',RAM,0,COMMON[k],hook=True)
    def jpeg(self,k):
        self.mu.mem_write(CFG+0x34,struct.pack('<I',COMMON[k]));self.run('tri_hook_jpeg',RAM,ARGS,hook=True)


def main():
    mod=build(OUT/'adapter-test',BASE,PRIOR,PRIOR);checks=[]
    rng=np.random.default_rng(612);still=[(rng.integers(24,220,(h,w),dtype=np.uint8),np.full((h,w),128,np.uint8)) for w,h in [(192,128),(64,48),(32,24)]]
    def same(a,b):
        for aa,bb in zip(a,b):
            for x,y in zip(aa,bb):np.testing.assert_array_equal(x,y)
    for moving,wrap in [(False,False),(True,False),(True,True)]:
        m=Camera(mod)
        if wrap:m.now=0xfffffff0
        m.arm();frames=[]
        for shot in range(3):
            pictures=[(y.copy(),c.copy()) for y,c in still]
            if moving:
                for y,c in pictures:y[8:20,4+shot*8:12+shot*8]=230
            frames.append(pictures);m.pictures(pictures);m.expose(shot);m.jpeg(shot);m.now=(m.now+100)&0xffffffff
            if shot<2:same(m.read(),pictures)
        same(m.read(),[reference([frames[k][i] for k in range(3)]) for i in range(3)])
        assert len(m.live)==1 and len(m.freed)==1,'only bounded adapter persists'
        checks.append(dict(case='timer_wrap' if wrap else 'moving' if moving else 'static',native_hook_chain=True,allocations=m.allocs))
    for case in ['no_burst','no_exposure','single_mode','standard_look','geometry','orientation','settings_changed','old_common','duplicate_jpeg','out_of_order','new_release','timeout','clock_failure','adapter_alloc_failure','pixels_alloc_failure','override','single_command','metadata_lock_busy']:
        m=Camera(mod,fail_at=1 if case=='adapter_alloc_failure' else 2 if case=='pixels_alloc_failure' else 0);m.pictures(still)
        if case!='no_burst':m.arm()
        if case not in ['no_exposure','adapter_alloc_failure']:m.expose(0)
        m.jpeg(0)
        if case=='single_mode':m.mu.mem_write(COMMON[1]+0x6f4,b'\x01')
        if case=='standard_look':m.mu.mem_write(COMMON[1]+0x77c,b'\x00')
        if case=='geometry':m.mu.mem_write(PICS+16,struct.pack('<H',188))
        if case=='orientation':m.mu.mem_write(COMMON[1]+0xc8,b'\x01')
        if case=='settings_changed':m.mu.mem_write(COMMON[1]+0x779,b'\x04')
        if case=='new_release':m.arm();m.jpeg(0)
        if case=='timeout':m.now+=31000
        if case=='clock_failure':m.clock_ok=False
        if case=='override':m.run('tri_hook_override',RAM,0,COMMON[3],hook=True)
        if case=='single_command':m.run('tri_hook_single',RAM,COMMAND,hook=True)
        if case=='metadata_lock_busy':
            ptr=m.rd(ANCHOR);m.mu.mem_write(ptr+4,struct.pack('<I',1));m.expose(1)
            m.mu.mem_write(ptr+4,bytes(4))
        if case=='duplicate_jpeg':m.jpeg(0)
        m.expose(1);m.expose(2)
        if case=='old_common':m.mu.mem_write(CFG+0x34,struct.pack('<I',COMMON[3]));m.run('tri_hook_jpeg',RAM,ARGS,hook=True)
        elif case=='out_of_order':m.jpeg(2)
        else:m.jpeg(1)
        m.jpeg(2);same(m.read(),still)
        assert len(m.live)<=1,case
        checks.append(dict(case=case,no_op=True,owned_pixel_memory_freed=True))
    # Exact full-resolution allocation/preflight, stopping before the first
    # 24Mpixel extraction. No full-frame timing/processing result is implied.
    m=Camera(mod);m.arm();m.expose(0)
    desc=[]
    for i,(w,h,stride) in enumerate([(6000,4000,6144),(720,480,736),(160,120,176)]):
        ya=0x80000000+i*0x05000000;ca=ya+0x02000000
        desc.append(struct.pack('<4B3I6H4B',1,0,0,0,ya,ca,stride*h*2,w,h,stride,h,0,0,0,0,0,0))
    m.mu.mem_write(PICS,b''.join(desc));m.mu.mem_write(CFG+0x34,struct.pack('<I',COMMON[0]))
    u=m.mu;u.reg_write(r.UC_ARM_REG_R0,RAM);u.reg_write(r.UC_ARM_REG_R1,ARGS)
    u.reg_write(r.UC_ARM_REG_SP,STACK);u.reg_write(r.UC_ARM_REG_LR,STOP)
    u.emu_start(m.s['tri_hook_jpeg'],m.s['store_plane'],count=1000000)
    assert u.reg_read(r.UC_ARM_REG_PC)==m.s['store_plane']
    assert m.allocs==[524,3057600],m.allocs
    for ptr,(start,n,size) in m.live.items():
        assert bytes(u.mem_read(start,64))==b'\xa7'*64
        assert bytes(u.mem_read(ptr+n,start+size-ptr-n))==b'\xa7'*(start+size-ptr-n)
    checks.append(dict(case='6000x4000_stride6144_preflight',allocations=m.allocs,
        persistent_adapter_bytes=524,reduced_R_G_bytes=3045600,row_scratch_bytes=12000,
        peak_owned_requested_bytes=sum(m.allocs),stopped_before_pixel_extraction=True))
    report=dict(checks=checks,adapter_bytes=Camera(mod).run('tri_camera_state_bytes'),
                hook_gpr_flags_fp_sp_preserved=True,heap_guards_checked=True,native_module_sha256=mod['sha256'],
                capture_adapter_verified_in_emulation=True,hardware_tested=False,
                limits='Own control logic plus synthetic exposure/JPEG records. Actual BeforeExpose→JPEG record identity remains a manual camera test; mismatches fail closed.')
    (OUT/'native-adapter-verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
