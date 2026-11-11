"""Full6000x4000 integer-reference evidence from one real photo + authored motion.

No captured burst, image upload, generative editing, or EXIF copying. Native ARM
parity is independently checked on smaller fixtures by check.py/check_camera.py.
"""
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np
from PIL import Image, ImageDraw, ImageOps

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];OUT=ROOT/'scratch/trichrome-firmware/visual'
SOURCE=Path('C:/Users/Antoine/Pictures/Ricoh/AK000079.JPG')
sys.path.insert(0,str(ROOT/'tools/trichrome'))
from run import draw_subject


def ycc(rgb):
    h,w,_=rgb.shape;y=np.empty((h,w),np.uint8);c=np.empty_like(y)
    for row in range(0,h,64):
        a=rgb[row:row+64].astype(np.int32);r,g,b=a.transpose(2,0,1)
        y[row:row+64]=np.clip((77*r+150*g+29*b+128)>>8,0,255)
        cb=np.clip(((-43*r-85*g+128*b+128)>>8)+128,0,255)
        cr=np.clip(((128*r-107*g-21*b+128)>>8)+128,0,255)
        c[row:row+64,::2]=((cb[:,::2]+cb[:,1::2]+1)>>1).astype(np.uint8)
        c[row:row+64,1::2]=((cr[:,::2]+cr[:,1::2]+1)>>1).astype(np.uint8)
    return y,c


def rgb(y,c):
    h,w=y.shape;out=np.empty((h,w,3),np.uint8)
    for row in range(0,h,64):
        a=y[row:row+64].astype(np.int32);p=c[row:row+64].astype(np.int32)-128
        cb=np.repeat(p[:,::2],2,axis=1);cr=np.repeat(p[:,1::2],2,axis=1)
        out[row:row+64]=np.stack([np.clip(a+((359*cr+128)>>8),0,255),
            np.clip(a-((88*cb+183*cr+128)>>8),0,255),np.clip(a+((454*cb+128)>>8),0,255)],axis=2)
    return out


def reduce(pair):
    y,c=pair;h,w=y.shape;red=np.empty((h//4,w//4),np.int32);green=np.empty_like(red)
    for row in range(0,h,64):
        a=y[row:row+64].astype(np.int32);p=c[row:row+64].astype(np.int32)-128
        cb=np.repeat(p[:,::2],2,axis=1);cr=np.repeat(p[:,1::2],2,axis=1)
        r=np.clip(a+((359*cr+128)>>8),0,255);g=np.clip(a-((88*cb+183*cr+128)>>8),0,255)
        for dest,v in [(red,r),(green,g)]:dest[row//4:(row+len(a))//4]=(v.reshape(len(a)//4,4,w//4,4).sum(axis=(1,3))+8)>>4
    return red,green


def reference(frames):
    y,c=frames[2];h,w=y.shape;r,_=reduce(frames[0]);_,g=reduce(frames[1]);r3,g3=reduce(frames[2])
    dr=r-r3;dg=g-g3;oy=y.copy();oc=c.copy()
    xx=np.arange(w)[None,:];sx=2*xx+1-4;x0=sx//8;tx=sx%8;x1=np.clip(x0+1,0,w//4-1);x0=np.clip(x0,0,w//4-1)
    for row in range(0,h,64):
        yy=np.arange(row,min(row+64,h))[:,None];sy=2*yy+1-4;y0=sy//8;ty=sy%8
        y1=np.clip(y0+1,0,h//4-1);y0=np.clip(y0,0,h//4-1)
        def up(d):return (d[y0,x0]*(8-tx)*(8-ty)+d[y0,x1]*tx*(8-ty)+d[y1,x0]*(8-tx)*ty+d[y1,x1]*tx*ty+32)>>6
        a=up(dr);b=up(dg);sr=a[:,::2]+a[:,1::2];sg=b[:,::2]+b[:,1::2]
        oy[row:row+64]=np.clip(y[row:row+64].astype(np.int32)+((77*a+150*b+128)>>8),0,255)
        oc[row:row+64,::2]=np.clip(c[row:row+64,::2].astype(np.int32)+((-43*sr-85*sg+256)>>9),0,255)
        oc[row:row+64,1::2]=np.clip(c[row:row+64,1::2].astype(np.int32)+((128*sr-107*sg+256)>>9),0,255)
    return oy,oc


def main():
    OUT.mkdir(parents=True,exist_ok=True);before=hashlib.sha256(SOURCE.read_bytes()).hexdigest();started=time.perf_counter()
    with Image.open(SOURCE) as im:
        display=np.asarray(ImageOps.exif_transpose(im).convert('RGB')).copy()
    # Original has storage6000x4000 and orientation6. Author in display space,
    # rotate back for processing; output previews rotate only after composition.
    frames=[ycc(np.rot90(draw_subject(display,p),1).copy()) for p in [.28,.5,.72]]
    assert frames[0][0].shape==(4000,6000)
    result=reference(frames);static=reference([frames[2]]*3)
    assert all(np.array_equal(a,b) for a,b in zip(static,frames[2]))
    pictures=[np.rot90(rgb(*f),-1).copy() for f in frames]
    composite=np.rot90(rgb(*result),-1).copy()
    labels=['Frame1: retain reducedR','Frame2: retain reducedG','Frame3: current YCbCr422','Composite: R1/G2 delta + frame3 detail']
    panels=pictures+[composite];sheet=Image.new('RGB',(1600,680),(22,24,29));d=ImageDraw.Draw(sheet)
    d.text((20,12),'TRICHROME NATIVE INTEGER REFERENCE | full storage6000x4000',fill='white')
    d.text((20,32),'CONTROLLED SYNTHESIS from one real still. Authored figure; no captured burst or hardware output.',fill='white')
    for i,(label,a) in enumerate(zip(labels,panels)):
        p=Image.fromarray(a);p.thumbnail((380,1200));x=12+i*400;d.text((x,62),label,fill='white');sheet.paste(p,(x,88))
    sheet.save(OUT/'native-reference-comparison.jpg',quality=94)
    # Native100% crop includes all three positions in the synthetic subject row.
    h,w=composite.shape[:2];box=(int(.21*w),int(.51*h),int(.79*w),int(.51*h)+800)
    crop=Image.new('RGB',(box[2]-box[0],1640),(22,24,29));cd=ImageDraw.Draw(crop)
    for k,(label,a) in enumerate([('Frame3 |100% source pixels',pictures[2]),('Native integer composite |100%',composite)]):
        cd.text((10,k*820+4),label,fill='white');crop.paste(Image.fromarray(a).crop(box),(0,k*820+20))
    crop.save(OUT/'native-reference-motion100.jpg',quality=96)
    Image.fromarray(composite).save(OUT/'native-reference-full.png')
    Image.fromarray(pictures[2]).save(OUT/'frame3-full.png')
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==before
    paths=sorted(OUT.glob('*.jpg'))+sorted(OUT.glob('*.png'))
    assert all(not Image.open(p).getexif() for p in paths)
    report=dict(provenance='Controlled authored figure over one real still. No independently captured motion.',source=str(SOURCE),
        source_sha256_before=before,source_sha256_after=before,native_storage_dimensions=[6000,4000],display_dimensions=[4000,6000],
        algorithm='Integer BT601-full-range YCbCr422 proxy, quarter-width/height BOX R1/G2, center-aligned bilinear temporal deltas. Exact static YCbCr identity.',
        full_resolution_static_identity=True,arm_parity_scope='Exact independent ARM parity separately at small fixtures; this full-resolution render is Python integer reference.',
        seconds_desktop_only=time.perf_counter()-started,hardware_tested=False,
        outputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (OUT/'manifest.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
