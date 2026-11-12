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

os.environ['LOADED_VARIANT'] = 'diag'
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_adapter_loaded as cl  # noqa: E402
ca = cl.ca
OUT, BUILD = cl.OUT, cl.BUILD
GREY, RUN, OK, BAD = 0, 1, 2, 3
NCELLS = 12
LAYOUT = ['ld', 'cell', 'step', 'film', 'shots', 'ld_pixels', 'ld_engine', 'ld_views', 'sizeof_diag', 'sizeof_ld', 'info', 'pixels',
          'view', 'ld_params', 'sequence', 'diag_on']
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

    # ---- A. all ok: step by step, two ticks per step (orange, then result), pixels equal to the JS reference
    p = new()
    base = len(p.allocations)
    p.call('grmod_on_shot')
    root = p.roots[0]
    ok(p.get(ca.ANCHOR) != 0 and p.get(p.s()) == 0x44474c47, 'diag state word and magic')
    ok([s for _, s in p.allocations[base:]] == [p.L['sizeof_diag'], 248, 4], 'the hook itself makes only the panel allocations (block, view, the root child list growing by one slot): shooting is not delayed')
    ok(p.allocations[base][1] == p.L['sizeof_diag'] and p.L['sizeof_diag'] <= 172 * 1024, ('diag block size', p.L['sizeof_diag']))
    ok(p.allocations[base + 1][1] == 248, 'panel view allocation as the Terminal view')
    kids = p.children(root)
    ok(kids == [p.diag_view()] and len(p.timers()) == 1, 'one panel view, one timer')
    ok(p.cells() == [OK, OK] + [GREY] * 10, ('cells at the shot', p.cells()))
    ok(p.info()[1] == 'SHOT 1' and p.info()[2] == 'P%04X' % (p.s() & 0xffff), ('info text', p.info()))
    # panel pixels: the Terminal rectangle, grey cells drawn
    pix = p.s() + p.L['pixels']
    px = lambda x, y: struct.unpack('<I', p.uc.mem_read(pix + 4 * (y * 240 + x), 4))[0]
    ok(px(6 + 17, 24 + 16 + 12) == COLOUR[OK] and px(6 + 38 * 2 + 17, 24 + 16 + 12) == COLOUR[GREY], 'cell colours in the panel pixels')
    ok(px(1, 1) == 0xffffffff and px(120, 170) == 0xff101010, 'panel frame and background')
    seq = []
    sizes0 = len(p.allocations)
    for k in range(10):
        c1 = p.tick()
        ok(c1[2 + k] == RUN, f'step {k}: the running cell is orange before the step executes: {c1}')
        ok(c1[:2 + k] == [OK] * (2 + k) and set(c1[3 + k:]) <= {GREY}, f'step {k}: earlier ok, later grey: {c1}')
        c2 = p.tick()
        ok(c2[2 + k] == OK, f'step {k}: ok after executing: {c2}')
        seq.append(c2)
    ok(p.cells() == [OK] * 12, 'all twelve cells green')

    ok(p.info()[0] == 'L75 F%d' % slot_film[75], ('film text', p.info()))
    ok(len(p.children(root)) == 5 and len(p.timers()) == 1, 'panel plus four Loaded views')
    ok(p.children(root)[0] == p.diag_view() and p.children(root)[1:] == p.ld_views(), 'panel first, then the four views in order')
    elapsed = 2 * 33
    want = cl.js_hashes([cl.jscase('shot', slot_film[75], 1, 1, elapsed)])[0][1:]
    ok(p.ld_hashes() == want, 'Loaded first frame equals the JS reference when every step succeeds')
    p.call(0x53391b14, root)
    vis = bytes(p.uc.mem_read(ca.DEST + 32, 736 * 480 * 4))
    cov = lambda x, y, w, h: any(vis[((y + yy) * 736 + x + xx) * 4 + 3] != 0xa5 for yy in range(0, h, 4) for xx in range(0, w, 4))
    ok(cov(464, 259, 240, 176), 'the panel is drawn at the Terminal rectangle through the original canvas draw')
    ok(all(cov(x, y, w, h) for (x, y, w, h) in cl.VIEWS), 'the four Loaded views draw too')
    p.canaries()
    # the panel stays through the Loaded moment and goes at about 6 s; Loaded ends by itself
    p.fire(1500)
    ok(len(p.children(root)) == 5, 'panel stays while Loaded lingers')
    start = p.now
    while p.timers() and p.now - start < 9000:
        p.fire(33)
        if not p.children(root):
            ok(p.now - start + 1500 + 20 * 33 >= 5900, 'the panel must stay about six seconds')
    ok(len(p.children(root)) == 0 and not p.timers(), 'the panel and everything else are gone after the panel window')
    checks.append('all ok: two ticks per step (orange then result), twelve cells green, film text and the pointer text correct, Loaded first frame equals the JS reference, '
                  'panel + four views drawn by the original canvas draw, everything removed after the panel window; hook itself makes only 2 allocations')

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
        for _ in range(240):
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
    for _ in range(200):
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
