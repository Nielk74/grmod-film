"""Compile and execute the current12-pose Terminal renderer on emulated ARM.

No firmware/camera is modified. Original firmware ABI probes are separate.
"""
import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import time
import zlib
from pathlib import Path
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

HERE=Path(__file__).resolve().parent
OUT=HERE.parent/'out'/'firmware'

def save_png(path,rgba):
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    scan=b''.join(b'\0'+rgba[y*960:(y+1)*960] for y in range(176))
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',240,176,8,6,0,0,0))+
        chunk(b'IDAT',zlib.compress(scan))+chunk(b'IEND',b''))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clang',default=shutil.which('clang') or r'C:\Program Files\LLVM\bin\clang.exe')
    parser.add_argument('--lld',default=shutil.which('ld.lld') or r'C:\Program Files\LLVM\bin\ld.lld.exe')
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    objects=[]
    for name in ('terminal','test_terminal'):
        obj=OUT/(name+'.o')
        subprocess.run([args.clang,'-target','armv7-none-eabi','-mcpu=cortex-a9','-marm','-mfloat-abi=soft','-mfpu=none',
            '-Os','-ffreestanding','-fno-builtin','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
            '-fno-stack-protector','-Wall','-Wextra','-Werror','-c',str(HERE/(name+'.c')),'-o',str(obj)],check=True)
        objects.append(str(obj))
    elf_path=OUT/'terminal-tests.elf'
    subprocess.run([args.lld,'-Ttext=0x10000000','--entry=test_terminal_asset','--no-undefined',*objects,'-o',str(elf_path)],check=True)
    cpu=Uc(UC_ARCH_ARM,UC_MODE_ARM)
    cpu.mem_map(0x10000,0x1000);cpu.mem_map(0x10000000,0x100000)
    cpu.mem_map(0x20000000,0x20000);cpu.mem_map(0x30000000,0x800000)
    with elf_path.open('rb') as stream:
        elf=ELFFile(stream)
        for segment in elf.iter_segments():
            if segment['p_type']=='PT_LOAD':cpu.mem_write(segment['p_vaddr'],segment.data())
        symbols={s.name:s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()}
    def call(name,*values,want=0):
        cpu.reg_write(UC_ARM_REG_SP,0x2001f000);cpu.reg_write(UC_ARM_REG_LR,0x20000000)
        for register,value in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3),values):cpu.reg_write(register,value)
        cpu.emu_start(symbols[name],0x20000000,count=1_000_000_000)
        assert cpu.reg_read(UC_ARM_REG_PC)==0x20000000,f'{name}: instruction budget exhausted'
        result=cpu.reg_read(UC_ARM_REG_R0)
        assert result==want,f'{name} failed at test_terminal.c:{result} (expected{want})'
    asset=(OUT/'terminal-native.trm').read_bytes()
    def reject(name,edit,repair=True):
        changed=bytearray(asset);edit(changed)
        if repair:struct.pack_into('<I',changed,64,zlib.crc32(changed[80:]))
        cpu.mem_write(0x30000000,bytes(changed));call('test_terminal_reject',0x30000000,len(changed))
        return name
    tracks=struct.unpack_from('<I',asset,52)[0]
    indices=struct.unpack_from('<I',asset,48)[0]
    invalid=[]
    invalid.append(reject('truncated',lambda b:b.pop()))
    invalid.append(reject('magic',lambda b:b.__setitem__(0,0)))
    invalid.append(reject('CRC',lambda b:b.__setitem__(-1,b[-1]^1),False))
    invalid.append(reject('indices',lambda b:b.__setitem__(indices,255)))
    invalid.append(reject('pose',lambda b:struct.pack_into('<H',b,tracks,12)))
    invalid.append(reject('reserved',lambda b:b.__setitem__(tracks+3,1)))
    invalid.append(reject('vector extent',lambda b:struct.pack_into('<I',b,tracks+36,0xfffffff0)))
    invalid.append(reject('section offset',lambda b:struct.pack_into('<I',b,52,0xfffffff0)))
    cpu.mem_write(0x30000000,asset)
    start=time.monotonic();call('test_terminal_asset',0x30000000,len(asset));elapsed=time.monotonic()-start
    # Reuse the lab's installedSharp decoder rather than adding a Python image dependency.
    sharp_uri=(HERE.parent/'node_modules'/'sharp'/'lib'/'index.js').as_uri()
    script=('import sharp from '+json.dumps(sharp_uri)+'; import{writeFile}from"node:fs/promises";const root='+json.dumps(str(OUT))+';'
        'for(const id of["dash","portal","rocket"])for(const ms of[400,900,1900,4400,6750,7000]){'
        'const input=root+"/browser-"+id+"-"+ms+".png";const{data,info}=await sharp(input).ensureAlpha().raw().toBuffer({resolveWithObject:true});'
        'if(info.width!==240||info.height!==176)throw Error("Unexpected browser capture size");await writeFile(input+".rgba",data);}')
    subprocess.run([shutil.which('node') or 'node','--input-type=module','-e',script],check=True)
    comparisons=[]
    for sequence,name in enumerate(('dash','portal','rocket')):
        for ms in (400,900,1900,4400,6750,7000):
            call('test_terminal_render',sequence,ms)
            rgba=bytes(cpu.mem_read(symbols['frame']+4,240*176*4))
            save_png(OUT/f'native-{name}-{ms}.png',rgba)
            actual=list(struct.iter_unpack('4B',rgba))
            expected=list(struct.iter_unpack('4B',(OUT/f'browser-{name}-{ms}.png.rgba').read_bytes()))
            union=[i for i,(a,b) in enumerate(zip(actual,expected)) if max(a[3],b[3])>=32]
            if not union:continue
            error=sum(sum(abs(a[k]*a[3]/255-b[k]*b[3]/255) for k in range(3))+abs(a[3]-b[3])
                for i in union for a,b in [(actual[i],expected[i])])/(len(union)*4)
            alpha_intersection=sum(min(actual[i][3],expected[i][3]) for i in union)
            alpha_union=sum(max(actual[i][3],expected[i][3]) for i in union)
            iou=alpha_intersection/alpha_union
            comparisons.append(dict(sequence=name,ms=ms,premultiplied_mae=round(error,3),alpha_iou=round(iou,5)))
            assert iou>.88 and error<18,f'{name}@{ms}: native/browser disagreement{iou=},{error=}'
    report=dict(artifact_sha256=hashlib.sha256(asset).hexdigest(),asset_bytes=len(asset),
        source_hashes={name:hashlib.sha256((HERE/name).read_bytes()).hexdigest() for name in ('terminal.c','terminal.h','test_terminal.c')},
        native_assertions=struct.unpack('<I',cpu.mem_read(symbols['checks'],4))[0],
        corrupt_cases=invalid,comparisons=comparisons,framebuffer_bytes=240*176*4,
        harness_emulation_seconds=round(elapsed,3),hardware_performance_measured=False,camera_adapter_verified=False)
    (OUT/'native-verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
