"""Verify the exported comparisons and report actual visibility gates."""
from pathlib import Path
import json
import re
import hashlib
from urllib.parse import unquote
from PIL import Image
import numpy as np
from perceptual_v2 import measure

ROOT=Path('C:/Users/Antoine/Pictures/GRMod-JPEG-Experiments-v2-2026-10-31')

def main():
    summary=json.loads((ROOT/'summary.json').read_text(encoding='utf-8'))
    originals=[]
    for entry in summary['sources']:
        digest=hashlib.sha256(Path(entry['path']).read_bytes()).hexdigest()
        assert digest==entry['sha256_before']==entry['sha256_after']
        originals.append({'path':entry['path'],'unchanged':True})
    links=[]
    for reference in re.findall(r'(?:href|src)="([^"]+)"',(ROOT/'index.html').read_text(encoding='utf-8')):
        if reference.startswith(('#','http:','https:')): continue
        assert (ROOT/unquote(reference)).is_file(), reference
        links.append(reference)
    checks=[]
    for section in summary['sections']:
        for record in section['results']:
            before=np.asarray(Image.open(ROOT/record['before']).convert('RGB'),dtype=np.float32)/255
            after=np.asarray(Image.open(ROOT/record['after']).convert('RGB'),dtype=np.float32)/255
            assert before.shape==after.shape
            assert max(before.shape[:2])==1800
            if section['folder'] in ['03-film-hue','04-film-density']:
                exported=measure(before,after)
                value=exported['regions']['colour']['mean_de00']
                assert value>=3, (record['id'],value)
                assert abs(exported['regions']['all']['mean_de00']-record['metrics']['regions']['all']['mean_de00'])<.10
                checks.append({'id':record['id'],'folder':section['folder'],
                               'exported_png_target_mean_de00':value,'passes_ge3':True})
    models=json.loads((ROOT/'models/models.json').read_text(encoding='utf-8'))
    assert len(models['models'])==30
    hashes={}
    for file in (ROOT/'models').iterdir():
        if file.is_file(): hashes[file.name]=hashlib.sha256(file.read_bytes()).hexdigest()
    report={'originals':originals,'local_links_checked':len(links),
            'main_comparisons':sum(len(s['results']) for s in summary['sections']),
            'colour_visibility_checks':checks,'models':len(models['models']),
            'model_file_sha256':hashes,
            'limits':['Visibility gates establish substantial exported change, not aesthetic superiority.',
                      'RAW is compared with the paired camera JPEG; geometric differences preclude colour-accuracy claims.',
                      'Two outdoor Standard views do not validate skin tones or broad scene robustness.',
                      'Native multi-axis register packing and tone functions are emulated; ISP pixel behaviour remains unverified.']}
    (ROOT/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['main_comparisons','local_links_checked','models','colour_visibility_checks']},indent=2))

if __name__=='__main__': main()
