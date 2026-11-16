"""Compile actual ARM adapter; execute it with original hash-bound firmware.

OS/heap/device boundaries, singleton inputs, and an existing mutex-registry
lookup entry are simulated. Native
View/Canvas tree methods, RGBA copier, AppTimerModel/AlarmTimer wrappers, clock,
MutexLock, WAV parsing/start/cancel/volume bodies execute. This is not a camera,
physical display, DMA/cache or speaker test. No dependency on ignored scripts.
"""
import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import zlib
from pathlib import Path
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_PROT_EXEC, UC_PROT_READ
from unicorn import arm_const as R

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
STACK, STOP = 0x610ff000, 0x620ff000

SHA = '8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67'
ANCHOR, LATCH, MODEL, APP = 0x55804374, 0x55804378, 0x55063edc, 0x550645f0
POINTERS, SLOTS, ALARMS = 0x62010000, 0x62011000, 0x62012000
LV, QV, OTHER, SERVICE, DRIVER = 0x62020000, 0x62021000, 0x62022000, 0x62023000, 0x62024000
USERDATA, RECORD, CONTEXT, SURFACE, EVENT = 0x62025000, 0x62026000, 0x62028000, 0x62029000, 0x6202a000
REQUEST, DEST = 0x6202b000, 0x63000000
RUNTIME, REGISTRY_NODE, REGISTRY_ENTRY = 0x6202f000, 0x6202f200, 0x6202f210
DRIVERS = {0x53714330:'channel', 0x537144d4:'disable', 0x537144e0:'supply',
           0x53714d60:'start', 0x53714510:'enable', 0x5371451c:'stop',
           0x5371457c:'flush', 0x5371485c:'volume'}

def asset():
    colors = bytes([0,0,0,0,235,173,67,255])
    indices = bytes([1]) * (12*128*128)
    tracks = bytearray()
    for sequence in range(3):
        for frame in range(228):
            s = bytearray(52)
            struct.pack_into('<HBB6i4h4I', s, 0, frame%12, 255, 0,
                             65536,0,0,65536,0,0, 0,0,128,128, 0,4,0,4)
            tracks += s
    body = colors + indices + tracks + bytes(4)
    header = bytearray(80)
    struct.pack_into('<4s12H13I', header, 0, b'TRM2', 2,80,240,176,128,128,12,2,30,3,228,52,
                     7600,1400,5000,1200,80,88,88+len(indices),88+len(indices)+len(tracks),
                     80+len(body),zlib.crc32(body),0,0,0)
    return bytes(header) + body

def build(args, out):
    assert (HERE/'camera_gr3.c').exists(), 'Adapter missing: a shot cannot attach an owned View'
    out.mkdir(parents=True, exist_ok=True)
    (out/'fixture.trm').write_bytes(asset())
    data_bytes = 48000*4*7600//1000
    wave = struct.pack('<4sI4s4sIHHIIHH4sI', b'RIFF',36+data_bytes,b'WAVE',b'fmt ',16,
                       1,2,48000,192000,4,16,b'data',data_bytes) + bytes(data_bytes)
    (out/'fixture.wav').write_bytes(wave)
    assembly = ['.section .rodata.assets,"a",%progbits', '.balign 4']
    for name, filename in [('terminal_asset','fixture.trm')] + [('terminal_wav_'+n,'fixture.wav') for n in ('dash','portal','rocket')]:
        assembly += [f'.global {name}_start, {name}_end',f'{name}_start:',
                     '.incbin "'+(out/filename).as_posix()+'"', f'{name}_end:', '.balign 4']
    (out/'fixture-assets.S').write_text('\n'.join(assembly)+'\n', encoding='utf-8', newline='\n')
    objects=[]
    for source in [HERE/'terminal.c', HERE/'camera_clock.c', HERE/'camera_gr3.c', out/'fixture-assets.S']:
        obj=out/(source.stem+'.o')
        subprocess.run([args.clang,'-target','armv7-none-eabi','-mcpu=cortex-a9','-marm',
            '-mfloat-abi=soft','-mfpu=none','-Os','-ffreestanding','-fno-builtin',
            '-fno-unwind-tables','-fno-asynchronous-unwind-tables','-fno-stack-protector',
            '-Wall','-Wextra','-Werror','-c',str(source),'-o',str(obj)],check=True)
        objects.append(str(obj))
    elf_path=out/'adapter-tests.elf'
    subprocess.run([args.lld,'-Ttext=0x10000000','--entry=grmod_on_shot','--no-undefined',
                    '--defsym=grmod_adapter_state=0x55804374',
                    '--defsym=grmod_audio_shutdown_latch=0x55804378',*objects,'-o',str(elf_path)],check=True)
    return read_elf(elf_path)

def read_elf(elf_path):
    with elf_path.open('rb') as stream:
        elf=ELFFile(stream)
        segments=[(s['p_vaddr'],s.data(),s['p_memsz'],s['p_flags']) for s in elf.iter_segments() if s['p_type']=='PT_LOAD']
        symbols={s.name:s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()}
        assert all(not(flags&2) or not(size) for _,_,size,flags in segments), 'Mutable payload section must live in native heap'
    return segments,symbols

def embedded(segments,symbols,name):
    start,end=symbols[name+'_start'],symbols[name+'_end']
    assert 0<end-start<8*1024*1024,(name,'invalid embedded extent')
    result=bytearray(end-start);covered=0
    for at,data,_,_ in segments:
        left,right=max(start,at),min(end,at+len(data))
        if right>left:
            result[left-start:right-start]=data[left-at:right-at];covered+=right-left
    assert covered==len(result),(name,'ELF segments do not cover embedded bytes')
    return bytes(result)

class Fixture:
    def __init__(self,data,segments,symbols):
        self.heap=0x59600020
        self.allocations=[]
        self.frees=[]
        self.events=[]
        self.alarms={101+n:False for n in range(10)}
        self.now=1000
        self.clock_ok=True
        self.lock_busy=False
        self.locked=False
        self.task='ui'
        self.mutex_owners={0x1234:None}
        self.next_mutex=0x5678
        self.fail_mutex_create=False
        self.pause_driver=None
        self.pause_gate=False
        self.pause_create=False
        self.paused=None
        self.fail_alloc=False
        self.free_service=False
        self.active=LV
        self.symbols=symbols
        self.uc=Uc(UC_ARCH_ARM,UC_MODE_ARM)
        rom_bytes=(len(data)+4095)&~4095
        self.uc.mem_map(0x53000000,rom_bytes)
        self.uc.mem_write(0x53000000,data)
        self.uc.mem_protect(0x53000000,rom_bytes,UC_PROT_READ|UC_PROT_EXEC)
        src,dst,size=struct.unpack_from('<3I',data,0x450)
        assert (src,dst,size)==(0x5407b540,0x55000000,0x3a080)
        self.uc.mem_map(dst,(size+4095)&~4095)
        self.uc.mem_write(dst,data[src-0x53000000:src-0x53000000+size])
        self.uc.mem_map(0x61000000,0x100000)
        self.uc.mem_map(0x62000000,0x100000)
        self.uc.reg_write(R.UC_ARM_REG_C1_C0_2,0xf00000)
        self.uc.reg_write(R.UC_ARM_REG_FPEXC,0x40000000)
        self.diagnostics,self.stubs=[],[]
        # Hook only substituted boundaries. A global per-instruction Python
        # hook makes CRC/rendering of real megabyte assets needlessly slow.
        boundaries={0x53050c9c,0x53051284,0x536b9f1c,0x536b93d0,0x53050b7c,
                    0x536af2a8,0x536af31c,0x536af2e4,0x536af358,
                    0x5320ad88,0x5320aefc,0x53228a90,0x5320b31c,
                    0x5320804c,0x532081ec,0x53051188,0x530511f4,
                    0x53050d08,0x536a9d1c,0x537143a8,0x536aeeb4,0x536abcdc,
                    0x530503c0,0x536a8014,*DRIVERS}
        for at in boundaries:self.uc.hook_add(UC_HOOK_CODE,self._hook,begin=at,end=at)
        self.uc.mem_map(0x5503b000,0x55805000-0x5503b000)
        self.uc.mem_map(0x59600000,0x800000)
        self.uc.mem_map(DEST,0x200000)
        stock_end=0x53000000+len(data)
        stock_page_end=(stock_end+4095)&~4095
        extra_end=max([stock_page_end]+[at+size for at,_,size,_ in segments if at>=0x53000000])
        assert extra_end<=0x55000000,'Payload overlaps native initialized RAM'
        extra_page_end=(extra_end+4095)&~4095
        if extra_page_end>stock_page_end:self.uc.mem_map(stock_page_end,extra_page_end-stock_page_end)
        if any(0x10000000<=at<0x11000000 for at,_,_,_ in segments):self.uc.mem_map(0x10000000,0x1000000)
        if any(at==0x10000 for at,_,_,_ in segments):self.uc.mem_map(0x10000,0x1000)
        for at,content,_,_ in segments:
            # A linker's ELF header LOAD can begin before the appended text.
            # Preserve every stock byte; only load its suffix beyond stock_end.
            skip=max(0,stock_end-at) if at>=0x53000000 else 0
            if skip<len(content):self.uc.mem_write(at+skip,content[skip:])
        if any(0x10000000<=at<0x11000000 for at,_,_,_ in segments):
            self.uc.mem_protect(0x10000000,0x1000000,UC_PROT_READ|UC_PROT_EXEC)
        if extra_page_end>stock_page_end:self.uc.mem_protect(stock_page_end,extra_page_end-stock_page_end,UC_PROT_READ|UC_PROT_EXEC)
        assert hashlib.sha256(self.uc.mem_read(0x53000000,len(data))).hexdigest()==SHA, 'ELF loader changed original firmware bytes'
        assert symbols['grmod_adapter_state']==ANCHOR
        assert symbols['grmod_audio_shutdown_latch']==LATCH
        for at,value in [(0x5536c880,0x6202f000),(0x5536d07c,1),(0x5536d078,0x53d624d8),
                         (0x5536d070,1),(0x5536d074,0x53d62268),
                         (0x5536c7a4,1),(0x550645ac,1),(0x55348b28,1),(0x55348b24,SERVICE),
                         (MODEL,0x53b4df78),(MODEL+0x24,0x53b4df94),(MODEL+0x28,0x53b4dfa8),
                         (MODEL+0x3c,POINTERS),(MODEL+0x40,POINTERS+40),(MODEL+0x44,POINTERS+40),
                         (MODEL+0x50,1),(LV,0x53b2f9e8),(QV,0x53b41380),(OTHER,0x53b2dead),
                         (SERVICE,0x53d1b7b8),(SERVICE+0xbc,DRIVER),(SERVICE+0x108,0x1234),
                         (USERDATA+4,RECORD),(SURFACE+8,DEST+32)]:self.put(at,value)
        self.uc.mem_write(SERVICE+0x35,bytes([1,1,1,0]))
        self.put(RUNTIME+4,256)
        self.put(REGISTRY_NODE,REGISTRY_ENTRY)
        self.uc.mem_write(RECORD+0x98b,b'\x07')
        self.uc.mem_write(SURFACE+2,b'\x05')
        self.uc.mem_write(SURFACE+0x18,struct.pack('<4H',736,480,720,480))
        self.uc.mem_write(DEST,b'\xa5'*(736*480*4+64))
        self.uc.mem_write(EVENT,struct.pack('<H2xII',0x199,0,MODEL+0x28))
        # The native service destructor traverses its empty list sentinels.
        # Construct them through the same native constructors as AudioService.
        for offset in (0x3c,0x4c,0x5c):self.call(0x536b539c,SERVICE+offset,0)
        for n in range(10):
            slot,alarm=SLOTS+n*0x20,ALARMS+n*0x20
            for at,value in [(POINTERS+n*4,slot),(slot,alarm),(alarm,0x53b4db38),
                             (alarm+4,101+n),(alarm+8,0x53b20f0c),(alarm+0x10,MODEL+0x24)]:self.put(at,value)
        self.roots=[]
        for controller in (LV,QV):
            self.uc.mem_write(REQUEST,struct.pack('<6I',1,0,0,720,480,0))
            root=self.call(0x533ad7f0,REQUEST)
            self.roots.append(root)
            self.put(controller+0x15c,root)
            self.put(controller+4,root)
            self.uc.mem_write(controller+0xc,bytes(self.uc.mem_read(SURFACE,0x28)))
            self.call(0x53391a30,root,controller+0xc)

    def put(self,at,value):self.uc.mem_write(at,struct.pack('<I',value&0xffffffff))
    def get(self,at):return struct.unpack('<I',self.uc.mem_read(at,4))[0]
    def r(self,n):return self.uc.reg_read(getattr(R,'UC_ARM_REG_R'+str(n)))
    def ret(self,value=0):
        self.uc.reg_write(R.UC_ARM_REG_R0,value&0xffffffff)
        self.uc.reg_write(R.UC_ARM_REG_PC,self.uc.reg_read(R.UC_ARM_REG_LR))

    def _hook(self,cpu,at,size,user):
        if at==0x530503c0:
            if self.pause_create:
                self.pause_create=False;self.paused=('during_gate_creation',self.task)
                cpu.emu_stop();return
            args=struct.unpack('<6I',cpu.mem_read(self.r(0),24))
            assert args[1:]==(2,0x8c,0,0,0),args
            assert self.get(ANCHOR)==0,'State published before its private gate initialized'
            handle=0xffce0000 if self.fail_mutex_create else self.next_mutex
            self.events.append(('mutex_create',args,handle))
            if not self.fail_mutex_create:
                self.mutex_owners[handle]=None;self.next_mutex+=1
            self.ret(handle)
        elif at==0x536a8014:
            if self.r(0)==RUNTIME:self.ret(REGISTRY_NODE)
            # Other callers retain the original registry/container body.
        elif at==0x53050c9c:
            assert self.r(1) in (0,0xffffffff)
            handle,timeout=self.r(0),self.r(1)
            assert handle in self.mutex_owners,('Unknown mutex handle',hex(handle))
            if self.pause_gate and handle!=0x1234 and not timeout:
                self.pause_gate=False;self.paused=('before_private_lock',self.task,handle)
                cpu.emu_stop();return
            busy=(handle==0x1234 and self.lock_busy) or self.mutex_owners[handle] is not None
            self.events.append(('lock',timeout,not busy,handle,self.task))
            if busy and timeout==0xffffffff and handle!=0x1234:
                self.paused=('blocking_private_wait',self.task,handle)
                cpu.emu_stop() # Suspended OS wait: resume this actual CPU context later.
            elif busy:self.ret(0xffce0000)
            else:
                self.mutex_owners[handle]=self.task
                if handle==0x1234:self.locked=True
                self.ret(0)
        elif at==0x53051284:
            handle=self.r(0);assert self.mutex_owners.get(handle)==self.task
            self.mutex_owners[handle]=None
            if handle==0x1234:self.locked=False
            self.events.append(('unlock',handle,self.task))
            self.ret(0)
        elif at in (0x536b9f1c,0x536b93d0):
            if not self.r(0) and self.fail_mutex_create and self.r(3)==0xc8:
                self.events.append(('expected_create_failure_diagnostic',))
                self.ret(0);return
            assert self.r(0),'Native diagnostic failure at '+hex(self.r(3))
            self.ret(0)
        elif at==0x53050b7c:
            if self.clock_ok:cpu.mem_write(self.r(0),struct.pack('<2I',0,self.now&0xffffffff))
            self.ret(0 if self.clock_ok else 0xffce0000)
        elif at in (0x536af2a8,0x536af31c):
            size=self.r(0)
            if self.fail_alloc:self.ret(0);return
            assert 0<size<0x100000
            ptr=self.heap;self.heap=(ptr+size+95)&~31
            assert self.heap<0x59e00000
            cpu.mem_write(ptr-32,b'\xa5'*(size+64))
            self.allocations.append((ptr,size));self.ret(ptr)
        elif at in (0x536af2e4,0x536af358):
            freed=self.r(0);self.frees.append(freed);self.ret(0)
            if freed==SERVICE and self.free_service:
                assert self.get(LATCH)==1
                assert all(owner is None for owner in self.mutex_owners.values()),'Native free occurred before module gate drained'
                self.events.append(('service_free',self.task))
                self.uc.mem_unmap(SERVICE&~0xfff,0x1000)
        elif at==0x5320ad88:self.ret(0x6202d000)
        elif at==0x5320aefc:self.ret(APP)
        elif at==0x53228a90:self.ret(self.active)
        elif at==0x5320b31c:self.ret(USERDATA)
        elif at==0x5320804c:self.ret(0x6202e000)
        elif at==0x532081ec:self.ret(CONTEXT)
        elif at in DRIVERS:
            if at==self.pause_driver:
                self.pause_driver=None;self.paused=('inside_audio_driver',self.task,at)
                cpu.emu_stop();return
            assert self.locked,'Audio driver call outside original service mutex'
            self.events.append((DRIVERS[at],self.r(0),self.r(1),self.r(2)))
            self.ret(0)
        elif at==0x53051188:
            self.alarms[self.r(0)]=True
            self.events.append(('timer_start',self.r(1)))
            self.ret(0)
        elif at==0x530511f4:
            self.alarms[self.r(0)]=False;self.ret(0)
        elif at==0x53050d08:
            cpu.mem_write(self.r(1),struct.pack('<3I',0,0,int(self.alarms[self.r(0)])))
            self.ret(0)
        elif at==0x536a9d1c:self.ret(0)
        elif at==0x537143a8:
            assert self.get(LATCH)==1
            self.events.append(('native_shutdown_driver',self.r(0),self.r(1)))
            self.ret(0)
        elif at in (0x536aeeb4,0x536abcdc):
            # Synthetic service has no real OS mutex/thread resources to free.
            # The original AudioService destructor and factory dispatch run.
            self.events.append(('native_shutdown_os_cleanup',hex(at)))
            self.ret(0)
        else:raise AssertionError('Unhandled fixture boundary '+hex(at))

    def call(self,name,*args,task='ui',stack_pointer=STACK,allow_pause=False):
        at=self.symbols[name] if isinstance(name,str) else name
        self.task=task;self.paused=None
        self.diagnostics,self.stubs=[],[]
        for n in range(13):self.uc.reg_write(getattr(R,'UC_ARM_REG_R'+str(n)),0)
        self.uc.reg_write(R.UC_ARM_REG_CPSR,0x13)
        self.uc.reg_write(R.UC_ARM_REG_SP,stack_pointer)
        self.uc.reg_write(R.UC_ARM_REG_LR,STOP)
        self.uc.mem_write(stack_pointer-0x4000,bytes(0x5000))
        saved={getattr(R,'UC_ARM_REG_R'+str(n)):0x12340000+n for n in range(4,12)}
        for register,value in saved.items():self.uc.reg_write(register,value)
        for n,value in enumerate(args[:4]):self.uc.reg_write(getattr(R,'UC_ARM_REG_R'+str(n)),value&0xffffffff)
        for n,value in enumerate(args[4:]):self.put(stack_pointer+n*4,value)
        self.uc.emu_start(at,STOP,timeout=30_000_000,count=1_000_000_000)
        if allow_pause and self.paused:return self.uc.context_save()
        assert self.uc.reg_read(R.UC_ARM_REG_PC)==STOP, ('instruction budget',name,hex(self.uc.reg_read(R.UC_ARM_REG_PC)))
        assert self.uc.reg_read(R.UC_ARM_REG_SP)==stack_pointer
        assert all(self.uc.reg_read(register)==value for register,value in saved.items()),('AAPCS',name)
        assert not self.diagnostics,self.diagnostics
        assert all(owner!=task for owner in self.mutex_owners.values()),('Leaked mutex',name)
        return self.r(0)

    def resume(self,snapshot,task,stack_pointer):
        self.task=task;self.paused=None;self.uc.context_restore(snapshot)
        self.uc.emu_start(self.uc.reg_read(R.UC_ARM_REG_PC),STOP,timeout=30_000_000,count=1_000_000_000)
        assert not self.paused,self.paused
        assert self.uc.reg_read(R.UC_ARM_REG_PC)==STOP
        assert self.uc.reg_read(R.UC_ARM_REG_SP)==stack_pointer
        assert all(self.uc.reg_read(getattr(R,'UC_ARM_REG_R'+str(n)))==0x12340000+n for n in range(4,12))
        assert all(owner!=task for owner in self.mutex_owners.values()),('Leaked mutex after resume',task)

    def children(self,root):
        begin,end=self.get(root+0xc),self.get(root+0x10)
        return [self.get(p) for p in range(begin,end,4)] if begin else []
    def timers(self):
        return [(self.get(SLOTS+n*0x20+4),self.get(SLOTS+n*0x20+8)) for n in range(10) if self.get(SLOTS+n*0x20+4)]
    def fire(self,delta=33):
        self.now=(self.now+delta)&0xffffffff
        for handle in self.alarms:self.alarms[handle]=False
        self.call(0x53228ab4,APP,EVENT)
    def canaries(self):
        for ptr,size in self.allocations:
            assert bytes(self.uc.mem_read(ptr-32,32))==b'\xa5'*32,(hex(ptr),'prefix')
            assert bytes(self.uc.mem_read(ptr+size,32))==b'\xa5'*32,(hex(ptr),'suffix')
        assert bytes(self.uc.mem_read(DEST,32))==b'\xa5'*32
        assert bytes(self.uc.mem_read(DEST+32+736*480*4,32))==b'\xa5'*32

def clipping(p,view,root):
    # Only the adapter's own heap-backed pixels are changed; the original
    # native copier and base Draw execute with a negative origin and clipped
    # source offsets. The expected image includes every row-padding byte.
    state=p.get(ANCHOR)
    size=next(size for at,size in p.allocations if at==state)
    source=state+size-240*176*4
    rgba=b''.join(struct.pack('<I',0xff000000|x|(y<<8)) for y in range(176) for x in range(240))
    p.uc.mem_write(source,rgba)
    p.uc.mem_write(view+0x30,struct.pack('<4i',-17,-23,240,176))
    p.uc.mem_write(view+0x64,struct.pack('<4i',0,0,223,153))
    length=736*480*4
    background=b'\xa5'*length
    p.uc.mem_write(DEST+32,background)
    surface=p.get(root+0xec)
    p.call('grmod_draw',view,surface)
    expected=bytearray(background)
    for y in range(153):
        expected[y*736*4:(y*736+223)*4]=rgba[((y+23)*240+17)*4:((y+23)*240+240)*4]
    assert bytes(p.uc.mem_read(DEST+32,length))==expected,'Native clipped RGBA output differs'
    for case in ('offscreen','format','stride','clip_overflow','hidden'):
        p.uc.mem_write(DEST+32,background)
        p.uc.mem_write(view+0x30,struct.pack('<4i',464,259,240,176))
        p.uc.mem_write(view+0x64,struct.pack('<4i',464,259,240,176))
        p.uc.mem_write(view+0x9e,b'\x01')
        p.uc.mem_write(surface+2,b'\x05')
        p.uc.mem_write(surface+0x18,struct.pack('<H',736))
        if case=='offscreen':p.uc.mem_write(view+0x30,struct.pack('<4i',800,600,240,176))
        elif case=='format':p.uc.mem_write(surface+2,b'\x04')
        elif case=='stride':p.uc.mem_write(surface+0x18,struct.pack('<H',719))
        elif case=='clip_overflow':p.uc.mem_write(view+0x64,struct.pack('<4i',0x7fffffff,259,240,176))
        else:p.uc.mem_write(view+0x9e,b'\0')
        p.uc.mem_write(view+0xa0,b'\x01')
        p.call('grmod_draw',view,surface)
        assert bytes(p.uc.mem_read(DEST+32,length))==background,case
        assert p.uc.mem_read(view+0xa0,1)==b'\0',case
        assert p.uc.mem_read(view+0x40,1)==(b'\0' if case=='hidden' else b'\x01'),case
    p.uc.mem_write(view+0x9e,b'\x01');p.uc.mem_write(surface+2,b'\x05')
    p.uc.mem_write(surface+0x18,struct.pack('<H',736))
    p.call(0x533aca14,root);p.call(0x533ad038,root)
    p.canaries()

def shutdown_trampoline(p):
    # Preserve factory argument; execute actual callback then original factory
    # Shutdown. This is a fixture helper, not a generated firmware patch.
    thunk=0x620e0000
    p.uc.mem_write(thunk,struct.pack('<10I',0xe92d4010,0xe1a04000,0xe59fc010,0xe12fff3c,
        0xe1a00004,0xe59fc008,0xe8bd4010,0xe12fff1c,p.symbols['grmod_before_audio_shutdown'],0x53568d58))
    return thunk

def verify(data,segments,symbols):
    p=Fixture(data,segments,symbols);checks=[]
    p.call('grmod_on_shot')
    root=p.roots[0]
    assert len(p.children(root))==1,'A completed shot must attach one owned native IconView'
    view=p.children(root)[0]
    assert p.get(view+4)==root
    assert len(p.timers())==1,'Animation must own one UI one-shot timer'
    assert p.uc.mem_read(SERVICE+0x35,1)==b'\x05'
    first_wave=p.get(SERVICE+0xf8)
    assert first_wave in [symbols['terminal_wav_'+n+'_start'] for n in ('dash','portal','rocket')]
    assert p.uc.mem_read(0x55018338,1)==b'\x14'
    checks.append('shot creates one persistent native child, starts own WAV at max enum20, arms UI timer')
    for _ in range(2):p.fire(500)
    p.call(0x53391b14,root)
    assert p.uc.mem_read(view+0x40,1)==b'\x01' and p.uc.mem_read(view+0xa0,1)==b'\0'
    visible=bytes(p.uc.mem_read(DEST+32,736*480*4))
    assert any(visible[((259+y)*736+464+x)*4+3] for y in range(176) for x in range(240)), 'Visible elapsed frame must contain nonzero owned pixels'
    p.canaries();checks.append('actual custom Draw and original copier/Canvas rendering preserve canaries and base bookkeeping')
    # Prove dimensions/stride through the original native hardware-descriptor
    # conversion, rather than assuming that fixture-populated fields are ABI.
    p.call(0x536c761c,0x6202c000,p.get(root+0xec))
    assert struct.unpack('<4H',p.uc.mem_read(0x6202c010,8))==(720,480,736,480)
    clipping(p,view,root)
    checks.append('native surface conversion proves size/stride fields; clipped negative origin and five rejected draws retain bounds and always baseDraw')
    p.call('grmod_before_transition',LV,0x08000020)
    assert not p.get(SERVICE+0xf8),'Unsupported transition must cancel owned WAV before old controller exit'
    assert not p.children(root) and not p.timers()
    p.active=OTHER;p.call('grmod_after_transition');p.active=LV
    p.now=1000;p.call('grmod_on_shot');first_wave=p.get(SERVICE+0xf8)
    checks.append('unsupported target ID cancels owned sound before native controller teardown')
    old_timer,listener=p.timers()[0]
    p.call('grmod_timer_expired',listener,old_timer+123)
    assert p.timers()==[(old_timer,listener)]
    checks.append('stale callback ID cannot consume current timer or advance state')
    p.now=4000
    p.call('grmod_before_transition',LV,0x0800000c)
    assert not p.children(root) and not p.timers()
    p.active=QV;p.call('grmod_after_transition')
    assert p.children(p.roots[1])==[view] and p.get(SERVICE+0xf8)==first_wave
    p.now=6000;p.call('grmod_before_transition',QV,0x08000000);p.active=LV;p.call('grmod_after_transition')
    assert p.children(root)==[view] and p.get(SERVICE+0xf8)==first_wave
    p.fire(2599);assert p.children(root)==[view]
    p.fire(1);assert not p.children(root) and not p.timers()
    assert p.get(SERVICE+0xf8)==0 and p.uc.mem_read(0x55018338,1)==b'\x07'
    checks.append('LV/QV transitions reuse child and WAV, preserving full7600ms deadline and restoring user volume')
    p.call('grmod_on_shot');p.lock_busy=True;p.call('grmod_cancel')
    assert not p.children(root) and len(p.timers())==1 and p.get(SERVICE+0xf8)
    p.fire();assert len(p.timers())==1 and p.get(SERVICE+0xf8)
    p.lock_busy=False;p.fire();assert not p.timers() and not p.get(SERVICE+0xf8)
    checks.append('cancel detaches immediately and retries owned WAV stop while try-lock busy')
    p.call('grmod_on_shot');p.put(SERVICE+0xf8,0x62077700);p.uc.mem_write(SERVICE+0x35,b'\x03')
    before=len(p.events);p.call('grmod_cancel')
    assert p.get(SERVICE+0xf8)==0x62077700
    assert not any(e[0] in ('stop','flush','volume') for e in p.events[before:])
    checks.append('ownership loss never stops or changes volume of foreign active audio')
    p.uc.mem_write(SERVICE+0x35,b'\x01');p.put(SERVICE+0xf8,0)
    p.uc.mem_write(RECORD+0x98d,b'\x01');p.call('grmod_on_shot')
    assert p.children(root)==[view] and not p.get(SERVICE+0xf8)
    p.call('grmod_cancel');p.uc.mem_write(RECORD+0x98d,b'\0')
    checks.append('camera mute permits visuals and suppresses custom WAV')
    for _ in range(5):p.call('grmod_on_shot')
    assert p.children(root)==[view] and len(p.timers())==1
    p.call('grmod_before_transition',LV,0x08000020);p.active=OTHER;p.call('grmod_after_transition')
    assert not p.children(root) and not p.timers() and not p.get(SERVICE+0xf8)
    checks.append('repeated shots replace owned playback without duplicate child/timer; unsupported destination cancels')
    p.active=LV;p.call('grmod_on_shot');p.call('grmod_before_canvas_delete',root)
    assert not p.children(root) and not p.timers()
    p.call(0x533918d0,root)
    p.fire();assert not p.timers()
    checks.append('owned Canvas deletion detaches before native destructor; late UI expiry does not use freed root')
    p.canaries()
    q=Fixture(data,segments,symbols);q.clock_ok=False;q.call('grmod_on_shot')
    assert not q.children(q.roots[0]) and not q.timers() and not q.get(SERVICE+0xf8)
    q.clock_ok=True;q.fail_alloc=True;q.call('grmod_on_shot')
    assert q.get(ANCHOR)==0 and not q.timers()
    checks.append('clock and first allocation failures leave no view, timer or audio')
    q.fail_alloc=False;q.lock_busy=True;q.call('grmod_on_shot')
    assert not q.get(SERVICE+0xf8)
    q.lock_busy=False;q.fire(1200)
    assert not q.get(SERVICE+0xf8),'An entrance sound skipped by busy lock must never start late'
    q.call('grmod_cancel')
    checks.append('new sound skips busy service immediately; later frames never start an entrance SFX late')
    q.put(0x55348b28,0);q.call('grmod_on_shot');q.put(0x55348b28,1);q.fire(1200)
    assert not q.get(SERVICE+0xf8),'Unready audio factory must skip new sound'
    q.call('grmod_cancel')
    checks.append('uninitialized audio service suppresses this shot without delayed playback')
    q.call('grmod_on_shot')
    for _ in range(8):
        if q.uc.mem_read(SERVICE+0x35,1)!=b'\x05':break
        q.call(0x53568934,SERVICE,0)
    assert not q.get(SERVICE+0xf8)
    q.fire();assert q.uc.mem_read(0x55018338,1)==b'\x07' and q.children(q.roots[0])
    q.call('grmod_cancel')
    checks.append('original native refill reaches natural completion; next UI tick restores user volume while visuals continue')
    q.now=0xfffffff0;q.call('grmod_on_shot');q.fire(7599)
    assert q.children(q.roots[0]);q.fire(1)
    assert not q.children(q.roots[0]) and not q.timers()
    checks.append('7600ms deadline holds across low32 millisecond wrap')
    q.call('grmod_on_shot');q.uc.mem_write(RECORD+0x98d,b'\x01');q.fire()
    assert not q.get(SERVICE+0xf8) and q.children(q.roots[0])
    q.call('grmod_cancel');q.uc.mem_write(RECORD+0x98d,b'\0')
    checks.append('camera mute changed during owned playback cancels only our audio and preserves visuals')
    q.call('grmod_on_shot');q.lock_busy=True
    q.call('grmod_before_transition',LV,0x08000020);q.active=OTHER;q.call('grmod_after_transition')
    assert q.timers() and q.get(SERVICE+0xf8)
    q.call('grmod_before_audio_shutdown');q.lock_busy=False;q.free_service=True
    q.call(0x53568d58,0x55348b20)
    assert q.get(LATCH)==1 and q.get(0x55348b28)==1 and q.get(0x55348b24)==SERVICE
    assert SERVICE in q.frees
    q.fire();q.call('grmod_cancel');assert not q.timers()
    q.active=LV;q.call('grmod_on_shot');q.fire();q.call('grmod_cancel')
    assert not q.timers()
    checks.append('original factory shutdown dispatches native service shutdown/destructor; latch prevents busy retry or later shots reading dangling unmapped service while C++guard stays1')
    q.canaries()
    r=Fixture(data,segments,symbols);r.call('grmod_before_audio_shutdown')
    assert r.get(LATCH)==1 and r.get(ANCHOR)==0
    r.uc.mem_unmap(SERVICE&~0xfff,0x1000);r.call('grmod_on_shot')
    assert r.children(r.roots[0]) and r.timers();r.call('grmod_cancel');r.canaries()
    checks.append('shutdown before first shot stores latch without allocating and suppresses audio after later state construction')
    m=Fixture(data,segments,symbols)
    mutex,mutex_name=0x62090020,0x62091000
    m.uc.mem_write(mutex-16,b'\xa5'*52);m.uc.mem_write(mutex_name,b'grmod-abi-test\0')
    assert m.call(0x536ae668,mutex)==mutex
    assert m.call(0x536aef0c,mutex,mutex_name,2,0x8c,0,0)==1
    assert m.get(mutex+4)>0 and m.get(mutex+8)==mutex_name
    assert m.get(REGISTRY_ENTRY+8)==mutex
    assert bytes(m.uc.mem_read(mutex-16,16))==bytes(m.uc.mem_read(mutex+20,16))==b'\xa5'*16
    checks.append('original20-byte Mutex ctor and six-argument Initialize execute; OS create receives native parameters and registry retains gate pointer')
    m.fail_mutex_create=True;m.call('grmod_on_shot')
    assert m.children(m.roots[0]) and m.timers() and not m.get(SERVICE+0xf8),'Private gate creation failure must preserve visuals and suppress audio'
    assert any(e[0]=='expected_create_failure_diagnostic' for e in m.events)
    m.call('grmod_cancel');m.canaries()
    checks.append('private mutex creation failure returns0, logs native failure, and fails closed for optional audio with visuals working')
    z=Fixture(data,segments,symbols);z.pause_driver=0x53714d60
    ui=z.call('grmod_on_shot',allow_pause=True)
    assert z.paused and z.paused[0]=='inside_audio_driver' and z.locked
    private=[handle for handle,owner in z.mutex_owners.items() if handle!=0x1234 and owner=='ui']
    assert len(private)==1,'In-flight UI operation must hold persistent module gate as well as native service mutex'
    # Minimal fixture trampoline preserves factory argument and executes our
    # actual callback, then tails the original factory Shutdown. Two saved CPU
    # contexts use separate stacks and share the same RAM/OS mutex state.
    z.free_service=True
    shutdown=z.call(shutdown_trampoline(z),0x55348b20,task='shutdown',stack_pointer=STACK-0x10000,allow_pause=True)
    assert z.paused==('blocking_private_wait','shutdown',private[0]),'Shutdown must block on module gate before factory free'
    assert z.get(LATCH)==1 and SERVICE not in z.frees
    z.resume(ui,'ui',STACK)
    assert not z.locked and z.mutex_owners[private[0]] is None and SERVICE not in z.frees
    z.resume(shutdown,'shutdown',STACK-0x10000)
    assert SERVICE in z.frees and z.get(0x55348b28)==1 and z.get(0x55348b24)==SERVICE
    z.fire();z.call('grmod_cancel');z.canaries()
    checks.append('two actual CPU contexts: shutdown waits infinitely on module gate while UI holds both locks; UI finishes/releases; shutdown drains then native factory frees service; later callback never reads unmapped service')
    a=Fixture(data,segments,symbols);a.pause_gate=True
    ui=a.call('grmod_on_shot',allow_pause=True)
    assert a.paused and a.paused[0]=='before_private_lock' and not a.locked
    a.free_service=True
    a.call(shutdown_trampoline(a),0x55348b20,task='shutdown',stack_pointer=STACK-0x10000)
    assert SERVICE in a.frees
    a.resume(ui,'ui',STACK)
    assert not any(e[0] in DRIVERS.values() for e in a.events),'Latched UI operation touched already deleted service'
    a.fire();a.call('grmod_cancel');a.canaries()
    checks.append('preemption before private acquire: shutdown completes first; resumed UI acquires persistent gate, rechecks latch and never reads deleted service')
    b=Fixture(data,segments,symbols);b.pause_create=True
    ui=b.call('grmod_on_shot',allow_pause=True)
    assert b.paused==('during_gate_creation','ui') and b.get(ANCHOR)==0
    b.free_service=True
    b.call(shutdown_trampoline(b),0x55348b20,task='shutdown',stack_pointer=STACK-0x10000)
    assert SERVICE in b.frees and b.get(ANCHOR)==0
    b.resume(ui,'ui',STACK)
    assert b.get(ANCHOR) and b.children(b.roots[0])
    assert not any(e[0] in DRIVERS.values() for e in b.events),'Late state publication bypassed shutdown latch'
    b.fire();b.call('grmod_cancel');b.canaries()
    checks.append('shutdown during first gate construction sees unpublished state; later initialized state publication preserves latch and optional audio stays disabled')
    return dict(checks=checks,allocations=len(p.allocations),state_pointer=hex(p.get(ANCHOR)),
                state_allocation_bytes=next(size for at,size in p.allocations if at==p.get(ANCHOR)),
                native_timer_dispatch=True,native_mutex_body=True,native_wave_bodies=True,native_canvas_draw=True,
                native_audio_teardown_dispatch=True,shutdown_thread_quiescence_verified=False,
                shutdown_private_gate_interleaving_verified=True,
                shutdown_overlap_verified=True,gate_initialization_failure_suppresses_audio=True,
                shutdown_safety_uses_private_mutex=True,
                simulated_boundaries=['OS create/wait/unlock and shared mutex ownership across saved CPU contexts',
                    'existing global mutex registry entry lookup','allocator','OS clock and alarms','driver calls',
                    'diagnostic sink','App/UserData/UI lookup inputs','native service destructor OS cleanup'],
                original_firmware_preserved=True,
                hardware_tested=False,physical_display_tested=False,dma_cache_tested=False)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rtos',type=Path,default=ROOT/'scratch/video-firmware-high-rate-2026-11-01/original-rtos.bin')
    parser.add_argument('--out',type=Path,default=HERE.parent/'out/adapter-check')
    parser.add_argument('--payload-elf',type=Path,help='Execute final linked camera callbacks and real embedded assets instead of building synthetic assets')
    parser.add_argument('--clang',default=shutil.which('clang') or r'C:\Program Files\LLVM\bin\clang.exe')
    parser.add_argument('--lld',default=shutil.which('ld.lld') or r'C:\Program Files\LLVM\bin\ld.lld.exe')
    args=parser.parse_args()
    data=args.rtos.read_bytes();assert hashlib.sha256(data).hexdigest()==SHA,'Wrong firmware identity'
    args.out=args.out.resolve();args.out.mkdir(parents=True,exist_ok=True)
    segments,symbols=read_elf(args.payload_elf) if args.payload_elf else build(args,args.out)
    sources=['camera_gr3.c','camera_gr3.h','terminal.c','terminal.h','camera_clock.c','camera_clock.h','check_adapter.py']
    ranges=[(0x53391a30,0x178),(0x536c761c,0xe8),(0x536c7704,0xb8),(0x5316cac0,0xd4),
            (0x53568d58,0x48),(0x53568c88,0xa0),(0x53566b68,0xc),(0x53568e58,0x70),
            (0x536ae668,0x3c),(0x536aef0c,0x24c),(0x53566e44,0x34)]
    report=dict(rtos_sha256=SHA,
        source_sha256={str((HERE/name).relative_to(ROOT)).replace('\\','/'):hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in sources},
        test_mode='final linked payload' if args.payload_elf else 'compiled adapter with synthetic assets',
        payload_elf_sha256=hashlib.sha256((args.payload_elf or args.out/'adapter-tests.elf').read_bytes()).hexdigest(),
        embedded_asset_sha256=hashlib.sha256(embedded(segments,symbols,'terminal_asset')).hexdigest(),
        embedded_wave_sha256={name:hashlib.sha256(embedded(segments,symbols,'terminal_wav_'+name)).hexdigest() for name in ('dash','portal','rocket')},
        fixture_asset_sha256=hashlib.sha256(asset()).hexdigest(),
        native_abi_evidence=[dict(address=hex(at),bytes=data[at-0x53000000:at-0x53000000+size].hex()) for at,size in ranges],
        **verify(data,segments,symbols))
    (args.out/'adapter-verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({k:v for k,v in report.items() if k!='native_abi_evidence'},indent=2))

if __name__=='__main__':main()
