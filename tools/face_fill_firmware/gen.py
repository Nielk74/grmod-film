"""Build the freestanding module twice and prove position independence."""
from __future__ import annotations
import base64,hashlib,json,subprocess,sys,tempfile
from pathlib import Path
from elftools.elf.elffile import ELFFile

HERE=Path(__file__).resolve().parent


def run(args):
    p=subprocess.run([str(x) for x in args],capture_output=True,text=True,encoding='utf-8')
    if p.returncode:raise RuntimeError(p.stdout+p.stderr)
    return p.stdout


def main():
    z=[sys.executable,'-m','ziglang'];source=HERE/'module.c'
    flags=['-target','arm-freestanding-eabi','-mcpu=cortex_a9','-marm','-mfloat-abi=soft','-O2','-ffreestanding',
           '-fno-builtin','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-nostdlib','-fropi','-frwpi','-fno-jump-tables','-Wall','-Wextra','-Werror']
    with tempfile.TemporaryDirectory() as temp:
        p=Path(temp);obj=p/'module.o';run(z+['cc']+flags+['-c',source,'-o',obj]);blobs=[];entries={}
        for origin in (0x10000,0x543f0000):
            elf=p/f'{origin:x}.elf';binary=p/f'{origin:x}.bin'
            run(z+['ld.lld',f'-Ttext=0x{origin:x}','--entry=face_fill','-o',elf,obj])
            run(z+['objcopy','-O','binary','-j','.text',elf,binary])
            with elf.open('rb') as f:
                e=ELFFile(f)
                assert e.get_section_by_name('.symtab').get_symbol_by_name('face_fill')[0]['st_value']==origin
                for name in ('face_fill','face_capture_clear'):
                    offset=e.get_section_by_name('.symtab').get_symbol_by_name(name)[0]['st_value']-origin
                    if name in entries:assert entries[name]==offset
                    entries[name]=offset
                assert all(not s['sh_size'] for s in e.iter_sections() if s.name.startswith(('.data','.bss','.rodata','.got')))
                assert all(s['st_shndx']!='SHN_UNDEF' or not s.name for s in e.get_section_by_name('.symtab').iter_symbols())
            blobs.append(binary.read_bytes())
    assert blobs[0]==blobs[1]
    code=blobs[0];code+=bytes((-len(code))%4)
    report={'code':base64.b64encode(code).decode(),'bytes':len(code),'sha256':hashlib.sha256(code).hexdigest(),
            'source_sha256':hashlib.sha256(source.read_bytes().replace(b'\r\n',b'\n')).hexdigest(),
            'compiler':run(z+['cc','--version']).splitlines()[0],'position_independent':True,'entries':entries}
    (HERE/'module-code.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(len(code),'bytes',report['sha256'])


if __name__=='__main__':main()
