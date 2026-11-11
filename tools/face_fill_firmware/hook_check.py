"""Execute the actual candidate JPEG/capture wrapper chains under Unicorn.

Only cache, allocation, platform/time and external device-read boundaries are
stubbed. The native picture modules and original entry handover execute.
"""
from __future__ import annotations
import argparse,hashlib,json,struct,sys
from pathlib import Path
import numpy as np
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn import arm_const as reg
from check import ref
ROOT=Path(__file__).resolve().parents[2]
BASE=0x53000000;CTX=0x60000000;CFG=CTX+0x1000;DESC=CTX+0x2000;ARG=CTX+0x3000
REC=0x61000000;YP=0x62001000;CP=0x66001000;STACK=0x700ff000;STOP=0x71000000
EXECUTE=0x535047d4;CAPTURE=0x5345133c


def machine(blob):
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    for at,size in [(BASE,(len(blob)+4095)&~4095),(0x55000000,0x100000),(0x55800000,0x100000),
                    (CTX,0x20000),(REC,0x80000),(YP,0x1800000),(CP,0x1800000),
                    (STACK-0xff000,0x100000),(STOP,4096)]:u.mem_map(at,size)
    u.mem_write(BASE,blob);src,dst,size=struct.unpack_from('<3I',blob,0x450)
    assert(src,dst,size)==(0x5407b540,0x55000000,0x3a080)
    u.mem_write(dst,blob[src-BASE:src-BASE+size]);u.reg_write(reg.UC_ARM_REG_C1_C0_2,0xf00000);u.reg_write(reg.UC_ARM_REG_FPEXC,0x40000000)
    log=[]
    def hook(cpu,at,size,_):
        if at in (0x536bbc30,0x536bbcc0,0x536bbcac,0x536af2a8,0x536af2e4,0x536bd838,0x536b6510,0x53666908):
            log.append(hex(at))
            if at==0x536bbc30:cpu.reg_write(reg.UC_ARM_REG_R0,1)
            elif at==0x536af2a8:cpu.reg_write(reg.UC_ARM_REG_R0,0) # recoverable baseline allocation failure
            elif at==0x536bd838:cpu.reg_write(reg.UC_ARM_REG_R0,CTX+0x9000)
            elif at==0x536b6510:cpu.mem_write(cpu.reg_read(reg.UC_ARM_REG_R1),struct.pack('<H6BH',2026,11,11,12,0,0,0,0))
            cpu.reg_write(reg.UC_ARM_REG_PC,cpu.reg_read(reg.UC_ARM_REG_LR))
    u.hook_add(UC_HOOK_CODE,hook,begin=0x53666000,end=0x536be000)
    return u,log


def jpeg_case(blob,look,count,allocation_failure=False):
    u,log=machine(blob);w,h,stride=6000,4000,6016;total=stride*h
    y=np.full((h,stride),72,np.uint8);c=np.full((h,stride),0xa5,np.uint8)
    c[:,:w:2]=108;c[:,1:w:2]=153
    u.mem_write(YP,y.tobytes());u.mem_write(CP,c.tobytes())
    source=CTX+0x4000;capture_out=CTX+0xc000;frame=CTX+0x10000
    u.mem_write(REC+0x38d6c,b'\x09\0')
    for off,val in [(0x9c8,6000),(0x9cc,4000),(0x266c,1),(0x5270,0)]:u.mem_write(source+off,struct.pack('<I',val))
    u.mem_write(source+0x4620,b'\x09\0')
    if count:u.mem_write(source+0x2900,struct.pack('<5I',1,400,500,1000,1000))
    u.mem_write(source+0x4010,struct.pack('<4I',23552,21626,49152,49152))
    u.mem_write(STACK,struct.pack('<3I',capture_out,0,REC))
    for i,v in enumerate((source,0,0,0)):u.reg_write(getattr(reg,'UC_ARM_REG_R'+str(i)),v)
    u.reg_write(reg.UC_ARM_REG_SP,STACK);u.reg_write(reg.UC_ARM_REG_LR,STOP)
    u.emu_start(CAPTURE,STOP,count=100000)
    assert u.reg_read(reg.UC_ARM_REG_PC)==STOP and struct.unpack('<H',u.mem_read(REC+0x38d6c,2))[0]==count
    rect=struct.unpack('<4I',u.mem_read(REC+0x38ff0,16));assert rect==(100,100,48,44),rect
    u.mem_write(REC+0x77c,bytes([look]))
    # Build and select the real JPEG config from this frame's owned Common.
    u.mem_write(frame+0x44c8,struct.pack('<I',REC));u.mem_write(frame+0x5c,struct.pack('<I',CTX+0xd000))
    u.mem_write(frame+0xb0,struct.pack('<B3xIII8H',1,YP,CP,0,w,h,stride,h,0,0,0,0))
    def call(at):
        u.reg_write(reg.UC_ARM_REG_R0,frame);u.reg_write(reg.UC_ARM_REG_R1,6)
        u.reg_write(reg.UC_ARM_REG_SP,STACK);u.reg_write(reg.UC_ARM_REG_LR,STOP);u.emu_start(at,STOP,count=10000)
        assert u.reg_read(reg.UC_ARM_REG_PC)==STOP
    call(0x5350e624);call(0x5350e114);cfg=u.reg_read(reg.UC_ARM_REG_R0)
    assert cfg==frame+0x9b8 and struct.unpack('<I',u.mem_read(cfg+0x34,4))[0]==REC
    argument=frame+0x440;u.mem_write(argument+8,struct.pack('<I',cfg));log.clear()
    stash=0x10000|32|(1<<19 if allocation_failure else 0);u.mem_write(0x55804378,struct.pack('<I',stash))
    values=[CTX+0x4000+i*64 for i in range(13)];values[1]=argument
    for i,value in enumerate(values):u.reg_write(getattr(reg,'UC_ARM_REG_R'+str(i)),value)
    cpsr=0xa8000013;u.reg_write(reg.UC_ARM_REG_CPSR,cpsr);u.reg_write(reg.UC_ARM_REG_SP,STACK);u.reg_write(reg.UC_ARM_REG_LR,STOP)
    u.emu_start(EXECUTE,EXECUTE+4,count=100_000_000)
    assert u.reg_read(reg.UC_ARM_REG_PC)==EXECUTE+4
    assert [u.reg_read(getattr(reg,'UC_ARM_REG_R'+str(i))) for i in range(12)]==values[:12]
    assert u.reg_read(reg.UC_ARM_REG_R12)==STACK and u.reg_read(reg.UC_ARM_REG_SP)==STACK and u.reg_read(reg.UC_ARM_REG_LR)==STOP
    # Existing baseline wrappers do not promise flags; new wrapper is separately
    # stopped at its baseline tail below to test its exact preservation.
    oy=bytes(u.mem_read(YP,total));oc=bytes(u.mem_read(CP,total))
    expected_y=y.copy();expected_c=c.copy()
    if count and 64<=look<84:
        # Local crop has identical absolute ellipse geometry, avoids a 24M-pixel
        # scalar reference while full native descriptors/buffers remain real.
        small_y=y[96:148,96:152].copy();small_c=c[96:148,96:152].copy()
        a,b=ref(small_y.tobytes(),small_c.tobytes(),56,52,56,[(4,4,48,44)],56,52,look in (65,68,74,76))
        expected_y[96:148,96:152]=np.frombuffer(a,np.uint8).reshape(52,56)
        expected_c[96:148,96:152]=np.frombuffer(b,np.uint8).reshape(52,56)
    assert oy==expected_y.tobytes() and oc==expected_c.tobytes(),(look,count,log)
    return {'look':look,'current_faces':count,'allocation_failure':allocation_failure,'exact_pixels':True,
            'actual_capture_and_config_builder_executed':True,'registers_stack_handover':True,'boundary_calls':log}


def wrapper_flags(blob,report):
    u,_=machine(blob);tail=int(report['appended']['chain_tail'],16)
    # Empty config is a strict no-op; inspect directly before baseline wrappers.
    u.mem_write(ARG+8,struct.pack('<I',CFG));values=[0x12340000+i for i in range(13)];values[1]=ARG
    for i,v in enumerate(values):u.reg_write(getattr(reg,'UC_ARM_REG_R'+str(i)),v)
    u.reg_write(reg.UC_ARM_REG_SP,STACK);u.reg_write(reg.UC_ARM_REG_LR,STOP);u.reg_write(reg.UC_ARM_REG_CPSR,0xf8000013)
    u.emu_start(EXECUTE,tail,count=100000)
    assert [u.reg_read(getattr(reg,'UC_ARM_REG_R'+str(i))) for i in range(13)]==values
    assert u.reg_read(reg.UC_ARM_REG_CPSR)==0xf8000013 and u.reg_read(reg.UC_ARM_REG_SP)==STACK and u.reg_read(reg.UC_ARM_REG_LR)==STOP
    # Clear wrapper handover into displaced prologue, preserving original args.
    u.mem_write(STACK+8,struct.pack('<I',REC));u.mem_write(REC+0x38d6c,b'\x09\x00')
    for i,v in enumerate(values):u.reg_write(getattr(reg,'UC_ARM_REG_R'+str(i)),v)
    u.reg_write(reg.UC_ARM_REG_SP,STACK);u.reg_write(reg.UC_ARM_REG_LR,STOP);u.reg_write(reg.UC_ARM_REG_CPSR,0xf8000013)
    u.emu_start(CAPTURE,CAPTURE+4,count=100000)
    assert bytes(u.mem_read(REC+0x38d6c,2))==b'\x00\x00'
    assert [u.reg_read(getattr(reg,'UC_ARM_REG_R'+str(i))) for i in range(12)]==values[:12]
    assert u.reg_read(reg.UC_ARM_REG_R12)==STACK and u.reg_read(reg.UC_ARM_REG_SP)==STACK and u.reg_read(reg.UC_ARM_REG_LR)==STOP and u.reg_read(reg.UC_ARM_REG_CPSR)==0xf8000013
    return {'jpeg_volatile_registers_and_flags':True,'capture_clear_and_native_handover':True}


def skipped_capture(blob):
    u,_=machine(blob);source=CTX+0x4000
    u.mem_write(REC+0x38d6c,b'\x09\0');before=bytearray(u.mem_read(REC,0x80000))
    u.mem_write(STACK,struct.pack('<3I',0,0,REC))
    for i,v in enumerate((source,0,0,0)):u.reg_write(getattr(reg,'UC_ARM_REG_R'+str(i)),v)
    u.reg_write(reg.UC_ARM_REG_SP,STACK);u.reg_write(reg.UC_ARM_REG_LR,STOP)
    u.emu_start(CAPTURE,STOP,count=100000)
    assert u.reg_read(reg.UC_ARM_REG_PC)==STOP and u.reg_read(reg.UC_ARM_REG_SP)==STACK
    before[0x38d6c:0x38d6e]=bytes(2)
    assert bytes(u.mem_read(REC,0x80000))==bytes(before)
    return {'null_result_branch_cannot_reuse_stale_B':True,'only_B_count_changed':True}


def main():
    p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,default=ROOT/'scratch/face-fill-firmware');a=p.parse_args()
    report=json.loads((a.directory/'build-report.json').read_text(encoding='utf-8'));blob=(a.directory/'candidate-rtos.bin').read_bytes()
    assert hashlib.sha256((a.directory/'fwdc239b.bin').read_bytes()).hexdigest()==report['candidate_sha256']
    result={'candidate_sha256':report['candidate_sha256'],'rtos_sha256':hashlib.sha256(blob).hexdigest(),
            'wrappers':wrapper_flags(blob,report),'skipped_capture':skipped_capture(blob),
            'cases':[jpeg_case(blob,*args) for args in [(64,1),(65,1),(64,0),(11,1),(64,1,True)]],
            'scope':'Actual wrappers and baseline picture chain, synthetic input, JPEG encoder/ISP/hardware not emulated'}
    (a.directory/'hook-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
