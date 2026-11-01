"""Focused visible experiments; genuine Standard fits and paired camera JPEGs.

Run with the jpeg-experiments-env interpreter, after film_pipeline_v2.ts.
Outputs are explicitly 1800px display comparisons, not full-resolution masters.
"""
from __future__ import annotations
import argparse
import hashlib
import html
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps
from color_ops import apply_lut
from perceptual_v2 import measure, fixed_masks, normal_view
from raw_ops import decode_raw
from raw_crop_v2 import crop_raw_to_camera_frame
from raw_tone_v2 import render_film_tone, render_reference_standard
from spatial_v2 import local_contrast, bloom, vignette, local_range

DEFAULT = Path('C:/Users/Antoine/Pictures/GRMod-JPEG-Experiments-v2-2026-10-31')
PICTURES = Path('C:/Users/Antoine/Pictures')
FONT = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 21)
SMALL = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 16)

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()

def load(path):
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert('RGB')
        im.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
        return np.asarray(im, dtype=np.float32) / 255

def picture(a):
    return Image.fromarray(np.round(np.clip(a, 0, 1) * 255).astype(np.uint8))

def save(path, a):
    path.parent.mkdir(parents=True, exist_ok=True)
    picture(a).save(path, compress_level=3)

def sheet(path, panels, columns=3):
    width, height = 520, 420
    rows = (len(panels) + columns - 1) // columns
    out = Image.new('RGB', (width * columns, height * rows), '#11151a')
    draw = ImageDraw.Draw(out)
    for i, (label, image, detail) in enumerate(panels):
        x, y = (i % columns) * width, (i // columns) * height
        im = picture(image)
        im.thumbnail((width-16, height-70), Image.Resampling.LANCZOS)
        out.paste(im, (x+(width-im.width)//2, y+48+(height-70-im.height)//2))
        draw.text((x+12, y+6), label, font=FONT, fill='white')
        draw.text((x+12, y+height-23), detail, font=SMALL, fill='#b9c7d9')
    path.parent.mkdir(parents=True, exist_ok=True)
    out.save(path, quality=95, subsampling=0)

class Run:
    def __init__(self, root):
        self.root = root
        self.data = json.loads((root/'models/models.json').read_text(encoding='utf-8'))
        self.models = {m['id']: m for m in self.data['models']}
        self.grids = {}
        self.sections = []
        self.sources = {}
        self.yardsticks = {}

    def source(self, path):
        key = str(path)
        if key not in self.sources:
            self.sources[key] = {'path': key, 'sha256_before': sha(path)}

    def film(self, rgb, identifier, kind='native'):
        key = (identifier, kind)
        if key not in self.grids:
            m = self.models[identifier]
            self.grids[key] = np.fromfile(self.root/'models'/m[kind], dtype='<f4').reshape(33, 33, 33, 3)
        return apply_lut(rgb, self.grids[key])

    def section(self, folder, title, description):
        s = {'folder': folder, 'title': title, 'description': description, 'results': []}
        self.sections.append(s)
        (self.root/folder).mkdir(parents=True, exist_ok=True)
        return s

    def pair(self, section, name, before, after, basis, target='all', **extra):
        folder = Path(section['folder'])/name
        save(self.root/folder/'before.png', before)
        save(self.root/folder/'after.png', after)
        metrics = measure(before, after)
        record = {'id': name, 'before': (folder/'before.png').as_posix(),
                  'after': (folder/'after.png').as_posix(), 'basis': basis,
                  'display_size': list(picture(before).size), 'metrics': metrics,
                  'target_region': target, **extra}
        if target != 'all':
            record['visibility_gate'] = bool((metrics['regions'][target]['mean_de00'] or 0) >= 3)
        section['results'].append(record)
        print(section['folder'], name, 'mean dE', round(metrics['regions']['all']['mean_de00'],2),
              target, round(metrics['regions'][target]['mean_de00'] or 0,2), flush=True)
        return record

    def run(self):
        standards = {}
        for name in ['R0000022', 'R0000023']:
            path = PICTURES/'Ricoh'/f'{name}.JPG'
            self.source(path)
            standards[name] = load(path)
        s = self.section('01-film-yardstick', 'The yardstick: actual GR Mod films',
                         'Before: your documented Standard JPEG. After: the existing film colour transform converted by Engine against official GR III 2.10 and evaluated with the stored Q13 matrix, 256-point curves and Q9 post matrix. This reference holds clarity, grain and neutral user controls fixed; it does not reproduce the complete recipe or physical ISP.')
        for name, rgb in standards.items():
            panels = [('Camera Standard', rgb, name)]
            for film in ['classic-chrome', 'astia', 'classic-neg']:
                base = self.film(rgb, film+'-base-0')
                rec = self.pair(s, f'{name}-{film}', rgb, base, 'Documented camera Standard → existing fitted '+film)
                self.yardsticks[(name, film)] = rec['metrics']['regions']['all']['mean_de00']
                panels.append((film, base, f"mean dE00 {self.yardsticks[(name,film)]:.2f}"))
            sheet(self.root/s['folder']/f'{name}-films.jpg', panels, 4)

        for kind, folder, title in [('hue','03-film-hue','Stronger hue separation inside the films'),
                                     ('density','04-film-density','Colour density as a film extra')]:
            s = self.section(folder, title,
                'Before: existing fitted film. Every after is a newly authored film target converted through the same actual Engine fit and quantization. Sweep includes deliberately excessive strength 2.5. Fixed chromatic masks come from the before film at 900px. The requested target and residual fitting error are shown separately.')
            for name, rgb in standards.items():
                for film in ['classic-chrome', 'astia', 'classic-neg']:
                    base = self.film(rgb, film+'-base-0')
                    basetarget = self.film(rgb, film+'-base-0','target')
                    masks = fixed_masks(normal_view(base))
                    panels = [('Original '+film, base, 'strength 0')]
                    sweep = []
                    for strength in ([] if sweep else [50,100,175,250]):
                        identifier = f'{film}-{kind}-{strength}'
                        rendered = self.film(rgb, identifier)
                        intended = self.film(rgb, identifier, 'target')
                        m = measure(base, rendered, masks)
                        requested = measure(basetarget, intended, masks)
                        residual = measure(intended, rendered, masks)
                        value = m['regions']['colour']['mean_de00']
                        item = {'strength': strength/100, 'model': identifier, 'metrics': m,
                                'requested_effect': requested, 'target_fit_residual': residual,
                                'target_visibility_ge3': bool((value or 0) >= 3),
                                'share_of_film_yardstick': m['regions']['all']['mean_de00']/self.yardsticks[(name,film)]}
                        sweep.append(item)
                        panels.append((f'Strength {strength/100:g}', rendered, f'colour dE {value:.2f}; whole {m["regions"]["all"]["mean_de00"]:.2f}'))
                    sweep_path = f'{folder}/{name}-{film}-sweep.jpg'
                    if len(panels)>1:
                        sheet(self.root/sweep_path, panels)
                    write_json(self.root/folder/f'{name}-{film}-sweep.json', sweep)
                    # Main comparisons are deliberately limited to two films.
                    if film == 'astia':
                        continue
                    selected = 100
                    item = next(v for v in sweep if v['strength'] == selected/100)
                    after = self.film(rgb, f'{film}-{kind}-{selected}')
                    target_img = self.film(rgb, f'{film}-{kind}-{selected}', 'target')
                    rec = self.pair(s, f'{name}-{film}', base, after,
                        f'{film}: existing fitted film → refitted {kind} strength {selected/100:g}', 'colour',
                        model=f'{film}-{kind}-{selected}', strength=selected/100,
                        sweep=sweep_path, sweep_data=f'{folder}/{name}-{film}-sweep.json',
                        requested_effect=item['requested_effect'], target_fit_residual=item['target_fit_residual'],
                        share_of_film_yardstick=item['share_of_film_yardstick'])
                    target_path = f'{folder}/{name}-{film}/requested-target.png'
                    save(self.root/target_path, target_img)
                    rec['requested_target'] = target_path

        s = self.section('05-raw-tones', 'Film-style RAW curves versus the camera JPEG',
            'Before is the camera JPEG of the same frame. After uses recorded camera WB, a fixed scene-linear decode, exposure multiplier 1, and an explicit film-style curve. No automatic brightness or exposure matching. The DNG DefaultCrop and LibRaw orientation match the camera field of view before display resizing. This is appearance comparison, not registered colour accuracy; lens rendering and demosaicing differ. These designed RAW curves are not the existing GR Mod film profiles.')
        for area, name, style, chosen in [('Ricoh2','AK000011','negative',1),
                                          ('Ricoh2','AK000025','contrast',.8),
                                          ('Ricoh','R0000001','fade',.8)]:
            dng, jpg = PICTURES/area/(name+'.DNG'), PICTURES/area/(name+'.JPG')
            self.source(dng); self.source(jpg)
            scene, decode = decode_raw(dng)
            before = load(jpg)
            th, tw = before.shape[:2]
            scene, crop = crop_raw_to_camera_frame(scene, dng)
            scene = np.stack([np.asarray(Image.fromarray(scene[...,c]).resize((tw,th),Image.Resampling.LANCZOS)) for c in range(3)],-1).clip(0,None)
            after = render_film_tone(scene, style=style, exposure=1, strength=chosen)
            reference=render_reference_standard(scene)
            reference_path=f'05-raw-tones/{name}/ordinary-raw-reference.png'
            save(self.root/reference_path,reference)
            panels = [('Camera JPEG', before, 'honest baseline'),
                      ('Ordinary S-curve RAW', reference, 'diagnostic only; not the baseline')]
            for strength in [.5,1,2]:
                panels.append((f'{style} {strength:g}', render_film_tone(scene,style=style,strength=strength), 'fixed WB and exposure 1'))
            sweep_path = f'{s["folder"]}/{name}-sweep.jpg'
            sheet(self.root/sweep_path,panels)
            self.pair(s,name,before,after,f'Paired camera JPEG → RAW {style} curve strength {chosen:g}, exposure 1',
                      style=style,strength=chosen,exposure=1,sweep=sweep_path,
                      decode=decode,raw_camera_crop=crop, metric_interpretation='appearance difference; not registered colour accuracy')
            s['results'][-1].update(raw_reference=reference_path,tone_only_metrics=measure(reference,after))
            del scene

        operations = [('06-local-contrast','Coarse local contrast',local_contrast,'all',2),
                      ('07-bloom','Broad highlight bloom',bloom,'highlights_and_surround',.5),
                      ('08-vignette','Visible peripheral falloff',vignette,'corners',.6),
                      ('09-local-range','Broad local dynamic-range treatment',local_range,'all',1)]
        for folder,title,op,region,chosen in operations:
            s = self.section(folder,title,
                'Before: the fitted Classic Chrome colour transform, with clarity and grain fixed. After: a spatial processing prototype applied to that film. Native-equivalent Gaussian sigmas are 20/50px for local contrast, 60px for bloom and 80px for local range, on a 6000px-long frame. Vignette is a whole-frame radial falloff. These are offline prototypes; only broad contrast has an approximate route through the current clarity bands. Sweeps reach strength 3 to expose the failure range.')
            for name,rgb in standards.items():
                base = self.film(rgb,'classic-chrome-base-0')
                masks = fixed_masks(normal_view(base))
                panels = [('Classic Chrome',base,'strength 0')]
                sweep=[]
                for strength in [.5,1,2,3]:
                    kwargs={} if op is vignette else {'frame_width':max(base.shape[:2])}
                    after = op(base,strength=strength,**kwargs)
                    m=measure(base,after,masks)
                    sweep.append({'strength':strength,'metrics':m})
                    panels.append((f'Strength {strength:g}',after,f'{region} dE {m["regions"][region]["mean_de00"]:.2f}'))
                sweep_path=f'{folder}/{name}-sweep.jpg'
                sheet(self.root/sweep_path,panels)
                write_json(self.root/folder/f'{name}-sweep.json',sweep)
                amount=(1 if name=='R0000022' else .5) if op is bloom else chosen
                kwargs={} if op is vignette else {'frame_width':max(base.shape[:2])}
                after=op(base,strength=amount,**kwargs)
                self.pair(s,name,base,after,f'Fitted Classic Chrome → {op.__name__} strength {amount:g}',region,
                          strength=amount,sweep=sweep_path,spatial=True,
                          parameters={'native_reference_longside':6000,'processing_longside':max(base.shape[:2]),
                                      'gaussian_sigmas_native_px':{'local_contrast':[20,50],'bloom':[60],'vignette':[],'local_range':[80]}[op.__name__],
                                      'corner_falloff_ev':amount if op is vignette else None},
                          share_of_film_yardstick=measure(base,after)['regions']['all']['mean_de00']/self.yardsticks[(name,'classic-chrome')])

        s=self.section('10-combinations','A combined film candidate',
            'Hue 1 and density 0.6 are authored together inside Classic Chrome and refitted as one film. Broad contrast and vignette can then follow as offline spatial processing. Compare each with the unmodified fitted colour transform. The stage sheet exposes each contribution. The combined colour candidate uses the existing matrix/curve path; its spatial extension is not camera-ready.')
        for name,rgb in standards.items():
            base=self.film(rgb,'classic-chrome-base-0')
            hue=self.film(rgb,'classic-chrome-hue-100')
            combined=self.film(rgb,'classic-chrome-combined-100')
            self.pair(s,name+'-colour',base,combined,'Classic Chrome colour transform → jointly refitted hue 1 + density .6',
                      stages={'hue':1,'density':.6},model='classic-chrome-combined-100')
            contrast=local_contrast(combined,strength=.7,frame_width=max(combined.shape[:2]))
            after=vignette(contrast,strength=.45)
            panels=[('Original Classic Chrome',base,'before'),('Refitted hue 1',hue,'first stage'),
                    ('Refitted hue + density .6',combined,'jointly fitted colour candidate'),
                    ('Plus coarse contrast .7',contrast,'offline spatial stage'),('Plus vignette .45',after,'combined candidate')]
            sweep=f'10-combinations/{name}-stages.jpg'
            sheet(self.root/sweep,panels,3)
            self.pair(s,name+'-spatial',base,after,'Classic Chrome colour transform → jointly refitted hue 1 + density .6 + offline local contrast .7 + vignette .45',
                      sweep=sweep,stages={'hue':1,'density':.6,'local_contrast':.7,'vignette':.45},
                      parameters={'native_reference_longside':6000,'processing_longside':max(base.shape[:2]),
                                  'local_contrast_sigmas_native_px':[20,50],'vignette_corner_falloff_ev':.45})

        for entry in self.sources.values():
            entry['sha256_after']=sha(Path(entry['path']))
            entry['unchanged']=entry['sha256_after']==entry['sha256_before']
            if not entry['unchanged']:
                raise RuntimeError('Original source hash changed: '+entry['path'])
        summary={'display_longside':1800,'metrics_longside':900,'sources':list(self.sources.values()),
                 'firmware':self.data['firmware'],'sections':self.sections,
                 'colour_reference':'Fitted colour coefficients only; recipe clarity/grain and nonneutral user controls are excluded.',
                 'scope':'Two views of the same outdoor scene for film colour/spatial tests, plus three distinct paired RAW scenes. Faces in the Standard inputs are too small for skin validation.',
                 'metrics_basis':'Floating display arrays before 8-bit PNG export. Verification independently checks the exported colour PNGs.',
                 'yardsticks':[{'photo':n,'film':f,'whole_mean_de00':v} for (n,f),v in self.yardsticks.items()],
                 'gate':'Mean target deltaE00 >=3 is a visibility engineering gate, not a quality score or universal detection threshold.',
                 'interpretation':'A large change can be ugly; fit error and effect size are distinct. Visual verdicts are recorded after inspection.'}
        for section in self.sections:
            write_json(self.root/section['folder']/'manifest.json',section)
        write_json(self.root/'summary.json',summary)
        gallery(self.root,summary)

def gallery(root,summary):
    e=html.escape
    nav=[]; blocks=[]
    for section in summary['sections']:
        nav.append(f'<a href="#{section["folder"]}">{e(section["title"])}</a>')
        cards=[]
        for record in section['results']:
            m=record['metrics']; region=record['target_region']; target=m['regions'][region]
            links=[]
            for field,label in [('sweep','Strength sweep / stages'),('requested_target','Requested target'),('sweep_data','Sweep measurements'),('raw_reference','Ordinary RAW S-curve')]:
                if record.get(field): links.append(f'<a href="{record[field]}">{label}</a>')
            fit=''
            if record.get('target_fit_residual'):
                err=record['target_fit_residual']['regions']['all']['mean_de00']
                req=record['requested_effect']['regions']['colour']['mean_de00']
                fit=f' · requested colour effect {req:.2f} · remaining target/fit error {err:.2f}'
            if record.get('tone_only_metrics'):
                fit+=f' · tone-only change from ordinary RAW curve {record["tone_only_metrics"]["regions"]["all"]["mean_de00"]:.2f}'
            cards.append(f'''<article tabindex="0"><h3>{e(record['id'])}</h3><p>{e(record['basis'])}</p>
<div class="viewer" style="--ratio:{record['display_size'][0]}/{record['display_size'][1]}"><img class="before" loading="lazy" src="{record['before']}" alt="Before {e(record['id'])}"><img class="after" loading="lazy" src="{record['after']}" alt="After {e(record['id'])}"><span class="state">AFTER</span></div>
<div class="buttons"><button data-mode="before">Before (A)</button><button data-mode="after">After (B)</button><button data-mode="blink">Blink (space)</button><a href="{record['before']}">Before PNG</a><a href="{record['after']}">After PNG</a>{' '.join(links)}</div>
<p class="stats">Whole-image ΔE00 {m['regions']['all']['mean_de00']:.2f} · target {e(region)} ΔE00 {target['mean_de00']:.2f} · mask coverage {target['coverage']*100:.1f}% · target pixels ≥3: {target['fraction_ge3']*100:.1f}% · mean RGB change {m['mean_absolute_rgb_255']:.2f}/255{fit}</p><p class="note">{e(record.get('verdict','Inspect the sweep; no automatic quality verdict.'))}</p></article>''')
        blocks.append(f'<section id="{section["folder"]}"><h2>{e(section["title"])}</h2><p>{e(section["description"])}</p><a href="{section["folder"]}/manifest.json">Exact parameters and measurements</a>{"".join(cards)}</section>')
    document='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GR Mod — visible processing experiments v2</title>
<style>:root{color-scheme:dark;font:16px Segoe UI,Arial;background:#11151a;color:#e6eaf1}*{box-sizing:border-box}body{margin:0}main,header{max-width:1500px;margin:auto;padding:28px}h1{font-size:40px;letter-spacing:-1px}h2{font-size:29px}p{line-height:1.6;color:#b9c6d6;max-width:1100px}a{color:#a6cff2}nav,.buttons{display:flex;flex-wrap:wrap;gap:14px;align-items:center}nav a{padding:9px;background:#263341;border-radius:5px}section{border-top:1px solid #3b4857;margin-top:45px;padding-top:20px}article{margin:28px 0 45px;padding:20px;background:#1a222b;border:1px solid #3b4857;border-radius:8px}h3{margin:0}.viewer{position:relative;width:100%;aspect-ratio:var(--ratio);max-height:82vh;background:#090b0d}.viewer img{position:absolute;width:100%;height:100%;object-fit:contain}.viewer img.before{visibility:hidden}.state{position:absolute;top:12px;left:12px;padding:7px 12px;background:#111b;letter-spacing:2px;font-size:12px}.buttons{margin:16px 0}button{font:inherit;padding:9px 16px;background:#314459;color:white;border:1px solid #6b829b;border-radius:5px;cursor:pointer}.stats{font-size:14px}.note{border-left:3px solid #9abac7;padding:10px 18px;background:#202d39}#verdicts{white-space:pre-wrap}@media(max-width:650px){main,header{padding:14px}h1{font-size:30px}article{padding:10px}.viewer{max-height:75vh}}</style>
<header><p>GR Mod processing lab · revised 31 October 2026</p><h1>Visible changes, honest baselines.</h1><p>Show each whole photograph at a comfortable viewing size. Click Before / After to flick between them; space toggles the focused comparison, A selects before and B selects after. Every idea includes a strength sweep through an exaggerated endpoint.</p><p class="note">1800px display images · metrics at 900px long side · original photos untouched. ΔE measures change, not beauty. The colour comparisons use genuine Standard inputs and actual fitted firmware coefficients; spatial and RAW branches remain offline prototypes. <a href="summary.json">Run manifest</a></p><nav>NAV</nav><p><a href="02-native-hue-research/report.txt">GR III native multi-axis findings</a> · <a href="05-raw-tones/native-tone-controls.txt">Native tone-control evidence</a> · <a href="findings.txt">Visual judgements and limitations</a></p></header><main>BLOCKS</main>
<script>let active=null;function show(card,mode){const before=card.dataset.before==='1';const next=mode==='blink'?!before:mode==='before';card.dataset.before=next?'1':'0';card.querySelector('.before').style.visibility=next?'visible':'hidden';card.querySelector('.after').style.visibility=next?'hidden':'visible';card.querySelector('.state').textContent=next?'BEFORE':'AFTER';active=card}document.querySelectorAll('article').forEach(card=>{card.addEventListener('focusin',()=>active=card);card.addEventListener('mouseenter',()=>active=card);card.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>show(card,b.dataset.mode)))});document.addEventListener('keydown',event=>{if(!active)return;let mode={a:'before',b:'after',' ':'blink'}[event.key.toLowerCase()];if(mode){event.preventDefault();show(active,mode)}});</script></html>'''
    (root/'index.html').write_text(document.replace('NAV',''.join(nav)).replace('BLOCKS',''.join(blocks)),encoding='utf-8')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=DEFAULT)
    Run(parser.parse_args().output).run()
