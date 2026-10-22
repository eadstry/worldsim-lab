# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Bounded local Ray actors exporting independent official LeRobot v3 datasets."""
from __future__ import annotations

import importlib.util
import json
import os
import time
from pathlib import Path

from lerobot_direct import DirectWriter, schema
from export_pool import layout, pack
from export_resources import check_export_capacity
from multiprocessing.shared_memory import SharedMemory
import numpy as np


def preflight():
    missing = [name for name in ('ray', 'lerobot') if importlib.util.find_spec(name) is None]
    if missing:
        raise RuntimeError('Missing direct-export dependencies: ' + ', '.join(missing)
                           + '; provision a compatible environment explicitly before running')


class RayLeRobotPool:
    def __init__(self, output, workers, memory_bytes, timeout, emit=None, task='', robot_type='openarm'):
        preflight()
        import ray
        if not isinstance(workers, int) or workers <= 0:
            raise ValueError('Ray requires an explicit positive --export-workers cap')
        if ray.is_initialized():
            raise RuntimeError('Direct export owns a local Ray instance; existing sessions are unsupported')
        self.ray, self.timeout, self.limit = ray, timeout, memory_bytes
        self.output = Path(output).with_suffix('.lerobot')
        self.output.mkdir(parents=True, exist_ok=False)
        self.entries, self.pending, self.actors = {}, {}, []
        self.closed, self.used, self.next_id = False, 0, 0
        self.worker_pids = set()
        self.memories = {}
        self.emit = emit or (lambda *a, **kw: None)
        self.started = time.monotonic()
        try:
            ray.init(address='local', include_dashboard=False, num_cpus=workers, num_gpus=0,
                     object_store_memory=80 * 1024**2)
            actor = ray.remote(num_cpus=1, num_gpus=0, max_restarts=0, max_task_retries=0)(DirectWriter)
            runtime_env = {'env_vars': {'PYTHONPATH': str(Path(__file__).parent) + os.pathsep + os.environ.get('PYTHONPATH', '')}}
            self.actors = [actor.options(runtime_env=runtime_env).remote(str(self.output / f'shard-{i:04d}'),
                f'local/shard-{i:04d}', task, robot_type) for i in range(workers)]
            self._manifest('running')
            self.emit('export_pool_started', worker_pids=[], max_workers=workers, scaling_policy='ray_fixed')
        except BaseException:
            ray.shutdown()
            raise

    def _manifest(self, status, **extra):
        path = self.output / 'manifest.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(dict(status=status, format='lerobot-v3-shards',
            entries=list(self.entries.values()), elapsed_seconds=time.monotonic() - self.started,
            **extra), indent=2) + '\n')
        temporary.replace(path)

    def poll(self, wait=0):
        if self.closed:
            raise RuntimeError('Pool is closed')
        if self.pending:
            ready, _ = self.ray.wait(list(self.pending), num_returns=1, timeout=wait)
            for ref in ready:
                key, size, _, actor_index = self.pending.pop(ref)
                result = self.ray.get(ref)
                memory = self.memories.pop(key)
                memory.close()
                memory.unlink()
                self.used -= size
                self.entries[key].update(status='saved', **result)
                pid = result.get('worker_pid')
                if pid is not None and pid not in self.worker_pids:
                    self.worker_pids.add(pid)
                    self.emit('export_worker_started', worker_pid=pid)
                self.emit('export_saved', key=key, **result)
                self._manifest('running')
            if any(time.monotonic() - start > self.timeout for _, _, start, _ in self.pending.values()):
                raise TimeoutError('Ray export exceeded timeout')

    def submit(self, data, output=None, env_args=None, attributes=None, env_id=None, **kwargs):
        # Validate before dispatch, so bad episodes never enter a writer's dataset.
        self.poll()
        if attributes.get('success') is not True:
            raise ValueError('LeRobot direct export requires successful-only recorder mode')
        # Accept either nested recorder data or flat fixture arrays, without copies.
        nested = {}
        for path, value in data.items():
            node = nested
            parts = path.split('/')
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = value
        leaves, size = layout(nested)
        if size > self.limit:
            raise ValueError(f'Episode bytes {size} exceeds export budget {self.limit}')
        waiting_start = time.monotonic()
        while self.used + size > self.limit or len(self.pending) >= len(self.actors):
            self.poll(.05)
        waited = time.monotonic() - waiting_start
        busy = {row[3] for row in self.pending.values()}
        actor_index = next(i for i in range(len(self.actors)) if i not in busy)
        key = str(self.next_id)
        self.next_id += 1
        check_export_capacity(size)
        memory = SharedMemory(create=True, size=size)
        try:
            packing_start = time.monotonic()
            pack(nested, leaves, memory, release_source=kwargs.get('release_source', False))
            arrays = {leaf['path']: np.ndarray(leaf['shape'], dtype=leaf['dtype'],
                      buffer=memory.buf, offset=leaf['offset']) for leaf in leaves}
            try:
                schema(arrays, env_args)
            finally:
                arrays.clear()
            packed = time.monotonic() - packing_start
            job = dict(memory=memory.name, leaves=leaves)
            ref = self.actors[actor_index].write_shared.remote(job, env_args, attributes, key)
        except BaseException:
            memory.close()
            memory.unlink()
            raise
        self.memories[key] = memory
        self.pending[ref] = (key, size, time.monotonic(), actor_index)
        self.used += size
        self.entries[key] = dict(key=key, status='submitted', attributes=attributes, env_id=env_id,
                                 source_demo_id=kwargs.get('demo_id'))
        self._manifest('running')
        self.emit('export_submitted', packing_seconds=packed,
                  queue_wait_seconds=waited, queue_memory_bytes=self.used)
        return int(key)

    def finish(self):
        try:
            while self.pending:
                self.poll(.05)
            self.ray.get([actor.finish.remote() for actor in self.actors], timeout=self.timeout)
            frames = sum(e['frames'] for e in self.entries.values())
            self._manifest('complete', frames=frames,
                episodes_per_second=len(self.entries) / (time.monotonic() - self.started))
            self.emit('export_complete', saved_episodes=len(self.entries),
                      final_ready_seconds=time.monotonic() - self.started)
            self.closed = True
            self.ray.shutdown()
        except BaseException as exc:
            self.abort(str(exc))
            raise

    def abort(self, reason):
        if self.closed:
            return
        for actor in self.actors:
            self.ray.kill(actor, no_restart=True)
        self.ray.shutdown()
        for memory in self.memories.values():
            memory.close()
            memory.unlink()
        self.memories.clear()
        self.used = 0
        self.closed = True
        self._manifest('failed', error=reason)
