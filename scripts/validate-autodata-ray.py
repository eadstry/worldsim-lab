#!/usr/bin/env python3
"""Read back completed local Ray production shards, including every video frame."""
import argparse
import json
from pathlib import Path


def validate(root):
    import av
    import numpy as np
    import pyarrow.parquet as pq
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    result = json.loads((root / 'result.json').read_text())
    if result['status'] != 'succeeded':
        return {'case': root.name, 'status': 'not_complete'}
    shards = []
    for info_path in sorted(root.glob('process-*/episodes.lerobot/shard-*/meta/info.json')):
        shard = info_path.parent.parent
        info = json.loads(info_path.read_text())
        assert info['codebase_version'] == 'v3.0'
        assert info['fps'] == 30
        assert not list(shard.rglob('*.hdf5'))
        features = info['features']
        assert features['action']['shape'] == [9]
        assert features['action']['names'] == features['observation.state']['names']
        tables = [pq.read_table(p).to_pandas() for p in sorted((shard / 'data').rglob('*.parquet'))]
        import pandas as pd
        rows = pd.concat(tables, ignore_index=True)
        assert len(rows) == info['total_frames']
        for key, spec in features.items():
            if spec['dtype'] == 'float32':
                assert np.isfinite(np.stack(rows[key].to_numpy())).all(), key
        counts = {}
        for key, spec in features.items():
            if spec['dtype'] != 'video':
                continue
            count = 0
            for path in sorted((shard / 'videos' / key).rglob('*.mp4')):
                with av.open(str(path)) as video:
                    assert float(video.streams.video[0].average_rate) == info['fps']
                    for frame in video.decode(video=0):
                        assert [frame.height, frame.width, 3] == spec['shape']
                        count += 1
            assert count == len(rows), (key, count, len(rows))
            counts[key] = count
        dataset = LeRobotDataset('local/production-validation', root=shard, video_backend='torchcodec')
        checked = []
        for _, episode in rows.groupby('episode_index', sort=True):
            for index in sorted(set([int(episode.index[0]), int(episode.index[len(episode)//2]), int(episode.index[-1])])):
                actual = dataset[index]
                for key in ('action', 'observation.state'):
                    np.testing.assert_array_equal(actual[key].numpy(), rows.iloc[index][key])
                for key in counts:
                    assert tuple(actual[key].shape) == (3, 480, 640)
                    assert np.isfinite(actual[key].numpy()).all()
                checked.append(index)
        shards.append({'shard': str(shard), 'episodes': info['total_episodes'],
                       'frames': len(rows), 'decoded_video_frames': counts, 'official_loader_indices': checked})
    assert sum(s['frames'] for s in shards) == result['frames']
    assert sum(s['episodes'] for s in shards) == result['episodes']
    return {'case': root.name, 'status': 'passed', 'shards': shards}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cases', type=Path, nargs='+')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    results = []
    for case in args.cases:
        try:
            row = validate(case)
        except Exception as exc:
            row = {'case': case.name, 'status': 'failed', 'error': repr(exc)}
        results.append(row)
        print(json.dumps({k: v for k, v in row.items() if k != 'shards'}), flush=True)
        args.output.write_text(json.dumps(results, indent=2) + '\n')
    raise SystemExit(any(row['status'] == 'failed' for row in results))
