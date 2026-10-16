"""Rebuild the concise reader; requires matplotlib and Poppler command-line tools."""
import hashlib, html, json, re, subprocess, tempfile
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
P=Path(__file__).resolve().parent
S=P/'source'
load=lambda p:json.loads(p.read_text())
new=load(P/'overview.json'); order=load(S/'chart-order.json'); notes=load(S/'page-explanations.json')
plt.rcParams.update({'font.family':'WenQuanYi Micro Hei','pdf.fonttype':42,'axes.unicode_minus':False})
(P/'figures').mkdir(exist_ok=True)
checks=[]
for page in new:
    fig=plt.figure(figsize=(12,9),facecolor='#f7f9fc')
    fig.text(.055,.94,page['title'],fontsize=23,weight='bold',color='#182b40',va='top')
    fig.text(.055,.88,page['lead'],fontsize=13,color='#197c88',va='top')
    fig.canvas.draw(); renderer=fig.canvas.get_renderer(); fp=FontProperties(family='WenQuanYi Micro Hei',size=14)
    def wrap(text):
        lines=[]; line=''
        for c in re.findall(r'[A-Za-z0-9_./<>-]+|.', text):
            if renderer.get_text_width_height_descent(line+c,fp,False)[0]>fig.bbox.width*.87:
                lines.append(line);line=c
            else: line+=c
        if line:lines.append(line)
        return '\n'.join(lines)
    blocks=[]
    for i,(title,body) in enumerate(page['blocks']):
        y=.79-i*.177
        t=fig.text(.055,y,title,fontsize=16,weight='bold',color='#197c88',va='top')
        b=fig.text(.055,y-.042,wrap(body),fontsize=14,color='#24384d',va='top',linespacing=1.65)
        blocks.extend([t,b])
    fig.text(.055,.053,'依据：'+page['source'],fontsize=8,color='#697586',va='top')
    fig.text(.055,.025,'v017 · 共 39 页；实验页保留 v015 原页码与引用。实现依据冻结材料，未新增运行验证。',fontsize=9,color='#697586')
    fig.canvas.draw(); renderer=fig.canvas.get_renderer()
    bounds=[t.get_window_extent(renderer) for t in blocks]
    assert all(b.x0>=0 and b.x1<=fig.bbox.width and b.y0>fig.bbox.height*.075 for b in bounds),page['id']
    assert all(a.y0>b.y1 for a,b in zip(bounds,bounds[1:])),page['id']
    fig.savefig(P/'figures'/f"{page['id']}.pdf");fig.savefig(P/'figures'/f"{page['id']}.png",dpi=120)
    checks.append({'id':page['id'],'text_in_bounds':True,'blocks_do_not_overlap':True})
    plt.close(fig)
# Replace mechanism pages 4–14 with four concise pages, and 38–40 with one.
# Drop the three redundant mechanism appendices (46–48). All other pages are copied.
sequence=[]
for old in range(1,52):
    if old==4:sequence.extend({'new':p['id']} for p in new[:4])
    if old==38:sequence.append({'new':'planner'})
    if 4<=old<=14 or 38<=old<=40 or 46<=old<=48:continue
    sequence.append({'original_page':old,'id':order[old-1]['id']})
with tempfile.TemporaryDirectory() as tmp:
    tmp=Path(tmp)
    subprocess.run(['pdfseparate',str(S/'v015-charts.pdf'),str(tmp/'page-%d.pdf')],check=True)
    paths=[P/'figures'/f"{r['new']}.pdf" if 'new' in r else tmp/f"page-{r['original_page']}.pdf" for r in sequence]
    subprocess.run(['pdfunite',*map(str,paths),str(P/'charts.pdf')],check=True)
    # Compare extracted text for every retained page after assembly.
    for i,r in enumerate(sequence,1):
        if 'original_page' not in r:continue
        def extract(pdf,page):return subprocess.check_output(['pdftotext','-f',str(page),'-l',str(page),str(pdf),'-'])
        assert extract(P/'charts.pdf',i)==extract(S/'v015-charts.pdf',r['original_page']),r
esc=html.escape
intro='非实验机制说明合并为 5 页；保留 34 页问题、方法、实验与结论，共 39 页。实验页直接取自 v015，原图及页注不改写。PDF 保留页脚中的原页码，页内引用也指 v015 原页码；本网页同时标出新旧位置。'
parts=[f'<h1>AutoData：数据结构、代码框架与版本区别</h1><p>{intro}</p><p><a href="charts.pdf">下载完整 PDF</a> · <a href="source/code-structure-evidence.md">代码证据</a> · <a href="source/interface-evidence.md">接口证据</a></p>']
for i,r in enumerate(sequence,1):
    if 'new' in r:
        p=next(p for p in new if p['id']==r['new'])
        body=f'<h2>{esc(p["title"])}</h2><p>{esc(p["lead"])}</p>'+''.join(f'<h3>{esc(a)}</h3><p>{esc(b)}</p>' for a,b in p['blocks'])+f'<small>依据：{esc(p["source"])}</small>'
        origin='精简机制说明'
    else:
        key=r['id']; e=notes[key]; origin=f'v015 原第 {r["original_page"]} 页'
        body=f'<h2>{esc(e["title"])}</h2><img loading="lazy" src="source/chart-images/{key}.png" alt="{esc(e["title"])}">'+''.join(f'<h3>{label}</h3><p>{esc(e[f])}</p>' for f,label in [('how','怎么做的'),('why','这样做的意义'),('result','当前结论'),('reading','读图与术语')])
    parts.append(f'<section id="page-{i}"><small>阅读顺序 {i:02d} / {len(sequence)} · {origin}</small>{body}</section>')
css='body{margin:0;background:#eef2f7;color:#182b40;font:18px/1.8 system-ui,sans-serif}main{max-width:1100px;margin:auto;padding:30px}section{background:white;padding:32px;margin:28px 0;border-radius:12px}h2{font-size:27px}h3{font-size:20px;color:#197c88;margin-bottom:6px}p{margin-top:4px}img{width:100%;height:auto}small{color:#697586}a{color:#245da0}@media(max-width:700px){main{padding:12px}section{padding:18px}}'
(P/'charts.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AutoData v017 精简说明</title><style>'+css+'</style><main>'+''.join(parts)+'</main></html>')
(P/'page-map.json').write_text(json.dumps(sequence,ensure_ascii=False,indent=2)+'\n')
(P/'verification.json').write_text(json.dumps({'page_count':len(sequence),'retained_original_pages':sum('original_page' in r for r in sequence),'retained_page_text_equal':True,'retained_pages_method':'pdfseparate + pdfunite; no rerendering','layout_checks':checks,'new_simulation_runs':False},ensure_ascii=False,indent=2)+'\n')
print('Built',len(sequence),'pages; retained original pages verified; five new layouts checked.')
