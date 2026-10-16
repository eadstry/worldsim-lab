# 代码结构证据

当前源码与实验冻结实现分别标记；静态检查不等于新运行验证。

## submodules/IsaacLab-Arena/submodules/IsaacLab/source/isaaclab/isaaclab/managers/recorder_manager.py

当前上游源码；SHA-256：9d684f8d8f7a7dfa78307dea86b879eb2af8ea4a25913a1a692a3fb1d1de7150

```text
311:     def add_to_episodes(self, key: str, value: torch.Tensor | dict, env_ids: Sequence[int] | None = None):
312:         """Adds the given key-value pair to the episodes for the given environment ids.
313: 
314:         Args:
315:             key: The key of the given value to be added to the episodes. The key can contain nested keys
316:                 separated by '/'. For example, "obs/joint_pos" would add the given value under ['obs']['policy']
317:                 in the underlying dictionary in the episode data.
318:             value: The value to be added to the episodes. The value can be a tensor or a nested dictionary of tensors.
319:                 The shape of a tensor in the value is (env_ids, ...).
320:             env_ids: The environment ids. Defaults to None, in which case all environments are considered.
321:         """
322:         # Do nothing if no active recorder terms are provided
323:         if len(self.active_terms) == 0:
324:             return
325: 
326:         # resolve environment ids
327:         if key is None:
328:             return
329:         if env_ids is None:
330:             env_ids = list(range(self._env.num_envs))
331:         if isinstance(env_ids, torch.Tensor):
332:             env_ids = env_ids.tolist()
333: 
334:         if isinstance(value, dict):
335:             for sub_key, sub_value in value.items():
336:                 if isinstance(sub_value, wp.array):
337:                     sub_value = wp.to_torch(sub_value)
338:                 self.add_to_episodes(f"{key}/{sub_key}", sub_value, env_ids)
339:             return
340: 
341:         if isinstance(value, wp.array):
342:             value = wp.to_torch(value)
343:         value = value.clone()  # Clone once for all envs
344:         for value_index, env_id in enumerate(env_ids):
345:             if env_id not in self._episodes:
346:                 self._episodes[env_id] = EpisodeData()
347:                 self._episodes[env_id].env_id = env_id
348:             self._episodes[env_id].add(key, value[value_index], clone=False)
```

```text
461:     def export_episodes(self, env_ids: Sequence[int] | None = None, demo_ids: Sequence[int] | None = None) -> None:
462:         """Concludes and exports the episodes for the given environment ids.
463: 
464:         Args:
465:             env_ids: The environment ids. Defaults to None, in which case
466:                 all environments are considered.
467:             demo_ids: Custom identifiers for the exported episodes.
468:                 If provided, episodes will be named "demo_{demo_id}" in the dataset.
469:                 Should have the same length as env_ids if both are provided.
470:                 If None, uses the default sequential naming scheme. Defaults to None.
471:         """
472:         # Do nothing if no active recorder terms are provided
473:         if len(self.active_terms) == 0:
474:             return
475: 
476:         if env_ids is None:
477:             env_ids = list(range(self._env.num_envs))
478:         if isinstance(env_ids, torch.Tensor):
479:             env_ids = env_ids.tolist()
480: 
481:         # Handle demo_ids processing
482:         if demo_ids is not None:
483:             if isinstance(demo_ids, torch.Tensor):
484:                 demo_ids = demo_ids.tolist()
485:             if len(demo_ids) != len(env_ids):
486:                 raise ValueError(f"Length of demo_ids ({len(demo_ids)}) must match length of env_ids ({len(env_ids)})")
487:             # Check for duplicate demo_ids
488:             if len(set(demo_ids)) != len(demo_ids):
489:                 duplicates = [x for i, x in enumerate(demo_ids) if demo_ids.index(x) != i]
490:                 raise ValueError(f"demo_ids must be unique. Found duplicates: {list(set(duplicates))}")
491: 
492:         # Export episode data through dataset exporter
493:         need_to_flush = False
494: 
495:         if any(env_id in self._episodes and not self._episodes[env_id].is_empty() for env_id in env_ids):
496:             ep_meta = self.get_ep_meta()
497:             if self._dataset_file_handler is not None:
498:                 self._dataset_file_handler.add_env_args(ep_meta)
499:             if self._failed_episode_dataset_file_handler is not None:
500:                 self._failed_episode_dataset_file_handler.add_env_args(ep_meta)
501: 
502:         for i, env_id in enumerate(env_ids):
503:             if env_id in self._episodes and not self._episodes[env_id].is_empty():
504:                 self._episodes[env_id].pre_export()
505: 
506:                 episode_succeeded = self._episodes[env_id].success
507:                 target_dataset_file_handler = None
508:                 if (self.cfg.dataset_export_mode == DatasetExportMode.EXPORT_ALL) or (
509:                     self.cfg.dataset_export_mode == DatasetExportMode.EXPORT_SUCCEEDED_ONLY and episode_succeeded
510:                 ):
511:                     target_dataset_file_handler = self._dataset_file_handler
512:                 elif self.cfg.dataset_export_mode == DatasetExportMode.EXPORT_SUCCEEDED_FAILED_IN_SEPARATE_FILES:
513:                     if episode_succeeded:
514:                         target_dataset_file_handler = self._dataset_file_handler
515:                     else:
516:                         target_dataset_file_handler = self._failed_episode_dataset_file_handler
517:                 if target_dataset_file_handler is not None:
518:                     # Use corresponding demo_id if provided, otherwise None
519:                     current_demo_id = demo_ids[i] if demo_ids is not None else None
520:                     target_dataset_file_handler.write_episode(
521:                         self._episodes[env_id], current_demo_id, self.cfg.dataset_compression
522:                     )
523:                     need_to_flush = True
524:                 # Update episode count
525:                 if episode_succeeded:
526:                     self._exported_successful_episode_count[env_id] = (
527:                         self._exported_successful_episode_count.get(env_id, 0) + 1
528:                     )
529:                 else:
530:                     self._exported_failed_episode_count[env_id] = self._exported_failed_episode_count.get(env_id, 0) + 1
531:             # Reset the episode buffer for the given environment after export
532:             self._episodes[env_id] = EpisodeData()
533: 
534:         if need_to_flush:
535:             if self._dataset_file_handler is not None:
536:                 self._dataset_file_handler.flush()
537:             if self._failed_episode_dataset_file_handler is not None:
538:                 self._failed_episode_dataset_file_handler.flush()
```

## submodules/IsaacLab-Arena/submodules/IsaacLab/source/isaaclab/isaaclab/utils/datasets/episode_data.py

当前上游源码；SHA-256：5c75e6681240e35515d1c23767f789267d79375b6f36b2ac4b60c858606ded28

```text
207:     def pre_export(self):
208:         """Prepare data for export by converting lists to tensors."""
209: 
210:         def pre_export_helper(data):
211:             for key, value in data.items():
212:                 if isinstance(value, list):
213:                     data[key] = torch.stack(value)
214:                 elif isinstance(value, dict):
215:                     pre_export_helper(value)
216: 
217:         pre_export_helper(self._data)
```

## submodules/IsaacLab-Arena/submodules/IsaacLab/source/isaaclab/isaaclab/utils/datasets/hdf5_dataset_file_handler.py

当前上游源码；SHA-256：b5c4365cfd46107dfe56288b092bbdb03d993dbb83e23415742965db7df8d793

```text
213:     def write_episode(self, episode: EpisodeData, demo_id: int | None = None, dataset_compression: bool = True):
214:         """Add an episode to the dataset.
215: 
216:         Args:
217:             episode: The episode data to add.
218:             demo_id: Custom index for the episode. If None, uses default index.
219:         """
220:         self._raise_if_not_initialized()
221:         if episode.is_empty():
222:             return
223: 
224:         # Use custom demo id if provided, otherwise use default naming
225:         if demo_id is not None:
226:             episode_group_name = f"demo_{demo_id}"
227:         else:
228:             episode_group_name = f"demo_{self._demo_count}"
229: 
230:         # create episode group with the specified name
231:         if episode_group_name in self._hdf5_data_group:
232:             raise ValueError(f"Episode group '{episode_group_name}' already exists in the dataset")
233:         h5_episode_group = self._hdf5_data_group.create_group(episode_group_name)
234: 
235:         # store number of steps taken
236:         if "actions" in episode.data:
237:             h5_episode_group.attrs["num_samples"] = len(episode.data["actions"])
238:         else:
239:             h5_episode_group.attrs["num_samples"] = 0
240: 
241:         if episode.seed is not None:
242:             h5_episode_group.attrs["seed"] = episode.seed
243: 
244:         if episode.success is not None:
245:             h5_episode_group.attrs["success"] = episode.success
246: 
247:         def create_dataset_helper(group, key, value):
248:             """Helper method to create dataset that contains recursive dict objects."""
249:             if isinstance(value, dict):
250:                 key_group = group.create_group(key)
251:                 for sub_key, sub_value in value.items():
252:                     create_dataset_helper(key_group, sub_key, sub_value)
253:             else:
254:                 if dataset_compression:
255:                     group.create_dataset(key, data=value.cpu().numpy(), compression="gzip", compression_opts=2)
256:                 else:
257:                     group.create_dataset(key, data=value.cpu().numpy())
258: 
259:         for key, value in episode.data.items():
260:             create_dataset_helper(h5_episode_group, key, value)
261: 
262:         # increment total step counts
263:         self._hdf5_data_group.attrs["total"] += h5_episode_group.attrs["num_samples"]
264: 
265:         # Only increment demo count if using default indexing
266:         if demo_id is None:
267:             # increment total demo counts
268:             self._demo_count += 1
```

```text
270:     def flush(self):
271:         """Flush the episode data to disk."""
272:         self._raise_if_not_initialized()
273: 
274:         self._hdf5_file_stream.flush()
```

## datasets/efficiency_20261014_201834/v1/launchers/v1/generate.py

冻结 launcher；SHA-256：028a03f3c75fe46131bd03f17634cb6ed44ae0f4f7274e01ba4fe41d92195ff4

```text
11: def build_source(source, args):
12:     if args.debug_planner:
13:         anchor_debug = "planner_config = CuroboPlannerCfg.from_profile(planner_profile)"
14:         assert source.count(anchor_debug) == 1
15:         source = source.replace(anchor_debug, anchor_debug + "\n            planner_config.debug_planner = True", 1)
16:     anchor = "simulation_app = app_launcher.app"
17:     assert source.count(anchor) == 1, "Upstream launcher changed; review the integration hook"
18:     source = source.replace(anchor, anchor + "\nfrom compat import install\ninstall()", 1)
19:     policy_anchor = "generation_policy_params = task_descriptor.get_generation_policy()"
20:     assert source.count(policy_anchor) == 1
21:     source = source.replace(policy_anchor, policy_anchor + f"""
22:     generation_policy_params.num_steps_final_hold = {args.final_hold_steps}
23:     from telemetry import record_policy
24:     record_policy(generation_policy_params, {args.generation_num_trials}, {args.num_envs})
25: """, 1)
26:     counter = '        stats["num_attempts"] += 1'
27:     assert source.count(counter) == 1, "Upstream attempt accounting changed; review the failure limit"
28:     source = source.replace(counter, counter + '''
29:         failure_limit = data_generator.datastream.get_generation_policy().max_num_failures
30:         if stats["num_failures"] >= failure_limit:
31:             raise RuntimeError(f"OpenArm generation reached failure limit {failure_limit}")
32: ''', 1)
33:     if args.export_workers:
34:         import json
35:         os.environ["OPENARM_ASYNC_EXPORT"] = json.dumps(dict(
36:             output=str(args.output_file.resolve()), workers=args.export_workers,
37:             memory_gib=args.export_queue_memory_gib, timeout=args.export_timeout_seconds))
38:         env_anchor = "    env = gym.make(env_name, cfg=env_cfg).unwrapped"
39:         assert source.count(env_anchor) == 1
40:         source = source.replace(env_anchor, """    from async_export import configure, attach
41:     import json, os
42:     configure(env_cfg)
43: """ + env_anchor + """
44:     attach(env.recorder_manager, json.loads(os.environ['OPENARM_ASYNC_EXPORT']))
45: """, 1)
46:         finish_anchor = "        if generation_completed and args_cli.result_file:"
47:         assert source.count(finish_anchor) == 1
48:         source = source.replace(finish_anchor, """        if not generation_completed:
49:             raise RuntimeError('Generation ended before target; async shards retained')
50:         from async_export import finish
51:         finish(expected_successes=async_components["stats"]["num_success"])
52: """ + finish_anchor, 1)
53:     else:
54:         os.environ.pop("OPENARM_ASYNC_EXPORT", None)
55:     close_anchor = "        env.close()"
56:     assert source.count(close_anchor) == 1
57:     source = source.replace(close_anchor, close_anchor + """
58:         if locals().get('generation_completed', False):
59:             from telemetry import record_output_ready
60:             record_output_ready()
61: """, 1)
62:     return source
```

## datasets/efficiency_20261014_201834/v1/launchers/v1/compat.py

冻结兼容层；SHA-256：0f7df8d7a65f1178645aa02c53d733baa2dfc13e0a5435d81b54235d16f6023a

```text
44: def install_generation_compat():
45:     """Preserve completion checks when planning returns without enqueuing an action."""
46:     import inspect
47:     import textwrap
48:     from autodata_interfaces import env as env_exports
49:     from autodata_interfaces.env import isaaclab_env_interface
50:     from autodata_core import data_generator
51: 
52:     source = textwrap.dedent(inspect.getsource(isaaclab_env_interface.env_loop))
53:     anchor = "                asyncio_event_loop.run_until_complete(asyncio.sleep(0))"
54:     assert source.count(anchor) == 1
55:     source = source.replace(anchor, anchor + '''
56:                 completed = stats["num_success"] if guarantee_success else stats["num_attempts"]
57:                 if completed >= num_trials:
58:                     return True
59:                 if stats["num_failures"] >= generation_policy_params.max_num_failures:
60:                     raise RuntimeError("OpenArm generation reached its configured failure limit")
61: ''', 1)
62:     import os
63:     if os.environ.get("OPENARM_ASYNC_EXPORT"):
64:         source = source.replace("        while True:\n", "        while True:\n            from async_export import poll\n            poll()\n", 1)
65:         source = source.replace(anchor, anchor + "\n                from async_export import poll\n                poll()", 1)
66:     scope = {}
67:     exec(compile(source, "<openarm-env-loop>", "exec"), vars(isaaclab_env_interface), scope)
68:     isaaclab_env_interface.env_loop = scope["env_loop"]
69:     env_exports.env_loop = scope["env_loop"]
70: 
71:     source = textwrap.dedent(inspect.getsource(data_generator.DataGenerator.generate))
72:     anchor = "    # Recorder lifecycle stays on env by design:"
73:     assert source.count(anchor) == 1
74:     source = source.replace(anchor, '''    final_hold_steps = self.datastream.get_generation_policy().num_steps_final_hold
75:     assert final_hold_steps >= 0
76:     for _ in range(final_hold_steps):
77:         exec_success = await multi_waypoint.execute(
78:             datastream=self.datastream, success_term=success_term,
79:             env_id=env_id, env_action_queue=env_action_queue,
80:         )
81:         buffers.success = buffers.success or exec_success
82: 
83: ''' + anchor, 1)
84:     scope = {}
85:     exec(compile(source, "<openarm-final-hold>", "exec"), vars(data_generator), scope)
86:     data_generator.DataGenerator.generate = scope["generate"]
```

## datasets/efficiency_20261014_201834/v1/launchers/v1/async_export.py

冻结保存桥；SHA-256：b44c38db5f28faecc316369e5bfafa73d627eeddf26eb757a1dcce26a2da6573

```text
15: class MetadataHandler:
16:     """Recorder-compatible metadata sink; workers own actual HDF5 handles."""
17:     def __init__(self):
18:         self.path = None
19:         self._env_args = {}
20:         self._demo_count = 0
21: 
22:     def create(self, file_path, env_name=None):
23:         self.path = Path(file_path if file_path.endswith('.hdf5') else file_path + '.hdf5')
24:         self.add_env_args(dict(env_name=env_name or '', type=2))
25: 
26:     def add_env_args(self, values):
27:         self._env_args.update(values)
28: 
29:     def close(self):
30:         pass
31: 
32:     @property
33:     def demo_count(self):
34:         return self._demo_count
```

```text
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
```

```text
58: def configure(env_cfg):
59:     from isaaclab.managers.recorder_manager import RecorderManager
60:     RecorderManager.add_to_episodes = owned_recording_method(RecorderManager.add_to_episodes)
61:     env_cfg.recorders.dataset_file_handler_class_type = MetadataHandler
```

```text
70: def attach(recorder, settings):
71:     global _active
72:     _active = Bridge(recorder, settings)
73:     atexit.register(abort, 'Process exited before async export completed')
```

```text
76: class Bridge:
77:     def __init__(self, recorder, settings):
78:         from isaaclab.managers.recorder_manager import DatasetExportMode
79:         from isaaclab.utils.datasets import EpisodeData
80:         from isaaclab.utils.datasets.hdf5_dataset_file_handler import DATASET_FORMAT_VERSION
81:         self.recorder = recorder
82:         self.mode_class = DatasetExportMode
83:         self.episode_class = EpisodeData
84:         self.format_version = DATASET_FORMAT_VERSION
85:         self.pool = ExportPool(settings['output'], workers=settings['workers'],
86:                                memory_bytes=int(settings['memory_gib'] * 1024**3),
87:                                timeout=settings['timeout'], emit=emit)
88:         recorder.export_episodes = MethodType(lambda instance, *a, **k: self.export(*a, **k), recorder)
89:         self.saved_seen = set()
90: 
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
102:             env_id = entry['env_id']
103:             counters[env_id] = counters.get(env_id, 0) + 1
104: 
105:     def export(self, env_ids=None, demo_ids=None):
106:         recorder, modes = self.recorder, self.mode_class
107:         self.poll()
108:         if not recorder.active_terms:
109:             return
110:         env_ids = list(range(recorder._env.num_envs)) if env_ids is None else list(map(int, env_ids))
111:         if demo_ids is not None:
112:             demo_ids = list(map(int, demo_ids))
113:             assert len(demo_ids) == len(env_ids) and len(set(demo_ids)) == len(demo_ids)
114:         for index, env_id in enumerate(env_ids):
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
```

```text
147: def finish(expected_successes=None):
148:     if _active is not None and not _active.pool.closed:
149:         if expected_successes is not None:
150:             submitted_successes = sum(e['attributes'].get('success') is True for e in _active.pool.entries.values())
151:             assert submitted_successes == expected_successes, 'Generated/submitted success count mismatch'
152:         _active.pool.finish()
153:         _active.update_counters()
```

## datasets/efficiency_20261014_201834/v1/launchers/v1/export_pool.py

冻结保存池；SHA-256：ef03ef54bbbc7276205b15030358ee691fc3f422c6449f263acd8c7887768aef

```text
29: def layout(data):
30:     leaves = []
31:     offset = 0
32: 
33:     def visit(values, prefix=''):
34:         nonlocal offset
35:         for key, value in values.items():
36:             name = f'{prefix}/{key}' if prefix else key
37:             if isinstance(value, dict):
38:                 visit(value, name)
39:                 continue
40:             if isinstance(value, list):
41:                 assert value, f'Empty recorder list: {name}'
42:                 first = array(value[0])
43:                 shape, dtype = (len(value), *first.shape), first.dtype
44:             else:
45:                 first = array(value)
46:                 shape, dtype = first.shape, first.dtype
47:             assert not dtype.hasobject, f'Object arrays are unsupported: {name}'
48:             offset = (offset + 63) // 64 * 64
49:             size = int(np.prod(shape)) * dtype.itemsize
50:             leaves.append(dict(path=name, shape=list(shape), dtype=dtype.str, offset=offset, bytes=size))
51:             offset += size
52: 
53:     visit(data)
54:     return leaves, max(offset, 1)
```

```text
77: def pack(data, leaves, memory, release_source=False):
78:     for leaf in leaves:
79:         value = data
80:         for key in leaf['path'].split('/'):
81:             value = value[key]
82:         target = np.ndarray(leaf['shape'], dtype=leaf['dtype'], buffer=memory.buf, offset=leaf['offset'])
83:         if isinstance(value, list) and getattr(value[0], 'is_cuda', False):
84:             # RGB is already CPU-resident. Batch the small GPU state fields to
85:             # avoid thousands of individual device synchronizations per episode.
86:             import torch
87:             np.copyto(target, torch.stack(value).detach().cpu().numpy(), casting='no')
88:             if release_source:
89:                 value.clear()
90:         elif isinstance(value, list):
91:             released = 0
92:             for index, frame in enumerate(value):
93:                 source = array(frame)
94:                 assert source.shape == target.shape[1:] and source.dtype == target.dtype, leaf['path']
95:                 np.copyto(target[index:index + 1], source.reshape((1, *source.shape)), casting='no')
96:                 if release_source:
97:                     released += source.nbytes
98:                     value[index] = None
99:                     del source, frame
100:                     if released >= 64 * 1024**2:
101:                         trim_free_memory()
102:                         released = 0
103:             if release_source:
104:                 value.clear()
105:                 trim_free_memory()
106:         else:
107:             np.copyto(target, array(value), casting='no')
```

```text
110: def write_job(job, handles, directory):
111:     import h5py
112: 
113:     route = job['route']
114:     if route not in handles:
115:         file = h5py.File(Path(directory) / f'worker-{os.getpid()}-{route}.hdf5', 'x')
116:         file.attrs['format_version'] = job['format_version']
117:         data = file.create_group('data')
118:         data.attrs['total'] = 0
119:         handles[route] = file
120:     file = handles[route]
121:     file['data'].attrs['env_args'] = json.dumps(job['env_args'])
122:     memory = SharedMemory(name=job['memory'])
123:     group = file.create_group(f'_pending_{job["demo_id"]}')
124:     view = None
125:     try:
126:         for name in job.get('empty_groups', []):
127:             group.require_group(name)
128:         for leaf in job['leaves']:
129:             view = np.ndarray(leaf['shape'], dtype=leaf['dtype'], buffer=memory.buf, offset=leaf['offset'])
130:             view.flags.writeable = False
131:             parent, _, key = leaf['path'].rpartition('/')
132:             options = dict(compression='gzip', compression_opts=2) if job['compression'] else {}
133:             destination = group.require_group(parent) if parent else group
134:             destination.create_dataset(key, data=view, **options)
135:             view = None
136:         for key, value in job['attributes'].items():
137:             group.attrs[key] = value
138:         file.move(group.name, f'/data/demo_{job["demo_id"]}')
139:         file['data'].attrs['total'] += job['attributes']['num_samples']
140:         file.flush()
141:         return str(Path(file.filename)), int(os.stat(file.filename).st_size)
142:     finally:
143:         view = None
144:         memory.close()
```

```text
147: def writer(jobs, results, directory, parent_pid):
148:     """Spawn entrypoint: no Isaac Sim, torch or CUDA imports."""
149:     handles = {}
150:     try:
151:         while True:
152:             if os.getppid() != parent_pid:
153:                 return
154:             try:
155:                 job = jobs.get(timeout=1)
156:             except queue.Empty:
157:                 if os.getppid() != parent_pid:
158:                     return
159:                 continue
160:             if job is None:
161:                 return
162:             start = time.monotonic()
163:             results.put(dict(kind='started', key=job['key'], worker_pid=os.getpid()))
164:             try:
165:                 shard, size = write_job(job, handles, directory)
166:                 results.put(dict(kind='saved', key=job['key'], shard=shard, shard_bytes=size,
167:                                  worker_pid=os.getpid(), write_seconds=time.monotonic() - start))
168:             except BaseException as exc:
169:                 results.put(dict(kind='failed', key=job['key'], error=f'{type(exc).__name__}: {exc}'))
170:                 raise
171:     finally:
172:         for file in handles.values():
173:             file.close()
```

```text
176: class ExportPool:
177:     def __init__(self, output, workers=2, memory_bytes=16 * 1024**3, timeout=600,
178:                  emit=None, worker_target=writer, resource_governor=None):
179:         self.output = Path(output).resolve()
180:         self.directory = self.output.with_suffix('.export-parts')
181:         self.manifest = self.output.with_suffix('.export.json')
182:         assert (workers == 'auto' or workers > 0) and memory_bytes > 0 and timeout > 0
183:         assert not self.output.exists() and not self.directory.exists() and not self.manifest.exists()
184:         check_export_capacity(memory_bytes)
185:         self.directory.mkdir(parents=True)
186:         self.limit, self.timeout = int(memory_bytes), timeout
187:         self.emit = emit or (lambda *args, **kwargs: None)
188:         self.started = time.monotonic()
189:         self.pending, self.entries, self.memories, self.next_ids, self.outputs = {}, {}, {}, {}, {}
190:         self.used = self.peak = 0
191:         self.wait_seconds = self.pack_seconds = 0.0
192:         self.closed = False
193:         self.context = mp.get_context('spawn')
194:         self.jobs, self.results = self.context.Queue(), self.context.Queue()
195:         self.max_workers = None if workers == 'auto' else int(workers)
196:         self.governor = (resource_governor or ResourceGovernor()) if workers == 'auto' else None
197:         self.scaling_policy = 'server_resources' if self.governor is not None else 'on_demand'
198:         self.admission = None
199:         self.worker_target = worker_target
200:         self.processes = []
201:         self._manifest('starting')
202:         self.emit('export_pool_started', workers=0, max_workers=self.max_workers,
203:                   scaling_policy=self.scaling_policy, memory_limit_bytes=self.limit, worker_pids=[])
204: 
205:     def _scale_workers(self):
206:         # Pending includes queued and writing jobs, including workers still starting.
207:         # Account for all of them without relying on multiprocessing.Queue.qsize().
208:         desired = len(self.pending)
209:         if desired <= len(self.processes):
210:             return
211:         if self.governor is not None:
212:             decision = self.governor.decide(self.processes, self.pending, self.output)
213:             if decision is None:
214:                 return
215:             previous_reason = self.admission.get('reason') if self.admission else None
216:             self.admission = decision
217:             if decision['reason'] != previous_reason:
218:                 self.emit('export_scaling_decision', workers=len(self.processes), **decision)
219:                 self._manifest('running')
220:             if not decision['allow']:
221:                 return
222:             desired = len(self.processes) + 1
223:         else:
224:             desired = min(desired, self.max_workers)
225:         try:
226:             while len(self.processes) < desired:
227:                 process = self.context.Process(target=self.worker_target,
228:                     args=(self.jobs, self.results, str(self.directory), os.getpid()), daemon=True)
229:                 self.processes.append(process)
230:                 process.start()
231:                 self.emit('export_worker_started', worker_pid=process.pid, workers=len(self.processes),
232:                           max_workers=self.max_workers, pending_episodes=len(self.pending))
233:                 self._manifest('running')
234:         except BaseException as exc:
235:             self.abort(f'Worker startup failed: {type(exc).__name__}: {exc}')
236:             raise
237: 
238:     def _manifest(self, status, **extra):
239:         value = dict(status=status, output=str(self.output), entries=list(self.entries.values()),
240:                      scaling_policy=self.scaling_policy, max_workers=self.max_workers,
241:                      resource_admission=self.admission,
242:                      worker_pids=[p.pid for p in self.processes if p.pid is not None],
243:                      memory_limit_bytes=self.limit, peak_memory_bytes=self.peak,
244:                      queue_wait_seconds=self.wait_seconds, packing_seconds=self.pack_seconds,
245:                      elapsed_seconds=time.monotonic() - self.started, **extra)
246:         temporary = self.manifest.with_suffix('.json.tmp')
247:         temporary.write_text(json.dumps(value, indent=2, default=str) + '\n')
248:         temporary.replace(self.manifest)
249: 
250:     def poll(self, wait=0):
251:         assert not self.closed, 'Export pool is closed'
252:         first = True
253:         while True:
254:             try:
255:                 row = self.results.get(timeout=wait if first else 0)
256:             except queue.Empty:
257:                 break
258:             first = False
259:             key = row['key']
260:             if row['kind'] == 'failed':
261:                 raise RuntimeError(f'Export {key} failed: {row["error"]}')
262:             if row['kind'] == 'started':
263:                 self.pending[key]['writing_started'] = time.monotonic()
264:                 self.emit('export_write_started', **row)
265:             elif row['kind'] == 'saved':
266:                 job = self.pending.pop(key)
267:                 self.entries[key].update(status='saved', **row)
268:                 memory = self.memories.pop(key)
269:                 memory.close()
270:                 memory.unlink()
271:                 self.used -= job['memory_bytes']
272:                 self.emit('export_saved', demo_id=job['demo_id'], env_id=job.get('env_id'),
273:                           queue_memory_bytes=self.used, **row)
274:                 self._manifest('running')
275:         for process in self.processes:
276:             if process.exitcode is not None:
277:                 raise RuntimeError(f'Export worker {process.pid} exited unexpectedly: {process.exitcode}')
278:         now = time.monotonic()
279:         for key, job in self.pending.items():
280:             if now - job.get('writing_started', job['submitted_at']) > self.timeout:
281:                 reason = self.admission.get('reason') if self.admission else None
282:                 raise TimeoutError(f'Export {key} exceeded {self.timeout}s; resource admission: {reason}')
283:         self._scale_workers()
284: 
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
338: 
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
371:         for route, path in self.outputs.items():
372:             entries = sorted((e for e in self.entries.values() if e['route'] == route), key=lambda e: e['demo_id'])
373:             temporary = Path(path).with_suffix('.partial.hdf5')
374:             assert not temporary.exists() and not Path(path).exists()
375:             with h5py.File(temporary, 'x') as destination:
376:                 destination.attrs['format_version'] = entries[0]['format_version']
377:                 data = destination.create_group('data')
378:                 data.attrs['env_args'] = json.dumps(entries[-1]['env_args'])
379:                 data.attrs['total'] = sum(e['attributes']['num_samples'] for e in entries)
380:                 for entry in entries:
381:                     assert entry['status'] == 'saved'
382:                     name = f'demo_{entry["demo_id"]}'
383:                     with h5py.File(entry['shard'], 'r') as source:
384:                         source.copy(source[f'data/{name}'], data, name=name)
385:                     copied = data[name]
386:                     assert dict(copied.attrs) == entry['attributes']
387:                     for name in entry.get('empty_groups', []):
388:                         assert isinstance(copied[name], h5py.Group) and not len(copied[name])
389:                     for leaf in entry['leaves']:
390:                         value = copied[leaf['path']]
391:                         assert list(value.shape) == leaf['shape'] and value.dtype.str == leaf['dtype']
392:                         assert value.compression == ('gzip' if entry['compression'] else None)
393:                 assert len(data) == len(entries)
394:             staged.append((temporary, Path(path)))
395:         for temporary, output in staged:
396:             os.link(temporary, output)  # Atomic publication, refuses overwrite.
397:             temporary.unlink()
398: 
399:     def abort(self, reason):
400:         if self.closed:
401:             return
402:         for process in self.processes:
403:             if process.pid is not None and process.is_alive():
404:                 process.terminate()
405:         for process in self.processes:
406:             if process.pid is not None:
407:                 process.join(timeout=5)
408:                 if process.is_alive():
409:                     process.kill()
410:                     process.join(timeout=5)
411:         for memory in self.memories.values():
412:             memory.close()
413:             memory.unlink()
414:         self.memories.clear()
415:         self.pending.clear()
416:         self.used = 0
417:         self.closed = True
418:         self._manifest('failed', error=reason)
419:         for channel in (self.jobs, self.results):
420:             channel.cancel_join_thread()
421:             channel.close()
```
