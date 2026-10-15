"""Render the report's small Markdown subset as a local HTML document (stdlib only)."""
from pathlib import Path
import html,re
P=Path(__file__).resolve().parent

def inline(value):
    value=html.escape(value)
    value=re.sub(r'\[([^\]]+)\]\((https://[^)]+)\)', r'<a href="\2">\1</a>', value)
    value=re.sub(r'`([^`]+)`',r'<code>\1</code>',value)
    return re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',value)

parts=[];toc=[]
for chunk in (P/'report.md').read_text().split('\n\n'):
    match=re.match(r'^(#{1,3}) (.*)',chunk)
    if match:
        level=len(match[1]);ident=f'section-{len(parts)}'
        parts.append(f'<h{level} id="{ident}">{inline(match[2])}</h{level}>')
        if level==2:toc.append(f'<li><a href="#{ident}">{inline(match[2])}</a></li>')
    elif chunk.startswith('!['):
        match=re.fullmatch(r'!\[(.*)\]\(([^)]+)\)',chunk)
        if not match:raise ValueError('Invalid image: '+chunk)
        alt,src=match.groups();parts.append(f'<figure><img loading="lazy" src="{html.escape(src)}" alt="{html.escape(alt)}"><figcaption>{html.escape(alt)}</figcaption></figure>')
    elif chunk.startswith('|'):
        rows=[]
        for i,row in enumerate(chunk.splitlines()):
            if i==1:continue
            tag='th' if i==0 else 'td'
            rows.append('<tr>'+''.join(f'<{tag}>{inline(cell.strip())}</{tag}>' for cell in row.strip('|').split('|'))+'</tr>')
        parts.append('<div class="scroll"><table>'+''.join(rows)+'</table></div>')
    else:parts.append('<p>'+inline(chunk).replace('\n','<br>')+'</p>')
css='body{font:16px/1.85 system-ui,sans-serif;background:#f7f9fc;color:#172436;margin:0}main{max-width:1160px;margin:auto;padding:40px 24px}h1{font-size:34px}h2{margin-top:52px;color:#135c69}img{width:100%;height:auto}figure{margin:24px 0}figcaption{font-size:13px;color:#526276}nav{display:flex;gap:20px;flex-wrap:wrap}a{color:#195eaa}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:12px;border-bottom:1px solid #cad4df;text-align:left}code{overflow-wrap:anywhere}.scroll{overflow:auto}summary{cursor:pointer}@media print{main{padding:0}h2{break-after:avoid}figure{break-inside:avoid}}'
nav='<nav><a href="charts.pdf">图册 PDF</a><a href="version-walkthrough.md">三版本讲解稿</a><a href="report.md">分析原文</a><a href="internal-timing.csv">内部耗时 CSV</a><a href="code-evidence.md">代码证据</a><a href="interface-evidence.md">接口证据</a></nav>'
contents='<details><summary>展开章节目录</summary><ol>'+''.join(toc)+'</ol></details>'
(P/'index.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AutoData 实现细节与 v2 实验复盘 v009</title><style>'+css+'</style><main>'+nav+contents+''.join(parts)+'</main></html>')
