"""Rebuild v3 in isolation with only extra film MTF disabled.

No shared source is edited. A pinned transformation of the reviewed baseline
builder is written into this worktree's ignored scratch directory and executed.
This baseline is NOT the face-fill feature candidate.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
OFFICIAL=Path('C:/Users/Antoine/project/grmod-film/scratch/video-firmware-high-rate-2026-11-01/original/fwdc239b.bin')
CUBE=Path('C:/Users/Antoine/project/grmod-film/examples/gr3x/film-pack-v3/out/cube/01-Pro-400H.cube')
PICTURES=Path('C:/Users/Antoine/project/grmod-film/scratch/portra-2026-11-01/build-out/pictures')
OUT=ROOT/'scratch/face-fill-firmware';BASELINE=OUT/'baseline-no-extra-mtf'


def main():
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    assert digest(OFFICIAL)=='d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4'
    builder=ROOT/'examples/gr3x/film-pack-v3/build.ts';original=builder.read_text(encoding='utf-8')
    expected="const FILM_MTF = new Set([...LOOKS.map(l => l.name), 'Pro 400H']);"
    assert original.count(expected)==1,'Baseline builder changed; review before adapting'
    changed=original.replace(expected,'const FILM_MTF = new Set<string>();')
    changed=changed.replace('../../../core','../../core')
    changed=changed.replace("'../film-pack/","'../../examples/gr3x/film-pack/")
    changed=changed.replace("'./response'","'../../examples/gr3x/film-pack-v3/response'")
    OUT.mkdir(parents=True,exist_ok=True);prepared=OUT/'baseline-build.ts'
    prepared.write_text(changed,encoding='utf-8',newline='\n')
    command=['node',str(ROOT/'node_modules/vite-node/vite-node.mjs'),str(prepared),str(OFFICIAL),str(CUBE),str(PICTURES),str(BASELINE)]
    result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    (OUT/'baseline-build.log').write_text(result.stdout+result.stderr,encoding='utf-8')
    if result.returncode:raise RuntimeError('Baseline build failed; see baseline-build.log')
    photos=sorted(PICTURES.glob('*.bgr'))
    report=dict(role='V3 baseline only; not face-fill feature',official_sha256=digest(OFFICIAL),
                source_builder_sha256=digest(builder),prepared_builder_sha256=digest(prepared),
                transformation='Only FILM_MTF set emptied; import paths adapted for scratch execution',
                pro400h_cube_sha256=digest(CUBE),end_screen_sha256={p.name:digest(p) for p in photos},
                file=str(BASELINE/'fwdc239b.bin'),sha256=digest(BASELINE/'fwdc239b.bin'),
                returncode=result.returncode)
    (OUT/'baseline-report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
