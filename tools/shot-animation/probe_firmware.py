"""Read-only research: identify review/sound candidates in the exact known RTOS.

This locates diagnostic string references; it does NOT verify callable function
signatures, the capture lifecycle, UI ownership or hardware behavior.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'gr3x'))
from disasm import mov_refs

KNOWN = {
    '8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67': 'GR III 2.10',
    '0f11b0d28bc67932d044c5d01bc0314844a756057c89984278c73a23449a24c6': 'GR IIIx 1.60',
}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rtos', type=Path)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    data = args.rtos.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest not in KNOWN:
        parser.error('RTOS SHA-256 does not match a supported known image')
    targets = {}
    for name in (b'Controller/QuickViewController.cpp', b'Model/SoundModel.cpp', b'PlaySound', b'A:\\sound\\AF_Beep.bin'):
        positions = [p for p in range(len(data)) if data.startswith(name + b'\0', p)]
        targets[name.decode('ascii')] = [0x53000000 + p for p in positions]
    addresses = [a for values in targets.values() for a in values]
    refs = mov_refs(data, addresses)
    report = dict(camera=KNOWN[digest], rtos_sha256=digest, evidence='shell string scan and A32 MOVW/MOVT references',
                  candidates=[dict(text=k, address=hex(a), references=[hex(r) for r in refs[a]]) for k,values in targets.items() for a in values],
                  adapter_verified=False, hardware_tested=False,
                  remaining=['successful-shot event independent of review setting', 'owned UI overlay surface',
                             'UI-task millisecond tick and cancellation events', 'sound signature and live mute policy'])
    text = json.dumps(report, indent=2) + '\n'
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding='utf-8', newline='\n')
    print(text)

if __name__ == '__main__':
    main()
