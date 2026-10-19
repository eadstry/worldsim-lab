# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Bounded whole-episode shared memory with HDF5 writers started on demand.

Workers import only CPU libraries. HDF5 objects and simulation objects never cross
process boundaries. The producer owns all shared-memory allocations until ACK.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import queue
import shutil
import time
from multiprocessing.shared_memory import SharedMemory
from pathlib import Path

import numpy as np

from export_resources import check_export_capacity
from export_governor import ResourceGovernor


def array(value):
    return value.detach().cpu().numpy() if hasattr(value, 'detach') else np.asarray(value)


def layout(data):
    leaves = []
    offset = 0

    def visit(values, prefix=''):
        nonlocal offset
        for key, value in values.items():
            name = f'{prefix}/{key}' if prefix else key
            if isinstance(value, dict):
                visit(value, name)
                continue
            if isinstance(value, list):
                assert value, f'Empty recorder list: {name}'
                first = array(value[0])
                shape, dtype = (len(value), *first.shape), first.dtype
            else:
                first = array(value)
                shape, dtype = first.shape, first.dtype
            assert not dtype.hasobject, f'Object arrays are unsupported: {name}'
            offset = (offset + 63) // 64 * 64
            size = int(np.prod(shape)) * dtype.itemsize
            leaves.append(dict(path=name, shape=list(shape), dtype=dtype.str, offset=offset, bytes=size))
            offset += size

    visit(data)
    return leaves, max(offset, 1)


def empty_groups(data, prefix=''):
    names = []
    for key, value in data.items():
        path = f'{prefix}/{key}' if prefix else key
        if isinstance(value, dict):
            if not value:
                names.append(path)
            names.extend(empty_groups(value, path))
    return names


def trim_free_memory():
    # glibc may retain freed recorder frames in arenas. Return those pages before
    # touching more shared-memory pages; workers never call this producer helper.
    import ctypes
    trim = getattr(ctypes.CDLL(None), 'malloc_trim', None)
    if trim is not None:
        trim(0)


def pack(data, leaves, memory, release_source=False):
    for leaf in leaves:
        value = data
        for key in leaf['path'].split('/'):
            value = value[key]
        target = np.ndarray(leaf['shape'], dtype=leaf['dtype'], buffer=memory.buf, offset=leaf['offset'])
        if isinstance(value, list) and getattr(value[0], 'is_cuda', False):
            # RGB is already CPU-resident. Batch the small GPU state fields to
            # avoid thousands of individual device synchronizations per episode.
            import torch
            np.copyto(target, torch.stack(value).detach().cpu().numpy(), casting='no')
            if release_source:
                value.clear()
        elif isinstance(value, list):
            released = 0
            for index, frame in enumerate(value):
                source = array(frame)
                assert source.shape == target.shape[1:] and source.dtype == target.dtype, leaf['path']
                np.copyto(target[index:index + 1], source.reshape((1, *source.shape)), casting='no')
                if release_source:
                    released += source.nbytes
                    value[index] = None
                    del source, frame
                    if released >= 64 * 1024**2:
                        trim_free_memory()
                        released = 0
            if release_source:
                value.clear()
                trim_free_memory()
        else:
            np.copyto(target, array(value), casting='no')


def write_job(job, handles, directory):
    import h5py

    route = job['route']
    if route not in handles:
        file = h5py.File(Path(directory) / f'worker-{os.getpid()}-{route}.hdf5', 'x')
        file.attrs['format_version'] = job['format_version']
        data = file.create_group('data')
        data.attrs['total'] = 0
        handles[route] = file
    file = handles[route]
    file['data'].attrs['env_args'] = json.dumps(job['env_args'])
    memory = SharedMemory(name=job['memory'])
    group = file.create_group(f'_pending_{job["demo_id"]}')
    view = None
    try:
        for name in job.get('empty_groups', []):
            group.require_group(name)
        for leaf in job['leaves']:
            view = np.ndarray(leaf['shape'], dtype=leaf['dtype'], buffer=memory.buf, offset=leaf['offset'])
            view.flags.writeable = False
            parent, _, key = leaf['path'].rpartition('/')
            options = dict(compression='gzip', compression_opts=2) if job['compression'] else {}
            destination = group.require_group(parent) if parent else group
            destination.create_dataset(key, data=view, **options)
            view = None
        for key, value in job['attributes'].items():
            group.attrs[key] = value
        file.move(group.name, f'/data/demo_{job["demo_id"]}')
        file['data'].attrs['total'] += job['attributes']['num_samples']
        file.flush()
        return str(Path(file.filename)), int(os.stat(file.filename).st_size)
    finally:
        view = None
        memory.close()


def writer(jobs, results, directory, parent_pid):
    """Spawn entrypoint: no Isaac Sim, torch or CUDA imports."""
    handles = {}
    try:
        while True:
            if os.getppid() != parent_pid:
                return
            try:
                job = jobs.get(timeout=1)
            except queue.Empty:
                if os.getppid() != parent_pid:
                    return
                continue
            if job is None:
                return
            start = time.monotonic()
            results.put(dict(kind='started', key=job['key'], worker_pid=os.getpid()))
            try:
                shard, size = write_job(job, handles, directory)
                results.put(dict(kind='saved', key=job['key'], shard=shard, shard_bytes=size,
                                 worker_pid=os.getpid(), write_seconds=time.monotonic() - start))
            except BaseException as exc:
                results.put(dict(kind='failed', key=job['key'], error=f'{type(exc).__name__}: {exc}'))
                raise
    finally:
        for file in handles.values():
            file.close()


class ExportPool:
    def __init__(self, output, workers=2, memory_bytes=16 * 1024**3, timeout=600,
                 emit=None, worker_target=writer, resource_governor=None):
        self.output = Path(output).resolve()
        self.directory = self.output.with_suffix('.export-parts')
        self.manifest = self.output.with_suffix('.export.json')
        assert (workers == 'auto' or workers > 0) and memory_bytes > 0 and timeout > 0
        assert not self.output.exists() and not self.directory.exists() and not self.manifest.exists()
        check_export_capacity(memory_bytes)
        self.directory.mkdir(parents=True)
        self.limit, self.timeout = int(memory_bytes), timeout
        self.emit = emit or (lambda *args, **kwargs: None)
        self.started = time.monotonic()
        self.pending, self.entries, self.memories, self.next_ids, self.outputs = {}, {}, {}, {}, {}
        self.used = self.peak = 0
        self.wait_seconds = self.pack_seconds = 0.0
        self.closed = False
        self.context = mp.get_context('spawn')
        self.jobs, self.results = self.context.Queue(), self.context.Queue()
        self.max_workers = None if workers == 'auto' else int(workers)
        self.governor = (resource_governor or ResourceGovernor()) if workers == 'auto' else None
        self.scaling_policy = 'server_resources' if self.governor is not None else 'on_demand'
        self.admission = None
        self.worker_target = worker_target
        self.processes = []
        self._manifest('starting')
        self.emit('export_pool_started', workers=0, max_workers=self.max_workers,
                  scaling_policy=self.scaling_policy, memory_limit_bytes=self.limit, worker_pids=[])

    def _scale_workers(self):
        # Pending includes queued and writing jobs, including workers still starting.
        # Account for all of them without relying on multiprocessing.Queue.qsize().
        desired = len(self.pending)
        if desired <= len(self.processes):
            return
        if self.governor is not None:
            decision = self.governor.decide(self.processes, self.pending, self.output)
            if decision is None:
                return
            previous_reason = self.admission.get('reason') if self.admission else None
            self.admission = decision
            if decision['reason'] != previous_reason:
                self.emit('export_scaling_decision', workers=len(self.processes), **decision)
                self._manifest('running')
            if not decision['allow']:
                return
            desired = len(self.processes) + 1
        else:
            desired = min(desired, self.max_workers)
        try:
            while len(self.processes) < desired:
                process = self.context.Process(target=self.worker_target,
                    args=(self.jobs, self.results, str(self.directory), os.getpid()), daemon=True)
                self.processes.append(process)
                process.start()
                self.emit('export_worker_started', worker_pid=process.pid, workers=len(self.processes),
                          max_workers=self.max_workers, pending_episodes=len(self.pending))
                self._manifest('running')
        except BaseException as exc:
            self.abort(f'Worker startup failed: {type(exc).__name__}: {exc}')
            raise

    def _manifest(self, status, **extra):
        value = dict(status=status, output=str(self.output), entries=list(self.entries.values()),
                     scaling_policy=self.scaling_policy, max_workers=self.max_workers,
                     resource_admission=self.admission,
                     worker_pids=[p.pid for p in self.processes if p.pid is not None],
                     memory_limit_bytes=self.limit, peak_memory_bytes=self.peak,
                     queue_wait_seconds=self.wait_seconds, packing_seconds=self.pack_seconds,
                     elapsed_seconds=time.monotonic() - self.started, **extra)
        temporary = self.manifest.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(value, indent=2, default=str) + '\n')
        temporary.replace(self.manifest)

    def poll(self, wait=0):
        assert not self.closed, 'Export pool is closed'
        first = True
        while True:
            try:
                row = self.results.get(timeout=wait if first else 0)
            except queue.Empty:
                break
            first = False
            key = row['key']
            if row['kind'] == 'failed':
                raise RuntimeError(f'Export {key} failed: {row["error"]}')
            if row['kind'] == 'started':
                self.pending[key]['writing_started'] = time.monotonic()
                self.emit('export_write_started', **row)
            elif row['kind'] == 'saved':
                job = self.pending.pop(key)
                self.entries[key].update(status='saved', **row)
                memory = self.memories.pop(key)
                memory.close()
                memory.unlink()
                self.used -= job['memory_bytes']
                self.emit('export_saved', demo_id=job['demo_id'], env_id=job.get('env_id'),
                          queue_memory_bytes=self.used, **row)
                self._manifest('running')
        for process in self.processes:
            if process.exitcode is not None:
                raise RuntimeError(f'Export worker {process.pid} exited unexpectedly: {process.exitcode}')
        now = time.monotonic()
        for key, job in self.pending.items():
            if now - job.get('writing_started', job['submitted_at']) > self.timeout:
                reason = self.admission.get('reason') if self.admission else None
                raise TimeoutError(f'Export {key} exceeded {self.timeout}s; resource admission: {reason}')
        self._scale_workers()

    def submit(self, data, output=None, env_args=None, attributes=None, compression=True,
               demo_id=None, env_id=None, format_version=1, release_source=False):
        self.poll()
        output = Path(output or self.output).resolve()
        route = next((r for r, p in self.outputs.items() if p == str(output)), None)
        if route is None:
            assert not output.exists(), f'Output exists: {output}'
            route = str(len(self.outputs))
            self.outputs[route] = str(output)
        leaves, size = layout(data)
        assert size <= self.limit, f'Episode requires {size} bytes, exceeding export budget {self.limit}'
        wait = time.monotonic()
        while self.used + size > self.limit:
            self.poll(wait=.05)
        waited = time.monotonic() - wait
        self.wait_seconds += waited
        index = self.next_ids.get(route, 0) if demo_id is None else int(demo_id)
        key = f'{route}:{index}'
        assert key not in self.entries, f'Duplicate demo id: {key}'
        if demo_id is None:
            self.next_ids[route] = index + 1
        attrs = dict(attributes or {})
        actions = next((leaf for leaf in leaves if leaf['path'] == 'actions'), None)
        attrs['num_samples'] = actions['shape'][0] if actions else 0
        assert size + 8 * 1024**2 <= shutil.disk_usage('/dev/shm').free, 'Shared memory capacity changed; cannot pack episode safely'
        memory = SharedMemory(create=True, size=size)
        try:
            start = time.monotonic()
            pack(data, leaves, memory, release_source=release_source)
            packed = time.monotonic() - start
            self.pack_seconds += packed
            job = dict(key=key, route=route, demo_id=index, env_id=env_id, memory=memory.name,
                       memory_bytes=size, leaves=leaves, empty_groups=empty_groups(data), attributes=attrs, env_args=env_args or {},
                       format_version=format_version, compression=bool(compression))
            # Packing a large episode can take seconds; acknowledge any writes that
            # finished meanwhile so an idle writer is reused before scaling up.
            self.poll()
            self.used += size
            self.peak = max(self.peak, self.used)
            self.memories[key] = memory
            self.pending[key] = dict(job, submitted_at=time.monotonic())
            self.entries[key] = dict(job, status='submitted')
            self._manifest('running')
            self.jobs.put(job)
            self.emit('export_submitted', demo_id=index, env_id=env_id, memory_bytes=size,
                      packing_seconds=packed, queue_wait_seconds=waited, queue_memory_bytes=self.used)
            self._scale_workers()
        except BaseException:
            if key not in self.memories and not self.closed:
                memory.close()
                memory.unlink()
            raise
        return index

    def finish(self):
        start = time.monotonic()
        try:
            while self.pending:
                self.poll(wait=.05)
            for _ in self.processes:
                self.jobs.put(None)
            for process in self.processes:
                process.join(timeout=self.timeout)
                if process.exitcode != 0:
                    raise RuntimeError(f'Writer shutdown failed: {process.pid}, exit={process.exitcode}')
            merge_start = time.monotonic()
            self._merge()
            self._manifest('complete', drain_seconds=merge_start - start,
                           merge_seconds=time.monotonic() - merge_start)
            shutil.rmtree(self.directory)
            self.closed = True
            self.jobs.close()
            self.jobs.join_thread()
            self.results.close()
            self.results.join_thread()
            self.emit('export_complete', saved_episodes=len(self.entries),
                      drain_seconds=merge_start - start, merge_seconds=time.monotonic() - merge_start,
                      peak_memory_bytes=self.peak, queue_wait_seconds=self.wait_seconds,
                      packing_seconds=self.pack_seconds, final_ready_seconds=time.monotonic() - self.started)
        except BaseException as exc:
            self.abort(str(exc))
            raise

    def _merge(self):
        import h5py
        staged = []
        for route, path in self.outputs.items():
            entries = sorted((e for e in self.entries.values() if e['route'] == route), key=lambda e: e['demo_id'])
            temporary = Path(path).with_suffix('.partial.hdf5')
            assert not temporary.exists() and not Path(path).exists()
            with h5py.File(temporary, 'x') as destination:
                destination.attrs['format_version'] = entries[0]['format_version']
                data = destination.create_group('data')
                data.attrs['env_args'] = json.dumps(entries[-1]['env_args'])
                data.attrs['total'] = sum(e['attributes']['num_samples'] for e in entries)
                for entry in entries:
                    assert entry['status'] == 'saved'
                    name = f'demo_{entry["demo_id"]}'
                    with h5py.File(entry['shard'], 'r') as source:
                        source.copy(source[f'data/{name}'], data, name=name)
                    copied = data[name]
                    assert dict(copied.attrs) == entry['attributes']
                    for name in entry.get('empty_groups', []):
                        assert isinstance(copied[name], h5py.Group) and not len(copied[name])
                    for leaf in entry['leaves']:
                        value = copied[leaf['path']]
                        assert list(value.shape) == leaf['shape'] and value.dtype.str == leaf['dtype']
                        assert value.compression == ('gzip' if entry['compression'] else None)
                assert len(data) == len(entries)
            staged.append((temporary, Path(path)))
        for temporary, output in staged:
            os.link(temporary, output)  # Atomic publication, refuses overwrite.
            temporary.unlink()

    def abort(self, reason):
        if self.closed:
            return
        for process in self.processes:
            if process.pid is not None and process.is_alive():
                process.terminate()
        for process in self.processes:
            if process.pid is not None:
                process.join(timeout=5)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=5)
        for memory in self.memories.values():
            memory.close()
            memory.unlink()
        self.memories.clear()
        self.pending.clear()
        self.used = 0
        self.closed = True
        self._manifest('failed', error=reason)
        for channel in (self.jobs, self.results):
            channel.cancel_join_thread()
            channel.close()
