#!/usr/bin/env python3
"""Reproduce report charts from measured logs, or from their portable trace snapshot."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path


def snapshot(summary):
    rows = json.loads(summary.read_text())['cases']
    traces = {}
    for row in rows:
        root = Path(row['source'])
        origin = row['config']['started_unix']
        samples, events, hashes = [], [], {}
        path = root / 'gpu.jsonl'
        hashes['gpu.jsonl'] = hashlib.sha256(path.read_bytes()).hexdigest()
        for line in path.read_text().splitlines():
            sample = json.loads(line)
            values = sample['csv'].split(',') if sample.get('returncode') == 0 and sample.get('csv') else []
            samples.append([sample['time'] - origin, float(values[2]) if values else None,
                            float(values[4])/1024 if values else None,
                            sample['available_ram_bytes']/2**30])
        for path in sorted(root.glob('process-*/episodes.telemetry.jsonl')):
            hashes[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
            for line in path.read_text().splitlines():
                event = json.loads(line)
                if event['event'] not in ('export_saved', 'export_submitted'):
                    continue
                event = {k: event[k] for k in ('event', 'time_utc', 'frames', 'queue_wait_seconds', 'packing_seconds') if k in event}
                event['seconds'] = datetime.fromisoformat(event.pop('time_utc')).timestamp() - origin
                event['process'] = path.parent.name
                events.append(event)
        events.sort(key=lambda e: e['seconds'])
        if row['status'] == 'succeeded':
            saved = [e for e in events if e['event'] == 'export_saved']
            assert len(saved) == row['episodes']
            assert sum(e['frames'] for e in saved) == row['frames']
        traces[row['case']] = dict(samples=samples, events=events, source_sha256=hashes)
    return dict(sample_columns=['elapsed_seconds', 'gpu_busy_percent', 'gpu_memory_gib', 'host_available_ram_gib'],
                cases=rows, traces=traces)


def plot(data, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    import numpy as np
    font_manager.fontManager.addfont('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')
    plt.rcParams.update({'font.family': 'Noto Sans CJK JP', 'font.size': 10,
                         'axes.unicode_minus': False, 'axes.spines.top': False,
                         'axes.spines.right': False, 'savefig.dpi': 200})
    by_name = {r['case']: r for r in data['cases']}
    names = ['shared-formal-p1-e4-r1', 'shared-formal-p2-e2-r1', 'shared-capacity-p1-e8-r1']
    rows = [by_name[n] for n in names]
    colors = ['#2979a8', '#dc7847', '#29927d']
    labels = ['1 进程 × 4 环境', '2 进程 × 2 环境', '1 进程 × 8 环境']

    def save(fig, name):
        fig.savefig(output / (name + '-20261022.png'), facecolor='white')
        plt.close(fig)

    def decorate(ax, ylabel):
        ax.set_ylabel(ylabel)
        ax.grid(axis='y', alpha=.18)
        ax.set_axisbelow(True)

    def bars(ax, values, title, unit):
        ax.bar(range(3), values, color=colors, width=.6)
        ax.set_xticks(range(3), ['1×4', '2×2', '1×8'])
        for i, value in enumerate(values):
            ax.text(i, value, f'{value:.2f}', ha='center', va='bottom')
        ax.set_title(title)
        decorate(ax, unit)
        ax.margins(y=.18)

    fig, axes = plt.subplots(1, 2, figsize=(7.2, 4.1), constrained_layout=True)
    bars(axes[0], [r['valid_frames_per_second'] for r in rows], '实际有效产出', '帧 / 秒（越高越好）')
    bars(axes[1], [r['seconds'] for r in rows], '完成整个批次的时间', '秒（越低越好）')
    fig.suptitle('01 生产效率：三个配置均以 8 条成功轨迹为目标')
    save(fig, 'throughput')

    fig, axes = plt.subplots(1, 2, figsize=(7.2, 4.1), constrained_layout=True)
    x = np.arange(3)
    for offset, key, title, color in [(-.18, 'gpu_utilization_sample_mean', '全程均值', '#2979a8'),
                                    (.18, 'gpu_utilization_p95', '样本 P95', '#9fbcd0')]:
        v = [r[key] for r in rows]
        axes[0].bar(x+offset, v, width=.34, label=title, color=color)
        for i, value in enumerate(v):
            axes[0].text(i+offset, value+1, f'{value:.1f}', ha='center', fontsize=8)
    axes[0].set_xticks(x, ['1×4', '2×2', '1×8'])
    axes[0].set_ylim(0, 108)
    axes[0].legend(loc='upper left', fontsize=8)
    decorate(axes[0], 'GPU 忙碌时间比例（%）')
    for r, label, color in zip(rows, ['1×4', '2×2', '1×8'], colors):
        axes[1].scatter(r['gpu_utilization_sample_mean'], r['valid_frames_per_second'], color=color, s=100)
        axes[1].annotate(label, (r['gpu_utilization_sample_mean'], r['valid_frames_per_second']),
                         xytext=(7, 5), textcoords='offset points')
    axes[1].set_xlim(0, 85)
    axes[1].set_ylim(0, 36)
    axes[1].set_xlabel('GPU 全程均值（%）')
    decorate(axes[1], '有效帧 / 秒')
    fig.suptitle('02 GPU 更忙，并不保证有效数据产出更多')
    save(fig, 'gpu-efficiency')

    def series(name, column, bin_seconds=None):
        samples = data['traces'][name]['samples']
        if bin_seconds:
            bins = {}
            for sample in samples:
                if sample[column] is not None:
                    bins.setdefault(int(sample[0] // bin_seconds), []).append((sample[0], sample[column]))
            indices = range(min(bins), max(bins)+1)
            return ([np.mean([p[0] for p in bins[i]]) if i in bins else i*bin_seconds+bin_seconds/2 for i in indices],
                    [np.mean([p[1] for p in bins[i]]) if i in bins else np.nan for i in indices])
        t, v, previous = [], [], None
        for sample in samples:
            if previous is not None and sample[0]-previous > 5:
                t.append((sample[0]+previous)/2); v.append(np.nan)
            t.append(sample[0]); v.append(sample[column] if sample[column] is not None else np.nan)
            previous = sample[0]
        return t, v

    fig, axes = plt.subplots(3, 1, figsize=(7.2, 5.2), sharex=True, constrained_layout=True)
    for ax, name, label, color in zip(axes, names, labels, colors):
        ax.plot(*series(name, 1), color=color, alpha=.22, linewidth=.6, label='原始采样')
        ax.plot(*series(name, 1, 10), color=color, linewidth=1.6, label='10 秒分箱均值')
        events = data['traces'][name]['events']
        for kind, style, legend in [('export_submitted', ':', '首次提交导出'), ('export_saved', '--', '首次写入确认')]:
            stamp = next(e['seconds'] for e in events if e['event']==kind)
            ax.axvline(stamp, linestyle=style, color='#59616b', linewidth=1, label=legend)
        ax.set_ylim(0, 103)
        ax.set_title(label, loc='left', fontsize=10)
        decorate(ax, 'GPU（%）')
    axes[0].legend(ncol=4, fontsize=7, loc='upper right')
    axes[-1].set_xlabel('从批次启动起的实际秒数；各曲线在本批次结束处停止')
    fig.suptitle('03 利用率时间曲线：执行、导出与等待交替出现')
    save(fig, 'gpu-timeline')

    memory_names = ['shared-production-p1-e8-r1', 'shared-formal-p2-e4-r2',
                    'shared-capacity-p1-e9-r1', 'shared-capacity-p1-e10-r1', 'shared-capacity-p1-e12-r1']
    memory_labels = ['1×8，16 条完成', '2×4，余量保护停止', '1×9，余量保护停止',
                     '1×10，余量保护停止', '1×12，失联后停止']
    palette = ['#29927d', '#dc7847', '#7d63ae', '#d0a021', '#a84850']
    fig, axes = plt.subplots(2, 1, figsize=(7.2, 5.1), sharex=True, constrained_layout=True)
    for name, label, color in zip(memory_names, memory_labels, palette):
        for ax, col in zip(axes, [2, 3]):
            ax.plot(*series(name, col), color=color, linewidth=1.35, label=label)
        stop = by_name[name]['resource_stop']
        if stop:
            stamp = stop['time']-by_name[name]['config']['started_unix']
            axes[1].scatter(stamp, stop['available_ram_bytes']/2**30, color=color, marker='x', s=45, zorder=5)
    axes[0].axhline(32607/1024, color='#777', linestyle='--', linewidth=1)
    axes[0].text(5, 32.6, '可用显存容量 31.84 GiB', ha='left', fontsize=8)
    axes[0].annotate('12 环境：约 115 秒采样缺口', xy=(300, 14.4), xytext=(240, 22), fontsize=8,
                     arrowprops=dict(arrowstyle='->', color='#a84850'), color='#a84850')
    axes[0].set_ylim(0, 36)
    axes[0].legend(ncol=2, fontsize=8, loc='upper right')
    decorate(axes[0], 'GPU 显存（GiB）')
    axes[1].axhline(14, color='#777', linestyle='--', linewidth=1)
    axes[1].text(665, 15.3, '强化后的 14 GiB 余量', ha='right', fontsize=8)
    axes[1].set_ylim(0, 65)
    decorate(axes[1], '主机可用内存（GiB）')
    axes[1].set_xlabel('从各批次启动起的秒数（包含退出和资源释放）')
    fig.suptitle('04 显存尚有空间，主机内存先耗尽余量')
    save(fig, 'memory')

    export_rows, export_labels = [], []
    for name in names + ['shared-production-p1-e8-r1']:
        row = by_name[name]
        for i, worker in enumerate(row['async_export']):
            export_rows.append(worker)
            c = row['config']
            export_labels.append(f"{c['processes']}×{c['envs']}" + (f"\n进程 {i+1}" if c['processes']>1 else '') + f"\n{worker['saved']} 条")
    fig, axes = plt.subplots(2, 1, figsize=(7.2, 5), constrained_layout=True)
    x = np.arange(len(export_rows))
    wait = [r['queue_wait_seconds']/r['saved'] for r in export_rows]
    pack = [r['packing_seconds']/r['saved'] for r in export_rows]
    axes[0].bar(x-.18, wait, .34, label='提交时等待队列空位', color='#dc7847')
    axes[0].bar(x+.18, pack, .34, label='共享内存打包', color='#2979a8')
    for i, value in enumerate(wait):
        axes[0].text(i-.18, value+.15, f'{value:.2f}', ha='center', fontsize=9)
    axes[0].set_ylim(0, 15)
    axes[0].legend(fontsize=8)
    decorate(axes[0], '累计秒数 / 成功条数')
    values = [r['write_seconds']['mean'] for r in export_rows]
    axes[1].bar(x, values, .55, color='#29927d')
    for i, value in enumerate(values):
        axes[1].text(i, value+.5, f'{value:.2f}', ha='center')
    axes[1].set_ylim(0, 45)
    decorate(axes[1], 'writer 每条平均写入秒数')
    for ax in axes:
        ax.set_xticks(x, export_labels, fontsize=9)
    fig.suptitle('05 导出端的等待：按进程单独统计，不累加并发耗时')
    save(fig, 'export')

    long_name = 'shared-production-p1-e8-r1'
    fig, axes = plt.subplots(2, 1, figsize=(7.2, 4.8), sharex=True, constrained_layout=True)
    for name, color, label in [(names[2], '#2979a8', '8 条目标'), (long_name, '#29927d', '16 条目标')]:
        events = [e for e in data['traces'][name]['events'] if e['event']=='export_saved']
        t = [0]+[e['seconds'] for e in events]+[by_name[name]['seconds']]
        counts = [0]+list(range(1,len(events)+1))+[len(events)]
        axes[0].step(t, counts, where='post', color=color, linewidth=1.8, label=label,
                     linestyle='--' if name==names[2] else '-', zorder=4 if name==names[2] else 2)
        axes[0].scatter(t[-1], counts[-1], color=color)
    axes[0].set_yticks([0,4,8,12,16])
    axes[0].legend(fontsize=9)
    decorate(axes[0], '收到写入确认的累计条数')
    axes[1].plot(*series(long_name, 1, 10), color='#29927d', linewidth=1.5, label='16 条批次：GPU 10 秒均值')
    first = True
    for e in data['traces'][long_name]['events']:
        if e['event']=='export_submitted' and e['queue_wait_seconds'] > .5:
            end = e['seconds']-e['packing_seconds']
            axes[1].axvspan(end-e['queue_wait_seconds'], end, color='#e5bd63', alpha=.35,
                           label='近似队列等待区间' if first else None)
            first = False
    axes[1].set_ylim(0, 103)
    axes[1].legend(fontsize=8, loc='upper right')
    decorate(axes[1], 'GPU（%）')
    axes[1].set_xlabel('批次启动后的实际秒数（同为 1 进程 × 8 环境）')
    fig.suptitle('06 连续生产：第一批写入后，第二批仍有等待')
    save(fig, 'production')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summary', type=Path)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.summary:
        data = snapshot(args.summary)
        args.evidence.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
    else:
        data = json.loads(args.evidence.read_text())
    plot(data, args.output_dir)
