"""Stage 5a scenarios (the end-of-roll contact sheet, tier 2 design A; the whole of stage 4a kept), run in the emulator on the delivered image
(LOADED_VARIANT=stage5aengine, stage5afilmpack, stage5atest3engine or stage5atest3filmpack).

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

VARIANTS = ('stage5aengine', 'stage5afilmpack', 'stage5atest3engine', 'stage5atest3filmpack')
os.environ['LOADED_VARIANT'] = os.environ.get('LOADED_VARIANT') if os.environ.get('LOADED_VARIANT') in VARIANTS else 'stage5aengine'
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_adapter_loaded as cl  # noqa: E402
ca = cl.ca
OUT, BUILD = cl.OUT, cl.BUILD
VIEWS = cl.VIEWS
LAYOUT = ['views', 'pixels', 'shots', 'pending_roll', 'engine', 'sizeof', 'pend', 'npend', 'last_accept', 'accepts', 'ignored', 'fallbacks', 'consumed', 'dropped',
          'running', 'params', 'shown', 'sliding', 'nframes', 'rolls', 'film', 'shows', 'hides', 'film_changes', 'attach_failures', 'rej_nosignal', 'rej_stale', 'sig_cleared', 'loads',
          'full', 'sheet', 'sheets', 'sheet_alloc_fail', 'sheet_view_fail', 'sheet_cancels', 'sheet_ends', 'att', 'sheet_ready']
ARMED, FAILED, SIGNAL = 0x55804390, 0x5580438c, 0x55804394
zlib_crc = zlib.crc32
TOP, BOTTOM, COUNTER, TAB = 0, 1, 2, 3


class F(cl.LoadedFixture):
    fail_ge = 0

    def __init__(self, *a):
        self.big_live, self.big_free, self.big_fresh, self.big_allocs = {}, [], 0, 0
        super().__init__(*a)
        from unicorn import UC_HOOK_CODE
        self.factory_calls = 0
        self.fail_factory = set()
        self.uc.hook_add(UC_HOOK_CODE, self._factory, begin=0x533ad7f0, end=0x533ad7f0)
        self.M = dict(zip(LAYOUT, [self.symbol_word('grmod_layout', i) for i in range(len(LAYOUT))]))

    def _hook(self, cpu, at, size, user):
        # the fixture's allocator stops at 1 MiB and never reuses: blocks of 1 MiB and more (the sheet buffer) come from a bump area with a free list
        if at in (0x536af2a8, 0x536af31c):
            size = self.r(0)
            if self.fail_ge and size >= self.fail_ge:
                self.alloc_count += 1
                self.ret(0)
                return
            if size >= 0x100000:
                n = self.alloc_count
                self.alloc_count += 1
                if n in self.fail_at:
                    self.ret(0)
                    return
                self.big_allocs += 1
                for k, (ptr, sz) in enumerate(self.big_free):
                    if sz == size:
                        self.big_free.pop(k)
                        self.big_live[ptr] = size
                        self.ret(ptr)
                        return
                ptr = self.heap
                self.heap = (ptr + size + 95) & ~31
                assert self.heap < 0x59e00000, 'the fixture heap is full'
                self.uc.mem_write(ptr - 32, bytes([0xa5]) * (size + 64))
                self.allocations.append((ptr, size))
                self.big_live[ptr] = size
                self.big_fresh += 1
                self.ret(ptr)
                return
        elif at in (0x536af2e4, 0x536af358):
            freed = self.r(0)
            if freed in self.big_live:
                self.big_free.append((freed, self.big_live.pop(freed)))
        super()._hook(cpu, at, size, user)

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

    def finish(p, limit=400):
        n = 0
        while p.timers() and n < limit:
            p.fire(250 if p.state() and p.v('sheet') else 33)       # the sheet's frames are rendered for the current clock: bigger steps skip frames
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

    # ---- 3. the end of the roll: the contact sheet (tier 2, design A)
    ROLLN = 3 if 'test3' in os.environ['LOADED_VARIANT'] else 36
    SHEET = 720 * 480 * 4
    ST = [0, 300, 1000, 1700, 2500, 3300]                           # the sheet's moments that are compared with the JS reference

    def full_crc(p):
        return zlib.crc32(bytes(p.uc.mem_read(p.v('full'), SHEET)))

    def sheet_hashes(p):
        return [full_crc(p)] + p.hashes()

    def js_roll(film, roll, ts):
        return cl.js_hashes([cl.jscase('roll', film, 36, roll, t, peek=-1, hold=1, tier=2) for t in ts])

    def matches(got, want):
        """All five views against the JS reference; in the TEST image (a roll of three) the bands and the counter count from 3, so only the sheet itself."""
        return got == want if ROLLN == 36 else got[0] == want[0]

    def paint(p):
        p.call(0x53391b14, p.roots[0])

    def drive(p, cap=300):
        """Fire 33 ms ticks until the sheet is running or the moment is over."""
        n = 0
        while p.v('running') and not p.v('sheet') and n < cap:
            p.fire(33)
            n += 1
        return n

    def poke_last(p, film):
        p.put(p.state() + p.M['nframes'] + 4 * film, ROLLN)

    def to_sheet(p, film=FILM, poke=True):
        """The photo that completes the roll (the counter is poked to the last frame first), then ticks until the sheet runs. Returns the clock of its first frame."""
        if poke:
            poke_last(p, film)
        p.key(3000)
        drive(p)
        return p.now

    def at(p, base, t):
        d = base + t - p.now
        assert d >= 0
        p.fire(d)

    def screen_rows(p, y0, y1):
        return bytes(p.uc.mem_read(ca.DEST + 32 + y0 * 736 * 4, (y1 - y0) * 736 * 4))

    def sheet_on_screen(p):
        """Rows 44 to 375 (nothing overlaps them): every pixel of the buffer is on the screen at its place."""
        paint(p)
        buf = bytes(p.uc.mem_read(p.v('full'), SHEET))
        scr = screen_rows(p, 44, 376)
        return all(scr[(y - 44) * 736 * 4:(y - 44) * 736 * 4 + 720 * 4] == buf[y * 720 * 4:(y + 1) * 720 * 4] for y in range(44, 376))

    def big_blocks(p):
        return [a for a in p.allocations if a[1] == SHEET]

    p = ready()
    finish(p)
    if ROLLN == 36:
        for i in range(35):
            p.key(3000)
            finish(p)
    else:
        for i in range(ROLLN - 1):
            p.key(3000)
            finish(p)
    ok(p.v('nframe') == ROLLN and p.v('roll') == 1 and p.hashes() == live(FILM, ROLLN, 1, 1000), f'after {ROLLN - 1} photos the counter shows {ROLLN}')
    ok(p.v('full') == 0 and not big_blocks(p) and p.v('sheets') == 0 and p.v('att') == 0xf, 'no sheet buffer exists before the roll ends: the views are the four small ones')
    p.key(3000)
    ok(p.v('pending_roll') == 1 and p.v('nframe') == 1 and p.v('roll') == 2, f'the photo {ROLLN} wraps the counter to 1 and advances the roll of that film')
    if ROLLN == 36:
        p.fire(300)
        ok(p.hashes() == cl.js_hashes([cl.jscase('shot', FILM, 36, 1, 300, peek=-1, hold=1)])[0][1:], 'the strips of the completing photo run as before (frame 36, furniture held)')
    ok(p.v('sheet') == 0 and p.v('full') == 0, 'the sheet waits for the end of the strips')
    drive(p)
    base = p.now
    root = p.roots[0]
    ok(p.v('sheet') == 1 and p.v('sheets') == 1 and p.v('running') == 1 and p.v('pending_roll') == 0 and p.v('sheet_alloc_fail') == 0, 'the strips are over: the sheet starts')
    ok(len(big_blocks(p)) == 1 and big_blocks(p)[0][0] == p.v('full') and p.v('full') & 3 == 0, 'one 1,382,400-byte buffer was allocated, for the sheet')
    kids = p.children(root)
    views5 = p.adapter_views() + [p.get(p.state() + p.layout[0] + 16)]
    ok(len(kids) == 5 and kids[0] == views5[4] and kids[1:] == views5[:4] and p.v('att') == 0x1f, ('the full-screen view is the first child (lowest z-order), the four small views stay above it', [hex(k) for k in kids]))
    paint(p)
    rect = list(struct.unpack('<4i', p.uc.mem_read(views5[4] + 0x30, 16)))
    ok(rect == [0, 0, 720, 480], ('the layout accepted the full-screen view', rect))
    ok(('timer_start', 50) in p.events, 'the sheet ticks every 50 ms')
    got = []
    want = js_roll(FILM, 1, ST)
    last_t = 0
    for t, w in zip(ST, want):
        at(p, base, t)
        got.append(sheet_hashes(p))
        ok(matches(got[-1], w), f'sheet frame at +{t} ms equals the JS reference (CRC of the full buffer{", the four small views" if ROLLN == 36 else ""})')
        ok(sheet_on_screen(p), f'the sheet pixels are on the screen at +{t} ms')
    ok(p.v('sheet') == 1 and len(p.children(root)) == 5, 'the sheet runs for 3.4 s')
    for ident in (0x0164, 0x0165, 0x0102, 0x01a4, 0x001b, 0x0199):   # half press and periodic events during the sheet: nothing happens
        p.ev(ident, 5)
    ok(p.v('sheet') == 1 and p.v('shots') == ROLLN and p.v('sheets') == 1, 'a half press (AF) and periodic events do nothing to the sheet')
    at(p, base, 3399)
    ok(p.v('sheet') == 1 and p.v('full') != 0, 'at +3399 ms the sheet is still running')
    p.fire(1)
    ok(p.v('sheet') == 0 and p.v('full') == 0 and p.v('sheet_ends') == 1 and p.v('running') == 0 and p.v('att') == 0xf and len(p.children(root)) == 4 and not p.timers(), 'the sheet is over: the view is gone, the buffer is freed, no timer')
    ok(p.get(p.state() + p.layout[1]) != 0 and not p.big_live, 'nothing of the sheet is still allocated')
    ok(p.hashes() == live(FILM, 1, 2, 1000), 'the tab and counter are back at frame 1 of roll 2 (JS reference)')
    kids = p.children(root)
    ok(kids == views5[:4] and views5[4] not in kids, 'the four small views are the children again')
    paint(p)
    p.canaries()
    checks.append(f'the end of the roll ({ROLLN} photos): no buffer before it; the strips of the completing photo run, then one 1,382,400-byte buffer is allocated and the full-screen view is added below the four small views (layout rectangle 0,0,720,480); '
                  f'six sheet frames equal the JS reference by CRC{" (all five views)" if ROLLN == 36 else " (the sheet view; the bands and the counter of the test image count from 3)"}, the sheet pixels are on the screen; a half press does nothing; '
                  'at the end the view is gone, the buffer freed, the tab and counter are at 1 of the next roll, no timer')

    # every film: the first frame, a filled frame and the end of the sheet equal the JS reference (the film tint, the chip, the tab pushed aside)
    films = sorted(set(slot_film.values()) | {21})
    got, cases = [], []
    for film in films:
        look = next((k for k, v in slot_film.items() if v == film), 11) if film != 21 else 11
        q = ready(look)
        finish(q)
        base_q = to_sheet(q, film)
        ok(q.v('film') == film and q.v('sheet') == 1, f'film {film}: the sheet starts')
        for t in (0, 1500):
            if t:
                at(q, base_q, t)
            got.append((film, t, sheet_hashes(q)))
        at(q, base_q, 3399)
        got.append((film, 3399, sheet_hashes(q)))
        q.fire(60)
        ok(q.v('sheet') == 0 and q.v('full') == 0 and q.hashes() == live(film, 1, 2, 1000), f'film {film}: the sheet ends and the counter shows 1 of roll 2')
    wants = cl.js_hashes([cl.jscase('roll', film, 36, 1, t, peek=-1, hold=1, tier=2) for film in films for t in (0, 1500, 3399)])
    for (film, t, g), w in zip(got, wants):
        ok(matches(g, w), f'film {film}: sheet frame at +{t} ms equals the JS reference')
    checks.append(f'every film ({len(films)} films, the neutral strip included): the sheet starts at the end of the roll; its frames at 0, 1500 and 3399 ms equal the JS reference; it ends with the counter at 1 of the next roll')

    # ---- 3b. the failure paths: the moment is skipped, once per roll end, nothing leaks
    SK = 1_000_000
    p = ready()
    finish(p)
    p.fail_ge = SK
    base = to_sheet(p)
    ok(p.v('sheet') == 0 and p.v('sheet_alloc_fail') == 1 and p.v('sheets') == 0 and p.v('running') == 0 and not p.timers() and len(p.children(p.roots[0])) == 4 and p.v('att') == 0xf,
       'the 1.38 MB allocation fails: the moment is skipped, the four small views stay, no timer')
    ok(p.hashes() == live(FILM, 1, 2, 1000) and p.v('nframe') == 1 and p.v('roll') == 2, 'and the tab and counter are back at frame 1 of the next roll')
    allocs = len(p.allocations)
    for _ in range(20):
        p.fire(33)
        p.ev(0x0199, 10)
    ok(p.v('sheet_alloc_fail') == 1 and len(p.allocations) == allocs and not p.timers(), 'one attempt per roll end: not retried')
    p.fail_ge = 0
    base = to_sheet(p)
    ok(p.v('sheet') == 1 and p.v('sheets') == 1 and p.v('sheet_alloc_fail') == 1, 'the next roll end tries again and succeeds')
    p.fire(3500)
    ok(p.v('sheet') == 0 and not p.big_live and p.hashes() == live(FILM, 1, 3, 1000), 'and ends normally')
    p.canaries()
    # the view the camera refuses (the factory returns null for the full-screen view)
    q = ready()
    finish(q)
    q.fail_factory = {q.factory_calls}
    to_sheet(q)
    ok(q.v('sheet') == 0 and q.v('sheet_view_fail') == 1 and q.v('sheet_alloc_fail') == 0 and not q.big_live and q.v('att') == 0xf and len(q.children(q.roots[0])) == 4 and not q.timers() and q.v('shown') == 1,
       'a view the camera refuses: the buffer is freed at once, the four small views stay, the moment is skipped')
    ok(q.hashes() == live(FILM, 1, 2, 1000), 'and the tab and counter are back at frame 1 of the next roll')
    q.fail_factory = set()
    to_sheet(q)
    ok(q.v('sheet') == 1 and q.v('sheet_view_fail') == 1, 'the next roll end plays the sheet')
    q.fire(3500)
    ok(q.v('sheet') == 0 and not q.big_live, 'and ends')
    q.canaries()
    # the clock fails at the moment the sheet should start: everything is hidden (the usual no-clock rule), nothing is allocated
    s = ready()
    finish(s)
    poke_last(s, FILM)
    s.key(3000)
    s.clock_ok = False
    s.fire(1600)
    ok(s.v('sheet') == 0 and s.v('shown') == 0 and not s.timers() and not s.children(s.roots[0]) and not s.big_live and not big_blocks(s), 'no clock when the sheet should start: nothing is shown, nothing is allocated')
    s.clock_ok = True
    s.call('grmod_before_transition', cl.LV, 0x08000020)
    s.active = cl.OTHER
    s.call('grmod_after_transition')
    s.call('grmod_before_transition', cl.OTHER, 0x08000000)
    s.active = cl.LV
    s.call('grmod_after_transition')
    ok(s.v('shown') == 1 and s.v('sheet') == 0 and s.hashes() == live(FILM, 1, 2, 0) , 'the next transition shows the tab and counter again (frame 1, roll 2)')
    finish(s)
    # no clock in the middle of the sheet
    u = ready()
    finish(u)
    base = to_sheet(u)
    at(u, base, 800)
    u.clock_ok = False
    u.fire(50)
    ok(u.v('sheet') == 0 and u.v('shown') == 0 and not u.children(u.roots[0]) and not u.big_live and not u.timers() and u.v('sheet_cancels') == 1, 'no clock during the sheet: it is cancelled, the buffer freed, nothing stays')
    for x in (p, q, s, u):
        x.canaries()
    checks.append('failures: a refused 1.38 MB allocation or a refused view skips the moment (counted, one attempt per roll end, the buffer freed, the four small views stay, the counter at 1 of the next roll) and the next roll end plays it; '
                  'a missing clock when the sheet should start allocates nothing and shows nothing, a missing clock during the sheet cancels it and frees the buffer')

    # ---- 3c. cancel by menu, playback, movie, canvas deletion, a photo, a film change; at several moments of the sheet
    def cancelled(x, label):
        ok(x.v('sheet') == 0 and x.v('full') == 0 and not x.big_live and not x.timers() and x.v('running') == 0, f'{label}: the sheet is cancelled, the buffer is freed, no timer')

    for t, how in ((200, 'menu'), (1100, 'playback'), (2000, 'menu'), (3300, 'playback')):
        x = ready()
        finish(x)
        base = to_sheet(x)
        at(x, base, t)
        ok(x.v('sheet') == 1, f'at +{t} ms the sheet runs')
        x.call('grmod_before_transition', cl.LV, 0x08000020 if how == 'menu' else 0x0800000d)
        ok(not x.children(x.roots[0]) and x.v('shown') == 0, f'a {how} transition at +{t} ms hides everything at once')
        cancelled(x, f'{how} at +{t} ms')
        ok(x.v('sheet_cancels') == 1 and x.v('att') == 0, 'counted as a cancel')
        x.active = cl.OTHER
        x.call('grmod_after_transition')
        x.call('grmod_before_transition', cl.OTHER, 0x08000000)
        x.active = cl.LV
        x.call('grmod_after_transition')
        ok(x.v('shown') == 1 and x.v('sheet') == 0 and x.v('sheets') == 1 and x.v('sliding') == 1 and len(x.children(x.roots[0])) == 4 and x.hashes() == live(FILM, 1, 2, 0), 'back in the live view: the slide-in at frame 1 of roll 2, the sheet is not replayed')
        finish(x)
        ok(x.hashes() == live(FILM, 1, 2, 1000) and not x.timers(), 'and the permanent state')
        x.canaries()
    x = ready()
    finish(x)
    base = to_sheet(x)
    at(x, base, 1500)
    x.call('grmod_before_transition', cl.LV, 0x08000001)              # movie
    x.record(1, 0, (75, 11, 11))
    x.call('grmod_after_transition')
    cancelled(x, 'a switch to movie mode at +1500 ms')
    ok(x.v('shown') == 0 and not x.children(x.roots[0]), 'nothing is shown in movie mode')
    x = ready()
    finish(x)
    base = to_sheet(x)
    at(x, base, 1500)
    x.call('grmod_before_canvas_delete', x.roots[0])
    cancelled(x, 'a canvas deletion at +1500 ms')
    ok(x.v('shown') == 0 and not x.children(x.roots[0]), 'and nothing remains attached')
    # a film change cancels the sheet (the menu visit) and the new film's load starts as in 4a
    x = ready()
    finish(x)
    base = to_sheet(x)
    at(x, base, 1800)
    hop(x, 64 + 13)
    cine = slot_film[64 + 13]
    ok(x.v('sheet') == 0 and not x.big_live and x.v('loads') == 1 and x.v('running') == 1 and x.v('film') == cine and x.hashes() == loadf(cine, 1, 1, 0) and len(x.children(x.roots[0])) == 4,
       'a film change during the sheet: the sheet is cancelled, the new film\'s load starts as in 4a')
    finish(x)
    ok(x.hashes() == live(cine, 1, 1, 1000), 'and settles')
    x.canaries()
    # a photo during the sheet: the shutter has priority
    for t in (1100, 2300, 3350):
        x = ready()
        finish(x)
        base = to_sheet(x)
        at(x, base, t)
        shots = x.v('shots')
        x.key(0, 20)
        ok(x.v('sheet') == 0 and x.v('full') == 0 and not x.big_live and x.v('shots') == shots + 1 and x.v('running') == 1 and x.v('sheet_cancels') == 1, f'a photo at +{t} ms of the sheet cancels it at once; the strips of the photo run')
        ok(x.v('nframe') == 2 and x.v('roll') == 2 and len(x.children(x.roots[0])) == 4 and x.v('att') == 0xf, 'the counter advances from 1 of the new roll; the four small views are the children')
        ok(x.hashes() == cl.js_hashes([cl.jscase('shot', FILM, 1, 2, 0, peek=-1, hold=1)])[0][1:], 'the first strip frame of the new photo equals the JS reference (no leftover of the sheet)')
        finish(x)
        ok(x.hashes() == live(FILM, 2, 2, 1000) and not x.timers() and x.v('shown') == 1, 'and the tab and counter end showing 2 of roll 2')
        x.canaries()
    # a photo during the strips of the completing photo (before the sheet starts): the sheet is dropped, the shutter wins
    x = ready()
    finish(x)
    poke_last(x, FILM)
    x.key(3000)
    x.fire(700)
    x.call('grmod_on_shot')                                           # the completion of the first photo only consumes its acceptance
    x.call('grmod_on_shot')                                           # a second completion with no acceptance: the late start of another photo (a 013E inside 2 s of an accepted one is ignored)
    ok(x.v('sheet') == 0 and x.v('pending_roll') == 0 and x.v('running') == 1 and not big_blocks(x), 'a photo during the strips of the last frame: no sheet for that roll, the strips of the new photo run')
    finish(x)
    ok(x.v('sheets') == 0 and x.v('nframe') == 2 and x.v('roll') == 2 and x.hashes() == live(FILM, 2, 2, 1000), 'and nothing was allocated')
    checks.append('cancel: a menu, playback, movie switch or canvas deletion at several moments of the sheet hides everything at once and frees the buffer, the return shows the slide-in at frame 1 of the next roll and the sheet is not replayed; '
                  'a film change cancels it and the new film loads (4a); a photo at three moments of the sheet cancels it, its strips run and the counter advances from 1 of the new roll; a photo during the last strips drops the sheet')

    # ---- 3d. two roll ends in a row (different films) and many roll ends: no leak
    p = ready()
    finish(p)
    to_sheet(p, FILM)
    p.fire(3500)
    ok(p.v('sheets') == 1 and p.v('sheet_ends') == 1 and p.hashes() == live(FILM, 1, 2, 1000), 'the first roll ends (Portra)')
    visit_look = 64 + 13
    p.call('grmod_before_transition', cl.LV, 0x08000020)
    p.active = cl.OTHER
    p.call('grmod_after_transition')
    p.record(0, 0, (visit_look, 11, 11))
    p.call('grmod_before_transition', cl.OTHER, 0x08000000)
    p.active = cl.LV
    p.call('grmod_after_transition')
    finish(p)
    cine = slot_film[visit_look]
    ok(p.v('film') == cine and p.v('loads') == 1, 'another film is loaded')
    base = to_sheet(p, cine)
    ok(p.v('sheet') == 1 and p.v('sheets') == 2 and len(big_blocks(p)) == 1, 'the second roll end (another film) plays its sheet; the buffer of the first was reused by the fixture allocator')
    at(p, base, 1500)
    ok(matches(sheet_hashes(p), js_roll(cine, 1, [1500])[0]), 'and its frame equals the JS reference for that film')
    p.fire(2000)
    ok(p.v('sheet') == 0 and not p.big_live and p.hashes() == live(cine, 1, 2, 1000) and p.rl(FILM) == 2 and p.rl(cine) == 2, 'both films advanced their own roll')
    p.canaries()
    # many roll ends on one instance: every block freed, none leaked, the heap grows once
    m = ready()
    finish(m)
    heap0 = None
    for k in range(10):
        poke_last(m, FILM)
        m.key(3000)
        drive(m)
        if heap0 is None:
            heap0 = m.heap
        m.fire(1500)
        m.fire(2000)
        ok(m.v('sheet') == 0 and not m.big_live and m.v('full') == 0 and m.v('att') == 0xf, f'roll end {k + 1}: the sheet is gone and nothing is allocated')
    ok(m.v('sheets') == 10 and m.v('sheet_ends') == 10 and m.heap == heap0 and m.big_fresh == 1 and m.big_allocs == 10, 'ten roll ends: ten sheets, every buffer freed, none leaked')
    ok(m.v('roll') == 11 and m.hashes() == live(FILM, 1, 11, 1000) and not m.timers(), 'and the roll counter is 11')
    m.canaries()
    ok('grmod_t2_layout' not in symbols, 'the tier 2 proof of stage 4b is not in this image')
    checks.append('two roll ends in a row with different films: each plays its sheet, each film advances its own roll; ten roll ends in a row: ten sheets, every buffer freed, no leak')

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

    if ROLLN == 36:                                                # the long scenarios of stage 4a (36 photos); the test image has its own
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
        count, nfrees, sends0 = len(p.allocations), len(p.frees), p.v('sheet_ends')
        for i in range(60):
            p.key(3000)
            finish(p)
            p.call('grmod_on_shot')
        small = [sz for _, sz in p.allocations[count:] if sz != SHEET]
        ok(len(p.allocations) - count - len(small) == 1 and len(small) <= 4 and max(small + [0]) <= 512 and not p.big_live and p.v('shown') == 1, ('sixty more photos (one roll end among them): the only allocations are the sheet buffer (freed) and the camera growing its own child list when the fifth child is added', small))
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

    if ROLLN == 36:                                                # the long scenarios of stage 4a (36 photos); the test image has its own
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

    # the cost of the sheet in emulated instructions (sampled ticks: a Python hook on every instruction is slow)
    if ROLLN == 36:
        from unicorn import UC_HOOK_CODE
        q = ready(75)
        finish(q)
        sbox = {'n': 0, 'on': False}

        def scount(uc, at_, size, user):
            if sbox['on']:
                sbox['n'] += 1
        q.uc.hook_add(UC_HOOK_CODE, scount)
        poke_last(q, FILM)
        q.key(3000)
        start_cost = None
        for _ in range(300):
            sbox['n'] = 0
            sbox['on'] = True
            q.fire(33)
            sbox['on'] = False
            if q.v('sheet'):
                start_cost = sbox['n']
                break
        sbase = q.now
        ticks, paints = [], []
        for t in (50, 150, 450, 800, 1200, 1600, 2000, 2400, 2800, 3300):
            sbox['n'] = 0
            sbox['on'] = True
            at(q, sbase, t)
            sbox['on'] = False
            ticks.append(sbox['n'])
            sbox['n'] = 0
            sbox['on'] = True
            paint(q)
            sbox['on'] = False
            paints.append(sbox['n'])
        sbox['n'] = 0
        sbox['on'] = True
        at(q, sbase, 3400)
        sbox['on'] = False
        end_cost = sbox['n']
        ok(q.v('sheet') == 0, 'the sampled sheet ended')
        sheet_cost = dict(sheet_start_tick=start_cost, sheet_tick_min=min(ticks), sheet_tick_max=max(ticks), sheet_tick_mean=sum(ticks) // len(ticks),
                          sheet_paint_min=min(paints), sheet_paint_max=max(paints), sheet_paint_mean=sum(paints) // len(paints), sheet_end_tick=end_cost,
                          sheet_frames=68, sheet_total_estimate=68 * (sum(ticks) // len(ticks) + sum(paints) // len(paints)))
        ok(max(ticks) > 1000000, ('the sheet frames cost instructions', sheet_cost))
        checks.append(f'cost of the sheet in emulated instructions (ten sampled ticks across the 3.4 s moment, the native timer and dispatch included, and the paint pass that copies the 1.38 MB buffer): {sheet_cost}; '
                      'the estimate takes 68 frames of 50 ms')
    else:
        sheet_cost = {}

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
    cost.update(sheet_cost)
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
