# 接口核对证据

2026-10-15 静态源码检查；不是新增运行验证。

## autodata_interfaces/motion_planners/curobo/curobo_planner.py

当前源码，非历史冻结快照；SHA-256：59a38b465dd073b8173b1a588347e7321f5f18685fc774ff5759d21f1748daaa

```text
14: from curobo.geom.sdf.world import CollisionCheckerType
15: from curobo.geom.sphere_fit import SphereFitType
16: from curobo.geom.types import WorldConfig
17: from curobo.types.base import TensorDeviceType
18: from curobo.types.math import Pose
19: from curobo.types.state import JointState
20: from curobo.util.logger import setup_curobo_logger
21: from curobo.util.usd_helper import UsdHelper
22: from curobo.util_file import load_yaml
23: from curobo.wrap.reacher.motion_gen import MotionGen, MotionGenConfig, MotionGenPlanConfig
24: from isaaclab.sim.spawners.materials import PreviewSurfaceCfg
```

```text
240:         # Load world configuration using the config's method
241:         world_cfg: WorldConfig = self.config.get_world_config()
242: 
243:         # Create motion generator config with parameters from configuration
244:         motion_gen_config: MotionGenConfig = MotionGenConfig.load_from_robot_config(
245:             robot_cfg,
246:             world_cfg,
247:             tensor_args=self.tensor_args,
248:             collision_checker_type=self.config.collision_checker_type,
249:             num_trajopt_seeds=self.config.num_trajopt_seeds,
250:             num_graph_seeds=self.config.num_graph_seeds,
251:             interpolation_dt=self.config.interpolation_dt,
252:             collision_cache=self.config.collision_cache_size,
253:             trajopt_tsteps=self.config.trajopt_tsteps,
254:             collision_activation_distance=self.config.collision_activation_distance,
255:             position_threshold=self.config.position_threshold,
256:             rotation_threshold=self.config.rotation_threshold,
257:         )
258: 
259:         # Create motion generator
260:         self.motion_gen: MotionGen = MotionGen(motion_gen_config)
261: 
262:         # Set motion generator reference for plan visualizer if enabled
263:         if self.visualize_plan:
264:             self.plan_visualizer.set_motion_generator_reference(self.motion_gen)
265: 
266:         # Create plan config with parameters from configuration
267:         self.plan_config: MotionGenPlanConfig = MotionGenPlanConfig(
268:             enable_graph=self.config.enable_graph,
269:             enable_graph_attempt=self.config.enable_graph_attempt,
270:             max_attempts=self.config.max_planning_attempts,
271:             enable_finetune_trajopt=self.config.enable_finetune_trajopt,
272:             time_dilation_factor=self.config.time_dilation_factor,
273:         )
274: 
275:         # Create USD helper. The collision-geometry source (USD stage) is read through the
276:         # Datastream so the planner never reaches into ``env.scene`` directly.
277:         self.usd_helper: UsdHelper = UsdHelper()
```

```text
1303:         planning_success = False
1304:         try:
1305:             result: Any = self.motion_gen.plan_single(start_state, goal_pose, self.plan_config)
1306: 
1307:             if result.success.item():
1308:                 if result.optimized_plan is not None and len(result.optimized_plan.position) != 0:
1309:                     self._current_plan = result.optimized_plan
1310:                     self.logger.debug(f"Using optimized plan with {len(self._current_plan.position)} waypoints")
1311:                 else:
1312:                     self._current_plan = result.get_interpolated_plan()
1313:                     self.logger.debug(f"Using interpolated plan with {len(self._current_plan.position)} waypoints")
1314: 
1315:                 self._current_plan = self.motion_gen.get_full_js(self._current_plan)
1316:                 common_js_names: list[str] = [
1317:                     x for x in self.datastream.get_robot_joint_names() if x in self._current_plan.joint_names
1318:                 ]
1319:                 self._current_plan = self._current_plan.get_ordered_joint_state(common_js_names)
1320:                 self._plan_index = 0
1321: 
1322:                 planning_success = True
1323:                 self.logger.debug(f"Contact planning succeeded with {len(self._current_plan.position)} waypoints")
1324:             else:
1325:                 self.logger.debug(f"Contact planning failed: {result.status}")
1326: 
```

```text
1545:             IndexError: If no more waypoints remain in the trajectory
1546:         """
1547:         if not self.has_next_waypoint():
1548:             raise IndexError("No more waypoints in the plan.")
1549:         next_joint_state: JointState = self._current_plan[self._plan_index]
1550:         self._plan_index += 1
1551:         eef_state: CudaRobotModelState = self.motion_gen.compute_kinematics(next_joint_state)
1552:         if self._base_frame_is_identity:
1553:             return eef_state.ee_pose
1554:         # Express the base-frame EE pose in the env-relative frame callers expect.
1555:         ee_pos = self._to_env_device(eef_state.ee_pose.position)
1556:         ee_rot = self._to_env_device(eef_state.ee_pose.get_rotation())
1557:         ee_pose_env = self._pose_base_to_env(PoseUtils.make_pose(ee_pos, ee_rot))
1558:         env_pos, env_rot = PoseUtils.unmake_pose(ee_pose_env)
1559:         return self._make_pose(position=env_pos, quaternion=PoseUtils.quat_from_matrix(env_rot))
1560: 
1561:     def reset_plan(self) -> None:
1562:         """Reset trajectory execution state.
1563: 
1564:         Clears the current trajectory and resets the execution index to zero.
1565:         This prepares the planner for a new planning operation.
```

```text
1828:     def update_world_and_plan_motion(
1829:         self,
1830:         target_pose: torch.Tensor,
1831:         expected_attached_object: str | None = None,
1832:         env_id: int = 0,
1833:         step_size: float | None = None,
1834:         enable_retiming: bool | None = None,
1835:     ) -> bool:
1836:         """Complete planning pipeline with world updates and object attachment handling.
1837: 
```

## datasets/efficiency_20261014_201834/v2/launchers/v2/v2_planner.py

实验冻结适配器；SHA-256：78b58d08f9503d302325a35775ffbd6ec8e98e366d0663c54b724f7808c779ea

```text
10: 
11: import torch
12: from curobo.kinematics import KinematicsCfg
13: from curobo.motion_planner import MotionPlanner, MotionPlannerCfg
14: from curobo.sphere_fit import SphereFitType
15: from curobo.types import DeviceCfg, GoalToolPose, JointState, Pose
16: # These two utilities have no public exports in the pinned v2 revision.
17: from curobo._src.types.robot import RobotCfg
```

```text
54:             data["kinematics"]["lock_joints"].update(positions)
55:             self._grip_models[closed] = KinematicsCfg.from_robot_yaml_file(data)
56:         self._grip_params = {closed: model.kinematics_config.clone()
57:                              for closed, model in self._grip_models.items()}
58:         cfg = MotionPlannerCfg.create(
59:             robot=RobotCfg(self._grip_models[False], device_cfg=self.device_cfg),
60:             scene_model=self._scene,
61:             collision_cache={"mesh": config.collision_cache_size["mesh"],
62:                              "cuboid": config.collision_cache_size["obb"]},
63:             num_ik_seeds=32,
64:             num_trajopt_seeds=config.num_trajopt_seeds,
65:             interpolation_dt=config.interpolation_dt,
66:             interpolation_buffer_size=1000,
67:             position_tolerance=config.position_threshold,
68:             orientation_tolerance=config.rotation_threshold,
69:             optimizer_collision_activation_distance=config.collision_activation_distance,
70:             random_seed=1531,  # Match v1 MotionGen's default IK seed.
71:             use_cuda_graph=True,
72:             device_cfg=self.device_cfg,
73:         )
74:         if not config.enable_graph:
75:             cfg.graph_planner_config = None
76:         self.motion_gen = MotionPlanner(cfg)
77:         # plan_pose otherwise hardcodes an extra refinement pass in the pinned v2 revision.
78:         # Match the existing OpenArm profile's disabled finetuning without editing cuRobo.
79:         if not config.enable_finetune_trajopt:
80:             solve_pose = self.motion_gen.trajopt_solver.solve_pose
81: 
82:             @functools.wraps(solve_pose)
83:             def solve_without_refinement(*args, **kwargs):
84:                 kwargs['finetune_attempts'] = 0
85:                 return solve_pose(*args, **kwargs)
86: 
87:             self.motion_gen.trajopt_solver.solve_pose = solve_without_refinement
88:         if 'MVP_METRICS_FILE' in os.environ:
```

```text
118:     def reset_plan(self) -> None:
119:         self._current_plan, self._index = None, 0
120: 
121:     def _update_world(self) -> None:
122:         self._base = self.datastream.get_robot_root_pose(env_ids=[self.env_id])[0]
123:         self._inverse_base = torch.linalg.inv(self._base)
124:         objects = self.datastream.get_object_poses(env_ids=[self.env_id])
125:         for name, values in objects.items():
126:             if name in self.config.static_objects:
127:                 continue
128:             pose = Pose.from_matrix(self._inverse_base @ values[0])
129:             matches = [o for o in self._scene.objects if name.lower() in o.name.lower()]
130:             assert matches, f"No collision geometry for dynamic object {name}"
131:             for obstacle in matches:
132:                 obstacle.pose = pose.tolist()
133:                 self.motion_gen.scene_collision_checker.update_obstacle_pose(
134:                     obstacle.name, pose, env_idx=0)
135: 
136:     def _set_gripper(self, closed: bool) -> None:
137:         params = self._grip_params[closed]
138:         for kin in [self.motion_gen.ik_solver.kinematics, self.motion_gen.trajopt_solver.kinematics]:
139:             kin.update_kinematics_config(params)
140:         self._grip = closed
141: 
142:     def _plan_to_contact_pose(self, start_state: JointState, goal_pose: Pose, contact: bool = True) -> bool:
143:         links = list(self.config.hand_link_names)
```

```text
159:             # Returned states can include the locked gripper. Select by name before flattening.
160:             assert trajectory.joint_names is not None, 'Trajectory has no joint identities'
161:             trajectory = trajectory.reorder(self.motion_gen.joint_names)
162:             assert trajectory.position.shape[-1] == len(self.motion_gen.joint_names)
163:             self._current_plan = trajectory.position.reshape(-1, len(self.motion_gen.joint_names)).clone()
164:             assert torch.isfinite(self._current_plan).all()
165:             return True
166:         finally:
167:             for name, spheres in saved.items():
168:                 params.update_link_spheres(name, spheres)
169: 
170:     @torch.inference_mode(False)
171:     @torch.enable_grad()
172:     def update_world_and_plan_motion(self, target_pose: torch.Tensor,
173:                                      expected_attached_object: str | None = None, env_id: int = 0,
174:                                      step_size: float | None = None, enable_retiming: bool = False) -> bool:
175:         assert env_id == self.env_id
176:         self.reset_plan()
177:         self._update_world()
178:         self._set_gripper(expected_attached_object is not None)
179:         state = self._state()
180:         attached = False
181:         try:
182:             if expected_attached_object:
```

```text
186:                 grasped = joint > self.config.grasp_gripper_open_val if self.config.gripper_closes_on_increasing_position else joint < self.config.grasp_gripper_open_val
187:                 assert grasped, "Expected carried object but gripper is not closed"
188:                 objects = [o.name for o in self._scene.objects if expected_attached_object.lower() in o.name.lower()]
189:                 assert objects, f"No obstacle to attach: {expected_attached_object}"
190:                 # Scene fitting produces base-frame centers. Identity offset makes update apply EE^-1.
191:                 identity = Pose.from_matrix(torch.eye(4, device=state.position.device))
```

```text
207:                                         + [1.0, 0.0, 0.0, 0.0], device_cfg=self.device_cfg)
208:                 targets.append(goal.multiply(offset))
209:                 contacts.append(False)
210:                 targets.append(goal)
211:                 contacts.append(True)
212:             else:
213:                 targets.append(goal)
214:                 contacts.append(False)
215:             segments = []
216:             for target, contact in zip(targets, contacts):
217:                 if not self._plan_to_contact_pose(start_state=state, goal_pose=target, contact=contact):
```

```text
249:         if not self._closed:
250:             self.motion_gen.destroy()
251:             self._closed = True
```

## datasets/efficiency_20261014_201834/v1/launchers/v1/async_export.py

实验冻结保存桥；SHA-256：b44c38db5f28faecc316369e5bfafa73d627eeddf26eb757a1dcce26a2da6573

```text
36: 
37: def owned_recording_method(original):
38:     """Preserve values while avoiding CPU frames that retain other environments."""
39:     import inspect
40:     import textwrap
41:     if getattr(original, '_openarm_cpu_owned', False):
42:         return original
43:     source = textwrap.dedent(inspect.getsource(original))
44:     anchor = '    value = value.clone()  # Clone once for all envs'
45:     add = 'self._episodes[env_id].add(key, value[value_index], clone=False)'
46:     assert source.count(anchor) == 1 and source.count(add) == 1
47:     source = source.replace(anchor, """    cpu_owned = value.device.type == 'cpu'
48:     if not cpu_owned:
49:         value = value.clone()""", 1)
50:     source = source.replace(add, 'self._episodes[env_id].add(key, value[value_index], clone=cpu_owned)', 1)
51:     namespace = dict(original.__globals__)
52:     exec(compile(source, inspect.getsourcefile(original), 'exec'), namespace)
53:     method = namespace['add_to_episodes']
54:     method._openarm_cpu_owned = True
55:     return method
56: 
57: 
58: def configure(env_cfg):
59:     from isaaclab.managers.recorder_manager import RecorderManager
60:     RecorderManager.add_to_episodes = owned_recording_method(RecorderManager.add_to_episodes)
61:     env_cfg.recorders.dataset_file_handler_class_type = MetadataHandler
62: 
63: 
64: def emit(event, **values):
65:     from telemetry import _active as telemetry
66:     if telemetry is not None:
67:         telemetry.emit(event, **values)
```

```text
91:     def poll(self):
92:         self.pool.poll()
93:         self.update_counters()
94: 
95:     def update_counters(self):
96:         for key, entry in self.pool.entries.items():
97:             if entry['status'] != 'saved' or key in self.saved_seen:
98:                 continue
99:             self.saved_seen.add(key)
100:             counters = (self.recorder._exported_successful_episode_count if entry['attributes'].get('success')
101:                         else self.recorder._exported_failed_episode_count)
```

```text
115:             episode = recorder._episodes.get(env_id)
116:             if episode is None or episode.is_empty():
117:                 recorder._episodes[env_id] = self.episode_class()
118:                 continue
119:             mode = recorder.cfg.dataset_export_mode
120:             handler = None
121:             if mode == modes.EXPORT_ALL or (mode == modes.EXPORT_SUCCEEDED_ONLY and episode.success):
122:                 handler = recorder._dataset_file_handler
123:             elif mode == modes.EXPORT_SUCCEEDED_FAILED_IN_SEPARATE_FILES:
124:                 handler = (recorder._dataset_file_handler if episode.success
125:                            else recorder._failed_episode_dataset_file_handler)
126:             if handler is not None:
127:                 handler.add_env_args(recorder.get_ep_meta())
128:                 attrs = {}
129:                 if episode.seed is not None:
130:                     attrs['seed'] = episode.seed
131:                 if episode.success is not None:
132:                     attrs['success'] = bool(episode.success)
133:                 self.pool.submit(episode.data, output=handler.path, env_args=dict(handler._env_args),
134:                                  attributes=attrs, compression=recorder.cfg.dataset_compression,
135:                                  demo_id=demo_ids[index] if demo_ids is not None else None, env_id=env_id,
136:                                  format_version=self.format_version, release_source=True)
137:                 handler._demo_count += int(demo_ids is None)
138:             episode.data.clear()
139:             recorder._episodes[env_id] = self.episode_class()
140: 
141: 
142: def poll():
143:     if _active is not None and not _active.pool.closed:
144:         _active.poll()
145: 
146: 
147: def finish(expected_successes=None):
148:     if _active is not None and not _active.pool.closed:
149:         if expected_successes is not None:
150:             submitted_successes = sum(e['attributes'].get('success') is True for e in _active.pool.entries.values())
151:             assert submitted_successes == expected_successes, 'Generated/submitted success count mismatch'
152:         _active.pool.finish()
```

```text

```

## datasets/efficiency_20261014_201834/v1/launchers/v1/export_pool.py

实验冻结保存池；SHA-256：ef03ef54bbbc7276205b15030358ee691fc3f422c6449f263acd8c7887768aef

```text
190:         self.used = self.peak = 0
191:         self.wait_seconds = self.pack_seconds = 0.0
192:         self.closed = False
193:         self.context = mp.get_context('spawn')
194:         self.jobs, self.results = self.context.Queue(), self.context.Queue()
195:         self.max_workers = None if workers == 'auto' else int(workers)
```

```text
285:     def submit(self, data, output=None, env_args=None, attributes=None, compression=True,
286:                demo_id=None, env_id=None, format_version=1, release_source=False):
287:         self.poll()
288:         output = Path(output or self.output).resolve()
289:         route = next((r for r, p in self.outputs.items() if p == str(output)), None)
290:         if route is None:
291:             assert not output.exists(), f'Output exists: {output}'
292:             route = str(len(self.outputs))
293:             self.outputs[route] = str(output)
294:         leaves, size = layout(data)
295:         assert size <= self.limit, f'Episode requires {size} bytes, exceeding export budget {self.limit}'
296:         wait = time.monotonic()
297:         while self.used + size > self.limit:
298:             self.poll(wait=.05)
299:         waited = time.monotonic() - wait
300:         self.wait_seconds += waited
301:         index = self.next_ids.get(route, 0) if demo_id is None else int(demo_id)
302:         key = f'{route}:{index}'
303:         assert key not in self.entries, f'Duplicate demo id: {key}'
304:         if demo_id is None:
305:             self.next_ids[route] = index + 1
306:         attrs = dict(attributes or {})
307:         actions = next((leaf for leaf in leaves if leaf['path'] == 'actions'), None)
308:         attrs['num_samples'] = actions['shape'][0] if actions else 0
309:         assert size + 8 * 1024**2 <= shutil.disk_usage('/dev/shm').free, 'Shared memory capacity changed; cannot pack episode safely'
310:         memory = SharedMemory(create=True, size=size)
311:         try:
312:             start = time.monotonic()
313:             pack(data, leaves, memory, release_source=release_source)
314:             packed = time.monotonic() - start
315:             self.pack_seconds += packed
316:             job = dict(key=key, route=route, demo_id=index, env_id=env_id, memory=memory.name,
317:                        memory_bytes=size, leaves=leaves, empty_groups=empty_groups(data), attributes=attrs, env_args=env_args or {},
318:                        format_version=format_version, compression=bool(compression))
319:             # Packing a large episode can take seconds; acknowledge any writes that
320:             # finished meanwhile so an idle writer is reused before scaling up.
321:             self.poll()
322:             self.used += size
323:             self.peak = max(self.peak, self.used)
324:             self.memories[key] = memory
325:             self.pending[key] = dict(job, submitted_at=time.monotonic())
326:             self.entries[key] = dict(job, status='submitted')
327:             self._manifest('running')
328:             self.jobs.put(job)
329:             self.emit('export_submitted', demo_id=index, env_id=env_id, memory_bytes=size,
330:                       packing_seconds=packed, queue_wait_seconds=waited, queue_memory_bytes=self.used)
331:             self._scale_workers()
332:         except BaseException:
333:             if key not in self.memories and not self.closed:
334:                 memory.close()
335:                 memory.unlink()
336:             raise
337:         return index
```

```text
339:     def finish(self):
340:         start = time.monotonic()
341:         try:
342:             while self.pending:
343:                 self.poll(wait=.05)
344:             for _ in self.processes:
345:                 self.jobs.put(None)
346:             for process in self.processes:
347:                 process.join(timeout=self.timeout)
348:                 if process.exitcode != 0:
349:                     raise RuntimeError(f'Writer shutdown failed: {process.pid}, exit={process.exitcode}')
350:             merge_start = time.monotonic()
351:             self._merge()
352:             self._manifest('complete', drain_seconds=merge_start - start,
353:                            merge_seconds=time.monotonic() - merge_start)
354:             shutil.rmtree(self.directory)
355:             self.closed = True
356:             self.jobs.close()
357:             self.jobs.join_thread()
358:             self.results.close()
359:             self.results.join_thread()
360:             self.emit('export_complete', saved_episodes=len(self.entries),
361:                       drain_seconds=merge_start - start, merge_seconds=time.monotonic() - merge_start,
362:                       peak_memory_bytes=self.peak, queue_wait_seconds=self.wait_seconds,
363:                       packing_seconds=self.pack_seconds, final_ready_seconds=time.monotonic() - self.started)
364:         except BaseException as exc:
365:             self.abort(str(exc))
366:             raise
367: 
368:     def _merge(self):
369:         import h5py
370:         staged = []
```

## v1 get_planned_poses 补充证据

```text
1593:             # Directly use the joint state from the plan to compute pose
1594:             # without advancing the main plan index in get_next_waypoint_ee_pose
1595:             next_joint_state: JointState = self._current_plan[self._plan_index]
1596:             self._plan_index += 1  # Manually advance index for this loop
1597:             eef_state: Any = self.motion_gen.compute_kinematics(next_joint_state)
1598:             planned_pose: Pose | None = eef_state.ee_pose
1599: 
1600:             if planned_pose is not None:
1601:                 # Convert pose to environment device for compatibility
1602:                 position = (
1603:                     self._to_env_device(planned_pose.position)
1604:                     if isinstance(planned_pose.position, torch.Tensor)
1605:                     else planned_pose.position
1606:                 )
1607:                 rotation = (
1608:                     self._to_env_device(planned_pose.get_rotation())
1609:                     if isinstance(planned_pose.get_rotation(), torch.Tensor)
1610:                     else planned_pose.get_rotation()
1611:                 )
1612:                 ee_pose_base = PoseUtils.make_pose(position, rotation)[0]
1613:                 planned_poses.append(self._pose_base_to_env(ee_pose_base))
1614: 
```
