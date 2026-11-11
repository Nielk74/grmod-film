"""Bounded static GR III 2.10 string/instruction evidence, no live camera claims.

REA cannot open ARM raw binaries on this configured Windows host. This fallback
uses explicit source bytes and Capstone, preserves hashes, only disassembles
the known metadata extractor switch and diagnostic string sites.
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path
from capstone import Cs,CS_ARCH_ARM,CS_MODE_ARM
from audit import sha,write_json

EXPECTED='8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67'
CONTAINER='d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4'


def run(rtos,container,output):
    if sha(rtos)!=EXPECTED or sha(container)!=CONTAINER:raise ValueError('Exact official GR III 2.10 identities required')
    blob=Path(rtos).read_bytes();base=0x53000000
    strings=[]
    for m in re.finditer(rb'[ -~]{5,}',blob):
        s=m.group().decode('ascii')
        if re.search(r'FaceDetectArea|FaceDetectionConfig|FaceDetect.*Service',s):
            strings.append({'address':hex(base+m.start()),'value':s})
    dis=Cs(CS_ARCH_ARM,CS_MODE_ARM)
    ranges=[(0x535eee20,0x535eee5c),(0x535ef020,0x535ef078)]
    instructions=[]
    for start,end in ranges:
        instructions.extend({'address':hex(i.address),'bytes':i.bytes.hex(),'instruction':i.mnemonic+' '+i.op_str}
                            for i in dis.disasm(blob[start-base:end-base],start))
    result={'rtos_sha256':EXPECTED,'container_sha256':CONTAINER,'model':'GR III','version':'2.10',
            'basis':'Static byte/string/disassembly scan of separately extracted original RTOS; hash matches repository profile',
            'rea_blocker':'Windows REA raw ARM target unsupported; Ghidra missing; no live provider used',
            'strings':strings,'extractor_switch_instructions':instructions,
            'proven':'Metadata extractor has diagnostics for center/size lists; bounded switch compares legacy face tags 0x0227 and 0x0228',
            'unknowns':['Live face service API, count and owner','Shot-time boxes lifetime and synchronization','Coordinates relative to sensor/crop/rotation','Boxes availability at JpegEncodeMacroProcess::Execute','GR IIIx separately inspected here: no']}
    write_json(output,result);print('Saved',output)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('rtos',type=Path);ap.add_argument('container',type=Path)
    ap.add_argument('--output',type=Path,default=Path('scratch/face-fill/firmware-evidence.json'))
    a=ap.parse_args();run(a.rtos,a.container,a.output)
