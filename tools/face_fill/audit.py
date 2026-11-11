"""Read-only bounded audit of Ricoh/Pentax MakerNote face structures.

No GPS, dates, camera serials or raw MakerNote payloads are exported. The
0x040b interpretation is ExifTool's K-3 III layout, tested only for plausibility
on GR III, never silently treated as proven GR III detector output.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import struct
from pathlib import Path
from PIL import Image

SOURCES=[Path('C:/Users/Antoine/Pictures/Ricoh'),Path('C:/Users/Antoine/Pictures/Ricoh2')]
FACE_TAGS={0x60:'FaceInfo',0x76:'FaceDetect',0x77:'FaceDetectFrameSize',
           0x227:'FacePos',0x228:'FaceSize',0x40b:'FaceInfoK3III'}


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def output_safe(path):
    dest=Path(path).resolve()
    for root in SOURCES:
        if dest==root.resolve() or root.resolve() in dest.parents:
            raise ValueError('Output must stay outside original folders')
    return dest


def write_json(path,obj):
    output_safe(path)
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(obj,indent=2,allow_nan=False),encoding='utf-8')


def maker_entries(data):
    if not data.startswith(b'RICOH\x00II'):
        return None
    if len(data)<10:raise ValueError('Short MakerNote')
    n=struct.unpack_from('<H',data,8)[0]
    if 10+n*12+4>len(data):raise ValueError('Truncated MakerNote directory')
    sizes={1:1,2:1,3:2,4:4,5:8,6:1,7:1,8:2,9:4,10:8,11:4,12:8}
    out={}
    for i in range(n):
        pos=10+i*12
        tag,kind,count,value=struct.unpack_from('<HHII',data,pos)
        size=sizes.get(kind,0)*count
        start=pos+8 if size<=4 else value
        if size<=0 or start+size>len(data):raise ValueError('Invalid MakerNote value bounds')
        out[tag]={'type':kind,'count':count,'data':data[start:start+size]}
    return out


def metadata(path):
    with Image.open(path) as im:
        exif=im.getexif();detail=exif.get_ifd(34665)
        entries=maker_entries(detail.get(37500,b''))
        record={'file':Path(path).name,'model':str(exif.get(272,'')).strip(),
                'orientation':int(exif.get(274,1)),'encoded_size':list(im.size),
                'iso':int(detail.get(34855,0)),'ricoh_pentax_header':entries is not None,
                'face_tags':{},'image_tone_code':None}
        if entries is None:return record
        if 0x4f in entries:
            record['image_tone_code']=int.from_bytes(entries[0x4f]['data'],'little')
        for tag,name in FACE_TAGS.items():
            if tag not in entries:continue
            payload=entries[tag]['data']
            item={'name':name,'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}
            if tag==0x40b and len(payload)>=40 and len(payload)%4==0:
                words=struct.unpack('<'+'I'*(len(payload)//4),payload)
                item.update({'candidate_layout':'ExifTool Pentax FaceInfoK3III; GR III semantics unverified',
                             'image_size':list(words[:2]),'caf_area':list(words[2:6]),
                             'count_a':words[6],'count_b':words[8],
                             'candidate_areas_a':[list(words[10+20*i:14+20*i]) for i in range(min(words[6],10))],
                             'candidate_areas_b':[list(words[210+20*i:214+20*i]) for i in range(min(words[8],10))],
                             'nonzero_area_slots':[{'slot':i,'xywh':list(words[10+20*i:14+20*i])}
                                                   for i in range(20) if any(words[10+20*i:14+20*i])],
                             'nonzero_words_after_header':sum(v!=0 for v in words[10:]),
                             'face1_area_if_populated':list(words[10:14]) if words[6] else None})
            record['face_tags'][f'0x{tag:04x}']=item
        return record


def audit(output):
    records=[]
    for root in SOURCES:
        for p in sorted(root.iterdir()):
            if p.suffix.lower() not in ('.jpg','.jpeg'):continue
            records.append({'folder':root.name,**metadata(p)})
    tags=collections.Counter(k for r in records for k in r['face_tags'])
    candidates=[r['face_tags']['0x040b'] for r in records if '0x040b' in r['face_tags']]
    result={'jpeg_count':len(records),'recognized_ricoh_makernotes':sum(r['ricoh_pentax_header'] for r in records),
            'face_tag_presence':dict(tags),'layout_count_pairs':dict(collections.Counter(f"{r.get('count_a')},{r.get('count_b')}" for r in candidates)),
            'payload_sha_distribution':dict(collections.Counter(r['sha256'] for r in candidates)),
            'scope':'Only Ricoh\\0II first MakerNote IFD and known Pentax face tags; other proprietary blocks are not decoded',
            'records':records}
    write_json(Path(output)/'metadata-audit.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='records'},indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=Path('scratch/face-fill'))
    audit(ap.parse_args().output)
