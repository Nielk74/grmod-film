import sys, glob, os
sys.path.insert(0, os.path.dirname(__file__))
from common import *
rows = []
for d in DIRS:
    for p in sorted(glob.glob(d + r"\*.JPG")):
        try: rows.append((os.path.basename(p)[:-4], d[-1], image_tone(p)))
        except Exception as e: rows.append((os.path.basename(p)[:-4], d[-1], 'err'))
std = [r for r in rows if r[2] == 0x100]
print(len(rows), len(std)); print({hex(r[2]) if isinstance(r[2], int) else r[2] for r in rows})
import collections
print(collections.Counter(hex(r[2]) if isinstance(r[2], int) else r[2] for r in rows))
open(OUT + r"\standard.txt", "w").write("\n".join(f"{n} {k}" for n, k, t in std))
