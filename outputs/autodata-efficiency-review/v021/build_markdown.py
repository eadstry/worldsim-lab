"""Rebuild the Markdown edition of the v015 chart book using only stdlib."""
import json
from pathlib import Path
P=Path(__file__).resolve().parent
order=json.loads((P/'chart-order.json').read_text())
explanations=json.loads((P/'page-explanations.json').read_text())
fields=[('how','怎么做的'),('why','这样做的意义'),('result','当前结论'),('reading','读图与术语')]
parts=['# AutoData 实现改进与内部耗时对照',
'本资料按原 PDF 的 51 页顺序整理，包含 45 页主线和 6 页附录。每页先展示图表，再解释怎么做、为什么这样做、当前结论及读图术语。说明文字可直接编辑，图表保留为原图。',
'历史 8 环境生产实验、新增 4 环境内部计时配对与 v2 跨日期运行分别标明。相机复用的条件收益尚待实验验证。',
'[对应的原 PDF](charts.pdf)', '## 阅读顺序']
sections={}
for i,row in enumerate(order,1):sections.setdefault(row['section'],[]).append(i)
parts.append('\n'.join(f'- {section}：第 {min(pages):02d}–{max(pages):02d} 页。' for section,pages in sections.items()))
for i,row in enumerate(order,1):
 e=explanations[row['id']]
 parts.extend([f'## 第 {i:02d} 页 · {e["title"]}',f'所属章节：{row["section"]}。',f'![第 {i:02d} 页：{e["title"]}](chart-images/{row["id"]}.png)'])
 for key,label in fields:parts.extend([f'### {label}',e[key]])
(P/'charts.md').write_text('\n\n'.join(parts)+'\n',encoding='utf-8')
print(f'Generated charts.md: {len(order)} charts and {len(order)*len(fields)} explanatory paragraphs')
