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
fig,axs=plt.subplots(3,1,figsize=(12,8))
items=[('同步保存 · workers=0',['生成轨迹','主流程压缩 / 写入','保存完成','继续生成'],'同一主流程承担保存等待','#697586'),('异步单 writer',['生成轨迹','提交队列','后台串行保存','排空 / 合并'],'提交后可继续生成；保存侧仍只有一个执行者','#197c88'),('异步多 writer / auto',['生成轨迹','有界共享内存队列','多个 writer 写分片','排空 / 合并'],'生成与保存重叠；队列满时等待预算，最终仍需合并','#345bc4')]
for ax,(title,nodes,note,c) in zip(axs,items):
 ax.axis('off');ax.set_xlim(0,12);ax.set_ylim(0,2);ax.set_title(title,loc='left',fontsize=13)
 for i,label in enumerate(nodes):
  x=1.3+i*3;ax.text(x,1.15,label,ha='center',va='center',fontsize=11,bbox=dict(boxstyle='round,pad=.55',fc=c,ec='none'),color='white')
  if i<3:ax.annotate('',xy=(x+2,1.15),xytext=(x+1,1.15),arrowprops=dict(arrowstyle='->',color='#697586',lw=1.5))
 ax.text(.1,.15,note,fontsize=11)
fig.suptitle('15  保存机制的串并行对照：所有生产配置仍使用 8 个仿真环境',fontsize=14)
fig.text(.03,.01,'控制流示意，无耗时比例。异步提交后生成可继续，后台保存同时推进；不是三个版本的实测时间线。',fontsize=10)
save(fig,'15-serial-parallel')

fig,ax=plt.subplots(figsize=(13,6));ax.axis('off');ax.set_xlim(0,13);ax.set_ylim(0,6)
lanes=[(.7,'生成主进程'),(2.7,'共享内存'),(4.7,'CPU writer')]
for y,label in lanes:ax.text(.1,y+.25,label,fontsize=13,fontweight='bold');ax.plot([2.1,12.6],[y,y],color='#c4ccd7',lw=1)
def node(x,y,text,c):ax.text(x,y,text,ha='center',va='center',fontsize=10,bbox={'boxstyle':'round,pad=.55','fc':c,'ec':'none'},color='white')
node(3,.7,'独立 CPU 帧\n预算检查','#197c88');node(5,.7,'pack + 释放源帧','#197c88');node(5,2.7,'布局 + 数组缓冲区','#8b5db7');node(7.8,4.7,'只读映射\n写分片 + flush','#345bc4');node(10,.7,'接收 saved\nclose + unlink','#197c88');node(11.8,2.7,'预算归还','#8b5db7')
for a,b in [((3.9,.7),(4.1,.7)),((5,1),(5,2.2)),((5.9,2.7),(7.5,4.2)),((8.3,4.2),(9.8,1.2)),((10.8,1),(11.6,2.3))]:ax.annotate('',xy=b,xytext=a,arrowprops={'arrowstyle':'->','color':'#59677a','lw':1.8})
ax.text(7,3.2,'传名称与布局',fontsize=10);ax.text(9.2,3.2,'saved 回执',fontsize=10);ax.set_title('12  数据所有权与回收：必须等 writer 确认后才能释放',loc='left',fontsize=15);fig.text(.03,.01,'示意图，无时间比例；队列预算不足会等待回执，writer 写入可与下一条生成重叠。',fontsize=10);save(fig,'12-memory-lifecycle')
fig,axs=plt.subplots(1,3,figsize=(15,6))
items=[('输入适配','原机器人配置深拷贝\nee_link → tool_frames\nretract_config →\ndefault_joint_position\n\n目标 / 物体 → 基座系\n开闭夹爪参数原地更新'),('规划与接触','MotionPlanner.plan_pose\nGoalToolPose 目标\n\n搬运时附着物体\n接触阶段临时调整碰撞\nfinally 恢复 / detach'),('输出适配','get_interpolated_plan\n读取稠密执行轨迹\n\n按 joint_names 重排\n可选关节距离重采样\nFK → 世界系末端位姿')]
for ax,(title,body),c in zip(axs,items,['#197c88','#345bc4','#8b5db7']):
 ax.axis('off');ax.set_title(title,loc='left',fontsize=16,color=c);ax.text(0,.86,body,va='top',transform=ax.transAxes,fontsize=13,linespacing=1.8)
fig.suptitle('13  cuRobo v2：保留 AutoData 任务契约，适配模型、规划与轨迹接口',fontsize=15);fig.text(.03,.01,'8 个环境各有规划对象；不把样条控制点直接执行，也不把规划成功等同于最终数据合格。',fontsize=10);save(fig,'13-v2-adapter')

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

if 'v2_rerun' in D:
 v=D['v2_rerun'];old=R[-1];fig,axs=plt.subplots(1,3,figsize=(15,5));names=['v1 auto\n10 月 14 日','v2 auto\n10 月 15 日']
 vals=[old['seconds'],v['seconds']];bs=axs[0].bar(names,vals,color=['#8b5db7','#197c88']);axs[0].bar_label(bs,fmt='%.1f',padding=4);axs[0].set_ylim(0,max(vals)*1.2);axs[0].set_ylabel('首条开始 → output_ready / 秒');axs[0].set_title('14  完整文件就绪',loc='left')
 keys=['motion_plan','execution_wait','export_enqueue'];x=np.arange(3)
 for offset,r,label,c in [(-.18,old,'v1 auto','#8b5db7'),(.18,v,'v2 auto 新实验','#197c88')]:
  vals=[r['stages'][k] if label=='v1 auto' else r['stages'][k]['mean'] for k in keys];bs=axs[1].bar(x+offset,vals,.36,label=label,color=c);axs[1].bar_label(bs,fmt='%.1f',padding=3,fontsize=9)
 axs[1].set_xticks(x,['规划','执行等待','入队']);axs[1].set_ylabel('秒 / 已完成 episode');axs[1].legend(fontsize=9);axs[1].set_title('内部阶段均值',loc='left');axs[1].margins(y=.25)
 axs[2].axis('off');axs[2].text(.02,.9,f"新实验检查（末态未全通过）\n\n生成成功：{v['successes']} / {v['completed']}\n最终保存：{v['saved_episodes']} 条\n末态通过：{v['physical_passes']} / {v['saved_episodes']}\n实际 writer：{v['writers']}\n记录成功：{v['rate']:.3f} 条 / 分钟\n末态合格：{v['terminal_passes_per_minute']:.3f} 条 / 分钟",va='top',fontsize=13,linespacing=1.8)
 fig.text(.03,.01,'跨日期单轮观测，缓存 / 热身 / 系统状态未控制一致；不能将差值单独归因于版本升级。',fontsize=10);save(fig,'14-v2-result')

# Conceptual diagrams: no measured scheduling implied.
from matplotlib.patches import FancyBboxPatch

def panel(title,h=7):
 fig,ax=plt.subplots(figsize=(14,h));ax.set_xlim(0,14);ax.set_ylim(0,10);ax.axis('off');ax.set_title(title,loc='left',fontsize=17,pad=15);return fig,ax

def node(ax,x,y,w,h,t,c='#197c88',fs=12):
 ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=.08',fc=c,ec='none',alpha=.96));ax.text(x+w/2,y+h/2,t,ha='center',va='center',color='white',fontsize=fs,linespacing=1.5)

def arrow(ax,a,b,label=''):
 ax.annotate('',xy=b,xytext=a,arrowprops=dict(arrowstyle='->',lw=1.7,color='#697586'))
 if label:ax.text((a[0]+b[0])/2,(a[1]+b[1])/2+.15,label,ha='center',fontsize=10)

fig,ax=panel('16  一台机器里的三层并行：协程、GPU 计算、CPU 进程')
node(ax,.3,7.6,8.2,1.4,'一个生成主进程\n8 个 asyncio 环境任务 + 每环境 planner','#345bc4',15)
node(ax,.3,4.8,3.7,1.5,'同步调用规划器\n准备世界状态 / 提交计算','#345bc4')
node(ax,4.8,4.8,3.7,1.5,'凑齐 8 份动作\n一次 env.step(actions)','#345bc4')
arrow(ax,(2.2,7.6),(2.2,6.3));arrow(ax,(6.6,7.6),(6.6,6.3))
node(ax,.3,1.7,8.2,1.65,'GPU：规划数值计算 / 批量仿真 / 渲染\n内部线程处理批量数据；跨请求重叠尚未测量','#197c88',14)
arrow(ax,(2.2,4.8),(2.2,3.35));arrow(ax,(6.6,4.8),(6.6,3.35))
node(ax,9.5,7.6,4.1,1.4,'CPU 打包 → 有界共享内存\n移交 episode 数据','#8b5db7')
arrow(ax,(8.5,8.3),(9.5,8.3))
for i in range(4):node(ax,9.5+(i%2)*2.15,3.7+(i//2)*1.45,1.95,1.15,f'CPU writer {i+1}\n压缩 + 分片',fs=11)
arrow(ax,(11.5,7.6),(11.5,6.3),'名称 / 布局')
node(ax,9.5,1.7,4.1,1.2,'ACK → 回收内存\n最终排空 / 合并','#697586');arrow(ax,(11.5,3.7),(11.5,2.9))
ax.text(.3,.45,'架构示意：8 环境不是 8 个 GPU 进程；本轮异步组实际均为 4 个 CPU writer。',fontsize=12)
save(fig,'16-process-gpu')

fig,ax=panel('17  环境在动作屏障汇合；GPU 在计算内部展开并行',8)
ax.text(.2,9.35,'主进程：每个环境提交动作后 await queue.join()，让出事件循环',fontsize=13)
for i in range(8):
 x=.25+i*1.7;node(ax,x,7.65,1.45,.95,f'env {i}',fs=12);arrow(ax,(x+.72,7.65),(x+.72,6.65))
node(ax,.25,5.55,13.35,1.05,'动作队列：等到 qsize == num_envs → 按 env_id 填入 actions','#8b5db7',14)
ax.text(.3,6.95,'缺一份动作就等待：慢任务可能影响整批推进',fontsize=12,color='#8b5db7')
arrow(ax,(6.9,5.55),(6.9,4.9));node(ax,.25,3.8,13.35,1.1,'一次 env.step(actions) → 返回 → 8 次 task_done → 环境继续','#345bc4',14)
node(ax,.25,.9,5.4,1.65,'一次规划调用\nPython 入口同步调用\nGPU 内部按批量数值运算展开','#197c88',12)
arrow(ax,(5.65,1.7),(6.6,1.7))
node(ax,6.6,.9,7,1.65,'候选初值 / 轨迹采样 / 碰撞等数据维度\nv2 配置 32 IK seeds ≠ 32 个进程\n具体线程映射与重叠需要 profiler 确认','#197c88',12)
ax.text(.3,2.95,'下方是规划计算原理示意，与上方动作屏障不是同一条执行时间线。',fontsize=11)
save(fig,'17-batch-barrier')

fig,axs=plt.subplots(1,3,figsize=(16,7))
items=[('同进程批量 GPU','当前生成侧','8 个协程管理环境\n↓\n凑齐动作 / 提交规划\n↓\nGPU 数值计算','共享事件循环与仿真对象\n同步调用 / 动作屏障会等待','#345bc4'),('CPU 多进程保存','当前保存侧','主进程打包 episode\n↓ 共享内存\n多个 writer 独立压缩\n↓\n各写分片 → 排空 / 合并','生成与保存可重叠\n竞争 CPU、内存与磁盘','#197c88'),('多 GPU 生产进程','未测试的另一种方案','进程 A：仿真 + 规划\n进程 B：仿真 + 规划\n↓\n共享 GPU 或绑定不同 GPU\n↓\n协调任务与输出','需额外设备资源与调度\n进程数不等于加速倍数','#697586')]
for ax,(title,tag,body,note,c) in zip(axs,items):
 ax.axis('off');ax.set_title(title,loc='left',fontsize=17,color=c);ax.text(.02,.91,tag,fontsize=12,color=c);ax.text(.02,.81,body,fontsize=14,va='top',linespacing=1.8);ax.text(.02,.12,note,fontsize=12,va='top',linespacing=1.7)
fig.suptitle('18  看并行单位与资源边界，不能只看数量',fontsize=18)
fig.text(.04,.01,'设备利用率不能证明 kernel 重叠；当前没有多 GPU 生产进程的实测吞吐对照。',fontsize=12)
save(fig,'18-parallel-comparison')

pdf.close()
print('19 figures (PNG/SVG) and charts.pdf generated')
