#!/usr/bin/env python3
"""Run independent single-environment commands within one shared-queue slot."""
import argparse
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time


def positive(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError('Must be finite and positive')
    return number


def gpu_sample():
    result = subprocess.run([
        'nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total',
        '--format=csv,noheader,nounits', '-i', '0'],
        capture_output=True, text=True, check=True, timeout=10)
    utilization, used, total = map(float, result.stdout.strip().split(','))
    return dict(utilization=utilization, used_mib=used, total_mib=total)


def inherited_queue_locks():
    """Keep the scheduler lock alive if this supervisor crashes before its children."""
    descriptors = []
    for path in Path('/proc/self/fd').iterdir():
        try:
            if Path(os.readlink(path)).name == 'worker.lock':
                descriptors.append(int(path.name))
        except OSError:
            pass
    return tuple(descriptors)


def stop(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def stop_all(processes):
    # The outer queue allows two seconds for cleanup. Signal every group before
    # waiting, so a slow child cannot hide the others from that deadline.
    for process in processes:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + .5
    for process in processes:
        try:
            process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            pass
    for process in processes:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    for process in processes:
        process.wait()


def load_jobs(path):
    jobs = json.loads(path.read_text())['jobs']
    if not jobs:
        raise ValueError('No jobs')
    names = set()
    for job in jobs:
        name = job['name']
        if not name or Path(name).name != name or name in ('.', '..') or name in names:
            raise ValueError('Job names must be unique single path components')
        names.add(name)
        if not Path(job['cwd']).is_absolute() or not Path(job['cwd']).is_dir():
            raise ValueError('Job cwd must be an existing absolute directory')
        if not job['argv'] or not all(isinstance(x, str) for x in job['argv']):
            raise ValueError('Job argv must contain strings')
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in job.get('env', {}).items()):
            raise ValueError('Job environment must contain strings')
    return jobs


def run(args):
    jobs = load_jobs(args.manifest)
    # Manifests may contain private environment snapshots. Never copy them to reports.
    args.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    report = {'started': time.time(), 'requested_workers': args.workers, 'jobs': [], 'samples': []}
    active = []
    lock_fds = inherited_queue_locks()
    pending = list(jobs)
    baseline = gpu_sample() if args.gpu_monitor else None
    capacity = args.workers
    if baseline:
        capacity = min(capacity, int((baseline['total_mib'] - baseline['used_mib'] - args.reserve_mib)
                                    // args.worker_mib))
        if capacity < 1:
            raise ValueError('Insufficient free GPU memory for one worker and reserve')
    report['effective_workers'] = capacity
    report['baseline_gpu'] = baseline
    (args.output / 'started.json').write_text(json.dumps(report, indent=2))
    print(f'Parallel environments: requested={args.workers}, admitted={capacity}', flush=True)

    def interrupted(signum, frame):
        raise SystemExit(128 + signum)

    previous = {s: signal.signal(s, interrupted) for s in (signal.SIGTERM, signal.SIGINT)}
    try:
        while pending or active:
            sample = gpu_sample() if args.gpu_monitor else None
            if sample:
                report['samples'].append(dict(time=time.time(), active=len(active), **sample))
            # Reserve estimated peak memory for newly starting workers. Admission also
            # remains capped by baseline capacity, even before CUDA allocations appear.
            headroom = (max(0, int((sample['total_mib'] - sample['used_mib'] - args.reserve_mib)
                                  // args.worker_mib)) if sample else capacity)
            to_start = min(capacity - len(active), len(pending), headroom)
            for _ in range(to_start):
                job = pending.pop(0)
                env = dict(os.environ) if job.get('inherit_env', True) else {}
                env.update(job.get('env', {}))
                env.update(OMP_NUM_THREADS=str(args.cpu_threads), MKL_NUM_THREADS=str(args.cpu_threads),
                           OPENBLAS_NUM_THREADS=str(args.cpu_threads))
                command = list(job['argv'])
                if args.kit_threads is not None:
                    command.append('--kit_args=--/plugins/carb.tasking.plugin/threadCount='
                                   f'{args.kit_threads} --/plugins/omni.tbb.globalcontrol/maxThreadCount='
                                   f'{args.kit_threads}')
                record = {'name': job['name'], 'source_task_id': job.get('source_task_id'),
                          'started': time.time(), 'status': 'running'}
                report['jobs'].append(record)
                log = (args.output / (job['name'] + '.log')).open('xb')
                try:
                    process = subprocess.Popen(command, cwd=job['cwd'], env=env,
                                               stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                               start_new_session=True, pass_fds=lock_fds)
                except OSError as exc:
                    record.update(status='failed_to_start', finished=time.time(),
                                  error=f'{type(exc).__name__}: {exc}')
                    log.close()
                    print(f"Failed to start {job['name']}", flush=True)
                    continue
                active.append((process, log, record))
                print(f"Started {job['name']}: pid={process.pid}", flush=True)
            if pending and not active and to_start == 0:
                raise RuntimeError('GPU memory admission blocked with no active worker')
            for item in list(active):
                process, log, record = item
                code = process.poll()
                expired = time.time() - record['started'] > args.job_timeout
                if code is not None or expired:
                    stop(process)
                    record.update(finished=time.time(), returncode=process.returncode,
                                  status='timed_out' if expired else ('succeeded' if code == 0 else 'failed'))
                    log.close()
                    active.remove(item)
                    print(f"Finished {record['name']}: {record['status']}", flush=True)
            if pending or active:
                time.sleep(args.interval)
    finally:
        stop_all([process for process, _, _ in active])
        for process, log, record in active:
            log.close()
            record.update(status='interrupted', finished=time.time(), returncode=process.returncode)
        report['not_started'] = [job['name'] for job in pending]
        report['finished'] = time.time()
        (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        for signum, handler in previous.items():
            signal.signal(signum, handler)
    return int(bool(report['not_started']) or any(r['status'] != 'succeeded' for r in report['jobs']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=16)
    parser.add_argument('--gpu-monitor', action='store_true')
    parser.add_argument('--reserve-mib', type=positive, default=4096)
    parser.add_argument('--worker-mib', type=positive, default=6000)
    parser.add_argument('--kit-threads', type=int, help='Append explicit Isaac Lab Kit thread limits')
    parser.add_argument('--cpu-threads', type=int, default=2)
    parser.add_argument('--job-timeout', type=positive, default=600)
    parser.add_argument('--interval', type=positive, default=1)
    args = parser.parse_args()
    if args.workers < 1 or args.cpu_threads < 1 or (args.kit_threads is not None and args.kit_threads < 1):
        parser.error('Workers and CPU threads must be positive')
    os.umask(0o077)
    raise SystemExit(run(args))
