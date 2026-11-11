"""Exact GR III 2.10 face reader/writer evidence and native round-trip probes."""
from __future__ import annotations
import argparse, hashlib, json, struct, sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]/'gr3x'))
from native_probe import NativeProbe, STACK, STOP
from capstone import Cs,CS_ARCH_ARM,CS_MODE_ARM
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM,UC_HOOK_CODE
from unicorn import arm_const as reg

ROOT=Path(__file__).resolve().parents[2]
RTOS_SHA='8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67'
RECORD,ENTRY,DATA,HELPER,HEAP=0x62500000,0x62600000,0x62700000,0x62020000,0x62800000


def probe(blob):
    n=NativeProbe(blob);u=n.uc
    for at,size in [(RECORD,0x80000),(ENTRY,0x1000),(DATA,0x1000),(HEAP,0x1000)]:u.mem_map(at,size)
    allocations=[]
    def hook(cpu,at,size,_):
        if at==0x536af2a8:
            assert cpu.reg_read(reg.UC_ARM_REG_R0)==16
            allocations.append(16);cpu.reg_write(reg.UC_ARM_REG_R0,HEAP)
            cpu.reg_write(reg.UC_ARM_REG_PC,cpu.reg_read(reg.UC_ARM_REG_LR))
        if at==0x536af2e4:
            assert cpu.reg_read(reg.UC_ARM_REG_R0)==HEAP
            cpu.reg_write(reg.UC_ARM_REG_PC,cpu.reg_read(reg.UC_ARM_REG_LR))
    u.hook_add(UC_HOOK_CODE,hook)
    cases=[]
    for na,nb in [(0,0),(1,0),(0,1),(2,1),(4,4),(10,10)]:
        words=[0]*410;words[:10]=[6000,4000,666,500,4668,3000,na,0,nb,0]
        for i in range(na+nb):
            words[10+i*20:14+i*20]=[100+i*180,200+i*80,400,500]
        payload=struct.pack('<410I',*words)
        u.mem_write(RECORD,bytes(0x80000));u.mem_write(ENTRY,struct.pack('<IHHIIII',0,0x40b,7,1640,0,DATA,0))
        u.mem_write(DATA,payload);u.mem_write(HELPER+8,struct.pack('<I',RECORD))
        n.call(0x535ee208,HELPER,ENTRY)
        assert struct.unpack('<6I',u.mem_read(RECORD+0x38d50,24))==(6000,4000,666,500,4668,3000)
        assert struct.unpack('<4H',u.mem_read(RECORD+0x38d68,8))==(na,0,nb,0)
        for stream,count,first in [(0,na,0),(1,nb,na)]:
            address=RECORD+0x38d70+stream*640
            if count:
                # Existing original reader writes every element over slot0.
                # Preserve this observation; do not "repair" firmware here.
                got=list(struct.unpack('<4I',u.mem_read(address,16)))
                assert got==words[10+(first+count-1)*20:14+(first+count-1)*20]
                assert bytes(u.mem_read(address+64,576))==bytes(576)
            # Independently populate the capture-style record for writer test.
            for j in range(count):
                u.mem_write(address+j*64,struct.pack('<4I',*words[10+(first+j)*20:14+(first+j)*20]))
        # The writer serializes A then B contiguously, not at fixed slot10.
        u.mem_write(HELPER+0x18,struct.pack('<I',RECORD));u.mem_write(DATA,bytes(1640))
        n.call(0x53605ef4,HELPER,ENTRY)
        assert bytes(u.mem_read(DATA,1640))==payload
        cases.append({'a':na,'b':nb,'writer_exact':True,'reader_retains_last_in_slot0':True})
    return {'native_reader':hex(0x535ee208),'native_writer':hex(0x53605ef4),'cases':cases,
            'stubbed_boundaries':['16-byte temporary allocation/free only'],
            'record_image_size_offset':hex(0x38d50),'record_counts_offset':hex(0x38d68),
            'record_arrays':[hex(0x38d70),hex(0x38ff0)],'record_stride':64}


def jpeg_lineage(blob):
    """Execute original builder/selector/dispatch, including descriptor copy.

    Independently reproduced from the parent's review probe. This proves
    config pointer lineage, rather than camera concurrency or face freshness.
    """
    u=Uc(UC_ARCH_ARM,UC_MODE_ARM);frame=0x62000000;common=0x62010000
    settings=0x62090000;pipeline=0x620a0000;stack=0x61010000;stop=0x61020000
    for at,size in [(0x53000000,(len(blob)+4095)&~4095),(frame,0x100000),
                    (stack-0x10000,0x10000),(stop,4096)]:u.mem_map(at,size)
    u.mem_write(0x53000000,blob)
    def w(at,value):u.mem_write(at,struct.pack('<I',value))
    def r(at):return struct.unpack('<I',u.mem_read(at,4))[0]
    def call(at,*args):
        u.reg_write(reg.UC_ARM_REG_SP,stack);u.reg_write(reg.UC_ARM_REG_LR,stop)
        for i,value in enumerate(args):u.reg_write(getattr(reg,'UC_ARM_REG_R'+str(i)),value)
        u.emu_start(at,stop,count=10000)
        assert u.reg_read(reg.UC_ARM_REG_PC)==stop and u.reg_read(reg.UC_ARM_REG_SP)==stack
        return u.reg_read(reg.UC_ARM_REG_R0)
    w(frame+0x44c8,common);w(frame+0x5c,settings);u.mem_write(frame+0x70,bytes(range(32)))
    call(0x5350e624,frame,6);config=call(0x5350e114,frame,6)
    assert config==frame+0x9b8
    fields={0x34:common,0x38:settings,0x3c:frame+0xb0,0x40:frame+0xd0,0x44:frame+0xf0,0x48:frame+0x110}
    assert all(r(config+off)==value for off,value in fields.items())
    for register,value in [(0,frame),(1,6),(4,frame),(6,pipeline),(8,6)]:
        u.reg_write(getattr(reg,'UC_ARM_REG_R'+str(register)),value)
    u.reg_write(reg.UC_ARM_REG_SP,stack);u.emu_start(0x5351eb6c,0x5351eb98,count=10000)
    args=frame+0x3b0+24*6
    assert u.reg_read(reg.UC_ARM_REG_PC)==0x5351eb98 and r(args+8)==config and r(config+0x34)==common
    return {'builder':'0x5350e624','selector':'0x5350e114','dispatch_prefix':['0x5351eb6c','0x5351eb98'],
            'macro_id':6,'config_offset':'frame+0x9b8','fields':{hex(k):hex(v-frame) if v!=common and v!=settings else 'CommonProperty*' if v==common else 'settings*' for k,v in fields.items()},
            'original_descriptor_copy_executed':True,'args_config_and_common_match':True,
            'limits':'Pointer lineage only; does not prove face freshness or burst identity.'}


def capture_freshness(blob):
    """Actual capture function with only its external device read stubbed.

    Ring population, clearing, count selection, coordinate transforms and
    CommonProperty writes execute original instructions. Detector inputs are
    synthetic; this is not a claim to emulate the AF hardware.
    """
    n=NativeProbe(blob);u=n.uc;source=0x62010000;common=0x62500000;out=0x62600000
    u.mem_map(common,0x80000);u.mem_map(out,4096)
    def hook(cpu,at,size,_):cpu.reg_write(reg.UC_ARM_REG_PC,cpu.reg_read(reg.UC_ARM_REG_LR))
    u.hook_add(UC_HOOK_CODE,hook,begin=0x53666908,end=0x53666908)
    cases=[]
    for count in (0,1,9):
        u.mem_write(source,bytes(0x6000));u.mem_write(common,bytes(0x80000))
        for off,value in [(0x9c8,6000),(0x9cc,4000),(0x266c,1),(0x5270,0)]:
            u.mem_write(source+off,struct.pack('<I',value))
        u.mem_write(common+0x38d6c,struct.pack('<H',9))
        u.mem_write(source+0x4620,struct.pack('<H',9))
        u.mem_write(source+0x4620+0xbc*3,struct.pack('<H',3))
        for i in range(count):
            u.mem_write(source+0x2900+i*0x290,struct.pack('<5I',1,400,500,1000,1000))
        # The detector's geometry snapshot is expressed in 16.16 sensor units.
        u.mem_write(source+0x4010,struct.pack('<4I',5<<16,6<<16,10<<16,10<<16))
        n.call(0x5345133c,source,0,0,out+0x200,stack=struct.pack('<3I',out,0,common))
        a=struct.unpack('<H',u.mem_read(common+0x38d68,2))[0]
        b=struct.unpack('<H',u.mem_read(common+0x38d6c,2))[0]
        xywh=struct.unpack('<4I',u.mem_read(common+0x38ff0,16))
        assert a==3 and b==count and xywh==(1333,1333,667,800)
        cases.append({'detector_valid_flags':count,'stale_current_ring_count':9,
                      'previous_A':a,'current_B':b,'native_encoded_xywh':xywh})
    return {'native_capture':'0x5345133c','native_current_population':'0x53450a8c',
            'native_coordinate_transform':'0x5356bf94','cases':cases,
            'stubbed_boundary':'0x53666908 external device snapshot; preserves supplied detector input',
            'limits':'Synthetic detector input; no hardware AF timing, scheduling or burst proof.'}


def develop_look_lineage(blob):
    """Prove ordinary Develop's virtual setup selects the direct owned look."""
    n=NativeProbe(blob);u=n.uc;process=0x62010000;config=0x620a0000
    common=0x62500000;settings=0x620a1000;obj=0x620b0000
    u.mem_map(common,0x80000)
    def w(at,value):u.mem_write(at,struct.pack('<I',value))
    def r(at):return struct.unpack('<I',u.mem_read(at,4))[0]
    assert struct.unpack_from('<I',blob,0x53501634-0x53000000)[0]==0x53c627b8
    assert struct.unpack_from('<I',blob,0x53c627b8+0x20-0x53000000)[0]==0x53501c38
    assert struct.unpack_from('<I',blob,0x53c627b8+0x24-0x53000000)[0]==0x535059ec
    w(process,0x53c627b8);w(config+0x34,common);w(config+0x38,settings)
    u.reg_write(reg.UC_ARM_REG_R0,process);u.reg_write(reg.UC_ARM_REG_R6,config);u.reg_write(reg.UC_ARM_REG_SP,STACK)
    u.emu_start(0x53501d04,0x53501d2c,count=1000)
    assert u.reg_read(reg.UC_ARM_REG_R12)==0x535059ec
    assert [u.reg_read(getattr(reg,'UC_ARM_REG_R'+str(i))) for i in (1,2,3)]==[process+0x40,process+0x8314,config]
    w(obj+4,obj+0x100);w(obj+0x114,obj+0x200);w(obj+0x21c,obj+0x300)
    u.mem_write(obj+0x304,struct.pack('<4H',1,1,1,1))
    boundaries=[]
    def hook(cpu,at,size,_):
        if at in (0x536eddf0,0x536ee4f8,0x53525d5c):
            boundaries.append(hex(at));cpu.reg_write(reg.UC_ARM_REG_R0,obj if at==0x53525d5c else 0)
            cpu.reg_write(reg.UC_ARM_REG_PC,cpu.reg_read(reg.UC_ARM_REG_LR))
    u.hook_add(UC_HOOK_CODE,hook)
    u.reg_write(reg.UC_ARM_REG_SP,STACK);u.reg_write(reg.UC_ARM_REG_LR,STOP)
    u.emu_start(0x535059ec,0x53505b20,count=100000)
    context=process+0x40
    assert r(context+0x82d0)==common and bytes(u.mem_read(context+0x82ac,1))==b'\0'
    u.mem_write(common+0x77c,b'\x40');u.mem_write(common+0x71248+0x77c,b'\x0b')
    u.reg_write(reg.UC_ARM_REG_R1,context);u.reg_write(reg.UC_ARM_REG_SP,STACK)
    u.emu_start(0x536db7d8,0x536db7fc,count=1000)
    assert u.reg_read(reg.UC_ARM_REG_R3)==common and u.reg_read(reg.UC_ARM_REG_R2)==64
    return {'vtable':'0x53c627b8','execute':'0x53501c38','virtual_setup':'0x535059ec',
            'execute_call_prefix':['0x53501d04','0x53501d2c'],'setup_prefix':['0x535059ec','0x53505b20'],
            'look_read_prefix':['0x536db7d8','0x536db7fc'],'context_common_offset':'0x82d0',
            'context_format_offset':'0x82ac','format_after_setup':0,'direct_common_look_offset':'0x77c',
            'direct_look':64,'unused_secondary_look':11,'helper_boundaries_stubbed':boundaries,
            'limits':'Bounded original setup prefixes; constructor, metadata accessor and platform singleton are boundaries.'}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('rtos',type=Path);ap.add_argument('--output',type=Path,default=ROOT/'scratch/face-fill-firmware/trace.json');a=ap.parse_args()
    blob=a.rtos.read_bytes();assert hashlib.sha256(blob).hexdigest()==RTOS_SHA
    md=Cs(CS_ARCH_ARM,CS_MODE_ARM)
    ranges=[(0x535ee208,0x535ee318),(0x53605ef4,0x53606098),(0x5345133c,0x534513a0),
            (0x53451680,0x534516c8),(0x53451814,0x534518d0),(0x53451c48,0x53451ca8),
            (0x53451ed0,0x53452020)]
    instructions=[]
    for start,end in ranges:
        instructions.extend({'at':hex(i.address),'bytes':i.bytes.hex(),'asm':i.mnemonic+' '+i.op_str}
                            for i in md.disasm(blob[start-0x53000000:end-0x53000000],start))
    report={'rtos_sha256':RTOS_SHA,'native_roundtrip':probe(blob),'jpeg_lineage':jpeg_lineage(blob),
            'capture_freshness':capture_freshness(blob),'develop_look_lineage':develop_look_lineage(blob),'instructions':instructions,
            'unknowns':['RAW development unsupported/unverified; saved valid face records may apply','Hardware timing and concurrency unmeasured']}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report['native_roundtrip'],indent=2))


if __name__=='__main__':main()
