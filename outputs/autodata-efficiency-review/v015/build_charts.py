"""Build the 51-page reader and guide from the same explanations used in the PDF."""
import html,json,struct
from pathlib import Path
P=Path(__file__).resolve().parent
order=json.loads((P/'chart-order.json').read_text())
explanations=json.loads((P/'page-explanations.json').read_text())
fields=[('how','怎么做的'),('why','这样做的意义'),('result','当前结论'),('reading','读图与术语')]
assert {r['id'] for r in order}==set(explanations)
esc=html.escape
nav=[];slides=[];guide=['# AutoData 图册逐页详细说明','45 页主线与 6 页附录。每页按怎么做、意义、结论和术语解释展开；与 PDF 使用相同说明原文。','历史 8 环境生产实验、新增 4 环境内部计时配对与 v2 跨日期运行分别标明。缓存方案及条件收益尚待实验验证。']
last=None
for i,row in enumerate(order,1):
    key=row['id'];section=row['section'];e=explanations[key]
    width,height=struct.unpack('>II',(P/'chart-images'/f'{key}.png').read_bytes()[16:24])
    if section!=last:
        nav.append(f'<li><a href="#page-{i}">{esc(section)}</a></li>');last=section
    paras=''.join(f'<div class="explanation-block"><h3>{esc(label)}</h3><p>{esc(e[field])}</p></div>' for field,label in fields)
    slides.append(f'<section id="page-{i}" aria-labelledby="title-{i}"><header><span>{i:02d} / {len(order)} · {esc(section)}</span><h2 id="title-{i}">{esc(e["title"])}</h2></header><img loading="lazy" width="{width}" height="{height}" src="chart-images/{key}.png" alt="第 {i} 页：{esc(e["title"])}"><div class="explanations">{paras}</div></section>')
    guide.append(f'## 第 {i:02d} 页 · {e["title"]}')
    guide.append(f'所属章节：{section}。图表：{key}。')
    for field,label in fields:guide.extend([f'### {label}',e[field]])
css='body{margin:0;background:#eef2f7;color:#182b40;font:17px/1.9 system-ui,sans-serif}main{max-width:1400px;margin:auto;padding:24px}img{display:block;width:100%;height:auto}section{background:white;margin:30px 0;border-radius:12px;overflow:hidden;scroll-margin-top:15px}header{padding:22px 28px 12px}header span{font-size:14px;color:#197c88}h1{font-size:28px}h2{margin:6px 0;font-size:24px}h3{font-size:17px;color:#197c88;margin:0}a{color:#245da0}.explanations{padding:24px 34px 32px;border-top:1px solid #d6dee7}.explanation-block{display:grid;grid-template-columns:8em 1fr;gap:20px;margin:16px 0}.explanation-block p{margin:0;max-width:64em}nav ul{display:flex;gap:24px;flex-wrap:wrap;padding:0;list-style:none}.intro{max-width:64em}@media(max-width:700px){main{padding:12px}header,.explanations{padding:18px}h2{font-size:21px}.explanation-block{display:block}.explanation-block h3{margin-bottom:5px}}@media print{section{break-before:page;break-inside:avoid}nav{display:none}.explanations{padding:12px}.explanation-block{font-size:12px;line-height:1.6}}'
intro='<h1>AutoData 实现改进与内部耗时对照</h1><p class="intro">本图册说明生成与保存如何配合、异步改造为何有效，以及下一步怎样验证加速方案。51 页均在图下直接提供实验方法、意义、当前结论与术语说明，首次阅读可按顺序浏览。</p><p class="intro">阅读时先确认实验规模和时间分母：历史 8 环境与新增 4 环境配对分别呈现；内部占比描述主机调用区间。相机复用的收益目前属于条件估算，尚未完成优化实验。</p>'
links='<nav><a href="charts.pdf">带详细页注的 PDF</a> · <a href="charts-guide.md">逐页说明原文</a> · <a href="acceleration-analysis.html">内部实测与加速方案</a> · <a href="gpu-analysis.html">GPU 源码分析</a> · <a href="execution-analysis.html">执行等待专项分析</a> · <a href="code-structure.html">代码结构详解</a> · <a href="index.html">完整研究报告</a><ul>'+''.join(nav)+'</ul></nav>'
(P/'charts.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AutoData 实验图册 v015 逐页详细说明</title><style>'+css+'</style><main>'+intro+links+''.join(slides)+'</main></html>')
(P/'charts-guide.md').write_text('\n\n'.join(guide)+'\n')
print(f'Generated {len(order)} pages with {len(order)*len(fields)} visible explanatory paragraphs')
