# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Full real-episode destructive handoff verification without simulation imports."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main():
    import h5py
    from benchmark_pool import compare
    from export_pool import ExportPool
    from replay_export import load_dataset_classes

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--demo', default='demo_0')
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    run = args.source.with_suffix('.run.json')
    if run.exists():
        assert json.loads(run.read_text()).get('ended_at'), 'Wait for production to finish'
    args.directory.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[2]
    _, Handler = load_dataset_classes(root / 'AutoData/submodules/IsaacLab-Arena/submodules/IsaacLab/source/isaaclab/isaaclab/utils/datasets')
    reader = Handler()
    reader.open(str(args.source.resolve()))
    episode = reader.load_episode(args.demo, 'cpu')
    version = reader.get_format_version()
    reader.close()

    def frames(value):
        return {k: frames(v) for k, v in value.items()} if isinstance(value, dict) else list(value.unbind(0))

    episode.data = frames(episode.data)
    with h5py.File(args.source, 'r') as original:
        env_args = json.loads(original['data'].attrs['env_args'])
        attrs = dict(original[f'data/{args.demo}'].attrs)
    output = args.directory.resolve() / 'episode.hdf5'
    pool = ExportPool(output, workers=2)
    try:
        pool.submit(episode.data, attributes=attrs, env_args=env_args,
                    format_version=version, release_source=True)
        pool.finish()
    except BaseException as exc:
        pool.abort(str(exc))
        raise
    compare(args.source, output, [args.demo])
    reader = Handler()
    reader.open(str(output))
    assert reader.get_num_episodes() == 1
    restored = reader.load_episode('demo_0', 'cpu')
    assert restored.data['actions'].shape[1] == 7
    reader.close()
    digest = hashlib.sha256()
    with output.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024**2), b''):
            digest.update(block)
    report = dict(source=str(args.source.resolve()), demo=args.demo, output=str(output),
                  complete_value_and_schema_equality=True, existing_loader_passed=True,
                  independent_file_verified_after_shard_removal=not pool.directory.exists(),
                  sha256=digest.hexdigest(), scope='CPU replay of real saved data, not GPU simulation')
    (args.directory / 'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
