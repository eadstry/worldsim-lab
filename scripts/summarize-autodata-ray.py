#!/usr/bin/env python3
"""Summarize measured production runs; failed runs never receive valid throughput."""
import argparse
import json
from pathlib import Path
import statistics


def summarize(case):
    config = json.loads((case / 'config.json').read_text())
    result = json.loads((case / 'result.json').read_text())
    samples = [json.loads(line) for line in (case / 'gpu.jsonl').read_text().splitlines()]
    valid = [s for s in samples if s.get('returncode') == 0 and s.get('csv')]
    values = [[float(v) for v in s['csv'].split(',')[2:]] for s in valid]
    utilization = sorted(v[0] for v in values)
    telemetry = [json.loads(p.read_text()) for p in case.glob('process-*/episodes.telemetry-summary.json')]
    good = result['status'] == 'succeeded'
    return dict(case=case.name, source=str(case), config=config, status=result['status'],
        seconds=result['seconds'], episodes=result.get('episodes', 0), frames=result.get('frames', 0),
        valid_frames_per_second=result.get('frames_per_second') if good else None,
        valid_episodes_per_hour=result.get('episodes_per_second', 0)*3600 if good else None,
        gpu_sample_count=len(samples), gpu_valid_sample_count=len(valid),
        gpu_utilization_sample_mean=statistics.mean(utilization) if utilization else None,
        gpu_utilization_p95=utilization[min(len(utilization)-1, int(.95*len(utilization)))] if utilization else None,
        gpu_peak_mib=max(v[2] for v in values) if values else None,
        max_valid_sample_gap_seconds=max((b['time']-a['time'] for a,b in zip(valid,valid[1:])),default=0),
        host_available_ram_min_gib=min(s['available_ram_bytes'] for s in samples)/2**30,
        disk_free_min_gib=min(s['free_disk_bytes'] for s in samples)/2**30,
        resource_stop=json.loads((case/'resource-stop.json').read_text()) if (case/'resource-stop.json').exists() else None,
        intervention=json.loads((case/'intervention.json').read_text()) if (case/'intervention.json').exists() else None,
        async_export=[t.get('async_export') for t in telemetry],
        episode_counts={key: sum(t.get(key, 0) for t in telemetry) for key in
                        ('episodes_started', 'episodes_completed', 'successes', 'failures', 'cancelled')},
        cgroup_events_after=result.get('cgroup_events_after'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cases', type=Path, nargs='+')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--figure', type=Path)
    parser.add_argument('--validation', type=Path, nargs='*', default=[])
    parser.add_argument('--host-context', type=Path)
    args = parser.parse_args()
    rows = [summarize(p) for p in args.cases]
    payload = dict(cases=rows, validation=[row for path in args.validation
                   for row in json.loads(path.read_text())])
    if args.host_context:
        payload['host_context'] = json.loads(args.host_context.read_text())
    args.output.write_text(json.dumps(payload, indent=2) + '\n')
    if args.figure:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(2, 2, figsize=(14, 8), constrained_layout=True)
        labels = [f"{r['config']['processes']} x {r['config']['envs']}\nn={r['config']['trials']}\n{'OK' if r['status']=='succeeded' else 'failed'}" for r in rows]
        fields = [('valid_frames_per_second', 'Valid frames / second'),
                  ('gpu_utilization_sample_mean', 'GPU busy sample mean (%; failed runs partial)'),
                  ('gpu_peak_mib', 'Peak GPU memory (MiB)'),
                  ('host_available_ram_min_gib', 'Minimum available host RAM (GiB)')]
        for ax, (key, title) in zip(axes.flat, fields):
            for i, row in enumerate(rows):
                value = row[key]
                if value is not None:
                    ax.bar(i, value, color='#26828e' if row['status']=='succeeded' else '#be6347')
                    ax.text(i, value, f'{value:.1f}', ha='center', va='bottom', fontsize=9)
                else:
                    ax.text(i, 0, 'N/A', ha='center')
            ax.set_xticks(range(len(rows)), labels, fontsize=9)
            ax.set_title(title)
            ax.margins(y=.16)
            ax.grid(axis='y', alpha=.2)
        axes[1,0].axhline(32607, color='gray', linestyle='--', label='GPU capacity')
        axes[1,0].legend(fontsize=8)
        for threshold in sorted({r['config'].get('min_available_ram_gib', 8) for r in rows}):
            axes[1,1].axhline(threshold, color='gray', linestyle='--', label=f'RAM reserve {threshold:g} GiB')
        axes[1,1].legend(fontsize=8)
        fig.suptitle('AutoData direct LeRobot v3: controlled concurrency and capacity (single runs)')
        fig.savefig(args.figure, dpi=160)
