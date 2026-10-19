# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Collect compatible local runs into portable data without machine paths."""
from __future__ import annotations

import argparse
from pathlib import Path
import statistics

from bench32 import aggregate, digest, journal, read, write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reports', nargs='+', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    reports = [read(p) for p in args.reports]
    sources = {r['source_sha256'] for r in reports}
    targets = {r['target'] for r in reports}
    tasks = {v['task_sha256'] for r in reports for v in r['variants']}
    if len(sources) != 1 or targets != {32} or len(tasks) != 1:
        parser.error('Reports must share source hash, task hash and 32-success target')
    if any(r['repeats'] != reports[0]['repeats'] for r in reports):
        parser.error('Cannot combine different repeat counts')
    if len({r.get('terminal_gate', False) for r in reports}) != 1:
        parser.error('Cannot compare different terminal acceptance policies')
    rows, seen, incomplete = [], set(), []
    for report, path in zip(reports, args.reports):
        for raw in report['rows']:
            key = (raw['variant'], raw['num_envs'], raw['seed'], raw['repeat'])
            if raw['status'] == 'starting':
                incomplete.append(dict(variant=raw['variant'], num_envs=raw['num_envs'], seed=raw['seed'],
                                       repeat=raw['repeat'], evidence_run=path.parent.name))
                continue
            if key in seen:
                parser.error(f'Duplicate cell: {key}; select one report explicitly')
            seen.add(key)
            row = {k: v for k, v in raw.items() if k not in ('command', 'error')}
            if 'error' in raw:
                row['error_kind'] = raw['error'].split(':', 1)[0]
                row['error_summary'] = raw['error'] if '/' not in raw['error'] else 'See local run journal'
            row['evidence_run'] = path.parent.name
            cell = path.parent / f'{raw["variant"]}-env{raw["num_envs"]}-seed{raw["seed"]}-rep{raw["repeat"]}'
            events = journal(cell / 'dataset.telemetry.jsonl')
            row['terminal_rejections'] = sum(e.get('passed') is False for e in events
                                             if e.get('event') == 'recorded_terminal_acceptance')
            if row['status'] == 'failed':
                samples = journal(cell / 'dataset.resources.jsonl')
                row['oom_observed'] = any(s.get('cgroup_memory_event_deltas', {}).get('oom_kill', 0) for s in samples)
                row['peak_process_rss_gib'] = max((s.get('process_rss_bytes') or 0 for s in samples), default=0) / 2**30
                gpu = [g['utilization_percent'] for s in samples for g in s.get('gpus', [])
                       if isinstance(g.get('utilization_percent'), (int, float))]
                row['observed_gpu_util_mean_including_startup'] = statistics.mean(gpu) if gpu else None
                telemetry = cell / 'dataset.telemetry-summary.json'
                if telemetry.exists():
                    state = read(telemetry)
                    row['observed_successes'] = state.get('successes')
                    row['observed_elapsed_seconds'] = state.get('elapsed_seconds')
            if row['status'] == 'valid' and 'episode_steps_mean' not in row:
                episodes = read(cell / 'dataset.validation.json')['episodes']
                steps = [e['steps'] for e in episodes]
                row.update(episode_steps_mean=sum(steps) / len(steps), episode_steps_min=min(steps), episode_steps_max=max(steps))
            rows.append(row)
    baseline = reports[0]['variants'][0]['name']
    result = dict(schema_version=1, target=32, source_sha256=next(iter(sources)), task_sha256=next(iter(tasks)),
                  repeats=reports[0]['repeats'], baseline=baseline, rows=rows,
                  incomplete_cells=incomplete,
                  source_reports=[dict(name=p.parent.name, sha256=digest(p), harness_sha256=r['harness_sha256'])
                                  for p, r in zip(args.reports, reports)],
                  conclusion_scope='single_seed_screening' if reports[0]['repeats'] == 1 else 'repeated_observed_cells',
                  summary=aggregate(rows, baseline, reports[0]['repeats']))
    write(args.output, result)
    print(f'Portable comparison: {args.output}')


if __name__ == '__main__':
    main()
