"""Reproduce inventory, real-sequence comparisons and controlled stress cases.

python tools/trichrome/run.py --out scratch/trichrome --max-edge 2400
All original files are SHA-256 checked before and after; output carries no EXIF.
"""
import argparse
import hashlib
import html
import json
import math
from pathlib import Path
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from pipeline import reduce_plane, warp_plane, process, reconstruct

ROOTS=[Path('C:/Users/Antoine/Pictures/Ricoh'),Path('C:/Users/Antoine/Pictures/Ricoh2')]
FONT_PATH=Path('C:/Windows/Fonts/arial.ttf')


def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def write_json(path,value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')


def inventory():
    records=[]
    for root in ROOTS:
        for p in sorted(root.iterdir()):
            if not p.is_file():continue
            row=dict(path=str(p),size_bytes=p.stat().st_size,sha256_before=sha(p))
            if p.suffix.lower() in ('.jpg','.jpeg','.dng'):
                try:
                    with Image.open(p) as im:
                        e=im.getexif();x=e.get_ifd(34665)
                        # Deliberately whitelist; do not serialize MakerNotes, serials, GPS, comments.
                        row.update(dimensions=list(im.size),orientation=e.get(274,1),
                                   model=e.get(272,'').strip(),capture_time=x.get(36867,e.get(306,'')),
                                   modified_time=e.get(306,''),digitized_time=x.get(36868,''),
                                   software=e.get(305,'').strip(),paired_dng=p.with_suffix('.DNG').exists(),
                                   subsecond=x.get(37521,''))
                        for name,key in [('exposure_seconds',33434),('f_number',33437),('iso',34855)]:
                            if key in x:row[name]=float(x[key])
                except Exception as exc:row['metadata_read_error']=type(exc).__name__
            records.append(row)
    return records


def load(path,max_edge):
    with Image.open(path) as im:
        im=ImageOps.exif_transpose(im).convert('RGB')
        scale=min(1,max_edge/max(im.size))
        size=tuple(max(128,int(v*scale)//4*4) for v in im.size)
        if size!=im.size:im=im.resize(size,Image.Resampling.LANCZOS)
        return np.asarray(im).copy()


def save_image(path,array):
    # A new Image has no original EXIF. PNG is lossless for numerical comparisons.
    Image.fromarray(array).save(path)


def sheet(path,panels,title,note,columns=3,width=600):
    font=ImageFont.truetype(str(FONT_PATH),22) if FONT_PATH.exists() else ImageFont.load_default()
    small=ImageFont.truetype(str(FONT_PATH),16) if FONT_PATH.exists() else ImageFont.load_default()
    thumb_h=420
    canvas=Image.new('RGB',(columns*width,110+math.ceil(len(panels)/columns)*(thumb_h+45)),(24,25,27))
    draw=ImageDraw.Draw(canvas);draw.text((18,14),title,font=font,fill='white')
    draw.text((18,52),note,font=small,fill=(205,205,205))
    for i,(label,arr) in enumerate(panels):
        im=Image.fromarray(arr);im.thumbnail((width-24,thumb_h),Image.Resampling.LANCZOS)
        x=(i%columns)*width;y=100+(i//columns)*(thumb_h+45)
        draw.text((x+12,y),label,font=small,fill='white')
        canvas.paste(im,(x+(width-im.width)//2,y+30))
    canvas.save(path,quality=95,subsampling=0)


def translated(a,dx,dy):
    # Positive dx means content moves right in the simulated exposure.
    return np.stack([warp_plane(a[...,k],-dx,-dy)[0] for k in range(3)],axis=2).round().clip(0,255).astype(np.uint8)


def draw_subject(base,x):
    im=Image.fromarray(base.copy());d=ImageDraw.Draw(im)
    w,h=im.size;u=w/1200;cx=x*w;top=.51*h
    # Deterministic authored geometric figure, visibly synthetic, not a photograph of motion.
    d.ellipse((cx-21*u,top,cx+21*u,top+42*u),fill=(235,218,190))
    d.polygon([(cx-24*u,top+40*u),(cx+24*u,top+40*u),(cx+35*u,top+145*u),
               (cx-35*u,top+145*u)],fill=(225,225,225))
    d.line([(cx-17*u,top+140*u),(cx-32*u,top+220*u)],fill=(205,205,205),width=max(1,round(18*u)))
    d.line([(cx+17*u,top+140*u),(cx+42*u,top+213*u)],fill=(205,205,205),width=max(1,round(18*u)))
    d.line([(cx-25*u,top+65*u),(cx-55*u,top+112*u)],fill=(220,220,220),width=max(1,round(13*u)))
    d.line([(cx+25*u,top+65*u),(cx+60*u,top+92*u)],fill=(220,220,220),width=max(1,round(13*u)))
    return np.asarray(im).copy()


def serializable(result):return {k:v for k,v in result.items() if k not in ('output','literal')}


def render_case(out,name,frames,provenance,truth=None,oracle=False,static=False,factor=4):
    dest=out/name;dest.mkdir(exist_ok=True)
    # A rerun that rejects must not leave an earlier accepted result beside it.
    for filename in ('detail.png','literal.png','frame3-cropped.png','crop-100.jpg','motion-crop-100.jpg',
                     'oracle-detail.png','oracle-literal.png'):
        p=dest/filename
        if p.exists():p.unlink()
    for k,f in enumerate(frames):save_image(dest/f'frame{k+1}.png',f)
    planes=[reduce_plane(frames[k][...,k],factor) for k in range(2)]
    start=time.perf_counter();result=process(frames[2],planes,factor);seconds=time.perf_counter()-start
    record=dict(name=name,provenance=provenance,processing_dimensions=list(frames[2].shape[1::-1]),
                downsample=f'1/{factor} width AND height = 1/{factor*factor} area, BOX uint8',
                retained_channel_bytes=sum(a.nbytes for a in planes),desktop_seconds=seconds,
                source_exif_copied=False,**serializable(result))
    if truth is not None:
        record['known_source_mapping_full_pixels']=truth
        if len(result.get('alignment',[]))==2:
            record['shift_error_full_pixels']=[(np.array(r['shift'])*factor-np.array(t)).tolist()
                                              for r,t in zip(result['alignment'],truth)]
    panels=[(f'Exposure {k+1}: '+('R saved' if k==0 else 'G saved' if k==1 else 'B + detail'),f)
            for k,f in enumerate(frames)]
    compared=None
    if result['accepted']:
        detail=result['output'];literal=result['literal'];box=result['crop_xyxy']
        baseline=frames[2][box[1]:box[3],box[0]:box[2]]
        save_image(dest/'detail.png',detail);save_image(dest/'literal.png',literal)
        save_image(dest/'frame3-cropped.png',baseline)
        panels.extend([('Frame 3, same valid crop',baseline),('Literal R1-small / G2-small / B3',literal),
                       ('Frame 3 detail + temporal R/G delta',detail)])
        cy,cx=np.array(detail.shape[:2])//2
        crop=lambda x:x[max(0,cy-256):cy+256,max(0,cx-256):cx+256]
        # No resizing: 100% means this declared processing grid, not original sensor pixels.
        crops=[('Frame 3 / 100% processing pixels',crop(baseline)),('Literal / 100%',crop(literal)),
               ('Detail reconstruction / 100%',crop(detail))]
        sheet(dest/'crop-100.jpg',crops,name,'Native pixels of the declared processing grid; JPEG sheet only.',width=540)
        record['blue_exact']=bool(np.array_equal(detail[...,2],baseline[...,2]))
        record['detail_vs_frame3_mae']=float(np.abs(detail.astype(float)-baseline).mean())
        record['literal_vs_frame3_mae']=float(np.abs(literal.astype(float)-baseline).mean())
        error=np.abs(detail[...,:2].astype(float)-baseline[...,:2])
        record['rg_error_percentiles_50_90_95_99_99p9_100']=np.percentile(error,[50,90,95,99,99.9,100]).tolist()
        record['rg_fraction_error_above_8_DN']=float(np.mean(error>8))
        yy,xx,cc=np.unravel_index(np.argmax(error),error.shape)
        record['max_rg_error_location_processing_xy_channel']=[int(xx+box[0]),int(yy+box[1]),'RG'[cc]]
        if 'foreground' in name:
            w,h=frames[2].shape[1],frames[2].shape[0];u=w/1200
            cy=round(.51*h+100*u)
            samples=[]
            for x in (.28,.50,.72):
                cx=round(x*w);py=cy-box[1];px=cx-box[0]
                samples.append(dict(position=x,frame3_rgb=baseline[py,px].tolist(),detail_rgb=detail[py,px].tolist(),
                                    literal_rgb=literal[py,px].tolist()))
            record['torso_channel_samples']=samples
            motion_crop=lambda a:a[round(.51*h)-box[1]:round(.51*h+230*u)-box[1],
                                   round(.28*w-65*u)-box[0]:round(.72*w+65*u)-box[0]]
            sheet(dest/'motion-crop-100.jpg',[(label,motion_crop(a)) for label,a in
                   [('Frame 3',baseline),('Literal',literal),('Detail reconstruction',detail)]],name,
                  'Synthetic foreground at 100% of declared processing grid.',columns=3,width=1000)
        if static:
            record['static_detail_max_error']=int(np.max(np.abs(detail.astype(int)-baseline.astype(int))))
            record['static_literal_max_error']=int(np.max(np.abs(literal.astype(int)-baseline.astype(int))))
        compared=(baseline,literal,detail)
    elif oracle and truth is not None:
        # Controlled known transform only. This NEVER changes guarded rejection.
        detail,literal,cropinfo=reconstruct(frames[2],planes,[np.array(t)/factor for t in truth],[(1,0)]*2,factor)
        save_image(dest/'oracle-detail.png',detail);save_image(dest/'oracle-literal.png',literal)
        panels.extend([('Frame 3',frames[2]),('KNOWN synthetic shift only: literal',literal),
                       ('KNOWN synthetic shift only: detail',detail)])
        record['oracle_diagnostic']='Known synthetic shifts bypass rejection for visual diagnosis; not a guarded result'
        record['oracle_crop']=cropinfo
    else:
        # Preserve rejection. Show the known last exposure, no confident composite.
        panels.append(('REJECTED: '+result['reason'],frames[2]))
    sheet(dest/'comparison.jpg',panels,name,
          ('ACCEPTED' if result['accepted'] else 'REJECTED')+' | '+provenance['basis'],columns=3)
    record['output_sha256']={p.name:sha(p) for p in sorted(dest.iterdir()) if p.is_file() and p.name!='manifest.json'}
    write_json(dest/'manifest.json',record)
    return record,compared


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,default=Path('scratch/trichrome'))
    ap.add_argument('--max-edge',type=int,default=2400)
    args=ap.parse_args();out=args.out.resolve()
    if args.max_edge<512:raise ValueError('max-edge must be at least 512')
    for root in ROOTS:
        if out==root.resolve() or root.resolve() in out.parents:raise ValueError('Output inside read-only originals')
    out.mkdir(parents=True,exist_ok=True)
    inv=inventory();write_json(out/'inventory-before.json',inv)
    jpg=[r for r in inv if Path(r['path']).suffix.lower() in ('.jpg','.jpeg') and '-edited' not in r['path']]
    same_second={}
    for r in jpg:
        if r.get('capture_time'):same_second.setdefault(r['capture_time'],[]).append(r['path'])
    groups=[paths for paths in same_second.values() if len(paths)>=3]
    write_json(out/'sequence-provenance.json',dict(jpeg_count=len(jpg),same_second_groups=groups,
               finding='One five-file group shares capture time, but JPEGs52..55 have modification dates almost five hours later and no paired DNG: likely RAW developments, not proof of independent exposures',
               limitation='No independently verified three-exposure burst found; one-second capture metadata cannot authenticate burst membership'))
    real_paths=[ROOTS[0]/f'R{n:07}.JPG' for n in (51,52,53)]
    records=[];overview=[]
    rec,images=render_case(out,'01-real-same-second',[load(p,args.max_edge) for p in real_paths],
        dict(basis='REAL matching JPEG variants; likely RAW developments; NOT verified independent exposures',sources=[str(p) for p in real_paths],
             exposure='1/125 s, f/2.8, ISO 3200 for all three',motion='Little visible scene motion; primarily stability evidence'))
    records.append(rec)
    if images:overview.extend([('Real JPEG variants / frame 3',images[0]),('Real JPEG variants / trichrome',images[2])])
    # A real lake scene, frozen identically; motion later is deterministic synthesis.
    source=ROOTS[0]/'AK000079.JPG';base=load(source,args.max_edge)
    synth=dict(basis='CONTROLLED SYNTHESIS from one real still; no captured motion',sources=[str(source)])
    rec,images=render_case(out,'02-static-identity',[base.copy() for _ in range(3)],synth,truth=[(0,0)]*2,static=True)
    records.append(rec)
    if images:overview.extend([('Static / literal soft R,G',images[1]),('Static / exact detail restoration',images[2])])
    shifts=[(5.25,-3.5),(-2.5,4.75),(0,0)]
    rec,images=render_case(out,'03-static-handheld',[translated(base,*s) for s in shifts],
                         {**synth,'known_camera_shifts_full_pixels':shifts},truth=shifts[:2],oracle=True,static=True)
    records.append(rec)
    rec,images=render_case(out,'03b-static-handheld-factor2',[translated(base,*s) for s in shifts],
                         {**synth,'known_camera_shifts_full_pixels':shifts,'memory_tradeoff':'12,000,000 retained bytes at6000x4000, four times factor4'},
                         truth=shifts[:2],oracle=True,static=True,factor=2)
    records.append(rec)
    moving=[draw_subject(base,x) for x in (.28,.50,.72)]
    rec,images=render_case(out,'04-synthetic-moving-foreground',moving,
                         {**synth,'motion':'Authored geometric walking figure in three positions; background frozen'},truth=[(0,0)]*2,oracle=True)
    records.append(rec)
    if images:overview.extend([('Synthetic motion / frame 3',images[0]),('Synthetic motion / RGB ghosts',images[2])])
    # Radiometric changes deliberately remain global and modest; clipping not simulated here.
    radio=[np.clip(moving[k].astype(float)*g+b,0,255).round().astype(np.uint8)
           for k,(g,b) in enumerate([(1.08,3),(.94,4),(1,0)])]
    rec,_=render_case(out,'05-synthetic-exposure-drift',radio,
                     {**synth,'motion':'Same authored figure + frame1 gain 1.08/+3 DN; frame2 .94/+4 DN'},truth=[(0,0)]*2)
    records.append(rec)
    # Split scene into incompatible depth translations. A single global shift is insufficient.
    a=translated(base,20,0);b=translated(base,-20,0)
    a[:,:a.shape[1]//2]=b[:,:b.shape[1]//2]
    rec,_=render_case(out,'06-synthetic-parallax',[a,a.copy(),base],
        {**synth,'motion':'Left/right halves shifted by -20/+20 processing pixels; global translation is invalid'})
    records.append(rec)
    concert=[ROOTS[0]/f'AK{n:06}.JPG' for n in (90,91,92)]
    rec,_=render_case(out,'07-real-concert-difficult',[load(p,args.max_edge) for p in concert],
        dict(basis='REAL separate shots 2 seconds apart, NOT a burst; perspective and stage lights change',
             sources=[str(p) for p in concert],expected='May be correctly rejected by translation-only model'))
    records.append(rec)
    # Motion-dominant unrelated frame deliberately violates global registration.
    rng=np.random.default_rng(192)
    noise=rng.integers(0,256,base.shape,dtype=np.uint8)
    rec,_=render_case(out,'08-synthetic-motion-dominant',[noise,noise.copy(),base],
        {**synth,'motion':'Independent random foreground replaces the entire old frame; must reject'})
    records.append(rec)
    for row in inv:
        row['sha256_after']=sha(Path(row['path']))
        row['unchanged']=row['sha256_before']==row['sha256_after']
    unchanged=all(r['unchanged'] for r in inv)
    write_json(out/'originals-integrity.json',dict(all_unchanged=unchanged,count=len(inv),files=inv))
    if not unchanged:raise RuntimeError('Original hash mismatch')
    for p in (p for p in out.rglob('*') if p.suffix.lower() in ('.png','.jpg','.jpeg')):
        with Image.open(p) as im:
            if im.getexif():raise RuntimeError(f'Unexpected output EXIF: {p}')
    write_json(out/'summary.json',dict(cases=records,originals_unchanged=unchanged,original_count=len(inv),
                                     max_edge=args.max_edge,dependencies=dict(numpy=np.__version__,pillow=Image.__version__)))
    if overview:sheet(out/'overview.jpg',overview,'TRICHROME BURST / desktop evidence',
                      'Real JPEG variants + explicitly synthetic motion. No verified burst or hardware feasibility claim.',columns=2,width=700)
    links=[]
    for r in records:
        name=r['name'];links.append(f'<article><h2>{html.escape(name)}</h2><p>{html.escape(r["provenance"]["basis"])} — '
                  f'{"ACCEPTED" if r["accepted"] else "REJECTED"}: {html.escape(r["reason"])}</p>'
                  f'<a href="{name}/comparison.jpg"><img src="{name}/comparison.jpg" alt="Comparison sheet"></a>'
                  f'<p><a href="{name}/manifest.json">Numerical manifest</a> | '
                  +(f'<a href="{name}/crop-100.jpg">100% crop</a> | ' if r['accepted'] else '')
                  +(f'<a href="{name}/motion-crop-100.jpg">100% synthetic motion</a> | ' if 'foreground' in name else '')
                  +'</p></article>')
    (out/'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Trichrome evidence</title>'
       '<style>body{background:#18191b;color:#eee;font:16px system-ui;max-width:1500px;margin:40px auto;padding:0 20px}img{max-width:100%}a{color:#7dd8e9}article{margin:60px 0}</style>'
       '<h1>Trichrome burst — desktop prototype</h1><p>All original files SHA-256 unchanged. No source EXIF/GPS copied. '
       'Real matching JPEGs likely derive from one capture; no independently verified burst. Walking figure and known offsets are synthetic. '
       '100% crops refer to the declared processing resolution. Rejection produces no final composite.</p>'
       '<p><a href="sequence-provenance.json">Capture provenance</a> | <a href="originals-integrity.json">288-original hash audit</a>'
       ' | <a href="memory.json">Memory accounting and unresolved lifecycle</a> | <a href="summary.json">Full numerical results</a></p>'+''.join(links),encoding='utf-8')
    memory=[]
    for label,w,h in [('main',6000,4000),('screennail',720,480),('thumbnail',160,120)]:
        for factor in (4,2):
            sw,sh=w//factor,h//factor;aligned_stride=(sw+63)//64*64
            memory.append(dict(image=label,dimensions=[w,h],factor=factor,stored_dimensions=[sw,sh],
                               two_channel_bytes_packed=2*sw*sh,two_channel_bytes_64byte_rows=2*aligned_stride*sh,
                               existing_ycc422_bytes_packed=2*w*h))
    write_json(out/'memory.json',dict(tables=memory,
       persistent='Only R1/G2; no encoder-owned picture pointer retained. Three MB means packed factor4 planes only.',
       conservative_scratch_example_bytes=dict(reference_and_source_384x256_u8=196608,
            both_reference_channels1500x1000_u8=3000000,warp_and_delta_int16_full_plane=6000000),
       realistic_simple_native_peak='3,072,000 retained with64byte rows +3,000,000 referenceR3/G3 +196,608 alignment +~300,000 row workspace = ~6.6 MB; no claim this fits camera heap',
       stream_design='Full reference/warped planes can potentially become bounded row rings, but YCC channel interdependence needs original-row carry and byte-exact native proof. Not implemented.',
       limits='Desktop float RGB arrays and FFT workspace are much larger; desktop runtime is not camera feasibility. Cross-exposure ownership and synchronization remain unproven.'))
    print(json.dumps(dict(output=str(out),all_originals_unchanged=unchanged,cases=[dict(name=r['name'],accepted=r['accepted'],reason=r['reason']) for r in records]),indent=2))


if __name__=='__main__':main()
