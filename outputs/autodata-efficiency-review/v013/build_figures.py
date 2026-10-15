"""Rebuild figures from the bundled data.json; requires matplotlib, no simulation runtime."""
import json,re
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.font_manager import FontProperties
import numpy as np
P=Path(__file__).resolve().parent
D=json.loads((P/'data.json').read_text()); R=D['latest']; labels=[r['label'] for r in R]
plt.rcParams.update({'pdf.fonttype':42,'font.family':'Noto Sans CJK JP','axes.unicode_minus':False,'font.size':11,'axes.spines.top':False,'axes.spines.right':False,'figure.facecolor':'#f7f9fc','axes.facecolor':'#f7f9fc','axes.titleweight':'bold','savefig.facecolor':'#f7f9fc'})
colors=['#697586','#197c88','#345bc4','#8b5db7']; (P/'figures').mkdir(exist_ok=True)
ORDER=json.loads((P/'chart-order.json').read_text())
PAGE={r['id']:(i+1,r['section']) for i,r in enumerate(ORDER)}
FIGURES={}
def save(fig,name):
 # Remove legacy chart IDs from titles; page order is managed by chart-order.json.
 for ax in fig.axes:
  for loc in ['left','center','right']:
   title=ax.get_title(loc=loc)
   if title:ax.set_title(re.sub(r'^\d{2}\s+', '',title),loc=loc)
 for t in fig.texts:t.set_text(re.sub(r'^(?:讲解 \d / 3：|\d{2}\s+)','',t.get_text()))
 fig.tight_layout(pad=2)
 # Extend the canvas below the original chart, preserving its physical layout.
 w,h=fig.get_size_inches();extra=1.65;total=h+extra
 positions=[(ax,ax.get_position().frozen()) for ax in fig.axes]
 text_positions=[(t,t.get_position()) for t in fig.texts]
 fig.set_size_inches(w,total)
 for ax,b in positions:ax.set_position([b.x0,(b.y0*h+extra)/total,b.width,b.height*h/total])
 for t,(x,y) in text_positions:t.set_position((x,(y*h+extra)/total))
 notes=json.loads((P/'slide-notes.json').read_text())[name]
 page,section=PAGE[name]
 fig.text(.035,1.30/total,f'{page:02d} / {len(ORDER)}  ·  {section}',fontsize=10,color='#197c88',va='center')
 fig.add_artist(plt.Line2D([.03,.97],[1.52/total,1.52/total],transform=fig.transFigure,color='#c4ccd7',lw=1))
 for y,line in zip([1.02,.64,.26],notes):
  fig.text(.035,y/total,line,fontsize=10,color='#24384d',va='center')
 fig.canvas.draw()
 renderer=fig.canvas.get_renderer()
 for t in fig.texts[-3:]:
  assert t.get_window_extent(renderer).x1 < fig.bbox.x1-5, (name,'footer exceeds width')
 fig.savefig(P/'figures'/f'{name}.png',dpi=160);fig.savefig(P/'figures'/f'{name}.svg');FIGURES[name]=fig;plt.close(fig)
def bars(ax,values,title,unit):
 bars=ax.bar(labels,values,color=colors);ax.set_title(title,loc='left');ax.set_ylabel(unit);ax.set_ylim(0,max(values)*1.22)
 for b,v in zip(bars,values): ax.text(b.get_x()+b.get_width()/2,v+max(values)*.025,f'{v:.2f}',ha='center')
 ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)

# Opening walkthrough: implementation, control flow, then measured evidence.
fig,axs=plt.subplots(1,3,figsize=(16,6.4))
version_panels=[
 ('原始版：v1 同步基线','本报告的对照实现',
 '规划：MotionGen\n环境：8 环境生成配置\n保存：主流程同步导出\n\n压缩与写入完成后\n生成控制流才能继续',
 '已使用 GPU 与多环境\n不是“整个系统完全串行”','#697586'),
 ('改进版：v1 异步保存','主要改变保存侧',
 '规划：保留 v1 后端\n环境：保留 8 环境\n保存：独立 CPU writer\n\n共享内存移交数据\n分片保存 → 排空 → 合并',
 '生成—保存流水线重叠\n另增加保存侧任务并行','#197c88'),
 ('cuRobo v2 适配版','主要改变规划侧',
 '规划：MotionPlanner\n环境：保留 8 环境\n保存：沿用异步保存池\n\n适配模型与目标表示\n插值轨迹 → 关节重排 → FK',
 '规划后端迁移与接口适配\n不是新增 GPU 生产进程','#345bc4')]
for ax,(title,tag,body,note,c) in zip(axs,version_panels):
 ax.axis('off');ax.set_title(title,loc='left',fontsize=16,color=c);ax.text(.01,.91,tag,fontsize=12,color=c);ax.text(.01,.80,body,fontsize=14,va='top',linespacing=1.8);ax.text(.01,.13,note,fontsize=12,va='top',linespacing=1.5)
fig.suptitle('讲解 1 / 3：先区分保存路径改造与规划后端迁移',fontsize=18)
save(fig,'19-version-boundaries')

fig,axs=plt.subplots(3,1,figsize=(16,8))
rows=[('原始版：同步保存',['MotionGen 规划','仿真执行 / 录制','主流程压缩 + HDF5','导出返回后继续'],'同步导出占用生成控制流。','#697586'),('改进版：异步保存',['v1 规划 / 生成','预算检查 + 内存打包','CPU writer 写分片','回执 / 排空 / 合并'],'Bridge.export → ExportPool.submit；提交后生成可继续，超预算仍会等待。','#197c88'),('v2 版：规划适配 + 异步保存',['模型 / 目标适配','plan_pose','插值 / 关节重排 / FK','生成后沿用异步保存'],'规划路径在前端变化；episode 保存仍走共享内存与 writer 池。','#345bc4')]
for ax,(title,steps,note,c) in zip(axs,rows):
 ax.axis('off');ax.set_xlim(0,16);ax.set_ylim(0,2.4);ax.text(.15,2.12,title,fontsize=14,fontweight='bold',color=c)
 for i,label in enumerate(steps):
  x=1.9+4*i;ax.text(x,1.2,label,ha='center',va='center',fontsize=12,color='white',bbox=dict(boxstyle='round,pad=.6',fc=c,ec='none'))
  if i<3:ax.annotate('',xy=(x+2.6,1.2),xytext=(x+1.5,1.2),arrowprops=dict(arrowstyle='->',lw=1.5,color='#697586'))
 ax.text(.15,.24,note,fontsize=12)
fig.suptitle('讲解 2 / 3：沿调用链说明具体改动',fontsize=18)
save(fig,'20-version-control-flow')

fig,axs=plt.subplots(1,3,figsize=(16,6))
v=D['v2_rerun'];records=[R[0],R[-1],v];names=['v1 同步\n10 月 14 日','v1 auto\n10 月 14 日','v2 auto\n10 月 15 日'];cols=['#697586','#197c88','#345bc4']
for ax,key,title,unit in [(axs[0],'seconds','最终就绪时间 ↓','秒 / 16 条保存数据'),(axs[1],'rate','记录成功吞吐 ↑','条 / 分钟')]:
 vals=[r[key] for r in records];bs=ax.bar(names,vals,color=cols);ax.bar_label(bs,fmt='%.2f',padding=5);ax.set_ylim(0,max(vals)*1.24);ax.set_title(title,loc='left');ax.set_ylabel(unit)
axs[2].axis('off');axs[2].set_title('解释与质量边界',loc='left');axs[2].text(.01,.90,'v1 auto 对比同步\n耗时减少 37.6%\n吞吐提高 60.2%\n末态均通过 16/16\n\nv2 auto：末态通过 15/16\n完成接口迁移与整轮运行\n尚未建立性能优势',va='top',fontsize=14,linespacing=1.7)
fig.suptitle('讲解 3 / 3：实现改变不等于性能优势，需结合完整输出与质量',fontsize=17)
save(fig,'21-version-evidence')

fig,ax=plt.subplots(figsize=(16,8));ax.axis('off');ax.set_title('流程分段：并行化发生在哪里，哪里仍需等待',loc='left',fontsize=18,pad=18)
rows=[['任务调度','asyncio 协程并发','共享主线程；等待未完成时挂起'],['规划计算','GPU 算子内部数据并行','主机逐环境调用；跨请求重叠未测'],['仿真步进','动作汇合后批量 env.step','等待整批动作；不是每环境一个进程'],['录制 / 内存移交','主流程 clone、pack、submit','CPU 帧所有权调整；仍有打包与预算等待'],['压缩 / 写入','spawn CPU 进程处理不同 episode','独立 HDF5 分片；共享 CPU 与磁盘资源'],['回执 / 收尾','主流程 poll、finish、merge','回执后回收内存；排空后合并最终输出']]
t=ax.table(cellText=rows,colLabels=['阶段','执行方式','同步点与边界'],colWidths=[.16,.36,.48],cellLoc='left',loc='center',bbox=[0,.06,1,.86]);t.auto_set_font_size(False);t.set_fontsize(13)
for (i,j),cell in t.get_celld().items():
 cell.set_edgecolor('#d5dee8');cell.set_facecolor('#e4edf5' if i==0 else ('#f0f5f8' if i%2 else '#ffffff'));cell.PAD=.08
save(fig,'22-stage-parallelism')

fig,axs=plt.subplots(1,2,figsize=(17,8))
for ax,title,body,c in [
 (axs[0],'v1：当前适配器调用','配置构造\nMotionGenConfig.load_from_robot_config(...)\nMotionGenPlanConfig(...)\n\n目标与调用\nPose\nplan_single(start_state, goal_pose, plan_config)\n\n轨迹结果\n优先 optimized_plan，空时取插值\nget_full_js → get_ordered_joint_state','#697586'),
 (axs[1],'v2：实验冻结适配器调用','配置构造\nMotionPlannerCfg.create(...)\nrobot / scene_model / device_cfg\n\n目标与调用\nGoalToolPose.from_poses(...)\nplan_pose(goals, start_state, max_attempts=...)\n\n轨迹结果\nget_interpolated_plan()\nreorder(joint_names) → FK → 世界系位姿','#345bc4')]:
 ax.axis('off');ax.set_title(title,loc='left',fontsize=16,color=c);ax.text(.01,.93,body,va='top',fontsize=13,linespacing=1.65)
fig.suptitle('接口迁移：目标类型、参数顺序、配置传递和轨迹语义均需适配',fontsize=17)
fig.text(.03,.015,'上层保留 update_world_and_plan_motion(...) → bool；enable_retiming 默认值仍有差异，详见正文。',fontsize=11)
save(fig,'23-exact-interfaces')

fig,ax=plt.subplots(figsize=(16,8));ax.axis('off');ax.set_title('cuRobo 库级变化 ≠ 本次 AutoData 全部启用并验证',loc='left',fontsize=18,pad=18)
rows=[['GPU 并行','v1 已有多初值并行求解\nv2 继续扩展 GPU 计算','每环境规划器；未实现跨环境批量请求\n不把 CPU writer 当作 GPU 并行升级'],['轨迹优化','v1 已有平滑性目标\nv2 强调 B-spline 与动力学约束','读取 v2 插值轨迹\n未验证本任务力矩约束激活与满足'],['场景感知','v2 增强 GPU 原生\n深度融合 TSDF / ESDF','从 USD 解析碰撞几何\n没有深度融合建图对照'],['高自由度计算','v2 强调拓扑感知运动学\n可微逆动力学与自碰撞计算','OpenArm 左臂任务\n没有全身机器人性能对照'],['性能结论','官方结果对应其测试任务\n不能直接转成生产吞吐收益','v2 完整保存 16 条、末态通过 15/16\n跨日期单轮，尚未确立性能优势']]
t=ax.table(cellText=rows,colLabels=['维度','库级能力变化','本次实验覆盖'],colWidths=[.16,.40,.44],cellLoc='left',loc='center',bbox=[0,.05,1,.88]);t.auto_set_font_size(False);t.set_fontsize(12)
for (i,j),cell in t.get_celld().items():
 cell.set_edgecolor('#d5dee8');cell.set_facecolor('#e4edf5' if i==0 else ('#f0f5f8' if i%2 else '#ffffff'));cell.PAD=.08
save(fig,'24-library-vs-integration')

fig,axs=plt.subplots(1,3,figsize=(15,6))
blocks=[('同步 · workers=0','保留原 recorder 导出','episode 完成\n↓\n主进程压缩 + 写 HDF5\n↓\n继续生成','主流程承担保存等待'),('固定上限 · 4 / 8','ExportPool._scale_workers','pending 有积压\n↓\ndesired = min(pending, cap)\n↓\n按需启动 CPU writer','本轮两种上限均启动 4 个'),('auto','ResourceGovernor.decide','pending 有积压\n↓\nCPU / 内存 / I/O 等准入\n↓\n通过：增加 1 个 writer','至少间隔 1 秒；不主动缩容')]
for ax,(title,sub,body,note),c in zip(axs,blocks,colors):
 ax.axis('off');ax.set_title(title,loc='left',fontsize=16);ax.text(.02,.83,sub,transform=ax.transAxes,fontsize=12,color=c);ax.text(.02,.63,body,transform=ax.transAxes,va='top',fontsize=14,linespacing=1.9);ax.text(.02,.05,note,transform=ax.transAxes,fontsize=12)
fig.suptitle('00  代码差别在导出路径和扩容决策，共用 cuRobo v1 生成任务',fontsize=16);save(fig,'00-code-methods')
fig,axs=plt.subplots(3,1,figsize=(12,8))
items=[('同步保存 · workers=0',['生成轨迹','主流程压缩 / 写入','保存完成','继续生成'],'同一主流程承担保存等待','#697586'),('异步单 writer',['生成轨迹','提交队列','后台串行保存','排空 / 合并'],'提交后可继续生成；保存侧仍只有一个执行者','#197c88'),('异步多 writer / auto',['生成轨迹','有界共享内存队列','多个 writer 写分片','排空 / 合并'],'生成与保存重叠；在途内存超预算时等待，最终仍需合并','#345bc4')]
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
ax.invert_yaxis();ax.set_xlabel('每个已完成 episode 的阶段均值（秒）');ax.set_title('03  阶段耗时：执行等待和同步导出下降',loc='left');ax.legend(ncol=3,loc='lower right');fig.text(.04,.01,'并发 episode 的耗时会重叠；此图不等于整批墙钟时间，也不覆盖所有未计时开销。',fontsize=10);save(fig,'03-stages')
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

fig,ax=panel('16  执行层次：协程并发、GPU 数据并行、CPU 多进程')
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
ax.text(.3,.45,'架构示意：8 个环境任务共享生成主进程；本轮异步组实际均为 4 个 CPU writer。',fontsize=12)
save(fig,'16-process-gpu')

fig,ax=panel('17  环境在动作屏障汇合；GPU 算子内部执行数据并行',8)
ax.text(.2,9.35,'主进程：环境提交动作后等待 queue.join()；等待未完成时挂起协程',fontsize=13)
for i in range(8):
 x=.25+i*1.7;node(ax,x,7.65,1.45,.95,f'env {i}',fs=12);arrow(ax,(x+.72,7.65),(x+.72,6.65))
node(ax,.25,5.55,13.35,1.05,'动作队列：等到 qsize == num_envs → 按 env_id 填入 actions','#8b5db7',14)
ax.text(.3,6.95,'缺一份动作就等待：慢任务可能影响整批推进',fontsize=12,color='#8b5db7')
arrow(ax,(6.9,5.55),(6.9,4.9));node(ax,.25,3.8,13.35,1.1,'一次 env.step(actions) → 返回 → 队列未完成计数归零 → 任务继续','#345bc4',14)
node(ax,.25,.9,5.4,1.65,'一次规划调用\n主机侧函数同步调用\nGPU 算子内部数据并行','#197c88',12)
arrow(ax,(5.65,1.7),(6.6,1.7))
node(ax,6.6,.9,7,1.65,'候选初值 / 轨迹采样 / 碰撞等数据维度\nv2 配置 32 IK seeds ≠ 32 个进程\n具体线程映射与重叠需要 profiler 确认','#197c88',12)
ax.text(.3,2.95,'下方是规划计算原理示意，与上方动作屏障不是同一条执行时间线。',fontsize=11)
save(fig,'17-batch-barrier')

fig,axs=plt.subplots(1,3,figsize=(16,7))
items=[('单进程多环境批量步进','当前生成侧','8 个环境任务协作调度\n↓\n动作汇合后批量步进\n↓\nGPU 数值计算','共享事件循环与仿真对象\n同步调用 / 动作屏障会等待','#345bc4'),('CPU 多进程保存','当前保存侧','主进程打包 episode\n↓ 共享内存\n多个 writer 独立压缩\n↓\n各写分片 → 排空 / 合并','生成与保存可重叠\n竞争 CPU、内存与磁盘','#197c88'),('使用 GPU 的多个生产进程','未测试的另一种方案','进程 A：仿真 + 规划\n进程 B：仿真 + 规划\n↓\n共享 GPU 或绑定不同 GPU\n↓\n协调任务与输出','需额外设备资源与调度\n进程数不等于加速倍数','#697586')]
for ax,(title,tag,body,note,c) in zip(axs,items):
 ax.axis('off');ax.set_title(title,loc='left',fontsize=17,color=c);ax.text(.02,.91,tag,fontsize=12,color=c);ax.text(.02,.81,body,fontsize=14,va='top',linespacing=1.8);ax.text(.02,.12,note,fontsize=12,va='top',linespacing=1.7)
fig.suptitle('18  看并行单位与资源边界，不能只看数量',fontsize=18)
fig.text(.04,.01,'设备利用率不能证明 kernel 重叠；当前没有单 GPU 多进程共享或多 GPU 部署的吞吐对照。',fontsize=12)
save(fig,'18-parallel-comparison')

def explanation_slide(name,title,columns):
 fig,axs=plt.subplots(1,len(columns),figsize=(16,7))
 if len(columns)==1:axs=[axs]
 for ax,(heading,body),c in zip(axs,columns,['#197c88','#345bc4','#8b5db7']):
  ax.axis('off');ax.set_title(heading,loc='left',fontsize=16,color=c,pad=20);ax.text(.01,.91,body,va='top',fontsize=14,linespacing=1.8)
 fig.suptitle(title,fontsize=19)
 save(fig,name)

explanation_slide('25-questions','实验要回答什么：两次实现变化，分别验证',[('问题 A：保存路径','同步保存 → 异步保存\n\n完整文件是否更早就绪？\n主流程负担转移到哪里？\n质量检查是否仍通过？\n\n主要证据：v1 四配置对照'),('问题 B：规划后端','v1 auto → v2 auto\n\n接口怎样迁移？\n能否完整生成并校验？\n是否建立性能优势？\n\n主要证据：v2 新重跑'),('讲解顺序','先交代实验与计时口径\n再说明实现机制\n然后读效率与内部耗时\n最后讨论质量和局限\n\n主线 37 页，附录 6 页')])

fig,ax=plt.subplots(figsize=(16,7));ax.axis('off');ax.set_title('实验矩阵：哪些条件相同，哪些条件不同',loc='left',fontsize=19,pad=20)
rows=[['v1 同步','10/14 · 8 环境 · seed 101','同步保存；0 writer','17 完成 / 16 保存 / 16 末态通过'],['v1 cap4 / cap8 / auto','10/14 · 8 环境 · seed 101','异步策略不同；实际均 4 writer','各 17 完成 / 16 保存 / 16 通过'],['v2 auto 重跑','10/15 · 8 环境 · seed 101','规划后端变化；实际 4 writer','16 完成 / 16 保存 / 15 通过'],['早期生产 / 离线保存','24 条生产 / 4 条离线','同步、单 writer、双 writer','不同批次；只作补充证据'],['离线压缩对照','1342 帧 / 相机；固定 chunk','gzip / none / lzf','仅比较保存耗时与体积']]
t=ax.table(cellText=rows,colLabels=['记录组','条件 / 范围','改变因素','样本与验收'],colWidths=[.18,.28,.26,.28],cellLoc='left',bbox=[0,.12,1,.76]);t.auto_set_font_size(False);t.set_fontsize(11)
for (i,j),cell in t.get_celld().items():cell.set_edgecolor('#d5dee8');cell.set_facecolor('#e4edf5' if i==0 else '#ffffff');cell.PAD=.04
save(fig,'26-experiment-matrix')

explanation_slide('27-metrics','指标口径：同一条数据，可以有不同的完成时刻',[('整批墙钟时间','T = 首条开始 → output_ready\n包含生成与最终收尾\n不含首条开始前全部启动\n\n完整启动退出用 launcher 时间\n不要混用两个计时边界'),('吞吐与质量分母','记录成功吞吐 = 16 × 60 / T\n末态合格吞吐 = 通过数 × 60 / T\n\nv1：末态通过 16 条\nv2：末态通过 15 条\n不能把保存成功直接当质量合格'),('内部阶段计时','v1：17 个完成 episode 的均值\nv2：16 个完成 episode 的均值\n后台：每组 16 次保存事件\n\n并发 episode 的耗时重叠\n阶段均值之和 ≠ 整批墙钟')])

explanation_slide('28-evidence-chain','从观察到解释：每一步结论都对应证据',[('已观察到','v1 异步最终就绪更早\n执行／等待阶段均值下降\n后台每条仍保存约 27–28 秒\n末态检查均为 16/16\n\n这是本轮完整系统的结果'),('与代码一致的解释','保存转入 CPU 子进程\n生成与保存可在时间上重叠\n主流程减少压缩与写入负担\n仍承担打包和预算等待\n\n机制解释不等于贡献分解'),('仍待验证','每项改动各贡献多少？\n重复运行排名是否稳定？\nGPU kernel 是否相互重叠？\n\n需要消融、重复与设备追踪\n不能只从 GPU 利用率推断')])

explanation_slide('29-v2-protocol','v2 补跑设计：补齐输出链，再讨论版本差异',[('为什么重跑','旧记录缺最终就绪与校验链\n部分分片已不在原路径\n\n旧记录保留为不完整证据\n新输出使用独立目录\n不覆盖旧实验状态'),('怎样运行与验收','冻结 launcher 与保留环境\n同源输入，8 环境，seed 101\n目标 16 条记录成功\n\n生成 → 保存 → 排空 / 合并\n最终文件读回 + 原阈值检查'),('哪些条件未控制','v1 与 v2 测试日期不同\n缓存、热身与系统状态不同\n完成 episode 分母不同\n\n没有同日交错重复\n因此不隔离纯后端因果效应')])

explanation_slide('30-conclusions','结论：效率改进、接口迁移与质量验收分别陈述',[('已观察到的收益','v1 auto 对同步基线\n最终就绪耗时减少 37.6%\n记录成功吞吐增加 60.2%\n末态检查均通过 16/16\n\n本轮整体保存改造有效'),('已完成的 v2 工作','迁移规划模型和调用接口\n正确读取插值轨迹并重排关节\n完整生成并保存 16 条\n完成输出读回与末态检查\n\n末态通过 15/16，未全合格'),('不能推出的结论','不能保证 auto 总是最快\n不能把吞吐收益当 GPU 加速比\n不能声称 v2 已建立性能优势\n不能把库全部能力当作已验证\n\n所有结果保留单轮限制')])

explanation_slide('31-next-experiments','下一轮验证：先规定问题和判据，再执行实验',[('性能稳定性','同日交错重复 v1 / v2\n保持输入、种子与计时一致\n记录热身和系统状态\n报告中位数、波动与合格吞吐\n\n本页为方案，尚未执行'),('收益来源','分别改变保存策略与 writer 上限\n记录实际进程数、预算等待\n设备追踪单独做诊断运行\n测动作就绪、规划与 kernel\n\n避免追踪开销污染吞吐对照'),('v2 质量失败','复核 demo_2 末态角速度\n检查结束条件与稳定等待\n修复另记版本并完整重跑\n保留原阈值与本轮失败记录\n\n末态验收与性能比较同时报告')])

explanation_slide('32-module-structure','模块拆分：原 handler 的保存职责转入桥接层与进程池',[
 ('原始：生成进程内','RecorderManager\n  录制 / export_episodes\n↓\nEpisodeData.pre_export\n  列表统一 torch.stack\n↓\nHDF5DatasetFileHandler\n  write_episode + flush'),
 ('改进：生成主进程','RecorderManager（保留）\n↓ 实例方法转接\nBridge + MetadataHandler\n  导出路由 / 元数据\n↓\nExportPool\n  预算 / 任务 / 内存 / 回执\n  最终排空与合并'),
 ('改进：CPU 子进程','spawn → writer\n↓ 消费 jobs 描述信息\nwrite_job\n  映射 CPU 共享内存\n  gzip + 独立 HDF5 分片\n↓\nresults 返回 saved / failed\n  不初始化仿真与 CUDA')])

explanation_slide('33-install-hooks','四个接入时刻：安装异步保存，不永久改写上游源码',[
 ('创建环境前后','generate.build_source\n按固定锚点改入口文本\n\n创建前 configure(env_cfg)\n替换类方法 add_to_episodes\n设置 MetadataHandler 类型\n\n创建后 attach(recorder, settings)\nMethodType 绑定实例 export'),
 ('生成运行中','compat.install_generation_compat\n在 env_loop 中插入 poll\n\n外层循环处理回执\n等待动作时也处理回执\n\nBridge.export → pool.submit\n主流程仍检查预算和打包\n提交返回不等于保存完成'),
 ('结束或异常时','达到生成目标 → finish\n检查成功提交数\n排空 → join → merge\n关闭环境 → output_ready\n\n异常 / finally / atexit\n调用 abort 清理自有资源\n锚点变化需重新核对适配')])

explanation_slide('34-buffer-changes','数据所有权：环境切片、源帧与共享内存分别管理',[
 ('原始数据路径','录制：整批 value.clone()\n每环境保留切片 clone=False\n切片可继续持有整批存储\n\n导出：pre_export\n各字段列表 torch.stack\n.cpu().numpy() → HDF5\n统一堆叠仍在生成进程'),
 ('改进 CPU 帧路径','录制：每环境独立 clone\n导出：layout 计算偏移与形状\n分配有界共享内存\n\n逐帧 np.copyto\n已复制源帧置 None / 清空\n尝试归还分配器空闲页\n不调用原统一 pre_export'),
 ('必须区分的边界','GPU 状态列表仍先 stack\n再转 CPU、复制到共享内存\n\n源帧复制后可释放\n共享内存等 saved 后释放\n\n不是零拷贝 / CUDA IPC\n没有独立峰值内存消融')])

explanation_slide('35-completion-failure','完成语义变化：提交、分片保存和最终就绪分成三步',[
 ('提交与保存','submit → entries=submitted\n任务加入 pending 与 jobs\n\nwriter：started → write_job\n写临时组 → 移动 → flush\n返回 saved\n\npoll 才释放内存并更新计数'),
 ('最终文件','finish 等待 pending 清空\n发送退出哨兵并 join\n\n_merge 排序复制分片\n检查属性 / shape / dtype\n.partial → os.link 最终路径\n\nenv.close 后记录 output_ready'),
 ('失败与限制','failed / 进程退出 / 超时\n由父进程 poll 报错\nabort 终止 writer 并回收内存\n\n合并检查不等于逐值校验\n没有多输出事务回滚保证\n没有 fsync 持久化承诺\n末态质量仍需独立验收')])

explanation_slide('36-execute-timer','执行／等待 = MultiWaypoint.execute 整段调用的墙钟时间',[
 ('计时包含的顺序','time.monotonic() 开始\n↓\n目标 / 噪声 → 动作转换\n↓\n动作 put → await queue.join\n↓\n成功条件检查 → bool\n↓\n正常返回后累计耗时'),
 ('queue.join 期间可能发生','等待其余环境提交动作\n整批 env.step(actions)\n仿真 / 观测 / 录制等路径\n队列完成后的协程恢复延迟\n\n其他环境同步规划或导出\n也可能占用共同事件循环线程'),
 ('旧日志无法直接拆出的量','纯 physics kernel 时间\n纯渲染与相机处理时间\n动作屏障占比\n主机与设备同步占比\n\n同一等待可被多个环境累计\n不能按 GPU 忙碌时间解释')])
W=json.loads((P/'execution-analysis.json').read_text());modes=['sync','cap4','cap8','auto','v2auto'];wnames=['v1 同步','v1 cap4','v1 cap8','v1 auto','v2 auto'];wc=['#697586','#197c88','#345bc4','#8b5db7','#d18a35'];S=W['summary']
fig,axs=plt.subplots(1,2,figsize=(15,6))
for ax,key,title in [(axs[0],'calls','完成样本 execute 调用总数'),(axs[1],'weighted_ms_per_call','累计执行等待 / 累计调用数（ms）')]:
 vals=[S[m][key] for m in modes];b=ax.bar(wnames,vals,color=wc);ax.bar_label(b,fmt='%.2f' if key!='calls' else '%.0f',padding=4);ax.set_ylim(0,max(vals)*1.22);ax.set_title(title,loc='left',fontsize=14);ax.tick_params(axis='x',labelsize=10)
fig.suptitle('v1 调用数逐样本一致：改善来自等待延迟下降，而非动作数减少',fontsize=17)
save(fig,'37-execute-normalized')

fig,axs=plt.subplots(1,2,figsize=(16,6))
vals=[[w['ms_per_call'] for w in W['windows'] if w['mode']==m] for m in modes]
axs[0].boxplot(vals,tick_labels=wnames,showfliers=True,flierprops=dict(markersize=3));axs[0].set_yscale('log');axs[0].set_ylabel('每 100 调用窗口的均值 / ms，纵轴对数');axs[0].set_title('完整窗口分布；点为箱线图离群值',loc='left',fontsize=13);axs[0].tick_params(axis='x',labelsize=10)
x=np.arange(5)
for off,key,label,c in [(-.18,'window_median_ms','窗口中位数','#197c88'),(.18,'window_p95_ms','窗口 P95','#e8aa46')]:
 v=[S[m][key] for m in modes];b=axs[1].bar(x+off,v,.36,label=label,color=c);axs[1].bar_label(b,fmt='%.0f',padding=3,fontsize=10)
axs[1].set_xticks(x,wnames,fontsize=10);axs[1].set_ylim(0,1100);axs[1].set_ylabel('窗口平均延迟 / ms');axs[1].legend();axs[1].set_title('v1 中位数接近，长尾下降明显',loc='left',fontsize=13)
fig.suptitle('区分典型速度与长时间停顿：窗口 P95 不是单次调用 P95',fontsize=17)
save(fig,'38-execute-tail')

fig,ax=plt.subplots(figsize=(14,6));bottom=np.zeros(5)
fields=[('execute_seconds','execute 调用（含等待）','#197c88'),('motion_seconds','规划','#345bc4'),('export_seconds','导出 / 入队','#8b5db7'),('reset','reset','#aab4c0'),('residual_seconds','未归类差额','#e8aa46')]
for key,label,c in fields:
 if key=='reset':v=np.array([np.mean([e['episode_seconds']-e['execute_seconds']-e['motion_seconds']-e['export_seconds']-e['residual_seconds'] for e in W['episodes'] if e['mode']==m]) for m in modes])
 else:v=np.array([np.mean([e[key] for e in W['episodes'] if e['mode']==m]) for m in modes])
 ax.barh(wnames,v,left=bottom,color=c,label=label)
 if key in ['execute_seconds','residual_seconds']:
  for i,n in enumerate(v):ax.text(bottom[i]+n/2,i,f'{n:.1f}',ha='center',va='center',fontsize=11)
 bottom+=v
ax.invert_yaxis();ax.set_xlabel('秒 / 已完成 episode；不是整批墙钟分解');ax.legend(ncol=3,loc='lower right',fontsize=10);ax.set_title('计时覆盖检查：v2 的未归类区间也需要继续拆分',loc='left',fontsize=17);ax.margins(x=.08);ax.set_ylim(5.35,-.6)
save(fig,'39-execute-residual')



explanation_slide('40-gpu-chain','GPU 工作提交受主线程闭环约束：保存并行没有拆开整条路径',[
 ('等齐动作 → 批量 step','各环境准备动作\n↓ put / queue.join\n等待队列达到 num_envs\n↓\nenv.step(actions)\n↓ task_done\n各协程继续下一步'),
 ('主线程仍执行什么','同步规划 plan_single\n成功标量 item / bool\n观测 GPU → CPU\n录制与共享内存 pack\n预算不足时等待回执\n\n这些路径可能推迟下一次提交'),
 ('对应源码位置','env_loop：250–275 行\nwaypoint：333–336 行\nplanner：1312–1314 行\ncameras：54–55 行\nexport_pool：296–314 行\n\n源码跳转：gpu-analysis.html')])
explanation_slide('41-camera-copies','相机路径：重复观测可能重复回传与复制，需核验实际加载版本',[
 ('每个 RGB term','update_mounted_camera_poses\n  循环更新三个相机\n↓\n读取一组相机 RGB\n↓ .to(cpu, copy=True)\nCPU 图像副本\n↓ observation term.clone()'),
 ('一次 step 的条件计数','三路 RGB term 启用\n且 recorder active\n且加载当前 RL step\n\n录制前 compute\n重置 / 事件后 compute\n→ 六次批量 RGB 回传调用\n→ 十八次 set_world_poses'),
 ('优化须保留语义','相机刷新可评估集中处理\nCPU 回传可评估有效缓存\n\nreset / 事件后可能已变状态\n不能直接删第二次 compute\n\n调用数不等于渲染次数\n需要实测计数与设备追踪')])
explanation_slide('42-gpu-validation','先定位设备空隙的来源，再评估批量大小和并行策略',[
 ('优先验证','1. 加载路径 / hash / 调用数\n2. 观测与 RGB 复制时间线\n3. 每环境动作就绪时刻\n4. bool / item 与规划区间\n5. pack 与预算等待\n\nCPU 区间需关联 CUDA 时间线'),
 ('分开做消融','相机刷新与缓存复用\n成功判定批量计算 / 读回\n规划与 FK 批处理\n共享内存打包调度\n\n单项改变，检查输出一致性\n诊断追踪与吞吐运行分开'),
 ('已有证据与边界','v1 调用数一致，长尾下降\n尚无各段 GPU 耗时占比\n\n利用率不是 SM occupancy\n整批均值还包含收尾阶段\n\n最终评价：合格产出 / 时间\n不以利用率越高越好为目标')])

assert set(FIGURES)==set(PAGE)
with PdfPages(P/'charts.pdf') as pdf:
 for row in ORDER:pdf.savefig(FIGURES[row['id']])

print('43 figures (PNG/SVG) and charts.pdf generated')
