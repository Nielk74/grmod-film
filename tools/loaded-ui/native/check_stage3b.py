"""Stage 3b scenarios (capture signal before a photo, per-film counters; the permanent tab and counter of 3a), run in the emulator on the delivered image
(LOADED_VARIANT=stage3bengine or stage3bfilmpack).

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

VARIANTS = ('stage3bengine', 'stage3bfilmpack')
os.environ['LOADED_VARIANT'] = os.environ.get('LOADED_VARIANT') if os.environ.get('LOADED_VARIANT') in VARIANTS else 'stage3bengine'
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_adapter_loaded as cl  # noqa: E402
ca = cl.ca
OUT, BUILD = cl.OUT, cl.BUILD
VIEWS = cl.VIEWS
LAYOUT = ['views', 'pixels', 'shots', 'pending_roll', 'engine', 'sizeof', 'pend', 'npend', 'last_accept', 'accepts', 'ignored', 'fallbacks', 'consumed', 'dropped',
          'running', 'params', 'shown', 'sliding', 'nframes', 'rolls', 'film', 'shows', 'hides', 'film_changes', 'attach_failures', 'rej_nosignal', 'rej_stale', 'sig_cleared']
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

    def _factory(self, cpu, at, size, user):
        n = self.factory_calls
        self.factory_calls += 1
        if n in self.fail_factory:
            self.ret(0)

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
    ok(p.v('shown') == 1 and p.v('sliding') == 1 and len(p.children(root)) == 4 and p.v('film') == cine and p.v('nframe') == 1 and p.v('roll') == 1 and p.v('film_changes') == 1, 'back in the live view: the slide-in, the new film with its own counter (1)')
    ok(p.hashes() == live(cine, 1, 1, 0), 'the first slide-in frame shows the new film (JS reference)')
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
