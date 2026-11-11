"""Offline face-local finishing. This is not a firmware implementation.

Coordinates are always in the EXIF-transposed, uncropped image. YuNet is a
desktop stand-in for the camera detector. Skin is a broad colour heuristic,
not semantic segmentation. No person/skin identity inference is performed.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.append(str(Path(__file__).resolve().parents[1] / 'jpeg_experiments'))
from color_ops import _to_lab

LUMA = np.array([.2126, .7152, .0722], np.float32)


def smooth(lo, hi, x):
    t = np.clip((x - lo) / (hi - lo), 0, 1)
    return t * t * (3 - 2 * t)


def srgb_to_linear(rgb):
    rgb = np.asarray(rgb, np.float32)
    return np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)


def linear_to_srgb(rgb):
    rgb = np.maximum(rgb, 0)
    return np.where(rgb <= .0031308, rgb * 12.92, 1.055 * rgb ** (1 / 2.4) - .055)


def validate(rgb, mask=None):
    if rgb.ndim != 3 or rgb.shape[-1] != 3 or not np.isfinite(rgb).all() or rgb.min() < 0 or rgb.max() > 1:
        raise ValueError('Expected finite HxWx3 sRGB within [0,1]')
    if mask is not None and (mask.shape != rgb.shape[:2] or not np.isfinite(mask).all() or mask.min() < 0 or mask.max() > 1):
        raise ValueError('Mask must match image and be finite within [0,1]')


def skin_probability(rgb):
    """Broad OkLab orange/red gate; permits darker and low-chroma warm skin.

    The hue plateau deliberately avoids an ethnicity-specific exposure cutoff.
    Warm clothes/wood within a false face box can still pass this heuristic.
    """
    lab = _to_lab(rgb)
    chroma = np.hypot(lab[...,1], lab[...,2])
    hue = np.rad2deg(np.arctan2(lab[...,2], lab[...,1]))
    return (smooth(8, 24, hue) * (1 - smooth(78, 100, hue))
            * smooth(.005,.018,chroma) * (1 - smooth(.19,.28,chroma))
            * smooth(.04,.16,lab[...,0])).astype(np.float32)


def face_mask(rgb, faces):
    validate(rgb)
    h,w = rgb.shape[:2]
    gate = skin_probability(rgb)
    combined = np.zeros((h,w), np.float32)
    for face in faces:
        x,y,bw,bh = face['box']
        if not np.isfinite([x,y,bw,bh]).all() or bw <= 0 or bh <= 0:
            raise ValueError('Face box must have finite positive dimensions')
        # Oval includes jaw/forehead, stops before clothes. Full-strength core
        # and C1 falloff. Combined by max so duplicate/overlap never stacks EV.
        yy,xx = np.ogrid[:h,:w]
        radius = np.sqrt(((xx-(x+bw*.5))/(bw*.57))**2 + ((yy-(y+bh*.5))/(bh*.59))**2)
        oval = 1-smooth(.64,1,radius)
        local = gate.copy()
        # Spatial smoothing bridges tiny pores and avoids colour-boundary
        # speckles. Multiplication by the oval after smoothing prevents spill.
        sigma = max(.6,min(bw,bh)*.013)
        local = cv2.GaussianBlur(local,(0,0),sigmaX=sigma)
        local *= oval
        # Dark hair/frames get little weight from colour; broad smoothing
        # can still lift edges. Eye/lip artifacts are a review limitation.
        np.maximum(combined,local,out=combined)
    return np.clip(combined,0,1).astype(np.float32)


def fill_light(rgb, mask, ev=.85):
    validate(rgb,mask)
    if not math.isfinite(ev) or not 0 <= ev <= 1.5:
        raise ValueError('ev must be finite in [0,1.5]')
    out = rgb.copy()
    if not np.any(mask) or ev == 0:
        return out
    # Strips bound transient allocation; linear here means decoded display
    # sRGB, not raw sensor light. It cannot recover crushed/clipped JPEG data.
    for start in range(0,len(rgb),64):
        sl = slice(start,start+64)
        lin = srgb_to_linear(rgb[sl])
        peak = lin.max(-1)
        headroom = 1-smooth(.45,.90,peak)
        gain = 2 ** (ev * mask[sl] * headroom)
        gain = np.minimum(gain, .999999/np.maximum(peak,1e-8))
        gain = np.maximum(1,gain)
        changed = linear_to_srgb(lin * gain[...,None])
        out[sl] = np.where((gain>1)[...,None],changed,rgb[sl])
    return np.clip(out,0,1)


def skin_keeper(original, film, mask, amount=.85):
    """Reference-assisted target: original chromaticity at film luminance.

    Requires both pre-film RGB and the full-strength film render. This is NOT
    claimed realizable from only the final camera JPEG. A post-film blind
    heuristic would need film-specific calibration and cannot recover clipping.
    """
    validate(original,mask);validate(film)
    if film.shape != original.shape or not math.isfinite(amount) or not 0 <= amount <= 1:
        raise ValueError('Matching original/film images and amount [0,1] required')
    out = film.copy()
    for start in range(0,len(original),64):
        sl = slice(start,start+64)
        src, graded = srgb_to_linear(original[sl]),srgb_to_linear(film[sl])
        target_y = graded @ LUMA
        ref = src * (target_y / np.maximum(src @ LUMA,1e-8))[...,None]
        # Contract excess gamut around luminance anchor, preserving Y.
        delta = ref-target_y[...,None]
        bound = np.maximum(np.maximum(delta,0)/np.maximum(1-target_y[...,None],1e-8),
                           np.maximum(-delta,0)/np.maximum(target_y[...,None],1e-8)).max(-1)
        ref = target_y[...,None] + delta / np.maximum(bound,1)[...,None]
        blend = mask[sl] * amount
        kept = graded + blend[...,None] * (ref-graded)
        out[sl] = np.where((blend>0)[...,None],linear_to_srgb(kept),film[sl])
    return np.clip(out,0,1)


def blind_keeper(film, mask, amount=.30):
    """One-input saturation contraction at constant display-linear luminance.

    Can reduce orange intensity, cannot correct a film's hue rotation or
    infer pre-film colour. Uniform amount needs per-film/camera calibration.
    """
    validate(film,mask)
    if not math.isfinite(amount) or not 0 <= amount <= 1:
        raise ValueError('amount must be in [0,1]')
    out=film.copy()
    for start in range(0,len(film),64):
        sl=slice(start,start+64)
        lin=srgb_to_linear(film[sl]);y=lin@LUMA
        blend=mask[sl]*amount
        changed=linear_to_srgb(lin+blend[...,None]*(y[...,None]-lin))
        out[sl]=np.where((blend>0)[...,None],changed,film[sl])
    return np.clip(out,0,1)


def map_face(row, detector_size, image_size, scale):
    sx,sy = image_size[0]/detector_size[0],image_size[1]/detector_size[1]
    return {'box':[float(row[0]*sx),float(row[1]*sy),float(row[2]*sx),float(row[3]*sy)],
            'landmarks':[[float(row[i]*sx),float(row[i+1]*sy)] for i in range(4,14,2)],
            'score':float(row[14]),'scale':scale}


def iou(a,b):
    ax,ay,aw,ah=a;bx,by,bw,bh=b
    inter=max(0,min(ax+aw,bx+bw)-max(ax,bx))*max(0,min(ay+ah,by+bh)-max(ay,by))
    return inter/max(aw*ah+bw*bh-inter,1e-8)


def merge_detections(candidates, threshold=.82, minimum_scales=2):
    remaining=sorted(candidates,key=lambda f:-f['score'])
    accepted,rejected=[],[]
    while remaining:
        best=remaining.pop(0)
        group=[best]+[c for c in remaining if iou(c['box'],best['box'])>.4]
        remaining=[c for c in remaining if iou(c['box'],best['box'])<=.4]
        scales=sorted({c['scale'] for c in group if c['score']>=threshold})
        merged=dict(best,support_scales=scales,candidate_count=len(group))
        if len(scales)>=minimum_scales:
            accepted.append(merged)
        else:
            rejected.append(merged)
    return accepted,rejected


def detect(image, model, scales=(320,640,960,1600)):
    candidates=[]
    for scale in scales:
        small=image.copy();small.thumbnail((scale,scale))
        detector=cv2.FaceDetectorYN.create(str(model),'',small.size,.80,.3,5000)
        _,faces=detector.detect(cv2.cvtColor(np.asarray(small),cv2.COLOR_RGB2BGR))
        if faces is not None:
            candidates.extend(map_face(row,small.size,image.size,scale) for row in faces)
    accepted,rejected=merge_detections(candidates)
    return {'accepted':accepted,'rejected':rejected,'candidates':candidates,
            'scales':list(scales),'candidate_threshold':.80,'consensus_threshold':.82,'minimum_scales':2}
