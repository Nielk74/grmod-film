"""Read-only final artifact/source/photo/output verification."""
import hashlib
import json
from pathlib import Path
import struct
from PIL import Image

ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'scratch/trichrome-firmware'


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    report=json.loads((OUT/'build-report.json').read_text(encoding='utf-8'))
    assert digest(Path(report['officialPath']))==report['officialSha256']=='d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4'
    assert digest(Path(report['baselinePath']))==report['baselineSha256']=='0eedc01b7f61cee64d6228978b0f99a01090a49491d6cb103dbfee4a3cc4fa59'
    candidate=OUT/'fwdc239b.bin';assert digest(candidate)==report['sha256']
    packed=candidate.read_bytes();assert sum(struct.unpack('<'+'I'*(len(packed)//4),packed))&0xffffffff==0
    old=(OUT/'baseline-rtos.bin').read_bytes();new=(OUT/'candidate-rtos.bin').read_bytes()
    allowed=set()
    for p in report['patchmap']:
        offset=p['address']-report['rtosBase'];assert struct.unpack_from('<I',old,offset)[0]==p['before']
        assert struct.unpack_from('<I',new,offset)[0]==p['after'];allowed.update(range(offset,offset+4))
    changed=[i for i,(a,b) in enumerate(zip(old,new)) if a!=b]
    assert set(changed)<=allowed and len(report['patchmap'])==5
    assert len(new)-len(old)==24576
    linked=report['module'];module=(OUT/'native/module.bin').read_bytes()
    assert new[len(old):len(old)+len(module)]==module and digest(OUT/'native/module.bin')==linked['sha256']
    for name,expected in linked['source_sha256'].items():assert digest(ROOT/'tools/trichrome_firmware/native'/name)==expected
    for name in ['installed-hook-verification.json']:
        r=json.loads((OUT/name).read_text(encoding='utf-8'));assert r['candidate_sha256']==report['sha256']
    inventory=json.loads((ROOT/'scratch/trichrome/inventory-before.json').read_text(encoding='utf-8'))
    for photo in inventory:assert digest(Path(photo['path']))==photo['sha256_before'],photo['path']
    visual=json.loads((OUT/'visual/manifest.json').read_text(encoding='utf-8'))
    for name,expected in visual['outputs'].items():
        path=OUT/'visual'/name;assert digest(path)==expected
        with Image.open(path) as im:im.verify()
        with Image.open(path) as im:assert not im.getexif()
    summary=dict(candidate_sha256=report['sha256'],official_unchanged=True,baseline_hash_pinned=True,
        packed_word_sum_zero=True,hook_words=5,original_rtos_changed_bytes=len(changed),
        original_rtos_changes_inside_five_words=True,appended_rtos_bytes=len(new)-len(old),
        native_module_and_source_hashes_match=True,installed_hook_report_matches_candidate=True,
        originals_count=len(inventory),all_original_photos_unchanged=True,
        generated_images_verified=len(visual['outputs']),no_copied_exif=True,hardware_tested=False)
    (OUT/'final-audit.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8');print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
