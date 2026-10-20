# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Read-only admission probe. Never launches a simulator or changes resources."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess

GIB = 1024**3


def required_gib(protocol):
    if protocol['schema_version'] != 1 or protocol['num_envs'] != 24:
        raise ValueError('This protocol requires exactly 24 environments')
    cfg, admission = protocol['configuration'], protocol['admission']
    if (len(cfg['cameras']) != 3 or len(set(cfg['cameras'])) != 3
            or cfg['image_shape'] != [480, 640, 3] or cfg['image_dtype'] != 'uint8'
            or cfg['control_hz'] != 30 or cfg['final_hold_steps'] != 60
            or cfg['compression'] != 'gzip level 2' or cfg['export_workers'] != 'auto'
            or cfg['guarantee_success'] is not False or cfg['keep_failed'] is not True
            or cfg['retry_failed_attempts'] is not False
            or cfg['allow_parallelism_fallback'] is not False
            or cfg['allow_observation_reduction'] is not False):
        raise ValueError('Full production observation/workload contract changed')
    values = [admission[k] for k in ('base_gib', 'recorder_gib_per_env', 'reserve_gib')]
    values.append(cfg['export_queue_gib'])
    if any(isinstance(v, bool) or not isinstance(v, (int, float))
           or not math.isfinite(v) or v <= 0 for v in values):
        raise ValueError('Admission estimates must be positive finite numbers')
    return values[0] + 24 * values[1] + values[2] + values[3]


def memory_snapshot(proc=Path('/proc'), cgroup_root=Path('/sys/fs/cgroup')):
    fields = {}
    for line in (proc / 'meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        fields[key] = int(value.split()[0]) * 1024
    available = fields['MemAvailable']
    limits, errors = [], []
    entries = (proc / 'self/cgroup').read_text().splitlines()
    entry = next((line.split(':', 2)[2] for line in entries if line.startswith('0::')), None)
    if entry is None:
        errors.append('Unified cgroup v2 path unavailable; effective memory not established')
    else:
        relative = Path(entry.lstrip('/'))
        if '..' in relative.parts:
            errors.append('Cgroup path escapes visible root; effective memory not established')
        else:
            current = cgroup_root / relative
            # Check ancestors too: a child may say max while its parent is capped.
            while True:
                try:
                    raw = (current / 'memory.max').read_text().strip()
                    if raw != 'max':
                        cap = int(raw)
                        used = int((current / 'memory.current').read_text())
                        headroom = max(0, cap - used)
                        available = min(available, headroom)
                        limits.append({'path': str(current), 'limit_gib': cap / GIB,
                                       'headroom_gib': headroom / GIB})
                except (OSError, ValueError) as exc:
                    errors.append(f'{current}: {type(exc).__name__}')
                if current == cgroup_root:
                    break
                current = current.parent
    return {'host_total_gib': fields['MemTotal'] / GIB,
            'host_available_gib': fields['MemAvailable'] / GIB,
            'effective_available_gib': available / GIB,
            'cgroup_limits': limits, 'probe_errors': errors}


def gpu_snapshot():
    def query(option):
        result = subprocess.run(['nvidia-smi', option, '--format=csv,noheader,nounits'],
                                capture_output=True, text=True, timeout=10)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return result.stdout.strip()
    devices = query('--query-gpu=uuid,name,memory.total,memory.used')
    processes = query('--query-compute-apps=pid')
    return {'devices': devices, 'compute_pids': processes.splitlines() if processes else []}


def assess(protocol, memory, gpu):
    required = required_gib(protocol)
    blockers = []
    if memory['probe_errors']:
        blockers.append('Effective memory probe incomplete')
    available = memory['effective_available_gib']
    if not math.isfinite(available) or available < required:
        blockers.append(f'Conservative admission requires {required:g} GiB available; observed {available:.2f} GiB')
    if gpu.get('error') or not gpu.get('devices'):
        blockers.append('GPU unavailable or probe failed')
    if gpu.get('compute_pids'):
        blockers.append('Other GPU compute processes present; wait for shared queue')
    return {'status': 'blocked' if blockers else 'resource_admissible',
            'required_available_gib': required, 'blockers': blockers,
            'memory': memory, 'gpu': gpu, 'num_envs': 24,
            'simulation_executed': False,
            'scope': 'Resource admission only; capacity, runtime dependencies and data quality are not validated'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', type=Path, default=Path(__file__).with_name('protocol.json'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    # Refuse reuse before probing; never overwrite a previous admission receipt.
    args.output.mkdir(parents=True, exist_ok=False)
    raw = args.protocol.read_bytes()
    protocol = json.loads(raw)
    required_gib(protocol)
    memory = memory_snapshot()
    try:
        gpu = gpu_snapshot()
    except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
        gpu = {'error': str(exc)}
    report = assess(protocol, memory, gpu)
    report.update(checked_at=datetime.now(timezone.utc).isoformat(),
                  protocol_sha256=hashlib.sha256(raw).hexdigest(),
                  probe_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (args.output / 'preflight.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if report['status'] == 'blocked' else 0


if __name__ == '__main__':
    raise SystemExit(main())
