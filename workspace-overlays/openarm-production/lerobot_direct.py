# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Direct recorder arrays -> official LeRobot v3 writer (no intermediate HDF5)."""
from __future__ import annotations

import inspect
import json
import os
import time
from pathlib import Path

import numpy as np


def flatten(data, prefix=''):
    result = {}
    for key, value in data.items():
        path = f'{prefix}/{key}' if prefix else key
        if isinstance(value, dict):
            result.update(flatten(value, path))
        else:
            def array(v):
                return v.detach().cpu().numpy() if hasattr(v, 'detach') else np.asarray(v)
            result[path] = np.stack([array(v) for v in value]) if isinstance(value, list) else array(value)
    return result


def schema(arrays, env):
    """Require recorded joint targets and verified pre-step joint state."""
    semantics = env['semantic_metadata']
    if semantics.get('schema_version') != 1:
        raise ValueError('Unsupported semantic schema')
    dt = semantics['control_dt']
    if not np.isfinite(dt) or dt <= 0:
        raise ValueError('Invalid control_dt')
    fps = round(1 / dt)
    if fps <= 0 or not np.isclose(fps, 1 / dt):
        raise ValueError('Integer FPS required')
    mapping = {'action': 'joint_actions', 'observation.state': 'obs/joint_pos_absolute',
               'source_action': 'actions', 'diagnostics.applied_joint_target': 'joint_applied_targets'}
    for path in arrays:
        if path.startswith('obs/') and path != 'obs/joint_pos_absolute':
            name = path[4:].replace('/', '.')
            if name.endswith('_rgb'):
                key = 'observation.images.' + name[:-4]
            else:
                key = 'observation.' + {'joint_pos': 'joint_pos_relative', 'actions': 'last_tcp_action'}.get(name, name)
            if key in mapping:
                raise ValueError(f'Feature collision: {key}')
            mapping[key] = path
        elif path.startswith('states/'):
            key = 'next.sim_state.' + path[7:].replace('/', '.')
            if key in mapping:
                raise ValueError(f'Feature collision: {key}')
            mapping[key] = path
    if 'processed_actions' in arrays:
        mapping['source_processed_action'] = 'processed_actions'
    length = len(arrays['actions'])
    if length == 0 or arrays['actions'].shape != (length, 7):
        raise ValueError('Expected nonempty 7-D source actions')
    features = {}
    for key, path in mapping.items():
        value = arrays[path]
        shape = value.shape[1:]
        if len(value) != length:
            raise ValueError(f'Frame count mismatch: {path}')
        if key.startswith('observation.images.'):
            if value.dtype != np.uint8 or len(shape) != 3 or shape[-1] != 3:
                raise ValueError(f'Expected uint8 HWC: {path}')
            features[key] = dict(dtype='video', shape=shape, names=['height', 'width', 'channels'])
        else:
            spec = semantics['fields'][path]
            names = spec['names']
            if (value.dtype != np.float32 or len(shape) != 1 or not np.isfinite(value).all()
                    or len(names) != shape[0] or len(set(names)) != len(names)
                    or any(not isinstance(n, str) or not n or n.startswith('column_') for n in names)
                    or len(spec['units']) != shape[0]):
                raise ValueError(f'Invalid numeric field or semantics: {path}')
            features[key] = dict(dtype='float32', shape=shape, names=names)
    names = features['action']['names']
    for path in ('joint_actions', 'obs/joint_pos_absolute', 'joint_applied_targets'):
        spec = semantics['fields'][path]
        if arrays[path].shape != (length, 9) or spec['names'] != names or spec['units'] != ['rad'] * 9:
            raise ValueError('Joint action/state/targets must share nine named radian dimensions')
    if (semantics['joint_control']['names'] != names
            or semantics['fields']['joint_actions']['representation'] != 'absolute_joint_position_target'):
        raise ValueError('Unverified joint commands')
    return length, fps, mapping, features


class DirectWriter:
    """One actor owns one dataset; never share LeRobot metadata between writers."""
    def __init__(self, output, repo_id, task, robot_type):
        self.output, self.repo_id = Path(output), repo_id
        self.task, self.robot_type = task, robot_type
        self.dataset = None
        self.signature = None
        self.records = []

    def write(self, arrays, env, attributes, key):
        started = time.monotonic()
        from lerobot.datasets.lerobot_dataset import LeRobotDataset
        if attributes.get('success') is not True:
            raise ValueError('Direct training export accepts successful episodes only')
        length, fps, mapping, features = schema(arrays, env)
        signature = json.dumps([fps, mapping, features, env['semantic_metadata']], sort_keys=True)
        if self.signature is not None and signature != self.signature:
            raise ValueError('Dataset schema changed between episodes')
        if self.dataset is None:
            params = inspect.signature(LeRobotDataset.create).parameters
            if 'vcodec' in params:
                encoding = dict(vcodec='h264')
            elif 'rgb_encoder' in params:
                from lerobot.configs.video import RGBEncoderConfig
                encoding = dict(rgb_encoder=RGBEncoderConfig(vcodec='h264'))
            else:
                raise RuntimeError('Unsupported LeRobot writer API')
            self.dataset = LeRobotDataset.create(repo_id=self.repo_id, root=self.output, fps=fps,
                features=features, robot_type=self.robot_type, use_videos=True,
                image_writer_threads=2, **encoding)
            self.signature = signature
        writer = self.dataset if hasattr(self.dataset, 'image_writer') else self.dataset.writer
        for index in range(length):
            self.dataset.add_frame({**{k: arrays[p][index].copy() for k, p in mapping.items()}, 'task': self.task})
            if index % 8 == 7:
                writer.image_writer.wait_until_done()
        writer.image_writer.wait_until_done()
        self.dataset.save_episode(parallel_encoding=False)
        self.records.append(dict(key=key, attributes=attributes, frames=length,
            initial_state={k: v.tolist() for k, v in arrays.items() if k.startswith('initial_state/')}))
        return dict(frames=length, shard=str(self.output), episode_index=len(self.records) - 1,
                    worker_pid=os.getpid(), write_seconds=time.monotonic() - started)

    def write_shared(self, job, env, attributes, key):
        """Read producer-owned pages on this host without serializing RGB via Ray."""
        from multiprocessing.shared_memory import SharedMemory
        from multiprocessing import resource_tracker
        memory = SharedMemory(name=job['memory'])
        # Ray workers have a separate Python 3.12 resource tracker. Only the
        # producer owns unlink; actor exit must not remove another job's pages.
        resource_tracker.unregister(memory._name, 'shared_memory')
        arrays = {leaf['path']: np.ndarray(leaf['shape'], dtype=leaf['dtype'],
                  buffer=memory.buf, offset=leaf['offset']) for leaf in job['leaves']}
        for value in arrays.values():
            value.flags.writeable = False
        del value
        try:
            return self.write(arrays, env, attributes, key)
        finally:
            arrays.clear()
            memory.close()

    def finish(self):
        if self.dataset is not None:
            writer = self.dataset if hasattr(self.dataset, 'image_writer') else self.dataset.writer
            writer.stop_image_writer()
            self.dataset.finalize()
            info = json.loads((self.output / 'meta/info.json').read_text())
            if info['codebase_version'] != 'v3.0':
                raise RuntimeError('Writer did not produce LeRobot v3.0')
            (self.output / 'production.json').write_text(json.dumps(dict(
                schema=json.loads(self.signature), episodes=self.records), indent=2) + '\n')
        return str(self.output)
