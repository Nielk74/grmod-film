"""Execute hash-pinned original GR III2.10 JPEG lineage and drive-property paths.

RAM objects are synthetic. Original builders, descriptor copy, property setter
and enum conversion execute unchanged; no hardware timing or burst identity is
inferred. Capture epoch assignment remains a separate required proof.
"""
import hashlib
import json
from pathlib import Path
import struct

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn import arm_const as ar

SOURCE=Path('C:/Users/Antoine/project/grmod-film/scratch/video-firmware-high-rate-2026-11-01/original-rtos.bin')
SHA='8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67'
BASE=0x53000000;FRAME=0x62000000;COMMON=0x62010000;SETTINGS=0x62090000
PIPELINE=0x620a0000;OBJECT=0x620b0000;INNER=0x620b1000;UPDATES=0x620b2000
INPUT=0x620b3000;STACK=0x61010000;STOP=0x61020000
OUT=Path(__file__).resolve().parents[2]/'scratch/trichrome-firmware'


def main():
    code=SOURCE.read_bytes();assert hashlib.sha256(code).hexdigest()==SHA
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    for at,n in [(BASE,(len(code)+4095)&~4095),(FRAME,0x100000),(STACK-0x10000,0x10000),(STOP,4096)]:u.mem_map(at,n)
    u.mem_write(BASE,code)
    def wr(a,v):u.mem_write(a,struct.pack('<I',v))
    def rd(a):return struct.unpack('<I',u.mem_read(a,4))[0]
    def call(at,*args,end=STOP):
        u.reg_write(ar.UC_ARM_REG_SP,STACK);u.reg_write(ar.UC_ARM_REG_LR,STOP)
        for i,v in enumerate(args):u.reg_write(getattr(ar,f'UC_ARM_REG_R{i}'),v)
        u.emu_start(at,end,count=100000)
        assert u.reg_read(ar.UC_ARM_REG_PC)==end
        if end==STOP:assert u.reg_read(ar.UC_ARM_REG_SP)==STACK
        return u.reg_read(ar.UC_ARM_REG_R0)
    wr(FRAME+0x44c8,COMMON);wr(FRAME+0x5c,SETTINGS)
    u.mem_write(FRAME+0x70,bytes(range(32)))
    call(0x5350e624,FRAME,6);config=call(0x5350e114,FRAME,6)
    assert config==FRAME+0x9b8
    fields={0x34:COMMON,0x38:SETTINGS,0x3c:FRAME+0xb0,0x40:FRAME+0xd0,0x44:FRAME+0xf0,0x48:FRAME+0x110}
    for off,v in fields.items():assert rd(config+off)==v
    for reg,v in [('R0',FRAME),('R1',6),('R4',FRAME),('R6',PIPELINE),('R8',6),('SP',STACK)]:
        u.reg_write(getattr(ar,'UC_ARM_REG_'+reg),v)
    u.emu_start(0x5351eb6c,0x5351eb98,count=10000)
    assert u.reg_read(ar.UC_ARM_REG_PC)==0x5351eb98
    args=FRAME+0x3b0+24*6;assert rd(args+8)==config and rd(rd(args+8)+0x34)==COMMON
    # Real conversion used by saved-drive getter53271448: saved2→native2.
    converted={i:call(0x5326c614,OBJECT,i) for i in range(12)}
    assert converted[2]==2 and converted[0]==1
    # Original property0x8f input handler and setter through the change event
    # store. Stop before dependent-property recalculation, not a full OS call.
    wr(OBJECT+0x518,INNER);wr(INNER+4,COMMON);wr(INNER+8,UPDATES)
    u.mem_write(INPUT,b'\x02');u.mem_write(COMMON+0x6f4,b'\x01')
    call(0x53540f48,OBJECT,INPUT,0,end=0x5355d558)
    assert bytes(u.mem_read(COMMON+0x6f4,1))==b'\x02'
    assert struct.unpack('<H',u.mem_read(UPDATES+2,2))[0]==0x8f
    assert bytes(u.mem_read(UPDATES,1))==b'\x01'
    # Native getter/FE helper independently read the same field.
    wr(OBJECT,COMMON);assert call(0x53551390,OBJECT)==2
    drive_tests={}
    for v in range(5):
        u.mem_write(COMMON+0x6f4,bytes([v]));drive_tests[v]=call(0x5346620c,OBJECT,COMMON)
    assert drive_tests=={0:0,1:0,2:1,3:1,4:0}
    # Execute the real clock wrapper; substitute only the OS get_tim boundary.
    # Native OS order is highword then lowword; C uint64_t output is LE low/high.
    u.reg_write(ar.UC_ARM_REG_C1_C0_2,0xf<<20);u.reg_write(ar.UC_ARM_REG_FPEXC,0x40000000)
    clock_input=[0,0,0]
    def get_tim(machine,address,size,data):
        p=machine.reg_read(ar.UC_ARM_REG_R0)
        machine.mem_write(p,struct.pack('<2I',clock_input[0],clock_input[1]))
        machine.reg_write(ar.UC_ARM_REG_R0,clock_input[2]);machine.reg_write(ar.UC_ARM_REG_PC,machine.reg_read(ar.UC_ARM_REG_LR))
    clock_hook=u.hook_add(UC_HOOK_CODE,get_tim,begin=0x53050b7c,end=0x53050b7c)
    clock_checks=[]
    for high,low,result in [(0,12345,0),(0x11223344,0x55667788,0),(0x99887766,0x55443322,0),(0,0,0xfffffffb)]:
        clock_input[:]=[high,low,result];u.mem_write(INPUT,b'\xa5'*8)
        ok=call(0x536afc5c,INPUT);actual=bytes(u.mem_read(INPUT,8))
        expected=struct.pack('<2I',low,high) if result==0 else b'\xa5'*8
        assert ok==int(result==0) and actual==expected
        clock_checks.append(dict(os_high=high,os_low=low,os_return=result,wrapper_success=ok,output_preserved_on_failure=result!=0))
    u.hook_del(clock_hook)
    spans=[(0x5350e624,0x840),(0x5350e114,0x110),(0x5351eb6c,0x2c),
           (0x5326c614,0xcc),(0x53540f48,0x38),(0x5355d4ec,0xe4),(0x53551390,12),(0x5346620c,24),(0x536afc5c,0x78)]
    report=dict(source=str(SOURCE),sha256=SHA,
        jpeg=dict(builder='0x5350e624',selector='0x5350e114',macro_id=6,
                  args_config='frame+0x3b0+24*6 -> +8',config='frame+0x9b8',
                  fields={hex(k):hex(v) for k,v in fields.items()},common_matches=True),
        drive=dict(saved_to_native=converted,property_id='0x8f',common_offset='0x6f4',
                   setter_path=['0x53540f48','0x5355d5d0','0x5355d4ec','stop0x5355d558'],
                   field_store_and_event_verified=True,fe_helper=drive_tests),
        native_clock=dict(entry='0x536afc5c',only_stub='OSget_tim0x53050b7c',checks=clock_checks,
                          unit_evidence='Existing shot-animation native clock caller analysis: UI blink/animation delta uses1000units per second; no hardware timing measured here.'),
        spans={hex(a):dict(size=n,sha256=hashlib.sha256(code[a-BASE:a-BASE+n]).hexdigest()) for a,n in spans},
        limits='Synthetic RAM objects; bounded original instruction execution. Drive mode alone does not establish capture generation, independent exposures or JPEG source. No hardware/concurrency proof.',
        capture_adapter_verified=False,hardware_tested=False)
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'native-lineage-verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
