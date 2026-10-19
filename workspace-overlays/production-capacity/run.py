# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Foreground, fail-closed pilot/screen/confirmation orchestration (74 attempts)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

GIB = 1024**3
CAMERAS = ('left_hand_rgb', 'right_hand_rgb', 'third_person_rgb')


def write(path, value):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024**2), b''):
            h.update(block)
    return h.hexdigest()


def read_rows(path):
    rows = []
    lines = path.read_text().splitlines()
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            if index != len(lines) - 1:
                raise
    return rows


def freeze(paths):
    result = {}
    for path in paths:
        path = path.resolve()
        files = path.rglob('*') if path.is_dir() else [path]
        for file in sorted(files):
            if file.is_file() and '__pycache__' not in file.parts and not file.name.endswith('.pyc'):
                result[str(file)] = digest(file)
    return result


def assert_frozen(manifest):
    for name, expected in manifest.items():
        if digest(Path(name)) != expected:
            raise RuntimeError('Frozen dependency changed: ' + name)


def validate(output, expected_successes):
    """Blockwise-read every dataset; no full RGB episode allocation."""
    import h5py
    import numpy as np
    from terminal_gate import terminal_success
    reports = []
    paths = [p for p in (output, output.with_name(output.stem + '_failed.hdf5')) if p.is_file()]
    for path in paths:
        with h5py.File(path, 'r') as file:
            for name, episode in file['data'].items():
                steps = len(episode['actions'])
                if episode['actions'].shape != (steps, 7) or steps <= 0:
                    raise ValueError('Invalid action dimensions')
                for camera in CAMERAS:
                    image = episode['obs/' + camera]
                    if image.shape != (steps, 480, 640, 3) or image.dtype != np.uint8:
                        raise ValueError('Image shape/dtype changed')
                hashes = {}
                def check(key, item):
                    if not isinstance(item, h5py.Dataset):
                        return
                    h = hashlib.sha256()
                    pieces = (item[i:i+4] for i in range(0, item.shape[0], 4)) if item.ndim else [item[()]]
                    for block in pieces:
                        array = np.asarray(block)
                        if np.issubdtype(array.dtype, np.number) and not np.isfinite(array).all():
                            raise ValueError('Non-finite recorded values: ' + key)
                        h.update(array.tobytes())
                    hashes[key] = h.hexdigest()
                episode.visititems(check)
                cube = episode['states/rigid_object/cube/root_pose'][-1]
                table = episode['states/rigid_object/table/root_pose'][-1]
                velocity = episode['states/rigid_object/cube/root_velocity'][-1]
                joints = episode['states/articulation/robot/joint_position'][-1]
                terminal = terminal_success(cube, table, velocity, joints)
                label = bool(episode.attrs['success'])
                if label and not terminal:
                    raise ValueError('Exported successful episode fails physical terminal gate')
                reports.append(dict(file=path.name, episode=name, steps=steps, recorded_success=label,
                    terminal_pass=terminal, dataset_hashes=hashes))
    if sum(r['recorded_success'] for r in reports) != expected_successes:
        raise ValueError('Saved success count disagrees with generator')
    return dict(episodes=reports, files={p.name: dict(bytes=p.stat().st_size, sha256=digest(p)) for p in paths},
        scope='Full dataset read and recorded terminal checks; no independent physics replay')


def videos(output, validation, destination, already_saved):
    """One near-field review video per outcome/configuration, outside timing."""
    import h5py
    try:
        import imageio_ffmpeg
        executable = imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        executable = shutil.which('ffmpeg')
    if not executable:
        return dict(status='unavailable', reason='No existing ffmpeg executable; no installation performed')
    saved = []
    # Prefer active left wrist because the right wrist can be black in this task.
    for episode in validation['episodes']:
        outcome = 'success' if episode['recorded_success'] else 'failure'
        if outcome in already_saved:
            continue
        target = destination / (outcome + '.mp4')
        destination.mkdir(parents=True, exist_ok=True)
        with h5py.File(output.parent / episode['file'], 'r') as file:
            group = file['data/' + episode['episode']]
            camera = group['obs/left_hand_rgb']
            # Source OpenArm control/camera frequency is 30 Hz; verify with provenance.
            cmd = [executable, '-nostdin', '-v', 'error', '-n', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                '-s', '640x480', '-r', '30', '-i', 'pipe:0', '-vf', 'fps=15,scale=320:240',
                '-c:v', 'libx264', '-crf', '28', '-pix_fmt', 'yuv420p', '-an', str(target)]
            process = subprocess.Popen(cmd, stdin=subprocess.PIPE)
            try:
                for frame in camera:
                    process.stdin.write(frame.tobytes())
                process.stdin.close()
                if process.wait() != 0:
                    raise RuntimeError('Review video encoding failed')
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait()
        already_saved.add(outcome)
        saved.append(str(target))
    return dict(status='complete', files=saved)


def run_cell(args, label, envs, workers, seed, attempts, provenance):
    import yaml
    from resources import cgroup_sample
    from bench32 import available_gib, terminate
    cell = args.directory / label
    cell.mkdir()
    row = dict(label=label, envs=envs, workers=workers, seed=seed, attempts_requested=attempts, status='preflight')
    def persist():
        write(cell / 'cell.json', row)
    persist()
    try:
        assert_frozen(provenance)
        if shutil.disk_usage(args.directory).free < 70 * GIB:
            raise RuntimeError('Storage reserve below 70 GiB')
        competing = subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader,nounits'], text=True).strip()
        if competing:
            raise RuntimeError('Other GPU compute processes present: ' + competing)
        if available_gib() < 12 + envs * 4.5 + (16 if workers else 0) + 8:
            raise RuntimeError('Insufficient effective memory for requested cell')
        output = cell / 'dataset.hdf5'
        task = yaml.safe_load(args.task.read_text())
        task['generation_policy'].update(seed=seed, guarantee_success=False, keep_failed=True, num_trials=attempts)
        descriptor = cell / 'task.yaml'
        descriptor.write_text(yaml.safe_dump(task, sort_keys=False))
        command = [sys.executable, str(Path(__file__).with_name('launch.py')), '--production-root', str(args.production_root),
            '--gate-root', str(args.gate_root), '--autodata-root', str(args.autodata_root), '--arm', 'left',
            '--final-hold-steps', '60', '--input_file', str(args.input), '--output_file', str(output),
            '--num_envs', str(envs), '--generation_num_trials', str(attempts), '--task_descriptor', str(descriptor),
            '--export-workers', str(workers), '--export-queue-memory-gib', '16', '--log-interval', '2']
        row.update(status='running', command=command)
        persist()
        initial_oom = cgroup_sample(os.getpid()).get('memory.events', {}).get('oom_kill', 0)
        start = time.monotonic()
        process = None
        with (cell / 'launcher.log').open('xb') as log:
            try:
                process = subprocess.Popen(command, cwd=args.production_root.parents[1], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                while process.poll() is None:
                    if time.monotonic() - start > 2400:
                        raise RuntimeError('Batch exceeded 2400 second limit')
                    if shutil.disk_usage(args.directory).free < 70 * GIB:
                        raise RuntimeError('Storage reserve below 70 GiB')
                    if available_gib() < 8:
                        raise RuntimeError('Effective available memory below 8 GiB')
                    samples = output.with_suffix('.resources.jsonl')
                    if samples.exists():
                        rows = read_rows(samples)
                        latest = rows[-1] if rows else {}
                        if latest.get('system_memory_available_bytes', 100 * GIB) < 8 * GIB:
                            raise RuntimeError('Available host memory below 8 GiB')
                        if latest.get('process_rss_bytes', 0) > 44 * GIB:
                            raise RuntimeError('Producer RSS above 44 GiB')
                    time.sleep(2)
                row['launcher_seconds'] = time.monotonic() - start
                if process.returncode:
                    raise RuntimeError('Production supervisor failed: ' + str(process.returncode))
            finally:
                if process is not None and process.poll() is None:
                    terminate(process)
                elif process is not None and process.returncode:
                    # Supervisor may have died before forwarding to its child.
                    run_path = output.with_suffix('.run.json')
                    if run_path.exists():
                        child_pid = json.loads(run_path.read_text()).get('child_pid')
                        if child_pid:
                            try:
                                os.killpg(child_pid, signal.SIGTERM)
                            except ProcessLookupError:
                                pass
        stats = json.loads(output.with_suffix('.result.json').read_text())
        telemetry = read_rows(output.with_suffix('.telemetry.jsonl'))
        starts = [r for r in telemetry if r['event'] == 'episode_started']
        finished = [r for r in telemetry if r['event'] == 'episode_finished']
        if (stats['num_attempts'] != attempts or len(starts) != attempts or len(finished) != attempts
                or stats['num_success'] + stats['num_failures'] != attempts
                or any(r['event'] == 'episode_cancelled' for r in telemetry)):
            raise ValueError('Exact attempt accounting mismatch')
        if any(r.get('error') for r in finished):
            raise ValueError('Execution exception is not an ordinary task failure')
        if cgroup_sample(os.getpid()).get('memory.events', {}).get('oom_kill', 0) > initial_oom:
            raise RuntimeError('OOM event observed; attribution may include other cgroup processes')
        ready = next(r for r in reversed(telemetry) if r['event'] == 'output_ready')
        final_seconds = ready['elapsed_seconds'] - starts[0]['elapsed_seconds']
        if final_seconds <= 0:
            raise ValueError('Invalid final-ready timing')
        check_start = time.monotonic()
        validation = validate(output, stats['num_success'])
        row['validation_seconds'] = time.monotonic() - check_start
        write(cell / 'validation.json', validation)
        row.update(status='complete', stats=stats, final_ready_seconds=final_seconds,
            qualified_per_minute=stats['num_success'] * 60 / final_seconds,
            verified_per_minute=stats['num_success'] * 60 / (row['launcher_seconds'] + row['validation_seconds']),
            saved_episodes=len(validation['episodes']),
            missing_failed_trajectories=attempts-len(validation['episodes']),
            failed_trajectory_note='Planning can return before recorder export; these attempts remain in denominator and telemetry',
            actual_workers_started=sum(r['event'] == 'export_worker_started' for r in telemetry))
        assert_frozen(provenance)
        # Review video encoding is outside production and validation timing.
        variant = f'env{envs}-workers{workers}'
        directory = args.directory / 'videos' / variant
        existing = {p.stem for p in directory.glob('*.mp4')} if directory.exists() else set()
        row['review_videos'] = videos(output, validation, directory, existing)
        persist()
        print(json.dumps({k: row[k] for k in ('label', 'status', 'qualified_per_minute', 'stats')}, ensure_ascii=False), flush=True)
        return row
    except BaseException as exc:
        row.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        persist()
        raise


def reuse_sync_pilot(args, provenance):
    """Recover only the known post-validation video failure; no new GPU work."""
    original = args.reuse_sync_pilot
    source = original / 'pilot-workers0'
    row = json.loads((source / 'cell.json').read_text())
    supervisor = json.loads((source / 'dataset.run.json').read_text())
    if (row.get('label') != 'pilot-workers0' or row.get('envs') != 1 or row.get('workers') != 0
            or row.get('seed') != 101 or row.get('attempts_requested') != 1
            or row.get('stats', {}).get('num_attempts') != 1
            or row.get('stats', {}).get('num_success') != 1
            or supervisor.get('status') != 'succeeded'
            or not row.get('error', '').startswith('FileNotFoundError:')
            or '/videos/env1-workers0' not in row['error']):
        raise ValueError('Only the verified sync pilot video-directory failure can be reused')
    old_manifest = json.loads((original / 'provenance.json').read_text())
    harness = Path(__file__).parent.resolve()
    # Only the controller and its tests/docs may change for this recovery.
    # The launch transform, simulation inputs/assets and production code must match.
    for name, expected in old_manifest.items():
        path = Path(name)
        if path.parent == harness and path.name in ('run.py', 'test_capacity.py', 'README.md'):
            continue
        if provenance.get(name) != expected:
            raise ValueError('Pilot dependency changed; refusing reuse: ' + name)
    recorded = json.loads((source / 'validation.json').read_text())
    for name, details in recorded['files'].items():
        if digest(source / name) != details['sha256']:
            raise ValueError('Recovered pilot file hash changed: ' + name)
    target = args.directory / 'pilot-workers0'
    shutil.copytree(source, target)
    before = time.monotonic()
    recovered = validate(target / 'dataset.hdf5', 1)
    if recovered != recorded:
        raise ValueError('Recovered pilot validation differs from original evidence')
    row['recovery_validation_seconds'] = time.monotonic() - before
    row['original_error'] = row.pop('error')
    row.update(status='complete', reused_from=str(source),
        reused_revision=json.loads((original/'environment.json').read_text())['workspace_commit'])
    row['review_videos'] = videos(target/'dataset.hdf5', recovered,
        args.directory/'videos/env1-workers0', set())
    write(target/'cell.json', row)
    return row


def main():
    parser = argparse.ArgumentParser()
    for name in ('directory', 'production-root', 'gate-root', 'autodata-root', 'input', 'task'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--reuse-sync-pilot', type=Path, default=None)
    args = parser.parse_args()
    def interrupted(signum, frame):
        raise KeyboardInterrupt('Controller received signal ' + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    for name, value in vars(args).items():
        if value is not None:
            setattr(args, name, value.resolve())
    args.directory.mkdir(parents=True, exist_ok=False)
    sys.path[:0] = [str(args.production_root), str(args.gate_root)]
    runtime = args.production_root / 'runtime'
    provenance = freeze([*args.production_root.glob('*.py'), runtime / 'openarm_autodata', runtime / 'patches',
        args.autodata_root / 'scripts/generate_dataset.py', args.autodata_root / 'autodata_core',
        args.autodata_root / 'autodata_interfaces', args.input, args.task,
        Path(__file__).parent, *args.gate_root.glob('*.py')])
    write(args.directory / 'provenance.json', provenance)
    metadata = dict(worktree=str(args.production_root.parents[1]), python=sys.executable,
        workspace_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        upstream_commit=subprocess.check_output(['git','-C',str(args.autodata_root),'rev-parse','HEAD'],text=True).strip(),
        upstream_worktree_diff_sha256=hashlib.sha256(subprocess.check_output(['git','-C',str(args.autodata_root),'diff','--binary','HEAD'])).hexdigest(),
        gpu=subprocess.check_output(['nvidia-smi','--query-gpu=name,uuid,driver_version,memory.total','--format=csv,noheader'],text=True).strip(),
        raw_rgb='3x640x480, 30 Hz, gzip2', review_video='320x240, 15 fps, H264 CRF28',
        physical_validation='Original recorded-terminal thresholds, 60 final hold steps; not continuous-stability proof')
    write(args.directory / 'environment.json', metadata)
    report = dict(status='running', budget=74, rows=[], storage='User-provided /data allocation approximately 700 GB; 70 GiB reserve',
        primary_metric='qualified / final_ready; includes drain, merge and close, excludes validation',
        scope='Small-batch production comparison; not steady-state throughput or policy evaluation')
    def run(label, envs, workers, seed, attempts):
        row = run_cell(args, label, envs, workers, seed, attempts, provenance)
        report['rows'].append(row)
        write(args.directory / 'report.json', report)
        return row
    write(args.directory / 'report.json', report)
    try:
        if args.reuse_sync_pilot is not None:
            report['rows'].append(reuse_sync_pilot(args, provenance))
            write(args.directory / 'report.json', report)
        for worker in ((2,) if args.reuse_sync_pilot is not None else (0, 2)):
            row = run(f'pilot-workers{worker}', 1, worker, 101, 1)
            if row['stats']['num_success'] != 1:
                raise RuntimeError('Pilot task unsuccessful; screening not started')
        for seed, variants in [(101, (0, 2, 'auto')), (202, ('auto', 2, 0))]:
            for envs in (1, 4):
                for workers in variants:
                    run(f'screen-env{envs}-workers{workers}-seed{seed}', envs, workers, seed, 4)
        # Confirmation requires a candidate beating the synchronous baseline at
        # the same concurrency without reducing aggregate observed success rate.
        candidates = []
        for envs in (1, 4):
            base = [r for r in report['rows'] if r['label'].startswith('screen-') and r['envs']==envs and r['workers']==0]
            base_rate = sum(r['stats']['num_success'] for r in base) / sum(r['final_ready_seconds'] for r in base)
            base_success = sum(r['stats']['num_success'] for r in base)
            for worker in (2, 'auto'):
                rows = [r for r in report['rows'] if r['label'].startswith('screen-') and r['envs']==envs and r['workers']==worker]
                rate = sum(r['stats']['num_success'] for r in rows) / sum(r['final_ready_seconds'] for r in rows)
                if rate > base_rate and sum(r['stats']['num_success'] for r in rows) >= base_success:
                    candidates.append((rate, envs, str(worker)))
        if candidates:
            _, envs, worker = max(candidates)
            report['confirmation_selection'] = dict(envs=envs, candidate_workers=worker,
                reason='Highest observed qualified rate among candidates outperforming same-concurrency sync with no observed success-count decrease; screening only')
            write(args.directory / 'report.json', report)
            for index, seed in enumerate((303, 404, 505)):
                for workers in ((0, worker) if index % 2 == 0 else (worker, 0)):
                    run(f'confirm-env{envs}-workers{workers}-seed{seed}', envs, workers, seed, 4)
        else:
            report['confirmation_selection'] = None
            report['confirmation_skipped_reason'] = 'No asynchronous candidate improved qualified rate without observed success-count decrease'
        report['status'] = 'complete'
        comparisons = []
        for stage, seeds in [('screen', (101, 202)), ('confirm', (303, 404, 505))]:
            for seed in seeds:
                for envs in (1, 4):
                    rows = [r for r in report['rows'] if r['label'].startswith(stage+'-') and r['seed']==seed and r['envs']==envs]
                    baseline = next((r for r in rows if str(r['workers'])=='0'), None)
                    if baseline is None:
                        continue
                    def signatures(row, images):
                        check = json.loads((args.directory/row['label']/'validation.json').read_text())
                        signatures = []
                        for ep in check['episodes']:
                            values = ep['dataset_hashes']
                            signatures.append(json.dumps({k:v for k,v in values.items() if images or k not in ['obs/'+c for c in CAMERAS]}, sort_keys=True))
                        return sorted(signatures)
                    for row in rows:
                        if row is not baseline:
                            comparisons.append(dict(baseline=baseline['label'],candidate=row['label'],
                                non_rgb_exact=signatures(baseline,False)==signatures(row,False),
                                all_dataset_values_exact=signatures(baseline,True)==signatures(row,True)))
        report['recorded_value_comparisons'] = comparisons
        report['comparison_note'] = 'Order-independent exact dataset-value hashes; RGB differences require interpretation and are not pixel-quality scores'
    except BaseException as exc:
        report.update(status='failed', error=f'{type(exc).__name__}: {exc}', remaining_batches='not started')
        raise
    finally:
        write(args.directory / 'report.json', report)
        # Only this experiment's data; no environments, caches, queue snapshots or secrets.
        write(args.directory / 'SHA256.json', {str(p.relative_to(args.directory)): digest(p)
            for p in sorted(args.directory.rglob('*')) if p.is_file() and p.name != 'SHA256.json'})

    # Packaging is outside all efficiency windows and inside the shared queue.
    archive = args.directory.with_name(args.directory.name + '.tar.gz')
    if archive.exists():
        raise FileExistsError(archive)
    payload = sum(p.stat().st_size for p in args.directory.rglob('*') if p.is_file())
    if 2 * payload > 600_000_000_000:
        raise RuntimeError('Payload plus archive exceeds conservative personal allocation budget')
    if shutil.disk_usage(args.directory).free < payload + 70 * GIB:
        raise RuntimeError('Insufficient reserve for archive; original results retained')
    subprocess.run(['tar', '-czf', str(archive), '-C', str(args.directory.parent), args.directory.name], check=True)
    write(archive.with_suffix('.receipt.json'), dict(file=str(archive), bytes=archive.stat().st_size,
        sha256=digest(archive), upload_status='pending_destination_and_authenticated_uploader'))


if __name__ == '__main__':
    main()
