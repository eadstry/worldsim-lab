from pathlib import Path
import html
import shutil
import re
from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
SOURCE = (ROOT / "report.md").read_text(encoding="utf-8")
shutil.copy2(ROOT / "report.md", DIST / "report.md")
shutil.copytree(ROOT / "figures", DIST / "figures", dirs_exist_ok=True)

FLOW = [
    "打通数据生产与成功判定", "定位导出及内存瓶颈", "异步导出：提高文件就绪吞吐",
    "内部计时：拆出渲染和物理耗时", "域随机化：验证状态和视觉变化",
    "Franka 家庭场景：IK 与 cuRobo 避障", "香蕉和多视角/力数据：扩展操作对象",
    "后续：扩增质量与训练泛化",
]

def render_mermaid(tokens, idx, options, env):
    items = "".join(f'<li><span>{html.escape(label)}</span></li>' for label in FLOW)
    return f'<ol class="experiment-flow" aria-label="实验递进路线">{items}</ol>'

md = MarkdownIt("default", {"html": False}).enable("table")
md.add_render_rule("fence", lambda self, tokens, idx, options, env: render_mermaid(tokens, idx, options, env)
                   if tokens[idx].info.strip() == "mermaid" else self.renderer.rules["fence"](self, tokens, idx, options, env))
body = md.render(SOURCE)
# The report cites detailed source files in separate local worktrees. Keep their labels
# readable without publishing links that would be broken on this standalone Site.
body = re.sub(r'<a href="(?:\.\./)+[^\"]*">([^<]*)</a>', r'<span class="local-reference" title="项目本地来源，未随本页面发布">\1</span>', body)
body = re.sub(r'<a href="\.\./[^\"]*">([^<]*)</a>', r'<span class="local-reference" title="项目本地来源，未随本页面发布">\1</span>', body)
body = body.replace('src="figures/', 'src="figures/')
page = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="具身数据生产、效率与仿真实验的可视化版本化报告">
<title>具身实验图谱 · 版本化实验报告</title>
<style>
:root{{--paper:#f6f4ef;--ink:#202a2c;--muted:#657174;--line:#d9ddd5;--accent:#17786f;--pale:#e6f0ea;--gold:#bf7436}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--paper);color:var(--ink);font:17px/1.75 system-ui,-apple-system,"Segoe UI",sans-serif}}
header{{padding:64px max(24px,calc((100vw - 1040px)/2)) 48px;background:#193b3a;color:#f5f2e9}}header .eyebrow{{letter-spacing:.15em;text-transform:uppercase;color:#b4d4c5;font-size:12px}}header h1{{font-size:clamp(34px,6vw,64px);line-height:1.1;max-width:850px;margin:20px 0}}header p{{max-width:740px;color:#d4dfd7;font-size:18px}}
.toolbar{{position:sticky;top:0;z-index:2;background:#f6f4eff0;backdrop-filter:blur(10px);border-bottom:1px solid var(--line);padding:10px max(20px,calc((100vw - 1040px)/2));display:flex;gap:12px;align-items:center}}.toolbar a,.toolbar button{{color:var(--accent);font:inherit;text-decoration:none;border:1px solid var(--line);background:#fff;padding:6px 12px;border-radius:20px;cursor:pointer}}.toolbar .spacer{{flex:1}}main{{max-width:1040px;margin:42px auto;padding:0 24px 80px}}
h1,h2,h3{{line-height:1.3;letter-spacing:-.02em}}main h1{{display:none}}main h2{{font-size:31px;margin:62px 0 20px;padding-top:12px}}main h3{{font-size:22px;margin-top:36px}}p{{margin:16px 0}}a{{color:#176c64}}blockquote{{margin:22px 0;padding:16px 24px;border-left:4px solid var(--gold);background:#fff9ed;border-radius:0 12px 12px 0}}ul,ol{{padding-left:1.5em}}li{{padding-left:.25em}}table{{border-collapse:collapse;width:100%;margin:22px 0;background:#fff;font-size:15px}}th,td{{border:1px solid var(--line);padding:10px 12px;text-align:left}}th{{background:#e8eee8}}img{{display:block;max-width:100%;height:auto;margin:26px auto;border-radius:12px;box-shadow:0 10px 28px #213c3518}}code{{background:#e9ece7;padding:.12em .35em;border-radius:4px;font-size:.9em}}hr{{border:0;border-top:1px solid var(--line);margin:40px 0}}.local-reference{{color:#5d716e;border-bottom:1px dotted #849b92;cursor:help}}
.experiment-flow{{list-style:none;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;padding:0;margin:26px 0 34px;counter-reset:flow}}.experiment-flow li{{position:relative;min-height:100px;padding:15px;background:var(--pale);border:1px solid #cadbd0;border-radius:12px;counter-increment:flow}}.experiment-flow li::before{{content:counter(flow,decimal-leading-zero);display:block;color:var(--accent);font-size:12px;font-weight:700;letter-spacing:.1em;margin-bottom:8px}}.experiment-flow li:not(:nth-child(4n))::after{{content:"→";position:absolute;right:-13px;top:34px;color:var(--gold);font-size:20px;z-index:1}}.download{{display:inline-block;margin:20px 0;padding:9px 15px;border-radius:8px;background:var(--accent);color:white!important;text-decoration:none}}footer{{max-width:1040px;margin:auto;padding:24px;border-top:1px solid var(--line);color:var(--muted);font-size:14px}}
@media(max-width:700px){{body{{font-size:16px}}header{{padding:46px 24px 36px}}main{{margin-top:24px;padding-inline:18px}}main h2{{font-size:26px;margin-top:44px}}.experiment-flow{{grid-template-columns:repeat(2,minmax(0,1fr))}}.experiment-flow li:not(:nth-child(4n))::after{{display:none}}table{{display:block;overflow-x:auto;white-space:nowrap}}.toolbar{{padding-inline:14px}}}}
@media print{{.toolbar{{display:none}}body{{background:white}}header{{background:white;color:var(--ink);padding:20px 0}}header p{{color:var(--muted)}}main{{max-width:none;padding:0}}}}
</style></head><body>
<header><div class="eyebrow">Research portfolio · v001 · 2026.10</div><h1>具身实验图谱</h1><p>从数据生产效率和质量验收，延伸到域随机化、避障与多传感操作记录。以图为入口，沿着实验问题和证据边界阅读。</p></header>
<nav class="toolbar" aria-label="页面工具"><a href="#先看实验如何递进">实验路线</a><a href="#9-下一阶段如何接着做">后续计划</a><span class="spacer"></span><a href="report.md" download>下载 Markdown</a><button onclick="window.print()">打印 / 存为 PDF</button></nav>
<main>{body}</main><footer>汇总版本 v001 · 材料截止 2026-10-19 · 此页面为已有实验资料的可视化整理，没有新增 GPU 仿真或训练。图表为压缩后的可移植副本，原始数据仍按项目版本留存。</footer>
</body></html>'''
(DIST / "index.html").write_text(page, encoding="utf-8")
