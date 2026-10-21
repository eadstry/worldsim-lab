"""Assemble a local chartbook from sealed figures and small saved JSON receipts."""
from __future__ import annotations
import argparse
import csv
import hashlib
from html import escape
import json
from pathlib import Path
import shutil

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib import font_manager
import numpy as np
from PIL import Image, ImageOps, ImageDraw, ImageFont

PAPER = '#f7f6f2'
INK = '#263c3b'
TEAL = '#157c73'
GRAY = '#9aa9a6'
RED = '#b34f43'
FONT = '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc'

# Figure IDs remain stable; old PNG payloads are preserved byte-for-byte.
LEGACY = [
('01-shared-config','配置与随机化','共享配置接口','16/16 项接口与判据检查通过','16 项检查','接口一致性；不是学习策略等价性','shared'),
('02-export-24','生产效率','24 条导出对照','三模式严格终态均为 23/24；最终文件吞吐最高提高 29.8%','3 模式，各 24 条','最终文件就绪；24 条不是 24 并行环境','export24'),
('03-export-16','生产效率','16 条成功目标的导出对照','四配置各 17 次尝试、16 次生成成功；auto 提高约 60.2%','4 配置 × 17 次尝试','最终文件就绪；各保存 16 条终态通过','export16'),
('04-capacity','生产效率','固定尝试预算产能','20 个单元、74 次尝试；确认 seed 的提高为 34.5%–37.7%','5 seed；74 次尝试','仿真终态接受吞吐；正式批次未独立文件验收','capacity'),
('05-timing','生产效率','内部耗时归因','8 对动作哈希匹配；导出等待下降 93.8%','4 环境 × 8 对','主机墙钟归因；不是隔离 GPU kernel 时间','timing'),
('06-domain-randomization','配置与随机化','OpenArm 位姿随机化检查','256 个 reset 位姿，9/9 项检查通过','256 reset；9 项检查','随机化生效检查；不是完整任务或策略成功率','randomization'),
('07-g1','配置与随机化','G1 视觉随机化','7 段尝试中 6 段成功；纯视觉组合动作与基线一致','7 段','G1 家庭搬运；尚未验证训练泛化收益','g1'),
('08-curobo-mvp','规划与传感','cuRobo v1/v2 最小对照','完整任务 v1=5/5，v2=4/5；两版规划请求均 10/10','每版 5 任务；9 个后续请求','集成方案对照；请求非独立任务；内部配置不完全等价','mvp'),
('09-curobo-rerun','规划与传感','cuRobo v2 补跑','v2 生成并保存 16 条，严格终态通过 15 条','v2 保存 16 条','生成、保存与严格终态分别报告；v1 仍为默认','v2'),
('10-franka','规划与传感','Franka 配对避障','有障碍时 IK 0/3，cuRobo＋IK 3/3；无障碍均 3/3','4 条件 × 3 配对状态','局部桌面避障；不代表 OpenArm 或整屋避障','franka'),
('11-banana','规划与传感','香蕉多传感示范','950 帧；双指搬运法向力中位数约 38.7/38.8 N','1 条，19 秒','刚体香蕉；腕部为关节反力；不是压伤或力控验证','banana'),
('12-hdr','配置与随机化','OpenArm HDR 小批生产','5 批各 1 次，均通过已有验收','5 批 × 1 次','生产可行性；不同墙钟不构成 HDR 加速证据','hdr'),
('13-concurrency','资源与稳定性','历史 GPU 并发观测','4–5 进程峰值 70%；均值约 9.4%–32.4%','历史混合工作负载','峰值不是持续高利用率；部分轮次含被终止任务','concurrency'),
('14-production-100','资源与稳定性','历史 100 条成功目标运行','63 次开始、55 次完成、8 次未完成；最终运行中断','目标 100 条成功；不是固定 100 次尝试','SIGKILL 并伴 cgroup OOM 事件；不能据此确定 OOM 受害进程','history'),
]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_sealed(root):
    manifest = json.loads((root / 'manifest.json').read_text())
    for name, expected in manifest['files'].items():
        path = Path(name)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('Unsafe sealed path')
        value = expected['sha256'] if isinstance(expected, dict) else expected
        if digest(root / path) != value:
            raise ValueError('Sealed source changed: ' + name)
    return manifest


def setup():
    font_manager.fontManager.addfont(FONT)
    family = font_manager.FontProperties(fname=FONT).get_name()
    plt.rcParams.update({'font.family': family, 'font.size': 11, 'axes.unicode_minus': False,
                         'figure.facecolor': PAPER, 'axes.facecolor': PAPER,
                         'text.color': INK, 'axes.labelcolor': INK, 'xtick.color': INK,
                         'ytick.color': INK, 'axes.edgecolor': '#c8d1cd',
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'pdf.fonttype': 42, 'svg.fonttype': 'path', 'savefig.facecolor': PAPER})


def page(title, subtitle, note, panels=1):
    fig, axes = plt.subplots(1, panels, figsize=(11.69, 8.27), squeeze=False)
    fig.subplots_adjust(left=.1, right=.94, top=.76, bottom=.23, wspace=.38)
    fig.text(.075, .92, title, fontsize=20, weight='medium')
    fig.text(.075, .85, subtitle, fontsize=12)
    fig.text(.075, .085, note, fontsize=10)
    return fig, axes[0]


def bars(ax, labels, values, colors, unit, top, annotations=None):
    ax.bar(labels, values, color=colors, width=.55)
    ax.set_ylim(0, top)
    ax.set_ylabel(unit)
    ax.grid(axis='y', alpha=.15)
    ax.set_axisbelow(True)
    for i, value in enumerate(values):
        label = annotations[i] if annotations else f'{value:g}'
        ax.text(i, value + top * .035, label, ha='center', va='bottom', fontsize=12)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-workspace', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--regression', type=Path, required=True)
    parser.add_argument('--conversion', type=Path, required=True)
    parser.add_argument('--failure-state', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    reference = args.reference_workspace.resolve()
    portfolio = reference / 'outputs/embodied-experiment-portfolio/v004'
    verify_sealed(portfolio)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    figures, evidence = out / 'figures', out / 'evidence'
    figures.mkdir(); evidence.mkdir()
    sources, data = {}, {}

    def collect(key, path):
        payload = path.read_bytes()
        target = evidence / (key + path.suffix)
        target.write_bytes(payload)
        sources[key] = dict(original_path=str(path.resolve()), local_path=str(target.relative_to(out)),
                            sha256=hashlib.sha256(payload).hexdigest(), bytes=len(payload))
        if path.suffix == '.json':
            data[key] = json.loads(payload)

    mapping = {
        'shared': reference / 'outputs/autodata-arena-shared-config/v003/comparison.json',
        'export24': reference / 'outputs/autodata-efficiency-report/v001/evidence.json',
        'export16': reference / 'outputs/autodata-efficiency-review/v003/data.json',
        'timing': reference / 'outputs/autodata-v1-internal-timing/v001/report.json',
        'randomization': reference / 'outputs/autodata-domain-randomization/v002/result.json',
        'mvp': reference / 'outputs/curobo-v2-openarm-mvp/v001/data.json',
        'v2': reference / 'outputs/autodata-efficiency-review/v003/v2-result.json',
        'history': reference / 'docs/process-log.md',
        'capacity': args.evidence / 'production-capacity-r04-report.json',
        'g1': args.evidence / 'g1-final-review-summary.json',
        'franka': args.evidence / 'franka-curobo-summary.json',
        'banana': args.evidence / 'banana-sensor-verification.json',
        'hdr': args.evidence / 'hdr-summary-console.json',
        'concurrency': args.evidence / 'gpu-parallelism-summary.json',
        'audit': args.audit,
        'regression': args.regression / 'report.json',
        'readback': args.regression / 'validation.json',
        'conversion': args.conversion,
        'failure': args.failure_state,
        'legacy-manifest': portfolio / 'manifest.json',
    }
    for key, path in mapping.items():
        collect(key, path)
    records = []
    for name, group, title, result, sample, scope, source in LEGACY:
        src = portfolio / 'figures' / (name + '.png')
        dst = figures / src.name
        shutil.copyfile(src, dst)
        assert digest(src) == digest(dst)
        records.append(dict(id=name, group=group, title=title, result=result, sample=sample,
                            scope=scope, source=source, png=str(dst.relative_to(out)),
                            origin='reused_exact', png_sha256=digest(dst), svg=None))

    # A tidy numeric index, never an aggregate success rate across tasks.
    metrics = []
    def add(figure, metric, condition, value, unit, n, source, scope):
        metrics.append(dict(figure=figure, metric=metric, condition=condition, value=value,
                            unit=unit, sample_n=n, source=source, scope=scope))
    shared = data['shared']['checks']
    add('01','interface_checks_passed','shared',sum(shared.values()),'checks',len(shared),'shared','接口检查')
    for row in data['export24']['async_validation']['gpu']['runs']:
        label = f"workers={row['workers']}"
        for metric, field, unit in [('final_ready_rate','final_ready_per_minute','episodes/min'),
                                    ('terminal_passes','terminal_successes','episodes')]:
            add('02',metric,label,row[field],unit,24,'export24','最终文件就绪；严格终态另列')
    for row in data['export16']['latest']:
        add('03','final_ready_rate',row['label'],row['rate'],'episodes/min',17,'export16','16 成功目标；每配置 17 次尝试')
    for row in data['capacity']['rows']:
        add('04','terminal_accepted_rate',row['label'],row['terminal_accepted_per_minute'],
            'episodes/min',row['stats']['num_attempts'],'capacity','仅生产模式；未独立文件验收')
    for row in data['timing']['runs']:
        add('05','final_ready_seconds',row['name'],row['final_ready_seconds'],'s',8,'timing','主机墙钟')
        for stage, value in row['execute_phase_mean_seconds'].items():
            add('05','execute_phase_mean',row['name']+'/'+stage,value,'s/episode',8,'timing','主机计时阶段')
    for key, value in data['randomization']['checks'].items():
        add('06','check_passed',key,int(value),'boolean',256,'randomization','reset 检查；非任务成功')
    for row in data['g1']['episodes']:
        add('07','task_success',row['name'],int(row['success']),'boolean',1,'g1','G1 小样本')
        add('07','image_mae',row['name'],row['matched_step_rgb_mae_255']['head'],'0–255',1,'g1','图像差；非泛化收益')
    for row in data['mvp']['runs']:
        for metric, field, unit in [('task_successes','successes','episodes'),
                                    ('warm_p50','request_warm_p50_seconds','s'),
                                    ('warm_p95','request_warm_p95_seconds','s')]:
            sample_n = row['attempts'] if metric == 'task_successes' else row['request_warm_sample_count']
            add('08',metric,row['backend'],row[field],unit,sample_n,'mvp','任务与后续请求分开计数；v1/v2 集成配置不同')
    assert {r['backend']: (r['attempts'], r['successes']) for r in data['mvp']['runs']} == {'v1': (5,5), 'v2': (5,4)}
    add('09','terminal_passes','v2',data['v2']['physical_passes'],'episodes',data['v2']['saved_episodes'],'v2','保存样本终态检查')
    for row in data['franka']['cells']:
        label = row['method'] + ('/obstacle' if row['obstacle'] else '/clear')
        add('10','collision_free_successes',label,row['collision_free_successes'],'episodes',row['completed'],'franka','配对局部避障')
    for i, value in enumerate(data['banana']['median_transfer_finger_normal_N']):
        add('11','median_transfer_normal_force',str(i),value,'N',1,'banana','刚体香蕉；力曲线非独立试次')
    for row in data['hdr']:
        add('12','wall_seconds',row['name'],row['seconds'],'s',1,'hdr','配置可行性；非速度对照')
    for row in data['concurrency']['rounds']:
        for field in ['gpu_mean_percent','gpu_peak_percent']:
            add('13',field,row['round'],row[field],'%',1,'concurrency',
                f"观测 1 轮、{row['duration_seconds']:.1f}s、{row['effective_workers']} 并发；历史混合负载，含失败轮次")
    # Explicit historical accounting from the saved process log; not recovered trajectories.
    history = (evidence / 'history.md').read_text()
    assert '63 次开始、55 次完成' in history and '成功 49、失败 6' in history
    for name, value in [('started',63),('completed',55),('success',49),('failure',6),('unfinished',8)]:
        add('14','telemetry_count',name,value,'episodes',63,'history','日志计数；最终 HDF5 未验收')

    setup()
    fresh = []
    def save_new(name, group, title, result, sample, scope, source, fig):
        path = figures / name
        fig.savefig(path.with_suffix('.png'), dpi=180)
        fig.savefig(path.with_suffix('.svg'))
        record = dict(id=name, group=group, title=title, result=result, sample=sample, scope=scope,
                      source=source, png=f'figures/{name}.png', svg=f'figures/{name}.svg',
                      origin='drawn_from_saved_json', png_sha256=digest(path.with_suffix('.png')))
        records.append(record); fresh.append((record, fig))

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

    group_order = ['生产效率','配置与随机化','规划与传感','资源与稳定性','本轮验收']
    records.sort(key=lambda record: (group_order.index(record['group']), record['id']))

    # PDF cover and one landscape page per chart. New chart pages retain vector artists.
    with PdfPages(out / 'experiment-chartbook.pdf') as pdf:
        fig = plt.figure(figsize=(11.69,8.27),facecolor=PAPER)
        fig.text(.07,.92,'具身数据生产 · 实验图册',fontsize=24)
        fig.text(.07,.86,'材料截至 2026-10-20｜14 张历史原图 + 5 张验收补图｜未新增仿真或训练',fontsize=12)
        table_ax = fig.add_axes([.07,.19,.86,.61]);table_ax.axis('off')
        rows = [[r['id'][:2],r['group'],r['title'],r['sample']] for r in records]
        table = table_ax.table(cellText=rows,colLabels=['图号','主题','实验','样本与范围'],loc='center',
                              colWidths=[.06,.15,.47,.32],cellLoc='left')
        table.auto_set_font_size(False);table.set_fontsize(8.5);table.scale(1,1.28)
        for (row,col), cell in table.get_celld().items():
            cell.set_edgecolor('#dde2de');cell.set_linewidth(.35)
            cell.set_facecolor('#e9eeea' if row==0 else PAPER)
        fig.text(.07,.08,'阅读口径：成功标签、文件回读、严格终态分开；不同机器人/任务不合并成功率。\n24 条数据 ≠ 24 并行环境。历史 100 条成功目标运行仍未完成；扩增训练闭环尚未开展。',fontsize=10)
        pdf.savefig(fig);plt.close(fig)
        new_pages = {record['id']: fig for record, fig in fresh}
        for record in records:
            if record['id'] in new_pages:
                fig = new_pages[record['id']]
                pdf.savefig(fig);plt.close(fig)
                continue
            fig = plt.figure(figsize=(11.69,8.27),facecolor=PAPER)
            fig.text(.065,.94,f"{record['id'][:2]} / {record['group']} · {record['title']}",fontsize=17)
            fig.text(.065,.885,record['result'],fontsize=11)
            axes = fig.add_axes([.04,.235,.92,.58]);axes.axis('off')
            axes.imshow(Image.open(out / record['png']))
            fig.text(.065,.14,'样本：'+record['sample']+'\n口径：'+record['scope'],fontsize=10)
            fig.text(.065,.06,'原图逐字节复用；来源：'+sources[record['source']]['local_path'],fontsize=8.5)
            pdf.savefig(fig);plt.close(fig)
        pages = pdf.get_pagecount()
    assert pages == len(records)+1

    fields = ['figure','metric','condition','value','unit','sample_n','source','scope']
    with (out / 'metrics.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(metrics)
    with (out / 'chart-index.csv').open('w',newline='',encoding='utf-8-sig') as f:
        fields=['id','group','title','result','sample','scope','source','origin','png','svg']
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(records)
    (out/'sources.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2)+'\n')
    (out/'chart-index.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
    report = ['# 具身数据生产实验图册','',
              '材料截至 2026-10-20。整理已有记录，没有新增仿真、训练或大型 HDF5 扫描。',
              '',f'共 {len(records)} 张图、{pages} 页 PDF；14 张历史 PNG 按原字节复用，5 张新图由保存的 JSON/末态向量绘制。',
              '', '入口：[本地图册](index.html) · [PDF](experiment-chartbook.pdf) · [图表索引](chart-index.csv) · [主要指标及阶段数据](metrics.csv)',
              '', '口径：24 条数据与 24 并行环境不同；成功标签、文件回读和严格终态分别报告。不同机器人、任务和重复观测不合并样本量或成功率。',
              '', '已明确 cuRobo 最小对照：v1=5/5、v2=4/5。历史混合并发的 70% 是峰值；历史 100 条目标中断不作为完成数据量。',
              '', '当前缺口：右腕持续近黑；24 环境内存准入受阻；正式扩增方法比较与学习策略训练/泛化仍未完成。']
    for record in records:
        report += ['',f"## {record['id']} · {record['title']}",'',record['result'],
                   '',f"样本：{record['sample']}。口径：{record['scope']}。",'',
                   f"![{record['title']}]({record['png']})",'',
                   f"来源：[{record['source']}]({sources[record['source']]['local_path']})。"]
    (out/'report.md').write_text('\n'.join(report)+'\n')
    navigation=''.join(f'<a href="#{escape(r["id"])}">{r["id"][:2]} {escape(r["title"])}</a>' for r in records)
    cards=[]
    for record in records:
        source=sources[record['source']]['local_path']
        vector=f' · <a href="{record["svg"]}">SVG</a>' if record['svg'] else ''
        cards.append(f'<section id="{record["id"]}"><div class="group">{escape(record["group"])}</div>'
                     f'<h2>{escape(record["title"])}</h2><p class="result">{escape(record["result"])}</p>'
                     f'<img src="{record["png"]}" alt="{escape(record["title"])}" loading="lazy">'
                     f'<p><strong>样本：</strong>{escape(record["sample"])}<br><strong>口径：</strong>{escape(record["scope"])}</p>'
                     f'<p class="links"><a href="{record["png"]}">PNG</a>{vector} · <a href="{source}">来源记录</a></p></section>')
    html='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>具身数据生产实验图册</title><style>
body{margin:0;background:#f7f6f2;color:#263c3b;font-family:system-ui,"Noto Sans CJK SC",sans-serif;line-height:1.7}header,main{max-width:1080px;margin:auto;padding:28px}h1{margin:0;font-weight:600}a{color:#157c73}nav{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:8px}nav a{padding:6px 0}section{padding:28px 0;border-top:1px solid #dce2dd;scroll-margin-top:12px}section img{width:100%;height:auto}h2{margin:4px 0}.group,.links{font-size:14px;color:#526764}.result{font-size:19px;margin:8px 0}.note{background:#e9eeea;padding:16px}header .downloads{display:flex;gap:18px;flex-wrap:wrap}@media(max-width:600px){header,main{padding:18px}.result{font-size:17px}}@media print{nav,.downloads{display:none}section{break-inside:avoid}header,main{padding:0}}</style></head><body><header><h1>具身数据生产 · 实验图册</h1><p>材料截至 2026-10-20 · 19 张图 · 20 页 PDF · 本轮仅整理已有证据</p><div class="downloads"><a href="experiment-chartbook.pdf">完整 PDF</a><a href="chart-index.csv">图表索引 CSV</a><a href="metrics.csv">主要指标 CSV</a><a href="sources.json">来源与校验</a></div><p class="note">成功标签、文件回读、严格终态分别报告。24 条数据 ≠ 24 并行环境。当前右腕近黑、24 环境内存准入受阻；策略训练与泛化尚未完成。</p><nav>'''+navigation+'</nav></header><main>'+''.join(cards)+'</main></body></html>'
    (out/'index.html').write_text(html)
    # Compact overview for visual inspection; individual charts remain full resolution.
    width, height = 480, 255
    sheet=Image.new('RGB',(width*3,height*7),PAPER)
    draw=ImageDraw.Draw(sheet);font=ImageFont.truetype(FONT,15)
    for i, record in enumerate(records):
        x,y=(i%3)*width,(i//3)*height
        thumb=ImageOps.contain(Image.open(out/record['png']).convert('RGB'),(width-20,height-38))
        sheet.paste(thumb,(x+(width-thumb.width)//2,y+8))
        draw.text((x+12,y+height-29),f'{record["id"][:2]} {record["title"]}',font=font,fill=INK)
    sheet.save(out/'overview.png')
    validation_record=dict(status='passed',charts=len(records),pdf_pages=pages,
                           legacy_figures_byte_identical=14,new_figures=5,metric_rows=len(metrics),
                           new_simulation=False,new_training=False,
                           legacy_source_manifest_sha256=digest(portfolio/'manifest.json'),
                           v1_v2_labels_verified_against_raw_json=True,
                           scope='Saved-source chart assembly and numerical extraction; no revalidation of old simulation')
    (out/'validation.json').write_text(json.dumps(validation_record,ensure_ascii=False,indent=2)+'\n')
    payload={str(p.relative_to(out)):dict(sha256=digest(p),bytes=p.stat().st_size)
             for p in sorted(out.rglob('*')) if p.is_file()}
    manifest=dict(schema_version=1,artifact_id='experiment-chartbook',version='v001',
                  sealed_at='2026-10-20',material_cutoff='2026-10-20 Asia/Shanghai',
                  files=payload,sources=sources,scope=validation_record['scope'],
                  delivery=dict(local=dict(status='saved'),external=dict(status='not_uploaded')))
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(validation_record,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
