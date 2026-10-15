"""Rebuild figures from the bundled data.json; requires matplotlib, no simulation runtime."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.font_manager import FontProperties
import numpy as np
P=Path(__file__).resolve().parent
D=json.loads((P/'data.json').read_text()); R=D['latest']; labels=[r['label'] for r in R]
plt.rcParams.update({'font.family':'Noto Sans CJK JP','axes.unicode_minus':False,'font.size':11,'axes.spines.top':False,'axes.spines.right':False,'figure.facecolor':'#f7f9fc','axes.facecolor':'#f7f9fc','axes.titleweight':'bold','savefig.facecolor':'#f7f9fc'})
colors=['#697586','#197c88','#345bc4','#8b5db7']; (P/'figures').mkdir(exist_ok=True)
pdf=PdfPages(P/'charts.pdf')
def save(fig,name):
 fig.tight_layout(pad=2);fig.savefig(P/'figures'/f'{name}.png',dpi=160);fig.savefig(P/'figures'/f'{name}.svg');pdf.savefig(fig);plt.close(fig)
def bars(ax,values,title,unit):
 bars=ax.bar(labels,values,color=colors);ax.set_title(title,loc='left');ax.set_ylabel(unit);ax.set_ylim(0,max(values)*1.22)
 for b,v in zip(bars,values): ax.text(b.get_x()+b.get_width()/2,v+max(values)*.025,f'{v:.2f}',ha='center')
 ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
fig,axs=plt.subplots(1,3,figsize=(15,6))
blocks=[('同步 · workers=0','保留原 recorder 导出','episode 完成\n↓\n主进程压缩 + 写 HDF5\n↓\n继续生成','主流程承担保存等待'),('固定上限 · 4 / 8','ExportPool._scale_workers','pending 有积压\n↓\ndesired = min(pending, cap)\n↓\n按需启动 CPU writer','本轮两种上限均启动 4 个'),('auto','ResourceGovernor.decide','pending 有积压\n↓\nCPU / 内存 / I/O 等准入\n↓\n通过：增加 1 个 writer','至少间隔 1 秒；不主动缩容')]
for ax,(title,sub,body,note),c in zip(axs,blocks,colors):
 ax.axis('off');ax.set_title(title,loc='left',fontsize=16);ax.text(.02,.83,sub,transform=ax.transAxes,fontsize=12,color=c);ax.text(.02,.63,body,transform=ax.transAxes,va='top',fontsize=14,linespacing=1.9);ax.text(.02,.05,note,transform=ax.transAxes,fontsize=12)
fig.suptitle('00  代码差别在导出路径和扩容决策，共用 cuRobo v1 生成任务',fontsize=16);save(fig,'00-code-methods')
fig,axs=plt.subplots(1,3,figsize=(15,5))
for ax,key,title in zip(axs,['motion_plan','execution_wait','export_enqueue'],['运动规划','执行 / 等待','主流程保存：同步导出 → 异步入队']):
 vals=[r['stages'][key] for r in R]
 if key=='export_enqueue':vals[0]=R[0]['stages']['export']
 ax.bar(labels,vals,color=colors);ax.set_title(title,loc='left',fontsize=12);ax.set_ylabel('秒 / 已完成 episode');ax.set_ylim(0,max(vals)*1.25)
 for i,v in enumerate(vals):ax.text(i,v+max(vals)*.03,f'{v:.2f}',ha='center')
 change=(vals[-1]/vals[0]-1)*100;ax.text(.5,.91,f'auto 相对同步 {change:+.1f}%',transform=ax.transAxes,ha='center')
fig.text(.03,.01,'各组 17 个完成样本（含 1 个失败）；右图两端工作不同，反映主流程负担而非后台写入加速。',fontsize=10);save(fig,'09-stage-change')
fig,axs=plt.subplots(1,2,figsize=(12,5));x=np.arange(3);names=labels[1:]
for offset,key,name,c in [(-.18,'packing_seconds','打包累计','#345bc4'),(.18,'queue_wait_seconds','预算等待累计','#e8aa46')]:
 vals=[r['internal'][key] for r in R[1:]];bs=axs[0].bar(x+offset,vals,.36,label=name,color=c);axs[0].bar_label(bs,fmt='%.2f',padding=3)
axs[0].set_xticks(x,names);axs[0].set_ylabel('整轮累计 / 秒');axs[0].set_ylim(0,36);axs[0].legend();axs[0].set_title('10  主流程数据移交开销',loc='left')
for offset,key,name,c in [(-.18,'mean','均值','#197c88'),(.18,'p95','P95','#8b5db7')]:
 vals=[r['internal']['write_seconds'][key] for r in R[1:]];bs=axs[1].bar(x+offset,vals,.36,label=name,color=c);axs[1].bar_label(bs,fmt='%.2f',padding=3)
axs[1].set_xticks(x,names);axs[1].set_ylabel('后台单条写入 / 秒');axs[1].set_ylim(0,43);axs[1].legend();axs[1].set_title('后台保存依然需要约 27–28 秒 / 条',loc='left');fig.text(.03,.01,'右图每组 16 个保存事件；后台并发耗时不能与左图相加为墙钟时间。',fontsize=10);save(fig,'10-async-cost')
fig,ax=plt.subplots(figsize=(11,5));bottom=np.zeros(3)
for key,name,c in [('drain_seconds','排空 + writer 退出','#345bc4'),('merge_seconds','合并事件阶段（含清理）','#e8aa46'),('other','其他收尾间隔','#697586')]:
 vals=np.array([r[key] if key!='other' else r['tail_seconds']-r['drain_seconds']-r['merge_seconds'] for r in R[1:]]);assert min(vals)>=0
 ax.barh(names,vals,left=bottom,label=name,color=c)
 for i,v in enumerate(vals):
  if v>4:ax.text(bottom[i]+v/2,i,f'{v:.2f}s',ha='center',va='center')
 bottom+=vals
ax.invert_yaxis();ax.set_xlabel('整批收尾墙钟时间 / 秒');ax.set_xlim(0,90);ax.set_title('11  auto 的合并阶段抵消了生成区间的领先',loc='left');ax.legend(loc='lower right',fontsize=9);fig.text(.03,.01,'区间：最后 episode 完成 → output_ready。其他间隔为差值，并非独立埋点；同步收尾仅 1.68 秒。',fontsize=10);save(fig,'11-tail-detail')

fig,ax=plt.subplots(1,2,figsize=(12,4.8));bars(ax[0],[r['seconds']/60 for r in R],'01  最终就绪时间 ↓','分钟 / 16 条');bars(ax[1],[r['rate'] for r in R],'最终就绪吞吐 ↑','条 / 分钟');fig.suptitle('8 环境 · seed 101 · cuRobo v1 · 单轮观测',fontsize=12);save(fig,'01-throughput')
fig,ax=plt.subplots(figsize=(11,4.8));x=np.arange(4);bottom=np.zeros(4)
for key,name,c in [('generation_seconds','首条开始 → 最后完成','#197c88'),('tail_seconds','最后完成 → 最终就绪','#e8aa46')]:
 vals=np.array([r[key] for r in R]);ax.barh(x,vals,left=bottom,label=name,color=c)
 for i,v in enumerate(vals):ax.text(bottom[i]+v/2,i,f'{v:.1f}s',ha='center',va='center',fontsize=10)
 bottom+=vals
ax.set_yticks(x,labels);ax.invert_yaxis();ax.set_xlabel('墙钟时间（秒）');ax.set_title('02  生成结束不等于数据可用',loc='left');ax.legend(loc='lower right');save(fig,'02-tail')
fig,ax=plt.subplots(figsize=(11,5));bottom=np.zeros(4)
for k,name,c in [('execution_wait','执行 / 等待','#197c88'),('export','同步导出','#e8aa46'),('export_enqueue','异步入队','#8b5db7'),('motion_plan','规划','#345bc4'),('reset','重置','#697586')]:
 v=np.array([r['stages'][k] for r in R]);ax.barh(labels,v,left=bottom,label=name,color=c);bottom+=v
ax.invert_yaxis();ax.set_xlabel('每个已完成 episode 的阶段均值（秒）');ax.set_title('03  阶段耗时：执行等待和同步导出下降',loc='left');ax.legend(ncol=3,loc='lower right');fig.text(.04,.01,'并行 episode 的耗时会重叠；此图不等于整批墙钟时间，也不覆盖所有未计时开销。',fontsize=10);save(fig,'03-stages')
fig,ax=plt.subplots(2,1,figsize=(11,7),sharex=True)
for r,c in zip(R,colors):
 pts=r['gpu_trace'];ax[0].plot([p['seconds']/60 for p in pts],[p['gpu'] for p in pts],lw=1,alpha=.8,color=c,label=f"{r['label']} · 均值 {r['gpu_mean']:.1f}%")
 ax[1].scatter(r['seconds']/60,r['gpu_mean'],color=c,s=100);ax[1].annotate(r['label'],(r['seconds']/60,r['gpu_mean']),xytext=(8,4),textcoords='offset points')
ax[0].set_title('04  GPU 利用率：提高，但没有持续饱和',loc='left');ax[0].set_ylabel('设备利用率 %');ax[0].set_ylim(0,100);ax[0].legend(ncol=2);ax[1].set_ylabel('时间加权均值 %');ax[1].set_xlabel('分钟（上图：从首条开始；下图：最终就绪耗时）');ax[1].set_ylim(0,60);fig.text(.04,.01,'均值采用首条开始至 output_ready 内有效采样的左保持时间加权；设备级指标包含其他进程。',fontsize=9);save(fig,'04-gpu')
fig,ax=plt.subplots(figsize=(11,4.8));x=np.arange(4);w=.32
for offset,values,name,c in [(-w/2,[r['successes']/(r['successes']+r['failures'])*100 for r in R],'生成成功率（16 / 17）','#345bc4'),(w/2,[r['physical_passes']/16*100 for r in R],'保存数据末态检查通过率（16 / 16）','#197c88')]:
 b=ax.bar(x+offset,values,w,label=name,color=c);ax.bar_label(b,fmt='%.1f%%',padding=3)
ax.set_xticks(x,labels);ax.set_ylim(0,125);ax.set_ylabel('%');ax.set_title('05  本轮提速未伴随已测末态通过率下降',loc='left');ax.legend(loc='upper center',ncol=2);save(fig,'05-quality')
fig,ax=plt.subplots(1,2,figsize=(12,5))
e=D['early'];rates=[r['final_ready_per_minute'] for r in e];ax[0].plot([0,1,2],rates,marker='o',color='#197c88');ax[0].set_xticks([0,1,2],['同步','1 writer','2 writers']);ax[0].set_ylim(0,2);ax[0].set_ylabel('条 / 分钟');ax[0].set_title('06  早期 24 条完整生产：+29.8%',loc='left')
for i,v in enumerate(rates):ax[0].annotate(f'{v:.3f}',(i,v),xytext=(0,10),textcoords='offset points',ha='center')
o=D['offline'];ax[1].bar(['同步','1 writer','2 writers'],[r['final_ready_seconds'] for r in o],color=['#697586','#197c88','#345bc4']);ax[1].set_ylabel('4 条最终就绪时间 / 秒');ax[1].set_title('离线保存：单 writer 只是更早返回',loc='left')
for i,r in enumerate(o):ax[1].text(i,r['final_ready_seconds']+2,f"{r['final_ready_seconds']:.1f}s",ha='center')
ax[1].set_ylim(0,130);fig.text(.04,.01,'左：三个模式均为 24 条记录成功、23 条末态通过；右：CPU 离线回放，不能当作 GPU 生产吞吐。',fontsize=10);save(fig,'06-history')
fig,ax=plt.subplots(figsize=(10,5))
for r,c in zip(D['compression'],['#345bc4','#697586','#197c88']):
 x=r['output_bytes']/1e9;y=r['create_wall_seconds'];ax.scatter(x,y,s=160,color=c);ax.annotate(f"{r['compression']}\n{x:.2f} GB · {y:.2f}s",(x,y),xytext=(12,0),textcoords='offset points')
ax.set_xlim(0,4.8);ax.set_ylim(0,33);ax.set_xlabel('输出体积（十进制 GB）');ax.set_ylabel('dataset create 耗时（秒）');ax.set_title('07  压缩策略：速度与体积的取舍',loc='left');fig.text(.04,.01,'1342 帧 / 相机的离线 RGB 回放，保持 chunk 可比，单轮；含压缩、HDF5 和 I/O，非完整生产。',fontsize=10);save(fig,'07-compression')
fig,ax=plt.subplots(figsize=(12,5));ax.axis('off');ax.set_xlim(0,12);ax.set_ylim(0,5)
def box(x,y,text,c):ax.text(x,y,text,ha='center',va='center',bbox=dict(boxstyle='round,pad=.65',facecolor=c,edgecolor='none'),fontsize=11,color='white')
for y,title in [(3.7,'改进前：生成主流程等待导出'),(1.5,'改进后：生成与保存重叠')]:ax.text(.1,y+1,title,fontsize=13,fontweight='bold')
for x,y,t,c in [(1.3,3.7,'仿真 / 录制','#197c88'),(4.5,3.7,'同步压缩 + HDF5','#697586'),(8,3.7,'下一条生成','#197c88'),(1.3,1.5,'仿真 / 录制','#197c88'),(4.5,1.5,'独立帧所有权\n有界共享内存队列','#8b5db7'),(8,1.5,'多个 CPU writer\n压缩 + 分片保存','#345bc4'),(10.8,1.5,'排空 / 合并\n最终就绪','#697586')]:box(x,y,t,c)
for y,pairs in [(3.7,[(2.4,3.1),(6,6.8)]),(1.5,[(2.4,3.1),(6,6.6),(9.3,9.8)])]:
 for a,b in pairs:ax.annotate('',xy=(b,y),xytext=(a,y),arrowprops=dict(arrowstyle='->',color='#697586',lw=2))
ax.text(.1,.1,'机制图，无时间比例。质量判定保持独立；异步提交完成不能代替最终文件就绪。',fontsize=10);save(fig,'08-flow')

pdf.close()
print('12 figures (PNG/SVG) and charts.pdf generated')
