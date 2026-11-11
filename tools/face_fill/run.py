"""Local reproducible face-fill experiment. Originals stay read only."""
from __future__ import annotations
import argparse
import io
import json
import sys
import time
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageCms,ImageDraw,ImageFont,ImageOps
from audit import SOURCES,metadata,output_safe,sha,write_json
from face_fill import detect,face_mask,fill_light,skin_keeper,blind_keeper,srgb_to_linear,LUMA
from color_ops import apply_lut

ROOT=Path(__file__).resolve().parents[2]
SRGB=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB'))
MODEL_SHA='8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4'
DEFAULT_SELECTION=['Ricoh/R0000030.JPG','Ricoh/R0000005.JPG','Ricoh/AK000164.JPG',
                   'Ricoh/AK000075.JPG','Ricoh/R0000043.JPG','Ricoh2/AK000001.JPG']


def font(size):
    return ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',size)


def open_rgb(path,max_side=0):
    with Image.open(path) as src:
        im=ImageOps.exif_transpose(src).convert('RGB')
        if src.info.get('icc_profile'):
            im=ImageCms.profileToProfile(im,ImageCms.ImageCmsProfile(io.BytesIO(src.info['icc_profile'])),SRGB,outputMode='RGB')
        if max_side:im.thumbnail((max_side,max_side),Image.Resampling.LANCZOS)
        return im.copy()


def image(rgb):
    return Image.fromarray(np.rint(np.clip(rgb,0,1)*255).astype(np.uint8))


def save(im,path):
    output_safe(path);path.parent.mkdir(parents=True,exist_ok=True)
    # Do not propagate source EXIF/GPS/serials. All sides use identical encoding.
    im.save(path,quality=97,subsampling=0,icc_profile=SRGB.tobytes())


def strip(images,labels,width=550,height=850):
    out=Image.new('RGB',(width*len(images),height+62),(19,22,28));d=ImageDraw.Draw(out)
    for i,(im,label) in enumerate(zip(images,labels)):
        thumb=im.copy();thumb.thumbnail((width-8,height),Image.Resampling.LANCZOS)
        out.paste(thumb,(i*width+(width-thumb.width)//2,62+(height-thumb.height)//2))
        d.text((i*width+10,8),label,font=font(19),fill='white')
    return out


def overlay(im,mask,detection):
    rgb=np.asarray(im,np.float32)/255
    tinted=image(rgb*(1-mask[...,None]*.40)+np.array([0,1,1])*mask[...,None]*.40)
    d=ImageDraw.Draw(tinted)
    for status,color in [('accepted','lime'),('rejected','orange')]:
        for f in detection[status]:
            x,y,w,h=f['box'];d.rectangle((x,y,x+w,y+h),outline=color,width=max(3,im.width//500))
            d.text((max(x,0),max(0,y-30)),f"{f['score']:.3f} / {len(f['support_scales'])} scales",font=font(max(14,im.width//120)),fill=color)
    return tinted


def detector_scales(im,detection):
    views=[];labels=[]
    for scale in detection['scales']:
        view=im.copy();d=ImageDraw.Draw(view)
        candidates=[f for f in detection['candidates'] if f['scale']==scale]
        for f in candidates:
            x,y,w,h=f['box'];d.rectangle((x,y,x+w,y+h),outline='orange',width=max(3,im.width//400))
        views.append(view);labels.append(f'{scale}px raw: {len(candidates)} candidates')
    return strip(views,labels,400,600)


def metrics(before,after,mask):
    evs=[];outside_max=0.;changed=0;newclips=0
    for start in range(0,len(before),64):
        sl=slice(start,start+64);a=before[sl];b=after[sl];m=mask[sl]
        ya,yb=srgb_to_linear(a)@LUMA,srgb_to_linear(b)@LUMA
        active=(m>.65)&(ya>1e-6)
        if active.any():evs.extend(np.log2(np.maximum(yb[active],1e-8)/ya[active]).tolist())
        if (m==0).any():outside_max=max(outside_max,float(np.abs(a-b)[m==0].max()))
        changed+=int((np.max(np.abs(a-b),axis=-1)>1/255).sum())
        newclips+=int(((b.max(-1)>=1)&(a.max(-1)<1)).sum())
    return {'median_ev_core':float(np.median(evs)) if evs else None,
            'p10_ev_core':float(np.percentile(evs,10)) if evs else None,
            'core_pixels':len(evs),'changed_over_1_code_pixels':changed,
            'outside_mask_max_abs':outside_max,'new_float_clip_pixels':newclips,
            'mask_nonzero_fraction':float((mask>0).mean())}


def one(relative,output,model,films,max_side):
    root_name,filename=relative.split('/')
    root=next(r for r in SOURCES if r.name==root_name);src=root/filename
    before_hash=sha(src);meta=metadata(src);im=open_rgb(src,max_side)
    detection=detect(im,model)
    rgb=np.asarray(im,np.float32)/255
    small=im.copy();small.thumbnail((1600,1600),Image.Resampling.LANCZOS)
    sx,sy=small.width/im.width,small.height/im.height
    small_faces=[dict(f,box=[f['box'][0]*sx,f['box'][1]*sy,f['box'][2]*sx,f['box'][3]*sy]) for f in detection['accepted']]
    mask=cv2.resize(face_mask(np.asarray(small,np.float32)/255,small_faces),im.size,interpolation=cv2.INTER_LINEAR)
    # Reapply exact oval support after interpolation so outside stays exact.
    mask=np.clip(mask,0,1)
    outdir=output/(root_name+'-'+src.stem);outdir.mkdir(parents=True,exist_ok=True)
    fill=fill_light(rgb,mask);filled=image(fill)
    save(im,outdir/'original.jpg');save(filled,outdir/'fill.jpg')
    mask_im=Image.fromarray(np.rint(mask*255).astype(np.uint8))
    mask_im.save(outdir/'mask.png')
    over=overlay(im,mask,detection);save(over,outdir/'mask-overlay.jpg')
    save(detector_scales(im,detection),outdir/'detector-scale-failures.jpg')
    if detection['accepted']:
        x,y,w,h=detection['accepted'][0]['box'];cx,cy=x+w*.5,y+h*.5
    else:cx,cy=im.width*.5,im.height*.5
    edge=min(768,im.width,im.height)
    x=max(0,min(im.width-edge,round(cx-edge*.5)));y=max(0,min(im.height-edge,round(cy-edge*.5)))
    crop=(x,y,x+edge,y+edge)
    save(strip([im,filled,over],['Original JPEG','Fill +0.85 EV maximum','Mask / accepted / rejected']),outdir/'fill-sheet.jpg')
    save(strip([v.crop(crop) for v in [im,filled,over]],['Original 100%','Fill 100%','Mask 100%'],edge,edge),outdir/'fill-crop-100.jpg')
    film_records=[];gold_images=None
    for film in films:
        lut=np.fromfile(output/'models'/film['file'],dtype='<f4').reshape((33,33,33,3))
        graded=apply_lut(rgb,lut)
        # Realistic one-input gate is measured on final graded pixels.
        film_small=image(graded);film_small.thumbnail((1600,1600),Image.Resampling.LANCZOS)
        blind_mask=cv2.resize(face_mask(np.asarray(film_small,np.float32)/255,small_faces),im.size,interpolation=cv2.INTER_LINEAR)
        blind=blind_keeper(graded,blind_mask,.30)
        reference=skin_keeper(rgb,graded,mask,.85)
        ims=[im,image(graded),image(blind),image(reference)]
        slug=Path(film['file']).stem
        for label,img in zip(['full','blind','reference'],ims[1:]):save(img,outdir/(slug+'-'+label+'.jpg'))
        labels=['Original camera JPEG',film['name']+' full target','One-input keeper 30%','Reference upper bound 85%']
        save(strip(ims,labels),outdir/(slug+'-sheet.jpg'))
        save(strip([v.crop(crop) for v in ims],labels,edge,edge),outdir/(slug+'-crop-100.jpg'))
        save(overlay(image(graded),blind_mask,detection),outdir/(slug+'-blind-mask.jpg'))
        film_records.append({'film':film, 'blind':metrics(graded,blind,blind_mask),'reference':metrics(graded,reference,mask)})
        if film['name']=='Gold 200':gold_images=[im,filled,ims[1],ims[2],ims[3]]
    after_hash=sha(src)
    if before_hash!=after_hash:raise RuntimeError('Original changed')
    params={'source':str(src),'source_sha256_before':before_hash,'source_sha256_after':after_hash,
            'metadata':meta,'oriented_render_size':list(im.size),'max_side':max_side,
            'coordinates':'EXIF-transposed uncropped image; face XYWH mapped independently on x/y from each detector input',
            'detector':detection,'model_sha256':sha(model),'fill':{'maximum_ev':.85,**metrics(rgb,fill,mask)},
            'crop_xyxy':list(crop),'crop_scale':'1 output pixel to 1 rendered pixel; native only when max_side=0',
            'films':film_records,'no_exif_copied':True}
    write_json(outdir/'manifest.json',params)
    print(src.stem,'accepted',len(detection['accepted']),'rejected',len(detection['rejected']),'core EV',params['fill']['median_ev_core'],flush=True)
    return params,strip(gold_images,['Original','Fill','Gold full','Blind keeper','Reference upper bound'],430,645)


def metadata_sheets(output):
    records=json.loads((output/'metadata-audit.json').read_text(encoding='utf-8'))['records']
    thumbs=[];labels=[]
    for record in records:
        f=record['face_tags'].get('0x040b',{})
        if not f.get('count_a',0) and not f.get('count_b',0):continue
        root=next(r for r in SOURCES if r.name==record['folder'])
        with Image.open(root/record['file']) as src:
            raw=src.convert('RGB');d=ImageDraw.Draw(raw)
            for area in f['nonzero_area_slots']:
                x,y,w,h=area['xywh']
                d.rectangle((x,y,x+w,y+h),outline='lime',width=22)
            # Draw in encoded coordinates, then use original EXIF orientation.
            raw.getexif()[274]=record['orientation'];oriented=ImageOps.exif_transpose(raw)
        thumbs.append(oriented);labels.append(record['file']+f" header {f['count_a']}/{f['count_b']}; {len(f['nonzero_area_slots'])} boxes")
    rows=[strip(thumbs[i:i+5],labels[i:i+5],360,540) for i in range(0,len(thumbs),5)]
    sheet=Image.new('RGB',(1800,sum(r.height for r in rows)),(19,22,28));y=0
    for row in rows:sheet.paste(row,(0,y));y+=row.height
    save(sheet,output/'metadata-populated-boxes.jpg')


def verify(output):
    records=json.loads((output/'summary.json').read_text(encoding='utf-8'))['records']
    checks=0
    for r in records:
        if sha(Path(r['source']))!=r['source_sha256_before']:raise AssertionError('Source changed')
        folder=output/(Path(r['source']).parent.name+'-'+Path(r['source']).stem)
        for path in folder.glob('*.jpg'):
            with Image.open(path) as im:
                im.load()
                if im.getexif():raise AssertionError('EXIF copied')
                if not im.info.get('icc_profile'):raise AssertionError('Missing sRGB profile')
                checks+=1
        assert r['fill']['outside_mask_max_abs']==0
        assert r['fill']['new_float_clip_pixels']==0
        for film in r['films']:
            assert film['blind']['outside_mask_max_abs']==0
            assert film['reference']['outside_mask_max_abs']==0
    print('Verified source hashes, no copied EXIF, sRGB profiles, no outside-mask changes/new fill clipping;',checks,'JPEGs')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,default=ROOT/'scratch/face-fill')
    ap.add_argument('--max-side',type=int,default=0);ap.add_argument('--only',nargs='*');ap.add_argument('--verify',action='store_true')
    a=ap.parse_args();output=output_safe(a.output)
    if a.verify:verify(output);return
    model=output/'models/yunet.onnx'
    if sha(model)!=MODEL_SHA:raise ValueError('Unexpected model SHA')
    films=json.loads((output/'models/films.json').read_text(encoding='utf-8'))
    records=[];rows=[]
    for relative in a.only or DEFAULT_SELECTION:
        r,sheet=one(relative,output,model,films,a.max_side);records.append(r);rows.append(sheet)
    combined=Image.new('RGB',(max(r.width for r in rows),sum(r.height for r in rows)),(19,22,28));y=0
    for row in rows:combined.paste(row,(0,y));y+=row.height
    save(combined,output/'portrait-comparison.jpg')
    write_json(output/'summary.json',{'model':{'name':'OpenCV YuNet 2023mar','sha256':MODEL_SHA,
              'url':'https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet','license':'MIT'},'records':records})
    if (output/'metadata-audit.json').exists():metadata_sheets(output)
    verify(output)


if __name__=='__main__':main()
