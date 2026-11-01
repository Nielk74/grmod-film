"""Record choices made after viewing the sweeps; refresh export-based metrics.

Run after v2_compare.py. Deliberately keeps rejected/borderline ideas visible.
"""
from pathlib import Path
import json
import shutil
import sys
import numpy as np
from PIL import Image
from v2_compare import DEFAULT, gallery, save, write_json, sheet
from perceptual_v2 import measure
from spatial_v2 import local_contrast, bloom, vignette, local_range
from raw_ops import decode_raw
from raw_crop_v2 import crop_raw_to_camera_frame
from raw_tone_v2 import render_reference_standard

def load(path):
    return np.asarray(Image.open(path).convert('RGB'),dtype=np.float32)/255

VERDICTS={
 '01-film-yardstick':'Calibration reference. This measures the existing film colour transform; recipe grain and clarity are excluded. Astia is close to Standard on this scene, so use Classic Chrome/Neg as the stronger yardsticks.',
 '03-film-hue':'Keep as a visible creative film variant at strength 1 for Classic Chrome/Neg. Sky shifts toward teal, foliage toward olive. Strength 2.5 is rejected as a default because it pushes the sky green and foliage brown. Astia is better around 0.5. Skin is unvalidated.',
 '04-film-density':'Keep as an optional film extra at strength 1. Sky and blue clothing deepen without the same hue shift. Higher strengths make sky/denim inky and dark foliage loses separation; do not enable high density by default.',
 '05-raw-tones':'This is a visibly different RAW rendering, not proof of a generally better JPEG. The camera-versus-RAW difference also includes camera colour processing, WB interpretation and geometry; the separate tone-only metric isolates the designed curve relative to the ordinary RAW S-curve.',
 '06-local-contrast':'Borderline rather than a default recommendation. Strength 2 makes the building and people visibly more pronounced, especially in R0000023, but adds harsh architecture and deeper dark edges. Strength 1 was weaker; strength 3 looks overprocessed. The whole-image mean in R0000022 remains below 3.',
 '07-bloom':'Subject-dependent extra. Strength 0.5 on R0000023 softens the bright building and adds visible glow; strength 1 is already too washed out there. R0000022 tolerates 1. Higher strengths erase useful building contrast. No optical HDF equivalence is claimed.',
 '08-vignette':'Keep as an optional peripheral falloff at 0.6 corner EV. The stronger 2–3EV endpoints are intrusive. Native Image Control Shading is already supported by film recipes; its direction, radial profile and EV per step have not been calibrated to this offline example.',
 '09-local-range':'Conditional. Strength 1 visibly lifts dark areas and lowers bright areas, but reduces the existing film contrast. Above 1, the building scene becomes washed out. Native HDR Tone/Shadow Correction may offer related treatments; equivalence is untested.',
 '10-combinations':'Prefer the jointly refitted hue 1 + density 0.6 colour candidate. The spatial extension is shown for comparison; extra contrast/vignette does not automatically improve the colour candidate and should remain optional.'}

def main(root=DEFAULT):
    summary=json.loads((root/'summary.json').read_text(encoding='utf-8'))
    refresh='--metadata-only' not in sys.argv
    for section in summary['sections']:
        folder=section['folder']
        for record in section['results']:
            before=load(root/record['before'])
            if refresh and folder in ['06-local-contrast','07-bloom','08-vignette']:
                if folder=='06-local-contrast': op,amount=local_contrast,2
                elif folder=='07-bloom': op,amount=bloom,(1 if record['id']=='R0000022' else .5)
                else: op,amount=vignette,.6
                kwargs={} if op is vignette else {'frame_width':max(before.shape[:2])}
                save(root/record['after'],op(before,strength=amount,**kwargs))
                record.update(strength=amount,basis=f'Fitted Classic Chrome colour transform → {op.__name__} strength {amount:g}')
                record['parameters']['corner_falloff_ev']=amount if op is vignette else None
            if refresh and folder=='05-raw-tones':
                dng=Path(record['decode']['source_path'])
                scene,_=decode_raw(dng)
                scene,_=crop_raw_to_camera_frame(scene,dng)
                h,w=before.shape[:2]
                scene=np.stack([np.asarray(Image.fromarray(scene[...,c]).resize((w,h),Image.Resampling.LANCZOS)) for c in range(3)],-1).clip(0,None)
                reference=render_reference_standard(scene)
                reference_path=f'{folder}/{record["id"]}/ordinary-raw-reference.png'
                save(root/reference_path,reference)
                record['raw_reference']=reference_path
                record['tone_only_metrics']=measure(load(root/reference_path),load(root/record['after']))
                del scene
            if refresh: record['metrics']=measure(before,load(root/record['after']))
            record['verdict']=VERDICTS[folder]
            if folder=='10-combinations' and record['id'].endswith('-spatial'):
                record['parameters']={'native_reference_longside':6000,'processing_longside':max(before.shape[:2]),
                                      'local_contrast_sigmas_native_px':[20,50],'vignette_corner_falloff_ev':.45}
            region=record['target_region']
            if region!='all':record['visibility_gate']=(record['metrics']['regions'][region]['mean_de00'] or 0)>=3
        section['verdict']=VERDICTS[folder]
        if folder=='08-vignette' and 'Native Image Control Shading already provides' not in section['description']:
            section['description']+=' Native Image Control Shading already provides a recipe approximation route; the offline EV profile has not been calibrated to its steps.'
        if folder=='09-local-range':
            if 'Existing native HDR Tone' not in section['description']:
                section['description']+=' Existing native HDR Tone and Shadow Correction are possible related routes, without a measured match.'
            supplemental=root/folder/'R0000001-raw-fade/supplemental.json'
            if not supplemental.exists():
                base_path=root/'05-raw-tones/R0000001/after.png'
                destination=supplemental.parent
                destination.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(base_path,destination/'before.png')
                before=load(base_path)
                panels=[('RAW fade .8',before,'exact before PNG')]
                for strength in [.5,1,2,3]:
                    after=local_range(before,strength=strength,frame_width=max(before.shape[:2]))
                    panels.append((f'Local range {strength:g}',after,'80px native sigma'))
                save(destination/'after.png',local_range(before,strength=1,frame_width=max(before.shape[:2])))
                sheet(destination/'sweep.jpg',panels,5)
                record={'id':'R0000001-raw-fade','before':f'{folder}/R0000001-raw-fade/before.png',
                        'after':f'{folder}/R0000001-raw-fade/after.png','sweep':f'{folder}/R0000001-raw-fade/sweep.jpg',
                        'basis':'Designed RAW fade .8 → local range 1; supplemental film-style RAW branch, not a calibrated GR Mod colour profile',
                        'display_size':[before.shape[1],before.shape[0]],'target_region':'all','strength':1,
                        'metrics':measure(before,load(destination/'after.png')),
                        'parameters':{'native_reference_longside':6000,'radius_native_px':80,'processing_longside':max(before.shape[:2])}}
                write_json(supplemental,record)
            if supplemental.exists():
                record=json.loads(supplemental.read_text(encoding='utf-8'))
                record['verdict']='Useful scene-specific local-range treatment at strength 1: the face and room shadows open while the window darkens. Strengths 2–3 become grey and flat. This supplements the fitted-film tests using the designed RAW fade branch; no skin-colour accuracy or native ISP equivalence is established.'
                # Supplemental schema is written by the reviewing subagent.
                section['results']=[r for r in section['results'] if r['id']!='R0000001-raw-fade']
                section['results'].append(record)
        write_json(root/folder/'manifest.json',section)
    summary['metrics_basis']='Main comparison metrics are recomputed from decoded exported 8-bit PNGs at 900px. Authored-target and sweep diagnostics retain floating pre-export metrics.'
    summary['native_routes']={'hue':'Independent blocks pack correctly, but ISP sector semantics remain unverified. No native hue port or GR IV block copy.',
        'tone':'Custom RGB curves are supported. Native Image Control highlight/shadow sliders are not D-Range correction; tested curves retain zero black.',
        'local_contrast':'Clarity middle/coarse bands offer an approximate route, without a measured match to the log-luma prototype.',
        'vignette':'Native Image Control Shading defaults -4..4 already available; radial profile and EV mapping uncalibrated.',
        'local_range':'Native HDR Tone / Shadow Correction may be related; no pixel-level equivalence verified.',
        'bloom':'Offline thresholded bloom; no new camera implementation or optical HDF match claimed.'}
    summary['scope']='Two outdoor Standard views of the same scene for fitted colour/spatial tests, three paired RAW scenes, and a supplemental local-range test on the RAW portrait when present. Skin hue robustness remains unvalidated.'
    write_json(root/'summary.json',summary)
    gallery(root,summary)
    findings='''Revised judgement, 31 October 2026

The first pass was too weak and used misleading baselines. The v2 results are intentionally judged separately for visible size of change, aesthetic preference and camera feasibility.

Keep first: stronger per-hue film targets through the existing fit, optional density inside the film, and their jointly fitted combination. These make visible palette changes at normal size. They are creative GR Mod variants, not measured Fujifilm reproductions.

Conditional extras: modest vignette and restrained bloom, selected after viewing the excessive endpoints. Broad local range can help a dark subject but flattens the building scene. Coarse local contrast is visibly stronger at 2, with a harsh/HDR-like cost; it is not a default recommendation.

RAW: the before is always the paired camera JPEG. Three explicit designed film-style curves use fixed recorded WB and exposure multiplier 1. Camera-versus-RAW deltaE is appearance difference, not rendering accuracy. The separate ordinary RAW reference isolates the curve contribution. The roof DNG has a real digital crop; that crop and portrait orientation are now applied correctly. No JPEG highlight recovery is attempted.

Native hue: all factory GR III/IIIx entries share Standard's multi-axis descriptor. Actual ARM execution proves separate per-film records and all 540 packed coefficients. The coefficient block is not established as GR IV's 12x5 semantics. No native sector port is claimed; hardware characterization remains required. See 02-native-hue-research/report.txt.

Native tone: 72 actual ARM slider cases preserve black=0; the shadow slider cannot by itself make the lifted black endpoints of the authored fade curve. Custom per-channel curves offer that route. These are Image Control sliders, not automatic D-Range Correction. See 05-raw-tones/native-tone-controls.txt.

The limited Standard set is two views of one scene. It validates visible sky/foliage/stone changes here, not skin or broad photographic reliability. Existing film clarity/grain are excluded from the colour reference. Software coefficient evaluation and ARM function probes do not establish physical ISP/JPEG output.

Online primary sources checked:
Fujifilm X100VI manual describes separate film simulation, Color Chrome, tone, dynamic-range and clarity controls. The descriptions motivate separate tone/palette/spatial experiments; they do not disclose algorithms that these prototypes reproduce.
https://app.fujifilm-dsc.com/en/manual/x100vi/menu_shooting/image_quality_setting/
Ricoh's GR III/IIIx specifications distinguish Image Control Shading/HDR Tone, D-Range Highlight/Shadow Correction and RAW development. Existing camera controls should be calibrated before proposing entirely new camera processing.
https://www.ricoh-imaging.co.jp/english/products/gr-3/spec/
Ricoh's FAQ describes D-Range Correction and notes that stronger Shadow Correction can make noise more noticeable.
https://www.ricoh-imaging.co.jp/english/support/qa/gr-3/index.html

Native calibration remaining (no hardware result claimed): fixed tripod/raw+JPEG scene; constant manual exposure/WB and film, bracket only Image Control Shading, then clarity coarse gains, then D-Range correction separately. Keep a neutral control repeated between extremes. D-Range Auto may change capture behaviour; log ISO/exposure and reject unmatched captures as a curve-only comparison. Compare each capture's own RAW against its JPEG. This protocol has not been executed on a physical camera in this session.
'''
    (root/'findings.txt').write_text(findings,encoding='utf-8')
    color=next(s for s in summary['sections'] if s['folder']=='10-combinations')['results']
    example=next(r for r in color if r['id']=='R0000023-colour')
    sheet(root/'selected-colour-before-after.jpg',[
        ('Before: fitted Classic Chrome',load(root/example['before']),'existing colour transform'),
        ('After: jointly fitted hue + density',load(root/example['after']),'hue 1 + density .6 through Engine')],2)
    for section in summary['sections']:
        (root/section['folder']/'judgement.txt').write_text(VERDICTS[section['folder']]+'\n',encoding='utf-8')
    print('Curated',sum(len(s['results']) for s in summary['sections']),
          'comparisons; exported PNG metrics '+('refreshed.' if refresh else 'retained; metadata updated.'))

if __name__=='__main__':main()
