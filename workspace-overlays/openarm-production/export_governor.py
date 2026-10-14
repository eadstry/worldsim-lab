# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Read-only Linux resource admission for CPU export workers; no GPU imports."""
from __future__ import annotations

import math
import os
import shutil
import time
from pathlib import Path

MIB = 1024**2
GIB = 1024**3


def parse_workers(value):
    if value == 'auto':
        return value
    count = int(value)
    if count < 0:
        raise ValueError('Export workers must be auto or a nonnegative integer')
    return count


def read(path):
    try:
        return path.read_text().strip()
    except OSError:
        return ''


def fields(path):
    return dict(line.split(maxsplit=1) for line in read(path).splitlines() if ' ' in line)


def cgroup_directories():
    """Inspect the current cgroup and every ancestor visible in its v2 mount."""
    entry = next((line.split(':', 2)[2] for line in read(Path('/proc/self/cgroup')).splitlines()
                  if line.startswith('0::')), None)
    if entry is None:
        raise RuntimeError('Resource auto mode requires visible cgroup v2 limits')
    for line in read(Path('/proc/self/mountinfo')).splitlines():
        parts = line.split()
        if ' - cgroup2 ' not in line:
            continue
        mount = Path(parts[4].replace('\\040', ' '))
        root = Path(parts[3].replace('\\040', ' '))
        try:
            relative = Path(entry).relative_to(root)
        except ValueError:
            continue
        base = mount / relative
        # A cgroup namespace can hide the host-relative membership path.
        if not base.is_dir():
            base = mount
        if '..' in relative.parts:
            raise RuntimeError('Cannot resolve cgroup membership safely')
        return [base, *[p for p in base.parents if p == mount or mount in p.parents]]
    raise RuntimeError('Cannot locate the cgroup v2 mount')


def pressure(path):
    some = next((line for line in read(path).splitlines() if line.startswith('some ')), '')
    return float(dict(part.split('=') for part in some.split()[1:]).get('avg10', 0))


class ResourceGovernor:
    """Admit at most one new worker per second, preserving simulation headroom."""
    def __init__(self):
        self.previous = None
        self.last_checked = -math.inf
        self.private_peak = 256 * MIB

    def sample(self, processes, output):
        now = time.monotonic()
        affinity = os.sched_getaffinity(0)
        cpu_capacity = float(len(affinity))
        cpu_rows = {}
        for line in read(Path('/proc/stat')).splitlines():
            parts = line.split()
            if parts[0].startswith('cpu') and parts[0][3:].isdigit() and int(parts[0][3:]) in affinity:
                values = list(map(int, parts[1:9]))
                cpu_rows[parts[0]] = (sum(values), values[3] + values[4])
        if not cpu_rows:
            raise RuntimeError('Cannot sample CPUs available to this process')
        memory = fields(Path('/proc/meminfo'))
        capacity = int(memory['MemTotal:'].split()[0]) * 1024
        available = int(memory['MemAvailable:'].split()[0]) * 1024
        groups = cgroup_directories()
        quotas, usage, task_headroom = {}, {}, math.inf
        io_pressure = pressure(Path('/proc/pressure/io'))
        for group in groups:
            quota = read(group / 'cpu.max').split()
            if quota and quota[0] != 'max':
                quotas[str(group)] = int(quota[0]) / int(quota[1])
                cpu_capacity = min(cpu_capacity, quotas[str(group)])
                usage[str(group)] = int(fields(group / 'cpu.stat')['usage_usec']) / 1e6
            for name in ('memory.max', 'memory.high'):
                limit = read(group / name)
                if limit and limit != 'max':
                    capacity = min(capacity, int(limit))
                    available = min(available, int(limit) - int(read(group / 'memory.current')))
            limit = read(group / 'pids.max')
            if limit and limit != 'max':
                task_headroom = min(task_headroom, int(limit) - int(read(group / 'pids.current')))
            io_pressure = max(io_pressure, pressure(group / 'io.pressure'))
        cpu_sample_ready = self.previous is not None
        free_cores = cpu_capacity
        if self.previous is not None:
            previous_time, previous_cpus, previous_usage = self.previous
            elapsed = max(now - previous_time, .001)
            busy = 0.0
            for name, (total, idle) in cpu_rows.items():
                if name in previous_cpus:
                    old_total, old_idle = previous_cpus[name]
                    busy += max(0, 1 - (idle - old_idle) / max(total - old_total, 1))
            free_cores = min(free_cores, len(affinity) - busy)
            for name, value in usage.items():
                if name in previous_usage:
                    free_cores = min(free_cores, quotas[name] - (value - previous_usage[name]) / elapsed)
        self.previous = now, cpu_rows, usage
        worker_tasks = 32
        for process in processes:
            values = fields(Path(f'/proc/{process.pid}/smaps_rollup'))
            private = sum(int(values.get(key, '0 kB').split()[0]) * 1024
                          for key in ('Private_Clean:', 'Private_Dirty:', 'Private_Hugetlb:'))
            # Shared episode mappings are already counted in system/cgroup use.
            self.private_peak = max(self.private_peak, int(private * 1.25))
            status = fields(Path(f'/proc/{process.pid}/status'))
            worker_tasks = max(worker_tasks, int(status.get('Threads:', 0)))
        disk = shutil.disk_usage(output.parent)
        return dict(cpu_sample_ready=cpu_sample_ready, cpu_capacity=cpu_capacity, free_cpu_cores=max(free_cores, 0),
                    cpu_reserve_cores=min(2.0, cpu_capacity * .25),
                    memory_available_bytes=max(available, 0), memory_capacity_bytes=capacity,
                    memory_reserve_bytes=max(256 * MIB, int(capacity * .15)),
                    worker_private_bytes=self.private_peak,
                    task_headroom=None if math.isinf(task_headroom) else task_headroom,
                    worker_task_slots=worker_tasks + 16,
                    shared_memory_free_bytes=shutil.disk_usage('/dev/shm').free,
                    io_pressure_percent=io_pressure, disk_free_bytes=disk.free)

    @staticmethod
    def evaluate(sample, worker_count, episode_bytes):
        if not sample['cpu_sample_ready']:
            return 'cpu_sampling'
        cpu_budget = sample['cpu_capacity'] - sample['cpu_reserve_cores']
        cpu_limit = max(1, math.floor(cpu_budget))
        if worker_count >= cpu_limit:
            return 'cpu_capacity'
        if sample['free_cpu_cores'] < sample['cpu_reserve_cores'] + min(1.0, cpu_budget):
            return 'cpu_busy'
        if sample['memory_available_bytes'] < sample['memory_reserve_bytes'] + sample['worker_private_bytes']:
            return 'memory_reserve'
        if sample['task_headroom'] is not None and sample['task_headroom'] < sample['worker_task_slots']:
            return 'process_slots'
        if sample['shared_memory_free_bytes'] < 8 * MIB:
            return 'shared_memory'
        if sample['disk_free_bytes'] < episode_bytes + GIB:
            return 'disk_space'
        if sample['io_pressure_percent'] >= 20:
            return 'io_pressure'
        return 'available'

    def decide(self, processes, pending, output):
        now = time.monotonic()
        if now - self.last_checked < 1:
            return None
        self.last_checked = now
        try:
            sample = self.sample(processes, output)
            reason = self.evaluate(sample, len(processes), max(j['memory_bytes'] for j in pending.values()))
            return dict(allow=reason == 'available', reason=reason, resources=sample)
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            return dict(allow=False, reason='resources_unavailable', error=str(exc))
