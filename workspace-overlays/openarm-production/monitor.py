# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Read generation journals without opening the live HDF5 file."""
from __future__ import annotations

import argparse
import json
import math
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    temporary = path.with_name(path.name + f'.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def append_json(path, value):
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, default=str) + '\n')
        stream.flush()


def distribution(values):
    if not values:
        return {'count': 0, 'mean': None, 'p50': None, 'p95': None, 'max': None}
    values = sorted(values)
    return {'count': len(values), 'mean': sum(values) / len(values),
            'p50': values[math.ceil(len(values) * .50) - 1],
            'p95': values[math.ceil(len(values) * .95) - 1], 'max': values[-1]}


class Journal:
    """Incrementally read only complete JSONL lines; a writer may be appending."""
    def __init__(self, path):
        self.path = path
        self.offset = 0
        self.events = []
        self.invalid_lines = 0

    def refresh(self):
        if not self.path.exists():
            return self.events
        if self.path.stat().st_size < self.offset:
            self.offset = 0
            self.events = []
        with self.path.open('rb') as stream:
            stream.seek(self.offset)
            while True:
                line = stream.readline()
                if not line or not line.endswith(b'\n'):
                    break
                self.offset = stream.tell()
                try:
                    self.events.append(json.loads(line))
                except (ValueError, UnicodeDecodeError):
                    self.invalid_lines += 1
        return self.events


def summarize(rows, target=None, elapsed=None, window_seconds=60):
    episodes = {}
    finished = []
    requests = []
    iterations = []
    iteration_starts = 0
    for row in rows:
        event = row['event']
        key = row.get('episode_id')
        if event == 'episode_started':
            episodes[key] = row
        elif event == 'execution_progress' and key in episodes:
            episodes[key] = {**episodes[key], **row}
        elif event in ('stage_started', 'stage_finished') and key in episodes:
            episodes[key] = {**episodes[key], 'stage': row['stage'] if event == 'stage_started' else 'execution'}
        elif event == 'heartbeat':
            for active in row.get('active_episodes', []):
                if active.get('episode_id') in episodes:
                    episodes[active['episode_id']] = {**episodes[active['episode_id']], **active}
        elif event in ('episode_finished', 'episode_cancelled'):
            episodes.pop(key, None)
            finished.append(row)
        elif event == 'planner_request_finished' and key is not None:
            requests.append(row)
        elif event == 'solver_iteration_finished' and key is not None:
            iterations.append(row)
        elif event == 'solver_iteration_started' and key is not None:
            iteration_starts += 1
    completed = [r for r in finished if r['event'] == 'episode_finished']
    successes = [r for r in completed if r.get('success') is True]
    failures = [r for r in completed if r.get('success') is False]
    cancelled = sum(r['event'] == 'episode_cancelled' for r in finished)
    elapsed = max(elapsed if elapsed is not None else max((r.get('elapsed_seconds', 0) for r in rows), default=0), .001)
    first_start = min((r.get('elapsed_seconds', 0) for r in rows if r['event'] == 'episode_started'), default=None)
    generation_elapsed = max(elapsed - first_start, .001) if first_start is not None else None
    latest = max((r.get('elapsed_seconds', 0) for r in rows), default=0)
    window = min(window_seconds, generation_elapsed or elapsed)
    recent_successes = sum(r.get('elapsed_seconds', 0) >= elapsed - window for r in successes)
    rate = len(successes) / generation_elapsed if generation_elapsed else 0
    request_successes = sum(r.get('success') is True for r in requests)
    # Version 1 logs expose the actual iteration count only on request-finished records.
    n_iterations = iteration_starts or sum(r.get('curobo_solver_iterations', 0) for r in requests)
    completed_iterations = len(iterations) if iteration_starts else n_iterations
    n_iteration_successes = (sum(r.get('success') is True for r in iterations) if iteration_starts else
                            sum(r.get('curobo_iteration_successes', 0) for r in requests))
    stage_names = ('reset', 'motion_plan', 'execution_wait', 'export')
    policy = next((r for r in reversed(rows) if r['event'] == 'generation_policy'), {})
    target = policy.get('requested_trials', target)
    target_is_successes = policy.get('guarantee_success', True)
    target_done = len(successes) if target_is_successes else len(completed)
    target_rate = target_done / generation_elapsed if generation_elapsed else 0
    exports = [r for r in rows if r['event'] == 'export_breakdown']
    return {
        'schema_version': 2, 'time_utc': utc_now(), 'elapsed_seconds': elapsed,
        'observed_environment_count': len({r['env_id'] for r in rows
                                           if r['event'] == 'episode_started' and 'env_id' in r}),
        'generation_elapsed_seconds': generation_elapsed,
        'telemetry_last_elapsed_seconds': latest,
        'episodes_started': len(completed) + cancelled + len(episodes),
        'episodes_completed': len(completed), 'successes': len(successes), 'failures': len(failures),
        'unknown_outcomes': len(completed) - len(successes) - len(failures),
        'cancelled': cancelled, 'in_flight': len(episodes),
        'episode_success_rate': len(successes) / len(completed) if completed else None,
        'planner_requests': len(requests),
        'planner_request_success_rate': request_successes / len(requests) if requests else None,
        'solver_iterations': n_iterations,
        'solver_iterations_completed': completed_iterations,
        'solver_iterations_in_flight': max(n_iterations - completed_iterations, 0),
        'solver_iteration_success_rate': (n_iteration_successes / completed_iterations
                                          if completed_iterations else None),
        'solver_iterations_per_request': (sum(r.get('curobo_solver_iterations', 0) for r in requests) /
                                           len(requests) if requests else None),
        'solver_iteration_instrumentation_available': next(
            (r.get('solver_iteration_instrumentation') for r in reversed(rows)
             if r['event'] == 'instrumentation_ready'), None),
        'solver_retry_requests': sum(r.get('curobo_solver_iterations', 0) > 1 for r in requests),
        'solver_iterations_per_request_distribution': distribution(
            [r.get('curobo_solver_iterations', 0) for r in requests]),
        'generation_policy': policy,
        'successful_episodes_per_minute': rate * 60,
        'recent_window_seconds': window, 'recent_successes_per_minute': recent_successes * 60 / window,
        'amortized_wall_seconds_per_success': generation_elapsed / len(successes) if successes else None,
        'target_kind': 'successes' if target_is_successes else 'completed_attempts',
        'remaining_target': max(target - target_done, 0) if target is not None else None,
        'eta_seconds': max(target - target_done, 0) / target_rate if target is not None and target_rate else None,
        'episode_duration_seconds': distribution([r['duration_seconds'] for r in completed]),
        'successful_episode_duration_seconds': distribution([r['duration_seconds'] for r in successes]),
        'planner_request_duration_seconds': distribution([r['duration_seconds'] for r in requests]),
        'solver_iteration_duration_seconds': distribution([r['duration_seconds'] for r in iterations]),
        'solver_iterations_per_episode': distribution([r.get('curobo_solver_iterations', 0) for r in completed]),
        'execution_steps_per_wall_second': distribution(
            [r['execution_steps_per_wall_second'] for r in completed if 'execution_steps_per_wall_second' in r]),
        'simulation_seconds_per_wall_second': distribution(
            [r['simulation_seconds_per_wall_second'] for r in completed
             if 'simulation_seconds_per_wall_second' in r]),
        'stage_duration_seconds': {name: distribution([r.get('stages_seconds', {}).get(name, 0)
                                                       for r in completed]) for name in stage_names},
        'export_breakdown': {
            'count': len(exports),
            'phases_seconds': {phase: distribution([r['phases_seconds'][phase] for r in exports])
                               for phase in ('prepare_stack', 'cpu_numpy', 'dataset_create', 'flush')},
            'other_seconds': distribution([r['other_seconds'] for r in exports]),
            'last': exports[-1] if exports else None,
        },
        'active_episodes': list(episodes.values()),
        'last_progress': next((r for r in reversed(rows) if r['event'] in
                              ('episode_finished', 'execution_progress', 'solver_iteration_finished',
                               'planner_request_finished', 'stage_finished')), None),
        'errors': [r for r in rows if r.get('error')][-10:],
        'solver_status_counts': dict(Counter(str(r.get('status')) for r in iterations)),
    }


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        return {}


def snapshot(output, journal=None, resource_journal=None):
    journal = journal or Journal(output.with_suffix('.telemetry.jsonl'))
    resource_journal = resource_journal or Journal(output.with_suffix('.resources.jsonl'))
    run = read_json(output.with_suffix('.run.json'))
    now = datetime.now(timezone.utc)
    started = run.get('started_at')
    ended = run.get('ended_at')
    wall_elapsed = ((datetime.fromisoformat(ended) if ended else now) - datetime.fromisoformat(started)).total_seconds() if started else None
    # Child elapsed starts after simulator startup; use its own clock for production rates.
    rows = journal.refresh()
    child_elapsed = None
    if rows and started:
        child_elapsed = ((datetime.fromisoformat(ended) if ended else now) -
                         datetime.fromisoformat(rows[0]['time_utc'])).total_seconds()
    result = summarize(rows, run.get('config', {}).get('generation_num_trials'), elapsed=child_elapsed)
    resources = resource_journal.refresh()
    # Also support the original child-side resource samples.
    latest_resource = resources[-1] if resources else next(
        (r for r in reversed(journal.events) if r['event'] == 'resource_sample'), None)
    result.update(run=run, total_wall_seconds=wall_elapsed, resource=latest_resource,
                  invalid_journal_lines=journal.invalid_lines,
                  result_report=read_json(output.with_suffix('.result.json')))
    result['total_wall_seconds_per_success'] = (wall_elapsed / result['successes']
                                              if wall_elapsed is not None and result['successes'] else None)
    rss_samples = [r['process_rss_bytes'] for r in resources if r.get('process_rss_bytes') is not None]
    cpu_samples = [r['process_cpu_percent'] for r in resources if 'process_cpu_percent' in r]
    result['resource_summary'] = {'peak_rss_bytes': max(rss_samples) if rss_samples else None,
                                  'process_cpu_percent': distribution(cpu_samples)}
    gpu_peaks = {}
    for resource in resources:
        for gpu in resource.get('gpus', []):
            if gpu.get('memory_used_mib') is not None:
                gpu_peaks[gpu['uuid']] = max(gpu_peaks.get(gpu['uuid'], 0), gpu['memory_used_mib'])
    result['resource_summary']['device_peak_memory_used_mib'] = gpu_peaks
    result['unfinished_on_exit'] = result['in_flight'] if run.get('ended_at') else None
    if latest_resource:
        result['resource_age_seconds'] = (now - datetime.fromisoformat(latest_resource['time_utc'])).total_seconds()
    if journal.events:
        result['telemetry_age_seconds'] = (now - datetime.fromisoformat(journal.events[-1]['time_utc'])).total_seconds()
    result['telemetry_stale'] = (run.get('status') == 'running' and
                                 result.get('telemetry_age_seconds', 0) >
                                 max(30, run.get('config', {}).get('log_interval', 10) * 3))
    if output.exists():
        result['output_bytes'] = output.stat().st_size
    return result


def compact_status(value):
    resource = value.get('resource') or {}
    rss = resource.get('process_rss_bytes')
    memory = f'{rss / 1024**3:.1f} GiB' if rss is not None else '?'
    rate = value['episode_success_rate']
    success = f'{rate:.1%}' if rate is not None else '尚无完成样本'
    status = value.get('run', {}).get('status', '状态未知')
    solver_rate = value['solver_iteration_success_rate']
    solver = f'{solver_rate:.1%}' if solver_rate is not None else '?'
    return (f"{datetime.now().astimezone().strftime('%H:%M:%S')} [{status}] "
            f"成功 {value['successes']} / 完成 {value['episodes_completed']}，成功率 {success}，"
            f"进行中 {value['in_flight']}，速度 {value['successful_episodes_per_minute']:.2f} 条/分，"
            f"求解 {value['solver_iterations']} 次/成功率 {solver}，"
            f"RSS {memory}，遥测距今 {value.get('telemetry_age_seconds', 0):.0f}s")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-file', type=Path, required=True)
    parser.add_argument('--watch', action='store_true')
    parser.add_argument('--interval', type=float, default=10)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    assert args.interval > 0
    output = args.output_file.resolve()
    journal = Journal(output.with_suffix('.telemetry.jsonl'))
    resources = Journal(output.with_suffix('.resources.jsonl'))
    while True:
        value = snapshot(output, journal, resources)
        print(json.dumps(value, ensure_ascii=False, indent=2) if args.json else compact_status(value), flush=True)
        if not args.watch or value['run'].get('status') in ('succeeded', 'failed', 'interrupted'):
            return
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
