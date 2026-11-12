"""Stage 2a scenarios, run in the emulator on the delivered image (LOADED_VARIANT=stage2a).

The adapter, the Loaded renderer and the original native UI, view-tree, layout, timer, clock and RGBA copier bodies execute from the delivered
image. The camera's early event 0x013E is delivered to the C callback of the sixth hook (and ordinary events through the real trampoline and
dispatcher); the completion hook is the stage 1 hook. Boundaries (allocator, OS clock and alarms, settings record) are the Fixture's.
"""
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

os.environ['LOADED_VARIANT'] = 'stage2a'
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_adapter_loaded as cl  # noqa: E402
ca = cl.ca
OUT, BUILD = cl.OUT, cl.BUILD
VIEWS = cl.VIEWS
NAMES = cl.NAMES
LAYOUT = ['views', 'pixels', 'shots', 'pending_roll', 'engine', 'sizeof', 'pend', 'npend', 'last_accept', 'accepts', 'ignored', 'fallbacks', 'consumed', 'dropped',
          'running', 'params']
ARMED, FAILED = 0x55804390, 0x5580438c


class F(cl.LoadedFixture):
    def __init__(self, *a):
        super().__init__(*a)
        from unicorn import UC_HOOK_CODE
        self.factory_calls = 0
        self.fail_factory = set()
        self.uc.hook_add(UC_HOOK_CODE, self._factory, begin=0x533ad7f0, end=0x533ad7f0)
        self.M = dict(zip(LAYOUT, [self.symbol_word('grmod_layout', i) for i in range(len(LAYOUT))]))

    def _factory(self, cpu, at, size, user):
        n = self.factory_calls
        self.factory_calls += 1
        if n in self.fail_factory:
            self.ret(0)

    def v(self, name):
        return self.get(self.state() + self.M[name])

    def pend(self):
        return [self.get(self.state() + self.M['pend'] + 4 * i) for i in range(self.v('npend'))]

    def ev(self, ident, dt=0):
        self.now = (self.now + dt) & 0xffffffff
        self.uc.mem_write(ca.EVENT + 0x400, struct.pack('<HHI', ident, 0, 0))
        self.call('grmod_on_event', ca.APP, ca.EVENT + 0x400)

    def key(self, dt=0):
        self.ev(0x013e, dt)

    def running(self):
        return self.state() != 0 and self.v('running') == 1


def verify(data, segments, symbols):
    checks, counts = [], {}

    def ok(cond, msg):
        counts['n'] = counts.get('n', 0) + 1
        assert cond, msg

    def new(film_look=75):
        p = F(data, segments, symbols)
        p.uc.mem_unmap(cl.SERVICE & ~0xfff, 0x1000)
        p.record(0, 0, (film_look, 11, 11))
        return p

    def ready(look=75):
        """A camera that has been up for a while: the block exists (made by the idle rule)."""
        p = new(look)
        p.now = 21000
        p.put(ARMED, 4999)
        p.ev(0x0199)
        ok(p.state() != 0, 'idle allocation')
        return p

    manifest = json.loads((BUILD/'payload-manifest.json').read_text(encoding='utf-8'))
    slot_film = {x['look']: x['film'] for x in manifest['slots']}
    FILM = slot_film[75]

    def run(p, ms):
        done = 0
        while done < ms:
            p.fire(33)
            done += 33

    def finish(p):
        n = 0
        while p.timers() and n < 200:
            p.fire(33)
            n += 1

    # ---- 1. the fast path and the idle allocation (1g rule)
    p = new()
    n0 = len(p.allocations)
    p.now = 1000
    for _ in range(10):
        p.ev(0x0199, 5)
    ok(p.state() == 0 and len(p.allocations) == n0 and p.get(ARMED) == 10, 'before the block exists an ordinary event only counts')
    p.put(ARMED, 4990)
    for _ in range(20):
        p.ev(0x0199, 5)
    ok(p.state() == 0 and len(p.allocations) == n0 and p.get(ARMED) >= 5000, 'at the count threshold but with the clock under 20 s nothing is allocated')
    p.now = 21000
    p.ev(0x0199)
    sizes = [s for _, s in p.allocations[n0:]]
    ok(p.state() != 0 and sizes == [p.M['sizeof'], 126720, 126720, 20736, 28672], ('the idle rule allocates the adapter and four buffers, once', sizes))
    count = p.get(ARMED)
    for _ in range(5):
        p.ev(0x0199, 5)
    ok(len(p.allocations) == n0 + 5 and p.get(ARMED) == count, 'with the block present an ordinary event does nothing (the count word is not touched)')
    p.canaries()
    q = new()
    q.now = 30000
    q.put(ARMED, 5000)
    q.fail_at = {0}
    q.alloc_count = 0
    q.ev(0x0199)
    ok(q.state() == 0 and q.get(FAILED) == 1, 'a failed allocation is remembered')
    q.fail_at = set()
    base = len(q.allocations)
    for _ in range(5):
        q.ev(0x0199, 5)
    q.key(5)
    ok(q.state() == 0 and len(q.allocations) == base, 'and neither an event nor a key event retries it')
    checks.append('fast path and idle allocation: events before the block only count, the count threshold alone allocates nothing, 5000 events and a clock at 20 s allocate the adapter and four buffers once, '
                  'an ordinary event with the block present does nothing, a failed allocation is remembered and never retried')

    # ---- 2. the key event: accepted, the animation starts, the first frame is the JS reference, the layout request works on a clean root
    p = ready()
    root = p.roots[0]
    p.call(0x53391b14, root)                                       # the camera has just painted: the root is clean
    ok(tuple(p.uc.mem_read(root + 0x9c, 2)) == (0, 0), 'the root is clean')
    base = len(p.allocations)
    p.key(100)
    t0 = p.now
    ok(p.running() and len(p.children(root)) == 4 and p.adapter_views() == p.children(root) and len(p.timers()) == 1, 'an accepted 0x013E starts the animation: four views, one timer')
    ok(p.v('accepts') == 1 and p.v('shots') == 1 and p.pend() == [t0], 'one acceptance queued, the photo counted once')
    ok(p.hashes() == cl.js_hashes([cl.jscase('shot', FILM, 1, 1, 0)])[0][1:], 'the first frame equals the JS reference')
    p.call(0x53391b14, root)
    rects = [struct.unpack('<4i', p.uc.mem_read(v + 0x30, 16)) for v in p.adapter_views()]
    ok(rects == VIEWS, ('on a clean root the views are laid out (the root is asked)', rects))
    times = [33, 99, 330, 561, 1089, 1452]
    done = 0
    for t, want in zip(times, cl.js_hashes([cl.jscase('shot', FILM, 1, 1, t) for t in times])):
        p.fire(t - done)
        done = t
        ok(p.hashes() == want[1:], f'frame at +{t} ms differs from the JS reference')
    p.canaries()
    checks.append('an accepted 0x013E starts the animation (four views, one timer), counts the photo once and queues the acceptance; the first frame and six later frames equal the JS reference; '
                  'on a root that has just been painted the four views are laid out')

    # ---- 3. the second 0x013E of the pair and anything within 2 s of an accepted one are ignored
    p = ready()
    p.key(100)
    t0 = p.now
    start_before = p.get(p.state() + p.M['engine'] + 0)
    p.fire(300)
    p.key(0)
    ok(p.v('ignored') == 1 and p.v('shots') == 1 and p.v('accepts') == 1 and p.v('npend') == 1, 'the second event of the pair is ignored')
    p.fire(1599)
    ok(p.now - t0 == 1899, 'time')
    p.key(100)                                                     # 1999 ms after the accepted one
    ok(p.v('ignored') == 2 and p.v('shots') == 1, 'anything within 2 s is ignored (1999 ms)')
    p.key(1)                                                       # 2000 ms
    ok(p.v('accepts') == 2 and p.v('shots') == 2 and p.v('npend') == 2, 'the next one at 2000 ms is a new photo: the moment restarts, the counter advances once')
    finish(p)
    checks.append('a second 0x013E 0.3 s after the first and anything up to 1999 ms is ignored (counted); at 2000 ms a new photo is accepted: the counter advances once and the acceptance is queued')

    # ---- 4. an accepted key with no block yet (before the 20 s guard): the first photo works, same hook and task as the idle allocation
    p = new()
    p.now = 5000
    ok(p.state() == 0 and p.get(ARMED) == 0, 'young camera')
    base = len(p.allocations)
    p.key(100)
    sizes = [s for _, s in p.allocations[base:base + 5]]
    ok(sizes == [p.M['sizeof'], 126720, 126720, 20736, 28672] if p.state() else False, ('the first accepted key allocates the adapter and the buffers', sizes))
    ok(p.running() and p.v('shots') == 1 and p.get(ARMED) == 0, 'the animation runs for the first photo although the guard has not passed; the idle counter is untouched')
    finish(p)
    # the same with a failing allocation: no animation, remembered, the late fallback still works
    q = new()
    q.now = 5000
    q.fail_at = {0}
    q.alloc_count = 0
    q.key(100)
    ok(q.state() == 0 and q.get(FAILED) == 1 and not q.children(q.roots[0]), 'a failed allocation at the key: no animation, remembered')
    q.fail_at = set()
    q.key(2500)
    ok(q.state() == 0, 'a later key does not retry')
    q.call('grmod_on_shot')
    ok(q.state() != 0 and q.running() and q.v('fallbacks') == 1, 'the completion hook starts it late as before (and counts a fallback)')
    q.canaries()
    checks.append('a photo before the 20 s guard: the first accepted 0x013E allocates (same hook, same task as the idle allocation) and the animation runs; a failed allocation gives no animation, is remembered, and the completion hook still starts it late')

    # ---- 5. the completion hook consumes the acceptance; it does not start a second animation; the fallback and the 40 s limit
    p = ready()
    p.key(100)
    t0 = p.now
    finish(p)
    ok(not p.running() and not p.children(p.roots[0]) and p.v('shots') == 1, 'the animation is over')
    p.now = t0 + 18000
    p.call('grmod_on_shot')
    ok(p.v('consumed') == 1 and p.v('npend') == 0 and p.v('shots') == 1 and not p.running() and not p.children(p.roots[0]) and p.v('fallbacks') == 0, 'the completion hook 18 s later only consumes the acceptance')
    p.call('grmod_on_shot')
    ok(p.v('fallbacks') == 1 and p.running() and p.v('shots') == 2, 'a completion hook with no acceptance starts the animation late and counts a fallback')
    q = ready()
    q.key(100)
    finish(q)
    q.now += 41000
    q.call('grmod_on_shot')
    ok(q.v('dropped') == 1 and q.v('consumed') == 0 and q.v('fallbacks') == 1 and q.running(), 'an acceptance older than 40 s is dropped and the hook falls back')
    # the Standard timing: the completion 0.9 s after the press, while the animation is still running
    r = ready()
    r.key(100)
    r.fire(400)
    r.call('grmod_on_shot')
    ok(r.running() and r.v('consumed') == 1 and r.v('shots') == 1, 'the completion hook (and the release hook) do not cut or restart a running animation')
    r.call('grmod_cancel')
    ok(r.running(), 'the release hook (which fires with the completion in the field data) no longer cancels')
    checks.append('the completion hook consumes the queued acceptance and starts nothing; with none it starts late and counts a fallback; an acceptance older than 40 s is dropped; a completion 0.4 s into a Standard photo\'s animation does not cut it; the release hook does not cancel')

    # ---- 6. two photos back to back: restart on every accepted key, the counter once per photo, completions in order
    p = ready()
    p.key(100)
    p.fire(2500)
    p.key(0)                                                       # a second photo while the first is processing
    ok(p.v('shots') == 2 and p.v('npend') == 2 and p.running(), 'the second photo restarts the animation')
    ok(p.hashes() == cl.js_hashes([cl.jscase('shot', FILM, 2, 1, 0)])[0][1:], 'frame 2 of roll 1')
    finish(p)
    p.now += 14000
    p.call('grmod_on_shot')
    ok(p.v('consumed') == 1 and p.v('npend') == 1 and p.v('shots') == 2 and not p.running(), 'the first completion consumes the first acceptance')
    p.now += 5000
    p.call('grmod_on_shot')
    ok(p.v('consumed') == 2 and p.v('npend') == 0 and p.v('shots') == 2 and p.v('fallbacks') == 0, 'the second completion consumes the second')
    # a second photo inside the first animation but after the 2 s ignore time (the linger still showing): no new slide-in
    q = ready()
    q.key(100)
    q.fire(2000)
    q.key(1)
    ok(q.v('shots') == 2 and q.running(), 'a photo at 2 s restarts')
    for _ in range(5):                                           # five photos, then the queue holds at most four: the oldest is dropped
        q.fire(2100)
        q.key(0)
    ok(q.v('npend') == 4 and q.v('dropped') >= 2 and q.v('shots') == 7, ('the queue holds four acceptances', q.v('npend'), q.v('dropped')))
    finish(q)
    q.canaries()
    checks.append('two photos back to back: every accepted key restarts the animation (frame 2 of roll 1 equals the JS reference), the counter advances once per photo, completion hooks consume in order, the queue holds four and drops the oldest')

    # ---- 7. the film is read at the key: a film change between photos
    p = ready(75)
    p.key(100)
    ok(p.hashes() == cl.js_hashes([cl.jscase('shot', FILM, 1, 1, 0)])[0][1:], 'photo 1: Portra')
    finish(p)
    p.record(0, 0, (11, 11, 11))                                    # Standard: the neutral GR III strip
    p.key(3000)
    ok(p.hashes() == cl.js_hashes([cl.jscase('shot', 21, 2, 1, 0)])[0][1:], 'photo 2: the neutral strip, frame 2')
    finish(p)
    p.record(0, 0, (64 + 0, 11, 11))
    p.key(3000)
    ok(p.hashes() == cl.js_hashes([cl.jscase('shot', 20, 3, 1, 0)])[0][1:], 'photo 3: slot 0 (Pro 400H), frame 3')
    finish(p)
    p.record(1, 0, (75, 11, 11))                                    # movie mode: no animation, no crash
    p.key(3000)
    ok(not p.running() and not p.children(p.roots[0]), 'movie mode: no animation')
    p.call('grmod_on_shot')
    ok(not p.running() and p.v('shots') == 3, 'and the completion hook starts none')
    checks.append('the film is read at every accepted key: Portra, then the neutral strip for Standard, then Pro 400H, each equal to the JS reference; movie mode gives no animation and no crash')

    # ---- 8. view allocation failure (the native factory refusing), no root, bad clock: nothing breaks, the late path still works
    p = ready()
    p.fail_factory = {1}                                            # the second view of the first attach
    p.key(100)
    ok(not p.running() and not p.children(p.roots[0]) and p.v('accepts') == 1 and p.v('npend') == 0, 'a view the camera could not create: no animation, nothing queued')
    p.fail_factory = set()
    p.call('grmod_on_shot')
    ok(p.running() and p.v('fallbacks') == 1 and len(p.children(p.roots[0])) == 4, 'the completion hook starts it late')
    q = ready()
    q.active = cl.OTHER
    q.key(100)
    ok(not q.running() and not q.children(q.roots[0]) and not q.timers(), 'a key event on another controller: nothing')
    q.active = cl.LV
    q.clock_ok = False
    q.key(2500)
    ok(not q.running() and not q.timers(), 'no clock: nothing')
    q.clock_ok = True
    q.canaries()
    checks.append('a view the native factory refuses, another controller and a failing clock give no animation and no crash; the completion hook starts the animation late after a failed start')

    # ---- 9. transitions and the release hook while the animation runs
    p = ready()
    p.key(100)
    root = p.roots[0]
    p.call('grmod_before_transition', cl.LV, 0x08000020)
    ok(not p.children(root) and not p.timers(), 'a menu destination cancels')
    p.active = cl.OTHER
    p.call('grmod_after_transition')
    p.active = cl.LV
    p.key(3000)
    p.fire(300)
    p.call('grmod_before_transition', cl.LV, 0x0800000c)
    ok(not p.children(root) and not p.timers(), 'a shooting transition detaches')
    p.active = cl.QV
    p.call('grmod_after_transition')
    ok(len(p.children(p.roots[1])) == 4 and len(p.timers()) == 1, 'and reattaches the four views after it')
    p.call('grmod_before_canvas_delete', p.roots[1])
    ok(not p.children(p.roots[1]) and not p.timers(), 'canvas deletion cancels')
    p.canaries()
    checks.append('menu destination, shooting transition (detach and reattach) and canvas deletion behave as in stage 1')

    # ---- 10. burst, self-timer and 80 photos: no growth
    p = ready()
    for i in range(3):                                              # a burst: three keys within 2 s, one photo
        p.key(300)
    ok(p.v('accepts') == 1 and p.v('ignored') == 2 and p.v('shots') == 1, 'a burst of keys within 2 s is one photo')
    finish(p)
    count, nfrees = len(p.allocations), len(p.frees)
    for i in range(80):
        p.key(3000)
        finish(p)
        p.call('grmod_on_shot')
    ok(len(p.allocations) == count and len(p.frees) == nfrees and p.v('shots') == 81, 'eighty photos: no allocation, no growth, the counter follows')
    p.key(3000)
    p.fire(330)
    ok(p.hashes() == cl.js_hashes([cl.jscase('shot', FILM, 82 % 36 or 36, 1 + 81 // 36, 330)])[0][1:], 'frame and roll numbers follow the photo count')
    p.canaries()
    checks.append('a burst of keys within 2 s is one photo; eighty photos allocate and free nothing; frame and roll numbers follow the photo count')

    # ---- 11. the cost of one ordinary event through the real trampoline and the real dispatcher, in instructions
    from unicorn import UC_HOOK_CODE
    costs = {}
    for label, make in (('block_present', lambda: ready()), ('no_block', lambda: new())):
        q = make()
        q.key(100) if label == 'block_present' else None
        st = {'on': False, 'n': 0, 'out': []}
        entry = q.symbols['grmod_hook_event']

        def count(uc, at, size, user, st=st, entry=entry):
            if at == entry:
                st['on'] = True
                st['n'] = 0
            if st['on']:
                st['n'] += 1
                if at == 0x53228ab8:
                    st['on'] = False
                    st['out'].append(st['n'])
        q.uc.hook_add(UC_HOOK_CODE, count)
        q.fire(33)
        q.call(0x53228ab4, ca.APP, ca.EVENT) if label == 'no_block' else None
        costs[label] = st['out'][-1] if st['out'] else None
    ok(all(v is not None and v < 40 for v in costs.values()), ('cost of an ordinary event in instructions, trampoline included', costs))
    checks.append(f'cost of an ordinary UI event through the real trampoline and dispatcher: {costs} instructions (trampoline and displaced instruction included)')

    ok(p.audio_calls == [], 'audio entry reached')
    return dict(checks=checks, assertions=counts['n'], per_event_cost_instructions=costs, hardware_tested=False,
                simulated_boundaries=['allocator', 'OS clock and alarms', 'App and UI lookup inputs', 'settings record bytes'])


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
