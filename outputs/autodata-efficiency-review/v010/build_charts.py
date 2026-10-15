"""Build an ordered local slide reader, using the same sequence as charts.pdf."""
import html,json,re
from pathlib import Path
P=Path(__file__).resolve().parent
order=json.loads((P/'chart-order.json').read_text())
notes=json.loads((P/'slide-notes.json').read_text())
guide=(P/'charts-guide.md').read_text().split('## 第 ')[1:]
assert len(guide)==len(order)
esc=html.escape
nav=[];slides=[];last=None
for i,row in enumerate(order,1):
 key=row['id'];section=row['section']
 if section!=last:
  nav.append(f'<li><a href="#page-{i}">{esc(section)}</a></li>');last=section
 paras=guide[i-1].split('\n\n')[1:]
 details=''.join('<p>'+esc(x.strip())+'</p>' for x in paras if x.strip())
 slides.append(f'<section id="page-{i}"><h2>{i:02d} / {len(order)} · {esc(section)}</h2><img loading="lazy" src="figures/{key}.png" alt="{esc(notes[key][2])}"><details><summary>展开本页实验说明与讲解</summary>{details}</details></section>')
css='body{margin:0;background:#eef2f7;color:#182b40;font:16px/1.8 system-ui,sans-serif}main{max-width:1400px;margin:auto;padding:24px}img{width:100%;height:auto}section{background:white;padding:18px;margin:30px 0;border-radius:12px;scroll-margin-top:15px}h1{font-size:28px}h2{font-size:18px;color:#197c88}a{color:#245da0}details{padding:16px;background:#f5f8fc}summary{cursor:pointer;font-weight:600}nav ul{display:flex;gap:24px;flex-wrap:wrap;padding:0;list-style:none}@media print{section{break-before:page}details,nav{display:none}}'
(P/'charts.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>AutoData 实验图册 v010</title><style>'+css+'</style><main><h1>AutoData：实现改进与实验结果讲解</h1><p>26 页主线 + 6 页附录。按问题、设计、机制、结果、解释和下一轮验证展开。所有数字来自已有实验，本版没有新增运行。</p><nav><a href="charts.pdf">图册 PDF</a> · <a href="charts-guide.md">逐页讲解稿</a> · <a href="index.html">完整研究报告</a><ul>'+''.join(nav)+'</ul></nav>'+''.join(slides)+'</main></html>')
print('Ordered HTML reader generated: 32 slides with expandable explanations')
