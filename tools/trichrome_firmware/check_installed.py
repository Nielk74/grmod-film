"""Actual installed candidate entries→prior film/date wrappers→native handover.

Original config builder executes. Device/OS/cache/allocator boundaries only are
substituted; synthetic exposure records establish the test sequence explicitly.
"""
import hashlib
import json
from pathlib import Path
import struct
import numpy as np
from unicorn import UC_HOOK_CODE
from unicorn import arm_const as r
from check import reference, RAM, PICS, STACK, STOP
from check_camera import Camera, COMMON, CFG, ARGS, COMMAND, OUT, PRIOR


def main():
    report=json.loads((OUT/'build-report.json').read_text(encoding='utf-8'))
    assert hashlib.sha256((OUT/'fwdc239b.bin').read_bytes()).hexdigest()==report['sha256']
    blob=(OUT/'candidate-rtos.bin').read_bytes();mod=report['module'];checks=[]
    # Camera supplies guarded heap/buffers and native ABI boundary substitutes.
    # Its dummy test module is also mapped, but no candidate entry points to it.
    dummy=json.loads((OUT/'adapter-test/link.json').read_text(encoding='utf-8'))
    rng=np.random.default_rng(935)
    still=[(rng.integers(24,220,(h,w),dtype=np.uint8),np.full((h,w),128,np.uint8)) for w,h in [(192,128),(64,48),(32,24)]]
    for moving in [False,True]:
        m=Camera(dummy);u=m.mu
        u.mem_unmap(0x536af000,0x1000);u.mem_unmap(0x536bb000,0x1000)
        u.mem_map(0x53000000,(len(blob)+4095)&~4095);u.mem_write(0x53000000,blob)
        for at,n in [(0x55000000,0x100000),(0x55345000,0x1000)]:u.mem_map(at,n)
        src,dst,size=struct.unpack_from('<3I',blob,0x450)
        assert (src,dst,size)==(0x5407b540,0x55000000,0x3a080)
        u.mem_write(dst,blob[src-0x53000000:src-0x53000000+size])
        boundaries=[]
        def boundary(cpu,at,size,ud):
            if at==0x536bd838:cpu.reg_write(r.UC_ARM_REG_R0,RAM+0xe000)
            elif at==0x536b6510:cpu.mem_write(cpu.reg_read(r.UC_ARM_REG_R1),struct.pack('<H6BH',2026,11,11,12,0,0,0,0))
            else:return
            boundaries.append(hex(at));cpu.reg_write(r.UC_ARM_REG_PC,cpu.reg_read(r.UC_ARM_REG_LR))
        u.hook_add(UC_HOOK_CODE,boundary,begin=0x536b6000,end=0x536be000)
        visited=[]
        watched={0x5342c964,0x534322d8,0x535047d4,report['priorExpose'],report['priorJpeg'],mod['symbols']['tri_camera_arm'],mod['symbols']['tri_camera_expose'],mod['symbols']['tri_camera_jpeg']}
        def visits(cpu,at,size,ud):
            if at in watched:visited.append(hex(at))
        u.hook_add(UC_HOOK_CODE,visits,begin=0x53000000,end=0x55000000)
        def run(at,end,*args):
            values=[0x12340000+i for i in range(13)]
            for i,v in enumerate(args):values[i]=v
            for i,v in enumerate(values):u.reg_write(getattr(r,f'UC_ARM_REG_R{i}'),v)
            u.reg_write(r.UC_ARM_REG_SP,STACK);u.reg_write(r.UC_ARM_REG_LR,STOP)
            u.emu_start(at,end,count=50_000_000)
            assert u.reg_read(r.UC_ARM_REG_PC)==end,(hex(at),hex(u.reg_read(r.UC_ARM_REG_PC)))
            assert u.reg_read(r.UC_ARM_REG_SP)==STACK
            if end!=STOP:
                assert [u.reg_read(getattr(r,f'UC_ARM_REG_R{i}')) for i in range(12)]==values[:12]
                assert u.reg_read(r.UC_ARM_REG_R12)==STACK and u.reg_read(r.UC_ARM_REG_LR)==STOP
        run(0x5342c964,0x5342c968,RAM,COMMAND)
        frames=[]
        for shot in range(3):
            images=[(y.copy(),c.copy()) for y,c in still]
            if moving:
                for y,c in images:y[8:20,4+shot*8:12+shot*8]=230
            frames.append(images);m.pictures(images)
            run(0x534322d8,0x534322dc,RAM,0,COMMON[shot])
            # Real frame Common→JPEG config builder/selector. Copy picture
            # descriptors into their actual frame fields before macroID6 build.
            frame=RAM+0x200000
            u.mem_write(frame+0x44c8,struct.pack('<I',COMMON[shot]));u.mem_write(frame+0x5c,struct.pack('<I',RAM+0x2a0000))
            for i in range(3):u.mem_write(frame+0xb0+i*32,bytes(u.mem_read(PICS+i*32,32)))
            run(0x5350e624,STOP,frame,6);run(0x5350e114,STOP,frame,6)
            config=u.reg_read(r.UC_ARM_REG_R0);assert config==frame+0x9b8
            assert struct.unpack('<I',u.mem_read(config+0x34,4))[0]==COMMON[shot]
            u.mem_write(ARGS+8,struct.pack('<I',config))
            u.mem_write(0x55804378,struct.pack('<I',0x10000|32)) # Grain/Halation amounts0.
            run(0x535047d4,0x535047d8,RAM,ARGS)
            got=m.read();expected=images if shot<2 else [reference([frames[k][i] for k in range(3)]) for i in range(3)]
            for aa,bb in zip(got,expected):
                for a,b in zip(aa,bb):np.testing.assert_array_equal(a,b)
            m.now+=100
        assert hex(report['priorExpose']) in visited and hex(report['priorJpeg']) in visited
        assert len(m.live)==1
        checks.append(dict(case='moving' if moving else 'static',all3_pictures_exact=True,first2_untouched=True,
            original_config_builder=True,visited=visited,substituted_platform_calls=boundaries,allocations=m.allocs))
    result=dict(candidate_sha256=report['sha256'],rtos_sha256=hashlib.sha256(blob).hexdigest(),checks=checks,
        scope='Actual installed entry branches, own hooks, prior baseline grain/halation/date/orientation chain, original config builder and native+4 handover. Synthetic exposures; encoder/ISP/device execution not emulated.',hardware_tested=False)
    (OUT/'installed-hook-verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
