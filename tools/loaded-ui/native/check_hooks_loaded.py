"""Check the final film pack + Loaded stage 1 RTOS: film pack kept whole, five detours sound.

Same checks as tools/shot-animation/native/check_hooks_filmpack.py (silent), on the Loaded image.

Executes the real patched image. Only the added C callbacks are substituted, to
stress register, flag and stack preservation. No card or camera is accessed.
"""
import hashlib
import json
import struct
import sys
from pathlib import Path
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_PROT_READ, UC_PROT_EXEC
from unicorn import arm_const as reg

HERE = Path(__file__).resolve().parent
SOUND = False
import os
OUT = HERE.parent/'out'/{'diag': 'firmware-loaded-stage1d-diagnostic', 'diage': 'firmware-loaded-stage1e-diagnostic'}.get(os.environ.get('LOADED_VARIANT', ''), 'firmware-loaded-stage1')
BUILD = OUT/'build'
BASE = 0x53000000
STACK = 0x20010000
OBJECT = 0x10008000
STOP = 0x10000000
MASK = 0xf80f0000
CASES = [(0x532d55f8, 'grmod_on_shot', 0x532288b0, 'tail'),
         (0x5316caf8, 'grmod_before_transition', STOP, 'call'),
         (0x5316cb74, 'grmod_after_transition', 0x5316cb78, 'load'),
         (0x533918d0, 'grmod_before_canvas_delete', 0x533918d4, 'entry'),
         (0x53239818, 'grmod_cancel', 0x5323981c, 'entry')]
if SOUND:
    CASES.append((0x53568d58, 'grmod_before_audio_shutdown', 0x53568d5c, 'entry'))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify_pack_kept(image, pack, manifest, built, payload):
    """The whole point of this build: what the camera's saved settings need is untouched."""
    assert sha(pack) == manifest['packRtosSha256'], 'Wrong film pack RTOS'
    assert sha(image) == next(s['afterSha256'] for s in built['sections'] if s['name'] == 'RTOS'), 'Image differs from build report'
    allowed = {case[0] for case in CASES}
    changed = {BASE+i for i in range(0, len(pack), 4) if image[i:i+4] != pack[i:i+4]}
    assert changed == allowed, ('Film pack bytes changed outside the hooks', sorted(hex(a) for a in changed-allowed))
    at = manifest['base']-BASE
    assert at == len(pack) and image[at:at+len(payload)] == payload, 'Payload placement changed'
    assert sha(payload) == manifest['payloadSha256'], 'Payload digest changed'
    assert set(s['name'] for s in built['sections'] if s['beforeSha256'] != s['afterSha256']) == {'RTOS'}, 'Another section changed'
    assert struct.unpack_from('<I', image, 0x460)[0] == manifest['packZeroFillEnd'], 'Zero fill changed'
    if SOUND:
        assert manifest['silent'] is False and 'audioLatchWord' in manifest
        assert manifest['stateWord'] < manifest['audioLatchWord'] < manifest['packZeroFillEnd'], 'Latch must be zero-filled RAM'
        return
    # Silent: the audio shutdown site stays native, and the latch reads as shut down.
    assert image[0x53568d58-BASE:0x53568d58-BASE+4] == bytes.fromhex('0dc0a0e1'), 'Audio hook must stay unpatched'
    latch = manifest['audioLatchReadOnly']-BASE
    assert image[latch:latch+4] == struct.pack('<I', 1), 'Audio latch must read 1'


def main():
    manifest = json.loads((BUILD/'payload-manifest.json').read_text(encoding='utf-8'))
    built = json.loads((OUT/'build-report.json').read_text(encoding='utf-8'))
    image = (BUILD/'patched-rtos.bin').read_bytes()
    pack = (BUILD/'pack-rtos.bin').read_bytes()
    payload = (BUILD/'loaded-payload.bin').read_bytes()
    assert sha((BUILD/'loaded-payload.elf').read_bytes()) == manifest['elfSha256'], 'Linked ELF changed'
    with (BUILD/'loaded-payload.elf').open('rb') as stream:
        elf = ELFFile(stream)
        symbols = {s.name: s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols() if s.name}
        loaded = [s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD']
        assert len(loaded) == 1 and loaded[0].data() == payload, 'ELF and flat payload differ'
    assert symbols['grmod_adapter_state'] == manifest['stateWord']
    verify_pack_kept(image, pack, manifest, built, payload)

    # Regressions: a change to one film pack byte, or a missed hook, must be caught.
    rejected = []
    for name, position in (('film pack byte', 0x53d00000-BASE), ('appended film byte', len(pack)-64)):
        altered = bytearray(pack)
        altered[position] ^= 1
        try:
            verify_pack_kept(image, bytes(altered), {**manifest, 'packRtosSha256': sha(altered)}, built, payload)
        except AssertionError:
            rejected.append(name)
    missed = bytearray(image)
    missed[0x532d55f8-BASE:0x532d55f8-BASE+4] = pack[0x532d55f8-BASE:0x532d55f8-BASE+4]
    sections = [{**s, 'afterSha256': sha(missed)} if s['name'] == 'RTOS' else s for s in built['sections']]
    try:
        verify_pack_kept(bytes(missed), pack, manifest, {**built, 'sections': sections}, payload)
    except AssertionError:
        rejected.append('missed hook')
    assert rejected == ['film pack byte', 'appended film byte', 'missed hook'], rejected

    results = []
    for address, callback, destination, behavior in CASES:
        patch = next(p for p in built['patches'] if p['address'] == address)
        word, = struct.unpack_from('<I', image, address-BASE)
        delta = word & 0x00ffffff
        if delta & 0x00800000:
            delta -= 0x01000000
        assert address+8+delta*4 == symbols[patch['symbol']]
        assert (word >> 28) == 14 and (word & 0x0e000000) == 0x0a000000
        assert bool(word & 0x01000000) == (behavior == 'call')
        for flags in (0, 0xf80f0000, 0xa8050000, 0x500a0000):
            cpu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
            cpu.mem_map(BASE, (len(image)+4095) & ~4095, UC_PROT_READ | UC_PROT_EXEC)
            cpu.mem_write(BASE, image)
            cpu.mem_map(0x10000000, 0x10000)
            cpu.mem_map(0x20000000, 0x20000)
            cpu.mem_write(OBJECT+0x154, b'\xa7')
            cpu.mem_write(STACK-128, b'\xd3'*256)
            initial = [0x1000+i*0x100 for i in range(13)]
            initial[3] = STOP if behavior == 'call' else initial[3]
            initial[4] = OBJECT
            for i, value in enumerate(initial):
                cpu.reg_write(getattr(reg, 'UC_ARM_REG_R'+str(i)), value)
            cpu.reg_write(reg.UC_ARM_REG_SP, STACK)
            cpu.reg_write(reg.UC_ARM_REG_LR, STOP+4)
            cpu.reg_write(reg.UC_ARM_REG_CPSR, flags | 0x13)
            invoked, arrived = [], []

            def hook(uc, at, size, _):
                if at == symbols[callback]:
                    assert uc.reg_read(reg.UC_ARM_REG_SP) == STACK-32
                    if behavior == 'call':
                        assert uc.reg_read(reg.UC_ARM_REG_R1) == initial[5], 'destination ID must come from native R5'
                    invoked.append(uc.reg_read(reg.UC_ARM_REG_R0))
                    ret = uc.reg_read(reg.UC_ARM_REG_LR)
                    for i in (0, 1, 2, 3, 12):
                        uc.reg_write(getattr(reg, 'UC_ARM_REG_R'+str(i)), 0xabcdef00+i)
                    uc.reg_write(reg.UC_ARM_REG_CPSR, ((~flags) & MASK) | 0x13)
                    uc.reg_write(reg.UC_ARM_REG_PC, ret)
                elif at == destination:
                    arrived.append(at)
                    uc.emu_stop()
            cpu.hook_add(UC_HOOK_CODE, hook)
            cpu.emu_start(address, STOP+0x100, count=200)
            assert invoked == [initial[0]] and arrived == [destination]
            assert cpu.reg_read(reg.UC_ARM_REG_SP) == STACK
            assert cpu.reg_read(reg.UC_ARM_REG_CPSR) & MASK == flags
            assert cpu.reg_read(reg.UC_ARM_REG_LR) == (address+4 if behavior == 'call' else STOP+4)
            for i, value in enumerate(initial):
                expected = 0xa7 if behavior == 'load' and i == 3 else STACK if behavior == 'entry' and i == 12 else value
                assert cpu.reg_read(getattr(reg, 'UC_ARM_REG_R'+str(i))) == expected, (hex(address), flags, i)
            assert bytes(cpu.mem_read(STACK-128, 96)) == b'\xd3'*96
            assert bytes(cpu.mem_read(STACK, 128)) == b'\xd3'*128
            results.append(dict(site=hex(address), callback=callback, flags=hex(flags), nativeContinuation=hex(destination)))

    # The real start-up zero fill clears the animation's state word and stops at the heap header.
    cpu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    cpu.mem_map(BASE, 0x1000, UC_PROT_READ | UC_PROT_EXEC)
    cpu.mem_write(BASE, image[:0x1000])
    cpu.mem_map(0x55804000, 0x1000)
    start, end = 0x558043a0, manifest['packZeroFillEnd']
    cpu.mem_write(start-4, b'\xd3'*(end-start+12))
    cpu.reg_write(reg.UC_ARM_REG_R1, start)
    cpu.emu_start(0x530003ac, 0x530003c8, count=200)
    assert start <= manifest['stateWord'] < end
    assert not SOUND or start <= manifest['audioLatchWord'] < end
    assert bytes(cpu.mem_read(start, end-start)) == bytes(end-start)
    assert bytes(cpu.mem_read(end, 8)) == b'\xd3'*8, 'Heap header must survive'
    report = dict(schema=1, patchedRtosSha256=sha(image), payloadSha256=manifest['payloadSha256'],
                  packRtosSha256=manifest['packRtosSha256'], filmPackBytesKept=True, regressionsRejected=rejected,
                  detourCases=results, zeroFillClearsStateWord=True, heapHeaderPreserved=True, hardwareTested=False)
    (OUT/'hooks-verification.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps(dict(detourCases=len(results), filmPackBytesKept=True, regressionsRejected=rejected,
                          zeroFillClearsStateWord=True, heapHeaderPreserved=True, hardwareTested=False), indent=2))


if __name__ == '__main__':
    main()
