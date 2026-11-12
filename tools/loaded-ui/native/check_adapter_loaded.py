"""Run the Loaded stage 1 adapter inside the final film pack + Loaded RTOS, in the emulator.

The adapter, the Loaded renderer and the original native UI, view-tree, timer, clock and RGBA copier bodies execute
from the delivered image. Boundaries (allocator, OS clock and alarms, diagnostic sink, App/UI lookup inputs, the
settings record) are substituted by tools/shot-animation/native/check_adapter.Fixture. This is not a camera or
display test. The pixels the adapter produces are compared with the JS reference.
"""
import hashlib
import json
import struct
import subprocess
import sys
import zlib
from pathlib import Path
from unicorn import UC_HOOK_CODE

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
LAB = HERE.parent
sys.path.insert(0, str(LAB.parent/'shot-animation'/'native'))
import check_adapter as ca  # noqa: E402

import os
OUT = LAB/'out'/{'diag': 'firmware-loaded-stage1d-diagnostic', 'diage': 'firmware-loaded-stage1e-diagnostic', 'diagf': 'firmware-loaded-stage1f-diagnostic', 'diagg': 'firmware-loaded-stage1g-diagnostic'}.get(os.environ.get('LOADED_VARIANT', ''), 'firmware-loaded-stage1')
BUILD = OUT/'build'
LV, QV, OTHER, SERVICE = ca.LV, ca.QV, ca.OTHER, ca.SERVICE
RECORD = ca.RECORD
USERDATA_MODEL = 0x55063f30
VIEWS = [(0, 0, 720, 44), (0, 436, 720, 44), (612, 380, 108, 48), (0, 376, 128, 56)]      # top, bottom, counter, tab
NAMES = ['top', 'bottom', 'counter', 'tab']
AUDIO_ENTRIES = {0x53568e58, 0x53568ec0, 0x53568f8c, 0x53567004, 0x53566b74, 0x535677a8, 0x5320b31c, 0x53246528,
                 0x5324651c, 0x536aef0c, 0x536ae71c, 0x536ae870}
ALLOCS = ('state', 'top buffer', 'bottom buffer', 'counter buffer', 'tab buffer')


class LoadedFixture(ca.Fixture):
    def __init__(self, data, segments, symbols):
        self.fail_at = set()
        self.alloc_count = 0
        self.audio_calls = []
        super().__init__(data, segments, symbols)
        for at in AUDIO_ENTRIES - {0x5320b31c}:
            self.uc.hook_add(UC_HOOK_CODE, lambda cpu, a, s, u: self.audio_calls.append(a), begin=at, end=at)
        # the settings object (the singleton 0x5320b31c returns) holds the record in use at +4, as on the camera
        self.put(USERDATA_MODEL + 4, RECORD)
        self.layout = [self.symbol_word('grmod_layout', i) for i in range(6)]

    def symbol_word(self, name, index):
        return struct.unpack_from('<I', self.uc.mem_read(self.symbols[name] + 4 * index, 4))[0]

    def _hook(self, cpu, at, size, user):
        if at in (0x536af2a8, 0x536af31c):
            n = self.alloc_count
            self.alloc_count += 1
            if n in self.fail_at:
                self.ret(0)
                return
        super()._hook(cpu, at, size, user)

    # ---- helpers
    def record(self, movie=0, active=0, looks=(11, 11, 11)):
        self.uc.mem_write(RECORD + 0x44, bytes([movie]))
        self.uc.mem_write(RECORD + 0x1c0, bytes([active]))
        self.uc.mem_write(RECORD + 0x1c2, bytes([looks[0], 0, looks[1], 0, looks[2]]))

    def state(self):
        return self.get(ca.ANCHOR)

    def adapter_views(self):
        s = self.state()
        return [self.get(s + self.layout[0] + 4 * i) for i in range(4)]

    def hashes(self):
        s = self.state()
        out = []
        for i, (_, _, w, h) in enumerate(VIEWS):
            ptr = self.get(s + self.layout[1] + 4 * i)
            out.append(zlib.crc32(bytes(self.uc.mem_read(ptr, w * h * 4))))
        return out

    def shots(self):
        return self.get(self.state() + self.layout[2])

    def set_shots(self, n):
        self.put(self.state() + self.layout[2], n)

    def pending_roll(self):
        return self.get(self.state() + self.layout[3])


def js_hashes(cases):
    out = subprocess.run(['node', str(HERE/'export-adapter-hashes.mjs')], input=json.dumps(cases), capture_output=True, text=True,
                         check=True, cwd=str(LAB))
    return json.loads(out.stdout)


def jscase(moment, film, frame, roll, t, peek=None, hold=0):
    # stage 1: the adapter starts the peek clock at the shot, so during a moment the clock equals the elapsed time
    if peek is None:
        peek = -1 if moment == 'live' else t
    return dict(moment=moment, film=film, frame=frame, roll=roll, t=t, tabMode=1, counterMode=1, month=12, year=0, peek=peek, hold=hold)


def verify(data, segments, symbols):
    checks = []
    counts = {}

    def new():
        p = LoadedFixture(data, segments, symbols)
        p.uc.mem_unmap(SERVICE & ~0xfff, 0x1000)       # the audio service is not even mapped: nothing may reach it
        p.record(0, 0, (64 + 11, 11, 11))              # Portra 400 in the standard photo set
        return p

    def ok(cond, msg):
        counts['assertions'] = counts.get('assertions', 0) + 1
        assert cond, msg

    p = new()
    ok(p.get(ca.ANCHOR) == 0, 'State word must start clear')

    # ---- 1. the selected film: the adapter's read against the camera's own getter and the film pack's own layout
    sel = p.symbols['loaded_selected_film']
    slots = json.loads((BUILD/'payload-manifest.json').read_text(encoding='utf-8'))['slots']
    NEUTRAL = 21
    slot_film = {x['look']: x['film'] for x in slots}                                  # generated from the names read out of the image
    expected_of_look = lambda look: slot_film.get(look, NEUTRAL)
    cases = 0
    for active in (0, 1, 2):
        for look in list(range(11, 23)) + list(range(64, 84)) + [0, 10, 23, 63, 84, 255]:
            looks = [11, 11, 11]
            looks[active] = look
            p.record(0, active, tuple(looks))
            got = p.call(sel)
            ok(got == expected_of_look(look), f'film read: set {active} look {look}: {got}')
            cases += 1
    # the camera's own Image Control line getter (0x5326c1cc, original body in the film pack image) agrees for set 0
    p.put(0x62027000 + 4, RECORD)
    for look in range(64, 84):
        p.record(0, 0, (look, 11, 11))
        ok(p.call(0x5326c1cc, 0x62027000) == look, f'camera getter for film look {look}')
        ok(p.call(sel) == expected_of_look(look), 'adapter and camera getter disagree')
        cases += 1
    for active, menu_id in ((1, 0x17), (2, 0x18)):    # custom sets: the camera's getter reports the custom entry, the look byte is the set's film
        p.record(0, active, (11, 64 + 12, 64 + 13))
        ok(p.call(0x5326c1cc, 0x62027000) == menu_id, 'camera getter custom set')
        ok(p.call(sel) == (12 if active == 1 else 13), 'adapter reads the active custom set look')
        cases += 2
    # unreadable settings leave no animation: movie flag, bad set, null / misaligned / out of range pointer
    p.record(1, 0, (64, 11, 11)); ok(p.call(sel) == 0xffffffff, 'movie flag')
    p.record(0, 3, (64, 64, 64)); ok(p.call(sel) == 0xffffffff, 'active set 3')
    for pointer in (0, RECORD + 1):
        p.put(USERDATA_MODEL + 4, pointer); ok(p.call(sel) == 0xffffffff, f'record pointer {pointer:#x}')
    p.put(USERDATA_MODEL + 4, RECORD)
    p.record(0, 0, (64 + 11, 11, 11))
    checks.append(f'selected film: {cases} cases, adapter read equals the film pack\'s layout and the camera\'s own getter 0x5326c1cc; '
                  'movie flag, bad set, null and misaligned record pointers give no film')

    # the slot table: re-read from the base RTOS, equal to the manifest; a base with an unknown film is refused
    sys.path.insert(0, str(HERE))
    import link_loaded as linker
    reread = linker.read_slot_names((BUILD/'pack-rtos.bin').read_bytes())
    ok([(x['slot'], x['look'], x['name']) for x in reread] == [(x['slot'], x['look'], x['name']) for x in slots], 'slot names re-read from the image')
    ok(len(slots) == 20 and all(x['film'] == dict(linker.loaded_films()[i][::-1] for i in range(len(linker.loaded_films())))[x['name']] for x in slots), 'every slot has its Loaded film by name')
    refused = False
    try:
        linker.match_slots([dict(slot=0, look=64, name='Not A Loaded Film')], linker.loaded_films())
    except ValueError as error:
        refused = 'Not A Loaded Film' in str(error)
    ok(refused, 'a slot without a Loaded film must refuse the base')
    checks.append('the slot table: the 20 names re-read from the delivered base equal the manifest, each matches a Loaded film by name, and a slot without one is refused')

    # ---- 2. one completed shot: four owned views, one timer, frame 1 roll 1, pixels equal to the JS reference
    p = new()
    baseline = len(p.allocations)
    p.call('grmod_on_shot')
    root = p.roots[0]
    kids = p.children(root)
    ok(len(kids) == 4, 'A shot must attach four owned native views')
    ok(kids == p.adapter_views(), 'Children must be the adapter\'s views, in attach order (top, bottom, counter, tab)')
    ok(all(p.get(v + 4) == root for v in kids), 'Every view must have the root as parent')
    ok(len(p.timers()) == 1, 'One UI timer')
    allocs = [size for _, size in p.allocations[baseline:]]
    ok(allocs[:5] == [p.layout[5], 126720, 126720, 20736, 28672] and allocs[5:9] == [248] * 4, ('allocations', allocs))
    expected = js_hashes([jscase('shot', 11, 1, 1, 0)])[0]
    ok(p.hashes() == expected[1:], 'first frame differs from the JS reference')
    ok(p.audio_calls == [], 'audio entry reached')
    checks.append('a shot attaches four views (top, bottom, counter, tab) and one timer with five allocations (state + four pixel buffers); '
                  'first frame equals the JS reference')
    times = [0, 33, 99, 330, 561, 891, 1089, 1452, 1485]
    sample = js_hashes([jscase('shot', 11, 1, 1, t) for t in times])
    done = 0
    for t, want in zip(times, sample):
        if t:
            p.fire(t - done)
            done = t
        ok(p.hashes() == want[1:], f'frame at +{t} ms differs from the JS reference')
    # the strips leave at the deadline; the counter and tab linger and slide out; everything is gone after 2.0 s
    for pe in (1500, 1533, 1764, 1989):
        p.fire(pe - done); done = pe
        ok(len(p.children(root)) == 4 and len(p.timers()) == 1, f'views and timer stay through the linger (+{pe})')
        ok(p.hashes() == js_hashes([jscase('live', 11, 2, 1, 0, peek=pe)])[0][1:], f'linger frame at +{pe} differs from the JS reference')
        ok(p.hashes()[0] == zlib.crc32(bytes(720 * 44 * 4)) and p.hashes()[1] == zlib.crc32(bytes(720 * 44 * 4)), 'the strips are gone')
    p.fire(2010 - done)
    ok(not p.children(root) and not p.timers(), 'Everything must be gone after the peek window (about 2.0 s)')
    checks.append(f'{len(times)} frames across the 1500 ms shot equal the JS reference (peek clock at the shot); 4 linger frames after the deadline equal the JS reference; the views and the timer are gone at 2.0 s')

    # ---- 2b. a clean root (the camera has just painted): the new views must be laid out by the original layout pass (their absolute rectangles)
    p2 = new()
    r2 = p2.roots[0]
    p2.call(0x53391b14, r2)                              # a paint pass: layout runs and the root's flags are cleared
    ok(tuple(p2.uc.mem_read(r2 + 0x9c, 2)) == (0, 0), 'the root is clean')
    p2.call('grmod_on_shot')                             # the shot attaches brand new views to the clean root
    p2.call(0x53391b14, r2)
    for i, (x, y, w, h) in enumerate(VIEWS):
        got = struct.unpack('<4i', p2.uc.mem_read(p2.adapter_views()[i] + 0x30, 16))
        ok(got == (x, y, w, h), f'a view attached to a clean root must be laid out: {NAMES[i]} {got}')
    checks.append('views attached to a root that has just been painted get their absolute rectangles from the original layout pass (the root is asked to lay out its new children)')

    # ---- 3. real Canvas drawing through the original native copier; canaries; the draw checks per view
    p.set_shots(0)
    p.now = 5000
    p.call('grmod_on_shot')
    p.fire(700)
    p.call(0x53391b14, root)                              # the native canvas draws its children: our Draw callbacks run
    visible = bytes(p.uc.mem_read(ca.DEST + 32, 736 * 480 * 4))
    for i, (x, y, w, h) in enumerate(VIEWS):
        view = p.adapter_views()[i]
        ok(p.uc.mem_read(view + 0xa0, 1) == b'\0', 'base Draw bookkeeping must have run')
        covered = any(visible[((y + yy) * 736 + x + xx) * 4 + 3] != 0xa5 for yy in range(0, h, 4) for xx in range(0, w, 4))
        if NAMES[i] in ('top', 'bottom', 'tab', 'counter'):
            ok(covered, f'{NAMES[i]} view drew nothing into the canvas')
    p.canaries()
    checks.append('the original canvas draw reaches all four custom Draw callbacks; each view\'s pixels land in its own rectangle; canaries intact')
    surface = p.get(root + 0xec)
    length = 736 * 480 * 4
    for i, (x, y, w, h) in enumerate(VIEWS):
        view = p.adapter_views()[i]
        background = b'\xa5' * length
        for case in ('offscreen', 'format', 'stride', 'clip_overflow', 'hidden', 'wrong_size'):
            p.uc.mem_write(ca.DEST + 32, background)
            p.uc.mem_write(view + 0x30, struct.pack('<4i', x, y, w, h))
            p.uc.mem_write(view + 0x64, struct.pack('<4i', x, y, w, h))
            p.uc.mem_write(view + 0x9e, b'\x01')
            p.uc.mem_write(surface + 2, b'\x05')
            p.uc.mem_write(surface + 0x18, struct.pack('<H', 736))
            if case == 'offscreen':
                p.uc.mem_write(view + 0x30, struct.pack('<4i', 800, 600, w, h))
            elif case == 'format':
                p.uc.mem_write(surface + 2, b'\x04')
            elif case == 'stride':
                p.uc.mem_write(surface + 0x18, struct.pack('<H', 719))
            elif case == 'clip_overflow':
                p.uc.mem_write(view + 0x64, struct.pack('<4i', 0x7fffffff, y, w, h))
            elif case == 'wrong_size':
                p.uc.mem_write(view + 0x30, struct.pack('<4i', x, y, w + 1, h))
            else:
                p.uc.mem_write(view + 0x9e, b'\0')
            p.uc.mem_write(view + 0xa0, b'\x01')
            p.call('grmod_draw', view, surface)
            ok(bytes(p.uc.mem_read(ca.DEST + 32, length)) == background, f'{NAMES[i]} {case}: pixels written')
            ok(p.uc.mem_read(view + 0xa0, 1) == b'\0', f'{NAMES[i]} {case}: base Draw must always run')
        # a clipped draw (negative origin, partial clip): only the visible part of this view's own pixels is copied
        ptr = p.get(p.state() + p.layout[1] + 4 * i)
        rgba = b''.join(struct.pack('<I', 0xff000000 | xx | (yy << 8)) for yy in range(h) for xx in range(w))
        p.uc.mem_write(ptr, rgba)
        p.uc.mem_write(view + 0x9e, b'\x01'); p.uc.mem_write(surface + 2, b'\x05'); p.uc.mem_write(surface + 0x18, struct.pack('<H', 736))
        p.uc.mem_write(ca.DEST + 32, background)
        ox, oy = -17, -9
        p.uc.mem_write(view + 0x30, struct.pack('<4i', ox, oy, w, h))
        p.uc.mem_write(view + 0x64, struct.pack('<4i', 0, 0, w - 31, h - 5))
        p.call('grmod_draw', view, surface)
        expected = bytearray(background)
        for yy in range(0, min(h - 5, h + oy)):
            for xx in range(0, min(w - 31, w + ox)):
                src = ((yy - oy) * w + (xx - ox)) * 4
                expected[(yy * 736 + xx) * 4:(yy * 736 + xx) * 4 + 4] = rgba[src:src + 4]
        ok(bytes(p.uc.mem_read(ca.DEST + 32, length)) == bytes(expected), f'{NAMES[i]}: clipped copy differs')
    p.canaries()
    checks.append('per view: six rejected draws (off screen, wrong format, bad stride, clip overflow, hidden, wrong size) write nothing and always reach base Draw; '
                  'a clipped draw with a negative origin copies exactly the visible part of that view\'s pixels')

    # ---- 4. transitions mid-moment, menu / playback, a second shot, cancel, canvas deletion
    p = new()
    p.call('grmod_on_shot')
    root = p.roots[0]
    p.call('grmod_before_transition', LV, 0x08000020)       # a menu-like destination: cancel before the old screen exits
    ok(not p.children(root) and not p.timers(), 'menu destination must cancel')
    p.active = OTHER
    p.call('grmod_after_transition')
    p.active = LV
    p.now = 1000 + 3000
    p.call('grmod_on_shot')
    p.now = 4000 + 400
    p.call('grmod_before_transition', LV, 0x0800000c)       # live view -> review: detach but keep the deadline
    ok(not p.children(root) and not p.timers(), 'detach on a shooting transition')
    p.active = QV
    p.call('grmod_after_transition')
    ok(p.children(p.roots[1]) == p.adapter_views(), 'reattach all four views, same objects, same order')
    ok(len(p.timers()) == 1, 'timer re-armed after the transition')
    p.fire(100)
    ok(p.hashes() == js_hashes([jscase('shot', 11, 2, 1, 500)])[0][1:], 'moment continues across the transition (elapsed 500 ms)')
    p.now = 4000 + 900
    p.call('grmod_before_transition', QV, 0x08000000)
    p.active = LV
    p.call('grmod_after_transition')
    ok(p.children(root) == p.adapter_views(), 'reattached to live view')
    p.fire(599)
    ok(len(p.children(root)) == 4, 'still running at 1499 ms')
    p.fire(1)
    ok(len(p.children(root)) == 4 and len(p.timers()) == 1, 'the moment ends at its deadline; the counter and tab linger')
    # a transition during the linger detaches and reattaches the same views and keeps the peek window
    p.now = 5500 + 100
    p.call('grmod_before_transition', LV, 0x0800000c)
    ok(not p.children(root) and not p.timers(), 'detach during the linger')
    p.active = QV
    p.call('grmod_after_transition')
    ok(p.children(p.roots[1]) == p.adapter_views(), 'reattach during the linger')
    p.fire(100)
    ok(p.hashes() == js_hashes([jscase('live', 11, 3, 1, 0, peek=1700)])[0][1:], 'linger frame after a transition (+1700)')
    p.now = 5500 + 150
    p.call('grmod_before_transition', QV, 0x08000000)
    p.active = LV
    p.call('grmod_after_transition')
    # a new shot during the linger: no second set of views, one timer, the furniture is held (no new slide in)
    p.call('grmod_on_shot')
    ok(len(p.children(root)) == 4 and len(p.timers()) == 1, 'a shot during the linger reuses the views and the timer')
    nshots = p.shots()
    p.fire(330)
    ok(p.hashes() == js_hashes([jscase('shot', 11, (nshots - 1) % 36 + 1, 1, 330, peek=330 + 180)])[0][1:], 'a shot during the linger continues without a new slide-in')
    p.fire(1500 - 330 + 100)
    p.call('grmod_cancel')                                   # cancel during the linger
    ok(not p.children(root) and not p.timers(), 'cancel during the linger clears at once')
    p.call('grmod_on_shot')
    p.fire(2010)
    ok(not p.children(root) and not p.timers(), 'deadline and peek window end the sequence')
    checks.append('menu and playback destinations cancel; live view and photo review keep four views through the moment and the linger; a transition, a second shot and a cancel during the linger behave as during the moment')
    for _ in range(5):                                       # repeated shots (also while one runs) never add views or timers
        p.call('grmod_on_shot')
    ok(len(p.children(root)) == 4 and len(p.timers()) == 1, 'second shot mid-moment replaces the first')
    p.fire(560)
    ok(p.hashes() == js_hashes([jscase('shot', 11, (p.shots() - 1) % 36 + 1, 1 + (p.shots() - 1) // 36, 560, peek=560 + 180)])[0][1:], 'the last shot shows its own frame from its own start')
    p.call('grmod_cancel')
    ok(not p.children(root) and not p.timers(), 'cancel clears at once')
    p.call('grmod_on_shot')
    p.call(0x533918d0, root)                                 # the patched native canvas destructor, through its real detour
    ok(not p.timers(), 'canvas deletion must cancel')
    p.fire()
    ok(not p.timers(), 'a late tick uses nothing freed')
    checks.append('a second shot mid-moment restarts it with the next frame number and no extra view or timer; cancel and canvas deletion detach at once')
    p.canaries()

    # ---- 5. allocation failure at each allocation: no animation, everything released, nothing else
    for n, label in enumerate(ALLOCS):
        q = new()
        base = len(q.allocations)
        q.fail_at = {n}; q.alloc_count = 0
        q.call('grmod_on_shot')
        ok(q.get(ca.ANCHOR) == 0 and not q.children(q.roots[0]) and not q.timers(), f'failure of {label}: left state, views or a timer')
        ok(sorted(q.frees) == sorted(ptr for ptr, _ in q.allocations[base:]), f'failure of {label}: allocated pieces must all be freed')
        ok(len(q.allocations) - base == n, f'failure of {label}: allocation sequence')
        q.fail_at = set(); q.alloc_count = 0
        q.call('grmod_on_shot')
        ok(len(q.children(q.roots[0])) == 4, f'after a failed {label}, the next shot must work')
        q.canaries()
    checks.append('an allocation failure at each of the five allocations leaves no state, view or timer, frees the earlier pieces, and the next shot works')

    # ---- 6. unknown film, bad settings, clock failure, clock wrap
    q = new()
    q.record(0, 0, (11, 11, 11))                              # the camera's own Standard look
    q.call('grmod_on_shot')
    ok(len(q.children(q.roots[0])) == 4, 'a non-film look must still play the neutral strip')
    ok(q.hashes() == js_hashes([jscase('shot', NEUTRAL, 1, 1, 0)])[0][1:], 'neutral GR III strip must equal the JS reference')
    q.record(0, 0, (64 + 0, 11, 11))                          # slot 0 of this base is Pro 400H: a film of its own
    q.call('grmod_on_shot')
    ok(q.hashes() == js_hashes([jscase('shot', 20, 2, 1, 0, peek=180)])[0][1:], 'slot 0 is Pro 400H, not the neutral strip')
    q.call('grmod_cancel')
    q.record(1, 0, (64 + 11, 11, 11))                         # movie mode: no animation
    q.call('grmod_on_shot')
    ok(not q.children(q.roots[0]) and not q.timers(), 'movie flag: no animation')
    q.record(0, 0, (64 + 11, 11, 11))
    q.put(USERDATA_MODEL + 4, 0)
    q.call('grmod_on_shot')
    ok(not q.children(q.roots[0]), 'no record: no animation')
    q.put(USERDATA_MODEL + 4, RECORD)
    q.clock_ok = False
    q.call('grmod_on_shot')
    ok(not q.children(q.roots[0]) and not q.timers(), 'bad clock: no animation')
    q.clock_ok = True
    q.active = OTHER
    q.call('grmod_on_shot')
    ok(not q.children(q.roots[0]) and not q.timers(), 'unexpected controller: no animation')
    q.active = LV
    q.now = 0xfffffff0
    q.call('grmod_on_shot')
    q.fire(1499)
    ok(len(q.children(q.roots[0])) == 4, 'running at 1499 ms across the clock wrap')
    q.fire(1)
    ok(len(q.children(q.roots[0])) == 4, 'lingering after the deadline across the wrap')
    q.fire(501)
    ok(not q.children(q.roots[0]) and not q.timers(), 'the 2.0 s sequence ends across the 32-bit wrap')
    q.canaries()
    checks.append('a non-film look plays the neutral strip and slot 0 plays Pro 400H; movie mode, no settings record, bad clock and an unexpected controller give no animation; '
                  'the 2.0 s sequence holds across the 32-bit clock wrap')

    # ---- 7. frame 36 leads into the end of the roll, every film and format through the payload
    q = new()
    q.call('grmod_on_shot')
    q.set_shots(35)
    q.call('grmod_on_shot')
    ok(q.pending_roll() == 1, 'frame 36 must schedule the end of the roll')
    q.fire(700)
    ok(q.hashes() == js_hashes([jscase('shot', 11, 36, 1, 700)])[0][1:], 'frame 36 shot')
    q.fire(800)                                                # 1500: the shot is over, the roll moment starts
    ok(len(q.children(q.roots[0])) == 4 and q.pending_roll() == 0, 'the end of the roll follows once')
    ok(q.hashes() == js_hashes([jscase('roll', 11, 36, 1, 0, peek=-1, hold=1)])[0][1:], 'roll moment first frame: the counter and tab are already showing (no pop)')
    done = 0
    roll_times = [297, 990, 1485, 2013, 2706, 2871, 3366]
    for t, want in zip(roll_times, js_hashes([jscase('roll', 11, 36, 1, t, peek=-1, hold=1) for t in roll_times])):
        q.fire(t - done); done = t
        ok(q.hashes() == want[1:], f'roll frame at +{t} differs from the JS reference')
    q.fire(3400 - done); done = 3400                           # the roll's deadline: the strips go, the counter shows 1 and lingers
    ok(len(q.children(q.roots[0])) == 4, 'the roll lingers')
    ok(q.hashes() == js_hashes([jscase('live', 11, 1, 1, 0, peek=1500)])[0][1:], 'the counter shows 1 after the roll')
    q.fire(33); done += 33
    ok(q.hashes() == js_hashes([jscase('live', 11, 1, 1, 0, peek=1533)])[0][1:], 'roll linger frame (+33)')
    q.fire(520)
    ok(not q.children(q.roots[0]) and not q.timers(), 'the end of the roll is gone 0.5 s after the film')
    q.call('grmod_on_shot')                                    # the next shot is frame 1 of roll 2
    q.fire(330)
    ok(q.hashes() == js_hashes([jscase('shot', 11, 1, 2, 330)])[0][1:], 'frame 1 of the next roll')
    checks.append('frame 36 plays its shot, then the end of the roll (3400 ms, 7 frames equal the JS reference), lingers 0.5 s with the counter at 1 (no pop between the two moments), then clears; the next shot is frame 1 of roll 2')
    # every film kind through the payload, three times each
    spec = [(film, t) for film in (1, 8, 10, 12, 13, 17, 18, 20, 21) for t in (231, 561, 1089)]
    want_all = js_hashes([jscase('shot', film, 1, 1, t) for film, t in spec])
    for (film, t), want in zip(spec, want_all):
        q = new()
        q.record(0, 0, ({v: k for k, v in slot_film.items()}[film] if film < 21 else 11, 11, 11))
        q.call('grmod_on_shot')
        q.fire(t)
        ok(q.hashes() == want[1:], f'film {film} at +{t} differs from the JS reference')
    checks.append(f'{len(spec)} further film / time cases (slide, negative, b&w, cine, instant, neutral) equal the JS reference through the linked payload')

    # ---- 8. many shots: no growth, frame and roll numbers advance, the heap is not touched again
    q = new()
    q.call('grmod_on_shot')
    count = len(q.allocations)
    nfrees = len(q.frees)
    for i in range(1, 80):
        q.now += 2000
        q.call('grmod_on_shot')
        q.call('grmod_cancel')
    ok(len(q.allocations) == count and len(q.frees) == nfrees, 'repeated shots must reuse the single allocation set')
    ok(q.shots() == 80, 'every completed shot counts')
    q.call('grmod_on_shot')
    q.fire(330)
    ok(q.hashes() == js_hashes([jscase('shot', 11, 81 % 36 or 36, 1 + 80 // 36, 330)])[0][1:], 'frame and roll numbers advance with the shot count')
    q.canaries()
    checks.append('80 shots: one allocation set, no frees, frame and roll numbers follow the shot count (frame 9 of roll 3 on the 81st)')

    ok(p.audio_calls == [] and q.audio_calls == [], ('audio entries reached', p.audio_calls))
    checks.append('no audio, mute, volume, mutex or user-data service is reached in any scenario (the audio service page is unmapped)')
    state_alloc = next(size for ptr, size in q.allocations if ptr == q.get(ca.ANCHOR))
    return dict(checks=checks, assertions=counts['assertions'], state_pointer=hex(q.get(ca.ANCHOR)), state_allocation_bytes=state_alloc,
                pixel_buffer_bytes=[126720, 126720, 20736, 28672], total_heap_bytes=state_alloc + 302848,
                hardware_tested=False, physical_display_tested=False, dma_cache_tested=False,
                simulated_boundaries=['allocator', 'OS clock and alarms', 'diagnostic sink', 'App and UI lookup inputs', 'settings record bytes'])


def main():
    manifest = json.loads((BUILD/'payload-manifest.json').read_text(encoding='utf-8'))
    data = (BUILD/'patched-rtos.bin').read_bytes()
    elf_path = BUILD/'loaded-payload.elf'
    assert hashlib.sha256(elf_path.read_bytes()).hexdigest() == manifest['elfSha256'], 'Linked ELF changed'
    segments, symbols = ca.read_elf(elf_path)
    ca.SHA = hashlib.sha256(data).hexdigest()
    ca.ANCHOR = manifest['stateWord']
    ca.LATCH = manifest['audioLatchReadOnly']
    report = dict(patched_rtos_sha256=ca.SHA, payload_elf_sha256=manifest['elfSha256'], **verify(data, segments, symbols))
    (OUT/'adapter-verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'simulated_boundaries'}, indent=2))


if __name__ == '__main__':
    main()
