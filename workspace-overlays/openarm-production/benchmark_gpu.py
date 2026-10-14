# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Sequential 8-env GPU comparison; no dependency changes or concurrent runs."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--trials', type=int, default=24)
    parser.add_argument('--existing-baseline', type=Path)
    args = parser.parse_args()
    assert args.trials >= 24
    args.directory.mkdir(parents=True, exist_ok=False)
    overlay = Path(__file__).resolve().parent
    task = overlay / 'runtime/openarm_autodata/tasks/pick_place/autodata_configs/tasks/openarm_bimanual_left_pick_place.yaml'
    report = dict(source=str(args.input.resolve()), source_sha256=hashlib.sha256(args.input.read_bytes()).hexdigest(),
                  task_sha256=hashlib.sha256(task.read_bytes()).hexdigest(), num_envs=8,
                  trials=args.trials, runs=[])
    for workers in (0, 1, 2):
        output = (args.existing_baseline.resolve() if workers == 0 and args.existing_baseline
                  else args.directory.resolve() / f'workers-{workers}.hdf5')
        command = ['bash', str(overlay / 'run-local.sh'), '--arm', 'left', '--final-hold-steps', '60',
                   '--input_file', str(args.input.resolve()), '--output_file', str(output),
                   '--num_envs', '8', '--generation_num_trials', str(args.trials),
                   '--export-workers', str(workers), '--export-queue-memory-gib', '16', '--log-interval', '10']
        if workers == 0 and args.existing_baseline:
            from datetime import datetime
            existing = json.loads(output.with_suffix('.run.json').read_text())
            config = existing['config']
            assert existing['status'] == 'succeeded'
            assert config['num_envs'] == 8 and config['generation_num_trials'] == args.trials
            assert config['export_workers'] == 0 and config['final_hold_steps'] == 60
            assert Path(config['input_file']).resolve() == args.input.resolve() and config['arm'] == 'left'
            elapsed = (datetime.fromisoformat(existing['ended_at']) - datetime.fromisoformat(existing['started_at'])).total_seconds()
            print('Using completed synchronous baseline', flush=True)
        else:
            print(f'Starting GPU comparison workers={workers}', flush=True)
            start = time.monotonic()
            with output.with_suffix('.launcher.log').open('x') as log:
                completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
            elapsed = time.monotonic() - start
            if completed.returncode:
                raise RuntimeError(f'GPU run failed, workers={workers}; see {output.with_suffix(".launcher.log")}')
        rows = [json.loads(line) for line in output.with_suffix('.telemetry.jsonl').read_text().splitlines()]
        first = next(r for r in rows if r['event'] == 'episode_started')
        finished = [r for r in rows if r['event'] == 'episode_finished']
        ready = next(r for r in reversed(rows) if r['event'] == 'output_ready')
        status = json.loads(output.with_suffix('.status.json').read_text())
        production = finished[-1]['elapsed_seconds'] - first['elapsed_seconds']
        final_ready = ready['elapsed_seconds'] - first['elapsed_seconds']
        successes = sum(r['success'] is True for r in finished)
        assert successes >= args.trials
        with output.with_suffix('.validation.log').open('w') as log:
            physical = subprocess.run([sys.executable, str(overlay / 'validate_output.py'), str(output)],
                                      stdout=log, stderr=subprocess.STDOUT)
        physical_report = json.loads(output.with_suffix('.validation.json').read_text())
        assert physical.returncode in (0, 1), 'Physical validator crashed'
        assert physical.returncode == 0 or physical_report.get('passed') is False
        validator = overlay.parents[1] / 'AutoData/scripts/validate_dataset.py'
        with output.with_suffix('.schema.log').open('w') as log:
            subprocess.run([sys.executable, str(validator), str(output)], stdout=log, check=True)
        run = dict(workers=workers, successes=successes, production_seconds=production,
                   final_ready_seconds=final_ready, launcher_wall_seconds=elapsed,
                   production_per_minute=successes * 60 / production,
                   final_ready_per_minute=successes * 60 / final_ready,
                   launcher_per_minute=successes * 60 / elapsed,
                   async_export=status.get('async_export'), resource_summary=status['resource_summary'],
                   format_validation_passed=True, physical_validation_passed=physical_report['passed'],
                   terminal_successes=sum(e['final_state_success'] for e in physical_report['episodes']),
                   output=str(output))
        report['runs'].append(run)
        (args.directory / 'report.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(run), flush=True)
    baseline = report['runs'][0]['final_ready_per_minute']
    for run in report['runs']:
        run['final_ready_speedup'] = run['final_ready_per_minute'] / baseline
    report['passed'] = all(r['format_validation_passed'] and r['physical_validation_passed'] for r in report['runs'])
    (args.directory / 'report.json').write_text(json.dumps(report, indent=2))
    if not report['passed']:
        raise SystemExit('Comparison completed; physical validation failures retained in report (not a green acceptance)')


if __name__ == '__main__':
    main()
