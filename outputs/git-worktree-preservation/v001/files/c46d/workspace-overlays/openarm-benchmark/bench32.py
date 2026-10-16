# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Compare OpenArm production variants, with 32 successful episodes per cell.

The harness is host-safe to import/plan. Execution uses an already configured
production overlay and Python; it never installs dependencies or edits upstream.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import signal
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

GIB = 2**30


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    temp.replace(path)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def journal(path):
    if not Path(path).exists():
        return []
    lines = Path(path).read_text().splitlines()
    rows = []
    for i, line in enumerate(lines):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            if i != len(lines) - 1:
                raise
    return rows


def available_gib():
    values = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    available = int(values['MemAvailable'].split()[0]) * 1024
    # Include a stricter cgroup limit when the process is containerized.
    entry = next((x.split(':', 2)[2] for x in Path('/proc/self/cgroup').read_text().splitlines()
                  if x.startswith('0::')), '/')
    group = Path('/sys/fs/cgroup') / entry.lstrip('/')
    for parent in [group, *group.parents]:
        limit, used = parent / 'memory.max', parent / 'memory.current'
        if limit.is_file() and used.is_file() and limit.read_text().strip() != 'max':
            available = min(available, int(limit.read_text()) - int(used.read_text()))
        if parent == Path('/sys/fs/cgroup'):
            break
    return available / GIB


def terminate(process):
    """Ask the supervisor to forward TERM to its independently grouped child."""
    # Capture owned descendants before their parent can exit/reparent them.
    owned = {process.pid}
    for _ in range(5):
        for p in Path('/proc').glob('[0-9]*/stat'):
            try:
                fields = p.read_text().rsplit(')', 1)[1].split()
                if int(fields[1]) in owned:
                    owned.add(int(p.parent.name))
            except (OSError, ValueError, IndexError):
                pass
    process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        pass
    for pid in owned:
        try:
            # The tracker unlinks shared-memory segments after workers exit.
            # Killing it with those workers can leak the export queue in /dev/shm.
            command = Path(f'/proc/{pid}/cmdline').read_bytes()
            if b'multiprocessing.resource_tracker' in command:
                continue
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, FileNotFoundError):
            pass
    process.wait()


def launch(command, cwd, log, timeout, memory_floor_gib=0, output=None, max_rss_gib=0):
    start = time.monotonic()
    with Path(log).open('x') as stream:
        process = subprocess.Popen(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
        try:
            while process.poll() is None:
                elapsed = time.monotonic() - start
                if elapsed > timeout:
                    raise RuntimeError('cell_timeout')
                if memory_floor_gib and available_gib() < memory_floor_gib:
                    raise RuntimeError('host_memory_floor')
                if output is not None and max_rss_gib:
                    samples = journal(output.with_suffix('.resources.jsonl'))
                    recent = next((r for r in reversed(samples) if r.get('process_rss_bytes')), {})
                    if recent.get('process_rss_bytes', 0) / GIB > max_rss_gib:
                        raise RuntimeError('process_rss_ceiling')
                time.sleep(2)
        except BaseException:
            terminate(process)
            raise
    return process.returncode, time.monotonic() - start


def summarize(output, target, wall, validation_seconds):
    run = read(output.with_suffix('.run.json'))
    result = read(output.with_suffix('.result.json'))
    physical = read(output.with_suffix('.validation.json'))
    events = journal(output.with_suffix('.telemetry.jsonl'))
    policy = next(e for e in events if e['event'] == 'generation_policy')
    started = next(e for e in events if e['event'] == 'episode_started')
    finished = [e for e in events if e['event'] == 'episode_finished']
    successes = [e for e in finished if e['success'] is True]
    ready = next(e for e in reversed(events) if e['event'] == 'output_ready')
    if run['status'] != 'succeeded' or not policy['guarantee_success']:
        raise ValueError('Run did not complete a success-target policy')
    if result['requested_trials'] != target or len(successes) < target:
        raise ValueError('Success target not reached')
    episodes = physical['episodes']
    if not physical['passed'] or len(episodes) != result['num_success'] or len(successes) != len(episodes):
        raise ValueError('Saved, generated and physically valid counts disagree')
    if not all(e['recorded_success'] and e['final_state_success'] for e in episodes):
        raise ValueError('Terminal-state validation failed')
    export_path = output.with_suffix('.export.json')
    if export_path.exists() and read(export_path)['status'] != 'complete':
        raise ValueError('Async export has not finished')
    # All rows use 32 / elapsed as the primary rate. Overshoot is explicit and
    # never credited as an apparent speedup for more parallel environments.
    generation = finished[-1]['elapsed_seconds'] - started['elapsed_seconds']
    final_ready = ready['elapsed_seconds'] - started['elapsed_seconds']
    verified = wall + validation_seconds
    if min(generation, final_ready, verified) <= 0:
        raise ValueError('Invalid timing interval')
    resources = journal(output.with_suffix('.resources.jsonl'))
    first_time, end_time = started['time_utc'], ready['time_utc']
    active = [r for r in resources if first_time <= r.get('time_utc', '') <= end_time]
    util = [g['utilization_percent'] for r in active for g in r.get('gpus', [])
            if isinstance(g.get('utilization_percent'), (int, float))]
    vram = [g['memory_used_mib'] for r in resources for g in r.get('gpus', [])
            if isinstance(g.get('memory_used_mib'), (int, float))]
    cgroups = [r.get('cgroup', {}).get('memory.current', 0) for r in resources]
    oom = sum(r.get('cgroup_memory_event_deltas', {}).get('oom_kill', 0) for r in resources)
    if oom:
        raise ValueError('OOM occurred during measurement')
    return dict(status='valid', saved_successes=len(episodes), target=target,
                overshoot=len(episodes) - target, attempts=result['num_attempts'],
                success_rate=result['num_success'] / result['num_attempts'],
                generation_seconds=generation, final_ready_seconds=final_ready,
                time_to_32_generated_seconds=successes[target - 1]['elapsed_seconds'] - started['elapsed_seconds'],
                launcher_seconds=wall, validation_seconds=validation_seconds,
                verified_seconds=verified, episodes_per_minute=target * 60 / verified,
                final_ready_per_minute=target * 60 / final_ready,
                actual_saved_per_minute=len(episodes) * 60 / verified,
                gpu_util_mean=statistics.mean(util) if util else None,
                gpu_util_p50=statistics.median(util) if util else None,
                gpu_util_p95=sorted(util)[math.ceil(.95 * len(util)) - 1] if util else None,
                gpu_samples=len(util), peak_vram_mib=max(vram, default=None),
                peak_cgroup_memory_gib=max(cgroups, default=0) / GIB,
                peak_process_rss_gib=max((r.get('process_rss_bytes') or 0 for r in resources), default=0) / GIB,
                stage_host_seconds={name: sum(e.get('stages_seconds', {}).get(name, 0) for e in finished)
                                    for name in ('reset', 'motion_plan', 'execution_wait', 'export', 'export_enqueue')},
                episode_steps_mean=statistics.mean(e['steps'] for e in episodes),
                episode_steps_min=min(e['steps'] for e in episodes),
                episode_steps_max=max(e['steps'] for e in episodes),
                output_sha256=physical['sha256'], output_bytes=output.stat().st_size)


def aggregate(rows, baseline, repeats):
    groups = {}
    for row in rows:
        groups.setdefault((row['variant'], row['num_envs']), []).append(row)
    summaries = []
    for (variant, envs), cells in groups.items():
        valid = [c for c in cells if c['status'] == 'valid']
        if valid:
            rates = [c['episodes_per_minute'] for c in valid]
            summaries.append(dict(variant=variant, num_envs=envs, valid_repeats=len(valid),
                                  complete=len(valid) == repeats, median_episodes_per_minute=statistics.median(rates),
                                  min_episodes_per_minute=min(rates), max_episodes_per_minute=max(rates),
                                  median_gpu_util=statistics.median([c['gpu_util_mean'] for c in valid
                                                                   if c['gpu_util_mean'] is not None])
                                  if any(c['gpu_util_mean'] is not None for c in valid) else None))
    base = {s['num_envs']: s for s in summaries if s['variant'] == baseline and s['complete']}
    for s in summaries:
        b = base.get(s['num_envs'])
        s['matched_parallelism_speedup'] = s['median_episodes_per_minute'] / b['median_episodes_per_minute'] if b and s['complete'] else None
    best = {}
    for s in summaries:
        if s['complete'] and (s['variant'] not in best or s['median_episodes_per_minute'] > best[s['variant']]['median_episodes_per_minute']):
            best[s['variant']] = dict(s)
    for s in best.values():
        b = best.get(baseline)
        s['best_parallelism_speedup'] = s['median_episodes_per_minute'] / b['median_episodes_per_minute'] if b else None
    return dict(cells=summaries, best_by_variant=best)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--production-root', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--python', type=Path, default=Path(sys.executable))
    parser.add_argument('--variants', type=Path, help='JSON list of name, production_root and workers; first is baseline')
    parser.add_argument('--envs', type=int, nargs='+', default=[4, 6, 8, 12, 16, 24, 32, 64])
    parser.add_argument('--repeats', type=int, default=1, help='Screen once; confirm selected cells with >=3 repeats')
    parser.add_argument('--seeds', type=int, nargs='+', default=[1, 2, 3])
    parser.add_argument('--timeout', type=float, default=3600)
    parser.add_argument('--queue-gib', type=float, default=8)
    parser.add_argument('--estimated-env-gib', type=float, default=4.5)
    parser.add_argument('--memory-floor-gib', type=float, default=8)
    parser.add_argument('--base-reserve-gib', type=float, default=12)
    parser.add_argument('--max-rss-gib', type=float, default=44, help='Main-process RSS ceiling; retain headroom for export copies')
    parser.add_argument('--keep-datasets', action='store_true', help='Default: remove only verified cell datasets to bound disk use')
    parser.add_argument('--execute', action='store_true', help='Without this flag only write the exact plan')
    args = parser.parse_args()
    if args.repeats < 1 or len(args.seeds) < args.repeats or min(args.envs) < 1:
        parser.error('Need positive envs/repeats and one seed per repeat')
    for name in ('timeout', 'queue_gib', 'estimated_env_gib', 'memory_floor_gib', 'base_reserve_gib', 'max_rss_gib'):
        if not math.isfinite(getattr(args, name)) or getattr(args, name) <= 0:
            parser.error(f'{name} must be finite and positive')
    args.production_root = args.production_root.resolve()
    args.input = args.input.resolve()
    args.directory = args.directory.resolve()
    args.python = args.python.resolve()
    variants = read(args.variants) if args.variants else [
        dict(name='sync', workers=0), dict(name='pool2', workers=2), dict(name='auto', workers='auto')]
    names = [v['name'] for v in variants]
    if not names or len(names) != len(set(names)) or any(not re.fullmatch('[a-zA-Z0-9_-]+', n) for n in names):
        parser.error('Variant names must be unique portable directory names')
    for v in variants:
        v['production_root'] = str(Path(v.get('production_root', args.production_root)).resolve())
        if v['workers'] != 'auto' and (not isinstance(v['workers'], int) or v['workers'] < 0):
            parser.error('workers must be auto or a nonnegative integer')
        if 'max_envs' in v and (not isinstance(v['max_envs'], int) or v['max_envs'] < 1):
            parser.error('max_envs must be a positive integer')
        if 'min_envs' in v and (not isinstance(v['min_envs'], int) or v['min_envs'] < 1):
            parser.error('min_envs must be a positive integer')
    args.directory.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(__file__, args.directory / 'harness.py')
    plan = dict(schema_version=1, target=32, final_hold_steps=60, variants=variants,
                terminal_gate=True, benchmark_code_sha256={p.name: digest(p) for p in sorted(Path(__file__).parent.glob('*.py'))},
                envs=sorted(set(args.envs)), repeats=args.repeats, seeds=args.seeds[:args.repeats],
                source_sha256=digest(args.input), harness_sha256=digest(__file__),
                created_at=datetime.now(timezone.utc).isoformat(), rows=[],
                evidence='runtime' if args.execute else 'plan_only',
                retention='keep' if args.keep_datasets else 'remove_verified_datasets_keep_hashes_and_logs',
                settings={k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()})
    for v in variants:
        root = Path(v['production_root'])
        task = root / 'runtime/openarm_autodata/tasks/pick_place/autodata_configs/tasks/openarm_bimanual_left_pick_place.yaml'
        v['task_sha256'] = digest(task)
        # Runtime assets and code hashes make comparisons across revisions traceable.
        v['code_sha256'] = {p.name: digest(p) for p in sorted(root.glob('*.py'))}
        v['runtime_sha256'] = {str(p.relative_to(root)): digest(p) for p in sorted((root / 'runtime/openarm_autodata').rglob('*'))
                               if p.is_file() and p.suffix in ('.py', '.yaml', '.yml', '.usd', '.usda', '.usdc', '.urdf', '.stl', '.obj', '.dae')}
        v['upstream'] = {}
        for name, source in [('autodata', root.parents[1] / 'AutoData'),
                             ('arena', root.parents[1] / 'AutoData/submodules/IsaacLab-Arena'),
                             ('isaaclab', root.parents[1] / 'AutoData/submodules/IsaacLab-Arena/submodules/IsaacLab')]:
            commit = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
            diff = subprocess.check_output(['git', '-C', str(source), 'diff', '--no-ext-diff', 'HEAD'])
            v['upstream'][name] = dict(commit=commit, tracked_diff_sha256=hashlib.sha256(diff).hexdigest())
    write(args.directory / 'report.json', plan)
    if not args.execute:
        print(f'Plan prepared: {args.directory / "report.json"}', flush=True)
        return
    subprocess.run(['nvidia-smi'], check=True, stdout=subprocess.DEVNULL)
    plan['gpu_environment'] = subprocess.check_output(
        ['nvidia-smi', '--query-gpu=name,uuid,driver_version,memory.total,power.limit',
         '--format=csv,noheader,nounits'], text=True).strip()
    plan['cpu_governors'] = sorted({p.read_text().strip() for p in Path('/sys/devices/system/cpu').glob('cpu*/cpufreq/scaling_governor')})
    write(args.directory / 'report.json', plan)
    capacity_ceiling = {}
    # Process-level parallel runs would compete for the same GPU; only envs and
    # exporter workers within a cell are parallel. Alternate variant order.
    for rep, seed in enumerate(args.seeds[:args.repeats]):
        for envs in sorted(set(args.envs)):
            for v in (variants if rep % 2 == 0 else list(reversed(variants))):
                cell = args.directory / f'{v["name"]}-env{envs}-seed{seed}-rep{rep + 1}'
                cell.mkdir()
                row = dict(variant=v['name'], num_envs=envs, seed=seed, repeat=rep + 1, status='starting')
                plan['rows'].append(row)
                output = cell / 'dataset.hdf5'
                root = Path(v['production_root'])
                try:
                    if envs < v.get('min_envs', 1):
                        row.update(status='skipped_scope', reason='Outside variant requested scope')
                        continue
                    if envs > v.get('max_envs', math.inf):
                        row.update(status='skipped_capacity', reason='Configured ceiling from prior capacity evidence')
                        continue
                    if envs >= capacity_ceiling.get(v['name'], math.inf):
                        row.update(status='skipped_capacity', reason='Prior cell reached memory ceiling or OOM')
                        continue
                    need = args.base_reserve_gib + envs * args.estimated_env_gib + (args.queue_gib if v['workers'] else 0)
                    if available_gib() < need + args.memory_floor_gib:
                        row.update(status='skipped_memory', estimated_required_gib=need, available_gib=available_gib())
                        continue
                    # ~0.5 GiB/episode observed; allow overshoot and shard merge.
                    disk_need = (32 + envs + (32 if v['workers'] else 0)) * .55 + 4
                    if shutil.disk_usage(cell).free / GIB < disk_need:
                        row.update(status='skipped_disk')
                        continue
                    import yaml  # existing runtime dependency; not needed for import/plan
                    task_path = root / 'runtime/openarm_autodata/tasks/pick_place/autodata_configs/tasks/openarm_bimanual_left_pick_place.yaml'
                    task = yaml.safe_load(task_path.read_text())
                    if task['generation_policy']['guarantee_success'] is not True or task['generation_policy']['keep_failed'] is not False:
                        raise ValueError('Require guarantee_success=true and keep_failed=false')
                    task['generation_policy']['seed'] = seed
                    descriptor = cell / 'task.yaml'
                    descriptor.write_text(yaml.safe_dump(task, sort_keys=False))
                    launcher = 'owned_launch.py' if v.get('owned_recording') else 'terminal_launch.py'
                    command = [str(args.python), str(Path(__file__).with_name(launcher).resolve()),
                               '--production-root', str(root), '--arm', 'left', '--final-hold-steps', '60',
                               '--input_file', str(args.input), '--output_file', str(output),
                               '--num_envs', str(envs), '--generation_num_trials', '32',
                               '--task_descriptor', str(descriptor), '--export-workers', str(v['workers']),
                               '--export-queue-memory-gib', str(args.queue_gib), '--log-interval', '2']
                    row['command'] = command
                    # Refuse competing compute jobs; desktop graphics are permitted.
                    competing = subprocess.check_output(
                        ['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader,nounits'], text=True).strip()
                    if competing:
                        raise RuntimeError('GPU has another compute process: ' + competing)
                    write(args.directory / 'report.json', plan)
                    print(f'Starting {cell.name}', flush=True)
                    previous_python = os.environ.get('OPENARM_PYTHON')
                    os.environ['OPENARM_PYTHON'] = str(args.python)
                    try:
                        code, wall = launch(command, root.parents[1], cell / 'launcher.log', args.timeout,
                                            args.memory_floor_gib, output, args.max_rss_gib)
                    finally:
                        if previous_python is None:
                            os.environ.pop('OPENARM_PYTHON', None)
                        else:
                            os.environ['OPENARM_PYTHON'] = previous_python
                    if code:
                        raise RuntimeError(f'generation_exit_{code}')
                    validation_start = time.monotonic()
                    for name, script in [('physical', root / 'validate_output.py'),
                                         ('schema', root.parents[1] / 'AutoData/scripts/validate_dataset.py')]:
                        code, _ = launch([str(args.python), str(script), str(output)], root.parents[1],
                                         cell / f'{name}.log', args.timeout)
                        if code:
                            raise RuntimeError(f'{name}_validation_failed')
                    row.update(summarize(output, 32, wall, time.monotonic() - validation_start))
                    if not args.keep_datasets:
                        output.unlink()
                        parts = output.with_suffix('.export-parts')
                        if parts.exists():
                            shutil.rmtree(parts)
                        row['dataset_retained'] = False
                    else:
                        row['dataset_retained'] = True
                except Exception as exc:
                    row.update(status='failed', error=f'{type(exc).__name__}: {exc}')
                    samples = journal(output.with_suffix('.resources.jsonl'))
                    oom = any(r.get('cgroup_memory_event_deltas', {}).get('oom_kill', 0) for r in samples)
                    row['oom_observed'] = oom
                    if oom or str(exc) in ('host_memory_floor', 'process_rss_ceiling'):
                        capacity_ceiling[v['name']] = envs
                    if not oom and str(exc) in ('host_memory_floor', 'process_rss_ceiling'):
                        row['status'] = 'capacity_limited'
                    print(f'Failed {cell.name}: {exc}', flush=True)
                finally:
                    plan['summary'] = aggregate(plan['rows'], names[0], args.repeats)
                    write(args.directory / 'report.json', plan)
                    print(json.dumps(row, ensure_ascii=False), flush=True)
    plan['completed_at'] = datetime.now(timezone.utc).isoformat()
    compared = {r['variant'] for r in plan['rows'] if r['status'] == 'valid'}
    plan['complete_requested_grid'] = all(r['status'] == 'valid' for r in plan['rows'])
    plan['passed'] = bool(plan['rows']) and all(r['status'] in ('valid', 'skipped_memory', 'skipped_disk', 'skipped_capacity', 'skipped_scope', 'capacity_limited') for r in plan['rows']) and set(names) <= compared
    plan['conclusion_scope'] = 'single_seed_screening' if args.repeats == 1 else 'repeated_observed_cells'
    write(args.directory / 'report.json', plan)
    if not plan['passed']:
        raise SystemExit('Benchmark incomplete/failed; inspect report.json, no unvalidated speedup is accepted')


if __name__ == '__main__':
    main()
