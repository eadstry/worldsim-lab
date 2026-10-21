"""One isolated eight-environment export regression, not 24-env qualification."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import h5py
import numpy as np


def readback(output, expected_successes, terminal_success):
    reports, files = [], {}
    paths = [p for p in (output, output.with_name(output.stem + '_failed.hdf5')) if p.is_file()]
    for path in paths:
        with h5py.File(path, 'r') as file:
            for name, episode in file['data'].items():
                steps = len(episode['actions'])
                if steps <= 0 or episode['actions'].shape != (steps, 7):
                    raise ValueError('Invalid action shape')
                for camera in ('left_hand_rgb', 'right_hand_rgb', 'third_person_rgb'):
                    image = episode['obs/' + camera]
                    if image.shape != (steps, 480, 640, 3) or image.dtype != np.uint8:
                        raise ValueError('Camera shape or dtype changed')
                hashes = {}

                def check(key, item):
                    if not isinstance(item, h5py.Dataset):
                        return
                    digest = hashlib.sha256()
                    frame_bytes = max(1, int(np.prod(item.shape[1:])) * item.dtype.itemsize)
                    cap = max(1, 96 * 1024**2 // frame_bytes)
                    # Align time-axis reads with HDF5 chunks where the memory cap permits.
                    stride = min(cap, item.chunks[0] if item.chunks else cap)
                    blocks = (item[i:i + stride] for i in range(0, item.shape[0], stride)) if item.ndim else [item[()]]
                    for block in blocks:
                        array = np.asarray(block)
                        if np.issubdtype(array.dtype, np.number) and not np.isfinite(array).all():
                            raise ValueError('Nonfinite data: ' + key)
                        digest.update(array.tobytes())
                    hashes[key] = digest.hexdigest()

                episode.visititems(check)
                passed = terminal_success(episode['states/rigid_object/cube/root_pose'][-1],
                                          episode['states/rigid_object/table/root_pose'][-1],
                                          episode['states/rigid_object/cube/root_velocity'][-1],
                                          episode['states/articulation/robot/joint_position'][-1])
                label = bool(episode.attrs['success'])
                if label and not passed:
                    raise ValueError('Successful label fails unchanged terminal predicate')
                reports.append(dict(file=path.name, episode=name, steps=steps,
                                    recorded_success=label, terminal_pass=passed, dataset_hashes=hashes))
        files[path.name] = dict(bytes=path.stat().st_size)
    if sum(r['recorded_success'] for r in reports) != expected_successes:
        raise ValueError('Success counts disagree')
    return dict(episodes=reports, files=files,
                scope='All datasets read in bounded blocks with per-array hashes and recorded terminal checks; no physics replay')


def claim_directory(path):
    # mkdir is the ownership claim; no check-then-create or resume of an old run.
    path.mkdir(parents=True, exist_ok=False)


def check_manifest(path):
    manifest = json.loads(path.read_text())
    for name, expected in manifest.items():
        digest = hashlib.sha256(Path(name).read_bytes()).hexdigest()
        if digest != expected:
            raise ValueError('Frozen dependency changed: ' + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshots', type=Path, required=True)
    parser.add_argument('--source-manifest', type=Path, required=True)
    parser.add_argument('--autodata-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    check_manifest(args.source_manifest)
    claim_directory(args.output)
    production = args.snapshots.resolve() / 'export-source-snapshot'
    capacity = args.snapshots.resolve() / 'capacity-snapshot'
    gate = args.snapshots.resolve() / 'gate-snapshot'
    sys.path[:0] = [str(capacity), str(production), str(gate)]
    from produce import launch_cell
    from run import write
    from terminal_gate import terminal_success
    options = SimpleNamespace(directory=args.output.resolve(), production_root=production,
                              gate_root=gate, autodata_root=args.autodata_root.resolve(),
                              input=production / 'runtime/inputs/openarm_left_fixture_clearance_source.hdf5',
                              task=args.snapshots.resolve() / 'regression-task.yaml')
    report = dict(scope='8-env export regression only; formal production parallelism remains 24',
                  attempts_budget=8, num_envs=8, seed=606, automatic_retries=False,
                  qualification24=False, status='started')
    write(args.output / 'report.json', report)
    try:
        row = launch_cell(options, 'env8-auto-seed606', 8, 'auto', 606, 8)
        output = args.output / 'env8-auto-seed606/dataset.hdf5'
        # Read every numeric/image leaf and validate the unchanged terminal predicate.
        validation = readback(output, row['stats']['num_success'], terminal_success)
        if len(validation['episodes']) != 8:
            raise ValueError('Not all eight attempts have exported trajectories')
        write(args.output / 'validation.json', validation)
        check_manifest(args.source_manifest)
        report.update(status='completed', production=row,
                      exported_episodes=len(validation['episodes']),
                      validation='all recorded leaves read; successful labels satisfy recorded terminal gate',
                      image_semantic_usability='not established by structural readback',
                      dependencies_unchanged=True)
    except BaseException as exc:
        report.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        write(args.output / 'report.json', report)


if __name__ == '__main__':
    main()
