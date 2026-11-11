"""Run the silent animation inside the final film pack + Terminal RTOS.

The adapter, renderer and original native UI, timer and clock bodies execute from
the delivered image, with the real artwork. OS, heap and device boundaries are
substituted by check_adapter.Fixture. This is not a camera or display test.
"""
import hashlib
import json
import sys
from pathlib import Path
from unicorn import UC_HOOK_CODE

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_adapter as ca  # noqa: E402

OUT = HERE.parent/'out'/'firmware-filmpack'
LV, QV, OTHER, SERVICE = ca.LV, ca.QV, ca.OTHER, ca.SERVICE
# Native audio and audio-setting entries the silent build must never reach.
AUDIO_ENTRIES = {0x53568e58: 'audio factory', 0x53568ec0: 'audio service', 0x53568f8c: 'WAV parse',
                 0x53567004: 'WAV start', 0x53566b74: 'WAV stop', 0x535677a8: 'volume set',
                 0x5320b31c: 'user data', 0x53246528: 'sound flag', 0x5324651c: 'sound volume',
                 0x536aef0c: 'mutex create', 0x536ae71c: 'mutex lock', 0x536ae870: 'mutex unlock'}


def watched(data, segments, symbols):
    fixture = ca.Fixture(data, segments, symbols)
    fixture.audio_calls = []

    def note(cpu, at, size, user):
        fixture.audio_calls.append(AUDIO_ENTRIES[at])
    for at in AUDIO_ENTRIES:
        fixture.uc.hook_add(UC_HOOK_CODE, note, begin=at, end=at)
    return fixture


def verify(data, segments, symbols):
    checks = []
    p = watched(data, segments, symbols)
    assert p.get(ca.ANCHOR) == 0, 'State word must start clear'
    # No audio at all: the service page is not even mapped while the animation runs.
    p.uc.mem_unmap(SERVICE & ~0xfff, 0x1000)
    p.call('grmod_on_shot')
    root = p.roots[0]
    assert len(p.children(root)) == 1, 'A shot must attach one owned native view'
    view = p.children(root)[0]
    assert p.get(view+4) == root and len(p.timers()) == 1
    checks.append('shot attaches one native view and one UI timer, with the audio service unmapped')
    for _ in range(2):
        p.fire(500)
    p.call(0x53391b14, root)
    assert p.uc.mem_read(view+0x40, 1) == b'\x01' and p.uc.mem_read(view+0xa0, 1) == b'\0'
    visible = bytes(p.uc.mem_read(ca.DEST+32, 736*480*4))
    assert any(visible[((259+y)*736+464+x)*4+3] for y in range(176) for x in range(240)), 'Frame must show owned pixels'
    p.canaries()
    checks.append('real artwork renders through the native Canvas, with canaries intact')
    ca.clipping(p, view, root)
    checks.append('clipped draws and five rejected draws stay in bounds and always reach base Draw')
    p.call('grmod_before_transition', LV, 0x08000020)
    assert not p.children(root) and not p.timers()
    p.active = OTHER
    p.call('grmod_after_transition')
    p.active = LV
    checks.append('menu, playback or other destinations cancel the animation before the old screen exits')
    p.now = 1000
    p.call('grmod_on_shot')
    old_timer, listener = p.timers()[0]
    p.call('grmod_timer_expired', listener, old_timer+123)
    assert p.timers() == [(old_timer, listener)]
    checks.append('a stale timer ID cannot consume the current timer')
    p.now = 4000
    p.call('grmod_before_transition', LV, 0x0800000c)
    assert not p.children(root) and not p.timers()
    p.active = QV
    p.call('grmod_after_transition')
    assert p.children(p.roots[1]) == [view]
    p.now = 6000
    p.call('grmod_before_transition', QV, 0x08000000)
    p.active = LV
    p.call('grmod_after_transition')
    assert p.children(root) == [view]
    p.fire(2599)
    assert p.children(root) == [view]
    p.fire(1)
    assert not p.children(root) and not p.timers()
    checks.append('live view and photo review keep one view and the full 7600 ms deadline, then clear')
    for _ in range(5):
        p.call('grmod_on_shot')
    assert p.children(root) == [view] and len(p.timers()) == 1
    p.call('grmod_cancel')
    assert not p.children(root) and not p.timers()
    checks.append('repeated shots replace the animation without a second view or timer; cancel clears at once')
    p.call('grmod_on_shot')
    p.call(0x533918d0, root)  # The patched native destructor, through its real detour.
    assert not p.timers()
    p.fire()
    assert not p.timers()
    checks.append('deleting the Canvas through the patched destructor detaches first; a late tick uses nothing freed')
    p.canaries()
    assert not p.audio_calls, ('Silent build reached audio', sorted(set(p.audio_calls)))
    assert not any(e[0] in ('mutex_create', 'lock', 'unlock') for e in p.events), 'Silent build must make no audio mutex'
    checks.append('the whole run reaches no audio, mute, volume or mutex service')

    q = watched(data, segments, symbols)
    q.clock_ok = False
    q.call('grmod_on_shot')
    assert not q.children(q.roots[0]) and not q.timers()
    q.clock_ok = True
    q.fail_alloc = True
    q.call('grmod_on_shot')
    assert q.get(ca.ANCHOR) == 0 and not q.timers()
    q.fail_alloc = False
    checks.append('clock and first allocation failures leave no view, timer or state')
    q.now = 0xfffffff0
    q.call('grmod_on_shot')
    q.fire(7599)
    assert q.children(q.roots[0])
    q.fire(1)
    assert not q.children(q.roots[0]) and not q.timers()
    checks.append('the 7600 ms deadline holds across the 32-bit millisecond wrap')
    q.canaries()
    assert not q.audio_calls
    state = p.get(ca.ANCHOR)
    return dict(checks=checks, state_pointer=hex(state),
                state_allocation_bytes=next(size for at, size in p.allocations if at == state),
                audio_reached=False, hardware_tested=False, physical_display_tested=False, dma_cache_tested=False,
                simulated_boundaries=['allocator', 'OS clock and alarms', 'diagnostic sink', 'App and UI lookup inputs'])


def main():
    # --sound: the full official-build scenario set (sound, mute, volume, busy service,
    # shutdown preemption across two CPU contexts), run inside the final film pack image.
    # The patched audio shutdown detour is live here, so native shutdown passes through it.
    sound = '--sound' in sys.argv
    out = HERE.parent/'out'/('firmware-filmpack-sound' if sound else 'firmware-filmpack')
    manifest = json.loads((out/'payload-manifest.json').read_text(encoding='utf-8'))
    data = (out/'patched-rtos.bin').read_bytes()
    elf_path = out/'terminal-payload.elf'
    assert hashlib.sha256(elf_path.read_bytes()).hexdigest() == manifest['elfSha256'], 'Linked ELF changed'
    segments, symbols = ca.read_elf(elf_path)
    ca.SHA = hashlib.sha256(data).hexdigest()
    ca.ANCHOR = manifest['stateWord']
    ca.LATCH = manifest['audioLatchWord' if sound else 'audioLatchReadOnly']
    report = dict(patched_rtos_sha256=ca.SHA, payload_elf_sha256=manifest['elfSha256'],
                  embedded_asset_sha256=hashlib.sha256(ca.embedded(segments, symbols, 'terminal_asset')).hexdigest(),
                  **(ca.verify(data, segments, symbols) if sound else verify(data, segments, symbols)))
    assert report['embedded_asset_sha256'] == manifest['asset']['sha256'], 'Embedded artwork differs'
    if sound:
        report['embedded_wave_sha256'] = {name: hashlib.sha256(ca.embedded(segments, symbols, 'terminal_wav_'+name)).hexdigest()
                                          for name in ('dash', 'portal', 'rocket')}
        assert report['embedded_wave_sha256'] == {k: v['sha256'] for k, v in manifest['waves'].items()}, 'Embedded sound differs'
    (out/'adapter-verification.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'simulated_boundaries'}, indent=2))


if __name__ == '__main__':
    main()
