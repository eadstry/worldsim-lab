"""Redraw frozen chartbook evidence as vector figures; never upscale old PNGs."""
from __future__ import annotations
import argparse
import csv
from html import escape
import json
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
from PIL import Image

from build import LEGACY, setup, verify_sealed, digest, TEAL, RED, GRAY, PAPER


def page(title, subtitle, note, panels=1):
    fig, axes = plt.subplots(1, panels, figsize=(11.69, 8.27), squeeze=False)
    fig.subplots_adjust(left=.13, right=.94, top=.75, bottom=.27, wspace=.42)
    fig.text(.07, .92, title, fontsize=24)
    fig.text(.07, .845, subtitle, fontsize=14)
    fig.text(.07, .09, note, fontsize=12, linespacing=1.65)
    return fig, axes[0]


def bars(ax, labels, values, colors, unit, top, annotations=None):
    ax.bar(labels, values, color=colors, width=.55)
    ax.set_ylim(0, top)
    ax.set_ylabel(unit, fontsize=14)
    ax.grid(axis='y', alpha=.15)
    ax.set_axisbelow(True)
    for i, value in enumerate(values):
        label = annotations[i] if annotations else f'{value:g}'
        ax.text(i, value + top*.035, label, ha='center', va='bottom', fontsize=14)


def grouped(ax, labels, series, names, unit, top, fmt='.2f'):
    x = np.arange(len(labels)); width = .75/len(series)
    for i, (values, name, color) in enumerate(zip(series, names, [GRAY, TEAL, RED])):
        positions = x + (i-(len(series)-1)/2)*width
        ax.bar(positions, values, width, label=name, color=color)
        for pos, value in zip(positions, values):
            ax.text(pos, value+top*.025, format(value, fmt), ha='center', fontsize=12)
    ax.set_xticks(x, labels); ax.set_ylabel(unit); ax.set_ylim(0, top)
    ax.legend(loc='upper left', frameon=False, fontsize=12)
    ax.grid(axis='y', alpha=.15); ax.set_axisbelow(True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-bundle', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source, out = args.source_bundle.resolve(), args.output.resolve()
    verify_sealed(source)
    out.mkdir(parents=True, exist_ok=False)
    (out/'figures').mkdir()
    shutil.copytree(source/'evidence', out/'evidence')
    for name in ['metrics.csv', 'sources.json']:
        shutil.copyfile(source/name, out/name)
    data = {p.stem: json.loads(p.read_text()) for p in (out/'evidence').glob('*.json')}
    setup()
    plt.rcParams.update({'font.size':14, 'xtick.labelsize':12, 'ytick.labelsize':12,
                         'axes.labelsize':14, 'axes.titlesize':16})
    records, fresh = [], []

    def save_new(name, group, title, result, sample, scope, source_key, fig):
        # All artists are actual vector plots, including the fourteen legacy charts.
        fig.canvas.draw()
        bounds = fig.bbox
        for text in fig.texts + [t for ax in fig.axes for t in ax.texts]:
            box = text.get_window_extent(fig.canvas.get_renderer())
            if box.x0 < 0 or box.y0 < 0 or box.x1 > bounds.x1 or box.y1 > bounds.y1:
                raise ValueError(f'Text clipped in {name}: {text.get_text()}')
        path = out/'figures'/name
        fig.savefig(path.with_suffix('.png'), dpi=300)
        fig.savefig(path.with_suffix('.svg'))
        record = dict(id=name, group=group, title=title, result=result, sample=sample,
                      scope=scope, source=source_key, png=f'figures/{name}.png',
                      svg=f'figures/{name}.svg', origin='redrawn_from_frozen_evidence',
                      png_sha256=digest(path.with_suffix('.png')))
        records.append(record); fresh.append((record, fig))

    def legacy(index, subtitle, note, panels=1):
        meta = LEGACY[index-1]
        fig, axes = page(f'{index:02d} / {meta[2]}', subtitle, note, panels)
        return meta, fig, axes

    def save(meta, fig):
        save_new(*meta, fig)

    def add(*args):
        pass  # Numeric index is copied byte-for-byte from the verified sealed source.

    meta, fig, axes = legacy(1, '16/16 项接口与判据检查通过',
        '范围：任务接口、动作与成功判据的一致性。\n未验证完整轨迹或学习策略等价性。')
    ax = axes[0]; ax.axis('off')
    names = list(data['shared']['checks'])
    for i, name in enumerate(names):
        col, row = divmod(i, 8)
        ax.text(col*.55, .96-row*.13, f'{"通过" if data["shared"]["checks"][name] else "失败"}  {name}',
                transform=ax.transAxes, fontsize=12, color=TEAL)
    save(meta, fig)

    rows = data['export24']['async_validation']['gpu']['runs']
    meta, fig, axes = legacy(2, '8 个并行环境；每模式保存 24 条；严格终态均为 23/24',
        '吞吐以最终文件就绪为终点；24 条样本不代表 24 个并行环境。\nworkers=2 相比同步导出提高约 29.8%。')
    bars(axes[0], [f'workers={r["workers"]}' for r in rows],
         [r['final_ready_per_minute'] for r in rows], [GRAY,TEAL,TEAL], '最终文件就绪吞吐 / 条/分钟', 2,
         [f'{r["final_ready_per_minute"]:.3f}' for r in rows]); save(meta,fig)

    rows = data['export16']['latest']
    meta,fig,axes = legacy(3, '每配置尝试 17 次、生成成功 16 次；成功目标为 16 条',
        'auto 相比同步提高约 60.2%；cap=8 的观测吞吐更高。\n样本很小，结果不构成所有配置与负载下的最优性结论。')
    bars(axes[0], ['同步','cap=4','cap=8','auto'], [r['rate'] for r in rows], [GRAY,TEAL,TEAL,TEAL],
         '最终文件就绪吞吐 / 条/分钟',2, [f'{r["rate"]:.3f}' for r in rows]); save(meta,fig)

    rows = [r for r in data['capacity']['rows'] if r['label'].startswith('confirm')]
    series = [[next(r['terminal_accepted_per_minute'] for r in rows if r['seed']==seed and r['workers']==worker)
               for seed in [303,404,505]] for worker in [0,'auto']]
    meta,fig,axes = legacy(4, '确认阶段：4 环境；3 个配对 seed；每单元固定 4 次尝试',
        '完整预算共 20 单元、74 次尝试；此图展示 6 个确认单元。\n仅为仿真终态接受吞吐；正式批次未执行独立文件验收。')
    grouped(axes[0], ['seed 303','seed 404','seed 505'], series,['同步','auto'],
            '仿真终态接受吞吐 / 条/分钟',max(map(max,series))*1.4); save(meta,fig)

    rows = data['timing']['runs']
    meta,fig,axes = legacy(5, '8 对动作哈希匹配；导出与背压等待下降约 93.8%',
        '主机墙钟归因，非隔离 GPU kernel 时间。其余开销为其他阶段之和。\n最终文件就绪总耗时：515.77 → 350.30 秒。')
    groups = ['export','camera','physics']
    series = [[r['execute_groups'][g]['seconds_per_episode'] for g in groups]+[
        sum(v['seconds_per_episode'] for k,v in r['execute_groups'].items() if k not in groups)] for r in rows]
    for r in rows:
        assert np.isclose(sum(v['seconds_per_episode'] for v in r['execute_groups'].values()),r['mean_execute_seconds'])
    grouped(axes[0], ['导出与背压','相机采集','物理与控制','其余开销'], series,['同步','auto'], '执行阶段均值 / 秒/条',95);save(meta,fig)

    r = data['randomization']
    meta,fig,axes = legacy(6, '256 次 reset；9/9 项检查通过；同 seed 最大误差为 0',
        '显示配置边界与实测偏移标准差，未补造完整 256 点散点。\n随机化生效检查；未进行任务成功率或策略泛化评测。')
    ax=axes[0]
    for i,k in enumerate(['x','y']):
        lo,hi=r['pose_range'][k]; std=r['std_offset_m'][i]
        ax.plot([lo*100,hi*100],[i,i],lw=12,color=GRAY,solid_capstyle='butt')
        ax.plot([-std*100,std*100],[i,i],lw=5,color=TEAL)
        ax.text(hi*100+.4,i,f'±{hi*100:g} cm；σ={std*100:.2f} cm',va='center')
    ax.set(yticks=[0,1],yticklabels=['X 偏移','Y 偏移'],ylim=(-.6,1.6),xlim=(-7,13),xlabel='相对中心的偏移 / cm')
    ax.axvline(0,lw=1,color=GRAY);save(meta,fig)

    rows=data['g1']['episodes']
    meta,fig,axes=legacy(7, '7 段尝试，6 段成功；每个条件只有 1 段',
        '图像差来自匹配控制步的头部相机，基线 MAE=0。\n绿色=成功，红色=失败；视觉变化不等于训练泛化收益。')
    bars(axes[0], ['基线','光照','相机','材质','纯视觉','组合 A','组合 B'],
         [r['matched_step_rgb_mae_255']['head'] for r in rows], [TEAL if r['success'] else RED for r in rows],
         '相对基线图像 MAE / 0–255',70,[f'{r["matched_step_rgb_mae_255"]["head"]:.1f}' for r in rows]);save(meta,fig)

    rows=data['mvp']['runs']
    meta,fig,axes=legacy(8, '完整任务 v1=5/5、v2=4/5；两版规划请求均 10/10',
        '后续规划请求各 9 个，非独立任务重复；内部配置不完全等价。\n集成方案对照，不能将差异纯归因于 cuRobo 版本。',2)
    bars(axes[0],['v1','v2'],[r['successes'] for r in rows],[GRAY,TEAL],'完整任务成功 / 次',6.5,['5/5','4/5'])
    grouped(axes[1],['p50','p95'], [[r['request_warm_p50_seconds'],r['request_warm_p95_seconds']] for r in rows],
            ['v1','v2'],'后续规划延迟 / 秒',3);save(meta,fig)

    r=data['v2']
    meta,fig,axes=legacy(9, 'v2 补跑保存 16 条，其中严格终态通过 15 条',
        '分别计数生成、保存与严格终态，不将保存成功当作任务成功。\n该批与旧 v1 批次并非配对重复实验；v1 仍为默认。')
    bars(axes[0],['生成成功','保存','严格终态'],[r['successes'],r['saved_episodes'],r['physical_passes']],
         [GRAY,TEAL,TEAL],'轨迹数 / 条',20);save(meta,fig)

    rows=data['franka']['cells']
    meta,fig,axes=legacy(10, '4 个条件，每条件 3 个配对状态',
        '有障碍时 IK 峰值接触力约 381.8 N；cuRobo＋IK 为 0 N。\nFranka 局部桌面避障；接触阶段共用 IK，不代表 OpenArm 或整屋避障。')
    bars(axes[0],['无障碍\nIK','无障碍\ncuRobo＋IK','有障碍\nIK','有障碍\ncuRobo＋IK'],
         [r['collision_free_successes'] for r in rows],[GRAY,TEAL,RED,TEAL],'无碰撞成功 / 次',4,['3/3','3/3','0/3','3/3']);save(meta,fig)

    r=data['banana']
    meta,fig,axes=legacy(11, '1 条示范，950 RGB 帧；力采样 3800 点',
        '刚体香蕉，仅展示已保存力统计，不补造时间曲线。\n腕部传感为关节反力，包含动力学分量；未验证压伤阈值或闭环力控。')
    grouped(axes[0],['左指','右指'], [r['median_transfer_finger_normal_N'],r['peak_finger_normal_N']],
            ['搬运中位数','全程峰值'],'手指法向力 / N',60, '.1f');save(meta,fig)

    rows=data['hdr']
    meta,fig,axes=legacy(12, '5 批各 1 次，均通过已有验收',
        '不同批次墙钟仅作为运行记录，未控制为 HDR 速度对照。\n小批生产可行性不等于大规模稳定性或策略泛化验证。')
    bars(axes[0],['基线 r02','studio r03','beach r03','studio r04','beach r04'],
         [r['seconds'] for r in rows],[TEAL]*5,'批次墙钟 / 秒',260,[f'{r["seconds"]:.1f}' for r in rows]);save(meta,fig)

    rows=data['concurrency']['rounds']
    meta,fig,axes=legacy(13, '3 轮历史混合负载观测；包含初始化与被终止任务',
        '全轮 GPU 均值与瞬时峰值分别报告；70% 峰值不代表持续高利用率。\n每轮仅 1 次观测；5 进程轮次未证实 5 个仿真同时有效运行。')
    grouped(axes[0], [f'{r["round"]}\n{r["duration_seconds"]:.0f} 秒' for r in rows],
            [[r['gpu_mean_percent'] for r in rows],[r['gpu_peak_percent'] for r in rows]],
            ['全轮均值','峰值'],'GPU 利用率 / %',100,'.1f');save(meta,fig)

    meta,fig,axes=legacy(14, '目标为 100 条成功轨迹；开始 63 次，完成 55 次',
        '55 次完成 = 49 成功 + 6 失败；另有 8 次开始后未完成。\nSIGKILL 与 cgroup OOM 事件同期出现；不足以确定 OOM 受害进程，最终 HDF5 未验收。')
    bars(axes[0],['完成且成功','完成但失败','未完成'],[49,6,8],[TEAL,RED,GRAY], '63 次已开始尝试的状态 / 次',60);save(meta,fig)

    audit = data['audit']
    cameras = ['left_hand_rgb','right_hand_rgb','third_person_rgb']
    labels = ['左腕','右腕','第三视角']
    totals = [sum(v[c]['frames'] for v in audit['images'].values()) for c in cameras]
    assert len(audit['images']) == 4 and totals == [5453,5453,5453]
    black = [sum(v[c]['suspected_black_frames'] for v in audit['images'].values()) for c in cameras]
    post = [sum(v[c]['post_warmup_frames'] * v[c]['post_warmup_suspected_black_fraction']
                for v in audit['images'].values()) for c in cameras]
    post_n = [sum(v[c]['post_warmup_frames'] for v in audit['images'].values()) for c in cameras]
    fig, ax = page('15 / 相机全量扫描：右腕持续近黑', '旧数据 4 条轨迹；三路相机各 5453 帧；未新增轨迹',
                   '判定：8-bit 平均强度 <1，且 >99% 通道值 ≤2。\n每条剔除前 30 帧后，左腕/第三视角为 0%，右腕仍为 100%；不是目标可见性认证。')
    values = np.asarray(black) / totals * 100
    bars(ax[0], labels, values, [TEAL, RED, TEAL], '疑似黑帧比例 / %', 115,
         [f'{b}/{n} 帧\n{value:.3f}%' for b,n,value in zip(black,totals,values)])
    save_new('15-camera-quality','本轮验收','三路相机黑帧检查','右腕 5453/5453 帧近黑；左腕仅 4 个首帧，第三视角为 0',
             '4 条；各相机 5453 帧','全像素扫描；不是多视角训练通过','audit',fig)
    for c,n,b,p,pn in zip(cameras,totals,black,post,post_n):
        add('15','suspected_black_frames',c,b,'frames',n,'audit','全量像素诊断')
        add('15','post_warmup_black_fraction',c,p/pn,'fraction',pn,'audit','每条排除前 30 帧')

    regression, validation = data['regression'], data['readback']
    stats = regression['production']['stats']
    n = stats['num_attempts']; passed = sum(e['terminal_pass'] and e['recorded_success'] for e in validation['episodes'])
    assert regression['status'] == 'completed' and (n,stats['num_success'],passed,len(validation['episodes'])) == (8,7,7,8)
    fig, ax = page('16 / 独立目录导出回归：8 条均完整保存','8 环境 × 8 次固定尝试；7 成功 + 1 任务失败；无追加重试',
                   '8 条成功/失败轨迹均完成逐数组回读；7 个成功标签通过原严格终态谓词。\n导出完整性与任务成功分别计数；本批不替代 24 环境资格验证，也不作为速度对照。')
    vals = [n, n, regression['exported_episodes'], len(validation['episodes']), passed]
    bars(ax[0], ['尝试','完成','保存','完整回读','严格终态成功'], vals,
         [GRAY,GRAY,TEAL,TEAL,TEAL], '本批轨迹数 / 条', 9.5)
    save_new('16-export-closure','本轮验收','8 环境隔离导出回归','8 次完成、8 条保存、8 条完整回读；7 条严格终态成功',
             '8 次尝试','真实 GPU 回归；不是 24 并行或长期稳定性验证','regression',fig)
    for label,value in zip(['attempts','completed','exported','readback','strict_success'],vals):
        add('16','trajectory_count',label,value,'episodes',n,'regression' if label not in ['readback','strict_success'] else 'readback','不同验收层分别计数')

    gate = audit['qualification24']
    available, required = gate['memory']['effective_available_gib'], gate['required_available_gib']
    fig, ax = page('17 / 24 并行：现有记录路径未通过内存准入','准入检查已执行；没有启动 24 环境仿真',
                   '144 GiB = 12 基础 + 24×4.5 recorder + 16 导出队列 + 8 余量。\n这是当前路径的保守准入模型，不是实测最低需求；不能通过降低阈值宣称准入成功。')
    bars(ax[0], ['当前有效可用 RAM\n实测快照','24 环境准入要求\n保守估算'], [available,required], [GRAY,RED],
         '内存 / GiB', 175, [f'{available:.2f} GiB',f'{required:.0f} GiB'])
    ax[0].text(.5,.9,f'准入缺口约 {required-available:.1f} GiB',transform=ax[0].transAxes,ha='center')
    save_new('17-memory-admission','资源与稳定性','24 环境内存准入','有效可用 93.44 GiB，低于保守准入要求 144 GiB',
             '1 次资源快照','资源准入受阻；无 24 环境运行结果','audit',fig)
    add('17','effective_available_ram','observed',available,'GiB',1,'audit','资源快照')
    add('17','required_ram','24-env-model',required,'GiB',1,'audit','单个24环境准入模型；非实测最低内存')

    failure = data['failure']; velocity = np.asarray(failure['root_velocity'])
    event = failure['episode_finished_event']
    assert event['planner_calls'] == event['planner_successes'] == 4 and event['success'] is False
    speeds = [float(np.linalg.norm(velocity[:3])),float(np.linalg.norm(velocity[3:]))]
    limits = [failure['linear_speed_limit_m_s'],failure['angular_speed_limit_rad_s']]
    fig, axes = page('18 / 任务失败：规划成功，末态仍在运动','env1-attempt1；1447 控制步；4 次规划请求全部成功',
                     '失败样本仍完整保存；两个速度均高于原终态阈值。\n这是末态未稳定的证据，不能单凭末态确定完整滑落过程；未放宽成功判据。',2)
    for ax, value, limit, unit in zip(axes,speeds,limits,['线速度 / m/s','角速度 / rad/s']):
        bars(ax,['终态阈值','失败样本'],[limit,value],[GRAY,RED],unit,value*1.35,
             [f'{limit:.3g}',f'{value:.3f}'])
    save_new('18-failure-terminal','本轮验收','失败样本终态诊断','线速度约 0.193 m/s、角速度约 6.19 rad/s，均超过原阈值',
             '1 个失败样本','物理终态检查；不等于接口或导出失败','failure',fig)
    for metric,value,limit,unit in zip(['linear_speed','angular_speed'],speeds,limits,['m/s','rad/s']):
        add('18',metric,'failed_terminal',value,unit,1,'failure','单失败样本')
        add('18',metric,'unchanged_threshold',limit,unit,1,'failure','原严格终态阈值')

    conversion = data['conversion']; streams = conversion['fully_decoded_video_frames']
    assert conversion['status'] == 'passed' and conversion['numeric_roundtrip'] == 'all values exact'
    assert conversion['episodes'] == 4 and conversion['frames'] == 5453 and 'semantic_names' in conversion
    fig, ax = page('19 / LeRobot v3：转换与读取已通过','4 条轨迹 · 5453 帧 · 30 Hz · 12 个官方 loader 采样',
                   '每个数值字段全量匹配，三个视频流均完整解码；语义维度名称已核验。\n转换与加载通过，不代表已训练模型、已完成策略评测或相机画面均有用。')
    stream_values = [streams['observation.images.'+key] for key in ['left_hand','right_hand','third_person']]
    bars(ax[0], ['左腕视频','右腕视频','第三视角视频'],stream_values,[TEAL]*3,'完整解码帧数 / 帧',6500)
    save_new('19-lerobot-conversion','本轮验收','LeRobot v3 转换与回读','4 条、5453 帧；数值精确匹配，三路视频完整解码',
             '4 条；12 个 loader 采样','CPU 转换与回读；尚未训练或评测学习策略','conversion',fig)
    for name,value in streams.items():
        add('19','decoded_video_frames',name,value,'frames',conversion['episodes'],'conversion','转换格式检查；非视觉质量')

    records.sort(key=lambda r:r['id'])
    by_id={r['id']: fig for r,fig in fresh}
    with PdfPages(out/'experiment-chartbook.pdf') as pdf:
        cover=plt.figure(figsize=(11.69,8.27),facecolor=PAPER)
        cover.text(.07,.92,'具身数据生产 · 实验图册 v002',fontsize=26)
        cover.text(.07,.85,'19 张矢量重绘｜数据截至 2026-10-20｜排版更新 2026-10-22',fontsize=14)
        for i,r in enumerate(records):
            col,row=divmod(i,10)
            cover.text(.07+col*.48,.77-row*.055, r['id'][:2]+'  '+r['title'],fontsize=13)
        cover.text(.07,.12,'每页一图，可放大阅读；各图统计口径与证据限制见页脚。',fontsize=13)
        cover.text(.07,.075,'未新增 GPU 仿真或训练；未复制视频、HDF5 或模型。',fontsize=12)
        pdf.savefig(cover);plt.close(cover)
        for r in records:
            pdf.savefig(by_id[r['id']]);plt.close(by_id[r['id']])
    (out/'chart-index.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
    with (out/'chart-index.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
    cards=[]
    for r in records:
        name=escape(r['title']);svg=escape(r['svg']);png=escape(r['png'])
        cards.append(f'<article id="{r["id"]}"><h2>{r["id"][:2]} · {name}</h2>'
                     f'<p>{escape(r["result"])}</p><a href="{svg}" title="打开矢量原图，可放大">'
                     f'<img loading="lazy" src="{svg}" alt="{name}"></a>'
                     f'<p><a href="{svg}">打开矢量原图</a> · <a download href="{png}">下载 300 dpi PNG</a></p>'
                     f'<p class="note">{escape(r["sample"])}；{escape(r["scope"])}</p></article>')
    nav=' · '.join(f'<a href="#{r["id"]}">{r["id"][:2]}</a>' for r in records)
    (out/'index.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"><title>实验图册 v002</title>'
        '<style>body{margin:0;background:#f7f6f2;color:#263c3b;font:18px/1.6 system-ui,sans-serif}'
        'main{max-width:1200px;margin:auto;padding:24px}h1{font-size:32px}h2{font-size:25px}'
        'a{color:#157c73}article{margin:32px 0 60px;padding-top:12px;border-top:1px solid #ccd6d0}'
        'img{display:block;width:100%;height:auto}.note{font-size:16px}nav{line-height:2.3}</style>'
        '<main><h1>具身数据生产 · 实验图册 v002</h1>'
        '<p>19 张图全部以 SVG 展示；点击图形打开矢量原图，可继续放大。每张 PNG 为 300 dpi。</p>'
        '<p>数据截至 2026-10-20；本次仅重绘排版，未新增仿真或训练。</p>'
        '<p><a href="experiment-chartbook.pdf">下载矢量 PDF 图册</a> · '
        '<a href="metrics.csv">原始指标索引 CSV</a></p><nav>'+nav+'</nav>'+''.join(cards)+'</main></html>')
    (out/'code-ref.json').write_text(json.dumps({
        'overlay':'workspace-overlays/experiment-chartbook', 'entrypoint':'build_sharp.py',
        'source_manifest_sha256':digest(source/'manifest.json'), 'source_version':'v001',
        'reproduction':'python build_sharp.py --source-bundle outputs/experiment-chartbook/v001 --output outputs/experiment-chartbook/vNNN',
    },ensure_ascii=False,indent=2)+'\n')
    # Structural quality checks: no bitmap image embedded in any SVG or PDF.
    for r in records:
        with Image.open(out/r['png']) as im:
            assert im.size==(3507,2481), (r['id'],im.size)
            assert min(im.info['dpi'])>=299.9
        root=ET.parse(out/r['svg']).getroot()
        assert not list(root.iter('{http://www.w3.org/2000/svg}image'))
    info=subprocess.run(['pdfinfo',str(out/'experiment-chartbook.pdf')],check=True,capture_output=True,text=True).stdout
    assert 'Pages:           20' in info
    images=subprocess.run(['pdfimages','-list',str(out/'experiment-chartbook.pdf')],check=True,capture_output=True,text=True)
    assert len(images.stdout.strip().splitlines())==2, images.stdout
    text_result=subprocess.run(['pdftotext',str(out/'experiment-chartbook.pdf'),'-'],check=True,capture_output=True,text=True)
    assert not text_result.stderr, text_result.stderr
    assert '实验图册' in text_result.stdout
    assert digest(out/'metrics.csv')==digest(source/'metrics.csv')
    verify_sealed(source)
    validation=dict(status='passed', charts=19,vector_svg=19, pdf_pages=20,pdf_bitmap_images=0,
        png_pixels=[3507,2481],png_dpi=300,text_within_canvas=True,source_manifest_verified=True,metrics_csv_unchanged=True,
        scope='Chart rendering and frozen evidence integrity only; no new simulation or training')
    (out/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n')
    manifest=dict(schema_version=1,artifact_id='experiment-chartbook',version=out.name,
                  sealed_at='2026-10-22',material_cutoff='2026-10-20 Asia/Shanghai',files={})
    for p in sorted(out.rglob('*')):
        if p.is_file():manifest['files'][str(p.relative_to(out))]=dict(sha256=digest(p),bytes=p.stat().st_size)
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(validation,ensure_ascii=False))


if __name__=='__main__':
    main()
