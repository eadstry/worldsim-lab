"""Render the report from the frozen evidence snapshot (matplotlib required).

Run in a NEW version directory for revisions; sealed versions must not be rewritten.
"""
from pathlib import Path
import html
import json
import re
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

HERE = Path(__file__).resolve().parent
if (HERE / 'manifest.json').exists():
    raise SystemExit('Sealed version: copy sources to a new version directory before rendering.')
E = json.loads((HERE / 'evidence.json').read_text())
A = E['async_validation']
R = A['gpu']['runs']
GIB = 1024**3
FONT = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
if Path(FONT).exists():
    from matplotlib import font_manager
    font_manager.fontManager.addfont(FONT)
    plt.rcParams['font.family'] = FontProperties(fname=FONT).get_name()
plt.rcParams.update({'font.size': 12, 'svg.fonttype': 'none', 'axes.spines.top': False,
                     'axes.spines.right': False, 'axes.labelcolor': '#253844',
                     'text.color': '#253844', 'xtick.color': '#526875', 'ytick.color': '#526875',
                     'axes.edgecolor': '#b9c6ce', 'figure.facecolor': 'white',
                     'savefig.facecolor': 'white', 'axes.titleweight': 'bold'})
BLUE, TEAL, ORANGE, RED, GRAY = '#3376a8', '#21867e', '#c78325', '#b94d4d', '#8195a3'
COLORS = [GRAY, BLUE, TEAL]
LABELS = ['同步 · 0 worker', '异步 · 1 worker', '异步 · 2 workers']
FIGS = {}

def save(fig, number, title):
    fig.tight_layout(pad=1.7)
    p = HERE / 'figures' / f'figure-{number:02d}'
    fig.savefig(p.with_suffix('.svg'), bbox_inches='tight')
    fig.savefig(p.with_suffix('.png'), dpi=160, bbox_inches='tight')
    plt.close(fig)
    svg = p.with_suffix('.svg').read_text()
    svg = svg[svg.index('<svg'):]
    prefix = f'chart-{number:02d}-'
    svg = re.sub(r'id="([^"]+)"', lambda m: 'id="' + prefix + m[1] + '"', svg)
    svg = svg.replace('url(#', 'url(#' + prefix).replace('href="#', 'href="#' + prefix)
    svg = re.sub(r'<svg\b', '<svg role="img"', svg, count=1)
    svg = svg.replace('>', '><title>' + html.escape(title) + '</title>', 1)
    FIGS[number] = svg

def bars(ax, values, xlabel, labels=LABELS, colors=COLORS, fmt='.2f'):
    ax.barh(range(len(values)), values, color=colors, height=.53)
    ax.set_yticks(range(len(values)), labels)
    ax.invert_yaxis()
    ax.set_xlabel(xlabel)
    ax.set_xlim(0, max(values) * 1.25)
    ax.xaxis.grid(True, alpha=.15)
    ax.set_axisbelow(True)
    for i, v in enumerate(values): ax.text(v + max(values)*.025, i, format(v,fmt), va='center')

# 01: throughput; every mode has 24 recorded successes, 23 strict terminal passes.
fig, axes = plt.subplots(1, 2, figsize=(11, 3.5))
bars(axes[0], [r['final_ready_per_minute'] for r in R], '最终文件就绪吞吐（条 / 分钟）', fmt='.3f')
bars(axes[1], [r['launcher_wall_seconds'] for r in R], '完整启动器耗时（秒）', fmt='.1f')
axes[0].set_title('吞吐提升 29.8%'); axes[1].set_title('完整耗时减少 22.1%')
save(fig, 1, '三种导出模式的最终文件吞吐与完整启动器耗时')

# 02: historical results as distinct evidence lanes, not a success-rate trend.
fig, ax = plt.subplots(figsize=(11, 4.8)); ax.axis('off')
history = [('共享配置探针', '两端比较 16 / 16 项通过；只验证接口与判据', BLUE),
           ('早期生成修复', '修复前 0 / 1；修复后单环境 1 / 1、四环境 4 / 4', BLUE),
           ('100 条目标运行', '8 环境：遥测 49 成功、6 失败、8 未完成；SIGKILL', RED),
           ('异步初版尝试', 'SIGKILL + OOM 计数增加；发现 CPU 视图保留整批数据', RED),
           ('所有权修复后对照', '0 / 1 / 2 worker 各 24 条；严格终态均为 23 / 24', TEAL)]
for i, (label, detail, color) in enumerate(history):
    y = 4-i
    ax.scatter(.15, y, s=110, color=color)
    ax.text(.38, y+.12, label, weight='bold', va='center')
    ax.text(2.5, y+.12, detail, va='center')
ax.plot([.15,.15],[0,4],color='#d3dde3',zorder=0)
ax.set(xlim=(-.1,10),ylim=(-.5,4.6))
save(fig, 2, '实验演进与每轮验证边界，按证据阶段而非等间隔时间排列')

# 03: exclusive timings, inclusive write timer intentionally excluded.
D = E['diagnosis']['whole_episode_gzip']; P = D['phases_seconds']
fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
bars(axes[0], [P['dataset_create'],P['prepare_stack'],P['cpu_numpy'],P['flush'],D['other_seconds']],
     '主机墙钟耗时（秒）', ['建数据集','轨迹堆叠','CPU / NumPy','HDF5 flush','其他'],
     [TEAL,GRAY,GRAY,GRAY,GRAY], '.4f')
rgb = {'左腕 RGB':11.12223454285413,'右腕 RGB':4.148232925916091,'第三视角 RGB':10.558265327010304}
bars(axes[1], list(rgb.values()), '建数据集耗时（秒）', list(rgb), [BLUE,ORANGE,TEAL], '.2f')
axes[0].set_title('建数据集占导出总时长 98.7%'); axes[1].set_title('三路 RGB 主导写出成本')
save(fig, 3, '单条真实轨迹 CPU 回放的导出阶段和 RGB 写出耗时')

# 04: comparable full chunk layout; one repeat only.
C = E['compression_full']['results']; names=['gzip-2','无压缩','LZF']
fig, axes = plt.subplots(1,2,figsize=(11,3.8))
bars(axes[0],[c['create_wall_seconds'] for c in C],'建数据集耗时（秒）',names,[TEAL,GRAY,BLUE],'.2f')
bars(axes[1],[c['output_bytes']/1024**2 for c in C],'文件大小（MiB）',names,[TEAL,GRAY,BLUE],'.1f')
axes[0].set_title('相同 chunk 的三路 RGB 回放'); axes[1].set_title('速度与存储体积的取舍')
save(fig,4,'1342 帧三路 RGB、相同 chunk 的压缩方式耗时与文件大小对照')

def box(ax, x, y, width, height, title, detail, color=BLUE):
    from matplotlib.patches import FancyBboxPatch
    ax.add_patch(FancyBboxPatch((x,y),width,height,boxstyle='round,pad=0.02,rounding_size=0.06',
                              edgecolor=color,facecolor='#f5f8fa',linewidth=1.2))
    ax.text(x+width/2,y+height*.68,title,ha='center',va='center',weight='bold',fontsize=12)
    ax.text(x+width/2,y+height*.28,detail,ha='center',va='center',fontsize=11)

def arrow(ax,a,b,label=None):
    ax.annotate('',xy=b,xytext=a,arrowprops={'arrowstyle':'->','color':GRAY,'lw':1.4})
    if label:ax.text((a[0]+b[0])/2,(a[1]+b[1])/2+.13,label,ha='center',fontsize=10)

# 05 architecture is explicitly schematic, no invented lane timings.
fig,ax=plt.subplots(figsize=(11,5.4));ax.axis('off');ax.set(xlim=(0,11),ylim=(0,5.6))
ax.text(.1,5.25,'同步路径：生成线程承担导出',weight='bold',fontsize=13)
for x,t,d in [(0.2,'录制轨迹','逐帧列表'),(3,'整条 stack','临时连续张量'),(5.8,'gzip + HDF5','生成等待'),(8.6,'继续仿真','下一回合')]:box(ax,x,3.95,2.1,.95,t,d,GRAY)
for x in [2.3,5.1,7.9]:arrow(ax,(x,4.42),(x+.7,4.42))
ax.text(.1,3.25,'异步路径：共享内存移交，独立进程写分片',weight='bold',fontsize=13)
box(ax,.2,1.9,2.1,1,'按环境独占帧','逐帧拷贝并释放',TEAL)
box(ax,3,1.9,2.1,1,'有界共享内存','只排队描述符',TEAL)
box(ax,5.8,2.35,2.1,.85,'CPU worker 1','独立 HDF5 分片',TEAL)
box(ax,5.8,1.15,2.1,.85,'CPU worker 2','独立 HDF5 分片',TEAL)
box(ax,8.6,1.75,2.1,1,'排空 → 合并','发布独立 HDF5',TEAL)
arrow(ax,(2.3,2.4),(3,2.4));arrow(ax,(5.1,2.4),(5.8,2.78));arrow(ax,(5.1,2.4),(5.8,1.58))
arrow(ax,(7.9,2.78),(8.6,2.25));arrow(ax,(7.9,1.58),(8.6,2.25))
ax.text(3.05,.65,'预算满 → 生产者等待；写入 ACK → 回收共享内存',fontsize=12)
save(fig,5,'同步与异步导出结构示意；节点位置不表示耗时')

# 06 ownership schematic.
fig,ax=plt.subplots(figsize=(11,4.6));ax.axis('off');ax.set(xlim=(0,11),ylim=(0,4.7))
ax.text(.2,4.3,'旧所有权：切片很小，底层存储仍属于整批环境',weight='bold')
box(ax,.3,2.85,4.0,1,'一帧 batch：8 环境','env0 | env1 | … | env7',GRAY)
box(ax,6.2,2.85,4.0,1,'某环境的一帧视图','仍引用整批 storage',RED)
arrow(ax,(6.2,3.35),(4.3,3.35),'保留引用')
ax.text(.2,2.15,'新所有权：CPU 帧按环境 clone，移交时逐帧释放',weight='bold')
box(ax,.3,.65,2.6,1,'环境 0 独占帧','不持有其他环境',TEAL)
box(ax,4.15,.65,2.6,1,'packed 共享内存','path / shape / dtype / offset',TEAL)
box(ax,8,.65,2.6,1,'worker 确认完成','close + unlink',TEAL)
arrow(ax,(2.9,1.15),(4.15,1.15),'复制 / 释放');arrow(ax,(6.75,1.15),(8,1.15),'写入 / ACK')
save(fig,6,'CPU 录制帧从跨环境视图到独占存储与共享内存移交的所有权变化')

# 07 schemas: runtime transport changes, external storage contract preserved.
fig,ax=plt.subplots(figsize=(11,5.4));ax.axis('off');ax.set(xlim=(0,11),ylim=(0,5.7))
box(ax,.2,4.15,3.1,1.1,'录制态','dict → list[frame]\nCPU 按环境独占 / GPU 小字段保留',BLUE)
box(ax,3.95,4.15,3.1,1.1,'传输态','连续共享内存 + leaves 描述符\n64 字节对齐，不 pickle 整条 RGB',TEAL)
box(ax,7.7,4.15,3.1,1.1,'存储态','/data/demo_i/*\ngzip-2 + h5py auto chunks',TEAL)
arrow(ax,(3.3,4.7),(3.95,4.7));arrow(ax,(7.05,4.7),(7.7,4.7))
rows=[('actions','[T, 7] · float32'),('obs/*_rgb','[T, 480, 640, 3] · uint8 · 三路'),('states / initial_state','机器人与物体状态；保持字段结构'),('processed_actions / obs','保持帧序与动作、观测对应'),('attributes','seed / success / num_samples；env_args / total')]
for i,(a,b) in enumerate(rows):
    y=3.55-i*.67
    ax.text(.35,y,a,fontfamily='monospace',fontsize=12)
    ax.text(4.2,y,b,fontsize=12)
    ax.plot([.3,10.7],[y-.24,y-.24],color='#dde5e9',lw=.8)
save(fig,7,'录制态、传输态和 HDF5 存储态的结构与外部字段契约')

# 08 measured additive windows, not sums of concurrent work.
fig,ax=plt.subplots(figsize=(11,3.5))
prod=[r['production_seconds'] for r in R]
tail=[r['final_ready_seconds']-r['production_seconds'] for r in R]
ax.barh(range(3),prod,color=BLUE,height=.52,label='首回合开始 → 最后回合完成')
ax.barh(range(3),tail,left=prod,color=ORANGE,height=.52,label='最后完成 → 最终文件就绪')
for i,r in enumerate(R):
    ax.text(prod[i]/2,i,f'{prod[i]:.1f}s',ha='center',va='center',color='white')
    ax.text(r['final_ready_seconds']+15,i,f"总计 {r['final_ready_seconds']:.1f}s",va='center')
ax.set_yticks(range(3),LABELS);ax.invert_yaxis();ax.set_xlabel('自首回合开始的墙钟时间（秒）')
ax.set_xlim(0,1430);ax.legend(loc='lower left',bbox_to_anchor=(0,1.02),frameon=False,ncol=2,fontsize=11)
save(fig,8,'生产阶段与收尾阶段构成的最终文件就绪时间；阶段互不重叠')

# 09 queue waits/drain/merge never added to production time.
fig,axes=plt.subplots(1,3,figsize=(11,3.8))
for ax,key,title in zip(axes,['queue_wait_seconds','drain_seconds','merge_seconds'],['累计入队等待','收尾排空','分片合并']):
    vals=[r['async_export'][key] if key=='queue_wait_seconds' else r['async_export']['complete'][key] for r in R[1:]]
    bars(ax,vals,'墙钟时间（秒）',['1 worker','2 workers'],[BLUE,TEAL],'.1f');ax.set_title(title)
save(fig,9,'异步模式的累计入队等待、排空与合并；三个图不构成可相加的总耗时')

# 10 resource facets: producer RSS != physical machine memory.
fig,axes=plt.subplots(1,3,figsize=(11,3.8))
bars(axes[0],[r['resource_summary']['peak_rss_bytes']/GIB for r in R],'峰值 RSS（GiB）',['同步','异步 1','异步 2'],COLORS,'.1f')
bars(axes[1],[r['sampled_cgroup_peak_current_bytes']/GIB for r in R],'采样峰值（GiB）',['同步','异步 1','异步 2'],COLORS,'.1f')
bars(axes[2],[next(iter(r['resource_summary']['device_peak_memory_used_mib'].values()))/1024 for r in R],'整卡显存峰值（GiB）',['同步','异步 1','异步 2'],COLORS,'.1f')
for ax,t in zip(axes,['生产进程 RSS','cgroup memory.current','整卡显存']):ax.set_title(t)
save(fig,10,'生产进程内存、cgroup 采样总量和整卡显存的不同测量口径')

# 11 offline and GPU have independent scales, each includes final-ready work.
fig,axes=plt.subplots(1,2,figsize=(11,3.6))
bars(axes[0],[r['episodes_per_minute'] for r in A['offline']],'最终就绪吞吐（条 / 分钟）',fmt='.3f')
bars(axes[1],[r['final_ready_per_minute'] for r in R],'最终就绪吞吐（条 / 分钟）',fmt='.3f')
axes[0].set_title('离线 4 条回放：双 worker +85.6%');axes[1].set_title('GPU 24 条生成：双 worker +29.8%')
save(fig,11,'离线回放与 GPU 生成收益分别展示，不能互相外推')

# 12 actual strict terminal quality, all modes fail the same case.
fig,axes=plt.subplots(1,2,figsize=(11,3.6),gridspec_kw={'width_ratios':[1.1,1]})
axes[0].barh(range(3),[23]*3,color=TEAL,label='严格终态通过')
axes[0].barh(range(3),[1]*3,left=[23]*3,color=RED,label='严格终态未通过')
axes[0].set_yticks(range(3),LABELS);axes[0].invert_yaxis();axes[0].set_xlim(0,24)
axes[0].set_xlabel('轨迹条数（每模式保存 24 条）');axes[0].set_xticks([0,6,12,18,24])
for i in range(3):axes[0].text(11.5,i,'23 通过',color='white',ha='center',va='center')
axes[0].legend(loc='lower left',bbox_to_anchor=(0,1.02),frameon=False,fontsize=11)
f=R[0]['failed_terminal_cases'][0]
ratios=[f['linear_speed_m_s']/.03,f['angular_speed_rad_s']/.5]
bars(axes[1],ratios,'终态速度 / 允许阈值（倍）',['线速度','角速度'],[RED,RED],'.2f')
axes[1].axvline(1,color=GRAY,linestyle='--');axes[1].set_title('共同失败轨迹 demo_2')
save(fig,12,'三种模式严格终态均为 23/24，通过结构校验不等于物理验收通过')

def figure(n, caption, source):
    return f'<figure id="fig-{n}">{FIGS[n]}<figcaption><b>图 {n:02d} · {caption}</b><br><span>{source}</span></figcaption></figure>'

def section(n,title,body):
    return f'<section id="s{n}"><div class="section-number">{n:02d}</div><h2>{title}</h2>{body}</section>'

def p(s):return '<p>'+s+'</p>'
def table(headers,rows):
    return '<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+h+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+str(c)+'</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table></div>'

body = '''<header><div class="eyebrow">AUTODATA / OPENARM · 实验与结构优化复盘</div><h1>让生成继续，<br>让导出并行。</h1><p class="lead">效率优化报告 · 2026 年 10 月 14 日</p><p>从导出瓶颈、录制内存所有权到有界共享内存，围绕 12 组图表梳理已完成的实验、数据结构改动和验收边界。</p></header>'''
body += '<div class="abstract"><h2>先看结果</h2>'+p('8 环境、每模式 24 条的已有 GPU 对照中，双写入进程将最终文件就绪时间从 <b>1156.74 秒缩短到 891.22 秒</b>，耗时减少 <b>23.0%</b>，对应吞吐提升 <b>29.8%</b>。生产进程峰值 RSS 从 <b>56.2 GiB 降到 40.7 GiB</b>。')+p('收益来自导出并行与内存所有权调整的组合。gzip-2、HDF5 字段、帧序和成功标签保持原有规则。严格物理回读在三种模式中均为 <b>23/24</b>，整体物理验收仍未通过；历史 100 条目标也未完成。')+'</div>'
body += figure(1,'生成收益已经体现在最终文件与完整启动耗时中','来源：evidence.json → async_validation.gpu.runs；吞吐分子为已记录并保存的 24 条，含 1 条严格终态未通过轨迹。')
body += '<nav aria-label="报告目录">'+''.join(f'<a href="#s{i}">{t}</a>' for i,t in enumerate(['实验进程','瓶颈定位','结构改动','耗时拆解','内存边界','交叉验证','质量验收','下一步'],1))+'</nav>'

body += section(1,'先把不同实验放回各自的问题里',
    figure(2,'从可运行到可扩展，验证问题逐步变化','来源：共享配置 v003 报告、local-runtime-validation.json、docs/process-log.md、async-export-validation.json；顺序为阶段示意，纵向间距不表示时间。')+
    p('共享配置探针回答“两端能否按同一规则启动和判断成功”；早期 1 环境与 4 环境测试回答“生成链路是否能产出可回读轨迹”。随后 8 环境、100 条目标运行暴露了规模问题：63 次开始、55 次完成，遥测成功 49、失败 6，剩余 8 次结果未知。子进程 SIGKILL，cgroup 的 oom_kill 增加 1，进程峰值 RSS 约 66.6 GiB。该 cgroup 包含其他进程，仅凭这些记录不能锁定受害进程。')+
    p('异步初版也出现过 SIGKILL 和 OOM 计数增加。之后才定位并修复跨环境 CPU 视图保留整批存储的问题。最终对照的三种模式各保存 24 条、32,959 帧，OOM 计数均没有增加。图中不同轮次不可合并成统一成功率，也不能把 24 条对照当作 100 条生产验收。'))

body += section(2,'导出瓶颈落在 RGB 建数据集阶段',
    figure(3,'单条回放：总导出 26.18 秒，建数据集 25.83 秒','来源：runtime/export-diagnosis.json；真实已保存轨迹 demo_0，1342 帧 / 相机；CPU 离线回放，非 GPU 在线传输测量。')+
    p('左图中，轨迹堆叠约 0.230 秒，CPU / NumPy 约 0.000334 秒，HDF5 flush 约 0.00419 秒；建数据集占总导出时间 98.7%。右图将三路 RGB 拆开，左腕、右腕和第三视角分别约 11.12、4.15、10.56 秒。优化应优先处理 RGB 的压缩与 chunk 写出成本。')+
    p('这里的 dataset_create 同时包含压缩、HDF5 处理和 I/O；它不是纯磁盘耗时。建数据集的线程 CPU 时间与墙钟接近，支持 CPU 计算成本较高的判断。离线数据已在 CPU，因此极短的 cpu_numpy 时间不能证明在线 GPU 传输没有成本。write_episode_inclusive 是嵌套计时，未加入阶段总和；flush 也不表示数据已物理落盘。')+
    figure(4,'换压缩可以更快，但会显著增加文件体积','来源：runtime/export-compression-demo0-full.json；1342 帧 × 三路 RGB；相同 chunk [84,30,80,1]，各方式仅一次测量。')+
    p('gzip-2 建数据集约 25.75 秒、输出约 525 MiB；LZF 约 16.98 秒、796 MiB；无压缩约 10.10 秒、3545 MiB。无压缩输出约为 gzip 的 6.75 倍。当前方案保留 gzip-2，把 CPU 写出移入独立进程，以控制存储增长和格式变更。')+
    p('另有 32 帧 × 三路 RGB、每方式 3 次的轮换顺序对照，可用于局部复核。文件写入字节数不同、页缓存可能已预热，差值不能精确隔离出 gzip 的纯耗时。无压缩连续存储的另一轮回放为 0.859 秒，但 chunk 策略也改变了，不能和图 4 当作同口径比较。'))

body += section(3,'改变内部所有权与传输结构，保留输出契约',
    figure(5,'同步路径被拆成生产者、有界队列和独立写入进程','来源：async_export.py、export_pool.py 静态核对；结构示意，不表示阶段时长。')+
    p('同步模式仍为默认入口。启用异步后，生产者把完成的回合打包到共享内存；队列只传路径、形状、dtype、偏移和元数据描述符。CPU worker 使用 spawn，各自拥有 HDF5 分片，避免多个进程共享一个活动 HDF5 句柄。提交时分配 demo ID，完成顺序不会重排同一回合的帧、动作和观测。')+
    p('队列按字节预算约束，排队和正在写入的共享内存都计入预算；满载时生产者等待，单条超过预算会明确失败。worker 写完并 ACK 后才释放共享内存。最终等待全部 ACK、关闭分片，再复制压缩组、核对结构与计数，并发布独立文件。失败时保留分片和清单供诊断。')+
    figure(6,'独占帧消除跨环境存储的意外保留','来源：async_export.py → owned_recording_method；export_pool.py → pack / poll；静态结构核对。')+
    p('旧录制方式先 clone 整个环境 batch，再把某环境的切片放入其回合。切片仍引用原 batch 的底层存储：一个环境仍需要该帧时，其他环境对应的存储也可能无法释放。异步新路径对 CPU 帧按环境 clone，建立独立所有权；移交时逐帧写入共享内存并释放原帧，周期性将 glibc 空闲页归还系统。')+
    p('对图 3 的 1342 帧轨迹，三路 640×480×3 uint8 RGB 的未压缩体积为 3,710,361,600 字节，约 3.46 GiB。这是按形状计算的 RGB 体积，不是 RSS 实测。一次多保留整条副本就可能新增数 GiB 压力。新路径避免生产者对整条 RGB 再做完整 stack；小型 GPU 状态字段仍按字段堆叠后一次转到 CPU，减少逐帧同步。')+
    figure(7,'变化集中在录制态和传输态，HDF5 仍可独立读取','来源：export_pool.py、async_export.py、离线结构与全值相等检查；T 表示各回合实际长度，不保证相同。')+
    table(['层级','主要改动','保留约束'],[
        ['配置与描述','共享 experiment 派生任务、embodiment、profile','配置探针验证接口；无效率倍率数据'],
        ['录制数据','CPU 帧按环境独占；移交中释放','维持原字段和值；GPU 小字段仍按批记录'],
        ['进程传输','连续共享内存 + leaves；64 字节对齐','无整条 RGB pickle；队列有内存上限'],
        ['最终存储','独立分片合并为一个 HDF5','format_version=1；gzip-2；auto chunks；无外链 / VDS'],
        ['观测与验收','submitted / saved / pending 分开','生成完成、写出完成、物理成功分别判断']]))

body += section(4,'必须把收尾时间算进最终收益',
    figure(8,'生成结束后仍有排空、合并和关闭工作','来源：async_validation.gpu.runs；生产与收尾为互斥墙钟区间；同步收尾约 1.65 秒、异步分别约 113.87 / 100.80 秒。')+
    table(['模式','生产时间 s','最终就绪 s','完整启动器 s','最终吞吐 条/min'],[
        [LABELS[i],f"{r['production_seconds']:.2f}",f"{r['final_ready_seconds']:.2f}",f"{r['launcher_wall_seconds']:.2f}",f"{r['final_ready_per_minute']:.3f}"] for i,r in enumerate(R)])+
    p('双 worker 的生产阶段吞吐提升约 46.1%，但最终文件吞吐提升为 29.8%，完整启动器吞吐提升为 28.3%。最终文件就绪从首回合开始计时，包含排空、合并和关闭；完整启动器还包含启动与结束。报告主结论使用最终文件口径，避免只看“生成结束”而遗漏导出尾部。')+
    figure(9,'第二个 worker 主要减少等待，单条写入并未变快','来源：async_export 累计指标与 export_complete；累计入队等待和收尾计时可能属于整体墙钟窗口，不与图 8 重复相加。')+
    p('单 worker 的累计入队等待约 222.43 秒，双 worker 为 80.96 秒；收尾排空从 104.95 秒降至 53.18 秒。单条 worker 写出均值却接近：26.63 与 26.83 秒。观察支持“通过并行提高服务能力、减少阻塞”的解释，而不是单次压缩算法提速。')+
    p('双 worker 的合并耗时反而从 7.09 秒升至 44.42 秒。现有单轮记录无法确定原因，分片布局、缓存和系统 I/O 状态均需进一步测量。两种模式都要计入合并，后续增加 worker 也必须同时观察排空与合并，而不是假设吞吐线性增长。'))

body += section(5,'内存收益成立，但队列预算不是整机上限',
    figure(10,'RSS、cgroup 与显存分别观察','来源：resource_summary、sampled_cgroup_peak_current_bytes；单位统一 GiB。RSS 为生产进程；cgroup 可能含其他进程；显存为整卡。')+
    p('生产进程峰值 RSS 为 56.2 / 40.5 / 40.7 GiB，双 worker 相对同步下降约 27.6%。cgroup 采样峰值约 56.0 / 40.1 / 41.4 GiB，是另一种范围与采样口径，不能与进程 RSS 或队列内存相加。最终三轮 OOM 计数增量均为 0。')+
    p('异步队列峰值为 14.44 GiB，低于 16 GiB 配置上限，占约 90.2%。这个预算包含待写和在写共享载荷，不包含活跃环境的录制缓冲、模拟器、worker 私有内存和系统缓存。多个进程 RSS 还可能重复统计共享页，因此评估物理压力应结合 cgroup 与系统可用内存。')+
    p('整卡显存峰值从约 15.6 GiB 升至约 18.5 GiB。它不是当前进程独占显存，现有记录不足以将增长完全归因于某个代码改动。方案减少了 CPU 内存保留，却没有证明所有资源占用均下降。部署时仍须预留 /dev/shm 和系统内存，并持续观察显存。'))

body += section(6,'离线回放验证搬运，GPU 对照验证在线收益',
    figure(11,'离线导出更快，不等于在线生成能取得同样倍率','来源：async_validation.offline 与 gpu.runs；各模式离线 4 条、GPU 24 条，均计入最终文件就绪；坐标轴独立。')+
    p('离线 4 条固定数据：同步、单 worker、双 worker 最终就绪分别为 105.13、105.45、56.66 秒。单 worker 提交只需约 4.58 秒，但最终文件没有变快；只计提交时长会显著夸大收益。双 worker 离线吞吐提升约 85.6%，在线收益为 29.8%，因为仿真、规划、执行和录制也占用时间。')+
    table(['证据','已验证','不能据此推断'],[
        ['离线固定 4 条 / 每模式','全值、属性、shape、dtype、chunk、压缩和组结构一致','完整 GPU 仿真轨迹等价'],
        ['真实单条所有权移交','全 RGB 与非 RGB 相等；删分片后原 loader 可读取','所有在线 RGB 均逐值跨模式相同'],
        ['GPU 24 条 / 每模式','相同源 / 任务哈希；每模式 32,959 帧；异步各 672 个非 RGB 数据集逐位一致','不同渲染运行的所有 RGB 逐位一致'],
        ['源码溯源','当前 11 个实现文件哈希与验证记录匹配','当前机器重新运行仍取得同样结果']])+
    p('每种 GPU 模式目前只有一轮正式对照，存在执行顺序、页缓存和系统负载差异，且没有误差条或多轮统计区间。29.8% 是这组记录的描述性结果；同步与异步同时改变导出调度和 CPU 帧所有权，现有证据不能单独量化两项改动各自的因果贡献。'))

body += section(7,'格式兼容已经验证，物理质量仍有缺口',
    figure(12,'相同失败样本使质量问题可定位，也阻止整体验收通过','来源：async_validation.gpu.runs.failed_terminal_cases；原严格检查阈值：线速度 ≤0.03 m/s、角速度 ≤0.5 rad/s。')+
    p('三种模式都标记并保存 24 条成功轨迹，HDF5 格式检查通过；严格最终状态检查都只有 23 条通过。共同失败的 demo_2 已在垫内、夹爪已释放，但终态线速度约 0.2108 m/s、角速度约 5.7481 rad/s，分别约为允许阈值的 7.03 与 11.50 倍。成功标签与最终物理状态出现不一致，须在接受数据前解决。')+
    p('这个结果说明失败在三个模式中共同存在，且非 RGB 对照没有发现异步搬运改变轨迹数据；它不等于证明所有物理与标注质量都已正确。这里未修改阈值、轨迹数据或成功标签，也未把未通过样本剔除后重新包装成全量通过。')+
    p('源数据来自 replay fixture，阶段标注为推断结果，未经过人工审核。被动右腕视角在该左臂任务中可能接近黑图，结构有效不等于视觉信息充足。右臂没有实际可用生成源，因此本报告不包含右臂生成成功结论。历史共享配置 v003 的源文件当前也不齐全，其探针结果保留为历史证据。'))

body += section(8,'下一轮先闭合质量与规模验收，再扩展并行度',
    table(['顺序','工作','判断依据'],[
        ['1 · 修复质量闭环','定位 demo_2 的成功判断、最终保持与录制终点；新增证据保留旧记录','严格终态全量通过；成功标签与回读一致；阈值不放宽'],
        ['2 · 重跑规模目标','在独立 GPU 环境用新路径执行 100 条目标；默认同步仍可回退','生成数、submitted、saved、文件回读一致；排空合并完成；资源无异常'],
        ['3 · 验证收益稳定性','轮换 0 / 1 / 2 worker 顺序，增加重复；记录负载与缓存条件','分别报告生产、最终文件、完整启动器吞吐和波动'],
        ['4 · 继续优化尾部','检查分片布局、合并 I/O、背压与 16 GiB 队列余量','在同样质量和压缩条件下减少排空 / 合并总尾部'],
        ['5 · 再评估格式策略','仅在存储预算明确后评估 LZF / chunk 调整','同时比较写入、体积、训练读取和旧 loader 兼容性']])+
    p('基于当前单组对照，双 worker 是后续验证的候选配置：8 环境、16 GiB 导出队列、600 秒超时、gzip-2。它还不是百条生产验收通过的配置。共享配置与版本整理降低了复现和排查的复杂度，但没有独立工时测量，本报告不为这类改动虚构百分比收益。'))

body += '<section id="sources"><div class="section-number">附录</div><h2>统计口径与证据入口</h2>'
body += table(['指标','计算 / 边界'],[
    ['最终就绪吞吐','已记录成功并保存条数 × 60 / 首回合开始至 output_ready 的秒数；本组分子 24'],
    ['吞吐提升','基线耗时 / 新耗时 − 1；最终就绪为 29.8%，完整启动器为 28.3%'],
    ['耗时下降','1 − 新耗时 / 基线耗时；最终就绪为 23.0%，完整启动器为 22.1%'],
    ['合格条数','独立严格最终状态回读为 23 / 模式；不能以 telemetry success 替代'],
    ['帧 / 秒','每模式 32,959 / 最终就绪秒数：28.49 / 32.24 / 36.98'],
    ['内存单位','GiB = 2³⁰ bytes；MiB = 2²⁰ bytes；峰值为已有采样记录'],
    ['重叠时间','不累加并发回合墙钟；不累加嵌套 write_episode；累计 queue_wait 不再加入最终时间']])
body += p('本报告仅整理已有本地记录并核对当前源码，未新增 GPU 仿真、训练或大文件全量扫描。原实验格式 / 全值 / 物理校验结论均注明来源，报告生成检查不替代运行验收。数据截止北京时间 2026-10-14。')
body += '<details><summary>查看 28 个来源文件及 SHA256</summary>'+table(['来源（相对工作区根目录）','SHA256'],[[f'<a href="../../../{html.escape(s["path"])}">{html.escape(s["path"])}</a>',f'<code>{s["sha256"]}</code>'] for s in E['sources']])+'</details>'
body += '<p><a href="evidence.json">完整结构化证据快照</a> · <a href="build_report.py">图表与报告生成源</a> · <a href="verification.json">报告检查记录</a> · <a href="manifest.json">版本与文件校验清单</a></p></section>'
body += '<footer>AutoData 效率优化报告 · v001 · 本地研究报告，未发布</footer>'

css = '''
:root{color-scheme:light;--ink:#203745;--muted:#576e7c;--line:#dbe4e9;--accent:#21867e}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;color:var(--ink);background:#edf2f4;font-family:"Noto Sans CJK SC","Microsoft YaHei",sans-serif;font-size:16px;line-height:1.9}
main{max-width:1120px;margin:32px auto;background:white;padding:64px 72px}header{padding:0 0 36px;border-bottom:2px solid var(--ink)}.eyebrow{font-size:13px;letter-spacing:.12em;color:var(--accent)}h1{font-size:54px;line-height:1.25;letter-spacing:-.03em;margin:24px 0}h2{font-size:27px;line-height:1.5;margin:8px 0 24px}.lead{font-size:21px;color:var(--muted)}p{margin:18px 0}b,strong{font-weight:700}.abstract{padding:28px 0 8px}.abstract h2{font-size:20px;margin:0}nav{display:flex;flex-wrap:wrap;gap:12px 26px;padding:20px 0;border-block:1px solid var(--line)}a{color:#276b86;text-decoration-thickness:1px;text-underline-offset:3px}section{margin-top:64px;scroll-margin-top:20px}.section-number{font-size:13px;color:var(--accent);letter-spacing:.15em}figure{margin:30px 0 32px;break-inside:avoid}figure svg{display:block;width:100%;height:auto}figcaption{font-size:14px;line-height:1.7;border-top:1px solid var(--line);padding:12px 0 0}figcaption span{color:var(--muted)}.table-wrap{overflow:auto;margin:24px 0}table{border-collapse:collapse;width:100%;font-size:14px;line-height:1.7}th,td{padding:12px 13px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{background:#f1f5f7;font-weight:700}td code{font-size:12px;overflow-wrap:anywhere}td a{overflow-wrap:anywhere}details{margin:26px 0}summary{cursor:pointer;font-weight:700}footer{margin-top:56px;padding-top:20px;border-top:1px solid var(--line);font-size:13px;color:var(--muted)}
@media(max-width:700px){body{font-size:16px}main{margin:0;padding:28px 18px}h1{font-size:38px}h2{font-size:24px}section{margin-top:48px}th,td{padding:10px 7px}figure{margin:22px 0}figure svg{min-width:620px}figure{overflow-x:auto}figcaption{min-width:0}nav{gap:10px 18px}}
@media print{@page{size:A4;margin:15mm 12mm}body{background:white;font-size:10.5pt;line-height:1.75}main{margin:0;padding:0;max-width:none}h1{font-size:34pt}h2{font-size:18pt;break-after:avoid}.section-number{break-after:avoid}header{padding-bottom:20px}section{margin-top:24px}figure{margin:18px 0;break-inside:avoid}figure svg{min-width:0;width:100%}figcaption{font-size:9pt}table{font-size:9pt}tr{break-inside:avoid}.table-wrap{overflow:visible}nav{display:none}details{display:block}details:not([open])>:not(summary){display:none}a{color:inherit}p{orphans:3;widows:3}footer{font-size:9pt}}
'''
page='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AutoData 效率优化报告 · v001</title><style>'+css+'</style></head><body><main>'+body+'</main></body></html>'
(HERE/'index.html').write_text(page)
print('Rendered report with',len(FIGS),'figures')
