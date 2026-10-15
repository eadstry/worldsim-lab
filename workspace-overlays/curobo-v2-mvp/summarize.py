# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Summarize fixed-attempt runs without conflating startup failures with episode outcomes."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * quantile
    low = int(index)
    return ordered[low] + (ordered[min(low + 1, len(ordered) - 1)] - ordered[low]) * (index - low)


def wilson(successes: int, total: int) -> list[float] | None:
    if not total:
        return None
    assert 0 <= successes <= total
    z, p = 1.959963984540054, successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return [max(0, center - half), min(1, center + half)]


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def summarize(directory: Path) -> dict:
    launch = json.loads((directory / 'launch.json').read_text())
    metrics = read_jsonl(directory / 'episodes.metrics.jsonl')
    result_path = directory / 'episodes.result.json'
    result = json.loads(result_path.read_text()) if result_path.exists() else None
    requests = [row for row in metrics if row['event'] == 'request']
    phases = [row for row in metrics if row['event'] == 'phase']
    others = {row['pid'] for sample in launch['samples'] for row in sample['processes'] if row['pid'] != launch['pid']}
    memory = [row['memory_mib'] for sample in launch['samples'] for row in sample['processes'] if row['pid'] == launch['pid']]
    completed = result['num_attempts'] if result else None
    successes = result['num_success'] if result else None
    telemetry = read_jsonl(directory / 'episodes.telemetry.jsonl')
    outcomes = [row for row in telemetry if row['event'] == 'episode_finished' and not row.get('cancelled')]
    assert result is None or completed == len(outcomes), 'Result and episode journal disagree'
    return dict(backend=launch['backend'], status=launch['status'], smoke=launch['smoke'],
                diagnostics=launch.get('diagnostics', False),
                uncontended=not launch['foreign_gpu_processes_before'] and not others,
                foreign_pids_during_run=sorted(others), attempts=completed, successes=successes,
                success_rate=successes / completed if completed else None,
                success_rate_wilson_95=wilson(successes, completed) if completed else None,
                request_count=len(requests), request_successes=sum(row['success'] is True for row in requests),
                request_success_rate=sum(row['success'] is True for row in requests) / len(requests) if requests else None,
                request_warm_success_p50_seconds=percentile([r['elapsed_seconds'] for r in requests[1:] if r['success'] is True], .5),
                request_failure_p50_seconds=percentile([r['elapsed_seconds'] for r in requests if r['success'] is not True], .5),
                first_request_seconds=requests[0]['elapsed_seconds'] if requests else None,
                request_all_p50_seconds=percentile([r['elapsed_seconds'] for r in requests], .5),
                request_all_p95_seconds=percentile([r['elapsed_seconds'] for r in requests], .95),
                request_warm_sample_count=max(0, len(requests) - 1),
                request_warm_p50_seconds=percentile([r['elapsed_seconds'] for r in requests[1:]], .5),
                request_warm_p95_seconds=percentile([r['elapsed_seconds'] for r in requests[1:]], .95),
                phase_all_p50_seconds=percentile([r['elapsed_seconds'] for r in phases], .5),
                process_gpu_peak_mib=max(memory) if memory else None,
                torch_peak_allocated_mib=max((r['peak_allocated_bytes'] for r in requests), default=0) / 2**20 if requests else None,
                torch_peak_reserved_mib=max((r['peak_reserved_bytes'] for r in requests), default=0) / 2**20 if requests else None,
                planner_initialization=next((r for r in metrics if r['event'] == 'planner_initialized'), None),
                runtime=next((r for r in metrics if r['event'] == 'runtime'), None),
                backend_configuration=next((r for r in metrics if r['event'] == 'backend_configuration'), None),
                initial_states=[r for r in metrics if r['event'] == 'episode_reset'][:completed] if completed else [],
                returncode=launch['returncode'], elapsed_seconds=launch['ended_unix'] - launch['started_unix'])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runs', type=Path, nargs='+')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    reports = [summarize(run) for run in args.runs]
    args.output.write_text(json.dumps(dict(schema_version=1, runs=reports), indent=2) + '\n')
    for row in reports:
        print({key: row[key] for key in ['backend', 'status', 'attempts', 'successes', 'request_warm_p50_seconds', 'process_gpu_peak_mib', 'uncontended']})


if __name__ == '__main__':
    main()
