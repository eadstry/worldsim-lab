"""Publish a new local docs revision, reusing measured results and explaining correlations."""
from pathlib import Path
import argparse, hashlib, html, json, re, shutil, subprocess
import markdown

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source',type=Path,required=True)
p.add_argument('--docs',type=Path,required=True)
a=p.parse_args();src=a.source.resolve();docs=a.docs.resolve()
slug='openarm-task-error-20261021-r02';ref=docs/'openarm-task-error';ref.mkdir(parents=True,exist_ok=True)
old=src/'完成抓取任务后的指令与实际位置差值实验报告.md'
text=old.read_text();parts=re.split(r'^## ',text,flags=re.M);title=parts[0].strip()
sections=[]
for part in parts[1:]:
 heading,body=part.split('\n',1);sections.append((heading,body.strip()))
assert len(sections)==10
phase_title,phase_body=sections[7]
table_start=phase_body.index('| 原设置 |');table_end=phase_body.index('\n\n',table_start)
corr_table=phase_body[table_start:table_end]
sections[7]=('分阶段看差值：先接近，再抓起和搬运',phase_body[:table_start].strip())
explain='''这一项分析想回答：**关节动得越快，action与state的差值是不是就越大？** 表里分别比较运动方向和运动快慢。

### 第一列：运动方向与目标偏差是否一致

**有符号误差（Signed error）＝目标角度action－实际角度state。** 实际9°、目标10°，偏差是＋1°；实际9°、目标8°，偏差是－1°。关节向角度增大的方向运动，速度为正；反方向运动，速度为负。

第一列比较偏差与速度是否同向变化。数值越接近1，它们一起增大或减小的关系越强。例如关节3的0.925，表示两者有很强的同向变化关系。

### 第二列：运动快慢与差值大小是否一起变化

去掉方向，只比较**差值大小（Absolute error）**和**速率（Speed，速度的绝对值）**。它直接回答：关节转得更快时，目标与实际位置之间是否也差得更多？

'''+corr_table
reading='''下面用表里的实际数值说明两列的区别。

| 例子 | 通俗解释 |
| --- | --- |
| 关节3：第二列0.724 | 运动越快，差值越大的关系比较明显。 |
| 关节5：第二列0.699 | 也有比较明显的同向变化关系。 |
| 关节1：第二列0.165 | 关系较弱，单看速度很难判断差值大小。 |
| 关节4：第一列0.874，第二列0.280 | 偏差方向与运动方向较一致，但动得更快时，差值未必增加很多。 |

### r是什么，实际差了多少又看什么

**r是相关系数（Correlation coefficient），范围为−1到1。** 接近1表示同向变化关系强，接近−1表示反向变化关系强，接近0表示线性关系弱。

**0.724不是0.724°，也不是“72.4%的误差由速度造成”。** 它衡量两者一起变化的程度。实际差了多少度，要看平均绝对差值（Mean absolute error，MAE）。

第一列的正相关描述偏差与运动方向的关系；据此不能判断“多少帧目标领先”，也不能算出延迟了多少毫秒。

### 这项分析怎样计算，结论是什么

原设置有4个初始场景，各重复3次，共12次任务尝试。对每次任务、每个关节分别计算相关系数，再取12次结果的中位数；每个关节分别统计，不把7个关节混在一起。

速度来自相邻两帧实际角度的变化：**速度≈（本帧角度－上一帧角度）×30**，因为每秒记录30帧。计算不跨任务边界。

**结论：速度与差值有关，但各关节的关系强弱不同。** 这张表用于寻找规律；刚度、阻尼、重力等因素影响多少，要结合“每次只改一个参数”的对照实验判断。时间上相邻的记录不是独立实验重复。
'''
sections[8:8]=[('读懂相关性：方向一致与动得更快',explain),('用实际数值理解r 以及它能回答什么',reading)]
assert len(sections)==12
# Rebase all inherited local references into docs; retain raw simulation data in runs.
source_hashes={str(old):hashlib.sha256(old.read_bytes()).hexdigest()}
def relocate(m):
 raw=m.group(1)
 if raw.startswith(('https:','http:','#')):return m.group(0)
 f=(src/raw).resolve();assert f.exists(),f
 if raw.startswith('figures/'):
  dest=ref/'figures'/f.name
 elif f.suffix=='.pdf':
  dest=ref/'open-source-parameter-survey-20261021.pdf'
 else:dest=ref/'evidence'/f.name
 dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dest)
 if dest.suffix=='.svg':dest.write_text('\n'.join(line.rstrip() for line in dest.read_text().splitlines())+'\n')
 source_hashes[str(f)]=hashlib.sha256(f.read_bytes()).hexdigest()
 return ']('+dest.relative_to(docs).as_posix()+')'
sections=[(h,re.sub(r'\]\(([^)]+)\)',relocate,b)) for h,b in sections]
sections[-1]=(sections[-1][0],sections[-1][1]+'''\n\n### 本次修订\n\n2026-10-21 r02在相关性表格旁新增第9–10页的通俗解释、角度示例、读表示例与计算方法，更新此前“目标通常领先”的表述为偏差与速度的同向变化关系。实验数据、相关系数和其余实验结论沿用原报告，本次只作说明与排版更新。原版报告保留在原位置。''')
md=title+'\n\n'+'\n\n'.join('## '+h+'\n\n'+b for h,b in sections)+'\n'
(docs/(slug+'.md')).write_text(md)
oldhtml=(src/'完成抓取任务后的指令与实际位置差值实验报告.html').read_text()
css=re.search(r'<style>(.*?)</style>',oldhtml,re.S).group(1)
css+='\n#p9{font-size:13px;line-height:1.7}#p10{font-size:13.5px;line-height:1.75}#p12{font-size:12px;line-height:1.7}#p12 table{font-size:11.3px}'
render=[]
for i,(h,b) in enumerate(sections,1):
 body=markdown.markdown(b,extensions=['tables','fenced_code'])
 def embed(m):
  s=(docs/m.group(1)).read_text();return '<figure>'+s[s.index('<svg'):]+'</figure>'
 body=re.sub(r'<p><img[^>]*src="([^"]+\.svg)"[^>]*/></p>',embed,body)
 render.append(f'<section class="page" id="p{i}"><header><span>完整任务 · 控制与物理因素 · r02</span><span>2026.10.21</span></header><main><div class="kicker">{i:02d} / 12</div><h1>{html.escape(h)}</h1><article>{body}</article></main><footer><span>指令与实际位置差值 · 通俗解释修订版</span><span>{i} / 12</span></footer></section>')
js=re.search(r'(<script>.*?</script>)',oldhtml,re.S).group(1)
target=docs/(slug+'.html');markup=('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>完整任务差值实验报告 r02</title><style>'+css+'</style><body>'+''.join(render)+js+'</body></html>')
target.write_text('\n'.join(line.rstrip() for line in markup.splitlines())+'\n')
flags=['google-chrome','--headless','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--allow-file-access-from-files','--window-size=1440,1200','--virtual-time-budget=1500','--no-pdf-header-footer']
dom=subprocess.run(flags+['--dump-dom',target.as_uri()],capture_output=True,text=True,check=True).stdout
rows=json.loads(html.unescape(re.search(r'<pre id="layout-audit"[^>]*>(.*?)</pre>',dom,re.S).group(1)))
print('Footer clearances:',[(r['page'],round(r['footerTop']-r['contentBottom'],1)) for r in rows]);assert all(r['footerTop']-r['contentBottom']>12 for r in rows)
pdf=docs/(slug+'.pdf');subprocess.run(flags+['--print-to-pdf='+str(pdf),target.as_uri()],capture_output=True,text=True,check=True)
info=subprocess.check_output(['pdfinfo',str(pdf)],text=True);assert int(re.search(r'Pages:\s+(\d+)',info).group(1))==12
pdftext=subprocess.check_output(['pdftotext',str(pdf),'-'],text=True)
assert all(t in pdftext for t in ['0.925','0.724','0.165','72.4%','192','0.681'])
(ref/'evidence'/'explanation-revision-20261021-r02.json').write_text(json.dumps(dict(source_sha256=source_hashes,revision='Explanation only; no new simulation or metric recomputation; original report unchanged.',pages=12,layout=rows,pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest()),ensure_ascii=False,indent=2))
print(pdf)
