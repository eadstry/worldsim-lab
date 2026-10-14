# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Parent-side Linux process, cgroup and GPU sampling; no Python dependencies."""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from monitor import utc_now


def key_values(path):
    try:
        values = {}
        for line in path.read_text().splitlines():
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                values[parts[0]] = parts[1]
        return values
    except OSError:
        return {}


def cgroup_sample(pid):
    result = {}
    try:
        # Unified cgroup v2; do not substitute the supervisor's cgroup for the child.
        entry = next(line.split(':', 2)[2] for line in Path(f'/proc/{pid}/cgroup').read_text().splitlines()
                     if line.startswith('0::'))
        base = Path('/sys/fs/cgroup') / entry.lstrip('/')
        for name in ('memory.current', 'memory.max', 'memory.peak', 'memory.swap.current', 'memory.swap.max'):
            try:
                raw = (base / name).read_text().strip()
                result[name] = raw if raw == 'max' else int(raw)
            except (OSError, ValueError):
                pass
        for name in ('memory.events', 'cpu.stat'):
            result[name] = {key: int(value) for key, value in key_values(base / name).items()}
        result['path'] = str(base)
    except (OSError, StopIteration):
        pass
    return result


class ResourceSampler:
    def __init__(self, pid):
        self.pid = pid
        self.previous = None
        self.previous_cpu = None
        self.gpu_command = shutil.which('nvidia-smi')
        self.cgroup = cgroup_sample(pid)
        self.initial_memory_events = self.cgroup.get('memory.events', {}).copy()

    def sample(self):
        now = time.monotonic()
        result = {'time_utc': utc_now(), 'event': 'resource_sample', 'pid': self.pid}
        proc = Path(f'/proc/{self.pid}')
        try:
            fields = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
            cpu_seconds = (int(fields[11]) + int(fields[12])) / os.sysconf('SC_CLK_TCK')
            status = key_values(proc / 'status')
            def memory_bytes(key):
                return int(status[key].split()[0]) * 1024 if key in status else None

            result.update(process_cpu_seconds=cpu_seconds, process_state=fields[0],
                          process_start_ticks=int(fields[19]),
                          process_rss_bytes=memory_bytes('VmRSS:'),
                          process_swap_bytes=memory_bytes('VmSwap:'),
                          process_peak_rss_bytes=memory_bytes('VmHWM:'),
                          process_threads=int(status['Threads:']) if 'Threads:' in status else None,
                          io={k.rstrip(':'): int(v) for k, v in key_values(proc / 'io').items()})
            if self.previous is not None:
                delta = max(now - self.previous['monotonic'], .001)
                result['process_cpu_percent'] = (cpu_seconds - self.previous['cpu_seconds']) * 100 / delta
                if result['process_rss_bytes'] is not None and self.previous['rss'] is not None:
                    result['rss_growth_bytes_per_second'] = (result['process_rss_bytes'] - self.previous['rss']) / delta
                result['process_write_bytes_per_second'] = (result['io'].get('write_bytes', 0) -
                                                            self.previous['writes']) / delta
            self.previous = {'monotonic': now, 'cpu_seconds': cpu_seconds,
                             'rss': result['process_rss_bytes'], 'writes': result['io'].get('write_bytes', 0)}
        except (OSError, ValueError, IndexError) as exc:
            result['process_sample_error'] = f'{type(exc).__name__}: {exc}'
        try:
            mem = key_values(Path('/proc/meminfo'))
            result.update(system_memory_total_bytes=int(mem['MemTotal:'].split()[0]) * 1024,
                          system_memory_available_bytes=int(mem['MemAvailable:'].split()[0]) * 1024,
                          system_swap_total_bytes=int(mem['SwapTotal:'].split()[0]) * 1024,
                          system_swap_free_bytes=int(mem['SwapFree:'].split()[0]) * 1024)
            cpu = [int(x) for x in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
            idle, total = cpu[3] + cpu[4], sum(cpu)
            if self.previous_cpu:
                result['system_cpu_percent'] = 100 * (1 - (idle - self.previous_cpu[0]) /
                                                      max(total - self.previous_cpu[1], 1))
            self.previous_cpu = (idle, total)
        except (OSError, ValueError, KeyError):
            pass
        current = cgroup_sample(self.pid)
        if current:
            self.cgroup = current
        # Retain the cgroup path after /proc/<pid> disappears, to capture an OOM counter change.
        if self.cgroup.get('path'):
            events = key_values(Path(self.cgroup['path']) / 'memory.events')
            if events:
                self.cgroup['memory.events'] = {k: int(v) for k, v in events.items()}
        result['cgroup'] = dict(self.cgroup)
        result['cgroup_memory_event_deltas'] = {
            k: value - self.initial_memory_events.get(k, value)
            for k, value in self.cgroup.get('memory.events', {}).items()}
        if self.gpu_command:
            try:
                query = subprocess.run([
                    self.gpu_command, '--query-gpu=uuid,name,utilization.gpu,memory.used,memory.total,power.draw',
                    '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=2)
                result['gpu_monitor_available'] = query.returncode == 0
                result['gpus'] = []
                for line in query.stdout.splitlines():
                    parts = [x.strip() for x in line.split(',')]
                    if len(parts) != 6:
                        continue
                    gpu = dict(zip(('uuid', 'name', 'utilization_percent', 'memory_used_mib',
                                    'memory_total_mib', 'power_watts'), parts))
                    for key in ('utilization_percent', 'memory_used_mib', 'memory_total_mib', 'power_watts'):
                        try:
                            gpu[key] = float(gpu[key])
                        except ValueError:
                            gpu[key] = None
                    result['gpus'].append(gpu)
                if query.returncode:
                    result['gpu_monitor_error'] = query.stderr.strip()[:300]
            except (OSError, subprocess.TimeoutExpired) as exc:
                result.update(gpu_monitor_available=False, gpu_monitor_error=str(exc))
        else:
            result.update(gpu_monitor_available=False, gpu_monitor_error='nvidia-smi unavailable')
        return result
