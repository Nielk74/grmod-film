"""Rebuild fill from source + recorded model boxes and verify actual exports.

Records hashes separately, and saves lossless source/fill/support evidence.
This checks exported JPEG bytes against a recomputed render, rather than
accepting numerical assertions copied from the renderer's JSON manifest.
"""
from __future__ import annotations
import argparse
import io
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
from audit import output_safe,sha,write_json
from face_fill import face_mask,fill_light,srgb_to_linear,LUMA
from run import open_rgb,image,SRGB


def encoded_jpeg(im,profile):
    data=io.BytesIO();im.save(data,format='JPEG',quality=97,subsampling=0,icc_profile=profile)
    return data.getvalue()


def profile_colour_data(profile):
    # LittleCMS creates a timestamp in ICC header bytes24..35. ICC profile ID
    # can also depend on that date. All colour tags and other header bytes
    # must still match the generated sRGB profile exactly.
    return profile[:24]+bytes(12)+profile[36:84]+bytes(16)+profile[100:]


def run(output,record=False):
    output=output_safe(output)
    summary=json.loads((output/'summary.json').read_text(encoding='utf-8'))
    results=[]
    for item in summary['records']:
        src=Path(item['source']);folder=output/(src.parent.name+'-'+src.stem)
        assert sha(src)==item['source_sha256_before']==item['source_sha256_after']
        im=open_rgb(src,item['max_side']);rgb=np.asarray(im,np.float32)/255
        small=im.copy();small.thumbnail((1600,1600),Image.Resampling.LANCZOS)
        sx,sy=small.width/im.width,small.height/im.height
        faces=[dict(f,box=[f['box'][0]*sx,f['box'][1]*sy,f['box'][2]*sx,f['box'][3]*sy]) for f in item['detector']['accepted']]
        mask=cv2.resize(face_mask(np.asarray(small,np.float32)/255,faces),im.size,interpolation=cv2.INTER_LINEAR)
        fill=fill_light(rgb,mask,item['fill']['maximum_ev'])
        with Image.open(folder/'original.jpg') as saved:
            profile=saved.info['icc_profile']
        assert profile_colour_data(profile)==profile_colour_data(SRGB.tobytes())
        # Exact byte equality proves the saved JPEG is the recomputed result.
        assert (folder/'original.jpg').read_bytes()==encoded_jpeg(im,profile)
        assert (folder/'fill.jpg').read_bytes()==encoded_jpeg(image(fill),profile)
        assert np.array_equal(fill[mask==0],rgb[mask==0])
        assert not np.any((fill.max(-1)>=1)&(rgb.max(-1)<1))
        expected={'original-lossless.png':image(rgb),'fill-lossless.png':image(fill),
                  'mask-support.png':Image.fromarray((mask>0).astype(np.uint8)*255)}
        if record:
            for name,pixels in expected.items():pixels.save(folder/name)
        for name,pixels in expected.items():
            with Image.open(folder/name) as saved:
                assert np.array_equal(np.asarray(saved),np.asarray(pixels))
                assert not saved.getexif()
        original_u8=np.asarray(expected['original-lossless.png'])
        filled_u8=np.asarray(expected['fill-lossless.png'])
        assert np.array_equal(original_u8[mask==0],filled_u8[mask==0])
        if not faces:
            assert np.array_equal(rgb,fill)
            assert sha(folder/'original.jpg')==sha(folder/'fill.jpg')
            for film in item['films']:
                slug=Path(film['film']['file']).stem
                assert sha(folder/(slug+'-full.jpg'))==sha(folder/(slug+'-blind.jpg'))==sha(folder/(slug+'-reference.jpg'))
        hash_path=folder/'artifact-hashes.json'
        hashes={p.name:sha(p) for p in sorted(folder.iterdir()) if p.suffix.lower() in ('.jpg','.png')}
        if record:write_json(hash_path,hashes)
        assert hashes==json.loads(hash_path.read_text(encoding='utf-8'))
        results.append({'file':src.name,'source_hash_verified':True,'jpeg_recomputed_exact':True,
                        'outside_mask_exact_lossless':True,'no_faces_exact_identity':not bool(faces),
                        'hashed_artifacts':len(hashes),'native':item['max_side']==0})
        print(src.name,'recomputed JPEG + lossless identity verified',len(hashes),'hashes',flush=True)
    write_json(output/'verification.json',{'results':results,'all_passed':True})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('scratch/face-fill'))
    p.add_argument('--record',action='store_true');a=p.parse_args();run(a.output,a.record)
