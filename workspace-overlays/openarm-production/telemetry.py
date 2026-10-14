# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Episode, stage and actual cuRobo iteration journals, installed by the overlay."""
from __future__ import annotations

import asyncio
import atexit
import contextvars
import functools
import json
import os
import threading
import time
import uuid
from pathlib import Path

from monitor import append_json, atomic_json, summarize, utc_now

_episode_context = contextvars.ContextVar('openarm_episode', default=None)
_request_context = contextvars.ContextVar('openarm_request', default=None)
_active = None


def record_policy(policy, num_trials, num_envs):
    if _active is not None:
        _active.emit('generation_policy', requested_trials=num_trials, num_envs=num_envs,
                     guarantee_success=policy.guarantee_success,
                     max_failures=policy.max_num_failures, final_hold_steps=policy.num_steps_final_hold)


def error_text(exc):
    return f'{type(exc).__name__}: {exc}'


def result_success(result):
    try:
        return bool(result.success.all().item())
    except (AttributeError, TypeError, RuntimeError):
        return None


class Telemetry:
    def __init__(self, path, sample_interval=10):
        self.path = path
        self.summary_path = path.with_suffix('').with_suffix('.telemetry-summary.json')
        self.started = time.monotonic()
        self.run_id = os.environ.get('OPENARM_RUN_ID', uuid.uuid4().hex)
        self.interval = sample_interval
        self.lock = threading.RLock()
        self.rows = []
        self.episodes = {}
        self.env_attempts = {}
        self.request_count = 0
        self.stop_event = threading.Event()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.emit('telemetry_started', pid=os.getpid(), sample_interval_seconds=sample_interval,
                  config=json.loads(os.environ.get('OPENARM_RUN_CONFIG', '{}')),
                  timing_semantics='host wall seconds; asynchronous execution includes queue wait; GPU kernels are not explicitly synchronized')
        self.thread = threading.Thread(target=self._heartbeat, name='openarm-telemetry', daemon=True)
        self.thread.start()
        atexit.register(self.close)

    def emit(self, event, **values):
        row = {'schema_version': 2, 'run_id': self.run_id, 'time_utc': utc_now(),
               'elapsed_seconds': round(time.monotonic() - self.started, 6), 'event': event, **values}
        with self.lock:
            append_json(self.path, row)
            self.rows.append(row)
        return row

    def episode_values(self, episode):
        return {'episode_id': episode['key'], 'env_id': episode['env_id']}

    def start_episode(self, env_id):
        with self.lock:
            attempt = self.env_attempts.get(env_id, 0) + 1
            self.env_attempts[env_id] = attempt
            key = f'env{env_id}-attempt{attempt}'
            episode = {'key': key, 'env_id': env_id, 'started': time.monotonic(),
                       'planner_calls': 0, 'planner_successes': 0, 'planner_failures': 0,
                       'solver_iterations': 0, 'solver_successes': 0,
                       'execution_steps': 0, 'execution_wait_seconds': 0.0,
                       'stages_seconds': {}, 'stage': 'reset', 'export_calls': 0}
            self.episodes[key] = episode
        self.emit('episode_started', **self.episode_values(episode), attempt_in_env=attempt)
        return episode

    def finish_episode(self, episode, success, error=None, cancelled=False):
        self.emit('episode_cancelled' if cancelled else 'episode_finished',
                  **self.episode_values(episode), success=success, error=error,
                  duration_seconds=time.monotonic() - episode['started'],
                  planner_calls=episode['planner_calls'], planner_successes=episode['planner_successes'],
                  planner_failures=episode['planner_failures'],
                  curobo_solver_iterations=episode['solver_iterations'],
                  curobo_iteration_successes=episode['solver_successes'],
                  execution_steps=episode['execution_steps'], recorder_export_calls=episode['export_calls'],
                  simulated_seconds=episode['execution_steps'] * episode.get('step_dt', 0),
                  execution_steps_per_wall_second=(episode['execution_steps'] /
                                                   max(time.monotonic() - episode['started'], .001)),
                  simulation_seconds_per_wall_second=(episode['execution_steps'] * episode.get('step_dt', 0) /
                                                       max(time.monotonic() - episode['started'], .001)),
                  stages_seconds={**episode['stages_seconds'], 'execution_wait': episode['execution_wait_seconds']})
        with self.lock:
            self.episodes.pop(episode['key'], None)
        self.write_summary()

    def stage_started(self, episode, stage):
        previous = episode['stage']
        episode['stage'] = stage
        self.emit('stage_started', **self.episode_values(episode), stage=stage)
        return time.monotonic(), previous

    def stage_finished(self, episode, stage, started, previous, error=None):
        duration = time.monotonic() - started
        episode['stages_seconds'][stage] = episode['stages_seconds'].get(stage, 0) + duration
        episode['stage'] = previous if previous != 'reset' else 'execution'
        self.emit('stage_finished', **self.episode_values(episode), stage=stage,
                  duration_seconds=duration, error=error)

    def write_summary(self):
        with self.lock:
            value = summarize(self.rows, elapsed=time.monotonic() - self.started)
            atomic_json(self.summary_path, value)

    def _heartbeat(self):
        while not self.stop_event.wait(self.interval):
            try:
                with self.lock:
                    active = [{'episode_id': e['key'], 'env_id': e['env_id'], 'stage': e['stage'],
                               'age_seconds': time.monotonic() - e['started'],
                               'execution_steps': e['execution_steps'],
                               'simulated_seconds': e['execution_steps'] * e.get('step_dt', 0),
                               'execution_wait_seconds': e['execution_wait_seconds']}
                              for e in self.episodes.values()]
                self.emit('heartbeat', active_episodes=active)
                self.write_summary()
            except Exception as exc:
                print(f'OpenArm telemetry heartbeat error: {exc}', flush=True)

    def close(self):
        if self.stop_event.is_set():
            return
        self.stop_event.set()
        self.thread.join(timeout=2)
        self.emit('telemetry_closed', unfinished_episode_ids=list(self.episodes))
        self.write_summary()


def install(data_generator_module, planner_module, path):
    global _active
    assert _active is None, 'Telemetry was already installed'
    telemetry = _active = Telemetry(path, float(os.environ.get('OPENARM_LOG_INTERVAL', '10')))
    generator_class = data_generator_module.DataGenerator
    original_generate = generator_class.generate

    @functools.wraps(original_generate)
    async def tracked_generate(self, env_id, *args, **kwargs):
        episode = telemetry.start_episode(int(env_id))
        episode['step_dt'] = float(getattr(self.datastream.get_env(), 'step_dt', 0))
        token = _episode_context.set(episode)
        success, error, cancelled = None, None, False
        # Recorder is shared by concurrent environments; install its wrapper once.
        recorder = self.datastream.get_env().recorder_manager
        if not getattr(recorder, '_openarm_telemetry_installed', False):
            from export_timing import export_scope, install as install_export_timing
            install_export_timing(recorder)
            original_export = recorder.export_episodes

            @functools.wraps(original_export)
            def tracked_export(*export_args, **export_kwargs):
                current = _episode_context.get()
                if current is None:
                    return original_export(*export_args, **export_kwargs)
                started, previous = telemetry.stage_started(current, 'export')
                export_error = None
                try:
                    with export_scope(telemetry.emit, **telemetry.episode_values(current)):
                        result = original_export(*export_args, **export_kwargs)
                    current['export_calls'] += 1
                    return result
                except BaseException as exc:
                    export_error = error_text(exc)
                    raise
                finally:
                    telemetry.stage_finished(current, 'export', started, previous, export_error)

            recorder.export_episodes = tracked_export
            recorder._openarm_telemetry_installed = True
        try:
            result = await original_generate(self, env_id, *args, **kwargs)
            success = bool(result.success)
            return result
        except asyncio.CancelledError as exc:
            cancelled, error = True, error_text(exc)
            raise
        except BaseException as exc:
            success, error = False, error_text(exc)
            raise
        finally:
            _episode_context.reset(token)
            telemetry.finish_episode(episode, success, error, cancelled)

    generator_class.generate = tracked_generate
    original_reset = generator_class._reset_environment_for_generation

    @functools.wraps(original_reset)
    async def tracked_reset(self, *args, **kwargs):
        episode = _episode_context.get()
        if episode is None:
            return await original_reset(self, *args, **kwargs)
        started, previous = telemetry.stage_started(episode, 'reset')
        error = None
        try:
            return await original_reset(self, *args, **kwargs)
        except BaseException as exc:
            error = error_text(exc)
            raise
        finally:
            telemetry.stage_finished(episode, 'reset', started, previous, error)

    generator_class._reset_environment_for_generation = tracked_reset
    waypoint_class = data_generator_module.MultiWaypoint
    original_execute = waypoint_class.execute

    @functools.wraps(original_execute)
    async def tracked_execute(self, *args, **kwargs):
        episode = _episode_context.get()
        started = time.monotonic()
        result = await original_execute(self, *args, **kwargs)
        if episode is not None:
            episode['execution_steps'] += 1
            episode['execution_wait_seconds'] += time.monotonic() - started
            episode['stage'] = 'execution'
            if episode['execution_steps'] % 100 == 0:
                telemetry.emit('execution_progress', **telemetry.episode_values(episode),
                               execution_steps=episode['execution_steps'],
                               execution_wait_seconds=episode['execution_wait_seconds'])
        return result

    waypoint_class.execute = tracked_execute
    planner_class = planner_module.CuroboPlanner
    original_motion = planner_class.update_world_and_plan_motion

    @functools.wraps(original_motion)
    def tracked_motion(self, *args, **kwargs):
        episode = _episode_context.get()
        if episode is None:
            return original_motion(self, *args, **kwargs)
        started, previous = telemetry.stage_started(episode, 'motion_plan')
        error = None
        try:
            return original_motion(self, *args, **kwargs)
        except BaseException as exc:
            error = error_text(exc)
            raise
        finally:
            telemetry.stage_finished(episode, 'motion_plan', started, previous, error)

    planner_class.update_world_and_plan_motion = tracked_motion
    original_plan = planner_class._plan_to_contact_pose

    @functools.wraps(original_plan)
    def tracked_plan(self, *args, **kwargs):
        episode = _episode_context.get()
        telemetry.request_count += 1
        request = {'request_id': telemetry.request_count, 'episode_id': episode['key'] if episode else None,
                   'env_id': getattr(self, 'env_id', None), 'iterations': 0, 'successes': 0,
                   'iteration_instrumentation_available': solver_instrumented}
        token = _request_context.set(request)
        fields = {k: request[k] for k in ('request_id', 'episode_id', 'env_id')}
        telemetry.emit('planner_request_started', **fields, contact_phase=kwargs.get('contact'),
                       configured_solver_max_attempts=getattr(self.plan_config, 'max_attempts', None))
        started, success, error = time.monotonic(), None, None
        try:
            success = bool(original_plan(self, *args, **kwargs))
            return success
        except BaseException as exc:
            error = error_text(exc)
            raise
        finally:
            _request_context.reset(token)
            if episode is not None:
                episode['planner_calls'] += 1
                episode['planner_successes' if success else 'planner_failures'] += 1
                episode['solver_iterations'] += request['iterations']
                episode['solver_successes'] += request['successes']
            telemetry.emit('planner_request_finished', **fields, success=success, error=error,
                           duration_seconds=time.monotonic() - started,
                           curobo_solver_iterations=request['iterations'],
                           curobo_iteration_successes=request['successes'],
                           iteration_instrumentation_available=solver_instrumented)

    # Count actual outer cuRobo attempts, without counting each IK/trajopt seed as an attempt.
    from curobo.wrap.reacher.motion_gen import MotionGen
    solver_instrumented = False
    for name in ('_plan_from_solve_state', '_plan_from_solve_state_batch'):
        original = getattr(MotionGen, name, None)
        if original is None:
            continue
        solver_instrumented = True

        def wrap_solver(method):
            @functools.wraps(method)
            def tracked_solver(self, *args, **kwargs):
                request = _request_context.get()
                if request is None:
                    return method(self, *args, **kwargs)
                request['iterations'] += 1
                fields = {k: request[k] for k in ('request_id', 'episode_id', 'env_id')}
                fields['iteration'] = request['iterations']
                telemetry.emit('solver_iteration_started', **fields)
                started, result, error = time.monotonic(), None, None
                try:
                    result = method(self, *args, **kwargs)
                    return result
                except BaseException as exc:
                    error = error_text(exc)
                    raise
                finally:
                    success = result_success(result) if result is not None else False
                    request['successes'] += int(success is True)
                    diagnostics = {}
                    for field in ('solve_time', 'ik_time', 'graph_time', 'trajopt_time', 'trajopt_attempts'):
                        value = getattr(result, field, None)
                        if isinstance(value, (int, float, str, bool)) or value is None:
                            diagnostics[field] = value
                    telemetry.emit('solver_iteration_finished', **fields, success=success,
                                   status=str(getattr(result, 'status', None)), error=error,
                                   duration_seconds=time.monotonic() - started, curobo_reported=diagnostics)
            return tracked_solver

        setattr(MotionGen, name, wrap_solver(original))
    telemetry.emit('instrumentation_ready', solver_iteration_instrumentation=solver_instrumented)
    planner_class._plan_to_contact_pose = tracked_plan
