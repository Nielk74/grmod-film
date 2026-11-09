# SPDX-License-Identifier: GPL-2.0-only
"""Native/TypeScript geometry parity on non-flat 4:2:2 jobs, with immutable descriptors,
same-Y whole-buffer aliases, row padding, pointer offsets, heap canaries and failure paths.
Run from repository root: python tools/halation/check.py. Outputs stay in ignored research/.
No camera or firmware input is used. Also checks all six grain settings against TypeScript.
"""
import base64
import json
import re
import struct
import subprocess
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'research/gr3-210/wp2-implementation/halation-parity'
CODE_AT, CTX, CONFIG, DESC, STASH, TABLES = 0x10000, 0x60000000, 0x60001000, 0x60002000, 0x60003000, 0x61000000
STUB, STACK, HEAP = 0x70000000, 0x71000000, 0x48000000


def references():
    OUT.mkdir(parents=True, exist_ok=True)
    cases = []
    for mode in [0, 1, 2]:
        for colour in ['red', 'white', 'gold', 'orange']:
            cases.append(dict(mode=mode, colour=colour, primary='valid', width=1280, height=96))
    for primary in ['missing', 'invalid', 'preview']:
        for colour in ['red', 'white']:
            cases.append(dict(mode=1, colour=colour, primary=primary, width=1280, height=96))
    for width, height in [(3360, 224), (1280, 1280), (960, 1280), (640, 1280)]:
        for colour in ['red', 'white']:
            cases.append(dict(mode=1, colour=colour, primary='valid', width=width, height=height))
    (OUT / 'cases.json').write_text(json.dumps(cases), encoding='utf-8')
    # A temporary driver calls the production TypeScript reference and exports its exact tables.
    script = r"""
import {readFileSync,writeFileSync} from 'node:fs';
import {halateYcc,paramBytes,halationGains,halationLight,halationLut} from '../../../../core/src/fw/aspect/halation';
import {grainYC} from '../../../../core/src/color/grain';
const d='research/gr3-210/wp2-implementation/halation-parity/';
const cases=JSON.parse(readFileSync(d+'cases.json','utf8'));
const light=halationLight();
writeFileSync(d+'tables.json',JSON.stringify({params:Array.from(paramBytes()),gains:halationGains(),light:Array.from(light.table),
 luts:Object.fromEntries(['red','white','gold','orange'].map(c=>[c,Array.from(new Uint8Array([...halationLut(c),...halationLut('white').subarray(0,4096)]))]))}));
for(let k=0;k<cases.length;k++){
 const c=cases[k],geometry=c.mode?{policy:c.mode===1?'sensor':'output',...(c.primary==='valid'?{main:{width:c.width,height:c.height}}:{})}:undefined;
 for(const [name,w,h] of [['main',c.width,c.height],['sn',720,480],['th',160,120]]){
  const stride=w+16,offset=64,iy=new Uint8Array(offset+stride*(h+4)).fill(0xa5),ic=iy.slice();
  const y=new Uint8Array(w*h),ch=y.slice();
  for(let r=0;r<h;r++)for(let x=0;x<w;x++){
   const lamp=Math.abs(x-w/2)<w/32&&Math.abs(r-h/2)<Math.max(8,h/8);
   y[r*w+x]=lamp?252:16+((x*3+r*5)%160); ch[r*w+x]=108+((Math.floor(x/2)+r)%40);
  }
  for(let r=0;r<h;r++){iy.set(y.subarray(r*w,(r+1)*w),offset+r*stride);ic.set(ch.subarray(r*w,(r+1)*w),offset+r*stride);}
  const oy=iy.slice(),oc=ic.slice();
  halateYcc(y,ch,w,h,3,light,c.colour,geometry);
  for(let r=0;r<h;r++){oy.set(y.subarray(r*w,(r+1)*w),offset+r*stride);oc.set(ch.subarray(r*w,(r+1)*w),offset+r*stride);}
  for(const [label,a] of [['iy',iy],['ic',ic],['oy',oy],['oc',oc]])writeFileSync(d+`${k}-${name}-${label}.bin`,a);
 }
}
// Six grain settings, both new policies, with non-flat padded planes. Native check.py shares this fixture.
for(const mode of [1,2])for(const setting of [1,2,3,5,6,7]){
 const w=600,h=400,stride=608,y=new Uint8Array(h*stride),c=y.slice();
 for(let r=0;r<h;r++)for(let x=0;x<w;x++)y[r*stride+x]=(x*7+r*3+((x*r)>>5)+5)&255;
 for(let i=0;i<c.length;i++)c[i]=(i*13+12)&255;
 grainYC(y,c,w,h,stride,setting,6000,{policy:mode===1?'sensor':'output',main:{width:3360,height:2240}});
 writeFileSync(d+`grain-${mode}-${setting}.bin`,new Uint8Array([...y,...c]));
}
"""
    driver = OUT / 'reference.ts'
    driver.write_text(script, encoding='utf-8', newline='\n')
    result = subprocess.run([str(ROOT / 'node_modules/.bin/vite-node.cmd'), str(driver)], cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return cases, json.loads((OUT / 'tables.json').read_text(encoding='utf-8'))


def run(case, index, tables, code, fail_alloc=False, odd=False):
    mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    mu.mem_map(CODE_AT, 0x10000); mu.mem_write(CODE_AT, code)
    for address, length in [(CTX, 0x10000), (TABLES, 0x10000), (STUB, 0x1000), (STACK-0x10000, 0x10000), (HEAP, 0x1000000)]:
        mu.mem_map(address, length)
    planes = []
    for n, (name, w, h) in enumerate([('main', case['width'], case['height']), ('sn', 720, 480), ('th', 160, 120)]):
        iy = (OUT / f'{index}-{name}-iy.bin').read_bytes(); ic = (OUT / f'{index}-{name}-ic.bin').read_bytes()
        ya, ca = 0x80000000+n*0x4000000, 0x82000000+n*0x4000000
        for address, data in [(ya, iy), (ca, ic)]:
            mu.mem_map(address, (len(data)+0xfff)&~0xfff); mu.mem_write(address, data)
        planes.append((name, w, h, ya, ca, iy, ic))
    heap = [HEAP]; allocations = []; freed = []
    for n in range(5): mu.mem_write(STUB+n*16, struct.pack('<I', 0xe12fff1e))

    def hook(uc, at, size, _):
        operation = (at-STUB)//16
        if operation == 0: uc.reg_write(UC_ARM_REG_R0, 0x553a09c4)
        elif operation == 3:
            length = uc.reg_read(UC_ARM_REG_R0)
            address = heap[0]; heap[0] += (length+127)&~63
            assert heap[0] < HEAP+0x1000000
            uc.mem_write(address+length, b'\x5a'*32)
            allocations.append((address, length))
            uc.reg_write(UC_ARM_REG_R0, 0 if fail_alloc else address)
        elif operation == 4: freed.append(uc.reg_read(UC_ARM_REG_R0))
    mu.hook_add(UC_HOOK_CODE, hook, begin=STUB, end=STUB+0x50)
    mu.mem_write(TABLES, bytes(tables['luts'][case['colour']]))
    look = struct.pack('<4H256H', *tables['gains'], 0, *tables['light'])
    mu.mem_write(TABLES+0x8000, look)
    word = 0x10000 | 35 | (3<<8) | (0x20000 if case['colour']=='white' else 0)
    mu.mem_write(STASH, struct.pack('<I', word))
    ctx = struct.pack('<10I', *(STUB+i*16 for i in range(5)), STASH, TABLES, TABLES+0x8000, 1, case['mode']) + bytes(tables['params']) + struct.pack('<I', 0x344c4148) + bytes(1 if i==35 else 0 for i in range(64))
    mu.mem_write(CTX, ctx)
    for n, (_, w, h, ya, ca, _, _) in enumerate(planes):
        fmt = 2 if n==0 and case['primary']=='invalid' else 1
        mu.mem_write(DESC+n*32, struct.pack('<B3xIII4H2H4x', fmt, ya+64, ca+64, 0, w+int(odd), h, w+16, h, 0, 0))
    # Same-Y descriptor deliberately claims a larger whole-buffer width. Dedup must keep first valid crop.
    _, w, h, ya, ca, _, _ = planes[0]
    mu.mem_write(DESC+96, struct.pack('<B3xIII4H2H4x', 1, ya+64, ca+64, 0, w+(16 if case['primary']=='valid' else 0)+int(odd), h, w+16, h, 0, 0))
    primary = 0 if case['primary']=='missing' else DESC+32 if case['primary']=='preview' else DESC
    mu.mem_write(CONFIG+0x3c, struct.pack('<4I', primary, DESC+32, DESC+64, DESC+96))
    descriptors = bytes(mu.mem_read(DESC, 128))
    mu.reg_write(UC_ARM_REG_R0, CTX); mu.reg_write(UC_ARM_REG_R1, CONFIG)
    mu.reg_write(UC_ARM_REG_SP, STACK); mu.reg_write(UC_ARM_REG_LR, STUB+0x100)
    mu.emu_start(CODE_AT, STUB+0x100, count=8_000_000_000)
    assert mu.reg_read(UC_ARM_REG_PC)==STUB+0x100, 'module did not return'
    assert bytes(mu.mem_read(CTX,len(ctx)))==ctx, 'context changed'
    assert bytes(mu.mem_read(DESC,128))==descriptors, 'descriptor changed'
    assert bytes(mu.mem_read(TABLES,len(tables['luts'][case['colour']])))==bytes(tables['luts'][case['colour']]), 'LUT changed'
    assert bytes(mu.mem_read(TABLES+0x8000,len(look)))==look, 'look table changed'
    for address, length in allocations: assert bytes(mu.mem_read(address+length,32))==b'\x5a'*32, 'heap canary changed'
    if not fail_alloc: assert len(freed)==len(allocations), 'allocation leaked'
    for name, w, h, ya, ca, iy, ic in planes:
        for suffix, address, before in [('y', ya, iy), ('c', ca, ic)]:
            expected = before if fail_alloc or odd else (OUT/f'{index}-{name}-o{suffix}.bin').read_bytes()
            got = bytes(mu.mem_read(address,len(before)))
            if got != expected:
                bad = next(i for i,(a,b) in enumerate(zip(got,expected)) if a!=b)
                raise AssertionError(f'{case} {name} {suffix}: first difference at {bad}, {got[bad]} != {expected[bad]}')


def main():
    cases, tables = references()
    source = (ROOT/'core/src/fw/aspect/halation-code.ts').read_text(encoding='utf-8')
    code = base64.b64decode(re.search(r"HALATION_CODE = '([^']+)'",source)[1])
    for index, case in enumerate(cases):
        run(case,index,tables,code)
        print(f"ok {case['mode']} {case['colour']} {case['primary']} {case['width']}x{case['height']}: TS parity, descriptor/plane/heap canaries",flush=True)
    for index in [0, 1]:  # Both red and white paths, including all allocations made before output.
        run(cases[index],index,tables,code,fail_alloc=True)
        run(cases[index],index,tables,code,odd=True)
    print('ok allocation failure and odd 4:2:2 widths: every plane unchanged')
    # Independently tie the Python grain reference used by the native checker to production TypeScript.
    import importlib.util
    spec=importlib.util.spec_from_file_location('grain_check',ROOT/'tools/grain/check.py')
    grain=importlib.util.module_from_spec(spec);spec.loader.exec_module(grain)
    for mode in [1,2]:
        for setting in [1,2,3,5,6,7]:
            y,c=grain.test_picture(600,400,608,5),grain.test_colour(608,400,5)
            grain.reference(y,c,600,400,608,setting,mode,(3360,2240))
            assert bytes(y+c)==(OUT/f'grain-{mode}-{setting}.bin').read_bytes(),(mode,setting)
    print('ok grain geometry Python/TypeScript parity: both policies, six amount/size settings')


if __name__=='__main__':
    main()
