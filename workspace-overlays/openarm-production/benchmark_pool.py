# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Compare fixed real episodes via synchronous and shared-memory export paths."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import h5py
import numpy as np

from export_pool import ExportPool


def compare(source, target, expected):
    with h5py.File(source, 'r') as original, h5py.File(target, 'r') as result:
        assert dict(result.attrs) == dict(original.attrs)
        assert json.loads(result['data'].attrs['env_args']) == json.loads(original['data'].attrs['env_args'])
        assert result['data'].attrs['total'] == sum(original[f'data/{name}'].attrs['num_samples'] for name in expected)
        assert len(result['data']) == len(expected)
        for index, name in enumerate(expected):
            a, b = original[f'data/{name}'], result[f'data/demo_{index}']
            assert dict(a.attrs) == dict(b.attrs)
            source_names, target_names = [], []
            a.visit(source_names.append)
            b.visit(target_names.append)
            assert source_names == target_names
            for path in source_names:
                if not isinstance(a[path], h5py.Dataset):
                    continue
                x, y = a[path], b[path]
                assert not y.is_virtual and not y.external
                assert x.shape == y.shape and x.dtype == y.dtype and x.chunks == y.chunks
                assert x.compression == y.compression and x.compression_opts == y.compression_opts
                block = x.chunks[0] if x.chunks else 64
                for start in range(0, len(x), block):
                    np.testing.assert_array_equal(x[start:start + block], y[start:start + block])


def main():
    import torch
    from replay_export import load_dataset_classes
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--episodes', type=int, default=4)
    args = parser.parse_args()
    assert args.episodes > 0
    args.directory.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[2]
    classes = root / 'AutoData/submodules/IsaacLab-Arena/submodules/IsaacLab/source/isaaclab/isaaclab/utils/datasets'
    Episode, Handler = load_dataset_classes(classes)
    originals = []
    with h5py.File(args.source, 'r') as file:
        names = sorted(file['data'], key=lambda n: int(n.split('_')[-1]))[:args.episodes]
        env_args = json.loads(file['data'].attrs['env_args'])
        for name in names:
            ep = Episode()
            ep.success = bool(file[f'data/{name}'].attrs['success'])
            ep.seed = file[f'data/{name}'].attrs.get('seed')

            def read(group):
                return {k: read(v) if isinstance(v, h5py.Group) else list(torch.from_numpy(v[:]).unbind(0))
                        for k, v in group.items()}

            ep.data = read(file[f'data/{name}'])
            originals.append(ep)
    report = []
    for workers in (0, 1, 2):
        target = args.directory / f'workers-{workers}.hdf5'
        start = time.monotonic()
        events = []
        if workers:
            pool = ExportPool(target, workers=workers, emit=lambda event, **values: events.append(dict(event=event, **values)))
            try:
                for ep in originals:
                    attrs = dict(success=ep.success)
                    if ep.seed is not None:
                        attrs['seed'] = ep.seed
                    pool.submit(ep.data, attributes=attrs, env_args=env_args)
                submitted = time.monotonic()
                pool.finish()
            except BaseException as exc:
                pool.abort(str(exc))
                raise
        else:
            handler = Handler()
            handler.create(str(target), env_name=env_args['env_name'])
            handler.add_env_args(env_args)
            for ep in originals:
                copy = Episode()
                # Copy dict/list containers, retaining read-only frame tensors.
                def containers(value):
                    return {k: containers(v) for k, v in value.items()} if isinstance(value, dict) else list(value)
                copy.data = containers(ep.data)
                copy.success, copy.seed = ep.success, ep.seed
                copy.pre_export()
                handler.write_episode(copy)
                handler.flush()
            handler.close()
            submitted = time.monotonic()
        elapsed = time.monotonic() - start
        print(f'workers={workers} export complete in {elapsed:.3f}s; validating all values', flush=True)
        compare(args.source, target, names)
        reader = Handler()
        reader.open(str(target))
        assert reader.get_num_episodes() == len(names)
        loaded = reader.load_episode('demo_0', 'cpu')
        assert loaded.data['actions'].shape[1] == 7
        assert loaded.data['obs']['left_hand_rgb'].dtype == torch.uint8
        del loaded
        reader.close()
        row = dict(workers=workers, episodes=len(names), final_ready_seconds=elapsed,
                   submission_seconds=submitted - start, episodes_per_minute=len(names) * 60 / elapsed,
                   complete_value_and_schema_equality=True, events=events)
        report.append(row)
        print(json.dumps({k: v for k, v in row.items() if k != 'events'}), flush=True)
        (args.directory / 'report.json').write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
