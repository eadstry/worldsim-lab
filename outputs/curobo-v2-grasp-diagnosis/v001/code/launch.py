# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Launch one isolated experiment, record GPU occupancy and enforce a bounded runtime."""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path


def gpu_processes() -> list[dict]:
    result = subprocess.run(['nvidia-smi', '--query-compute-apps=pid,used_memory', '--format=csv,noheader,nounits'],
                            capture_output=True, text=True, check=True, timeout=15)
    rows = {}
    for line in result.stdout.splitlines():
        pid, memory = line.split(',')
        rows[int(pid)] = dict(pid=int(pid), memory_mib=float(memory))
    return list(rows.values())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=['v1', 'v2'], required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--attempts', type=int, default=5)
    parser.add_argument('--seed', type=int, default=101)
    parser.add_argument('--timeout', type=float, default=1200)
    parser.add_argument('--smoke', action='store_true', help='Allow foreign GPU load; never use this run for performance comparison')
    parser.add_argument('--probe-model', action='store_true', help='Run only the v2 GPU/URDF model preflight')
    parser.add_argument('--diagnostics', action='store_true', help='Record control targets; exclude this run from performance comparisons')
    args = parser.parse_args()
    assert args.name and Path(args.name).name == args.name
    assert args.attempts > 0 and args.timeout > 0
    assert not args.probe_model or args.backend == 'v2'
    root = Path(__file__).resolve().parent
    cfg = json.loads((root / '.local/machine.json').read_text())
    foreign = gpu_processes()
    assert args.smoke or not foreign, f'GPU busy; comparison refused: {foreign}'
    directory = root / '.local/runs' / args.name
    directory.mkdir(parents=True, exist_ok=False)
    python = Path(cfg[args.backend + '_python'])
    env_root = python.parent.parent
    cache = root / '.local/cache' / args.backend
    cache.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    cuda = env_root / 'lib/python3.12/site-packages/nvidia/cu13'
    env.update(PYTHONDONTWRITEBYTECODE='1', OMNI_KIT_ACCEPT_EULA='YES',
               XDG_CACHE_HOME=str(cache), CUDA_CACHE_PATH=str(cache / 'cuda'),
               TORCH_EXTENSIONS_DIR=str(cache / 'torch'), WARP_CACHE_PATH=str(cache / 'warp'),
               CUROBO_CACHE_DIR=str(cache / 'curobo'), CUDA_HOME=str(cuda),
               LD_LIBRARY_PATH=str(cuda / 'lib') + ':' + str(env_root / 'lib') + ':' + env.get('LD_LIBRARY_PATH', ''),
               PATH=str(python.parent) + ':' + str(cuda / 'bin') + ':' + env['PATH'])
    command = [str(python), '-u', str(root / 'run.py'), '--backend', args.backend,
               '--output', str(directory / 'episodes.hdf5'), '--attempts', str(args.attempts), '--seed', str(args.seed)]
    if args.diagnostics:
        command.append('--diagnostics')
    if args.probe_model:
        command = [str(python), '-u', str(root / 'probe_model.py'), '--cuda']
    record = dict(backend=args.backend, smoke=args.smoke, command=command, foreign_gpu_processes_before=foreign,
                  run_kind='model_probe' if args.probe_model else 'skillgen',
                  diagnostics=args.diagnostics,
                  v2_commit=cfg['v2_commit'], started_unix=time.time(), samples=[], status='running')
    path = directory / 'launch.json'
    path.write_text(json.dumps(record, indent=2) + '\n')
    with (directory / 'console.log').open('x') as log:
        child = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True)
        record['pid'] = child.pid
        try:
            while child.poll() is None:
                sample = dict(time_unix=time.time(), processes=gpu_processes())
                record['samples'].append(sample)
                path.write_text(json.dumps(record, indent=2) + '\n')
                if sample['time_unix'] - record['started_unix'] > args.timeout:
                    record['status'] = 'timeout'
                    os.killpg(child.pid, signal.SIGTERM)
                    try:
                        child.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                    break
                time.sleep(2)
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                child.wait(timeout=30)
    record.update(returncode=child.wait(), ended_unix=time.time())
    if record['status'] != 'timeout':
        result = root / '.local/model-cuda.json' if args.probe_model else directory / 'episodes.result.json'
        fresh_result = result.is_file() and result.stat().st_mtime >= record['started_unix']
        record['status'] = 'completed' if record['returncode'] == 0 and fresh_result else 'failed'
    path.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({key: record[key] for key in ['backend', 'status', 'returncode', 'pid']}), flush=True)
    raise SystemExit(0 if record['status'] == 'completed' else 1)


if __name__ == '__main__':
    main()
