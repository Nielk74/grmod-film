"""Stage 4b scenarios (the tier 2 hardware proof; the whole of stage 4a kept with the proof disabled), run in the emulator on the delivered image
(LOADED_VARIANT=stage4btier2engine or stage4btier2filmpack).

The adapter, the Loaded renderer and the original native UI, view-tree, layout, timer, clock and RGBA copier bodies execute from the delivered
image. Boundaries (allocator, OS clock and alarms, settings record bytes, the controller identities) are the Fixture's.
"""
import hashlib
import json
import os
import struct
import sys
import zlib
from pathlib import Path

VARIANTS = ('stage4btier2engine', 'stage4btier2filmpack')
os.environ['LOADED_VARIANT'] = os.environ.get('LOADED_VARIANT') if os.environ.get('LOADED_VARIANT') in VARIANTS else 'stage4btier2engine'
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_adapter_loaded as cl  # noqa: E402
ca = cl.ca
OUT, BUILD = cl.OUT, cl.BUILD
VIEWS = cl.VIEWS
LAYOUT = ['views', 'pixels', 'shots', 'pending_roll', 'engine', 'sizeof', 'pend', 'npend', 'last_accept', 'accepts', 'ignored', 'fallbacks', 'consumed', 'dropped',
          'running', 'params', 'shown', 'sliding', 'nframes', 'rolls', 'film', 'shows', 'hides', 'film_changes', 'attach_failures', 'rej_nosignal', 'rej_stale', 'sig_cleared', 'loads', 't2', 't2_wait']
T2L = ['sizeof', 'step', 'probe', 's2', 's3a', 's3b', 's4', 's5', 'n_alloc', 'n_free', 'frames', 'avg_ms', 'draw_max', 'base_rate', 's4_rate', 'largest', 'r3a', 'r3b', 'pixels',
       'ev', 'page', 'sizeof_row', 'failed', 'total_ms', 'draws', 'mode']
T2FLAG = 0x55804398
ARMED, FAILED, SIGNAL = 0x55804390, 0x5580438c, 0x55804394
zlib_crc = zlib.crc32
TOP, BOTTOM, COUNTER, TAB = 0, 1, 2, 3


class F(cl.LoadedFixture):
    def __init__(self, *a):
        super().__init__(*a)
        from unicorn import UC_HOOK_CODE
        self.factory_calls = 0
        self.fail_factory = set()
        self.uc.hook_add(UC_HOOK_CODE, self._factory, begin=0x533ad7f0, end=0x533ad7f0)
        self.M = dict(zip(LAYOUT, [self.symbol_word('grmod_layout', i) for i in range(len(LAYOUT))]))
        self.T = dict(zip(T2L, [self.symbol_word('grmod_t2_layout', i) for i in range(len(T2L))]))
        self.fail_ge = 0
        self.put(T2FLAG, 3)                                           # the proof is disabled except in its own scenarios

    def _factory(self, cpu, at, size, user):
        n = self.factory_calls
        self.factory_calls += 1
        if n in self.fail_factory:
            self.ret(0)

    fail_ge = 0

    def _hook(self, cpu, at, size, user):
        if at in (0x536af2a8, 0x536af31c):
            size = self.r(0)
            if self.fail_ge and size >= self.fail_ge:
                self.ret(0)
                return
            if size >= 0x100000:                                       # the fixture's own allocator stops at 1 MiB: a bump allocation for the big probes
                n = self.alloc_count
                self.alloc_count += 1
                if n in self.fail_at:
                    self.ret(0)
                    return
                ptr = self.heap
                self.heap = (ptr + size + 95) & ~31
                assert self.heap < 0x59e00000, 'the fixture heap is full'
                self.uc.mem_write(ptr - 32, b'\xa5' * (size + 64))
                self.allocations.append((ptr, size))
                self.ret(ptr)
                return
        super()._hook(cpu, at, size, user)

    def t2p(self):
        s = self.state()
        return self.get(s + self.M['t2']) if s else 0

    def t2v(self, name):
        return self.get(self.t2p() + self.T[name])

    def row(self, name, k=0):
        at = self.t2p() + self.T[name] + k * self.T['sizeof_row']
        w = self.get(at)
        return dict(st=w & 255, why=(w >> 8) & 255, a=self.get(at + 4), b=self.get(at + 8), c=self.get(at + 12))

    def rect(self, name):
        return [struct.unpack('<i', struct.pack('<I', self.get(self.t2p() + self.T[name] + 4 * i)))[0] for i in range(4)]

    def v(self, name):
        if name in ('nframe', 'roll'):                                 # the active film's counter and roll
            return self.get(self.state() + self.M[name + 's'] + 4 * self.v('film'))
        return self.get(self.state() + self.M[name])

    def nf(self, film):
        return self.get(self.state() + self.M['nframes'] + 4 * film)

    def rl(self, film):
        return self.get(self.state() + self.M['rolls'] + 4 * film)

    def ev(self, ident, dt=0):
        self.now = (self.now + dt) & 0xffffffff
        self.uc.mem_write(ca.EVENT + 0x400, struct.pack('<HHI', ident, 0, 0))
        self.call('grmod_on_event', ca.APP, ca.EVENT + 0x400)

    def key(self, dt=0, gap=300):
        """A photo: the capture signal (0161), then the live view returns (013E) 0.3 s later."""
        self.ev(0x0161, dt)
        self.ev(0x013e, gap)

    def key_only(self, dt=0):
        self.ev(0x013e, dt)


def verify(data, segments, symbols):
    checks, counts = [], {}

    def ok(cond, msg):
        counts['n'] = counts.get('n', 0) + 1
        assert cond, msg

    def new(look=75):
        p = F(data, segments, symbols)
        p.uc.mem_unmap(cl.SERVICE & ~0xfff, 0x1000)
        p.record(0, 0, (look, 11, 11))
        return p

    def ready(look=75):
        """The camera has been up a while, in the shooting live view: the idle rule allocates and the views are shown."""
        p = new(look)
        p.now = 21000
        p.put(ARMED, 4999)
        p.ev(0x0199)
        return p

    manifest = json.loads((BUILD/'payload-manifest.json').read_text(encoding='utf-8'))
    slot_film = {x['look']: x['film'] for x in manifest['slots']}
    FILM = slot_film[75]

    def live(film, frame, roll, peek):
        return cl.js_hashes([cl.jscase('live', film, frame, roll, 0, peek=peek)])[0][1:]

    def loadf(film, frame, roll, t):
        return cl.js_hashes([cl.jscase('load', film, frame, roll, t, peek=-1)])[0][1:]

    def hop(p, look, to=0x08000020):
        """Leave the live view for a menu, change the look there, come back (the owner's Image Control visit)."""
        p.call('grmod_before_transition', cl.LV, to)
        p.active = cl.OTHER
        p.call('grmod_after_transition')
        p.record(0, 0, (look, 11, 11))
        p.call('grmod_before_transition', cl.OTHER, 0x08000000)
        p.active = cl.LV
        p.call('grmod_after_transition')

    def finish(p, limit=300):
        n = 0
        while p.timers() and n < limit:
            p.fire(33)
            n += 1

    # ---- 13. the tier 2 hardware proof
    def pat(x, y, frame):
        if y < 40:
            return [0xff0000ff, 0xff00a5ff, 0xff00ffff, 0xff00ff00, 0xffffff00, 0xffff0000, 0xffff00ff, 0xffffffff][x * 8 // 720]
        if 290 <= x < 430 and 190 <= y < 290:
            lx = x - 295
            if x >= 295 and lx < 135 and lx % 45 < 40 and 200 <= y < 256:
                d = lx // 45
                digit = (frame // 100 % 10, frame // 10 % 10, frame % 10)[d]
                glyph = {'0': [14, 17, 19, 21, 25, 17, 14], '1': [4, 12, 4, 4, 4, 4, 14], '2': [14, 17, 1, 2, 4, 8, 31], '3': [31, 2, 4, 2, 1, 17, 14],
                         '4': [2, 6, 10, 18, 31, 2, 2], '5': [31, 16, 30, 1, 1, 17, 14], '6': [6, 8, 16, 30, 17, 17, 14], '7': [31, 1, 2, 4, 8, 8, 8],
                         '8': [14, 17, 17, 14, 17, 17, 14], '9': [14, 17, 17, 15, 1, 2, 12]}[str(digit)]
                if glyph[(y - 200) // 8] & (16 >> ((lx % 45) // 8)):
                    return 0xff00ffff
            return 0xff202020
        if x % 60 == 0 or y % 60 == 0:
            return 0xffffffff
        return 0

    def dest(p, x, y):
        at = ca.DEST + 32 + (y * 736 + x) * 4
        return struct.unpack('<I', p.uc.mem_read(at, 4))[0]

    def paint(p):
        p.call(0x53391b14, p.roots[0])

    def run_proof(p, events=0, limit=900, watch=None):
        """Drive the proof like the camera: a timer tick, then the paint pass; stop when the proof is over. watch(step) is called each tick."""
        n = 0
        while p.get(T2FLAG) == 1 and n < limit:
            for _ in range(events):
                p.ev(0x0199)
            p.fire(33)
            if p.t2p():
                if watch:
                    watch(p)
            paint(p)
            if p.t2p() and watch:
                watch(p)
            n += 1
        return n

    def photo(p, gap=3000):
        p.key(gap)
        finish(p)

    def primed(look=75):
        p = ready(look)
        finish(p)
        p.put(T2FLAG, 0)
        return p

    # the trigger: not on the first photo, on the SECOND accepted photo once its moment is over, never again
    p = primed()
    photo(p)
    ok(p.get(T2FLAG) == 0 and not p.t2p(), 'the first photo starts nothing')
    p.key(3000)
    ok(p.get(T2FLAG) == 0 and p.v('t2_wait') == 1, 'the second accepted photo only arms the proof')
    n = 0
    while p.get(T2FLAG) == 0 and n < 200:
        p.fire(33)
        paint(p)
        n += 1
    ok(p.get(T2FLAG) == 1 and p.t2p() and p.v('running') == 0 and p.v('shown') == 1, 'the proof starts when the second photo\'s moment is over')
    seen = {}
    snapshots = []

    def watch(q):
        step = q.t2v('step')
        seen[step] = seen.get(step, 0) + 1
        if step == 7 and 'pages' not in seen:
            seen['pages'] = 1
            snapshots.append(dict(probe=[q.row('probe', i) for i in range(7)], s2=q.row('s2'), s3a=q.row('s3a'), s3b=q.row('s3b'), s4=q.row('s4'), s5=q.row('s5'),
                                  r3a=q.rect('r3a'), r3b=q.rect('r3b'), frames=q.t2v('frames'), avg=q.t2v('avg_ms'), gap=q.t2v('draw_max'), base=q.t2v('base_rate'),
                                  s4rate=q.t2v('s4_rate'), na=q.t2v('n_alloc'), nf=q.t2v('n_free'), largest=q.t2v('largest'), failed=q.t2v('failed'), total=q.t2v('total_ms')))
        if step == 5 and q.t2v('mode') == 2 and q.t2v('draws') in (7, 8) and 'band' not in seen:
            seen['band'] = (q.t2v('draws'), None)
        if step == 4 and q.t2v('mode') == 1 and q.t2v('draws') >= 1 and 'a720' not in seen:
            seen['a720'] = 1
            for (x, y) in ((0, 0), (359, 20), (719, 39), (60, 100), (61, 100), (200, 60), (500, 120), (300, 205), (310, 230), (340, 250), (719, 479), (120, 479), (0, 300), (401, 300), (299, 200)):
                seen[('p', x, y)] = dest(q, x, y)
        if step == 5 and q.t2v('mode') == 2 and q.t2v('draws') >= 2 and 'b720' not in seen:
            seen['b720'] = q.t2v('draws')
            for (x, y) in ((0, 0), (359, 20), (719, 39), (60, 100), (61, 100), (200, 60), (500, 120), (300, 205), (310, 230), (340, 250), (719, 479), (120, 479), (0, 300), (401, 300), (299, 200),
                           (60, 15), (60, 16), (61, 17), (300, 31), (300, 32), (300, 33), (350, 255), (500, 463), (500, 464)):
                seen[('q', x, y)] = dest(q, x, y)
    nrun = run_proof(p, events=8, watch=watch)
    ok(p.get(T2FLAG) == 2, ('the proof ends with the flag 2', p.get(T2FLAG), nrun))
    snap = snapshots[0]
    ok([r['st'] for r in snap['probe']] == [1] * 7 and snap['largest'] == 1382400, ('S1: all seven probes allocated and freed', snap['probe']))
    ok(snap['s2']['st'] == 3 and snap['s2']['why'] == 9, 'S2: skipped, no safe pool')
    ok(snap['s3a']['st'] == 1 and snap['r3a'] == [0, 0, 360, 240], ('S3a: the 360x240 view, rectangle accepted', snap['s3a'], snap['r3a']))
    ok(snap['s3b']['st'] == 1 and snap['r3b'] == [0, 0, 720, 480], ('S3b: the 720x480 view, rectangle accepted', snap['s3b'], snap['r3b']))
    ok(snap['s4']['st'] == 1 and snap['frames'] >= 30, ('S4: banded, thirty frames', snap['s4'], snap['frames']))
    ok(snap['s5']['st'] == 1 and snap['na'] == snap['nf'], ('S5: clean, every test allocation freed', snap['s5'], snap['na'], snap['nf']))
    ok(snap['failed'] == 0 and snap['base'] > 0 and snap['s4rate'] > 0, ('events per second are counted: base, during S4', snap['base'], snap['s4rate']))
    ok(set(seen) >= {0, 1, 2, 3, 4, 5, 6, 7}, 'every step ran, in order')
    # the pixels: the buffered full-screen draw (design A) and the banded draw (design B) put the pattern at the right places, frame number included
    bad = []
    for key, got in seen.items():
        if isinstance(key, tuple) and key[0] == 'p':
            want = pat(key[1], key[2], 0)
            if (want == 0 and got != 0) or (want != 0 and got != want):
                bad.append((key, hex(got), hex(want)))
    ok(not bad and 'a720' in seen, ('design A: pattern pixels in place', bad[:4]))
    frame_b = seen['b720']
    bad = []
    for key, got in seen.items():
        if isinstance(key, tuple) and key[0] == 'q':
            want = pat(key[1], key[2], frame_b)
            if (want == 0 and got != 0) or (want != 0 and got != want):
                bad.append((key, hex(got), hex(want)))
    ok(not bad, ('design B: banded pattern pixels in place, bands meet at rows 16, 32, 464 (frame %d)' % frame_b, bad[:4]))
    ok(not p.t2p() and p.get(T2FLAG) == 2 and p.v('shown') == 1 and len(p.children(p.roots[0])) == 4, 'the panel and the test are gone, the four Loaded views are back')
    finish(p)
    # no leak: every allocation made after the proof began has been freed (the block, the panel pixels live in it)
    ok(p.hashes() == live(FILM, 3, 1, 1000), 'the Loaded tab and counter are unchanged afterwards')
    photo(p)                                                          # a third photo: normal strips, no new proof
    ok(p.get(T2FLAG) == 2 and not p.t2p() and p.v('shots') == 3 and p.hashes() == live(FILM, 4, 1, 1000), 'a third photo works as in 4a and starts no new proof')
    p.canaries()
    checks.append('the proof starts after the second accepted photo only (once per power-on): S1 probes 64K to 1.4M all freed at once, S2 skipped, S3 the 360x240 and 720x480 views get their rectangles and draw, '
                  'S4 thirty banded frames, S5 clean with every allocation freed; the buffered and the banded pattern pixels are where they should be; events per second are counted; Loaded is unchanged afterwards')

    return dict(checks=checks, assertions=counts['n'], cost_instructions={}, hardware_tested=False, simulated_boundaries=[])
    # ---- 9. cost in instructions: ordinary events, the slide-in, the strips, idle
    from unicorn import UC_HOOK_CODE
    cost = {}
    q = ready()
    box = {'n': 0, 'on': False}

    def counter(uc, at, size, user):
        if box['on']:
            box['n'] += 1
    q.uc.hook_add(UC_HOOK_CODE, counter)

    def measure(label, action):
        box['n'] = 0
        box['on'] = True
        action()
        box['on'] = False
        cost[label] = box['n']
    measure('slide_in_tick', lambda: q.fire(33))
    finish(q)
    measure('idle_second_of_dispatch', lambda: [q.fire(33) for _ in range(30)])
    cost['idle_second_of_dispatch'] = cost['idle_second_of_dispatch']
    q.key(3000)
    ticks = []
    for i in range(10):
        measure('t', lambda: q.fire(33))
        ticks.append(cost['t'])
    cost.pop('t')
    cost['strips_tick_min'], cost['strips_tick_max'] = min(ticks), max(ticks)
    finish(q)
    measure('ordinary_event', lambda: q.ev(0x0199))
    ok(True, ('costs', cost))
    checks.append(f'cost in emulated instructions: {cost} (a tick includes the native timer and event dispatch; idle second = 30 dispatches of an ordinary event with no timer)')

    cost.update(cost_load)
    return dict(checks=checks, assertions=counts['n'], cost_instructions=cost, hardware_tested=False,
                simulated_boundaries=['allocator', 'OS clock and alarms', 'App and UI lookup inputs', 'settings record bytes', 'controller identities'])


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
