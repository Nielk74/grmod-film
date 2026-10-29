"""GR Mod's film recipes, a film's Hue as its teal sky (films-r10.ts installGr3xR10TealHue): the
official descriptor builder (0x536dc0f4) runs on two builds of the same films, one with the teal sky
(--manifest) and one without (--plain), for every look the camera has and every Hue 0..8.

  - a film takes the record of its Hue (the build's nine, addedLooks[k].tealRecords) and the neutral
    Hue byte (+0x5c = 4); everything else in its descriptor is the plain build's;
  - the camera's own looks are the plain build's, byte for byte (their Hue still turns colours);
  - the nine records of a film are the same but for their matrix (word +4); Hue 4's is the plain
    build's, the others step evenly (the teal mix is linear in the step) and keep grey grey.

No firmware output. Like the other probes, this cannot test the sensor or the ISP itself.

  python teal_hue_probe.py --rtos OFFICIAL-RTOS.bin --manifest TEAL.json --plain PLAIN.json --report OUT.json
"""
import argparse
import json
import struct
from pathlib import Path
from image_control_probe import LookProbe, NATIVE
from native_probe import OUTPUT
from adj_probe import u32

if not __debug__:
    raise RuntimeError('Run without Python -O')


def matrix(probe, record):
    return struct.unpack('<9h', bytes(probe.uc.mem_read(u32(probe.uc, record + 4), 18)))


def verify(data, teal_manifest, plain_manifest):
    assert teal_manifest['lookEntries']['films'].get('tealHue') and not plain_manifest['lookEntries']['films'].get('tealHue')
    teal, plain = LookProbe(data, teal_manifest), LookProbe(data, plain_manifest)
    films, plains = teal_manifest['addedLooks'], plain_manifest['addedLooks']
    assert [f['id'] for f in films] == [f['id'] for f in plains] and all(len(f['tealRecords']) == 9 for f in films)
    calls = 0
    for look in NATIVE + [f['id'] for f in films]:
        film = next((f for f in films if f['id'] == look), None)
        for hue in range(9):
            teal.descriptor(look, hue=hue)
            plain.descriptor(look, hue=hue)
            a, b = bytes(teal.uc.mem_read(OUTPUT, 0xa0)), bytes(plain.uc.mem_read(OUTPUT, 0xa0))
            calls += 2
            if film is None:
                assert a == b, (look, hue)
                continue
            assert b[0x5c] == hue, (look, hue, b[0x5c])
            assert struct.unpack_from('<I', a, 8)[0] == film['tealRecords'][hue], (look, hue)
            assert a[0x5c] == 4, (look, hue, a[0x5c])
            assert a[:8] + a[12:0x5c] + a[0x5d:] == b[:8] + b[12:0x5c] + b[0x5d:], (look, hue)
    steps = []
    for f, p in zip(films, plains):
        recs = f['tealRecords']
        assert recs == [recs[0] + 84 * h for h in range(9)] and recs[4] == f['record']
        body = [bytes(teal.uc.mem_read(r, 84)) for r in recs]
        assert all(x[:4] + x[8:] == body[4][:4] + body[4][8:] for x in body)
        plain_body = bytes(plain.uc.mem_read(p['record'], 84))
        assert body[4][:4] + body[4][8:] == plain_body[:4] + plain_body[8:]
        m = [matrix(teal, r) for r in recs]
        assert m[4] == matrix(plain, p['record'])
        assert all(sum(row[r * 3:r * 3 + 3]) == 8192 for row in m for r in range(3))
        assert len(set(m)) == 9
        for h in range(9):
            for j in range(9):
                assert abs(m[h][j] - (m[4][j] + (h - 4) / 4 * (m[8][j] - m[4][j]))) <= 3, (f['id'], h, j)
        steps.append(max(abs(a - b) for a, b in zip(m[0], m[8])))
    return {
        'kind': 'gr3x-teal-hue-probe',
        'films': len(films),
        'native_looks': len(NATIVE),
        'descriptor_calls': calls,
        'largest_matrix_change_q13': max(steps),
        'hardware_tested': False,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('rtos', 'manifest', 'plain', 'report'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.rtos.read_bytes(), json.loads(args.manifest.read_text()), json.loads(args.plain.read_text()))
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
