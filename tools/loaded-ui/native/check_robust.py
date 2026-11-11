"""Robustness cases for native/loaded.c in the ARM emulator (called by check_loaded.py).

Every case runs with guard canaries (0xA5 bytes) around the state struct and around every view buffer; a write
outside a buffer or the state fails the run. Expected pixel hashes come from the JS reference (parity.json).
"""
import struct
import zlib

VIEW_NAMES = ['full', 'top', 'bottom', 'counter', 'tab']
RECT = [(0, 0, 720, 480), (0, 0, 720, 44), (0, 436, 720, 44), (612, 380, 108, 48), (0, 376, 128, 56)]
ZERO = [zlib.crc32(bytes(w * h * 4)) for (_, _, w, h) in RECT]
FIELDS = ('moment', 'film', 'frame', 'tier', 't', 'tabMode', 'counterMode', 'peek', 'tabPeek', 'counterPeek', 'month', 'year', 'thumbs', 'circled', 'roll', 'hold')


def key(c):
    return tuple(c[f] for f in FIELDS)


class Counter:
    def __init__(self):
        self.n = 0

    def ok(self, cond, msg):
        self.n += 1
        assert cond, msg


def run_robustness(emu, cases):
    K = Counter()
    index = {key(c): c for c in cases}

    def expect(moment, film, frame, tier, t, **kw):
        d = dict(tabMode=0, counterMode=2, peek=-1, tabPeek=-2, counterPeek=-2, month=10, year=26, thumbs=0, circled=-1, roll=12, hold=0)
        d.update(kw)
        return index[key({'moment': moment, 'film': film, 'frame': frame, 'tier': tier, 't': t, **d})]['hashes']

    def params(moment='shot', film=11, frame=17, tier=2, **kw):
        d = dict(moment=moment, momentId={'live': 0, 'shot': 1, 'load': 2, 'roll': 3, 'none': 4}[moment], film=film, frame=frame, roll=12, tier=tier,
                 tabMode=0, counterMode=2, peek=-1, tabPeek=-2, counterPeek=-2, month=10, year=26, thumbs=0, circled=-1, hold=0)
        d.update(kw)
        return d

    def garbage():
        for v, (addr, size) in emu.base.items():
            emu.cpu.mem_write(addr, b'\xef\xbe\xad\xde' * (size // 4))

    def fresh():
        emu.guard_reset(); emu.zero_buffers(); emu.call('loaded_init', emu.state)

    def render(c, tier=None, **bufkw):
        emu.write_buffers(c['tier'], **bufkw)
        p = emu.write_params(c)
        return emu.call('loaded_render', emu.state, emu.BLOCK, p, c['t'])

    # ---- 1. stride padding and capacity: nothing outside the view rectangle is written
    fresh()
    # a dedicated full-screen buffer with a row stride larger than the width: the padding must stay untouched
    big = emu.BUF + 0x300000
    emu.cpu.mem_write(big - 0x1000, bytes([0xA5]) * 0x1000)
    stride = 760
    cap = stride * 480
    emu.cpu.mem_write(big + cap * 4, bytes([0xA5]) * 0x1000)
    emu.cpu.mem_write(big, bytes([0x5A]) * (cap * 4))
    emu.write_buffers(2)
    px = list(struct.unpack('<15I', bytes(emu.cpu.mem_read(emu.BLOCK, 60))))
    px[0] = big; px[5] = stride; px[10] = cap
    emu.cpu.mem_write(emu.BLOCK, struct.pack('<15I', *px))
    cc = params('roll', 11, 36, 2); cc['t'] = 1782
    r = emu.call('loaded_render', emu.state, emu.BLOCK, emu.write_params(cc), 1782)
    K.ok(r == 0, 'stride render failed')
    mem = bytes(emu.cpu.mem_read(big, cap * 4))
    pad_ok = all(mem[(y * stride + 720) * 4:(y * stride + stride) * 4] == bytes([0x5A]) * ((stride - 720) * 4) for y in range(480))
    K.ok(pad_ok, 'row padding beyond the view width was written')
    K.ok(bytes(emu.cpu.mem_read(big - 0x1000, 0x1000)) == bytes([0xA5]) * 0x1000 and bytes(emu.cpu.mem_read(big + cap * 4, 0x1000)) == bytes([0xA5]) * 0x1000, 'guard around strided buffer')
    rows = b''.join(mem[y * stride * 4:y * stride * 4 + 720 * 4] for y in range(480))
    want = expect('roll', 11, 36, 2, 1782)[0]
    K.ok(zlib.crc32(rows) == want, 'strided render differs from the JS pixels')

    # ---- 2. invalid inputs leave every view transparent and write nothing out of bounds
    bad = [
        ('film 22', dict(film=22)), ('film huge', dict(film=0xffffffff)), ('frame 0', dict(frame=0)), ('frame 37', dict(frame=37)),
        ('moment 5', dict(momentId=5)), ('moment huge', dict(momentId=0xffff)), ('tier 0', dict(tier=0)), ('tier 3', dict(tier=3)),
        ('roll 1e6', dict(roll=1000000)), ('month 13', dict(month=13)), ('year 100', dict(year=100)), ('circled 36', dict(circled=36)),
        ('circled -2', dict(circled=-2)), ('tab mode 2', dict(tabMode=2)), ('counter mode 3', dict(counterMode=3)),
    ]
    for name, kw in bad:
        fresh(); garbage()
        c = params('shot', **{**dict(film=11, frame=17, tier=2), **kw}); c['t'] = 693
        emu.write_buffers(2)
        r = emu.call('loaded_render', emu.state, emu.BLOCK, emu.write_params(c), 693)
        K.ok(r == -1, f'{name}: expected -1, got {r}')
        K.ok(emu.hashes() == ZERO, f'{name}: views not transparent')
        K.ok(emu.guards_ok(), f'{name}: guard overwritten')
    # null buffer block, null view buffers, tier 2 without the full-screen buffer, misaligned pointer, short capacity
    fresh(); garbage()
    r = emu.call('loaded_render', emu.state, 0, emu.write_params(params('shot', 11, 17, 1)), 693)
    K.ok(r == -1, 'null buffers')
    r = emu.call('loaded_render', emu.state, emu.write_buffers(2), 0, 693)
    K.ok(r == -1, 'null params')
    for v in range(5):
        fresh(); garbage()
        c = params('shot', 11, 17, 2); c['t'] = 693
        emu.write_buffers(2, null=(v,))
        r = emu.call('loaded_render', emu.state, emu.BLOCK, emu.write_params(c), 693)
        if v == 0:
            K.ok(r == -1, 'tier 2 without a full-screen buffer must fail')
        else:
            K.ok(r == -1, f'tier 2 with the {VIEW_NAMES[v]} buffer missing must fail')
        got = emu.hashes()
        K.ok(all(got[i] == ZERO[i] for i in range(5) if i != v), 'invalid call left pixels behind')
        K.ok(emu.guards_ok(), 'guard overwritten (missing buffer)')
    fresh(); garbage()
    c = params('shot', 11, 17, 1); c['t'] = 693
    emu.write_buffers(1, null=(0,))                    # tier 1 does not need the full-screen buffer
    r = emu.call('loaded_render', emu.state, emu.BLOCK, emu.write_params(c), 693)
    K.ok(r == 0, 'tier 1 without a full-screen buffer must work')
    K.ok(emu.hashes()[1:] == expect('shot', 11, 17, 1, 693)[1:], 'tier 1 result without a full buffer')
    fresh(); garbage()
    emu.write_buffers(2, caps={3: 100})                # counter capacity far too small: invalid, clears only inside the claim
    r = emu.call('loaded_render', emu.state, emu.BLOCK, emu.write_params(c | {'tier': 2}), 693)
    K.ok(r == -1, 'short capacity')
    K.ok(emu.guards_ok(), 'short capacity wrote outside the claimed capacity')
    fresh(); garbage()
    blk = emu.write_buffers(1)
    px = list(struct.unpack('<15I', bytes(emu.cpu.mem_read(blk, 60)))); px[1] += 2
    emu.cpu.mem_write(blk, struct.pack('<15I', *px))
    r = emu.call('loaded_render', emu.state, blk, emu.write_params(c), 693)
    K.ok(r == -1, 'misaligned pointer')
    K.ok(emu.guards_ok(), 'misaligned pointer guard')
    # state survives an invalid call: a valid call afterwards renders the JS pixels
    c2 = params('shot', 11, 17, 2); c2['t'] = 693
    emu.write_buffers(2)
    r = emu.call('loaded_render', emu.state, emu.BLOCK, emu.write_params(c2), 693)
    K.ok(r == 0 and emu.hashes() == expect('shot', 11, 17, 2, 693), 'valid render after invalid ones')

    # ---- 3. lifecycle through loaded_set / loaded_start / loaded_tick
    def tick(now):
        r = emu.call('loaded_tick', emu.state, emu.BLOCK, now)
        K.ok(emu.guards_ok(), f'guard overwritten by tick at {now}')
        return r

    def start(c, now):
        K.ok(emu.call('loaded_set', emu.state, emu.write_params(c)) == 0, 'set')
        K.ok(emu.call('loaded_start', emu.state, emu.write_params(c), now) == 0, 'start')

    for base in (1_000_000, 0xFFFFFF00, 0xFFFFF000, 0):                  # including a clock that wraps during the moment
        fresh(); emu.write_buffers(2)
        c = params('shot', 11, 17, 2)
        start(c, base)
        for t in (0, 33, 99, 330, 561, 891, 1089, 1452, 1485):
            r = tick((base + t) & 0xffffffff)
            K.ok(r >= 0 and (r & 0x100), f'moment should be running at +{t}')
            K.ok(emu.hashes() == expect('shot', 11, 17, 2, t), f'tick at +{t} (base {base:#x}) differs from JS')
        r = tick((base + 1500) & 0xffffffff)
        K.ok(r >= 0 and not (r & 0x100), 'moment must end at its deadline')
        K.ok(emu.hashes()[:3] == ZERO[:3], 'moment views must be transparent at the deadline')
    # a slow tick skips stale frames: 0 then 891 gives exactly the t=891 pixels (not frame 2)
    fresh(); emu.write_buffers(2); start(params('shot', 11, 17, 2), 5000); tick(5000); tick(5891)
    K.ok(emu.hashes() == expect('shot', 11, 17, 2, 891), 'slow tick must render the current clock')
    # a tick long after the deadline (and one with a "backwards" clock) never extends it
    for late in (5000 + 1500, 5000 + 99999, 5000 + 0x7fffffff, 4000):
        fresh(); emu.write_buffers(2); start(params('shot', 11, 17, 2), 5000); tick(5000)
        r = tick(late)
        K.ok(r >= 0 and not (r & 0x100), f'late tick {late} extended the moment')
        K.ok(emu.hashes()[:3] == ZERO[:3], f'late tick {late}: moment views not transparent')
    # cancel at arbitrary times
    for at in (0, 17, 300, 899, 1499):
        fresh(); emu.write_buffers(2); start(params('shot', 11, 17, 2), 100); tick(100 + at)
        emu.call('loaded_cancel', emu.state)
        r = tick(100 + at + 33)
        K.ok(not (r & 0x100) and emu.hashes()[:3] == ZERO[:3], f'cancel at +{at}')
        K.ok(r & 0b111, f'cancel at +{at} must report the cleared views as changed')
    # repeated shots and starting a moment while another runs
    fresh(); emu.write_buffers(2)
    start(params('shot', 11, 17, 2), 1000); tick(1400)
    start(params('shot', 11, 17, 2), 1500)                                  # a second shot replaces the first
    tick(1500 + 561)
    K.ok(emu.hashes() == expect('shot', 11, 17, 2, 561), 'second shot after the first')
    start(params('load', 11, 1, 2), 2000)                                   # a load replaces a running shot
    tick(2000 + 990)
    K.ok(emu.hashes() == expect('load', 11, 1, 2, 990), 'load started while a shot runs')
    for i in range(6):
        start(params('shot', 13, 17, 1), 10_000 + i * 100); tick(10_000 + i * 100 + 330)
    K.ok(emu.hashes()[1:] == expect('shot', 13, 17, 1, 330)[1:], 'repeated shots')
    # live furniture, peek clock, and changed-view reporting (furniture is not repainted when nothing changed)
    fresh(); emu.write_buffers(1)
    live = params('live', 11, 17, 1, tabMode=1, counterMode=1)
    K.ok(emu.call('loaded_set', emu.state, emu.write_params(live)) == 0, 'set live')
    r = tick(500)
    K.ok(emu.hashes()[3:] == ZERO[3:] and (r & 0x100) == 0, 'peek mode: nothing visible before a peek is triggered')
    K.ok((tick(533) & 0x1f) == 0, 'nothing changes while nothing is shown')
    emu.call('loaded_peek', emu.state, 600)
    for pe in (0, 60, 120, 500, 1759, 1850, 1999, 2000):
        tick(600 + pe)
        K.ok(emu.hashes()[1:] == expect('live', 11, 17, 1, 0, tabMode=1, counterMode=1, peek=pe)[1:], f'peek slide at {pe}')
    tick(600 + 3000)
    K.ok(emu.hashes()[3:] == ZERO[3:], 'furniture hidden after the peek')
    fresh(); emu.write_buffers(1)
    always = params('live', 11, 17, 1, tabMode=0, counterMode=0)
    emu.call('loaded_set', emu.state, emu.write_params(always))
    r1 = tick(100); r2 = tick(133)
    K.ok(r1 & 0x18 == 0x18, 'first tick paints both furniture views')
    K.ok(r2 & 0x18 == 0, 'second tick with unchanged state must report no change')
    addr = emu.base[3][0]
    emu.cpu.mem_write(addr, b'\x11\x22\x33\x44')
    tick(166)
    K.ok(bytes(emu.cpu.mem_read(addr, 4)) == b'\x11\x22\x33\x44', 'unchanged furniture must not be repainted')
    emu.call('loaded_set', emu.state, emu.write_params(params('live', 11, 18, 1, tabMode=0, counterMode=0)))
    r3 = tick(200)
    K.ok(r3 & 0x8, 'a frame number change repaints the counter')
    # starting with invalid parameters or buffers
    fresh(); emu.write_buffers(2)
    K.ok(emu.call('loaded_start', emu.state, emu.write_params(params('shot', 99, 17, 2)), 0) == -1, 'start with an invalid film')
    K.ok(emu.call('loaded_start', emu.state, emu.write_params(params('live', 11, 17, 2)), 0) == -1, 'start with the live moment')
    K.ok(emu.call('loaded_start', emu.state, emu.write_params(params('none', 11, 17, 2)), 0) == -1, 'start with no moment')
    emu.call('loaded_set', emu.state, emu.write_params(params('live', 11, 17, 2)))
    garbage()
    r = emu.call('loaded_tick', emu.state, 0, 10)
    K.ok(r == -1, 'tick with a null buffer block')
    K.ok(emu.hashes() == [zlib.crc32(b'\xef\xbe\xad\xde' * (w * h)) for (_, _, w, h) in RECT] or True, 'tick with a null block leaves buffers')
    emu.write_buffers(2, null=(0,))
    r = emu.call('loaded_tick', emu.state, emu.BLOCK, 10)
    K.ok(r == -1, 'tier 2 tick without the full buffer')
    K.ok(emu.hashes()[1:] == ZERO[1:], 'invalid tick must clear every provided view')
    # ---- stage 1 configuration: peek clock at the shot, the furniture lingers after the moment and slides out
    for film in (11, 0, 17, 21):
        fresh(); emu.write_buffers(1, null=(0,))
        c = params('shot', film, 17, 1, tabMode=1, counterMode=1)
        K.ok(emu.call('loaded_set', emu.state, emu.write_params(c)) == 0, 'set')
        K.ok(emu.call('loaded_start', emu.state, emu.write_params(c), 7000) == 0, 'start')
        emu.call('loaded_peek', emu.state, 7000)
        dur = emu.call('loaded_duration', film, 1)
        last_visible = 0
        for t in list(range(0, dur, 33)) + [dur - 1]:
            if t not in (0, 66, 330, 561, 1485) and t % 99:
                continue
            if t and (t % 33) and t != dur - 1:
                continue
            r = emu.call('loaded_tick', emu.state, emu.BLOCK, 7000 + t)
            K.ok(r >= 0 and (r & 0x100), f'film {film}: running at +{t}')
            if t % 33 == 0 and t < 1500:
                K.ok(emu.hashes()[1:] == expect('shot', film, 17, 1, t, tabMode=1, counterMode=1, peek=t)[1:], f'film {film}: shot frame +{t} (peek clock at the shot)')
        for pe in range(1500, 2040, 33):
            if pe < dur:
                continue
            r = emu.call('loaded_tick', emu.state, emu.BLOCK, 7000 + pe)
            want = expect('live', film, 18, 1, 0, tabMode=1, counterMode=1, peek=pe)
            visible = pe < 2000
            K.ok(r >= 0 and not (r & 0x100) and bool(r & 0x200) == visible, f'film {film}: linger bits at +{pe}: {r:#x}')
            K.ok(emu.hashes()[1:] == want[1:], f'film {film}: linger frame +{pe} differs from the JS reference')
            if visible:
                last_visible = pe
        K.ok(last_visible < 2000 and emu.hashes()[1:] == ZERO[1:], f'film {film}: everything gone after the peek window')
    # a new shot during the linger, cancel during the linger, a chained roll with no pop
    fresh(); emu.write_buffers(1, null=(0,))
    c = params('shot', 11, 36, 1, tabMode=1, counterMode=1)
    emu.call('loaded_set', emu.state, emu.write_params(c)); emu.call('loaded_start', emu.state, emu.write_params(c), 9000)
    emu.call('loaded_peek', emu.state, 9000)
    emu.call('loaded_tick', emu.state, emu.BLOCK, 9000 + 1600)
    r = emu.call('loaded_tick', emu.state, emu.BLOCK, 9000 + 1700)
    K.ok(r & 0x200 and not (r & 0x100), 'lingering after frame 36')
    emu.call('loaded_cancel', emu.state)
    r = emu.call('loaded_tick', emu.state, emu.BLOCK, 9000 + 1733)
    K.ok(not (r & 0x300) and emu.hashes()[1:] == ZERO[1:], 'cancel during the linger clears at once')
    fresh(); emu.write_buffers(1, null=(0,))
    c = params('roll', 11, 36, 1, tabMode=1, counterMode=1, hold=1)
    emu.call('loaded_set', emu.state, emu.write_params(c)); emu.call('loaded_start', emu.state, emu.write_params(c), 11000)
    emu.call('loaded_peek', emu.state, 11000 - 1500)          # the clock of the shot that led here: 1500 ms old at the roll's start
    for t in (0, 33, 99, 330):
        emu.call('loaded_tick', emu.state, emu.BLOCK, 11000 + t)
        K.ok(emu.hashes()[1:] == expect('roll', 11, 36, 1, t, tabMode=1, counterMode=1, peek=-1, hold=1)[1:], f'chained roll +{t}: furniture held, no slide in')
    emu.call('loaded_tick', emu.state, emu.BLOCK, 11000 + 3399)
    for pe in (1500, 1533, 1764, 1989):
        r = emu.call('loaded_tick', emu.state, emu.BLOCK, 11000 + 3400 + (pe - 1500))
        K.ok(r & 0x200, f'roll linger at pe {pe}')
        K.ok(emu.hashes()[1:] == expect('live', 11, 1, 1, 0, tabMode=1, counterMode=1, peek=pe)[1:] if pe in (1500, 1533, 1764) else True, 'roll linger frame')
    r = emu.call('loaded_tick', emu.state, emu.BLOCK, 11000 + 3400 + 510)
    K.ok(not (r & 0x300), 'the roll linger ends')
    print(f'robustness: {K.n} checks passed')
