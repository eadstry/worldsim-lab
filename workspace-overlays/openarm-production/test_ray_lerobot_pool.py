# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Deterministic scheduler tests; these do not claim real Ray/LeRobot execution."""
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ray_lerobot_pool import RayLeRobotPool
from test_lerobot_direct import fixture


class FakeRay:
    def __init__(self):
        self.calls, self.killed, self.actors = {}, [], []
        self.closed = False
    def is_initialized(self): return False
    def init(self, **kwargs): pass
    def shutdown(self): self.closed = True
    def remote(self, **options):
        self.options = options
        return lambda cls: self
    def options(self, **kwargs): return self
    def remote_actor(self, *args):
        actor = SimpleNamespace(write_shared=SimpleNamespace(remote=self.write), finish=SimpleNamespace(remote=lambda: 'finish'))
        self.actors.append(actor)
        return actor
    def write(self, arrays, env, attrs, key):
        ref = 'ref-' + key
        self.calls[ref] = dict(frames=3, shard='shard', episode_index=int(key), write_seconds=0.01)
        return ref
    def wait(self, refs, **kwargs): return refs[:1], refs[1:]
    def get(self, ref, **kwargs):
        return None if isinstance(ref, list) else self.calls[ref]
    def kill(self, actor, **kwargs): self.killed.append(actor)


class PoolTests(unittest.TestCase):
    def pool(self, folder, workers=2):
        ray = FakeRay()
        factory = SimpleNamespace(options=lambda **kwargs: SimpleNamespace(remote=ray.remote_actor))
        ray.remote = lambda **kwargs: lambda cls: factory
        with patch('ray_lerobot_pool.preflight'), patch.dict('sys.modules', {'ray': ray}):
            pool = RayLeRobotPool(Path(folder) / 'out.hdf5', workers, 1000000, 10)
        return pool, ray

    def test_acknowledgements_and_finalize(self):
        with tempfile.TemporaryDirectory() as folder:
            pool, ray = self.pool(folder)
            arrays, env = fixture()
            for i in range(4):
                pool.submit(arrays, env_args=env, attributes={'success': True}, env_id=i)
                self.assertLessEqual(len(pool.pending), 2)
            pool.finish()
            self.assertEqual(len(pool.entries), 4)
            self.assertTrue(all(e['status'] == 'saved' for e in pool.entries.values()))
            self.assertEqual(pool.used, 0)
            self.assertTrue(ray.closed)
            with self.assertRaises(FileExistsError): self.pool(folder)

    def test_shared_pages_live_until_ack_and_source_frames_are_released(self):
        from multiprocessing.shared_memory import SharedMemory
        with tempfile.TemporaryDirectory() as folder:
            pool, ray = self.pool(folder)
            arrays, env = fixture()
            data = {key: [frame.copy() for frame in value] for key, value in arrays.items()}
            pool.submit(data, env_args=env, attributes={'success': True}, release_source=True)
            self.assertTrue(all(value == [] for value in data.values()))
            memory_name = pool.memories['0'].name
            handle = SharedMemory(name=memory_name)
            handle.close()
            pool.finish()
            with self.assertRaises(FileNotFoundError): SharedMemory(name=memory_name)

    def test_timeout_and_failed_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            pool, ray = self.pool(folder)
            arrays, env = fixture()
            pool.submit(arrays, env_args=env, attributes={'success': True})
            ray.wait = lambda *a, **kw: ([], [])
            ref = next(iter(pool.pending))
            key, size, _, actor = pool.pending[ref]
            pool.pending[ref] = key, size, time.monotonic() - 20, actor
            with self.assertRaises(TimeoutError): pool.poll()
            pool.abort('timeout')
            self.assertEqual(len(ray.killed), 2)
            self.assertIn('failed', (pool.output / 'manifest.json').read_text())

    def test_oversize_and_unsuccessful_never_dispatched(self):
        with tempfile.TemporaryDirectory() as folder:
            pool, ray = self.pool(folder)
            arrays, env = fixture()
            with self.assertRaises(ValueError): pool.submit(arrays, env_args=env, attributes={'success': False})
            pool.limit = 1
            with self.assertRaises(ValueError): pool.submit(arrays, env_args=env, attributes={'success': True})
            self.assertFalse(ray.calls)
            pool.abort('test cleanup')


if __name__ == '__main__': unittest.main()
