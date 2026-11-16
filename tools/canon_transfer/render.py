# SPDX-License-Identifier: GPL-2.0-only
"""Render a review prototype; originals and production film tables remain inputs.

Requirements: numpy, Pillow. Run models.ts first, then:
    python tools/canon_transfer/render.py scratch/canon-transfer-2026-11-04
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path

import numpy as np
from PIL import Image, ImageCms, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[2]
PHOTOS = Path('C:/Users/Antoine/Pictures/Ricoh')
SRGB = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
SET = 2 * 128 * 128 + 256
GAIN = (38, 64, 102)

SCENES = [
    ('R0000022', 'Sky & foliage', (0.48, 0.36), 'Compare the blue sky, green trees and pale stone. The crop crosses the dome and sky.'),
    ('R0000030', 'Daylight portrait', (0.46, 0.43), 'Compare skin warmth, the beige coat and the transition into highlights.'),
    ('R0000027', 'Warm stone', (0.44, 0.4), 'Look at warm stone against blue sky, then the separation between bright and shaded walls.'),
    ('R0000023', 'People & whites', (0.52, 0.70), 'Compare pale clothing, skin and the crowded sunlit scene.'),
    ('AK000164', 'Night portrait', (0.49, 0.44), 'Judge the skin under warm light. In Grain only, inspect the smooth shadow areas.'),
    ('AK000167', 'Night lights', (0.6, 0.34), 'Check dark pavement, warm lamps and the depth of the shadows. Halation is off on both sides.'),
    ('R0000005', 'Window portrait', (0.47, 0.43), 'Look at backlit skin, hair and the white shirt. The white balance is the original camera balance.'),
    ('R0000004', 'Food & warm light', (0.5, 0.5), 'Compare the yellow pastry, warm highlights and subtle tones in the plate.'),
    ('gr3-stream', 'Forest greens', (0.50, 0.47), 'Compare the foliage colour and dark water. This source is a 2400px preview; its crop is at source resolution.'),
]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tone(path):
    with Image.open(path) as im:
        note = im.getexif().get_ifd(0x8769).get(0x927C)
    if not note or not note.startswith(b'RICOH'):
        return None
    endian = '<' if note[6:8] == b'II' else '>'
    for i in range(struct.unpack(endian + 'H', note[8:10])[0]):
        tag, kind, _, value = struct.unpack(endian + 'HHI4s', note[10 + i*12:22 + i*12])
        if tag == 0x004F:
            return struct.unpack(endian + ('H' if kind == 3 else 'I'), value[:2] if kind == 3 else value)[0]
    return None


def profile(path):
    raw = Path(path).read_bytes()
    assert len(raw) == 2 * SET
    return [(np.frombuffer(raw, np.int8, 16384, s*SET).reshape(128, 128).astype(np.int32),
             np.frombuffer(raw, np.int8, 16384, s*SET+16384).reshape(128, 128).astype(np.int32),
             np.frombuffer(raw, np.uint8, 256, s*SET+32768).astype(np.int32)) for s in range(2)]


def grid_apply(rgb, grid):
    shape = rgb.shape
    flat = np.asarray(rgb, np.float32).reshape(-1, 3)
    result = np.empty_like(flat)
    n = len(grid)
    for start in range(0, len(flat), 65536):
        p = np.clip(flat[start:start+65536], 0, 1) * (n - 1)
        low = np.minimum(p.astype(np.int32), n-2)
        f = p-low
        out = np.zeros(p.shape, np.float64)
        for r in (0, 1):
            for g in (0, 1):
                for b in (0, 1):
                    w = (f[:, 0] if r else 1-f[:, 0]) * (f[:, 1] if g else 1-f[:, 1]) * (f[:, 2] if b else 1-f[:, 2])
                    out += grid[low[:, 0]+r, low[:, 1]+g, low[:, 2]+b] * w[:, None]
        result[start:start+len(p)] = out
    return result.reshape(shape)


def byte_rgb(rgb):
    assert np.isfinite(rgb).all()
    return np.floor(np.clip(rgb, 0, 1)*255+0.5).astype(np.uint8)


def luma(rgb):
    rgb = np.asarray(rgb, np.float64)
    return np.clip(np.floor(0.299*rgb[..., 0]+0.587*rgb[..., 1]+0.114*rgb[..., 2]+0.5), 0, 255).astype(np.int32)


def seed_for(rgb):
    h, w = rgb.shape[:2]
    seed = (w*0x10001+h) & 0xffffffff
    for y in range(8):
        yy, xx = h*y >> 3, w*(7-y) >> 3
        seed = ((seed*0x01000193) ^ int(luma(rgb[yy:yy+1, xx:xx+1])[0, 0])) & 0xffffffff
    return seed


def seed_from_source(im, grid):
    w, h = im.size
    pixels = np.array([im.getpixel((w*(7-y) >> 3, h*y >> 3)) for y in range(8)], np.float32)/255
    ys = luma(byte_rgb(grid_apply(pixels, grid)))
    seed = (w*0x10001+h) & 0xffffffff
    for value in ys:
        seed = ((seed*0x01000193) ^ int(value)) & 0xffffffff
    return seed


def offsets(x, y, seed):
    xx = np.asarray(x >> 5, np.uint32)
    yy = np.asarray(y >> 5, np.uint32)
    with np.errstate(over='ignore'):
        h = (xx*np.uint32(0x9e3779b1)) ^ (yy*np.uint32(0x85ebca77)) ^ np.uint32(seed)
        h ^= h >> np.uint32(15); h *= np.uint32(0x2c1b3c6d)
        h ^= h >> np.uint32(12); h *= np.uint32(0x297a2d39)
        h ^= h >> np.uint32(15)
    return (h & np.uint32(0x7f7f)).astype(np.int32)


def grain(rgb, parts, amount, size, step, *, x0=0, y0=0, seed=None):
    """Same integer tile computation and RGB preview conversion as grain.ts.

    Absolute source coordinates and the full-frame seed make crop rendering
    identical to extracting the crop after full-frame grain processing.
    """
    if not amount:
        return rgb.copy()
    assert x0 % 2 == 0 and rgb.shape[1] % 2 == 0
    h, w = rgb.shape[:2]
    seed = seed_for(rgb) if seed is None else seed
    att = 65536//step if step > 256 else 256
    gain = GAIN[amount-1]*att >> 8
    lt, ct, tones = parts[size]
    result = rgb.copy()
    xs = np.arange(x0, x0+w, dtype=np.int32)[None, :]
    for row in range(0, h, 96):
        a = rgb[row:row+96].astype(np.float64)
        ys = np.arange(y0+row, y0+row+len(a), dtype=np.int32)[:, None]
        off = offsets(xs, ys, seed)
        tx = (off + ((xs & 31)*step >> 8)) & 127
        ty = ((off >> 8) + ((ys & 31)*step >> 8)) & 127
        Y = luma(a)
        strength = gain*tones[Y]
        dY = np.clip(Y+((lt[ty, tx]*strength+32768) >> 16), 0, 255)-Y
        even = a[:, ::2]
        cb = np.clip(np.floor(128-0.168736*even[..., 0]-0.331264*even[..., 1]+0.5*even[..., 2]+0.5), 0, 255).astype(np.int32)
        cr = np.clip(np.floor(128+0.5*even[..., 0]-0.418688*even[..., 1]-0.081312*even[..., 2]+0.5), 0, 255).astype(np.int32)
        cx, cy = tx[:, ::2] & ~1, ty[:, ::2]
        f = strength[:, ::2]
        dcb = np.repeat(np.clip(cb+((ct[cy, cx]*f+32768) >> 16), 0, 255)-cb, 2, axis=1)
        dcr = np.repeat(np.clip(cr+((ct[cy, cx+1]*f+32768) >> 16), 0, 255)-cr, 2, axis=1)
        v = np.stack([a[..., 0]+dY+1.402*dcr, a[..., 1]+dY-0.344136*dcb-0.714136*dcr, a[..., 2]+dY+1.772*dcb], -1)
        result[row:row+len(a)] = np.clip(np.floor(v+0.5), 0, 255).astype(np.uint8)
    return result


def verify_numerics(out, profiles):
    original = np.fromfile(out/'models/grain-test-input.rgb', np.uint8).reshape(96, 144, 3)
    checks = []
    for name, parts in profiles.items():
        for setting in (1, 2, 3, 5, 6, 7):
            want = np.fromfile(out/f'models/grain-test-{name}-{setting}.rgb', np.uint8).reshape(original.shape)
            got = grain(original, parts, setting & 3, setting >> 2, 256)
            delta = int(np.abs(got.astype(int)-want.astype(int)).max())
            assert delta == 0, (name, setting, delta)
            # Crops must inherit the source coordinates and full-frame seed.
            small = grain(original[20:80, 34:120], parts, setting & 3, setting >> 2, 256, x0=34, y0=20, seed=seed_for(original))
            assert np.array_equal(small, got[20:80, 34:120]), (name, setting, 'crop mismatch')
            checks.append({'profile': name, 'setting': setting, 'maxByteErrorAgainstTypeScript': delta, 'cropMatchesFullFrame': True})
    axis = np.linspace(0, 1, 33, dtype=np.float32)
    identity = np.stack(np.meshgrid(axis, axis, axis, indexing='ij'), -1)
    sample = np.random.default_rng(4).random((10007, 3), dtype=np.float32)
    error = float(np.max(np.abs(grid_apply(sample, identity)-sample)))
    assert error < 1e-6
    return {'grainVectors': checks, 'identityInterpolationMaxError': error}


def save(rgb, path):
    im = Image.fromarray(rgb)
    if path.suffix == '.png':
        im.save(path, compress_level=5, icc_profile=SRGB)
    else:
        im.save(path, quality=97, subsampling=0, icc_profile=SRGB)


def source_record(key):
    if key == 'gr3-stream':
        path = ROOT/'ui/src/assets/samples/gr3-stream.jpg'
        provenance = 'Standard verified by repository sample CREDITS.md; source reduced to 2400px'
        attribution = 'Stephan van Helden / Wikimedia Commons / CC BY-SA 4.0; https://commons.wikimedia.org/wiki/File:M%C3%BChlbach_s%C3%BCdwestlich_von_Eyrichshof.jpg'
    else:
        path = PHOTOS/(key+'.JPG')
        assert tone(path) == 0x100, f'{path}: not a Standard JPEG'
        provenance = 'Original camera JPEG; Ricoh maker-note ImageTone 0x100 verified'
        attribution = 'Project author private photograph; local review only'
    with Image.open(path) as source:
        exif = source.getexif()
        iso = exif.get_ifd(0x8769).get(34855, '?')
        im = ImageOps.exif_transpose(source).convert('RGB')
    return path, im, {'id':key,'iso':int(iso) if isinstance(iso, int) else str(iso),'source':str(path),'sourceSha256':digest(path),
                      'width':im.width,'height':im.height,'basis':provenance,'attribution':attribution}


def labelled_sheet(panels, title, labels, width=620):
    font_path = 'C:/Windows/Fonts/segoeui.ttf'
    font = ImageFont.truetype(font_path, 22)
    heading = ImageFont.truetype(font_path, 27)
    scaled=[]
    for im in panels:
        im=im.copy();im.thumbnail((width,800),Image.Resampling.LANCZOS);scaled.append(im)
    height=max(im.height for im in scaled)
    sheet=Image.new('RGB',(width*len(panels),height+112),(22,24,21))
    draw=ImageDraw.Draw(sheet);draw.text((18,13),title,font=heading,fill=(231,235,226))
    for i,(im,label) in enumerate(zip(scaled,labels)):
        draw.text((i*width+18,64),label,font=font,fill=(205,214,194))
        sheet.paste(im,(i*width+(width-im.width)//2,112))
    return sheet


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    args=parser.parse_args();out=args.output.resolve()
    assert PHOTOS.resolve() not in out.parents and out != PHOTOS.resolve()
    models=json.loads((out/'models.json').read_text(encoding='utf-8'))
    profiles={name:profile(out/f'models/grain-{name}.bin') for name in ('current','candidate')}
    verification=verify_numerics(out,profiles)
    print('Verified: 12 TypeScript grain vectors and absolute-coordinate crops',flush=True)
    grids={(f['key'],variant):np.fromfile(out/f'models/{f["key"]}-{variant}.f32','<f4').reshape(33,33,33,3)
           for f in models['films'] for variant in ('current','candidate','target')}
    (out/'thumbs').mkdir(exist_ok=True)
    records=[];outputs=[]
    for key,title,centre,look_for in SCENES:
        path,im,record=source_record(key)
        record.update(title=title,lookFor=look_for,thumb=f'thumbs/{key}.jpg')
        thumb=im.copy();thumb.thumbnail((240,180),Image.Resampling.LANCZOS);thumb.save(out/record['thumb'],quality=90)
        preview=im.copy();preview.thumbnail((1800,1800),Image.Resampling.LANCZOS)
        # Even widths keep 4:2:2 chroma pairs aligned in both paths.
        if preview.width%2:preview=preview.crop((0,0,preview.width-1,preview.height))
        w,h=im.size;cw=ch=720
        x0=max(0,min(w-cw,round(centre[0]*w-cw/2))) & ~1
        y0=max(0,min(h-ch,round(centre[1]*h-ch/2)))
        crop=im.crop((x0,y0,x0+cw,y0+ch));record['crop']=[x0,y0,cw,ch]
        folder=out/'images'/key;folder.mkdir(parents=True,exist_ok=True)
        for film in models['films']:
            fk=film['key'];size=int(film['grain']['size']=='large');amount=film['grain']['amount']
            for part,source in [('full',preview),('crop',crop)]:
                pixels=np.asarray(source,np.float32)/255
                colours={variant:byte_rgb(grid_apply(pixels,grids[fk,variant])) for variant in ('current','candidate','target')}
                step=max(1,int(6000*256/max(preview.size if part=='full' else im.size)))
                def texture(colour_name,grain_name):
                    kws={} if part=='full' else dict(x0=x0,y0=y0,seed=seed_from_source(im,grids[fk,colour_name]))
                    return grain(colours[colour_name],profiles[grain_name],amount,size,step,**kws)
                variants={'current-colour':colours['current'],'candidate-colour':colours['candidate'],
                          'current-grain':texture('current','current'),'candidate-old-grain':texture('candidate','current'),
                          'candidate-grain':texture('candidate','candidate'),'target-grain':texture('target','candidate')}
                for variant,rgb in variants.items():
                    dest=folder/(f'{fk}-{variant}.jpg' if part=='full' else f'{fk}-{variant}-crop.png')
                    save(rgb,dest);outputs.append({'path':dest.relative_to(out).as_posix(),'size':list(rgb.shape[1::-1]),'sha256':digest(dest)})
            print(f'{key} / {film["name"]}',flush=True)
        assert digest(path)==record['sourceSha256'],f'Original changed: {path}'
        records.append(record)
    # A few direct comparison images for chat, from the same files used by the viewer.
    for key,fk,name in [('R0000030','portra400','Portra 400 · daylight portrait'),('R0000027','gold200','Gold 200 · warm stone'),('AK000164','cinestill800t','CineStill 800T · night portrait'),('R0000022','portra400','Portra 400 · sky and foliage')]:
        paths=[out/'images'/key/f'{fk}-{v}.jpg' for v in ('current-grain','candidate-old-grain','candidate-grain')]
        panels=[Image.open(p).convert('RGB') for p in paths]
        labelled_sheet(panels,name,['Current v3','Adapted colour + current grain','Adapted colour + new grain']).save(out/f'comparison-{fk}-{key}.jpg',quality=95,subsampling=0,icc_profile=SRGB)
    key='AK000164';fk='cinestill800t'
    panels=[Image.open(out/'images'/key/f'{fk}-{v}-crop.png').convert('RGB') for v in ('candidate-old-grain','candidate-grain')]
    labelled_sheet(panels,'CineStill 800T · same colour, grain only · 100% source crop',['Current grain','New grain · matched mid-grey strength'],width=720).save(out/'comparison-grain.png',icc_profile=SRGB)
    for rec in records:
        assert digest(rec['source'])==rec['sourceSha256']
    data={'scenes':records,'films':[{'key':f['key'],'name':f['name']} for f in models['films']]}
    (out/'data.js').write_text('window.CANON_TRANSFER = '+json.dumps(data,ensure_ascii=False)+';\n',encoding='utf-8',newline='\n')
    manifest={'schema':1,'sources':records,'outputs':outputs,'modelsSha256':digest(out/'models.json'),'method':models['limitations'],
              'rendering':'Colour at 1800px for full-frame review; 720px crops from original oriented JPEGs. No exposure or WB matching. Grain crop coordinates and seeds inherited from full source.'}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
    verification.update(originalHashesUnchanged=True,scenes=len(records),films=3,renderedImages=len(outputs),
                        colourGridDimensions=[33,33,33,3],allOutputsFinite=True,halationAndExtraDenoising='off in all variants')
    (out/'verification.json').write_text(json.dumps(verification,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'output':str(out),'scenes':len(records),'images':len(outputs),'originalHashesUnchanged':True}),flush=True)


if __name__=='__main__':
    main()
