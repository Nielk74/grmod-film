"""Offline trichrome spike. No firmware patch, camera timing, or ISP equivalence.

Keep R1/G2 as uint8 at one quarter width AND height (one sixteenth area).
All shifts map reference frame 3 coordinates into the earlier source plane.
"""
import math
import numpy as np
from PIL import Image


def reduce_plane(plane, factor=4):
    h, w = plane.shape
    if factor not in (2, 4) or w % factor or h % factor:
        raise ValueError('Dimensions must be divisible by factor 2 or 4')
    # Integer BOX, round half upward, deliberately defined for bit-exact identity.
    return ((plane.astype(np.uint32).reshape(h//factor,factor,w//factor,factor)
             .sum(axis=(1,3)) + factor*factor//2)//(factor*factor)).astype(np.uint8)


def sample(plane, x, y):
    h,w=plane.shape
    valid=(x>=0)&(x<=w-1)&(y>=0)&(y<=h-1)
    x=np.clip(x,0,w-1);y=np.clip(y,0,h-1)
    x0=x.astype(np.int32);y0=y.astype(np.int32)
    x1=np.minimum(x0+1,w-1);y1=np.minimum(y0+1,h-1)
    ax=x-x0;ay=y-y0
    value=((1-ax)*(1-ay)*plane[y0,x0]+ax*(1-ay)*plane[y0,x1]
           +(1-ax)*ay*plane[y1,x0]+ax*ay*plane[y1,x1])
    return value.astype(np.float32),valid


def warp_plane(plane, dx, dy):
    yy,xx=np.indices(plane.shape,dtype=np.float32)
    return sample(plane,xx+dx,yy+dy)


def _resize(plane, size):
    return np.asarray(Image.fromarray(np.asarray(plane,dtype=np.float32))
                      .resize(size,Image.Resampling.BILINEAR),dtype=np.float32)


def _ncc(a,b):
    a=a-a.mean();b=b-b.mean()
    return float(np.sum(a*b)/max(float(np.sqrt(np.sum(a*a)*np.sum(b*b))),1e-8))


def estimate_shift(source, reference, max_shift=24):
    """FFT seed plus nine independently fitted tiles, reject weak/nonrigid fits.

    Units are stored-plane pixels. max_shift is a *desktop policy*, not a camera
    shake envelope. Tiles are same-channel: no persistent luma plane is needed.
    """
    if source.shape!=reference.shape or min(source.shape)<48:
        return dict(accepted=False,reason='dimensions',shift=[0.,0.])
    h,w=source.shape
    if float(np.std(reference))<2 or float(np.std(source))<2:
        return dict(accepted=False,reason='insufficient texture',shift=[0.,0.])
    ratio=max(1.,max(h,w)/384)
    cw,ch=round(w/ratio),round(h/ratio)
    a=_resize(reference,(cw,ch));b=_resize(source,(cw,ch))
    window=np.outer(np.hanning(ch),np.hanning(cw))
    fa=np.fft.rfft2((a-a.mean())*window);fb=np.fft.rfft2((b-b.mean())*window)
    prod=fb*np.conj(fa);corr=np.fft.irfft2(prod/np.maximum(np.abs(prod),1e-7),s=a.shape)
    py,px=np.unravel_index(np.argmax(corr),corr.shape)
    sx=(px if px<=cw//2 else px-cw)*w/cw
    sy=(py if py<=ch//2 else py-ch)*h/ch
    if abs(sx)>max_shift or abs(sy)>max_shift:
        return dict(accepted=False,reason='shift exceeds policy',shift=[float(sx),float(sy)])
    # Each tile uses 24x24 actual samples; full plane storage is not duplicated.
    tiles=[];radius=max(2,int(math.ceil(ratio)))
    for cy in (.2,.5,.8):
        for cx in (.2,.5,.8):
            span=min(w,h)*.12
            yy,xx=np.meshgrid(np.linspace(cy*h-span,cy*h+span,24),
                              np.linspace(cx*w-span,cx*w+span,24),indexing='ij')
            ref,valid=sample(reference,xx,yy)
            if ref.std()<2: continue
            best=(-2.,0.,0.)
            for dy in range(round(sy)-radius,round(sy)+radius+1):
                for dx in range(round(sx)-radius,round(sx)+radius+1):
                    old,v=sample(source,xx+dx,yy+dy)
                    if not np.all(valid&v): continue
                    score=_ncc(ref,old)
                    if score>best[0]:best=(score,float(dx),float(dy))
            # Quarter stored-pixel refinement, then a second eighth-pixel pass.
            for step in (.25,.125):
                score,bx,by=best
                for dy in np.arange(by-step*3,by+step*3+.01,step):
                    for dx in np.arange(bx-step*3,bx+step*3+.01,step):
                        old,v=sample(source,xx+dx,yy+dy)
                        if np.all(v):
                            score=_ncc(ref,old)
                            if score>best[0]:best=(score,float(dx),float(dy))
            tiles.append(dict(score=best[0],shift=list(best[1:])))
    strong=[t for t in tiles if t['score']>=.85]
    if len(strong)<5:
        return dict(accepted=False,reason='fewer than five reliable tiles',shift=[sx,sy],tiles=tiles)
    offsets=np.array([t['shift'] for t in strong]);center=np.median(offsets,axis=0)
    distances=np.linalg.norm(offsets-center,axis=1)
    support=distances<=.55
    fraction=float(np.count_nonzero(support)/len(tiles))
    # Permit two moving/weak tiles among nine; 7/9 is 0.777..., not 0.78.
    accepted=fraction>=.75
    final=np.median(offsets[support],axis=0).tolist() if support.any() else center.tolist()
    return dict(accepted=accepted,reason='translation consensus' if accepted else 'parallax / moving / ambiguous tiles',
                shift=final,consensus_fraction=fraction,tiles=tiles,
                max_inlier_disagreement=float(distances[support].max()) if support.any() else None)


def fit_radiometry(source, reference, valid):
    """Robust affine DN normalization. Approximation for rendered JPEGs, not RAW.

    Requires >=60% of sampled nonclipped pixels to agree within 12 DN. Spatially
    varying illumination and clipping cannot be repaired by this model.
    """
    good=valid&(source>8)&(source<247)&(reference>8)&(reference<247)
    x=source[good][::max(1,np.count_nonzero(good)//50000)].astype(np.float64)
    y=reference[good][::max(1,np.count_nonzero(good)//50000)].astype(np.float64)
    if len(x)<64 or x.std()<2:
        return dict(accepted=False,reason='insufficient radiometric signal',affine=[1.,0.])
    keep=np.ones(x.shape,dtype=bool);gain,bias=1.,0.
    for _ in range(4):
        xx=x[keep];yy=y[keep];xm=xx.mean();ym=yy.mean()
        gain=float(np.sum((xx-xm)*(yy-ym))/max(float(np.sum((xx-xm)**2)),1e-8));bias=float(ym-gain*xm)
        error=np.abs(gain*x+bias-y)
        keep=error<=max(2.,float(np.percentile(error,70)))
    error=np.abs(gain*x+bias-y)
    support=float(np.mean(error<=12))
    accepted=.7<=gain<=1.4 and abs(bias)<=20 and support>=.6
    return dict(accepted=accepted,reason='robust affine fit' if accepted else 'exposure / WB / motion mismatch',
                affine=[gain,bias],support_fraction=support,p75_error=float(np.percentile(error,75)))


def reconstruct(frame3, planes, shifts, affine, factor=4):
    """Returns detail-preserved, literal low-res-channel comparator, crop report.

    out.R = R3 + U(aligned_normalized(R1small) - D(R3)); same for G.
    out.B = B3. High frequencies come from frame3 in all three channels.
    No motion mask blends RGB together, so low-frequency temporal ghosts survive.
    """
    h,w,_=frame3.shape
    out=frame3.astype(np.float32);literal=out.copy()
    for k in range(2):
        old,_=warp_plane(planes[k].astype(np.float32),*shifts[k])
        old=old*affine[k][0]+affine[k][1]
        reference=reduce_plane(frame3[...,k],factor).astype(np.float32)
        delta=_resize(old-reference,(w,h))
        out[...,k]+=delta
        literal[...,k]=_resize(old,(w,h))
    # Conservative border: source shift plus one stored sample for interpolation.
    # Zero motion is exact identity and needs no crop. No wrap-around/black filling.
    if any(abs(v)>1e-8 for shift in shifts for v in shift):
        dx=[s[0] for s in shifts];dy=[s[1] for s in shifts]
        left=math.ceil(max(0.,-min(dx))*factor)+factor
        top=math.ceil(max(0.,-min(dy))*factor)+factor
        right=w-math.ceil(max(0.,max(dx))*factor)-factor
        bottom=h-math.ceil(max(0.,max(dy))*factor)-factor
    else:left=top=0;right=w;bottom=h
    if right<=left or bottom<=top:raise ValueError('No common valid image remains')
    clipped=float(np.mean((out<0)|(out>255)))
    encode=lambda a:np.clip(np.floor(a+.5),0,255).astype(np.uint8)[top:bottom,left:right]
    return encode(out),encode(literal),dict(crop_xyxy=[left,top,right,bottom],
                retained_area_fraction=(right-left)*(bottom-top)/(w*h),preclip_sample_fraction=clipped)


def process(frame3, planes, factor=4):
    align=[];fits=[]
    for k in range(2):
        ref=reduce_plane(frame3[...,k],factor).astype(np.float32)
        alignment=estimate_shift(planes[k],ref);align.append(alignment)
        if not alignment['accepted']:
            return dict(accepted=False,reason=f'Channel {k}: '+alignment['reason'],alignment=align)
        shifted,valid=warp_plane(planes[k],*alignment['shift'])
        fit=fit_radiometry(shifted,ref,valid);fits.append(fit)
        if not fit['accepted']:
            return dict(accepted=False,reason=f'Channel {k}: '+fit['reason'],alignment=align,radiometry=fits)
    out,literal,crop=reconstruct(frame3,planes,[a['shift'] for a in align],[f['affine'] for f in fits],factor)
    return dict(accepted=True,reason='accepted by prototype guards',output=out,literal=literal,
                alignment=align,radiometry=fits,**crop)


class BurstBuffer:
    """Desktop state-machine sketch. Owns only uint8 R1/G2 between submissions.

    mode_key must include dimensions/orientation, exposure/WB/film settings,
    capture mode and a real burst generation ID in a future firmware adapter.
    timeout is a desktop test parameter; no camera burst cadence is assumed.
    """
    def __init__(self,factor=4,memory_limit=3_100_000,timeout=10.):
        if factor not in (2,4) or memory_limit<=0 or timeout<=0:
            raise ValueError('Invalid factor, memory budget or expiry')
        self.factor=factor;self.memory_limit=memory_limit;self.timeout=timeout;self.cancel()

    def cancel(self):
        self.planes=[];self.token=None;self.mode=None;self.shape=None;self.last_time=None

    @property
    def retained_bytes(self):return sum(x.nbytes for x in self.planes)

    def expire(self,now):
        """Caller must run this from its timer when no third frame arrives."""
        if self.last_time is not None and (now<self.last_time or now-self.last_time>self.timeout):
            self.cancel();return True
        return False

    def submit(self,frame,index,token,mode_key,now):
        try:
            if index==1:
                self.cancel();self.token=token;self.mode=mode_key;self.shape=frame.shape
            if frame.dtype!=np.uint8 or frame.ndim!=3 or frame.shape[2]!=3:
                raise ValueError('Expected uint8 RGB')
            if token!=self.token or mode_key!=self.mode or frame.shape!=self.shape:
                raise ValueError('Changed burst or capture configuration')
            if self.expire(now):
                raise ValueError('Expired burst')
            if index!=len(self.planes)+1 or index not in (1,2,3):raise ValueError('Out-of-order burst')
            needed=2*(frame.shape[0]//self.factor)*(frame.shape[1]//self.factor)
            if needed>self.memory_limit:raise MemoryError('Persistent plane budget exceeded')
            if index<3:
                self.planes.append(reduce_plane(frame[...,index-1],self.factor));self.last_time=now
                return None
            try:return process(frame,self.planes,self.factor)
            finally:self.cancel()
        except Exception:
            self.cancel();raise
