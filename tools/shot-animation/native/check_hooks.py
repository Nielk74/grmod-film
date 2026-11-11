"""Execute the final firmware's six A32 detours and reserved-RAM startup loop.

Only the added C callbacks are substituted here to stress ABI preservation.
Their actual compiled bodies and native services are covered by check_adapter.
No card/camera is accessed. Run after linking and building the container.
"""
import hashlib
import json
import struct
from pathlib import Path
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_PROT_READ, UC_PROT_EXEC
from unicorn import arm_const as reg

HERE = Path(__file__).resolve().parent
OUT = HERE.parent/'out'/'firmware'
ROOT = HERE.parent.parent.parent
BASE = 0x53000000
STOCK_SHA = '8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67'
STACK = 0x20010000
OBJECT = 0x10008000
STOP = 0x10000000
MASK = 0xf80f0000


def verify_artifact_binding(manifest, built, image, payload, symbols):
    """A report may describe only the exact bytes/symbols it actually executes."""
    assert len(payload) == manifest['payloadBytes'], 'Payload length changed'
    assert hashlib.sha256(payload).hexdigest() == manifest['payloadSha256'], 'Payload digest changed'
    at = manifest['base']-BASE
    assert at == 17520064 and at+len(payload) <= len(image), 'Payload placement changed'
    assert image[at:at+len(payload)] == payload, 'Patched RTOS contains a different linked payload'
    section = next(s for s in built['sections'] if s['name'] == 'RTOS')
    assert hashlib.sha256(image).hexdigest() == section['afterSha256'], 'Patched RTOS differs from container build report'
    assert built['payloadBytes'] == len(payload), 'Container payload size changed'
    required = ['grmod_hook_shot', 'grmod_hook_transition_before', 'grmod_hook_transition_after',
                'grmod_hook_canvas_delete', 'grmod_hook_release', 'grmod_hook_audio_shutdown', 'grmod_on_shot',
                'grmod_before_transition', 'grmod_after_transition', 'grmod_before_canvas_delete',
                'grmod_cancel', 'grmod_before_audio_shutdown', 'grmod_adapter_state', 'grmod_audio_shutdown_latch']
    for name in required:
        assert symbols[name] == manifest['symbols'][name], 'ELF/manifest symbol differs: '+name


def main():
    manifest = json.loads((OUT/'payload-manifest.json').read_text(encoding='utf-8'))
    built = json.loads((OUT/'build-report.json').read_text(encoding='utf-8'))
    stock = (ROOT/'scratch'/'video-firmware-high-rate-2026-11-01'/'original-rtos.bin').read_bytes()
    assert hashlib.sha256(stock).hexdigest() == STOCK_SHA
    image = (OUT/'patched-rtos.bin').read_bytes()
    assert hashlib.sha256((OUT/'terminal-payload.elf').read_bytes()).hexdigest() == manifest['elfSha256'], 'Linked ELF changed'
    with (OUT/'terminal-payload.elf').open('rb') as stream:
        elf = ELFFile(stream)
        symbols = {s.name:s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols() if s.name}
        segments = [s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD']
        assert len(segments) == 1 and segments[0]['p_vaddr'] == manifest['base']
        elf_payload = segments[0].data()
    payload = (OUT/'terminal-payload.bin').read_bytes()
    assert elf_payload == payload, 'Linked ELF and flattened ARM payload differ'
    verify_artifact_binding(manifest, built, image, payload, symbols)
    # Regression: changing an otherwise unused appended byte used to escape the
    # detour tests while the report copied a newer manifest's hash verbatim.
    altered = bytearray(image)
    altered[manifest['base']-BASE+len(payload)-1] ^= 1
    try:
        verify_artifact_binding(manifest, built, altered, payload, symbols)
    except AssertionError:
        pass
    else:
        raise AssertionError('Stale-payload regression was not detected')
    cases = [
        (0x532d55f8, 'grmod_on_shot', 0x532288b0, 'tail'),
        (0x5316caf8, 'grmod_before_transition', STOP, 'call'),
        (0x5316cb74, 'grmod_after_transition', 0x5316cb78, 'load'),
        (0x533918d0, 'grmod_before_canvas_delete', 0x533918d4, 'entry'),
        (0x53239818, 'grmod_cancel', 0x5323981c, 'entry'),
        (0x53568d58, 'grmod_before_audio_shutdown', 0x53568d5c, 'entry'),
    ]
    results = []
    for address, callback, destination, behavior in cases:
        patch = next(p for p in built['patches'] if p['address'] == address)
        word, = struct.unpack_from('<I', image, address-BASE)
        delta = word & 0x00ffffff
        if delta & 0x00800000:
            delta -= 0x01000000
        assert address+8+delta*4 == manifest['symbols'][patch['symbol']]
        assert (word>>28) == 14 and (word&0x0e000000) == 0x0a000000
        assert bool(word&0x01000000) == (behavior == 'call')
        for flags in (0, 0xf80f0000, 0xa8050000, 0x500a0000):
            cpu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
            cpu.mem_map(BASE, (len(image)+4095)&~4095, UC_PROT_READ|UC_PROT_EXEC)
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
            cpu.reg_write(reg.UC_ARM_REG_CPSR, flags|0x13)
            invoked = []
            arrived = []
            def hook(uc, at, size, _):
                if at == symbols[callback]:
                    assert uc.reg_read(reg.UC_ARM_REG_SP) == STACK-32
                    if behavior == 'call':
                        assert uc.reg_read(reg.UC_ARM_REG_R1) == initial[5], 'destination ID must come from native R5'
                    invoked.append(uc.reg_read(reg.UC_ARM_REG_R0))
                    ret = uc.reg_read(reg.UC_ARM_REG_LR)
                    for i in (0, 1, 2, 3, 12):
                        uc.reg_write(getattr(reg, 'UC_ARM_REG_R'+str(i)), 0xabcdef00+i)
                    uc.reg_write(reg.UC_ARM_REG_CPSR, ((~flags)&MASK)|0x13)
                    uc.reg_write(reg.UC_ARM_REG_PC, ret)
                elif at == destination:
                    arrived.append(at)
                    uc.emu_stop()
            cpu.hook_add(UC_HOOK_CODE, hook)
            cpu.emu_start(address, STOP+0x100, count=200)
            assert invoked == [initial[0]] and arrived == [destination]
            assert cpu.reg_read(reg.UC_ARM_REG_SP) == STACK
            assert cpu.reg_read(reg.UC_ARM_REG_CPSR)&MASK == flags
            assert cpu.reg_read(reg.UC_ARM_REG_LR) == (address+4 if behavior == 'call' else STOP+4)
            for i, value in enumerate(initial):
                expected = 0xa7 if behavior == 'load' and i == 3 else STACK if behavior == 'entry' and i == 12 else value
                assert cpu.reg_read(getattr(reg, 'UC_ARM_REG_R'+str(i))) == expected, (hex(address), flags, i)
            assert bytes(cpu.mem_read(STACK-128, 96)) == b'\xd3'*96
            assert bytes(cpu.mem_read(STACK, 128)) == b'\xd3'*128
            results.append(dict(site=hex(address), callback=callback, flags=hex(flags), nativeContinuation=hex(destination)))

    # Execute the original zero-fill loop, with its actual patched literal and
    # a short suffix of the original BSS. The heap-side canary must survive.
    cpu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    cpu.mem_map(BASE, 0x1000, UC_PROT_READ|UC_PROT_EXEC)
    cpu.mem_write(BASE, image[:0x1000])
    cpu.mem_map(0x55804000, 0x1000)
    start, end = 0x5580436c, 0x55804380
    cpu.mem_write(start-4, b'\xd3'*(end-start+12))
    cpu.reg_write(reg.UC_ARM_REG_R1, start)
    cpu.emu_start(0x530003ac, 0x530003c8, count=100)
    assert bytes(cpu.mem_read(start, end-start)) == bytes(end-start)
    assert bytes(cpu.mem_read(start-4, 4)) == b'\xd3'*4
    assert bytes(cpu.mem_read(end, 8)) == b'\xd3'*8
    assert cpu.reg_read(reg.UC_ARM_REG_R1) == end
    assert manifest['symbols']['grmod_adapter_state'] == 0x55804374
    assert manifest['symbols']['grmod_audio_shutdown_latch'] == 0x55804378
    report = dict(schema=1, patchedRtosSha256=hashlib.sha256(image).hexdigest(),
                  payloadSha256=manifest['payloadSha256'], detourCases=results,
                  detourAssertions=len(results)*20, zeroFillNativeLoopPassed=True,
                  nativeHeapCanaryPreserved=True, artifactBindingVerified=True,
                  stalePayloadRegressionRejected=True, mutatedCallbacksOnly=True, hardwareTested=False)
    (OUT/'hooks-verification.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps(dict(detourCases=len(results), nativeBehaviorPreserved=True,
                          zeroFillNativeLoopPassed=True, heapCanaryPreserved=True, hardwareTested=False), indent=2))


if __name__ == '__main__':
    main()
