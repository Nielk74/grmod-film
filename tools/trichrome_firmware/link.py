"""Deterministic freestanding A32 build; no writable globals in RTOS text."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from elftools.elf.elffile import ELFFile

HERE=Path(__file__).resolve().parent


def build(out,base,prior_expose,prior_jpeg):
    out.mkdir(parents=True,exist_ok=True)
    cc=[sys.executable,'-m','ziglang','cc','-target','arm-freestanding-eabi','-mcpu=cortex_a9','-marm',
        '-mfloat-abi=soft','-Os','-ffreestanding','-fno-builtin','-fno-unwind-tables','-fno-asynchronous-unwind-tables',
        '-fno-jump-tables','-fno-pic','-nostdlib','-Wall','-Wextra','-Werror']
    objects=[]
    for name in ['trichrome.c','camera.c','hooks.S']:
        obj=out/(name+'.o');subprocess.run(cc+['-c',str(HERE/'native'/name),'-o',str(obj)],check=True,capture_output=True)
        objects.append(str(obj))
    script=out/'module.ld'
    script.write_text(f'''ENTRY(tri_hook_jpeg)
SECTIONS {{ . = {base:#x}; .text : {{ *(.text*) }} .rodata : {{ *(.rodata*) }}
 .data : {{ *(.data*) }} .bss : {{ *(.bss*) *(COMMON) }}
 /DISCARD/ : {{ *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) }} }}
ASSERT(SIZEOF(.data)==0,"No mutable RTOS data allowed")
ASSERT(SIZEOF(.bss)==0,"No mutable RTOS globals allowed")
tri_prior_expose = {prior_expose:#x}; tri_prior_jpeg = {prior_jpeg:#x};
tri_cont_arm = 0x5342c968; tri_cont_override = 0x53510804; tri_cont_single = 0x5342caf0;
''',encoding='utf-8',newline='\n')
    elf=out/'module.elf'
    subprocess.run([sys.executable,'-m','ziglang','ld.lld','-T',str(script),'-o',str(elf),*objects],check=True,capture_output=True)
    with elf.open('rb') as f:
        e=ELFFile(f);symbols={s.name:s['st_value'] for s in e.get_section_by_name('.symtab').iter_symbols() if s.name and s['st_shndx']!='SHN_UNDEF'}
        assert all(s['st_shndx']!='SHN_UNDEF' or not s.name for s in e.get_section_by_name('.symtab').iter_symbols()),'unresolved symbol'
        sections=[(s.name,s['sh_addr'],s.data()) for s in e.iter_sections() if s['sh_flags']&2 and s['sh_size']]
    end=max(a+len(b) for _,a,b in sections);blob=bytearray(end-base)
    for _,a,b in sections:assert a>=base;blob[a-base:a-base+len(b)]=b
    (out/'module.bin').write_bytes(blob)
    report=dict(base=base,end=end,size=len(blob),sha256=hashlib.sha256(blob).hexdigest(),
        symbols=symbols,sections=[dict(name=n,address=a,size=len(b)) for n,a,b in sections],
        prior_expose=prior_expose,prior_jpeg=prior_jpeg,
        source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((HERE/'native').glob('*'))})
    (out/'link.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--base',type=lambda v:int(v,0),required=True)
    p.add_argument('--prior-expose',type=lambda v:int(v,0),required=True);p.add_argument('--prior-jpeg',type=lambda v:int(v,0),required=True)
    a=p.parse_args();print(json.dumps(build(a.out,a.base,a.prior_expose,a.prior_jpeg),indent=2))
