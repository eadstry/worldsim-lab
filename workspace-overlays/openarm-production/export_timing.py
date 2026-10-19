# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Scoped export timings; never change compression, buffering or file ownership."""
from __future__ import annotations

import contextvars
import functools
import inspect
import textwrap
import time
from contextlib import contextmanager

_context = contextvars.ContextVar('openarm_export_timing', default=None)


@contextmanager
def measure(phase, **details):
    state = _context.get()
    if state is None:
        yield
        return
    wall, cpu = time.perf_counter(), time.thread_time()
    error = None
    try:
        yield
    except BaseException as exc:
        error = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        row = dict(phase=phase, wall_seconds=time.perf_counter() - wall,
                   thread_cpu_seconds=time.thread_time() - cpu, error=error, **details)
        state['operations'].append(row)


def as_numpy(value):
    with measure('cpu_numpy', source_device=str(value.device), shape=list(value.shape)):
        return value.cpu().numpy()


def wrap_method(cls, name, phase):
    original = getattr(cls, name)
    if getattr(original, '_openarm_export_timing', False):
        return

    @functools.wraps(original)
    def tracked(*args, **kwargs):
        with measure(phase):
            return original(*args, **kwargs)

    tracked._openarm_export_timing = True
    setattr(cls, name, tracked)


def install(recorder):
    """Instrument the recorder's actual episode and file-handler classes in memory."""
    import h5py

    # Includes newly reset empty episodes; later instances use the same class.
    for cls in {type(episode) for episode in recorder._episodes.values()}:
        wrap_method(cls, 'pre_export', 'prepare_stack')
    handlers = (recorder._dataset_file_handler, recorder._failed_episode_dataset_file_handler)
    for cls in {type(handler) for handler in handlers if handler is not None}:
        original = cls.write_episode
        if not getattr(original, '_openarm_export_timing', False):
            source = textwrap.dedent(inspect.getsource(original))
            anchor = 'value.cpu().numpy()'
            assert source.count(anchor) == 2, 'HDF5 writer changed; review export timing anchors'
            source = source.replace(anchor, '_openarm_export_as_numpy(value)')
            namespace = {**original.__globals__, '_openarm_export_as_numpy': as_numpy}
            exec(compile(source, inspect.getsourcefile(original), 'exec'), namespace)
            cls.write_episode = namespace['write_episode']
            wrap_method(cls, 'write_episode', 'write_episode_inclusive')
        wrap_method(cls, 'flush', 'flush')

    original_create = h5py.Group.create_dataset
    if not getattr(original_create, '_openarm_export_timing', False):
        @functools.wraps(original_create)
        def tracked_create(group, name, *args, **kwargs):
            if _context.get() is None:
                return original_create(group, name, *args, **kwargs)
            data = kwargs.get('data')
            with measure('dataset_create', dataset=f'{group.name}/{name}',
                         shape=list(data.shape) if data is not None else None,
                         dtype=str(data.dtype) if data is not None else None,
                         raw_bytes=int(data.nbytes) if data is not None else None,
                         compression=kwargs.get('compression'),
                         compression_opts=kwargs.get('compression_opts'),
                         requested_chunks=kwargs.get('chunks')):
                return original_create(group, name, *args, **kwargs)

        tracked_create._openarm_export_timing = True
        h5py.Group.create_dataset = tracked_create


@contextmanager
def export_scope(emit, **identity):
    """Report exclusive phase totals plus per-dataset inclusive HDF5 timings."""
    state = {'operations': []}
    token = _context.set(state)
    started, cpu = time.perf_counter(), time.thread_time()
    error = None
    try:
        yield
    except BaseException as exc:
        error = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        wall = time.perf_counter() - started
        cpu_seconds = time.thread_time() - cpu
        _context.reset(token)
        phases = ('prepare_stack', 'cpu_numpy', 'dataset_create', 'flush')
        totals = {phase: sum(r['wall_seconds'] for r in state['operations'] if r['phase'] == phase)
                  for phase in phases}
        emit('export_breakdown', **identity, duration_seconds=wall,
             thread_cpu_seconds=cpu_seconds, phases_seconds=totals,
             other_seconds=wall - sum(totals.values()), operations=state['operations'], error=error,
             timing_semantics='host wall and current-thread CPU; dataset_create includes gzip, HDF5 and I/O; '
                              'flush is HDF5 flush, not fsync; GPU copies may synchronize; '
                              'write_episode_inclusive overlaps cpu_numpy and dataset_create')
        print('[OpenArm export] ' + str(identity.get('episode_id', '?')) +
              f' total={wall:.3f}s stack={totals["prepare_stack"]:.3f}s '
              f'cpu_numpy={totals["cpu_numpy"]:.3f}s '
              f'compress+hdf5_write={totals["dataset_create"]:.3f}s '
              f'flush={totals["flush"]:.3f}s other={wall - sum(totals.values()):.3f}s '
              f'thread_cpu={cpu_seconds:.3f}s', flush=True)
