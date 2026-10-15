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

## v2 launcher / export_pool.py:77–175

```python
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


```

## v2 launcher / export_pool.py:250–284

```python
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

```

## v2 launcher / export_pool.py:399–421

```python
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
```

## v2 launcher / v2_planner.py:42–92

```python
            reference_prim_path=config.robot_prim_path or datastream.get_robot_prim_path(env_id),
            ignore_substring=config.world_ignore_substrings,
        ).get_collision_check_world()
        robot = convert_robot(config.get_robot_config())
        kin = robot["kinematics"]
        kin["extra_collision_spheres"] = deepcopy(config.extra_collision_spheres)
        kin["grasp_contact_link_names"] = list(config.hand_link_names)
        self._robot_data = robot
        # Precompute both lock states, then copy parameters in-place so CUDA graph addresses stay stable.
        self._grip_models = {}
        for closed, positions in [(False, config.gripper_open_positions), (True, config.gripper_closed_positions)]:
            data = deepcopy(robot)
            data["kinematics"]["lock_joints"].update(positions)
            self._grip_models[closed] = KinematicsCfg.from_robot_yaml_file(data)
        self._grip_params = {closed: model.kinematics_config.clone()
                             for closed, model in self._grip_models.items()}
        cfg = MotionPlannerCfg.create(
            robot=RobotCfg(self._grip_models[False], device_cfg=self.device_cfg),
            scene_model=self._scene,
            collision_cache={"mesh": config.collision_cache_size["mesh"],
                             "cuboid": config.collision_cache_size["obb"]},
            num_ik_seeds=32,
            num_trajopt_seeds=config.num_trajopt_seeds,
            interpolation_dt=config.interpolation_dt,
            interpolation_buffer_size=1000,
            position_tolerance=config.position_threshold,
            orientation_tolerance=config.rotation_threshold,
            optimizer_collision_activation_distance=config.collision_activation_distance,
            random_seed=1531,  # Match v1 MotionGen's default IK seed.
            use_cuda_graph=True,
            device_cfg=self.device_cfg,
        )
        if not config.enable_graph:
            cfg.graph_planner_config = None
        self.motion_gen = MotionPlanner(cfg)
        # plan_pose otherwise hardcodes an extra refinement pass in the pinned v2 revision.
        # Match the existing OpenArm profile's disabled finetuning without editing cuRobo.
        if not config.enable_finetune_trajopt:
            solve_pose = self.motion_gen.trajopt_solver.solve_pose

            @functools.wraps(solve_pose)
            def solve_without_refinement(*args, **kwargs):
                kwargs['finetune_attempts'] = 0
                return solve_pose(*args, **kwargs)

            self.motion_gen.trajopt_solver.solve_pose = solve_without_refinement
        if 'MVP_METRICS_FILE' in os.environ:
            from metrics import emit
            transition = cfg.trajopt_solver_config.metrics_rollout_config.transition_model_cfg
            emit('backend_configuration', control_space=transition.control_space.name,
                 random_seed=1531,
```

## v2 launcher / v2_planner.py:139–167

```python
            kin.update_kinematics_config(params)
        self._grip = closed

    def _plan_to_contact_pose(self, start_state: JointState, goal_pose: Pose, contact: bool = True) -> bool:
        links = list(self.config.hand_link_names)
        if contact:
            links.append(self.config.attached_object_link_name)
        params = self.motion_gen.kinematics.config.kinematics_config
        saved = {name: params.get_link_spheres(name).clone() for name in links} if contact else {}
        try:
            if contact:
                self.motion_gen.disable_link_collision(links)
            goals = GoalToolPose.from_poses({self.config.ee_link_name: goal_pose},
                                            ordered_tool_frames=self.motion_gen.tool_frames)
            result = self.motion_gen.plan_pose(goals, start_state, max_attempts=self.config.max_planning_attempts)
            if result is None or not bool(result.success.all().item()):
                return False
            # The spline control points are not executable samples. Use the dense trajectory.
            trajectory = result.get_interpolated_plan()
            assert trajectory is not None
            # Returned states can include the locked gripper. Select by name before flattening.
            assert trajectory.joint_names is not None, 'Trajectory has no joint identities'
            trajectory = trajectory.reorder(self.motion_gen.joint_names)
            assert trajectory.position.shape[-1] == len(self.motion_gen.joint_names)
            self._current_plan = trajectory.position.reshape(-1, len(self.motion_gen.joint_names)).clone()
            assert torch.isfinite(self._current_plan).all()
            return True
        finally:
            for name, spheres in saved.items():
```

## v2 launcher / model.py:1–16

```python
# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Convert the OpenArm v1 robot dictionary without changing the shared source."""
from __future__ import annotations

from copy import deepcopy


def convert_robot(robot: dict) -> dict:
    """Preserve authored geometry and joint ordering while renaming v2 model fields."""
    result = deepcopy(robot)
    kin = result['kinematics']
    kin['tool_frames'] = [kin.pop('ee_link')]
    cspace = kin['cspace']
    cspace['default_joint_position'] = cspace.pop('retract_config')
    return result
```

## v2 launcher / trajectory.py:1–25

```python
# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Joint-space path retiming shared by the prototype and CPU checks."""
import torch


def resample_path(path: torch.Tensor, step_size: float) -> torch.Tensor:
    """Match the existing v1 overlay's uniform joint-distance retiming [rad]."""
    assert step_size > 0
    if len(path) <= 1:
        return path
    distances = torch.linalg.vector_norm(path[1:] - path[:-1], dim=-1)
    path = path[torch.cat((torch.ones(1, dtype=torch.bool, device=path.device), distances > 1e-6))]
    if len(path) <= 1:
        return path
    distances = torch.linalg.vector_norm(path[1:] - path[:-1], dim=-1)
    cumulative = torch.cat((distances.new_zeros(1), distances.cumsum(0)))
    if cumulative[-1] < 1e-6:
        return path
    samples = torch.linspace(0, cumulative[-1], int(torch.ceil(cumulative[-1] / step_size).item()) + 1,
                             device=path.device)
    indices = torch.searchsorted(cumulative, samples).clamp(1, len(path) - 1)
    weights = ((samples - cumulative[indices - 1]) / (cumulative[indices] - cumulative[indices - 1]))[:, None]
    return torch.lerp(path[indices - 1], path[indices], weights)

```

## v005：GPU 与进程并行的主循环依据

当前源码检查（2026-10-15），非新增运行验证。相对于本地主仓库 AutoData：

- scripts/generate_dataset.py:190–228：同一事件循环 create_task；232–263：每环境 planner。
- autodata_core/waypoint.py:330–334：提交动作并等待 queue.join。
- autodata_interfaces/env/isaaclab_env_interface.py:250–275：凑齐动作、单次 env.step、task_done 屏障。
- autodata_core/algorithms.py:240–247：普通同步规划调用。
- 实验冻结 export_pool.py:193、227：spawn 与独立 CPU writer 进程。

GPU kernel 的候选数据并行为机制说明，未测量跨规划器 stream 重叠；没有多 GPU 生产进程对照实验。

## v006 术语修订

沿用 v005 源码依据。task_done 表示队列项完成记账，不等于设备同步；主机侧普通函数调用不推出 GPU 全局同步；协程 await 仅在等待操作未完成时挂起。图中未测试架构分为单 GPU 多进程共享和多 GPU 任务分配。
