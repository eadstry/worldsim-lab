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
print('8 figures (PNG/SVG) and charts.pdf generated')
