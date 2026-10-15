# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Host-only spawn, transport, ordering, schema and failure tests."""
import json
import os
import tempfile
import time
import unittest
from multiprocessing.shared_memory import SharedMemory
from pathlib import Path

import h5py
import numpy as np

from export_pool import ExportPool, layout


def delayed_writer(jobs, results, directory, parent):
    import export_pool
    original = export_pool.write_job

    def delayed(job, handles, directory):
        if job['demo_id'] == 0:
            time.sleep(.4)
        return original(job, handles, directory)

    export_pool.write_job = delayed
    export_pool.writer(jobs, results, directory, parent)


def dead_writer(*args):
    os._exit(7)


def stuck_writer(jobs, results, directory, parent):
    job = jobs.get()
    results.put(dict(kind='started', key=job['key']))
    time.sleep(10)


def bad_writer(jobs, results, directory, parent):
    job = jobs.get()
    results.put(dict(kind='failed', key=job['key'], error='simulated disk error'))
    time.sleep(10)


def gated_writer(jobs, results, directory, parent):
    import export_pool
    original = export_pool.write_job

    def gated(job, handles, directory):
        deadline = time.monotonic() + 10
        while not (Path(directory) / 'release-writers').exists():
            if time.monotonic() >= deadline:
                raise TimeoutError('Test did not release writers')
            time.sleep(.01)
        return original(job, handles, directory)

    export_pool.write_job = gated
    export_pool.writer(jobs, results, directory, parent)


def episode(index):
    return dict(actions=[np.full(7, index + step, np.float32) for step in range(4)],
                initial_state=dict(pose=[np.arange(7, dtype=np.float32)], empty={}),
                obs=dict(rgb=[np.full((16, 16, 3), index + step, np.uint8) for step in range(4)],
                         signal=[np.asarray(step, dtype=np.int64) for step in range(4)]),
                states=dict(pose=[np.arange(7, dtype=np.float32) for _ in range(4)]))


class PoolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.output = Path(self.temp.name) / 'result.hdf5'
        self.pools = []

    def tearDown(self):
        for pool in self.pools:
            pool.abort('test cleanup')
        self.temp.cleanup()

    def pool(self, **kwargs):
        pool = ExportPool(self.output, memory_bytes=1024**2, **kwargs)
        self.pools.append(pool)
        return pool

    def test_lazy_workers_grow_with_backlog_and_stop_at_cap(self):
        from monitor import summarize
        events = []
        pool = self.pool(workers=2, worker_target=gated_writer,
                         emit=lambda event, **kw: events.append(dict(event=event, **kw)))
        self.assertEqual(pool.processes, [])
        for index, expected_workers in enumerate((1, 2, 2, 2)):
            pool.submit(episode(index))
            self.assertEqual(len(pool.processes), expected_workers)
        state = json.loads(pool.manifest.read_text())
        self.assertEqual(state['max_workers'], 2)
        self.assertEqual(len(state['worker_pids']), 2)
        pool.directory.joinpath('release-writers').touch()
        pool.finish()
        summary = summarize(events)['async_export']
        self.assertEqual(summary['workers_started'], 2)
        self.assertEqual(summary['max_workers'], 2)
        self.assertEqual(summary['saved'], 4)
        with h5py.File(self.output) as file:
            self.assertEqual(len(file['data']), 4)
            for index in range(4):
                np.testing.assert_array_equal(file[f'data/demo_{index}/obs/rgb'][:],
                                              np.stack(episode(index)['obs']['rgb']))

    def test_auto_workers_pause_and_resume_without_a_new_submission(self):
        from types import SimpleNamespace
        from monitor import summarize
        events = []
        governor = SimpleNamespace(decide=lambda *a: dict(allow=False, reason='memory_reserve'))
        pool = self.pool(workers='auto', worker_target=gated_writer, resource_governor=governor,
                         emit=lambda event, **kw: events.append(dict(event=event, **kw)))
        for index in range(4):
            pool.submit(episode(index))
        self.assertFalse(pool.processes)
        self.assertEqual(pool.admission['reason'], 'memory_reserve')
        governor.decide = lambda *a: dict(allow=True, reason='available')
        for count in range(1, 5):
            pool.poll()
            self.assertEqual(len(pool.processes), count)
        self.assertIsNone(pool.max_workers)
        self.assertEqual(json.loads(pool.manifest.read_text())['scaling_policy'], 'server_resources')
        pool.directory.joinpath('release-writers').touch()
        pool.finish()
        summary = summarize(events)['async_export']
        self.assertEqual(summary['workers_started'], 4)
        self.assertIsNone(summary['max_workers'])
        self.assertEqual(summary['saved'], 4)
        with h5py.File(self.output) as file:
            self.assertEqual(len(file['data']), 4)

    def test_auto_pressure_stops_growth_but_existing_writer_drains_queue(self):
        from types import SimpleNamespace
        governor = SimpleNamespace(decide=lambda *a: dict(allow=True, reason='available'))
        pool = self.pool(workers='auto', worker_target=gated_writer, resource_governor=governor)
        pool.submit(episode(0))
        governor.decide = lambda *a: dict(allow=False, reason='cpu_busy')
        pool.submit(episode(1))
        self.assertEqual(len(pool.processes), 1)
        pool.directory.joinpath('release-writers').touch()
        pool.finish()
        self.assertEqual(len(pool.processes), 1)
        with h5py.File(self.output) as file:
            self.assertEqual(len(file['data']), 2)

    def test_auto_unavailable_resources_timeout_releases_pending_memory(self):
        from types import SimpleNamespace
        governor = SimpleNamespace(decide=lambda *a: dict(allow=False, reason='resources_unavailable'))
        pool = self.pool(workers='auto', resource_governor=governor, timeout=.05)
        pool.submit(episode(0))
        name = next(iter(pool.memories.values())).name
        with self.assertRaisesRegex(TimeoutError, 'resources_unavailable'):
            pool.finish()
        self.assertTrue(pool.closed)
        self.assertFalse(self.output.exists())
        with self.assertRaises(FileNotFoundError):
            SharedMemory(name=name)

    def test_idle_worker_is_reused_without_spawning(self):
        pool = self.pool(workers=3)
        pool.submit(episode(0))
        deadline = time.monotonic() + 10
        while pool.pending and time.monotonic() < deadline:
            pool.poll(wait=.05)
        self.assertFalse(pool.pending)
        self.assertEqual(len(pool.processes), 1)
        pid = pool.processes[0].pid
        pool.submit(episode(1))
        self.assertEqual([p.pid for p in pool.processes], [pid])
        pool.finish()
        self.assertEqual(len(pool.entries), 2)

    def test_empty_pool_finishes_without_spawning(self):
        pool = self.pool(workers=3)
        self.assertEqual(pool.processes, [])
        pool.finish()
        self.assertTrue(pool.closed)
        self.assertFalse(self.output.exists())
        self.assertEqual(json.loads(pool.manifest.read_text())['status'], 'complete')

    def test_late_worker_start_failure_cleans_existing_workers_and_memory(self):
        from unittest.mock import patch
        pool = self.pool(workers=2, worker_target=gated_writer)
        pool.submit(episode(0))
        names = [e['memory'] for e in pool.entries.values()]
        with patch.object(pool.context, 'Process', side_effect=RuntimeError('simulated spawn failure')):
            with self.assertRaisesRegex(RuntimeError, 'simulated spawn failure'):
                pool.submit(episode(1))
        names += [e['memory'] for e in pool.entries.values()]
        self.assertTrue(pool.closed)
        self.assertFalse(pool.memories)
        self.assertTrue(all(not p.is_alive() for p in pool.processes))
        for name in names:
            with self.assertRaises(FileNotFoundError):
                SharedMemory(name=name)
        self.assertEqual(json.loads(pool.manifest.read_text())['status'], 'failed')

    def test_reordered_workers_preserve_values_metadata_and_self_containment(self):
        events = []
        pool = self.pool(workers=2, worker_target=delayed_writer,
                         emit=lambda event, **kw: events.append((event, kw)))
        originals = []
        for index in range(4):
            data = episode(index)
            originals.append(data)
            pool.submit(data, env_args=dict(env_name='test', type=2),
                        attributes=dict(success=True, seed=index), env_id=index % 2)
            data['actions'][0][:] = -99  # Producer reuse must not modify the queued episode.
        memory_names = [e['memory'] for e in pool.entries.values()]
        pool.finish()
        saved = [row['demo_id'] for event, row in events if event == 'export_saved']
        self.assertNotEqual(saved, sorted(saved))
        self.assertFalse(pool.directory.exists())
        for name in memory_names:
            with self.assertRaises(FileNotFoundError):
                SharedMemory(name=name)
        with h5py.File(self.output) as file:
            self.assertEqual(file.attrs['format_version'], 1)
            self.assertEqual(file['data'].attrs['total'], 16)
            self.assertEqual(json.loads(file['data'].attrs['env_args']), dict(env_name='test', type=2))
            for index in range(4):
                group = file[f'data/demo_{index}']
                self.assertEqual(dict(group.attrs), dict(success=True, seed=index, num_samples=4))
                self.assertEqual(list(group['initial_state/empty']), [])
                self.assertIsInstance(file['data'].get(f'demo_{index}', getlink=True), h5py.HardLink)
                for leaf in layout(episode(index))[0]:
                    value = episode(index)
                    for key in leaf['path'].split('/'):
                        value = value[key]
                    expected = np.stack(value)
                    actual = group[leaf['path']]
                    np.testing.assert_array_equal(expected, actual[:])
                    self.assertEqual(actual.dtype, expected.dtype)
                    self.assertEqual(actual.compression, 'gzip')
                    self.assertEqual(actual.compression_opts, 2)

    def test_budget_includes_writing_and_backpressure(self):
        size = layout(episode(0))[1]
        pool = ExportPool(self.output, workers=1, memory_bytes=size, worker_target=delayed_writer)
        self.pools.append(pool)
        pool.submit(episode(0))
        pool.submit(episode(1))
        pool.finish()
        self.assertEqual(pool.peak, size)
        self.assertGreater(pool.wait_seconds, .2)

    def test_oversize_and_duplicate_rejected(self):
        pool = self.pool(workers=1)
        with self.assertRaisesRegex(AssertionError, 'exceeding'):
            pool.submit(dict(actions=np.zeros((1024, 1024), np.float32)))
        pool.submit(episode(0), demo_id=7)
        with self.assertRaisesRegex(AssertionError, 'Duplicate'):
            pool.submit(episode(1), demo_id=7)
        pool.finish()
        with h5py.File(self.output) as file:
            self.assertEqual(list(file['data']), ['demo_7'])

    def test_worker_failure_timeout_and_abort(self):
        for target, error in ((dead_writer, RuntimeError), (stuck_writer, TimeoutError), (bad_writer, RuntimeError)):
            with self.subTest(target=target.__name__):
                self.output = Path(self.temp.name) / f'{target.__name__}.hdf5'
                pool = self.pool(workers=1, worker_target=target, timeout=1)
                try:
                    pool.submit(episode(0))
                    with self.assertRaises(error):
                        pool.finish()
                except RuntimeError:
                    # A dead worker may be discovered before submit.
                    self.assertIs(target, dead_writer)
                    pool.abort('dead before submit')
                self.assertFalse(self.output.exists())
                self.assertFalse(pool.memories)
                self.assertTrue(all(not p.is_alive() for p in pool.processes))
                self.assertEqual(json.loads(pool.manifest.read_text())['status'], 'failed')

    def test_multiple_routes_and_uncompressed(self):
        pool = self.pool(workers=2)
        failed = self.output.with_name('failed.hdf5')
        pool.submit(episode(0), attributes=dict(success=True), compression=False)
        pool.submit(episode(1), output=failed, attributes=dict(success=False))
        pool.finish()
        with h5py.File(self.output) as file, h5py.File(failed) as other:
            self.assertIsNone(file['data/demo_0/actions'].compression)
            self.assertFalse(other['data/demo_0'].attrs['success'])

    def test_cpu_capture_has_per_environment_storage(self):
        import ast
        import __future__
        import torch
        from collections.abc import Sequence
        from types import MethodType, SimpleNamespace
        from async_export import owned_recording_method
        from replay_export import load_dataset_classes
        root = Path(__file__).resolve().parents[2]
        source_root = root / 'AutoData/submodules/IsaacLab-Arena/submodules/IsaacLab/source/isaaclab/isaaclab'
        Episode, _ = load_dataset_classes(source_root / 'utils/datasets')
        path = source_root / 'managers/recorder_manager.py'
        tree = ast.parse(path.read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'RecorderManager')
        node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'add_to_episodes')
        namespace = dict(torch=torch, EpisodeData=Episode, Sequence=Sequence,
                         wp=SimpleNamespace(array=type('DummyWarp', (), {})))
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec',
                     flags=__future__.annotations.compiler_flag), namespace)
        method = owned_recording_method(namespace['add_to_episodes'])
        recorder = SimpleNamespace(active_terms=['record'], _env=SimpleNamespace(num_envs=2),
                                   _episodes={0: Episode(), 1: Episode()})
        recorder.add_to_episodes = MethodType(method, recorder)
        batch = torch.arange(120, dtype=torch.float32).reshape(2, 4, 5, 3)
        recorder.add_to_episodes('obs/rgb', batch)
        for env in range(2):
            frame = recorder._episodes[env].data['obs']['rgb'][0]
            self.assertEqual(frame.untyped_storage().nbytes(), frame.numel() * frame.element_size())
            torch.testing.assert_close(frame, batch[env])
        batch.zero_()
        self.assertGreater(recorder._episodes[1].data['obs']['rgb'][0].sum(), 0)

    def test_destructive_handoff_releases_frames_and_preserves_output(self):
        pool = self.pool(workers=1)
        data = episode(3)
        pool.submit(data, release_source=True)
        self.assertEqual(data['obs']['rgb'], [])
        self.assertEqual(data['actions'], [])
        pool.finish()
        with h5py.File(self.output) as file:
            np.testing.assert_array_equal(file['data/demo_0/obs/rgb'][:], np.stack(episode(3)['obs']['rgb']))

    def test_bridge_success_filter_and_buffer_detach(self):
        from enum import IntEnum
        from types import SimpleNamespace
        from async_export import Bridge, MetadataHandler
        class Modes(IntEnum):
            EXPORT_ALL = 1
            EXPORT_SUCCEEDED_ONLY = 2
            EXPORT_SUCCEEDED_FAILED_IN_SEPARATE_FILES = 3
        class Episode:
            def __init__(self, success=None):
                self.data = episode(2) if success is not None else {}
                self.success, self.seed = success, None
            def is_empty(self):
                return not self.data
        handler = MetadataHandler()
        handler.create(str(self.output), 'test')
        recorder = SimpleNamespace(active_terms=['record'], _env=SimpleNamespace(num_envs=2),
            cfg=SimpleNamespace(dataset_export_mode=Modes.EXPORT_SUCCEEDED_ONLY, dataset_compression=True),
            _episodes={0: Episode(True), 1: Episode(False)}, _dataset_file_handler=handler,
            _failed_episode_dataset_file_handler=None, get_ep_meta=lambda: dict(sim_args=dict(num_envs=2)),
            _exported_successful_episode_count={}, _exported_failed_episode_count={})
        bridge = Bridge.__new__(Bridge)
        bridge.recorder, bridge.mode_class, bridge.episode_class = recorder, Modes, Episode
        bridge.format_version = 1
        bridge.pool, bridge.saved_seen = self.pool(workers=1), set()
        bridge.export()
        self.assertEqual(len(bridge.pool.entries), 1)
        self.assertTrue(all(e.is_empty() for e in recorder._episodes.values()))
        bridge.pool.finish()
        bridge.update_counters()
        self.assertEqual(recorder._exported_successful_episode_count, {0: 1})
        with h5py.File(self.output) as file:
            self.assertEqual(json.loads(file['data'].attrs['env_args'])['env_name'], 'test')

    def test_launcher_hooks_compile_for_sync_and_spawn_modes(self):
        from types import SimpleNamespace
        from generate import build_source
        root = Path(__file__).resolve().parents[2]
        source = (root / 'AutoData/scripts/generate_dataset.py').read_text()
        for workers in (0, 1, 2, 'auto'):
            args = SimpleNamespace(debug_planner=False, final_hold_steps=60,
                                   generation_num_trials=24, num_envs=8, export_workers=workers,
                                   output_file=self.output, export_queue_memory_gib=16,
                                   export_timeout_seconds=600)
            patched = build_source(source, args)
            compile(patched, '<patched-generate>', 'exec')
            self.assertEqual('configure(env_cfg)' in patched, bool(workers))
            self.assertEqual('        finish(expected_successes=' in patched, bool(workers))
        os.environ.pop('OPENARM_ASYNC_EXPORT', None)

    def test_abort_releases_pending_memory(self):
        pool = self.pool(workers=1, worker_target=stuck_writer)
        pool.submit(episode(0))
        names = [e['memory'] for e in pool.entries.values()]
        pool.abort('interrupted')
        for name in names:
            with self.assertRaises(FileNotFoundError):
                SharedMemory(name=name)
        self.assertTrue(pool.directory.exists())
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
