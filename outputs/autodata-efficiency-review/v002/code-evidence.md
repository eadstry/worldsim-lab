# 冻结代码证据

以下为测试目录中的代码片段，不代表新的实现修改。原文件 SHA-256 见 data.json。

## generate.py:33–63

```python
    if args.export_workers:
        import json
        os.environ["OPENARM_ASYNC_EXPORT"] = json.dumps(dict(
            output=str(args.output_file.resolve()), workers=args.export_workers,
            memory_gib=args.export_queue_memory_gib, timeout=args.export_timeout_seconds))
        env_anchor = "    env = gym.make(env_name, cfg=env_cfg).unwrapped"
        assert source.count(env_anchor) == 1
        source = source.replace(env_anchor, """    from async_export import configure, attach
    import json, os
    configure(env_cfg)
""" + env_anchor + """
    attach(env.recorder_manager, json.loads(os.environ['OPENARM_ASYNC_EXPORT']))
""", 1)
        finish_anchor = "        if generation_completed and args_cli.result_file:"
        assert source.count(finish_anchor) == 1
        source = source.replace(finish_anchor, """        if not generation_completed:
            raise RuntimeError('Generation ended before target; async shards retained')
        from async_export import finish
        finish(expected_successes=async_components["stats"]["num_success"])
""" + finish_anchor, 1)
    else:
        os.environ.pop("OPENARM_ASYNC_EXPORT", None)
    close_anchor = "        env.close()"
    assert source.count(close_anchor) == 1
    source = source.replace(close_anchor, close_anchor + """
        if locals().get('generation_completed', False):
            from telemetry import record_output_ready
            record_output_ready()
""", 1)
    return source

```

## async_export.py:37–60

```python
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
```

## async_export.py:127–138

```python
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
```

## export_pool.py:195–234

```python
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
```

## export_pool.py:285–328

```python
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
```

## export_pool.py:339–396

```python
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
```

## export_governor.py:144–174

```python
        if not sample['cpu_sample_ready']:
            return 'cpu_sampling'
        cpu_budget = sample['cpu_capacity'] - sample['cpu_reserve_cores']
        cpu_limit = max(1, math.floor(cpu_budget))
        if worker_count >= cpu_limit:
            return 'cpu_capacity'
        if sample['free_cpu_cores'] < sample['cpu_reserve_cores'] + min(1.0, cpu_budget):
            return 'cpu_busy'
        if sample['memory_available_bytes'] < sample['memory_reserve_bytes'] + sample['worker_private_bytes']:
            return 'memory_reserve'
        if sample['task_headroom'] is not None and sample['task_headroom'] < sample['worker_task_slots']:
            return 'process_slots'
        if sample['shared_memory_free_bytes'] < 8 * MIB:
            return 'shared_memory'
        if sample['disk_free_bytes'] < episode_bytes + GIB:
            return 'disk_space'
        if sample['io_pressure_percent'] >= 20:
            return 'io_pressure'
        return 'available'

    def decide(self, processes, pending, output):
        now = time.monotonic()
        if now - self.last_checked < 1:
            return None
        self.last_checked = now
        try:
            sample = self.sample(processes, output)
            reason = self.evaluate(sample, len(processes), max(j['memory_bytes'] for j in pending.values()))
            return dict(allow=reason == 'available', reason=reason, resources=sample)
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            return dict(allow=False, reason='resources_unavailable', error=str(exc))
```
