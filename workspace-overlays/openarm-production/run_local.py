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


def main():
    script = Path(__file__).resolve().with_name('generate.py')
    if '--help' in sys.argv or '-h' in sys.argv:
        return subprocess.call([sys.executable, '-u', str(script), *sys.argv[1:]])
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--output_file', type=Path, required=True)
    parser.add_argument('--input_file', type=Path, required=True)
    parser.add_argument('--num_envs', type=int, default=1)
    parser.add_argument('--generation_num_trials', type=int, default=1)
    parser.add_argument('--arm', default='right')
    parser.add_argument('--final-hold-steps', type=int, default=0)
    parser.add_argument('--log-interval', type=float, default=10)
    args, _ = parser.parse_known_args()
    assert args.log_interval > 0
    output = args.output_file.resolve()
    assert output != args.input_file.resolve(), 'Input and output must differ'
    assert args.input_file.is_file(), f'Missing input: {args.input_file}'
    suffixes = ('.console.log', '.run.json', '.resources.jsonl', '.status.json', '.telemetry.jsonl',
                '.telemetry-summary.json', '.result.json', '.error.txt')
    assert not output.exists(), f'Output already exists: {output}'
    for suffix in suffixes:
        assert not output.with_suffix(suffix).exists(), f'Existing run artifact: {output.with_suffix(suffix)}; use a new output name'
    output.parent.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex
    command = [sys.executable, '-u', str(script), *sys.argv[1:]]
    config = vars(args).copy()
    config = {k: str(v.resolve()) if isinstance(v, Path) else v for k, v in config.items()}
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
    report = output.with_suffix('.result.json')
    completion_error = None
    stats = None
    if returncode == 0:
        try:
            stats = json.loads(report.read_text())
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
