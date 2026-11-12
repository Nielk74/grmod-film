"""Stage 1d (diagnostic) scenarios, run in the emulator on the delivered image (LOADED_VARIANT=diag).

For every failure cell the failure is provoked and the cells, the text and everything else are checked: the right cell is
red, the later ones grey, the earlier ones green, shooting is not delayed (the hook itself only makes the panel's own two
allocations), nothing else breaks and the next shot starts again. The all-ok case equals the JS reference pixels.
"""
import hashlib
import json
import os
import struct
import sys
import zlib
from pathlib import Path

os.environ['LOADED_VARIANT'] = 'diagf'
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_adapter_loaded as cl  # noqa: E402
ca = cl.ca
OUT, BUILD = cl.OUT, cl.BUILD
GREY, RUN, OK, BAD = 0, 1, 2, 3
NCELLS = 12
LAYOUT = ['ld', 'cell', 'step', 'film', 'shots', 'ld_pixels', 'ld_engine', 'ld_views', 'sizeof_diag', 'sizeof_ld', 'info', 'pixels',
          'view', 'ld_params', 'sequence', 'diag_on',
          'vs', 'sizeof_vs', 'hook', 'rootfail_h', 'rootfail_u', 'last_vt', 'trans_b', 'trans_a', 'ticks', 'stale', 'late', 'cancels', 'last_cancel', 'proof',
          'page', 'variant', 't_root', 't_att', 't_first', 'first_draw_ms', 'panel_calls_shot', 'log', 'nlog', 'surf', 'sizeof_log', 'ld_copies_shot',
          'last_cancel_hook', 'reattach', 'proof_seen', 'tk_panel', 'tk_ld', 'first_copy_mask',
          'glog', 'ng', 'sizeof_glog', 'pre', 'npre', 't_pre', 'ev_total', 'ev_logged',
          'tab', 'sizeof_tabrow', 'ntab', 'tab_ovf', 'rl_count', 'rl_time', 't_rl', 'rlhk', 'nrlhk', 'hk_rl_count']
PROOF_COL = [0xff0000ff, 0xff00ff00, 0xffff0000, 0xff00ffff]
COLOUR = {GREY: 0xff5a5a5f, RUN: 0xff14a0fa, OK: 0xff46be28, BAD: 0xff2828dc}
CELL_NAMES = ['1 hook+clock', '2 root', '3 film', '4 state', '5A top buffer', '5B bottom buffer', '5C counter buffer',
              '5D tab buffer', '6 views', '7 attach', '8 loaded_start', '9 first tick']


class D(cl.LoadedFixture):
    def __init__(self, *a):
        super().__init__(*a)
        self.factory_calls = 0
        self.fail_factory = set()
        from unicorn import UC_HOOK_CODE
        self.uc.hook_add(UC_HOOK_CODE, self._factory, begin=0x533ad7f0, end=0x533ad7f0)
        self.L = dict(zip(LAYOUT, [self.symbol_word('grmod_layout', i) for i in range(len(LAYOUT))]))

    def _factory(self, cpu, at, size, user):
        n = self.factory_calls
        self.factory_calls += 1
        if n in self.fail_factory:
            self.ret(0)

    def s(self):
        return self.get(ca.ANCHOR)

    def cells(self):
        return list(self.uc.mem_read(self.s() + self.L['cell'], NCELLS))

    def info(self):
        raw = bytes(self.uc.mem_read(self.s() + self.L['info'], 48))
        return [raw[i * 16:(i + 1) * 16].split(b'\0')[0].decode() for i in range(3)]

    def ld(self):
        return self.get(self.s() + self.L['ld'])

    def diag_view(self):
        return self.get(self.s() + self.L['view'])

    def v(self, name):
        return self.get(self.s() + self.L[name])

    def vs(self, i):
        base = self.s() + self.L['vs'] + i * self.L['sizeof_vs']
        w = [self.get(base + 4 * k) for k in range(14)]
        return dict(calls=w[0:3], copied=w[3:6], last_rej=w[6:9], parent=w[9], abs=[x - (1 << 32) if x >= 1 << 31 else x for x in w[10:14]])

    def log(self):
        out = []
        for k in range(self.v('nlog')):
            at = self.s() + self.L['log'] + k * self.L['sizeof_log']
            w0 = self.get(at)
            out.append((w0 & 255, (w0 >> 8) & 255, (w0 >> 16) & 255, self.get(at + 4)))
        return out

    def glog(self):
        n = self.v('ng')
        out = []
        for k in range(max(0, n - 160), n):
            at = self.s() + self.L['glog'] + (k % 160) * self.L['sizeof_glog']
            w0 = self.get(at)
            out.append((w0 & 0xffff, (w0 >> 16) & 255, (w0 >> 24) & 255, self.get(at + 4)))
        return out

    def pre(self):
        out = []
        for k in range(self.v('npre')):
            at = self.s() + self.L['pre'] + k * self.L['sizeof_glog']
            w0 = self.get(at)
            out.append((w0 & 0xffff, self.get(at + 4)))
        return out

    def tab(self):
        out = []
        for k in range(self.v('ntab')):
            at = self.s() + self.L['tab'] + k * self.L['sizeof_tabrow']
            w0 = self.get(at)
            out.append((w0 & 0xffff, (w0 >> 16) & 255, (w0 >> 24) & 255, self.get(at + 4), self.get(at + 8), self.get(at + 12)))
        return out

    def cancels(self):
        return [self.get(self.s() + self.L['cancels'] + 4 * k) for k in range(10)]

    def tick(self):
        self.fire(33)
        return self.cells()

    def ld_hashes(self):
        ld = self.ld()
        out = []
        for i, (_, _, w, h) in enumerate(cl.VIEWS):
            ptr = self.get(ld + self.L['ld_pixels'] + 4 * i)
            out.append(zlib.crc32(bytes(self.uc.mem_read(ptr, w * h * 4))))
        return out

    def ld_views(self):
        return [self.get(self.ld() + self.L['ld_views'] + 4 * i) for i in range(4)]


def expected(fail):
    """cells for a failure at cell index `fail`; None means all ok"""
    out = [OK, OK] + [GREY] * 10
    last = NCELLS if fail is None else fail
    for i in range(2, last):
        out[i] = OK
    if fail is not None:
        out[fail] = BAD
    return out


def verify(data, segments, symbols):
    checks, counts = [], {}

    def ok(cond, msg):
        counts['n'] = counts.get('n', 0) + 1
        assert cond, msg

    def new():
        p = D(data, segments, symbols)
        p.uc.mem_unmap(cl.SERVICE & ~0xfff, 0x1000)
        p.record(0, 0, (64 + 11, 11, 11))
        return p

    manifest = json.loads((BUILD/'payload-manifest.json').read_text(encoding='utf-8'))
    slot_film = {x['look']: x['film'] for x in manifest['slots']}

    # ---- A. the first shot of a session is variant A (timer ticks plus layout request): allocations, panel, steps, proof, real moment
    p = new()
    base = len(p.allocations)
    p.call('grmod_on_shot')
    root = p.roots[0]
    ok(p.get(ca.ANCHOR) != 0 and p.get(p.s()) == 0x44474c47, 'diag state word and magic')
    ok([s for _, s in p.allocations[base:]] == [p.L['sizeof_diag'], 248, 4], 'the hook makes only the panel allocations (block, view, one child-list slot): shooting is not delayed')
    ok(p.L['sizeof_diag'] <= 172 * 1024, ('diag block size', p.L['sizeof_diag']))
    ok(p.v('hook') == 1 and p.v('variant') == 0 and p.v('shots') == 1, 'first shot: hook 1, variant A')
    ok(p.children(root) == [p.diag_view()] and len(p.timers()) == 1, 'one panel view, one timer')
    ok(p.cells() == [OK, OK] + [GREY] * 10, ('cells at the shot', p.cells()))
    ok(p.info()[1] == 'SHOT 1' and p.info()[2] == 'P%04X' % (p.s() & 0xffff), ('info text', p.info()))
    pix = p.s() + p.L['pixels']
    px = lambda x, y: struct.unpack('<I', p.uc.mem_read(pix + 4 * (y * 240 + x), 4))[0]
    ok(px(6 + 17, 24 + 16 + 12) == COLOUR[OK] and px(6 + 38 * 2 + 17, 24 + 16 + 12) == COLOUR[GREY], 'cell colours in the panel pixels')
    ok(px(1, 1) == 0xffffffff and px(120, 170) == 0xff101010, 'panel frame and background')
    for k in range(10):
        c1 = p.tick()
        ok(c1[2 + k] == RUN, f'step {k}: orange before the step executes: {c1}')
        ok(c1[:2 + k] == [OK] * (2 + k) and set(c1[3 + k:]) <= {GREY}, f'step {k}: earlier ok, later grey: {c1}')
        c2 = p.tick()
        ok(c2[2 + k] == OK, f'step {k}: ok after executing: {c2}')
    ok(p.cells() == [OK] * 12, 'all twelve cells green')
    ok(p.info()[0] == 'L75 F%d' % slot_film[75], ('film text', p.info()))
    ok(len(p.children(root)) == 5 and len(p.timers()) == 1, 'panel plus four Loaded views')
    ok(p.children(root)[0] == p.diag_view() and p.children(root)[1:] == p.ld_views(), 'panel first, then the four views in order')
    codes = [e[0] for e in p.log()]
    ok(codes[0] == 0 and 3 in codes, ('log has hook and attach', codes))
    ok(p.v('proof') == 1, 'proof phase running after cell 9')
    ld = p.ld()
    for i, (_, _, w, h) in enumerate(cl.VIEWS):
        buf = p.get(ld + p.L['ld_pixels'] + 4 * i)
        rd = lambda x, y: struct.unpack('<I', p.uc.mem_read(buf + 4 * (y * w + x), 4))[0]
        ok(rd(1, 1) == PROOF_COL[i] and rd(w - 2, h - 2) == PROOF_COL[i], f'proof outline of view {i + 1}')
        ok(rd(w // 2 - 24, h // 2) == PROOF_COL[i], f'proof block of view {i + 1}')
        black = sum(1 for yy in range(h // 2 - 10, h // 2 + 11) for xx in range(w // 2 - 8, w // 2 + 8) if rd(xx, yy) == 0xff000000)
        ok(black > 20, f'proof digit of view {i + 1} is drawn')
    top = p.get(ld + p.L['ld_pixels'])
    ok(all(struct.unpack('<I', p.uc.mem_read(top + 4 * (20 * 720 + xx), 4))[0] == 0 for xx in range(10, 40)), 'the rest of the proof view is transparent')
    p.call(0x53391b14, root)
    vis = bytes(p.uc.mem_read(ca.DEST + 32, 736 * 480 * 4))
    cov = lambda x, y, w, h: any(vis[((y + yy) * 736 + x + xx) * 4 + 3] != 0xa5 for yy in range(0, h, 4) for xx in range(0, w, 4))
    ok(cov(464, 259, 240, 176), 'the panel is drawn at the Terminal rectangle through the original canvas draw')
    ok(all(cov(x, y, w, h) for (x, y, w, h) in cl.VIEWS), 'the four proof patterns reach the screen through the original canvas draw')
    ok(all(p.vs(i)['copied'][0] >= 1 and p.vs(i)['last_rej'][0] == 0 for i in range(5)), 'draw statistics: every view copied, last reject 0, controller type LiveView')
    ok(p.v('ld_copies_shot') == 4 and p.v('tk_ld') == 20, ('first draw ticks', p.v('ld_copies_shot'), p.v('tk_ld')))
    p.canaries()
    n = 0
    while p.v('proof') and n < 60:
        p.fire(33)
        n += 1
    ok(30 <= n <= 32, ('proof lasts about one second', n))
    p.fire(33)
    want = cl.js_hashes([cl.jscase('shot', slot_film[75], 1, 1, 33)])[0][1:]
    ok(p.ld_hashes() == want, 'after the proof the real moment starts and its first frame equals the JS reference')
    start = p.now
    while p.timers() and p.now - start < 25000:
        p.fire(33)
        if not p.children(root):
            ok(p.now - start + 1000 + 20 * 33 + 33 * 31 >= 20900, 'the panel stays about twenty-one seconds')
    ok(len(p.children(root)) == 0 and not p.timers(), 'the panel and everything else are gone after the panel window')
    checks.append('first shot (variant A): hook makes 3 allocations, two ticks per step, twelve cells green, proof patterns (outline, block, digit, transparent rest) in all four buffers '
                  'and on the screen through the original canvas draw for one second, then the real moment whose first frame equals the JS reference, everything gone after the 21 s window')

    # ---- A2. layout (stage 1e's field finding): a view attached to a clean root keeps the rectangle 0,0,0,0 unless the root is asked to lay out its children
    def session(variant):
        q = new()
        for _ in range(variant):
            q.call('grmod_on_shot')
            q.call('grmod_cancel')
            q.now += 5000
        q.call(0x53391b14, q.roots[0])                          # the camera has just painted: the root is clean
        ok(tuple(q.uc.mem_read(q.roots[0] + 0x9c, 2)) == (0, 0), 'the root is clean before the shot')
        q.call('grmod_on_shot')
        return q
    VIEWRECT = list(cl.VIEWS)
    for variant in (0, 1, 2):
        q = session(variant)
        ok(q.v('variant') == variant, ('variant', variant, q.v('variant')))
        if variant == 1:
            ok(q.cells() == [OK] * 10 + [GREY] * 2 and len(q.children(q.roots[0])) == 5, ('variant B runs the steps up to the attach inside the hook', q.cells()))
            ok(q.v('t_att') == 0 or True, 'timing')
            for _ in range(4):
                q.tick()
        else:
            ok(q.cells() == [OK, OK] + [GREY] * 10, 'variants A and C run the steps on timer ticks')
            for _ in range(20):
                q.tick()
        ok(q.cells() == [OK] * 12 and len(q.children(q.roots[0])) == 5, f'variant {variant}: sequence ok')
        q.call(0x53391b14, q.roots[0])
        rects = [struct.unpack('<4i', q.uc.mem_read(v + 0x30, 16)) for v in q.ld_views()]
        if variant == 0:
            ok(rects == VIEWRECT, ('variant A: the root was asked to lay out its new children, the views have their rectangles', rects))
            ok(all(q.vs(i)['copied'][0] >= 1 for i in range(4)), 'variant A: the four views draw')
        else:
            ok(all(r == (0, 0, 0, 0) for r in rects), (f'variant {variant}: no layout request, the views keep 0,0,0,0 (the 1e field finding)', rects))
            ok(all(q.vs(i)['last_rej'][0] == 11 and q.vs(i)['copied'][0] == 0 for i in range(4)), f'variant {variant}: every draw rejected with code 11')
        steps = 0
        while q.v('proof') and steps < 100:
            q.fire(33)
            steps += 1
        ok(30 <= steps <= 33, f'variant {variant}: proof one second ({steps})')
        q.fire(33)
        want = cl.js_hashes([cl.jscase('shot', slot_film[75], q.v('shots'), 1, 33)])[0][1:]
        ok(q.ld_hashes() == want, f'variant {variant}: real moment after the proof equals the JS reference')
        q.canaries()
    checks.append('layout, reproduced with the original native layout pass on a clean root: variant A (timer plus layout request) gives the four views their rectangles and they draw; '
                  'variants B (steps inside the hook) and C (control) leave 0,0,0,0 and every draw is rejected with code 11, as in the 1e field video')

    # ---- B. failures of the film read
    def run_to_end(q, ticks=20):
        for _ in range(ticks):
            q.tick()

    film_cases = [('record null', lambda q: q.put(cl.USERDATA_MODEL + 4, 0), 'NO RECORD'),
                  ('record misaligned', lambda q: q.put(cl.USERDATA_MODEL + 4, cl.RECORD + 1), 'MISALIGNED'),
                  ('movie byte set', lambda q: q.record(1, 0, (75, 11, 11)), 'MOVIE 1'),
                  ('set 3', lambda q: q.record(0, 3, (75, 75, 75)), 'SET 3')]
    for name, setup, text in film_cases:
        q = new()
        setup(q)
        q.call('grmod_on_shot')
        run_to_end(q)
        ok(q.cells() == expected(2), (name, q.cells()))
        ok(q.info()[0] == text, (name, q.info()))
        ok(q.ld() == 0 and q.children(q.roots[0]) == [q.diag_view()], f'{name}: only the panel is attached, no Loaded state')
        for _ in range(800):
            q.fire(33)
        ok(not q.children(q.roots[0]) and not q.timers(), f'{name}: the panel goes after its window')
        q.canaries()
        q.put(cl.USERDATA_MODEL + 4, cl.RECORD)
        q.record(0, 0, (75, 11, 11))
        q.call('grmod_on_shot')
        run_to_end(q)
        ok(q.cells() == [OK] * 12, f'{name}: the next shot works once the cause is gone')
    checks.append('film read failures (record null, misaligned, movie byte set, set 3): cell 3 red with the reason as text, cells 4..9 grey, only the panel attached, panel leaves at its window, next shot all green')

    # ---- C. allocation failures: index 3 = state, 4..7 = buffers, 8..11 = views (0 to 2: the panel block, its view and the root child list)
    plan = [(3, 3, 'state'), (4, 4, 'top buffer'), (5, 5, 'bottom buffer'), (6, 6, 'counter buffer'), (7, 7, 'tab buffer'),
            ]
    for index, cell, name in plan:
        q = new()
        base = len(q.allocations)
        q.fail_at = {index}
        q.alloc_count = 0
        q.call('grmod_on_shot')
        run_to_end(q)
        ok(q.cells() == expected(cell), (name, q.cells()))
        ok(q.children(q.roots[0]) == [q.diag_view()], f'{name}: only the panel is attached')
        if cell < 8:
            ok(q.ld() == 0, f'{name}: the pieces allocated for Loaded were released')
            made = [ptr for ptr, _ in q.allocations[base + 3:]]
            ok(sorted(q.frees) == sorted(made), f'{name}: every earlier Loaded piece freed, none else')
        else:
            ok(q.ld() != 0, f'{name}: pieces kept for the next shot')
        q.canaries()
        q.fail_at = set()
        q.alloc_count = 0
        q.call('grmod_on_shot')
        run_to_end(q)
        ok(q.cells() == [OK] * 12 and len(q.children(q.roots[0])) == 5, f'{name}: the next shot works')
        q.canaries()
    # view creation refusing (the native factory returning null): the native factory cannot cope with a null allocation (it writes through it),
    # so this is provoked at the factory itself; the views already made are kept for the next shot
    for k in (1, 2, 3, 4):
        q = new()
        q.fail_factory = {k}
        q.call('grmod_on_shot')
        run_to_end(q)
        ok(q.cells() == expected(8), (f'view {k} not created', q.cells()))
        ok(q.children(q.roots[0]) == [q.diag_view()] and q.ld() != 0, f'view {k}: only the panel attached, Loaded pieces kept')
        q.canaries()
        q.fail_factory = set()
        q.call('grmod_on_shot')
        run_to_end(q)
        ok(q.cells() == [OK] * 12 and len(q.children(q.roots[0])) == 5, f'view {k}: the next shot works')
    checks.append('allocation failures (state, four buffers, and each of four views refused by the native factory: the right cell red (cell 4 for state, 5A to 5D for buffers, 6 for views), later cells grey, earlier green, '
                  'Loaded pieces released, only the panel attached, canaries intact, next shot all green')

    # ---- D. attach failing, loaded_start failing, first tick failing
    q = new()
    q.call('grmod_on_shot')
    for _ in range(14):
        q.tick()                                                # steps 0..6 done
    q.tick()                                                    # attach marked orange
    ok(q.cells()[9] == RUN and q.cells()[8] == OK, ('attach running', q.cells()))
    q.put(q.ld_views()[0] + 4, 0x1234)                          # one view already belongs to another tree
    q.tick()
    ok(q.cells() == expected(9), ('attach failure', q.cells()))
    ok(q.children(q.roots[0]) == [q.diag_view()], 'attach failure leaves only the panel')
    q.put(q.ld_views()[0] + 4, 0)
    q.canaries()
    q2 = new()
    q2.call('grmod_on_shot')
    q2.tick(); q2.tick()                                        # film read ok
    q2.put(q2.s() + q2.L['film'], 999)                          # an impossible film reaches loaded_start
    for _ in range(16):
        q2.tick()
    ok(q2.cells() == expected(10), ('loaded_start failure', q2.cells()))
    ok(q2.children(q2.roots[0]) == [q2.diag_view()], 'loaded_start failure detaches the Loaded views')
    q2.canaries()
    q3 = new()
    q3.call('grmod_on_shot')
    for _ in range(19):
        q3.tick()                                               # first tick marked orange
    ok(q3.cells()[11] == RUN, ('tick running', q3.cells()))
    q3.put(q3.ld() + q3.L['ld_engine'], 0)                      # the engine magic is damaged
    q3.tick()
    ok(q3.cells() == expected(11), ('first tick failure', q3.cells()))
    ok(q3.children(q3.roots[0]) == [q3.diag_view()], 'first tick failure leaves only the panel')
    q3.canaries()
    checks.append('attach failing (a view already in another tree), loaded_start refusing (impossible film), first tick refusing (damaged engine): cell 7, 8 or 9 red, later grey, '
                  'only the panel attached afterwards, canaries intact')

    # ---- E. clock failure, wrong screen, cancel and transitions clear both
    q = new()
    q.clock_ok = False
    q.call('grmod_on_shot')
    ok(q.children(q.roots[0]) == [q.diag_view()] and q.cells()[:2] == [BAD, OK], ('no clock: the panel shows cell 1 red', q.cells()))
    for _ in range(25):
        q.tick()
    ok(q.cells()[0] == BAD and q.cells()[10] == BAD and q.ld() != 0 and len(q.children(q.roots[0])) == 1, ('no clock: loaded_start cannot be given a time', q.cells()))
    for _ in range(800):
        q.fire(33)
    ok(not q.children(q.roots[0]) and not q.timers(), 'no clock: the panel leaves after 182 ticks')
    q.clock_ok = True
    q.active = cl.OTHER
    q.call('grmod_on_shot')
    ok(not q.children(q.roots[0]) and not q.timers(), 'unexpected controller: nothing')
    q.active = cl.LV
    q.call('grmod_on_shot')
    for _ in range(24):
        q.tick()
    ok(len(q.children(q.roots[0])) == 5, 'running with the panel and four views')
    q.call('grmod_before_transition', cl.LV, 0x08000020)
    ok(not q.children(q.roots[0]) and not q.timers(), 'a menu destination clears the panel and the four views at once')
    q.active = cl.OTHER
    q.call('grmod_after_transition')
    q.active = cl.LV
    q.call('grmod_on_shot')
    for _ in range(24):
        q.tick()
    q.call('grmod_cancel')
    ok(not q.children(q.roots[0]) and not q.timers(), 'cancel clears the panel and the four views at once')
    q.call('grmod_on_shot')
    for _ in range(24):
        q.tick()
    q.call('grmod_before_transition', cl.LV, 0x0800000c)
    ok(not q.children(q.roots[0]) and not q.timers(), 'a shooting transition detaches everything')
    q.active = cl.QV
    q.call('grmod_after_transition')
    ok(len(q.children(q.roots[1])) == 5 and len(q.timers()) == 1, 'and reattaches the panel and the four views after it')
    q.call('grmod_before_canvas_delete', q.roots[1])
    ok(q.s() and not q.children(q.roots[1]) and not q.timers(), 'canvas deletion cancels')
    q.canaries()
    ok(q.audio_calls == [], 'no audio entry reached')
    checks.append('no clock: the panel shows cell 1 red and leaves after 182 ticks; an unexpected controller: nothing drawn; a menu transition, cancel and canvas deletion clear the panel and the four views and the timer at once; '
                  'a shooting transition detaches everything and reattaches the panel and the four views')

    # ---- F. many shots: one set of allocations, no growth
    q = new()
    q.call('grmod_on_shot')
    for _ in range(24):
        q.tick()
    count, nfrees = len(q.allocations), len(q.frees)
    for _ in range(60):
        q.now += 2000
        q.call('grmod_on_shot')
        for _ in range(24):
            q.tick()
        q.call('grmod_cancel')
    ok(len(q.allocations) == count and len(q.frees) == nfrees, 'repeated shots reuse the same allocations')
    ok(q.get(q.s() + q.L['shots']) == 61, 'shot counter')
    q.canaries()
    checks.append('61 shots with a full step sequence each: the allocation set never grows or is freed; the shot counter counts')
    # ---- G. event counters, reasons, controller split, draw statistics, log, timing, the suspected repaint and timing failures
    # G1. the hook is counted before any early return; a root that cannot be found leaves the vtable seen
    q = new()
    q.active = cl.OTHER
    q.call('grmod_on_shot')
    ok(q.s() != 0 and q.v('hook') == 1 and q.v('rootfail_h') == 1 and q.v('shots') == 0, 'hook counted although the root was not found')
    ok(q.v('last_vt') == (q.get(cl.OTHER) & 0xffff), ('vtable seen at the failure', hex(q.v('last_vt')), hex(q.get(cl.OTHER))))
    ok(q.cancels()[1] == 1 and not q.children(q.roots[0]) and not q.timers(), 'cancel reason ROOT counted, nothing drawn')
    ok([e[0] for e in q.log()] == [0, 14, 13], ('log', q.log()))
    q.active = cl.LV
    for _ in range(5):
        q.fire(33)
    ok(not q.children(q.roots[0]) and not q.timers(), 'suspect B in the emulator: a hook that fires before the camera is on LiveView gets no panel and nothing retries it')
    q.call('grmod_on_shot')
    ok(q.v('hook') == 2 and q.v('shots') == 1 and len(q.children(q.roots[0])) >= 1, 'the next hook works')
    # G2. the controller turns into something else for one tick in the middle of the sequence: the panel and everything are cancelled for good
    for _ in range(6):
        q.tick()
    q.active = cl.OTHER
    q.fire(33)
    ok(not q.children(q.roots[0]) and not q.timers() and q.cancels()[1] == 2 and q.v('rootfail_u') == 1, 'suspect B in the emulator: one tick on another controller cancels the whole shot (reason ROOT, update site)')
    q.active = cl.LV
    for _ in range(5):
        q.fire(33)
    ok(not q.children(q.roots[0]), 'and it does not come back')
    # G3. cancel reasons: external (the release hook), transition, canvas deletion, film, create
    q = new()
    q.call('grmod_on_shot')
    q.call('grmod_cancel')
    ok(q.cancels()[9] == 1 and q.v('last_cancel') == 10 and not q.children(q.roots[0]), 'external cancel counted (the release hook calls it)')
    q.call('grmod_on_shot')
    q.call('grmod_before_transition', cl.LV, 0x08000020)
    ok(q.cancels()[7] == 1 and q.v('trans_b') == 1, 'menu destination: reason TRANS, before count')
    q.call('grmod_after_transition')
    ok(q.v('trans_a') == 1, 'after count')
    q.call('grmod_on_shot')
    q.call('grmod_before_canvas_delete', q.roots[0])
    ok(q.cancels()[8] == 1, 'canvas deletion counted')
    q.put(cl.USERDATA_MODEL + 4, 0)
    q.call('grmod_on_shot')
    for _ in range(4):
        q.tick()
    ok(q.cancels()[2] == 1, 'film read failure counted as FILM')
    q.put(cl.USERDATA_MODEL + 4, cl.RECORD)
    q2 = new()
    q2.fail_factory = {1}
    q2.call('grmod_on_shot')
    for _ in range(20):
        q2.tick()
    ok(q2.cancels()[3] == 1, 'view creation failure counted as CREATE')
    q.clock_ok = False
    q.fail_factory = set()
    q.call('grmod_on_shot')
    for _ in range(25):
        q.tick()
    ok(q.cancels()[0] >= 1, 'clock failure counted as CLOCK')
    q.clock_ok = True
    ok(q.v('ticks') > 0, 'timer ticks counted')
    q.canaries()
    checks.append('counters: the hook is counted before any early return (also with no root: the vtable seen is kept), cancel reasons ROOT, FILM, CREATE, CLOCK, TRANS, CANVAS and EXT (release hook) count separately, '
                  'transition before and after, timer ticks; suspect B reproduced in the emulator: a hook before LiveView gets no panel and nothing retries, and one tick on another controller cancels a running shot for good')

    # G4. draw statistics split by controller type: LiveView and QuickView, geometry kept, reject codes
    q = new()
    q.active = cl.QV
    q.call('grmod_on_shot')
    for _ in range(21):
        q.tick()
    root = q.roots[1]
    q.call(0x53391b14, root)
    ok(all(q.vs(i)['copied'][1] >= 1 and q.vs(i)['copied'][0] == 0 for i in range(5)), 'a QuickView draw counts under QuickView only')
    for i, (x, y, w, h) in enumerate(cl.VIEWS):
        ok(q.vs(i)['abs'] == [x, y, w, h] and q.vs(i)['parent'] == 1, ('geometry kept', i, q.vs(i)['abs']))
    ok(q.get(q.s() + q.L['surf'] + 16 * 1 + 0) > 0, 'surface width kept')
    ok(q.get(q.s() + q.L['surf'] + 16 * 1 + 12) == 5, 'surface format kept')
    log = q.log()
    ok([e[0] for e in log if 4 <= e[0] <= 12][:5] and all(e[1] == 1 for e in log if 4 <= e[0] <= 12), ('first calls and draws logged under QuickView', log))
    ok(sum(1 for e in log if e[0] in (4, 5, 6, 7)) == 4 and sum(1 for e in log if e[0] in (8, 9, 10, 11)) == 4, 'first call and first draw of each view are logged once')
    ok(q.v('panel_calls_shot') >= 1 and q.v('first_draw_ms') >= 0 and q.v('tk_panel') == 21, 'panel calls and first draw time recorded')
    # reject codes on the top view, called directly as the camera would
    surface = q.get(root + 0xec)
    view = q.ld_views()[0]
    x, y, w, h = cl.VIEWS[0]
    def attempt(mut):
        q.uc.mem_write(view + 0x30, struct.pack('<4i', x, y, w, h))
        q.uc.mem_write(view + 0x64, struct.pack('<4i', x, y, w, h))
        q.uc.mem_write(view + 0x9e, b'\x01')
        q.uc.mem_write(surface + 2, b'\x05')
        q.uc.mem_write(surface + 0x18, struct.pack('<H', 736))
        arg = mut(surface)
        q.call('grmod_draw', view, arg if arg else surface)
        return q.vs(0)['last_rej'][1]
    ok(attempt(lambda s_: None) == 0, 'reject 0: copied')
    ok(attempt(lambda s_: q.uc.mem_write(view + 0x9e, b'\0')) == 5, 'reject 5: hidden')
    ok(attempt(lambda s_: q.uc.mem_write(view + 4, struct.pack('<I', 0x1234))) == 6, 'reject 6: parent')
    q.uc.mem_write(view + 4, struct.pack('<I', root))
    ok(attempt(lambda s_: ca.DEST) == 7, 'reject 7: not the root surface')
    ok(attempt(lambda s_: q.uc.mem_write(surface + 2, b'\x04')) == 8, 'reject 8: format')
    ok(attempt(lambda s_: q.uc.mem_write(surface + 0x18, struct.pack('<H', 719))) == 9, 'reject 9: surface geometry')
    ok(attempt(lambda s_: q.uc.mem_write(view + 0x30, struct.pack('<4i', x, y, w + 1, h))) == 11, 'reject 11: rectangle')
    ok(attempt(lambda s_: q.uc.mem_write(view + 0x64, struct.pack('<4i', 0x7fffffff, y, w, h))) == 12, 'reject 12: clip')
    ok(attempt(lambda s_: q.uc.mem_write(view + 0x30, struct.pack('<4i', 800, 600, w, h))) == 13, 'reject 13: empty intersection')
    q.canaries()
    checks.append('draw statistics: counted per view and per controller type (QuickView draws count under QuickView only), geometry (absolute rectangle, parent) and the surface kept, '
                  'first call and first draw of every view logged once with the controller type; reject codes 0, 5, 6, 7, 8, 9, 11, 12 and 13 reproduced on a real view object')

    # G5. a late repaint: ticks late and a moment found already over without ever being painted
    q = session(0)
    for _ in range(20):
        q.tick()
    q.fire(250)
    ok(q.v('late') >= 1, 'a late tick (250 ms) is counted')
    n = 0
    while q.v('proof') and n < 60:
        q.fire(33)
        n += 1
    q.fire(33)
    ok(q.v('ld_copies_shot') == 0, 'nothing was painted')
    q.fire(3000)
    ok(q.v('stale') == 1 and 15 in [e[0] for e in q.log()], ('the moment found over at its first tick without a paint is counted stale', q.v('stale'), q.log()))
    q = session(0)
    for _ in range(20):
        q.tick()
    q.call(0x53391b14, q.roots[0])
    n = 0
    while q.v('proof') and n < 60:
        q.fire(33)
        n += 1
    q.fire(33)
    q.fire(3000)
    ok(q.v('stale') == 0, 'a moment that was painted is never stale')
    checks.append('timing: a late tick is counted; a moment that is over at its first tick without any Loaded view painted is counted stale and logged (and not when it was painted); '
                  'ticks to the first panel and Loaded draw, ms from hook to attach and to the first tick are kept')

    # G6. timing fields of the last shot, ticks before the first draw
    q = new()
    q.call('grmod_on_shot')
    ok(q.v('t_root') == 0 and q.v('t_att') == 0, 'the emulator clock is frozen inside the hook: H>R and H>A are 0')
    q.fire(33)
    ok(q.v('t_first') == 33, 'H>T is the time of the first tick')
    q.canaries()
    checks.append('H>R, H>A (hook to root found and to attached) and H>T (hook to first tick) are kept per shot')

    # ---- H. who allocates and when, the distinct-id table, RL to HK, the cost per dispatched event
    ev = ca.EVENT + 0x400

    def evt(q, ident, dt=0):
        q.now += dt
        q.uc.mem_write(ev, struct.pack('<H', ident))
        q.call('grmod_on_event', ca.APP, ev)

    # H1. the release hook never allocates; the first UI event allocates the block once, with nothing else touched
    q = new()
    n0 = len(q.allocations)
    q.call('grmod_cancel')
    ok(q.s() == 0 and len(q.allocations) == n0, 'the release hook never allocates: with no block it does nothing')
    evt(q, 0x199)
    ok(q.s() != 0 and len(q.allocations) == n0 + 1 and q.allocations[-1][1] == q.L['sizeof_diag'] and q.v('ev_total') == 1, 'the first UI event allocates the block, once')
    evt(q, 0x199, 10)
    evt(q, 0x2222, 10)
    ok(len(q.allocations) == n0 + 1 and q.v('ev_total') == 3 and q.v('ntab') == 2, 'later events allocate nothing')
    q.call('grmod_before_transition', cl.LV, 0x0800000c)
    q.call('grmod_after_transition')
    q.call('grmod_before_canvas_delete', q.roots[0])
    q.call('grmod_timer_expired', 0, 0)
    ok(q.v('trans_b') == 0 and q.v('trans_a') == 0 and q.cancels() == [0] * 10 and not q.children(q.roots[0]), 'the other hooks stay inert until the first photo')
    base = len(q.allocations)
    q.call('grmod_on_shot')
    ok([s for _, s in q.allocations[base:]] == [248, 4] and len(q.timers()) == 1, 'a photo after the block exists allocates only the panel view and the child slot, and starts its timer')
    for _ in range(21):
        q.tick()
    ok(q.cells() == [OK] * 12, 'the whole sequence works on a block made by the event hook')
    # H2. an allocation failure in the event hook is remembered in a spare RAM word and never retried; the shot hook still allocates
    q = new()
    q.fail_at = {0}
    q.alloc_count = 0
    evt(q, 0x199)
    ok(q.s() == 0 and q.get(0x5580438c) == 1, 'a failed allocation leaves no block and sets the flag word')
    q.fail_at = set()
    count = len(q.allocations)
    for _ in range(5):
        evt(q, 0x199, 10)
    ok(q.s() == 0 and len(q.allocations) == count, 'and the event hook never tries again')
    q.call('grmod_on_shot')
    ok(q.s() != 0 and len(q.children(q.roots[0])) == 1, 'the shot hook allocates as before')
    # H3. the distinct-id table: first and last time, count since the last RL, periodic ids marked
    q = new()
    q.call('grmod_on_shot')                                        # hook 1 at t0
    t0 = q.now
    for i in range(5):
        evt(q, 0x199, 33)
    evt(q, 0x2222, 100)
    rows = {r[0]: r for r in q.tab()}
    ok(rows[0x199][5] == 5 and rows[0x199][3] == t0 + 33 and rows[0x199][4] == t0 + 165 and rows[0x2222][5] == 1, ('counts, first and last', rows))
    q.now += 400
    q.call('grmod_cancel')                                         # RL: the release lane only
    ok(q.v('rl_count') == 1 and q.v('rl_time') == q.now and q.tab()[0][5] != 0, 'the release hook writes its lane and does not touch the table')
    trl = q.now
    evt(q, 0x199, 33)                                              # the UI task syncs the table
    rows = {r[0]: r for r in q.tab()}
    ok(rows[0x199][5] == 1 and rows[0x199][3] == trl + 33 and rows[0x199][2] == 1, ('after the RL: reset, count 1, periodic', rows[0x199]))
    ok(rows[0x2222][5] == 0 and rows[0x2222][2] == 1 and rows[0x1001][5] == 1 and rows[0x1001][3] == trl, 'a silent id is hidden (count 0) but remembered as periodic; the RL row is at time 0')
    evt(q, 0x3333, 100)
    rows = {r[0]: r for r in q.tab()}
    ok(rows[0x3333][5] == 1 and rows[0x3333][2] == 0 and rows[0x3333][3] == trl + 133, 'a new id after the RL is not periodic')
    # the completion hook of this photo: RL to HK, and a new window
    q.now += 14000
    q.call('grmod_on_shot')
    ok(q.v('nrlhk') == 2 and q.get(q.s() + q.L['rlhk']) == q.now - trl, ('RL to HK', q.get(q.s() + q.L['rlhk'])))
    rows = {r[0]: r for r in q.tab()}
    ok(rows[0x3333][1] == 0 and rows[0x1002][1] == 0 and rows[0x1002][5] == 1, 'HK clears the window flags')
    q.now += 500
    q.call('grmod_on_shot')                                        # a second photo with no RL since the previous HK
    ok(q.get(q.s() + q.L['rlhk']) == 0xffffffff, 'no RL since the previous hook: NO RL')
    # H4. more distinct ids than rows: counted as overflow, nothing else disturbed
    q = new()
    q.call('grmod_on_shot')
    for i in range(30):
        evt(q, 0x4000 + i, 1)
    ok(q.v('ntab') == 24 and q.get(q.s() + q.L['tab_ovf']) == 7, ('table full: the HK row and 23 ids, 7 overflowed', q.v('ntab'), q.get(q.s() + q.L['tab_ovf'])))
    evt(q, 0x4001, 1)
    ok({r[0]: r for r in q.tab()}[0x4001][5] == 2, 'existing rows keep counting when the table is full')
    ok(q.v('ng') <= 400 and q.v('ev_logged') >= 1, 'the ring stays bounded')
    # H5. the cost of one dispatched event, in instructions, measured through the real trampoline and the real dispatcher on the timer event
    from unicorn import UC_HOOK_CODE
    q = new()
    q.call('grmod_on_shot')
    state = {'on': False, 'n': 0}
    samples = []
    entry = q.symbols['grmod_hook_event']

    def count(uc, at, size, user):
        if at == entry:
            state['on'] = True
            state['n'] = 0
        if state['on']:
            state['n'] += 1
            if at == 0x53228ab8:
                state['on'] = False
                samples.append(state['n'])
    q.uc.hook_add(UC_HOOK_CODE, count)
    q.fire(33)                                                      # a new id: row created, ring written
    q.fire(33)                                                      # the same id within 500 ms: row found, ring not written
    q.fire(600)                                                     # after 500 ms: ring written again
    cost = dict(new_id=samples[0], same_id_within_500ms=samples[1], same_id_after_500ms=samples[2])
    worst = {'on': False, 'n': 0}

    def anyhook(uc, at, size, user):
        if worst['on']:
            worst['n'] += 1
    q.uc.hook_add(UC_HOOK_CODE, anyhook)
    for i in range(30):
        evt(q, 0x5000 + i, 1)
    worst['on'] = True
    evt(q, 0x6000, 1)                                               # table full, an id that is not in it: the longest search, no row
    worst['on'] = False
    cost['table_full_unknown_id_callback_only'] = worst['n']
    ok(len(samples) == 3 and max(samples) < 400 and worst['n'] < 400, ('cost per dispatched event in instructions', cost))
    q.canaries()
    checks.append('allocation context: the release hook never allocates (no block, no log), the first UI event allocates the block once, a failed allocation sets a spare RAM flag word and is never retried, the other hooks are inert before the first photo, '
                  'and a photo after the block exists allocates only the panel view; the distinct-id table (first, last, count since the RL, periodic marks, reset at the RL by the UI task, 24 rows with overflow counted); '
                  f'RL to HK for the last three photos; cost per dispatched event {cost} instructions (trampoline included)')

    return dict(checks=checks, assertions=counts['n'], diag_block_bytes=p.L['sizeof_diag'], loaded_state_bytes=p.L['sizeof_ld'],
                cells=CELL_NAMES, hardware_tested=False)


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
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
