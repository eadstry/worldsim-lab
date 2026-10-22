# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Recorder bridge installed only when --export-workers is positive."""
from __future__ import annotations

import atexit
from pathlib import Path
from types import MethodType

from export_pool import ExportPool

_active = None


class MetadataHandler:
    """Recorder-compatible metadata sink; workers own actual HDF5 handles."""
    def __init__(self):
        self.path = None
        self._env_args = {}
        self._demo_count = 0

    def create(self, file_path, env_name=None):
        self.path = Path(file_path if file_path.endswith('.hdf5') else file_path + '.hdf5')
        self.add_env_args(dict(env_name=env_name or '', type=2))

    def add_env_args(self, values):
        self._env_args.update(values)

    def close(self):
        pass

    @property
    def demo_count(self):
        return self._demo_count


def owned_recording_method(original):
    """Preserve values while avoiding CPU frames that retain other environments."""
    import inspect
    import textwrap
    if getattr(original, '_openarm_cpu_owned', False):
        return original
    source = textwrap.dedent(inspect.getsource(original))
    anchor = '    value = value.clone()  # Clone once for all envs'
    add = 'self._episodes[env_id].add(key, value[value_index], clone=False)'
    assert source.count(anchor) == 1 and source.count(add) == 1
    source = source.replace(anchor, """    cpu_owned = value.device.type == 'cpu'
    if not cpu_owned:
        value = value.clone()""", 1)
    source = source.replace(add, 'self._episodes[env_id].add(key, value[value_index], clone=cpu_owned)', 1)
    namespace = dict(original.__globals__)
    exec(compile(source, inspect.getsourcefile(original), 'exec'), namespace)
    method = namespace['add_to_episodes']
    method._openarm_cpu_owned = True
    return method


def configure(env_cfg):
    from isaaclab.managers.recorder_manager import RecorderManager
    RecorderManager.add_to_episodes = owned_recording_method(RecorderManager.add_to_episodes)
    env_cfg.recorders.dataset_file_handler_class_type = MetadataHandler


def emit(event, **values):
    from telemetry import _active as telemetry
    if telemetry is not None:
        telemetry.emit(event, **values)


def attach(recorder, settings):
    global _active
    _active = Bridge(recorder, settings)
    atexit.register(abort, 'Process exited before async export completed')


class Bridge:
    def __init__(self, recorder, settings):
        from isaaclab.managers.recorder_manager import DatasetExportMode
        from isaaclab.utils.datasets import EpisodeData
        from isaaclab.utils.datasets.hdf5_dataset_file_handler import DATASET_FORMAT_VERSION
        self.recorder = recorder
        self.mode_class = DatasetExportMode
        self.episode_class = EpisodeData
        self.format_version = DATASET_FORMAT_VERSION
        pool_class, extra = ExportPool, {}
        if settings.get('format') == 'lerobot-v3':
            from ray_lerobot_pool import RayLeRobotPool
            if recorder.cfg.dataset_export_mode != DatasetExportMode.EXPORT_SUCCEEDED_ONLY:
                raise ValueError('Direct LeRobot export requires EXPORT_SUCCEEDED_ONLY')
            pool_class = RayLeRobotPool
            extra = dict(task=settings['task'], robot_type=settings['robot_type'])
        self.pool = pool_class(settings['output'], workers=settings['workers'],
                              memory_bytes=int(settings['memory_gib'] * 1024**3),
                              timeout=settings['timeout'], emit=emit, **extra)
        recorder.export_episodes = MethodType(lambda instance, *a, **k: self.export(*a, **k), recorder)
        self.saved_seen = set()

    def poll(self):
        self.pool.poll()
        self.update_counters()

    def update_counters(self):
        for key, entry in self.pool.entries.items():
            if entry['status'] != 'saved' or key in self.saved_seen:
                continue
            self.saved_seen.add(key)
            counters = (self.recorder._exported_successful_episode_count if entry['attributes'].get('success')
                        else self.recorder._exported_failed_episode_count)
            env_id = entry['env_id']
            counters[env_id] = counters.get(env_id, 0) + 1

    def export(self, env_ids=None, demo_ids=None):
        recorder, modes = self.recorder, self.mode_class
        self.poll()
        if not recorder.active_terms:
            return
        env_ids = list(range(recorder._env.num_envs)) if env_ids is None else list(map(int, env_ids))
        if demo_ids is not None:
            demo_ids = list(map(int, demo_ids))
            assert len(demo_ids) == len(env_ids) and len(set(demo_ids)) == len(demo_ids)
        for index, env_id in enumerate(env_ids):
            episode = recorder._episodes.get(env_id)
            if episode is None or episode.is_empty():
                recorder._episodes[env_id] = self.episode_class()
                continue
            mode = recorder.cfg.dataset_export_mode
            handler = None
            if mode == modes.EXPORT_ALL or (mode == modes.EXPORT_SUCCEEDED_ONLY and episode.success):
                handler = recorder._dataset_file_handler
            elif mode == modes.EXPORT_SUCCEEDED_FAILED_IN_SEPARATE_FILES:
                handler = (recorder._dataset_file_handler if episode.success
                           else recorder._failed_episode_dataset_file_handler)
            if handler is not None:
                handler.add_env_args(recorder.get_ep_meta())
                attrs = {}
                if episode.seed is not None:
                    attrs['seed'] = episode.seed
                if episode.success is not None:
                    attrs['success'] = bool(episode.success)
                self.pool.submit(episode.data, output=handler.path, env_args=dict(handler._env_args),
                                 attributes=attrs, compression=recorder.cfg.dataset_compression,
                                 demo_id=demo_ids[index] if demo_ids is not None else None, env_id=env_id,
                                 format_version=self.format_version, release_source=True)
                handler._demo_count += int(demo_ids is None)
            episode.data.clear()
            recorder._episodes[env_id] = self.episode_class()


def poll():
    if _active is not None and not _active.pool.closed:
        _active.poll()


def finish(expected_successes=None):
    if _active is not None and not _active.pool.closed:
        if expected_successes is not None:
            submitted_successes = sum(e['attributes'].get('success') is True for e in _active.pool.entries.values())
            assert submitted_successes == expected_successes, 'Generated/submitted success count mismatch'
        _active.pool.finish()
        _active.update_counters()


def abort(reason='Generation failed'):
    if _active is not None:
        _active.pool.abort(reason)
