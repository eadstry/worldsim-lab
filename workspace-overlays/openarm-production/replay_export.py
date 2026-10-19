# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Host-only whole-episode replay of the actual upstream stack/write methods."""
from __future__ import annotations

import argparse
import ast
import json
import os
import tempfile
import time
from collections.abc import Iterable
from pathlib import Path
from types import SimpleNamespace

import h5py
import numpy as np
import torch

from export_timing import export_scope, install


def load_dataset_classes(root):
    """Execute only dataset class definitions, without importing Isaac Sim packages."""
    namespace = dict(torch=torch, np=np, json=json, os=os, Iterable=Iterable,
                     DatasetFileHandlerBase=object, DATASET_FORMAT_VERSION=1)
    for file, name in (('episode_data.py', 'EpisodeData'),
                       ('hdf5_dataset_file_handler.py', 'HDF5DatasetFileHandler')):
        path = root / file
        tree = ast.parse(path.read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)
        exec(compile(ast.Module(body=[cls], type_ignores=[]), str(path), 'exec'), namespace)
    return namespace['EpisodeData'], namespace['HDF5DatasetFileHandler']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--demo', default='demo_0')
    parser.add_argument('--compression', choices=('gzip', 'none'), default='gzip')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    source = args.input.resolve()
    assert source != args.report.resolve() and not args.report.exists()
    run_file = source.with_suffix('.run.json')
    if run_file.exists():
        assert json.loads(run_file.read_text()).get('ended_at'), 'Refusing active/stale production file'
    root = Path(__file__).resolve().parents[2]
    dataset_root = root / 'AutoData/submodules/IsaacLab-Arena/submodules/IsaacLab/source/isaaclab/isaaclab/utils/datasets'
    Episode, Handler = load_dataset_classes(dataset_root)
    episode = Episode()
    raw_bytes = 0
    start = time.perf_counter()
    with h5py.File(source, 'r') as dataset:
        group = dataset[f'data/{args.demo}']
        episode.success = bool(group.attrs.get('success', True))
        episode.seed = group.attrs.get('seed')

        def read_group(group):
            nonlocal raw_bytes
            values = {}
            for key, value in group.items():
                if isinstance(value, h5py.Group):
                    values[key] = read_group(value)
                else:
                    array = value[:]
                    raw_bytes += array.nbytes
                    tensor = torch.from_numpy(array)
                    # Reconstruct per-step lists; no GPU transfers in this replay.
                    values[key] = list(tensor.unbind(0))
            return values

        episode.data = read_group(group)
    input_read = time.perf_counter() - start
    rows = []

    def emit(event, **values):
        rows.append(dict(event=event, **values))

    with tempfile.TemporaryDirectory(prefix='export-replay-', dir=source.parent) as directory:
        target = Path(directory) / 'replay.hdf5'
        handler = Handler()
        handler.create(str(target))
        recorder = SimpleNamespace(_episodes={0: episode}, _dataset_file_handler=handler,
                                   _failed_episode_dataset_file_handler=None)
        install(recorder)
        try:
            with export_scope(emit, episode_id=args.demo, env_id=0):
                episode.pre_export()
                handler.write_episode(episode, dataset_compression=args.compression == 'gzip')
                handler.flush()
        finally:
            handler.close()
        start = time.perf_counter()
        with target.open('rb') as stream:
            os.fsync(stream.fileno())
        sync_seconds = time.perf_counter() - start
        output_bytes = target.stat().st_size
        with h5py.File(target, 'r') as output:
            def verify(name, value):
                if isinstance(value, h5py.Dataset):
                    tensor = episode.data
                    for key in name.split('/'):
                        tensor = tensor[key]
                    # Compare in frame blocks, avoiding another full-episode copy.
                    for offset in range(0, len(value), 32):
                        np.testing.assert_array_equal(value[offset:offset + 32], tensor[offset:offset + 32].numpy())
            output['data/demo_0'].visititems(verify)
    report = dict(source=str(source), demo=args.demo, compression=args.compression,
                  raw_bytes=raw_bytes, output_bytes=output_bytes,
                  input_read_seconds_excluded=input_read, export=rows[-1],
                  post_close_fsync_seconds=sync_seconds, data_roundtrip_equal=True,
                  limitations='Offline CPU replay of one saved episode, not a GPU production run. '
                              'Reconstructed CPU frame views differ from live allocation layout. '
                              'No recorder metadata/reset overhead, no concurrent simulation, and no GPU transfer. '
                              'fsync is diagnostic only and excluded from production-like export timing.')
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open('x') as stream:
        json.dump(report, stream, indent=2, default=str)
    print(json.dumps({k: v for k, v in report.items() if k != 'export'}, indent=2))
    print(json.dumps({k: v for k, v in rows[-1].items() if k != 'operations'}, indent=2))


if __name__ == '__main__':
    main()
