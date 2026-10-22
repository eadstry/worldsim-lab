# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Real Ray -> official LeRobot integration, using tiny CPU fixtures."""
import argparse
import json
from pathlib import Path
from ray_lerobot_pool import RayLeRobotPool
from test_lerobot_direct import fixture

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    pool = RayLeRobotPool(args.output / 'episodes.hdf5', 2, 128 * 1024**2, 120, task='test', robot_type='openarm')
    try:
        for i in range(4):
            arrays, env = fixture()
            pool.submit(arrays, env_args=env, attributes={'success': True}, env_id=i)
        pool.finish()
        from lerobot.datasets.lerobot_dataset import LeRobotDataset
        for shard in sorted({e['shard'] for e in pool.entries.values()}):
            ds = LeRobotDataset('local/' + Path(shard).name, root=Path(shard), video_backend='torchcodec')
            assert len(ds) > 0
            for i in range(len(ds)):
                assert (ds[i]['action'].numpy() == 42).all()
        print(json.dumps(dict(status='passed', episodes=len(pool.entries), entries=pool.entries)))
    finally:
        pool.abort('smoke cleanup')
