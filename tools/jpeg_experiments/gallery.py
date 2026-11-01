"""Write a self-contained local gallery; no remote assets or photo uploads."""
from __future__ import annotations

import html
import json
from pathlib import Path
from urllib.parse import quote


def write_gallery(output: Path, experiments: list[dict], summary: dict) -> None:
    e = html.escape
    findings_path = output / "findings.json"
    findings = json.loads(findings_path.read_text(encoding="utf-8")) if findings_path.exists() else {}
    links, sections = [], []
    for experiment in experiments:
        slug, title = experiment["folder"], experiment["title"]
        links.append(f'<a href="#{e(slug)}">{e(title)}</a>')
        cards = []
        for index, result in enumerate(experiment["results"]):
            before, after = quote(result["before_preview"]), quote(result["after_preview"])
            full_before, full_after = quote(result["before"]), quote(result["after"])
            width, height = result["preview_size"]
            crop = ""
            if result.get("crop"):
                crop = f'<a class="crop" href="{quote(result["crop"])}"><img loading="lazy" src="{quote(result["crop"])}" alt="Matched 100 percent detail crops"><span>Open 100% crop comparison</span></a>'
            metrics = result.get("metrics", {})
            stats = f'Mean RGB change {metrics.get("mean_absolute_rgb_255", 0):.2f}/255 · {result["output_size"][0]} × {result["output_size"][1]} output'
            stages = f'<a href="{quote(result["stage_sheet"])}">Combination steps</a>' if result.get("stage_sheet") else ""
            cards.append(f'''<article class="result">
<div class="result-head"><h3>{e(result['source_id'])}</h3><p>{e(result['basis'])}</p></div>
<div class="compare" style="aspect-ratio:{width}/{height}">
 <img loading="lazy" src="{before}" alt="Before {e(result['source_id'])}">
 <img loading="lazy" class="after" src="{after}" alt="After {e(result['source_id'])}">
 <span class="label left">BEFORE</span><span class="label right">AFTER</span><span class="divider"></span>
 <input aria-label="Before after divider" type="range" min="0" max="100" value="50">
</div>
<div class="actions"><button class="toggle" data-mode="before">Show before</button><button class="toggle" data-mode="after">Show after</button><button class="toggle" data-mode="split">Split</button><a href="{quote(result['comparison'])}">Side by side</a><a href="{full_before}">Before file</a><a href="{full_after}">After file</a>{stages}</div>
<p class="stats">{e(stats)}</p>{crop}
</article>''')
        verdict = experiment.get("verdict", findings.get(slug, "Experimental result; inspect the comparison at both whole-image size and 100%."))
        sections.append(f'''<section id="{e(slug)}"><div class="section-heading"><p class="eyebrow">{e(slug)}</p><h2>{e(title)}</h2><p>{e(experiment['description'])}</p><p class="verdict">{e(verdict)}</p><a href="{quote(slug)}/manifest.json">Parameters and source provenance</a></div>{''.join(cards)}</section>''')
    document = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GR Mod · JPEG experiments</title>
<style>
:root{color-scheme:dark;font-family:Segoe UI,Arial,sans-serif;background:#11151a;color:#e2e8f0}*{box-sizing:border-box}body{margin:0}header,main{max-width:1500px;margin:auto;padding:32px}header{padding-top:54px}h1{font-size:clamp(30px,4vw,54px);letter-spacing:-1.8px;line-height:1.1;margin:10px 0 24px}h2{font-size:30px;letter-spacing:-.8px}h3{margin:0;font-size:19px}p{line-height:1.65;color:#acb9c8;max-width:1050px}a{color:#a9c5ee;text-decoration:none}a:hover{text-decoration:underline}.eyebrow{font-size:12px;text-transform:uppercase;letter-spacing:2px;color:#83b9b1}.notice{padding:18px 22px;background:#1a222c;border:1px solid #303c4b;border-radius:10px}.navigation{display:flex;flex-wrap:wrap;gap:10px;margin-top:26px}.navigation a{padding:10px 14px;background:#202832;border-radius:7px;font-size:13px}section{scroll-margin-top:20px;padding:28px 0 45px;border-top:1px solid #303943}.section-heading{margin-bottom:28px}.verdict{border-left:3px solid #77a99b;padding-left:15px;color:#d7e2e9}.result{background:#1a2028;border:1px solid #323b46;border-radius:12px;overflow:hidden;margin:26px 0}.result-head{padding:20px 24px}.result-head p{margin:7px 0 0;font-size:14px}.compare{position:relative;overflow:hidden;background:#080a0c;max-height:85vh;margin:auto}.compare img{position:absolute;width:100%;height:100%;object-fit:contain;inset:0}.compare .after{clip-path:inset(0 0 0 50%)}.compare input{position:absolute;inset:0;width:100%;height:100%;opacity:0;cursor:ew-resize;margin:0}.divider{position:absolute;top:0;bottom:0;left:50%;width:2px;background:rgba(255,255,255,.85);pointer-events:none}.divider:after{content:'↔';position:absolute;top:50%;left:-18px;background:#111a26dd;border:1px solid #b7c9db;border-radius:50%;width:38px;height:38px;text-align:center;line-height:34px}.label{position:absolute;top:14px;background:#111a26bb;padding:6px 10px;font-size:11px;letter-spacing:1px;border-radius:4px;pointer-events:none}.left{left:14px}.right{right:14px}.actions{padding:16px 22px;display:flex;flex-wrap:wrap;gap:12px;align-items:center}.actions button{background:#2b3948;color:#e4eaf0;border:1px solid #42566b;border-radius:5px;padding:8px 13px;cursor:pointer}.actions a{font-size:13px}.stats{font-size:12px;margin:0;padding:0 23px 20px}.crop{display:block;padding:0 22px 22px}.crop img{max-width:100%;display:block}.crop span{font-size:12px;display:block;margin-top:8px}footer{padding:30px;color:#91a0b2;text-align:center;font-size:12px}@media(max-width:700px){header,main{padding:20px}.result-head{padding:15px}.compare{max-height:none}h2{font-size:25px}}
</style></head><body><header><p class="eyebrow">GR Mod · offline processing lab · 31 October 2026</p><h1>Your photographs.<br>Each processing idea, compared.</h1><p>Drag across each image, switch between before and after, or open a side-by-side comparison. Full-size files and exact processing parameters are kept beside every experiment.</p><p class="notice">All original photographs remain untouched. These are deterministic offline prototypes, not camera-verified firmware or measured Fujifilm reproductions. JPEG experiments begin with your camera JPEG as shot. RAW experiments use a shared, explicitly documented LibRaw rendering baseline. Exposure protection is a rendering experiment using existing DNG headroom; no photograph was recaptured.</p><div class="navigation">NAVIGATION</div><p><a href="00-source-selection/selection.json">Selected sources</a> · <a href="summary.json">Complete run manifest</a> · <a href="overview.jpg">Overview contact sheet</a></p></header><main>SECTIONS</main><footer>Local files only · no remote libraries, analytics or uploads · sRGB output</footer><script>
function split(card,value){const box=card.querySelector('.compare');box.querySelector('.after').style.clipPath=`inset(0 0 0 ${value}%)`;box.querySelector('.divider').style.left=value+'%';box.querySelector('input').value=value;box.querySelector('.divider').style.display=value==0||value==100?'none':'block';box.querySelector('.label.left').style.display=value==0?'none':'block';box.querySelector('.label.right').style.display=value==100?'none':'block'}
document.querySelectorAll('.compare input').forEach(input=>input.addEventListener('input',()=>split(input.closest('.result'),input.value)));
document.querySelectorAll('.toggle').forEach(button=>button.addEventListener('click',()=>split(button.closest('.result'),button.dataset.mode==='before'?100:button.dataset.mode==='after'?0:50)));
</script></body></html>'''
    document = document.replace("NAVIGATION", "".join(links)).replace("SECTIONS", "".join(sections))
    (output / "index.html").write_text(document, encoding="utf-8")
