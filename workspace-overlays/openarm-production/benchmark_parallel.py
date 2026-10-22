# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Queued single-host controlled Ray/process vs environment parallelism experiment."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time


def write_json(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    temp.replace(path)


def stop_tree(pid):
    import psutil
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
    except psutil.NoSuchProcess:
        return
    for process in [parent, *children]:
        try: process.terminate()
        except psutil.NoSuchProcess: pass
    _, alive = psutil.wait_procs([parent, *children], timeout=15)
    for process in alive:
        try: process.kill()
        except psutil.NoSuchProcess: pass
    psutil.wait_procs(alive, timeout=5)


def worker(command, directory, cpus, timeout, stop_file, driver_pid):
    """Keep a bounded foreground child; cooperative stop precedes Ray shutdown."""
    directory = Path(directory)
    os.sched_setaffinity(0, set(cpus))
    started = time.monotonic()
    with (directory / 'launcher.log').open('x') as log:
        child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        write_json(directory / 'worker.json', dict(pid=os.getpid(), child_pid=child.pid, cpus=cpus,
            command=command, started=time.time()))
        try:
            while child.poll() is None:
                # NVML or /proc/meminfo can stall under memory pressure. This
                # check runs in the independent Ray worker, not the sampler.
                sample_path = Path(stop_file).parent / 'gpu.jsonl'
                age = (time.time() - sample_path.stat().st_mtime if sample_path.exists()
                       else time.monotonic() - started)
                if age > 20:
                    write_json(directory / 'watchdog-stop.json', dict(sample_age_seconds=age))
                    Path(stop_file).touch()
                if (Path(stop_file).exists() or time.monotonic() - started > timeout
                        or not Path(f'/proc/{driver_pid}').exists()):
                    raise TimeoutError('Driver stopped or worker time limit reached')
                time.sleep(.2)
            result = dict(returncode=child.returncode, seconds=time.monotonic() - started)
            output = directory / 'episodes'
            for key, suffix in [('run', '.run.json'), ('telemetry', '.telemetry-summary.json')]:
                path = output.with_suffix(suffix)
                if path.exists(): result[key] = json.loads(path.read_text())
            manifest = output.with_suffix('.lerobot') / 'manifest.json'
            if manifest.exists(): result['export'] = json.loads(manifest.read_text())
            write_json(directory / 'worker-result.json', result)
            return result
        finally:
            stop_tree(child.pid)


def gpu_sample():
    import psutil
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=timestamp,uuid,utilization.gpu,utilization.memory,memory.used,power.draw',
            '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=5)
        sample = dict(time=time.time(), returncode=result.returncode, csv=result.stdout.strip())
    except subprocess.TimeoutExpired:
        # A busy driver can delay NVML. Missing telemetry is not zero GPU load
        # and must not abort a valid production run after a single delayed query.
        sample = dict(time=time.time(), returncode=None, csv='', error='nvidia-smi timeout')
    sample.update(available_ram_bytes=psutil.virtual_memory().available,
                  free_disk_bytes=shutil.disk_usage('.').free)
    return sample



def cpu_partitions(cpus, processes):
    """Round-robin physical cores, preserving SMT siblings and balancing P/E cores."""
    groups = {}
    for cpu in cpus:
        topology = Path(f'/sys/devices/system/cpu/cpu{cpu}/topology')
        key = ((topology / 'physical_package_id').read_text().strip(),
               (topology / 'core_id').read_text().strip())
        groups.setdefault(key, []).append(cpu)
    partitions = [[] for _ in range(processes)]
    for index, group in enumerate(groups.values()):
        partitions[index % processes].extend(group)
    if any(len(p) != len(cpus) // processes for p in partitions):
        raise ValueError('CPU topology cannot satisfy equal physical-core allocation')
    return partitions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--implementation', choices=['upstream', 'modified'], required=True)
    parser.add_argument('--processes', type=int, default=1)
    parser.add_argument('--envs', type=int, default=1)
    parser.add_argument('--total-envs', type=int, required=True)
    parser.add_argument('--total-writers', type=int, default=2)
    parser.add_argument('--total-cpus', type=int, default=24)
    parser.add_argument('--total-memory-gib', type=float, default=8)
    parser.add_argument('--min-available-ram-gib', type=float, default=14)
    parser.add_argument('--trials', type=int, default=4)
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--timeout', type=float, default=1200)
    args = parser.parse_args()
    if (not 1 <= args.processes <= 2 or args.envs * args.processes != args.total_envs
            or not 1 <= args.total_envs <= 16 or args.total_writers % args.processes
            or args.trials % args.processes or args.total_cpus % args.processes
            or min(args.total_writers, args.trials, args.total_cpus) <= 0
            or not 0 <= args.seed <= 2**32 - args.processes
            or any(not math.isfinite(v) or v <= 0 for v in
                   (args.total_memory_gib, args.min_available_ram_gib, args.timeout))):
        parser.error('Invalid concurrency budget or indivisible trial/CPU/writer allocation')
    cpus = sorted(os.sched_getaffinity(0))[:args.total_cpus]
    if len(cpus) != args.total_cpus: parser.error('Insufficient available CPUs')
    args.output.mkdir(parents=True, exist_ok=False)
    stop_file = args.output / 'STOP'
    stopped = False
    def stop(signum, frame):
        nonlocal stopped
        stopped = True
        stop_file.touch()
    for sig in (signal.SIGINT, signal.SIGTERM): signal.signal(sig, stop)
    root = Path(__file__).resolve().parent
    config = {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}
    partitions = cpu_partitions(cpus, args.processes)
    config['cpu_partitions'] = partitions
    config['cgroup_events_before'] = Path('/sys/fs/cgroup/memory.events').read_text()
    config['started_unix'] = time.time()
    config['source_sha256'] = hashlib.sha256(args.input.read_bytes()).hexdigest()
    config['overlay_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.glob('*.py'))}
    write_json(args.output / 'config.json', config)
    import ray
    started = time.monotonic()
    ray.init(address='local', num_cpus=args.total_cpus, num_gpus=1, include_dashboard=False,
             object_store_memory=80 * 1024**2)
    remote = ray.remote(num_cpus=args.total_cpus / args.processes, num_gpus=1 / args.processes,
                        max_retries=0)(worker)
    refs, results = [], []
    last_gpu_sample = time.monotonic()
    try:
        for i in range(args.processes):
            directory = args.output / f'process-{i:02d}'
            directory.mkdir()
            command = [sys.executable, '-u', str(root / 'run_local.py'), '--autodata-root', str(args.source_root),
                '--runtime', str(args.runtime), '--arm', 'left', '--input_file', str(args.input),
                '--output_file', str(directory / 'episodes'), '--num_envs', str(args.envs),
                '--generation_num_trials', str(args.trials // args.processes), '--generation-seed', str(args.seed + i),
                '--implementation', args.implementation, '--final-hold-steps', '60', '--max-failures', '2',
                '--export-format', 'lerobot-v3',
                '--export-workers', str(args.total_writers // args.processes),
                '--export-queue-memory-gib', str(args.total_memory_gib / args.processes),
                '--export-timeout-seconds', '300', '--log-interval', '2']
            width = args.total_cpus // args.processes
            refs.append(remote.remote(command, str(directory), partitions[i],
                                      args.timeout, str(stop_file), os.getpid()))
        with (args.output / 'gpu.jsonl').open('x') as samples:
            while refs:
                sample = gpu_sample()
                samples.write(json.dumps(sample) + '\n'); samples.flush()
                gpu_used = max((float(line.split(',')[4]) for line in sample['csv'].splitlines()), default=0)
                if sample['returncode'] == 0 and sample['csv']:
                    last_gpu_sample = time.monotonic()
                elif time.monotonic() - last_gpu_sample > 60:
                    write_json(args.output / 'telemetry-stop.json', sample)
                    stop_file.touch(); stopped = True
                if (sample['available_ram_bytes'] < args.min_available_ram_gib * 1024**3 or sample['free_disk_bytes'] < 4 * 1024**3
                        or gpu_used > 30 * 1024):
                    write_json(args.output / 'resource-stop.json', sample)
                    stop_file.touch(); stopped = True
                ready, _ = ray.wait(refs, timeout=1)
                for ref in ready:
                    refs.remove(ref)
                    try: results.append(ray.get(ref))
                    except Exception as exc: results.append(dict(error=str(exc)))
                    if results[-1].get('returncode') != 0:
                        stop_file.touch(); stopped = True
                if time.monotonic() - started > args.timeout + 30:
                    stop_file.touch(); stopped = True
                if stopped and time.monotonic() - started > args.timeout + 90:
                    raise TimeoutError('Worker cleanup deadline')
        elapsed = time.monotonic() - started
        success = not stopped and all(r.get('returncode') == 0 and r.get('run', {}).get('status') == 'succeeded' for r in results)
        episodes = sum(len(r.get('export', {}).get('entries', [])) for r in results)
        frames = sum(r.get('export', {}).get('frames', 0) for r in results)
        write_json(args.output / 'result.json', dict(status='succeeded' if success else 'failed',
            seconds=elapsed, episodes=episodes, frames=frames, episodes_per_second=episodes/elapsed,
            frames_per_second=frames/elapsed, workers=results,
            cgroup_events_after=Path('/sys/fs/cgroup/memory.events').read_text()))
        return 0 if success else 1
    except BaseException as exc:
        write_json(args.output / 'result.json', dict(status='failed', error=str(exc),
            seconds=time.monotonic() - started, workers=results))
        raise
    finally:
        stop_file.touch()
        # Reap only this experiment's recorded subprocess trees before shutdown.
        for path in args.output.glob('process-*/worker.json'):
            row = json.loads(path.read_text())
            stop_tree(row['child_pid'])
        ray.shutdown()

if __name__ == '__main__':
    raise SystemExit(main())
