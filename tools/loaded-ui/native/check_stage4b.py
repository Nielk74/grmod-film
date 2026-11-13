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
                self.uc.mem_write(ptr - 32, bytes([0xa5]) * (size + 64))
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

    # ---- 1. the idle allocation shows the views: slide-in, then steady, then nothing (no timer at idle)
    p = new()
    p.now = 21000
    p.put(ARMED, 4999)
    root = p.roots[0]
    p.call(0x53391b14, root)                                       # a clean root
    p.ev(0x0199)
    t0 = p.now
    ok(p.state() != 0 and p.v('shown') == 1 and p.v('sliding') == 1 and len(p.children(root)) == 4 and len(p.timers()) == 1, 'the idle allocation shows the views (slide-in started)')
    ok(p.hashes() == live(FILM, 1, 1, 0), 'slide-in, first frame: equals the JS reference (peek 0)')
    done = 0
    for pe in (33, 66, 99, 132, 165):
        p.fire(pe - done)
        done = pe
        ok(p.hashes() == live(FILM, 1, 1, pe), f'slide-in at {pe} ms equals the JS reference')
    p.fire(33)
    ok(p.v('sliding') == 0 and not p.timers(), 'the slide-in is over: no timer')
    ok(p.hashes() == live(FILM, 1, 1, 1000), 'steady state equals the JS reference (the tab and the counter 1, the strips empty)')
    steady = p.hashes()
    for _ in range(40):
        p.fire(250)
    ok(p.hashes() == steady and not p.timers() and p.v('shows') == 1, 'ten seconds idle: nothing changes, no timer')
    for ident in (0x0164, 0x0165, 0x0102, 0x01a4, 0x001b, 0x0199):   # a half press and the periodic events
        p.ev(ident, 10)
    ok(p.hashes() == steady and not p.timers() and p.v('hides') == 0, 'a half press (the AF events) and periodic events change nothing')
    p.call(0x53391b14, root)
    rects = [struct.unpack('<4i', p.uc.mem_read(v + 0x30, 16)) for v in p.adapter_views()]
    ok(rects == VIEWS, ('on a clean root the views are laid out', rects))
    vis = bytes(p.uc.mem_read(ca.DEST + 32, 736 * 480 * 4))
    for name, i in (('tab', TAB), ('counter', COUNTER)):
        x, y, w, h = VIEWS[i]
        buf = p.get(p.state() + p.layout[1] + 4 * i)
        px = bytes(p.uc.mem_read(buf, w * h * 4))
        opaque = [k for k in range(w * h) if px[4 * k + 3] != 0]
        ok(len(opaque) > 500, f'the {name} buffer has content')
        same = sum(1 for k in opaque if vis[((y + k // w) * 736 + x + k % w) * 4:((y + k // w) * 736 + x + k % w) * 4 + 4] == px[4 * k:4 * k + 4])
        ok(same == len(opaque), f'every opaque pixel of the {name} is on the screen, at its place ({same} of {len(opaque)})')
    empty = zlib_crc(bytes(720 * 44 * 4))
    ok(p.hashes()[TOP] == empty and p.hashes()[BOTTOM] == empty, 'the strips are empty')
    p.canaries()
    checks.append('the idle allocation shows the tab and counter in the shooting live view: the slide-in (six frames) and the steady state equal the JS reference, then no timer; ten seconds idle and a half press change nothing; '
                  'on a clean root the views are laid out and the tab and counter pixels land on the screen, the strips are empty')

    # ---- 2. a photo: the moment starts on 0x013E with the furniture showing, the counter rolls, then they stay with the new number
    p = ready()
    finish(p)
    p.key(3000)
    ok(p.v('running') == 1 and p.v('shots') == 1 and p.v('nframe') == 2 and p.v('shown') == 1, 'an accepted 0x013E starts the moment; the counter is already 2')
    ok(p.hashes() == cl.js_hashes([cl.jscase('shot', FILM, 1, 1, 0, peek=-1, hold=1)])[0][1:], 'the first frame (furniture held) equals the JS reference')
    times = [33, 99, 330, 561, 1089, 1452]
    done = 0
    for t, want in zip(times, cl.js_hashes([cl.jscase('shot', FILM, 1, 1, t, peek=-1, hold=1) for t in times])):
        p.fire(t - done)
        done = t
        ok(p.hashes() == want[1:], f'frame at +{t} ms equals the JS reference (the counter rolls)')
    finish(p)
    ok(p.v('running') == 0 and not p.timers() and p.v('shown') == 1, 'the moment is over: no timer, the views stay')
    ok(p.hashes() == live(FILM, 2, 1, 1000), 'afterwards the tab and counter sit there showing 2 (equal to the JS reference), the strips are gone')
    p.now += 14000
    p.call('grmod_on_shot')
    ok(p.v('consumed') == 1 and p.hashes() == live(FILM, 2, 1, 1000) and not p.timers(), 'the completion hook later only consumes the acceptance')
    p.canaries()
    checks.append('a photo on 0x013E: the moment runs with the tab and counter held, the counter rolls (seven frames equal the JS reference), afterwards the tab and counter stay with the new number and no timer remains; the completion hook changes nothing')

    # ---- 3. thirty-six photos: the end of the roll, the counter wraps to 1, the roll number advances
    p = ready()
    finish(p)
    for i in range(35):
        p.key(3000)
        finish(p)
    ok(p.v('nframe') == 36 and p.v('roll') == 1 and p.hashes() == live(FILM, 36, 1, 1000), 'after 35 photos the counter shows 36')
    p.key(3000)
    ok(p.v('pending_roll') == 1 and p.v('nframe') == 1 and p.v('roll') == 2, 'the 36th photo wraps the counter to 1 and advances the roll of that film')
    p.fire(1500)
    p.fire(300)
    ok(p.hashes() == cl.js_hashes([cl.jscase('roll', FILM, 36, 1, 300, peek=-1, hold=1)])[0][1:], 'the end of the roll follows with the tab and counter held')
    finish(p)
    ok(p.hashes() == live(FILM, 1, 2, 1000) and not p.timers(), 'after the end of the roll the counter sits at 1')
    p.canaries()
    checks.append('thirty-six photos: the counter shows 36, the 36th photo is followed by the end of the roll with the furniture held, the counter wraps to 1 and the roll number advances; the final state equals the JS reference')

    # ---- 4. visibility: menu, playback, quick review, movie, canvas deletion; the owner's menu visit with a film change
    p = ready()
    finish(p)
    root = p.roots[0]
    p.call('grmod_before_transition', cl.LV, 0x08000020)           # the main or Image Control menu
    ok(not p.children(root) and not p.timers() and p.v('shown') == 0, 'a menu destination hides everything')
    p.active = cl.OTHER
    p.call('grmod_after_transition')
    ok(not p.children(root) and not p.timers(), 'nothing is shown in the menu')
    p.record(0, 0, (64 + 13, 11, 11))                              # the owner changes the look to CineStill 800T in the Image Control menu
    p.call('grmod_before_transition', cl.OTHER, 0x08000000)
    p.active = cl.LV
    p.call('grmod_after_transition')
    cine = slot_film[64 + 13]
    ok(p.v('shown') == 1 and p.v('running') == 1 and p.v('loads') == 1 and len(p.children(root)) == 4 and p.v('film') == cine and p.v('nframe') == 1 and p.v('roll') == 1 and p.v('film_changes') == 1, 'back in the live view with another film: the load plays, the new film with its own counter (1)')
    ok(p.hashes() == loadf(cine, 1, 1, 0), 'the first load frame shows the new film (JS reference)')
    finish(p)
    ok(p.hashes() == live(cine, 1, 1, 1000), 'the new look sits there')
    # playback
    p.call('grmod_before_transition', cl.LV, 0x0800000d)
    ok(not p.children(root) and p.v('shown') == 0, 'playback hides')
    p.active = cl.OTHER
    p.call('grmod_after_transition')
    p.call('grmod_before_transition', cl.OTHER, 0x08000000)
    p.active = cl.LV
    p.call('grmod_after_transition')
    ok(p.v('shown') == 1 and p.v('film_changes') == 1 and p.v('nframe') == 1, 'back from playback: shown again, same film, the counter kept')
    finish(p)
    # quick review: the live view controller is not the shooting live view
    p.call('grmod_before_transition', cl.LV, 0x0800000c)
    p.active = cl.QV
    p.call('grmod_after_transition')
    ok(not p.children(p.roots[1]) and p.v('shown') == 0, 'quick review: nothing is shown')
    p.call('grmod_before_transition', cl.QV, 0x08000000)
    p.active = cl.LV
    p.call('grmod_after_transition')
    ok(p.v('shown') == 1 and len(p.children(root)) == 4, 'and they come back with the live view')
    finish(p)
    # movie
    p.call('grmod_before_transition', cl.LV, 0x08000001)
    p.record(1, 0, (64 + 13, 11, 11))
    p.call('grmod_after_transition')
    ok(p.v('shown') == 0 and not p.children(root) and not p.timers(), 'movie mode: nothing is shown, no crash')
    p.call('grmod_before_transition', cl.LV, 0x08000001)
    p.record(0, 0, (64 + 13, 11, 11))
    p.call('grmod_after_transition')
    ok(p.v('shown') == 1, 'back to still shooting: shown')
    finish(p)
    p.call('grmod_before_canvas_delete', root)
    ok(p.v('shown') == 0 and not p.children(root) and not p.timers(), 'canvas deletion hides')
    p.canaries()
    checks.append('visibility: a menu, playback, quick review, movie and canvas deletion hide everything (no timer); the owner\'s Image Control visit shows the new look with the slide-in, the counter reset to 1 and a new roll; '
                  'playback and quick review keep the film and the counter; the first slide-in frame and the steady state equal the JS reference')

    # ---- 5. a film change seen only at a photo (no transition): new roll, the strips of the new film
    p = ready()
    finish(p)
    p.key(3000)
    finish(p)
    p.record(0, 0, (11, 11, 11))                                   # Standard
    p.key(3000)
    ok(p.v('film') == 21 and p.v('film_changes') == 1 and p.v('nframe') == 2 and p.v('roll') == 1, 'a film change at a photo: the neutral strip has its own counter, the shot is its frame 1')
    ok(p.hashes() == cl.js_hashes([cl.jscase('shot', 21, 1, 1, 0, peek=-1, hold=1)])[0][1:], 'frame 1 of the neutral strip')
    finish(p)
    ok(p.hashes() == live(21, 2, 1, 1000), 'and the new tab and counter 2 afterwards')
    checks.append('a film change noticed at a photo: the new film own counter (frame 1 of its roll 1), then the tab and counter show 2')

    # ---- 6. a photo before the block exists (young camera): the first accepted key allocates and everything shows; the idle count is untouched
    p = new()
    p.now = 5000
    ok(p.state() == 0 and not p.children(p.roots[0]), 'young camera: nothing shown')
    p.key(100)
    ok(p.v('running') == 1 and p.v('shown') == 1 and p.get(ARMED) == 0, 'the first accepted key allocates and starts the moment (the tab and counter slide in with the photo)')
    ok(p.hashes() == cl.js_hashes([cl.jscase('shot', FILM, 1, 1, 0)])[0][1:], 'first frame as in stage 2a (peek at the photo)')
    finish(p)
    ok(p.hashes() == live(FILM, 2, 1, 1000), 'afterwards the tab and counter sit there showing 2')
    checks.append('a photo before the block exists: the first accepted 0x013E allocates, the moment starts with the tab and counter sliding in, and afterwards they sit there showing 2')

    # ---- 7. failures are harmless: allocation, attach (a view the camera refuses), a bad clock; the next transition tries again
    q = new()
    q.now = 30000
    q.put(ARMED, 5000)
    q.fail_at = {0}
    q.alloc_count = 0
    q.ev(0x0199)
    ok(q.state() == 0 and q.get(FAILED) == 1 and not q.children(q.roots[0]), 'an allocation failure shows nothing')
    q.fail_at = set()
    for _ in range(5):
        q.ev(0x0199, 10)
    ok(q.state() == 0, 'and is not retried by events')
    p = new()
    p.now = 21000
    p.put(ARMED, 4999)
    p.fail_factory = {1}
    p.ev(0x0199)
    ok(p.state() != 0 and p.v('shown') == 0 and p.v('attach_failures') == 1 and not p.children(p.roots[0]) and not p.timers(), 'a view the camera refuses: nothing shown, counted, no crash')
    p.fail_factory = set()
    p.call('grmod_before_transition', cl.LV, 0x08000000)
    p.call('grmod_after_transition')
    ok(p.v('shown') == 1 and len(p.children(p.roots[0])) == 4, 'the next transition tries again and succeeds')
    r = ready()
    finish(r)
    r.clock_ok = False
    r.call('grmod_before_transition', cl.LV, 0x08000000)
    r.call('grmod_after_transition')
    ok(r.v('shown') == 0 and not r.timers(), 'no clock: nothing shown')
    r.clock_ok = True
    r.call('grmod_before_transition', cl.LV, 0x08000000)
    r.call('grmod_after_transition')
    ok(r.v('shown') == 1, 'and the next transition shows')
    s = ready()
    finish(s)
    s.active = cl.OTHER
    s.call('grmod_before_transition', cl.LV, 0x08000000)
    s.call('grmod_after_transition')
    ok(s.v('shown') == 0, 'a transition that ends in another controller shows nothing')
    for x in (p, q, r, s):
        x.canaries()
    checks.append('an allocation failure, a view the camera refuses, a failing clock and a transition into another controller show nothing without a crash; events never retry an allocation; the next transition tries once more and succeeds')

    # ---- 8. a photo during the slide-in and two photos back to back; the completion hook and the fallback as in stage 2a
    p = ready()
    p.fire(66)                                                      # sliding in
    ok(p.v('sliding') == 1, 'sliding')
    p.key(0, 20)
    ok(p.v('running') == 1 and p.v('shots') == 1 and p.v('sliding') == 0, 'a photo during the slide-in takes it over')
    finish(p)
    p.key(3000)
    ok(p.v('shots') == 2 and p.v('nframe') == 3, 'two photos: the counter advanced once per photo')
    finish(p)
    p.key(2000)
    p.fire(300)
    p.key(1000)
    ok(p.v('shots') == 3 and p.v('ignored') >= 1, 'a key within 2 s of an accepted one is ignored')
    finish(p)
    q = ready()
    finish(q)
    q.call('grmod_on_shot')                                         # a completion with no 0x013E: the late start
    ok(q.v('fallbacks') == 1 and q.v('running') == 1 and q.v('shots') == 1, 'the completion fallback starts the moment late')
    finish(q)
    ok(q.hashes() == live(FILM, 2, 1, 1000), 'and ends with the tab and counter showing 2')
    count, nfrees = len(p.allocations), len(p.frees)
    for i in range(60):
        p.key(3000)
        finish(p)
        p.call('grmod_on_shot')
    ok(len(p.allocations) == count and len(p.frees) == nfrees and p.v('shown') == 1, 'sixty more photos: no allocation, the views stay')
    ok(p.audio_calls == [], 'audio entry reached')
    p.canaries()
    checks.append('a photo during the slide-in takes it over; two photos advance the counter twice; a key within 2 s is ignored; the completion fallback ends with the tab and counter showing the new number; sixty photos allocate and free nothing')

    # ---- 10. the capture signal: playback return, stale signal, half press, transitions, the pair, the late fallback
    p = ready()
    finish(p)
    steady = p.hashes()
    p.call('grmod_before_transition', cl.LV, 0x0800000d)            # to playback and back by a half press
    p.active = cl.OTHER
    p.call('grmod_after_transition')
    p.call('grmod_before_transition', cl.OTHER, 0x08000000)
    p.active = cl.LV
    p.call('grmod_after_transition')
    finish(p)
    shows = p.v('shows')
    p.key_only(500)                                                  # the live view returns: 013E with no capture signal
    p.key_only(100)
    ok(p.v('accepts') == 0 and p.v('shots') == 0 and p.v('rej_nosignal') >= 1 and p.v('nframe') == 1, '013E alone (the return from playback) is not a photo: no counter, no acceptance')
    ok(not p.timers() and p.v('running') == 0 and p.hashes() == live(FILM, 1, 1, 1000) and p.v('shows') == shows, 'and nothing is drawn: no strips, no timer, the tab and counter unchanged')
    p.ev(0x0161, 1000)                                               # a capture signal, then 4 s, then a 013E
    p.key_only(4000)
    ok(p.v('accepts') == 0 and p.v('rej_stale') == 1 and p.v('shots') == 0 and not p.timers(), 'a signal 4 s old is rejected')
    p.ev(0x0161, 1000)
    p.key_only(2900)                                                 # 2.9 s: still fresh
    ok(p.v('accepts') == 1 and p.v('shots') == 1 and p.get(SIGNAL) == 0, 'a signal 2.9 s old makes a photo and is consumed')
    finish(p)
    ok(p.hashes() == live(FILM, 2, 1, 1000), 'the counter shows 2')
    p.key_only(100)                                                  # the second 013E of the pair: no signal left, and inside the 2 s debounce
    ok(p.v('shots') == 1 and p.v('accepts') == 1 and not p.timers(), 'the second event of the pair does nothing')
    # a half press with AF: the events of a half press, and a 013E after it
    q = ready()
    finish(q)
    for ident in (0x0164, 0x0102, 0x01a4, 0x001b, 0x0165):
        q.ev(ident, 30)
    q.key_only(500)
    ok(q.v('shots') == 0 and q.v('accepts') == 0 and not q.timers() and q.v('rej_nosignal') == 1, 'a half press (AF) gives no signal, and a 013E after it is not a photo')
    # a menu visit between the signal and the 013E clears the signal; the quick review chain of a photo keeps it
    r = ready()
    finish(r)
    r.ev(0x0161, 100)
    r.call('grmod_before_transition', cl.LV, 0x08000020)
    ok(r.get(SIGNAL) == 0 and r.v('sig_cleared') == 1, 'a transition to a menu clears the signal')
    r.active = cl.OTHER
    r.call('grmod_after_transition')
    r.call('grmod_before_transition', cl.OTHER, 0x08000000)
    r.active = cl.LV
    r.call('grmod_after_transition')
    finish(r)
    r.key_only(300)
    ok(r.v('shots') == 0, 'so the 013E after it is not a photo')
    s = ready()
    finish(s)
    s.ev(0x0161, 100)
    s.call('grmod_before_transition', cl.LV, 0x0800000c)             # quick review on: the photo's own LV -> QV -> LV chain
    ok(s.get(SIGNAL) != 0 and s.v('sig_cleared') == 0, 'a transition to a shooting controller keeps the signal')
    s.active = cl.QV
    s.call('grmod_after_transition')
    s.call('grmod_before_transition', cl.QV, 0x08000000)
    s.active = cl.LV
    s.call('grmod_after_transition')
    s.key_only(1000)
    ok(s.v('shots') == 1 and s.v('running') == 1, 'and the 013E when the live view returns is the photo')
    finish(s)
    # the completion hook: a photo whose 013E was rejected still gets its late start (a completion hook means a photo was taken)
    t = ready()
    finish(t)
    t.key_only(500)                                                  # rejected
    t.call('grmod_on_shot')
    ok(t.v('fallbacks') == 1 and t.v('running') == 1 and t.v('shots') == 1, 'a completion hook with no accepted photo starts the animation late')
    finish(t)
    # a completion hook after an accepted photo only consumes it
    u = ready()
    finish(u)
    u.key(100)
    finish(u)
    u.now += 15000
    u.call('grmod_on_shot')
    ok(u.v('consumed') == 1 and u.v('fallbacks') == 0 and u.v('shots') == 1 and not u.timers(), 'after an accepted photo the completion hook only consumes it')
    # a capture signal before the block exists (young camera) works; a lone 013E there does nothing, not even an allocation
    v = new()
    v.now = 5000
    v.key_only(100)
    ok(v.state() == 0 and not v.children(v.roots[0]), 'a lone 013E on a young camera allocates nothing')
    v.ev(0x0161, 100)
    ok(v.get(SIGNAL) != 0 and v.state() == 0, 'the capture signal is kept in the spare RAM word, no block needed')
    v.key_only(300)
    ok(v.state() != 0 and v.v('running') == 1, 'and the photo allocates and starts')
    for x in (p, q, r, s, t, u, v):
        x.canaries()
    checks.append('capture signal: a 013E alone (the playback return) is not a photo and draws nothing; a signal 4 s old is rejected, 2.9 s old is accepted and consumed; the second 013E of the pair does nothing; '
                  'a half press (AF) gives no signal; a menu transition clears the signal and a shooting-controller transition (quick review chain) keeps it; a completion hook with no accepted photo starts late, after an accepted one only consumes; '
                  'on a young camera the signal lives in the spare RAM word and a lone 013E allocates nothing')

    # ---- 11. per-film counters for the power session
    p = ready(75)
    finish(p)
    p.key(3000)
    finish(p)
    p.key(3000)
    finish(p)
    ok(p.nf(FILM) == 3 and p.rl(FILM) == 1, 'Portra after two photos: the counter shows 3')
    cine = slot_film[64 + 13]
    root = p.roots[0]

    def visit(look):
        p.call('grmod_before_transition', cl.LV, 0x08000020)
        p.active = cl.OTHER
        p.call('grmod_after_transition')
        p.record(0, 0, (look, 11, 11))
        p.call('grmod_before_transition', cl.OTHER, 0x08000000)
        p.active = cl.LV
        p.call('grmod_after_transition')
        finish(p)
    visit(64 + 13)
    ok(p.v('film') == cine and p.v('nframe') == 1 and p.hashes() == live(cine, 1, 1, 1000), 'another film: its own counter, at 1')
    p.key(3000)
    finish(p)
    ok(p.nf(cine) == 2 and p.nf(FILM) == 3 and p.hashes() == live(cine, 2, 1, 1000), 'a photo advances only that film')
    visit(75)
    ok(p.v('film') == FILM and p.v('nframe') == 3 and p.hashes() == live(FILM, 3, 1, 1000), 'back to Portra: its count resumes at 3 (a roll put back)')
    visit(11)
    ok(p.v('film') == 21 and p.v('nframe') == 1 and p.hashes() == live(21, 1, 1, 1000), 'a non-film look: the neutral strip with its own counter')
    visit(75)
    for i in range(33):                                              # Portra: 3 .. 35 more photos to 36
        p.key(3000)
        finish(p)
    ok(p.nf(FILM) == 36 and p.rl(FILM) == 1 and p.nf(cine) == 2, 'Portra reaches 36, the other films are untouched')
    p.key(3000)
    finish(p)
    ok(p.nf(FILM) == 1 and p.rl(FILM) == 2 and p.rl(cine) == 1 and p.nf(cine) == 2 and p.hashes() == live(FILM, 1, 2, 1000), 'Portra wraps to 1 and its roll advances; the other films keep theirs')
    visit(64 + 13)
    ok(p.v('nframe') == 2 and p.v('roll') == 1 and p.hashes() == live(cine, 2, 1, 1000), 'back to CineStill: still frame 2 of roll 1')
    p.canaries()
    checks.append('per-film counters: Portra counts 3, CineStill starts at 1, back to Portra resumes at 3, a non-film look has its own, Portra wraps at 36 to 1 and advances only its own roll; every state equals the JS reference')

    # ---- 12. the film-load moment
    cine = slot_film[64 + 13]
    # a film change through a menu visit: the load plays, frame by frame equal to the JS reference, then the tab and counter settle
    p = ready(75)
    finish(p)
    hop(p, 64 + 13)
    ok(p.v('loads') == 1 and p.v('running') == 1 and p.v('shown') == 1 and len(p.children(p.roots[0])) == 4 and len(p.timers()) == 1, 'a film change at the return to the live view starts the load')
    got = [p.hashes()]
    times = [0, 33, 99, 330, 660, 990, 1320, 1450, 1650, 1749, 1980, 2150]
    done = 0
    for t in times[1:]:
        p.fire(t - done)
        done = t
        got.append(p.hashes())
    want = cl.js_hashes([cl.jscase('load', cine, 1, 1, t, peek=-1) for t in times])
    for t, g, w in zip(times, got, want):
        ok(g == w[1:], f'load frame at +{t} ms equals the JS reference')
    finish(p)
    ok(p.v('running') == 0 and not p.timers() and p.v('shown') == 1 and p.hashes() == live(cine, 1, 1, 1000), 'afterwards the tab and counter sit there, no timer')
    # a quick review chain and a menu visit with the same film replay nothing
    p.call('grmod_before_transition', cl.LV, 0x0800000c)
    p.active = cl.QV
    p.call('grmod_after_transition')
    p.call('grmod_before_transition', cl.QV, 0x08000000)
    p.active = cl.LV
    p.call('grmod_after_transition')
    finish(p)
    hop(p, 64 + 13)
    ok(p.v('loads') == 1 and p.v('sliding') == 1 and p.hashes() == live(cine, 1, 1, 0), 'the same film again: no load, the slide-in')
    finish(p)
    p.canaries()
    # the neutral strip: no load; and from the neutral strip to a film: the load
    hop(p, 11)
    ok(p.v('loads') == 1 and p.v('running') == 0 and p.v('sliding') == 1 and p.v('film') == 21 and p.hashes() == live(21, 1, 1, 0), 'a look that is not a film: no load, the slide-in')
    finish(p)
    hop(p, 64 + 13)
    ok(p.v('loads') == 2 and p.v('running') == 1 and p.hashes() == loadf(cine, 1, 1, 0), 'from the neutral strip to a film: the load plays (the counter of that film resumes: 1)')
    finish(p)
    checks.append('a film change at the return to the live view plays the load (twelve frames equal the JS reference) and the tab and counter settle; a quick review chain and a visit with the same film replay nothing; '
                  'the neutral strip gets the slide-in only; neutral to a film plays the load')

    # every film slot: the load frames equal the JS reference
    p = ready(75)
    finish(p)
    cases, got = [], []
    for look in list(range(64, 84)):
        if look == 75:
            continue
        film = slot_film[look]
        hop(p, look)
        ok(p.v('film') == film and p.v('running') == 1 and p.v('loads') >= 1, f'film {film}: the load starts')
        cases.append(film)
        got.append((film, p.hashes()))
        p.fire(1100)
        got.append((film, p.hashes()))
        p.fire(1050)
        got.append((film, p.hashes()))
        finish(p)
    wants = cl.js_hashes([cl.jscase('load', f, 1, 1, t, peek=-1) for f in cases for t in (0, 1100, 2150)])
    for (film, g), w in zip(got, wants):
        ok(g == w[1:], f'load of film {film} equals the JS reference')
    hop(p, 75)                                                      # Portra itself, from the film before it
    ok(p.hashes() == loadf(slot_film[75], 1, 1, 0), 'Portra loads too')
    finish(p)
    p.canaries()
    checks.append(f'every film slot ({len(cases) + 1} films): the load starts at the return to the live view and its first, middle and last frames equal the JS reference')

    # a photo during the load takes over; another film change (which needs a menu visit) restarts it; leaving the live view cancels it
    p = ready(75)
    finish(p)
    hop(p, 64 + 13)
    p.fire(792)
    p.key(0, 20)                                                     # a photo during the load: the capture signal, then the live view event
    ok(p.v('running') == 1 and p.v('shots') == 1 and p.v('nframe') == 2 and p.v('loads') == 1, 'a photo during the load: the shot moment takes over, the counter advances once')
    ok(p.hashes() == cl.js_hashes([cl.jscase('shot', cine, 1, 1, 0, peek=-1, hold=1)])[0][1:], 'the first shot frame (furniture held) equals the JS reference: no leftover load')
    finish(p)
    ok(p.hashes() == live(cine, 2, 1, 1000) and not p.timers(), 'and the tab and counter end showing 2')
    q = ready(75)
    finish(q)
    hop(q, 64 + 13)
    q.fire(800)
    q.call('grmod_before_transition', cl.LV, 0x08000020)             # to the menu again
    ok(not q.children(q.roots[0]) and not q.timers() and q.v('running') == 0 and q.v('shown') == 0, 'leaving the live view cancels the load at once')
    q.active = cl.OTHER
    q.call('grmod_after_transition')
    q.record(0, 0, (64 + 18, 11, 11))                                # another film
    q.call('grmod_before_transition', cl.OTHER, 0x08000000)
    q.active = cl.LV
    q.call('grmod_after_transition')
    f2 = slot_film[64 + 18]
    ok(q.v('loads') == 2 and q.v('running') == 1 and q.v('film') == f2 and q.hashes() == loadf(f2, 1, 1, 0), 'another film: its own load starts from the beginning')
    finish(q)
    ok(q.hashes() == live(f2, 1, 1, 1000), 'and settles')
    r = ready(75)
    finish(r)
    hop(r, 64 + 13)
    r.fire(800)
    r.call('grmod_before_transition', cl.LV, 0x08000020)
    r.active = cl.OTHER
    r.call('grmod_after_transition')
    r.call('grmod_before_transition', cl.OTHER, 0x08000000)
    r.active = cl.LV
    r.call('grmod_after_transition')                                 # back with the same film
    ok(r.v('loads') == 1 and r.v('running') == 0 and r.v('sliding') == 1 and r.hashes() == live(cine, 1, 1, 0), 'a menu visit during the load, same film: nothing is replayed, the slide-in')
    finish(r)
    ok(r.hashes() == live(cine, 1, 1, 1000), 'the permanent state')
    for x in (p, q, r):
        x.canaries()
    checks.append('a photo during the load takes over (the shot moment equals the JS reference, the counter advances once, the tab and counter end at 2); leaving the live view cancels the load at once; '
                  'another film then loads from the beginning; the same film replays nothing')

    # a film changed before the block exists; failures; no clock
    v = new(64 + 13)
    v.now = 21000
    v.put(ARMED, 4999)
    v.ev(0x0199)
    ok(v.v('loads') == 0 and v.v('sliding') == 1 and v.v('film') == cine and v.hashes() == live(cine, 1, 1, 0), 'a film chosen before the block exists: the first show is the slide-in, no load')
    finish(v)
    w = new(64 + 13)
    w.now = 5000
    w.key(100)
    ok(w.v('loads') == 0 and w.v('running') == 1, 'and a photo before the block exists still starts the shot moment, no load')
    finish(w)
    x = ready(75)
    finish(x)
    view = x.adapter_views()[0]
    x.call('grmod_before_transition', cl.LV, 0x08000020)
    x.active = cl.OTHER
    x.call('grmod_after_transition')
    x.record(0, 0, (64 + 13, 11, 11))
    x.uc.mem_write(view + 4, struct.pack('<I', 0x1234))             # a view the camera still owns: the attach fails
    x.call('grmod_before_transition', cl.OTHER, 0x08000000)
    x.active = cl.LV
    x.call('grmod_after_transition')
    ok(x.v('shown') == 0 and x.v('attach_failures') == 1 and x.v('loads') == 0 and not x.timers(), 'an attach failure shows nothing and loses nothing')
    x.uc.mem_write(view + 4, struct.pack('<I', 0))
    x.call('grmod_before_transition', cl.LV, 0x08000020)
    x.call('grmod_after_transition')
    ok(x.v('shown') == 1 and x.v('loads') == 1 and x.v('running') == 1, 'the next transition retries and the load plays (the film change was kept)')
    finish(x)
    y = ready(75)
    finish(y)
    y.call('grmod_before_transition', cl.LV, 0x08000020)
    y.active = cl.OTHER
    y.call('grmod_after_transition')
    y.record(0, 0, (64 + 13, 11, 11))
    y.call('grmod_before_transition', cl.OTHER, 0x08000000)
    y.active = cl.LV
    y.clock_ok = False
    y.call('grmod_after_transition')
    ok(y.v('shown') == 0 and y.v('loads') == 0 and not y.timers(), 'no clock: nothing shown, nothing broken')
    y.clock_ok = True
    y.call('grmod_before_transition', cl.LV, 0x08000020)
    y.call('grmod_after_transition')
    ok(y.v('running') == 1 and y.v('loads') == 1, 'and the next transition plays the load')
    finish(y)
    z = new()
    z.now = 30000
    z.put(ARMED, 5000)
    z.fail_at = {0}
    z.alloc_count = 0
    z.record(0, 0, (64 + 13, 11, 11))
    z.ev(0x0199)
    ok(z.state() == 0 and z.get(FAILED) == 1 and not z.children(z.roots[0]), 'an allocation failure: nothing shown, no crash')
    for q_ in (v, w, x, y, z):
        q_.canaries()
    checks.append('a film chosen before the block exists gets the slide-in only (and a photo there no load); an attach failure shows nothing and the next transition plays the load; no clock shows nothing and the next transition plays it; an allocation failure shows nothing')

    # the cost of the load, per tick
    from unicorn import UC_HOOK_CODE
    q = ready(75)
    finish(q)
    box = {'n': 0, 'on': False}

    def counter(uc, at, size, user):
        if box['on']:
            box['n'] += 1
    q.uc.hook_add(UC_HOOK_CODE, counter)
    hop(q, 64 + 13)
    ticks = []
    for i in range(30):
        box['n'] = 0
        box['on'] = True
        q.fire(33)
        box['on'] = False
        ticks.append(box['n'])
    load_cost = dict(load_tick_min=min(ticks), load_tick_max=max(ticks))
    finish(q)
    ok(q.v('running') == 0, 'the load finished')
    cost_load = load_cost
    checks.append(f'cost of the load per 33 ms tick in emulated instructions (native timer and dispatch included): {load_cost}')

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

    # refusals and failures: every step after a failure is skipped, the clean-up still runs, nothing leaks
    def run_with(q, ge=0, factory=None):
        photo(q)
        q.fail_ge = ge
        if factory is not None:
            q.fail_factory = {q.factory_calls + factory}
        base = len(q.allocations)
        q.key(3000)
        res = {}

        def w(x):
            if x.t2v('step') == 7 and not res:
                res.update(probe=[x.row('probe', i) for i in range(7)], s3a=x.row('s3a'), s3b=x.row('s3b'), s4=x.row('s4'), s5=x.row('s5'), s2=x.row('s2'),
                           na=x.t2v('n_alloc'), nf=x.t2v('n_free'), failed=x.t2v('failed'), frames=x.t2v('frames'))
        n = 0
        while q.get(T2FLAG) == 0 and n < 200:
            q.fire(33)
            paint(q)
            n += 1
        run_proof(q, watch=w)
        return res, base

    q = primed()
    res, base = run_with(q, ge=1000000)
    ok(q.get(T2FLAG) == 2 and [r['st'] for r in res['probe']] == [1, 1, 1, 1, 1, 2, 3] and res['s3b']['st'] == 3 and res['s3b']['why'] == 8 and res['s4']['st'] == 1 and res['s5']['st'] == 1,
       ('the allocator refuses 1 MB: S1 stops there, 1.4 MB and the buffered full view are skipped, the banded view still runs', res['probe'], res['s3b'], res['s4']))
    q = primed()
    res, base = run_with(q, ge=500000)
    ok(q.get(T2FLAG) == 2 and [r['st'] for r in res['probe']] == [1, 1, 1, 1, 2, 3, 3] and res['s3b']['st'] == 3 and res['s4']['st'] == 1, ('the allocator refuses 512 KB', res['probe']))
    q = primed()
    res, base = run_with(q, ge=q.T['sizeof'])
    ok(q.get(T2FLAG) == 3 and not q.t2p() and not res and q.v('shown') == 1 and len(q.children(q.roots[0])) == 4, 'the proof block cannot be allocated: it never runs, nothing is attached, flag 3')
    photo(q)
    ok(q.get(T2FLAG) == 3 and q.v('shots') == 3 and q.hashes() == live(FILM, 4, 1, 1000), 'and Loaded goes on as in 4a; the proof does not run again in this power-on')
    q = primed()
    res, base = run_with(q, factory=1)
    ok(q.get(T2FLAG) == 3 and res['s3a']['st'] == 2 and res['s3a']['why'] == 2 and res['s3b']['st'] == 3 and res['s4']['st'] == 3 and res['s5']['st'] == 1 and res['na'] == res['nf'],
       ('a refused view: S3a fails, the rest are skipped, S5 cleans', res['s3a'], res['s5']))
    q = primed()
    res, base = run_with(q)
    made = [ptr for ptr, size in q.allocations[base:] if size >= 40000]
    ok(all(ptr in q.frees for ptr in made) and len(made) >= 10, ('nothing leaks: every proof block was freed', len(made), [ptr for ptr in made if ptr not in q.frees][:3]))
    # a transition and a photo end the proof at once
    q = primed()
    photo(q)
    q.key(3000)
    n = 0
    while q.get(T2FLAG) == 0 and n < 200:
        q.fire(33)
        paint(q)
        n += 1
    base = len(q.allocations)
    n = 0
    while not (q.t2p() and q.t2v('step') == 5 and q.t2v('draws') >= 3) and n < 600:
        q.fire(33)
        paint(q)
        n += 1
    ok(q.t2p() and q.t2v('mode') == 2, 'the proof is in its banded step')
    ok(len(q.children(q.roots[0])) == 6, ('the four Loaded views, the test view and the panel are children', len(q.children(q.roots[0]))))
    q.call('grmod_before_transition', cl.LV, 0x08000020)
    ok(not q.t2p() and q.get(T2FLAG) == 3 and not q.children(q.roots[0]) and not q.timers(), 'a menu transition ends the proof at once: everything detached, flag 3')
    made = [ptr for ptr, size in q.allocations[base:] if size >= 40000]
    ok(all(ptr in q.frees for ptr in made), 'and the proof\'s buffers were freed')
    q.active = cl.OTHER
    q.call('grmod_after_transition')
    q.call('grmod_before_transition', cl.OTHER, 0x08000000)
    q.active = cl.LV
    q.call('grmod_after_transition')
    finish(q)
    ok(q.get(T2FLAG) == 3 and q.v('shown') == 1 and not q.t2p(), 'back in the live view Loaded is as before and the proof does not restart')
    q.canaries()
    r = primed()
    photo(r)
    r.key(3000)
    n = 0
    while not (r.t2p() and r.t2v('step') == 5 and r.t2v('draws') >= 2) and n < 600:
        r.fire(33)
        paint(r)
        n += 1
    shots = r.v('shots')
    r.key(0, 20)
    ok(not r.t2p() and r.get(T2FLAG) == 3 and r.v('shots') == shots + 1 and r.v('running') == 1, 'a photo during the proof ends it, the photo\'s strips run')
    finish(r)
    r.canaries()
    checks.append('refusals: the allocator refusing 1 MB or 512 KB stops S1 there and skips only what needs the big block; a proof block that cannot be allocated never runs; a refused view skips the rest and S5 cleans; '
                  'every proof block is freed; a menu transition or a photo ends the proof at once and it never restarts in this power-on')

    # the cost of the banded frame and of the proof's ticks, in emulated instructions
    from unicorn import UC_HOOK_CODE
    s = primed()
    photo(s)
    s.key(3000)
    n = 0
    while s.get(T2FLAG) == 0 and n < 200:
        s.fire(33)
        paint(s)
        n += 1
    box = {'n': 0, 'on': False}

    def counter(uc, at, size, user):
        if box['on']:
            box['n'] += 1
    s.uc.hook_add(UC_HOOK_CODE, counter)
    got = {'tick_max': 0}
    n = 0
    while s.get(T2FLAG) == 1 and n < 900:
        box['n'] = 0
        box['on'] = True
        s.fire(33)
        box['on'] = False
        if s.t2p():
            got['tick_max'] = max(got['tick_max'], box['n'])
            mode = s.t2v('mode')
            box['n'] = 0
            box['on'] = True
            paint(s)
            box['on'] = False
            if mode == 2 and 'band' not in got and s.t2v('draws') >= 2:
                got['band'] = box['n']
            if mode == 1 and 'buf' not in got and s.t2v('draws') >= 1:
                got['buf'] = box['n']
        n += 1
    t2cost = dict(s4_frame_paint=got.get('band'), buffered_paint=got.get('buf'), proof_tick_max=got['tick_max'])
    ok(got.get('band') and got['band'] > 1000000, ('cost of a banded full-screen frame (the paint pass with the test view), instructions', t2cost))
    t = primed()
    box2 = {'n': 0, 'on': False}

    def counter2(uc, at, size, user):
        if box2['on']:
            box2['n'] += 1
    t.uc.hook_add(UC_HOOK_CODE, counter2)
    box2['on'] = True
    t.ev(0x0199)
    box2['on'] = False
    t2cost['ordinary_event_callback'] = box2['n']
    checks.append(f'cost in emulated instructions: {t2cost} (the banded frame is the whole paint pass; the proof ticks include the native timer and dispatch)')

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
