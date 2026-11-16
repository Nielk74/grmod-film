"""Compile the real clock adapter and exercise original GR III clock/UI code.

The exact firmware image is hash-guarded and mapped read/execute. Only the OS
clock service is simulated. No camera, firmware boot or hardware clock is used.
"""
import argparse
import hashlib
import json
import shutil
import struct
import subprocess
from pathlib import Path

from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_PROT_READ, UC_PROT_EXEC
from unicorn import arm_const as R

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OUT=HERE.parent/'out'/'firmware-lifecycle'
FIRMWARE=ROOT/'scratch'/'video-firmware-high-rate-2026-11-01'/'original-rtos.bin'
SHA='8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67'
BASE=0x53000000
NATIVE_CLOCK=0x536afc5c
OS_CLOCK=0x53050b7c
STACK=0x610ff000
STOP=0x620ff000
OUTPUT=0x62010008
VIEW=0x62020000


class ClockFixture:
    def __init__(self,firmware,elf_path):
        data=firmware.read_bytes()
        if hashlib.sha256(data).hexdigest()!=SHA:
            raise ValueError('Exact GR III 2.10 RTOS identity guard failed')
        assert data[NATIVE_CLOCK-BASE:NATIVE_CLOCK-BASE+16].hex()=='0dc0a0e130d82de97c4705e3054445e3'
        self.cpu=Uc(UC_ARCH_ARM,UC_MODE_ARM)
        c=self.cpu
        image_size=(len(data)+4095)&~4095
        c.mem_map(BASE,image_size)
        c.mem_write(BASE,data)
        c.mem_protect(BASE,image_size,UC_PROT_READ|UC_PROT_EXEC)
        c.mem_map(0x55000000,0x400000)
        src,dst,size=struct.unpack_from('<3I',data,0x450)
        assert (src,dst,size)==(0x5407b540,0x55000000,0x3a080)
        c.mem_write(dst,data[src-BASE:src-BASE+size])
        c.mem_map(0x61000000,0x100000)
        c.mem_map(0x62000000,0x100000)
        c.mem_map(0x10000,0x1000)
        c.mem_map(0x10000000,0x100000)
        with elf_path.open('rb') as stream:
            elf=ELFFile(stream)
            undefined=[s.name for s in elf.get_section_by_name('.symtab').iter_symbols()
                       if s.name and s['st_shndx']=='SHN_UNDEF']
            assert not undefined,undefined
            self.symbols={s.name:s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()}
            for segment in elf.iter_segments():
                if segment['p_type']=='PT_LOAD':c.mem_write(segment['p_vaddr'],segment.data())
        c.reg_write(R.UC_ARM_REG_C1_C0_2,0xf00000)
        c.reg_write(R.UC_ARM_REG_FPEXC,0x40000000)
        self.sample=0
        self.error=0
        self.os_calls=[]
        self.native_calls=[]
        self.stop_at=set()
        c.hook_add(UC_HOOK_CODE,self.hook)

    def hook(self,c,address,size,user):
        if address in self.stop_at:
            c.emu_stop()
        elif address==NATIVE_CLOCK:
            self.native_calls.append({'output':hex(c.reg_read(R.UC_ARM_REG_R0))})
        elif address==OS_CLOCK:
            output=c.reg_read(R.UC_ARM_REG_R0)
            # Deliberately write on errors too: neither native nor adapter may
            # expose this invalid result to its caller after a failed service.
            c.mem_write(output,struct.pack('<II',(self.sample>>32)&0xffffffff,self.sample&0xffffffff))
            self.os_calls.append({'sample_ms':self.sample,'result':self.error,'output':hex(output),
                                  'OS_word_order':['high32','low32']})
            c.reg_write(R.UC_ARM_REG_R0,self.error&0xffffffff)
            c.reg_write(R.UC_ARM_REG_PC,c.reg_read(R.UC_ARM_REG_LR))
        elif address==0x53820074:
            raise AssertionError('Native stack-canary failure')

    def prepare(self):
        c=self.cpu
        for i in range(13):c.reg_write(getattr(R,'UC_ARM_REG_R'+str(i)),0)
        c.reg_write(R.UC_ARM_REG_CPSR,0x13)
        c.reg_write(R.UC_ARM_REG_SP,STACK)
        c.reg_write(R.UC_ARM_REG_LR,STOP)
        c.mem_write(STACK-0x2000,bytes(0x3000))
        self.stop_at=set()

    def call(self,address,*args):
        self.prepare()
        c=self.cpu
        saved={getattr(R,'UC_ARM_REG_R'+str(i)):0x12340000+i for i in range(4,12)}
        for register,value in saved.items():c.reg_write(register,value)
        for i,value in enumerate(args):c.reg_write(getattr(R,'UC_ARM_REG_R'+str(i)),value)
        c.emu_start(address,STOP,count=100000)
        assert c.reg_read(R.UC_ARM_REG_PC)==STOP,'Instruction limit exhausted'
        assert c.reg_read(R.UC_ARM_REG_SP)==STACK,'AAPCS stack mismatch'
        assert all(c.reg_read(register)==value for register,value in saved.items()),'AAPCS register mismatch'
        return c.reg_read(R.UC_ARM_REG_R0)

    def read(self,value):
        self.sample=value
        self.cpu.mem_write(OUTPUT-8,b'\xa5'*20)
        assert self.call(self.symbols['grmod_clock_ms'],OUTPUT)==1
        assert bytes(self.cpu.mem_read(OUTPUT-8,8))==b'\xa5'*8
        assert bytes(self.cpu.mem_read(OUTPUT+4,8))==b'\xa5'*8
        actual=struct.unpack('<I',self.cpu.mem_read(OUTPUT,4))[0]
        assert actual==value&0xffffffff,(value,actual)
        return actual

    def blink(self,value):
        # Execute the original LiveView remainder/comparison instructions and
        # original 64-bit divide helper, stopping before the next UI draw call.
        self.prepare()
        c=self.cpu
        c.reg_write(R.UC_ARM_REG_R0,value&0xffffffff)
        c.reg_write(R.UC_ARM_REG_R1,(value>>32)&0xffffffff)
        c.reg_write(R.UC_ARM_REG_R4,VIEW)
        c.reg_write(R.UC_ARM_REG_R6,0)
        c.reg_write(R.UC_ARM_REG_R9,0)
        c.emu_start(0x531768b0,0x531768d8,count=100000)
        assert c.reg_read(R.UC_ARM_REG_PC)==0x531768d8
        actual=bytes(c.mem_read(VIEW+0x4de,1))[0]
        assert actual==int(value%1000<=499),(value,actual)
        return actual

    def view_deadline(self,started,now,duration):
        # Execute the original View animation prologue, clock call and low-word
        # subtraction. Skip geometry/easing; execute its original duration test.
        self.prepare()
        c=self.cpu
        self.sample=now
        c.mem_write(VIEW+0x138,struct.pack('<I',started&0xffffffff))
        c.mem_write(VIEW+0xac,struct.pack('<I',duration))
        c.mem_write(VIEW+0x128,b'\x02')
        c.reg_write(R.UC_ARM_REG_R0,VIEW)
        c.emu_start(0x533949b0,0x53394a04,count=100000)
        assert c.reg_read(R.UC_ARM_REG_PC)==0x53394a04
        elapsed=c.reg_read(R.UC_ARM_REG_R7)
        assert elapsed==(now-started)&0xffffffff
        self.stop_at={0x53394ad0,0x53394af0}
        c.emu_start(0x53394abc,STOP,count=100)
        assert c.reg_read(R.UC_ARM_REG_PC) in self.stop_at
        active=bytes(c.mem_read(VIEW+0x128,1))[0]
        assert active==(2 if elapsed<duration else 0),(started,now,duration,elapsed,active)
        return {'started_ms':started,'now_ms':now,'duration_ms':duration,'elapsed_ms':elapsed,'active':active!=0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--firmware',type=Path,default=FIRMWARE)
    parser.add_argument('--clang',default=shutil.which('clang') or r'C:\Program Files\LLVM\bin\clang.exe')
    parser.add_argument('--lld',default=shutil.which('ld.lld') or r'C:\Program Files\LLVM\bin\ld.lld.exe')
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    obj=OUT/'camera_clock.o'
    elf_path=OUT/'camera-clock-tests.elf'
    subprocess.run([args.clang,'-target','armv7-none-eabi','-mcpu=cortex-a9','-marm','-mfloat-abi=soft','-mfpu=none',
        '-Os','-ffreestanding','-fno-builtin','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
        '-fno-stack-protector','-Wall','-Wextra','-Werror','-c',str(HERE/'camera_clock.c'),'-o',str(obj)],check=True)
    subprocess.run([args.lld,'-Ttext=0x10000000','--entry=grmod_clock_ms','--no-undefined',str(obj),'-o',str(elf_path)],check=True)
    p=ClockFixture(args.firmware,elf_path)
    checks=[]
    values=[0,1,8,16,499,500,999,1000,7600,49*86400000,0xffffffff,0x100000000,0x100000010,
            0x7fffffff00112233,0xffffffff00112233]
    for value in values:p.read(value)
    checks.append('Actual compiled ARM adapter calls unchanged native wrapper and returns low32 milliseconds with intact adjacent canaries')
    before=len(p.os_calls)
    assert p.call(p.symbols['grmod_clock_ms'],0)==0 and len(p.os_calls)==before
    checks.append('Null output returns false without invoking native clock')
    for error in (-5,-1,1):
        p.error=error
        p.sample=0x1122334455667788
        p.cpu.mem_write(OUTPUT,b'\xa5'*4)
        assert p.call(p.symbols['grmod_clock_ms'],OUTPUT)==0
        assert bytes(p.cpu.mem_read(OUTPUT,4))==b'\xa5'*4
    p.error=0
    checks.append('OS errors return false and leave output unchanged even when OS writes an invalid sample')
    start=0x100000000-3800
    a=p.read(start)
    before_deadline=p.read(start+7599)
    deadline=p.read(start+7600)
    assert (before_deadline-a)&0xffffffff==7599
    assert (deadline-a)&0xffffffff==7600
    checks.append('Unsigned elapsed time is7599 then7600 across49.7-day low32-millisecond wrap')
    blink_values=[0,1,499,500,999,1000,1499,1500,0x100000010,0xffffffff00112233]
    phases=[{'time_ms':value,'phase':p.blink(value)} for value in blink_values]
    checks.append('Original LiveView64-bit remainder/comparison selects two500ms phases in a1000ms cycle')
    deadlines=[p.view_deadline(1000,1000+elapsed,7600) for elapsed in (0,16,7599,7600,8000)]
    deadlines.extend(p.view_deadline(start,start+elapsed,7600) for elapsed in (0,16,7599,7600,8000))
    checks.append('Original View clock subtraction and duration comparison remain active before7600 and stop at7600, including low-word wrap')
    report={'firmware':str(args.firmware.resolve()),'rtos_sha256':SHA,
            'wrapper_source_sha256':hashlib.sha256((HERE/'camera_clock.c').read_bytes()).hexdigest(),
            'scope':'Compiled ARM adapter and unchanged native clock; injected OS samples. Original LiveView/View instruction paths run in synthetic contexts.',
            'native_clock':hex(NATIVE_CLOCK),'OS_service':hex(OS_CLOCK),'OS_word_order':['high32','low32'],
            'native_uint64_word_order':['low32','high32'],'time_units':'milliseconds, established by native UI callers; no division by1000',
            'checks':checks,'sample_values_ms':values,'blink_phases':phases,'view_deadlines':deadlines,
            'native_clock_calls':len(p.native_calls),'injected_OS_calls':len(p.os_calls),
            'AAPCS_sp_and_callee_saved_registers_checked':True,'undefined_symbols':[],
            'hardware_tested':False,'firmware_modified':False}
    (OUT/'clock-verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
