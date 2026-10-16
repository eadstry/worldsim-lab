# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Supervise generation, persist console output and monitor independently of Isaac Sim."""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from monitor import Journal, append_json, atomic_json, compact_status, snapshot, utc_now
from resources import ResourceSampler
from export_governor import parse_workers


def main():
    script = Path(__file__).resolve().with_name('generate.py')
    if '--help' in sys.argv or '-h' in sys.argv:
        return subprocess.call([sys.executable, '-u', str(script), *sys.argv[1:]])
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--output_file', type=Path, required=True)
    parser.add_argument('--input_file', type=Path, required=True)
    parser.add_argument('--runtime', type=Path)
    parser.add_argument('--background-config', type=Path)
    parser.add_argument('--background-seed', type=int, default=101)
    parser.add_argument('--num_envs', type=int, default=1)
    parser.add_argument('--generation_num_trials', type=int, default=1)
    parser.add_argument('--arm', default='right')
    parser.add_argument('--final-hold-steps', type=int, default=0)
    parser.add_argument('--log-interval', type=float, default=10)
    parser.add_argument('--export-workers', '--export-max-workers', type=parse_workers, default=0)
    parser.add_argument('--export-queue-memory-gib', type=float, default=16)
    parser.add_argument('--export-timeout-seconds', type=float, default=600)
    args, _ = parser.parse_known_args()
    assert args.log_interval > 0
    output = args.output_file.resolve()
    assert output != args.input_file.resolve(), 'Input and output must differ'
    assert args.input_file.is_file(), f'Missing input: {args.input_file}'
    suffixes = ('.console.log', '.run.json', '.resources.jsonl', '.status.json', '.telemetry.jsonl',
                '.telemetry-summary.json', '.background.json', '.result.json', '.error.txt', '.export.json', '.export-parts', '.partial.hdf5')
    assert not output.exists(), f'Output already exists: {output}'
    for suffix in suffixes:
        assert not output.with_suffix(suffix).exists(), f'Existing run artifact: {output.with_suffix(suffix)}; use a new output name'
    output.parent.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex
    command = [sys.executable, '-u', str(script), *sys.argv[1:]]
    requested_memory_gib = args.export_queue_memory_gib
    if args.export_workers:
        from export_resources import resolve_export_memory_gib
        args.export_queue_memory_gib = resolve_export_memory_gib(requested_memory_gib)
        command.extend(['--export-queue-memory-gib', str(args.export_queue_memory_gib)])
    config = vars(args).copy()
    config = {k: str(v.resolve()) if isinstance(v, Path) else v for k, v in config.items()}
    config['requested_export_queue_memory_gib'] = requested_memory_gib
    run = {'schema_version': 2, 'run_id': run_id, 'started_at': utc_now(), 'status': 'starting',
           'command': command, 'config': config, 'supervisor_pid': os.getpid(),
           'cwd': str(Path.cwd()), 'hostname': os.uname().nodename,
           'cuda_visible_devices': os.environ.get('CUDA_VISIBLE_DEVICES')}
    run_path = output.with_suffix('.run.json')
    atomic_json(run_path, run)
    env = {**os.environ, 'OPENARM_RUN_ID': run_id, 'OPENARM_RUN_CONFIG': json.dumps(config),
           'OPENARM_LOG_INTERVAL': str(args.log_interval)}
    try:
        child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 env=env, start_new_session=True)
    except BaseException as exc:
        run.update(status='failed', ended_at=utc_now(), launch_error=f'{type(exc).__name__}: {exc}')
        atomic_json(run_path, run)
        raise
    run.update(status='running', child_pid=child.pid)
    atomic_json(run_path, run)
    stop = threading.Event()
    pump_errors = []
    resources = ResourceSampler(child.pid)
    journal = Journal(output.with_suffix('.telemetry.jsonl'))
    resource_journal = Journal(output.with_suffix('.resources.jsonl'))
    previous_output = None
    worker_samplers = {}

    def pump_console():
        try:
            with output.with_suffix('.console.log').open('xb', buffering=0) as log:
                while True:
                    chunk = os.read(child.stdout.fileno(), 65536)
                    if not chunk:
                        return
                    log.write(chunk)
                    try:
                        sys.stdout.buffer.write(chunk)
                        sys.stdout.buffer.flush()
                    except (BrokenPipeError, OSError):
                        pass
        except Exception as exc:
            pump_errors.append(str(exc))

    def sample_once():
        nonlocal previous_output
        sample = resources.sample()
        sample.update(run_id=run_id, output_bytes=output.stat().st_size if output.exists() else 0)
        for row in journal.refresh():
            pids = (row['worker_pids'] if row['event'] == 'export_pool_started' else
                    [row['worker_pid']] if row['event'] == 'export_worker_started' else [])
            for pid in pids:
                if pid not in worker_samplers:
                    worker_samplers[pid] = ResourceSampler(pid)
                    worker_samplers[pid].gpu_command = None
        sample['export_workers'] = [sampler.sample() for sampler in worker_samplers.values()]
        sample['shared_memory_used_bytes'] = (__import__('shutil').disk_usage('/dev/shm').used)
        # Worker RSS includes shared pages; use cgroup/available RAM for physical totals.
        sample['process_tree_rss_bytes_including_shared_duplicates'] = sum(
            row.get('process_rss_bytes') or 0 for row in [sample, *sample['export_workers']])
        now = time.monotonic()
        if previous_output is not None:
            sample['output_growth_bytes_per_second'] = ((sample['output_bytes'] - previous_output[1]) /
                                                       max(now - previous_output[0], .001))
        previous_output = (now, sample['output_bytes'])
        append_json(output.with_suffix('.resources.jsonl'), sample)
        value = snapshot(output, journal, resource_journal)
        atomic_json(output.with_suffix('.status.json'), value)
        return value

    def monitor_loop():
        while not stop.is_set():
            try:
                value = sample_once()
                print('[OpenArm monitor] ' + compact_status(value), flush=True)
            except Exception as exc:
                append_json(output.with_suffix('.resources.jsonl'),
                            {'event': 'monitor_error', 'time_utc': utc_now(), 'error': str(exc)})
            stop.wait(args.log_interval)

    pump = threading.Thread(target=pump_console, daemon=True, name='openarm-console')
    monitor = threading.Thread(target=monitor_loop, daemon=True, name='openarm-parent-monitor')
    pump.start()
    monitor.start()
    received_signals = []

    def forward_signal(signum, frame):
        received_signals.append(signum)
        try:
            os.killpg(child.pid, signum)
        except ProcessLookupError:
            pass

    old_handlers = {sig: signal.signal(sig, forward_signal) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        returncode = child.wait()
    finally:
        stop.set()
        monitor.join(timeout=6)
        pump.join(timeout=3)
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
    if returncode != 0:
        # The simulator may be SIGKILLed before its own finally/atexit handlers.
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        export_path = output.with_suffix('.export.json')
        if export_path.exists():
            state = json.loads(export_path.read_text())
            if state.get('status') != 'complete':
                state.update(status='failed', child_returncode=returncode)
                state.setdefault('error', 'Generation process exited before export completion')
                atomic_json(export_path, state)
    report = output.with_suffix('.result.json')
    completion_error = None
    stats = None
    if returncode == 0:
        try:
            error_path = output.with_suffix('.error.txt')
            if error_path.is_file():
                raise ValueError('Generation failed: ' + error_path.read_text().strip())
            stats = json.loads(report.read_text())
            if args.background_config is not None:
                background = json.loads(output.with_suffix('.background.json').read_text())
                assert background.get('dataset_annotated') is True, 'HDR dataset provenance is incomplete'
            if args.export_workers:
                export = json.loads(output.with_suffix('.export.json').read_text())
                assert export['status'] == 'complete' and output.is_file(), 'Async export is incomplete'
                assert sum(e['attributes'].get('success') is True for e in export['entries']) == stats['num_success'], 'Saved/generated success count mismatch'
            assert stats['num_success'] > 0, 'No successful demonstrations'
            assert stats.get('requested_trials') == args.generation_num_trials, 'Completion target mismatch'
            policy = next((r for r in reversed(journal.refresh()) if r['event'] == 'generation_policy'), {})
            completed = stats['num_success'] if policy.get('guarantee_success', True) else stats['num_attempts']
            assert completed >= args.generation_num_trials, 'Generation target was not reached'
        except (OSError, ValueError, KeyError, AssertionError) as exc:
            completion_error = str(exc)
    status = ('interrupted' if received_signals else
              'succeeded' if returncode == 0 and completion_error is None else 'failed')
    run.update(status=status, ended_at=utc_now(), returncode=returncode,
               exit_signal=signal.Signals(-returncode).name if returncode < 0 else None,
               received_signals=received_signals, completion_error=completion_error,
               result=stats, console_capture_errors=pump_errors)
    atomic_json(run_path, run)
    value = sample_once()
    print('[OpenArm monitor] ' + compact_status(value), flush=True)
    if completion_error:
        print(f'Generation completion check failed: {completion_error}', file=sys.stderr, flush=True)
    return (128 - returncode if returncode < 0 else returncode) or (0 if status == 'succeeded' else 1)


if __name__ == '__main__':
    raise SystemExit(main())
