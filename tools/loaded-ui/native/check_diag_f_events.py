"""Focused stage1f regressions against the linked ARM image, including UI ownership.

Run after linking/building diagf: python native/check_diag_f_events.py
Uses the existing native fixture; allocation, OS time, and UI lookup are substituted,
while the adapter, native view/paint code, and event trampoline execute in Unicorn.
"""
import hashlib
import json
import struct
import unittest

import check_diag_f as f


def fixture_input():
    manifest = json.loads((f.BUILD / 'payload-manifest.json').read_text(encoding='utf-8'))
    data = (f.BUILD / 'patched-rtos.bin').read_bytes()
    elf = f.BUILD / 'loaded-payload.elf'
    assert hashlib.sha256(elf.read_bytes()).hexdigest() == manifest['elfSha256']
    segments, symbols = f.ca.read_elf(elf)
    f.ca.SHA = hashlib.sha256(data).hexdigest()
    f.ca.ANCHOR = manifest['stateWord']
    f.ca.LATCH = manifest['audioLatchReadOnly']
    return data, segments, symbols


def event(q, ident, dt=0, raw=None, receiver_vtable=0x53b1f2cc, payload=None):
    q.now += dt
    at = f.ca.EVENT + 0x400
    receiver = at + 0x100
    message = at + 0x200
    q.put(receiver, receiver_vtable)
    if raw is not None:
        q.put(message, raw)
    q.uc.mem_write(at, struct.pack('<H2xII', ident, message if payload is None else payload, receiver))
    q.call('grmod_on_event', f.ca.APP, at)
    return at


def rows(q, frozen=False):
    base = 'frozen_tab' if frozen else 'tab'
    count = 'frozen_ntab' if frozen else 'ntab'
    result = {}
    size = q.L['sizeof_tabrow']
    for i in range(q.v(count)):
        at = q.s() + q.L[base] + i * size
        if size == 16:  # Allows the regression to run against the handoff image.
            word = q.get(at)
            ident, kind, flag, first_at = word & 0xffff, 0, word >> 24, at + 4
        else:
            ident = q.get(at)
            flag, kind = q.uc.mem_read(at + 5, 2)
            first_at = at + 8
        result[(kind, ident)] = dict(first=q.get(first_at), last=q.get(first_at + 4),
                                    count=q.get(first_at + 8), before=flag)
    return result


class EventRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = fixture_input()

    def new(self):
        q = f.D(*self.inputs)
        q.record(0, 0, (75, 11, 11))
        self.addCleanup(q.canaries)
        return q

    def test_panel_lays_out_before_loaded_steps(self):
        q = self.new()
        q.call(0x53391b14, q.roots[0])
        q.call('grmod_on_shot')
        q.call(0x53391b14, q.roots[0])
        self.assertGreater(q.vs(4)['copied'][0], 0, 'panel must paint before Loaded allocation')

    def test_early_failure_panel_is_visible(self):
        q = self.new()
        q.call(0x53391b14, q.roots[0])
        q.put(f.cl.USERDATA_MODEL + 4, 0)
        q.call('grmod_on_shot')
        for _ in range(3):
            q.tick()
            q.call(0x53391b14, q.roots[0])
        self.assertEqual(q.cells()[2], f.BAD)
        self.assertGreater(q.vs(4)['copied'][0], 0, 'film-read error must be visible')

    def test_rejected_callback_is_not_first_successful_copy(self):
        q = self.new()
        q.call('grmod_on_shot')
        q.now += 77
        q.call('grmod_draw', q.diag_view(), 0)
        self.assertEqual(q.v('first_draw_ms'), 0, 'rejected callback is not a copy')
        self.assertFalse(any(e[0] == 0x100a for e in q.glog()), 'PD must mean successful panel copy')
        q.now += 23
        q.call(0x53391b14, q.roots[0])
        self.assertEqual(q.v('first_draw_ms'), 100)
        self.assertEqual(sum(e[0] == 0x100a for e in q.glog()), 1)

    def test_release_callback_only_publishes_mailbox(self):
        q = self.new()
        q.call('grmod_on_shot')
        before = (q.children(q.roots[0]), q.timers(), q.cancels(), q.v('ng'), len(q.allocations))
        q.now += 400
        q.call('grmod_cancel')
        after = (q.children(q.roots[0]), q.timers(), q.cancels(), q.v('ng'), len(q.allocations))
        self.assertEqual(after, before, 'non-UI callback must not mutate UI or ring')
        event(q, 0x199, payload=0, receiver_vtable=0)
        self.assertEqual(q.children(q.roots[0]), [])
        self.assertEqual(q.timers(), [])
        self.assertEqual(q.v('rl_count'), 1)

    def test_startup_flood_cannot_reserve_capture_rows(self):
        q = self.new()
        for ident in range(0x400, 0x428):
            event(q, ident)
        q.call('grmod_cancel')
        event(q, 0x163, 3)
        self.assertIn((0, 0x163), rows(q), 'new capture window needs fresh row capacity')

    def test_native_messages_are_not_timer_0199(self):
        q = self.new()
        event(q, 0x199, raw=0x22440229)
        event(q, 0x199, 1, raw=0x23480201)
        event(q, 0x199, 1, receiver_vtable=0, payload=0)
        found = rows(q)
        self.assertIn((1, 0x22440229), found)
        self.assertIn((1, 0x23480201), found)
        self.assertIn((0, 0x199), found)

    def test_other_0199_receiver_never_dereferences_payload(self):
        q = self.new()
        event(q, 0x199, receiver_vtable=0, payload=0xfffffff0)
        self.assertIn((0, 0x199), rows(q))

    def test_full_table_still_counts_known_ids(self):
        q = self.new()
        for ident in range(0x400, 0x428):
            event(q, ident)
        event(q, 0x400)
        self.assertEqual(rows(q)[(0, 0x400)]['count'], 2)
        self.assertGreater(q.v('tab_ovf'), 0)

    def test_release_contention_is_bounded_and_visible(self):
        q = self.new()
        event(q, 0x199, receiver_vtable=0, payload=0)
        q.put(q.s() + q.L['release_gate'], 1)
        q.call('grmod_cancel')
        self.assertEqual(q.v('release_dropped'), 1)
        self.assertEqual(q.v('pending_releases'), 0)
        q.put(q.s() + q.L['release_gate'], 0)
        q.call('grmod_cancel')
        event(q, 0x163)
        self.assertEqual(q.v('rl_count'), 1)
        self.assertEqual(q.v('release_gate'), 0)

    def test_clock_failure_never_invents_release_latency(self):
        q = self.new()
        event(q, 0x199, receiver_vtable=0, payload=0)
        q.clock_ok = False
        q.call('grmod_cancel')
        q.clock_ok = True
        event(q, 0x163, 100)
        q.call('grmod_on_shot')
        self.assertEqual(q.v('rl_count'), 1)
        self.assertEqual(q.v('rl_valid'), 0)
        self.assertEqual(q.v('frozen_base_valid'), 0)
        self.assertEqual(q.get(q.s() + q.L['rlhk_valid']), 0)

    def test_frozen_capture_survives_later_button_and_release(self):
        q = self.new()
        event(q, 0x199, receiver_vtable=0, payload=0)
        q.call('grmod_cancel')
        event(q, 0x199, 10, raw=0x22440229)
        event(q, 0x199, 15000, raw=0x23480201)
        q.call('grmod_on_shot')
        snapshot = rows(q, frozen=True)
        self.assertIn((1, 0x22440229), snapshot)
        self.assertIn((1, 0x23480201), snapshot)
        q.call('grmod_cancel')
        event(q, 0x40, 100)
        self.assertEqual(rows(q, frozen=True), snapshot)
        self.assertEqual(q.v('frozen_base'), 1000)

    def test_clock_recovery_preserves_panel_window(self):
        q = self.new()
        q.now = 60000
        q.clock_ok = False
        q.call('grmod_on_shot')
        q.clock_ok = True
        for _ in range(22):
            q.fire(33)
        self.assertEqual(q.v('diag_on'), 1, 'recovered uptime must not expire the panel')
        self.assertEqual(q.v('page'), 0, 'unknown hook time needs tick-based paging')
        self.assertIn(q.diag_view(), q.children(q.roots[0]))

    def test_unknown_event_time_has_a_visible_glyph(self):
        q = self.new()
        q.clock_ok = False
        q.call('grmod_on_shot')
        q.put(q.s() + q.L['page'], 1)
        q.call('refresh', q.s())
        pixels = q.s() + q.L['pixels']
        unknown = [q.get(pixels + 4 * (y * 240 + x))
                   for y in range(34, 48) for x in range(20, 30)]
        self.assertIn(0xffffffff, unknown, 'unknown F time must render a readable mark')

    def test_multiple_attempts_are_counted_without_photo_pairing(self):
        q = self.new()
        event(q, 0x199, receiver_vtable=0, payload=0)
        q.call('grmod_cancel')
        q.now += 100
        q.call('grmod_cancel')
        event(q, 0x163, 50)
        q.call('grmod_on_shot')
        self.assertEqual(q.v('rl_count'), 2)
        self.assertEqual(q.get(q.s() + q.L['rlhk_delta']), 2)
        self.assertEqual(q.get(q.s() + q.L['rlhk']), 50)
        self.assertEqual(rows(q)[(2, 0x1001)]['count'], 2, 'boundary includes both coalesced attempts')

    def test_uint32_clock_wrap_keeps_observed_delta(self):
        q = self.new()
        event(q, 0x199, receiver_vtable=0, payload=0)
        q.now = 0xfffffff0
        q.call('grmod_cancel')
        event(q, 0x163, 64)
        q.call('grmod_on_shot')
        self.assertEqual(q.get(q.s() + q.L['rlhk']), 64)
        self.assertEqual(q.get(q.s() + q.L['rlhk_valid']), 1)


def measure_cost(q):
    """Count only from real trampoline entry to restored native continuation.

    The continuation is stopped before native dispatch, so renderer work isn't
    counted or slowed by an unbounded per-instruction callback. Clock/allocator
    boundary stubs are the fixture's, so this is instructions, never CPU time.
    """
    from unicorn import UC_HOOK_CODE
    state = {'count': 0}

    def count(uc, at, size, user):
        if at == 0x53228ab8:
            q.ret(q.r(0))
        else:
            state['count'] += 1

    def sample(ident, dt=0, raw=None):
        at = f.ca.EVENT + 0x400
        q.now += dt
        q.put(at + 0x100, 0x53b1f2cc if raw is not None else 0)
        q.put(at + 0x200, raw or 0)
        q.uc.mem_write(at, struct.pack('<H2xII', ident, at + 0x200, at + 0x100))
        state['count'] = 0
        h = q.uc.hook_add(UC_HOOK_CODE, count)
        try:
            q.call('grmod_hook_event', f.ca.APP, at)
        finally:
            q.uc.hook_del(h)
        return state['count']

    result = dict(new_timer=sample(0x199), repeated_timer=sample(0x199, 33),
                  timer_after_500ms=sample(0x199, 600), raw_message=sample(0x199, 1, 0x23480201))
    for ident in range(0x400, 0x420):
        event(q, ident)
    result['full_table_unknown'] = sample(0x900)
    assert max(result.values()) < 1024, ('bounded steady-state hook instruction budget', result)
    q.canaries()
    return result


if __name__ == '__main__':
    unittest.main(verbosity=2)
