# 执行等待计时源码证据

## datasets/efficiency_20261014_201834/v1/launchers/v1/telemetry.py

SHA-256：a6425d399ba0de11e8ef6233772a6af1117c99f8c62ed0249d7a7acbf2ab4e8c

```text
233:     original_execute = waypoint_class.execute
234: 
235:     @functools.wraps(original_execute)
236:     async def tracked_execute(self, *args, **kwargs):
237:         episode = _episode_context.get()
238:         started = time.monotonic()
239:         result = await original_execute(self, *args, **kwargs)
240:         if episode is not None:
241:             episode['execution_steps'] += 1
242:             episode['execution_wait_seconds'] += time.monotonic() - started
243:             episode['stage'] = 'execution'
244:             if episode['execution_steps'] % 100 == 0:
245:                 telemetry.emit('execution_progress', **telemetry.episode_values(episode),
246:                                execution_steps=episode['execution_steps'],
247:                                execution_wait_seconds=episode['execution_wait_seconds'])
248:         return result
249: 
250:     waypoint_class.execute = tracked_execute
```

```text
94:         self.emit('episode_cancelled' if cancelled else 'episode_finished',
95:                   **self.episode_values(episode), success=success, error=error,
96:                   duration_seconds=time.monotonic() - episode['started'],
97:                   planner_calls=episode['planner_calls'], planner_successes=episode['planner_successes'],
98:                   planner_failures=episode['planner_failures'],
99:                   curobo_solver_iterations=episode['solver_iterations'],
100:                   curobo_iteration_successes=episode['solver_successes'],
101:                   execution_steps=episode['execution_steps'], recorder_export_calls=episode['export_calls'],
102:                   simulated_seconds=episode['execution_steps'] * episode.get('step_dt', 0),
103:                   execution_steps_per_wall_second=(episode['execution_steps'] /
104:                                                    max(time.monotonic() - episode['started'], .001)),
105:                   simulation_seconds_per_wall_second=(episode['execution_steps'] * episode.get('step_dt', 0) /
106:                                                        max(time.monotonic() - episode['started'], .001)),
107:                   stages_seconds={**episode['stages_seconds'], 'execution_wait': episode['execution_wait_seconds']})
```

## autodata_core/waypoint.py

SHA-256：3e47b8fdccf54c9b20054037d45188dbda17b82d3a6cd88280028b59d42524ee

```text
288:     async def execute(
289:         self,
290:         datastream: Datastream,
291:         success_term: TerminationTermCfg,
292:         env_id: int = 0,
293:         env_action_queue: asyncio.Queue | None = None,
294:     ) -> bool:
295:         """Issue one env step from the assembled multi-EEF action.
296: 
297:         Action encoding is routed through the embodiment adapter (via Datastream). Env-side
298:         controller ops (``env.step``, ``env.scene.get_state``) are reached through the Datastream
299:         ``get_env()`` escape hatch — by design, they stay on env.
300: 
301:         Args:
302:             datastream: Composed datastream; provides action encoding and env access.
303:             success_term: Termination term used to check task success after the step.
304:             env_id: Vectorized env index.
305:             env_action_queue: If given, action is enqueued for the simulator-side loop instead of
306:                 stepped here.
307: 
308:         Returns:
309:             Whether the task succeeded after this step.
310:         """
311:         env = datastream.get_env()
312: 
313:         target_eef_pose_dict = {eef_name: waypoint.pose for eef_name, waypoint in self.waypoints.items()}
314:         action_noise_dict = {eef_name: waypoint.noise for eef_name, waypoint in self.waypoints.items()}
315:         passthrough_action_dict: dict[str, torch.Tensor] = {}
316:         for eef_name in sorted(self.waypoints):
317:             for channel_name, channel_tensor in self.waypoints[eef_name].passthrough_action.items():
318:                 passthrough_action_dict.setdefault(channel_name, channel_tensor)
319: 
320:         play_action = datastream.target_eef_pose_to_action(
321:             target_eef_pose_dict=target_eef_pose_dict,
322:             passthrough_action_dict=passthrough_action_dict,
323:             action_noise_dict=action_noise_dict,
324:             env_id=env_id,
325:         )
326: 
327:         if play_action.dim() == 1:
328:             play_action = play_action.unsqueeze(0)
329: 
330:         if env_action_queue is None:
331:             env.step(play_action)
332:         else:
333:             await env_action_queue.put((env_id, play_action[0]))
334:             await env_action_queue.join()
335: 
336:         return bool(success_term.func(env, **success_term.params)[env_id])
```

## autodata_interfaces/env/isaaclab_env_interface.py

SHA-256：eb4812da4cb418c82f8fb1fd4fef1e0bb569a43e4b077ba7e851194c4a5b157c

```text
245:     prev_num_attempts = 0
246:     # simulate environment -- run everything in inference mode
247:     with contextlib.suppress(KeyboardInterrupt) and torch.inference_mode():
248:         while True:
249:             # check if any environment needs to be reset while waiting for actions
250:             while env_action_queue.qsize() != env.num_envs:
251:                 asyncio_event_loop.run_until_complete(asyncio.sleep(0))
252:                 if data_gen_tasks is not None and data_gen_tasks.done():
253:                     exc = data_gen_tasks.exception()
254:                     if exc is not None:
255:                         raise exc
256:                     return False
257:                 while not env_reset_queue.empty():
258:                     env_id_tensor[0] = env_reset_queue.get_nowait()
259:                     env.reset(env_ids=env_id_tensor)
260:                     env_reset_queue.task_done()
261: 
262:             actions = torch.zeros(env.action_space.shape)
263: 
264:             # batch-fetch all per-env actions in one gather instead of sequential blocking calls
265:             get_tasks = [env_action_queue.get() for _ in range(env.num_envs)]
266:             results = asyncio_event_loop.run_until_complete(asyncio.gather(*get_tasks))
267:             for env_id, action in results:
268:                 actions[env_id] = action
269: 
270:             # perform action on environment
271:             env.step(actions)
272: 
273:             # mark done so the data generators can continue with the step results
274:             for _ in range(env.num_envs):
275:                 env_action_queue.task_done()
```
