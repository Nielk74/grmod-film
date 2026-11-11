"""Measure what loaded.c costs in the ARM emulator: instructions per tick (worst and mean frame of each moment,
tier 1 and tier 1+2), code and read-only data size, state size and buffer bytes. Instruction counts come from
a Unicorn block hook (basic-block sizes), i.e. exact executed instructions, not an estimate of time on the camera.

  python native/cost_loaded.py            writes out/native/cost.json and prints a table
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_loaded as cl  # noqa: E402

FILMS = {'Portra 400 (neg)': 11, 'CineStill 800T (cine)': 13, 'Velvia (slide)': 0, 'Instant (instant)': 17, 'Acros (bw)': 8}
FRAME = {'shot': 17, 'load': 1, 'roll': 36}


def main():
    elf = cl.build()
    emu = cl.Emu(elf)
    cost = {}
    base_params = dict(roll=12, tabMode=0, counterMode=2, peek=-1, tabPeek=-2, counterPeek=-2, month=10, year=26, thumbs=0, circled=-1)

    def tick(now):
        emu.start_counting()
        r = emu.call('loaded_tick', emu.state, emu.BLOCK, now)
        n = emu.stop_counting()
        assert r >= 0 and emu.guards_ok()
        return n, r

    for moment, films, step in (('shot', list(FILMS.values())[:4], 100), ('load', [11], 100), ('roll', [11], 100)):
        for tier in (1, 2):
            per_film = {}
            samples = []
            for film in films:
                emu.guard_reset(); emu.zero_buffers(); emu.call('loaded_init', emu.state)
                emu.write_buffers(tier, null=() if tier == 2 else (0,))
                c = dict(moment=moment, momentId=cl.MOMENTS[moment], film=film, frame=FRAME[moment], tier=tier, **base_params)
                dur = emu.call('loaded_duration', film, cl.MOMENTS[moment])
                emu.call('loaded_set', emu.state, emu.write_params(c))
                emu.call('loaded_start', emu.state, emu.write_params(c), 1000)
                counts = []
                for t in range(0, dur, step):
                    n, r = tick(1000 + t)
                    counts.append((n, t))
                worst = max(counts)
                per_film[film] = {'worst_instr': worst[0], 'worst_at_ms': worst[1], 'mean_instr': sum(n for n, _ in counts) // len(counts), 'ticks': len(counts)}
                samples += [n for n, _ in counts]
            cost[f'{moment} tier {tier}'] = {'films': per_film, 'worst_instr': max(v['worst_instr'] for v in per_film.values()),
                                              'mean_instr': sum(samples) // len(samples)}
            print(f'{moment:5s} tier {tier}: worst {cost[f"{moment} tier {tier}"]["worst_instr"]:>10,} instr/tick, mean {cost[f"{moment} tier {tier}"]["mean_instr"]:>10,}   per film worst:',
                  {k: v['worst_instr'] for k, v in per_film.items()}, flush=True)
    # idle: live furniture, nothing changing; and one peek-slide frame
    emu.guard_reset(); emu.zero_buffers(); emu.call('loaded_init', emu.state); emu.write_buffers(1, null=(0,))
    c = dict(moment='live', momentId=0, film=11, frame=17, tier=1, **base_params)
    emu.call('loaded_set', emu.state, emu.write_params(c))
    first, _ = tick(100); idle, _ = tick(133)
    c.update(tabMode=1, counterMode=1)
    emu.call('loaded_set', emu.state, emu.write_params(c)); emu.call('loaded_peek', emu.state, 500)
    slide, _ = tick(560)
    cost['live first tick (paints tab and counter)'] = first
    cost['live idle tick (nothing changed)'] = idle
    cost['live peek slide tick'] = slide
    print(f'live: first tick {first:,}, idle tick {idle:,}, peek-slide tick {slide:,}')
    sz = emu.sections
    view_bytes = [w * h * 4 for (_, _, w, h) in cl.RECT]
    cost['sizes'] = {'text': sz['.text'], 'rodata': sz['.rodata'], 'exidx': sz.get('.ARM.exidx', 0), 'state': emu.state_bytes,
                     'view_bytes': dict(zip(cl.VIEW_NAMES, view_bytes)), 'tier1_buffers': sum(view_bytes[1:]), 'tier2_buffers': sum(view_bytes)}
    print('sizes:', cost['sizes'])
    out = cl.OUT / 'cost.json'
    out.write_text(json.dumps(cost, indent=1), encoding='utf8')
    print('wrote', out)


if __name__ == '__main__':
    main()
