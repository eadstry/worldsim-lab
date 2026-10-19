# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Opt-in host latency attribution, installed only in copied experiment launchers.

Synchronous scopes partition the main thread's wall clock without CUDA fences.
Async execute calls snapshot that shared partition; their overlapping windows must
never be summed to obtain whole-run wall time. Queue.join latency is inclusive.
"""
from __future__ import annotations

import asyncio
import contextvars
import functools
import hashlib
import inspect
import json
import os
import threading
import time
import textwrap
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

_execute = contextvars.ContextVar("internal_execute", default=None)
_profiler = None


class Timeline:
    def __init__(self, clock=time.perf_counter, cpu_clock=time.thread_time):
        self.clock, self.cpu_clock = clock, cpu_clock
        self.owner = threading.get_ident()
        self.stack = ["unattributed"]
        self.wall, self.cpu, self.calls, self.inclusive = Counter(), Counter(), Counter(), Counter()
        self.last, self.last_cpu = clock(), cpu_clock()

    def flush(self):
        now, cpu_now = self.clock(), self.cpu_clock()
        self.wall[self.stack[-1]] += now - self.last
        self.cpu[self.stack[-1]] += cpu_now - self.last_cpu
        self.last, self.last_cpu = now, cpu_now
        return now

    def snapshot(self):
        now = self.flush()
        return now, dict(self.wall), dict(self.cpu)

    @contextmanager
    def scope(self, name):
        if threading.get_ident() != self.owner:
            yield
            return
        start = self.flush()
        self.stack.append(name)
        self.calls[name] += 1
        try:
            yield
        finally:
            end = self.flush()
            self.inclusive[name] += end - start
            assert self.stack.pop() == name


def difference(end, start):
    return {key: end.get(key, 0.0) - start.get(key, 0.0) for key in end.keys() | start.keys()}


class Profiler:
    def __init__(self, output):
        self.timeline = Timeline()
        self.output = Path(output)
        self.journal = self.output.with_suffix(".internal.jsonl")
        self.summary = self.output.with_suffix(".internal-summary.json")
        assert not self.journal.exists() and not self.summary.exists()
        self.begin_snapshot = None
        self.generation_end = None
        self.episodes = {}
        self.finished = []
        self.sources = {}
        self.hooks = []
        self.begin_counts = Counter()
        self.begin_inclusive = Counter()

    def emit(self, event, **values):
        with self.journal.open("a") as stream:
            stream.write(json.dumps({"event": event, "time_monotonic": time.perf_counter(), **values}) + "\n")

    def begin(self):
        assert self.begin_snapshot is None
        self.begin_snapshot = self.timeline.snapshot()
        self.begin_counts = self.timeline.calls.copy()
        self.begin_inclusive = self.timeline.inclusive.copy()
        self.emit("generation_begin", hooks=self.hooks, sources=self.sources,
                  semantics="exclusive main-thread host wall latency; no added CUDA synchronization")

    def window(self, end):
        start = self.begin_snapshot
        return {"wall_seconds": end[0] - start[0],
                "exclusive_wall_seconds": difference(end[1], start[1]),
                "exclusive_thread_cpu_seconds": difference(end[2], start[2])}

    def checkpoint(self, final=False):
        if self.begin_snapshot is None:
            return
        end = self.timeline.snapshot()
        value = {"schema_version": 1, "final": final,
                 "semantics": "host API latency; CUDA work can be deferred to later blocking calls; queue wait and execute attribution are overlapping inclusive metrics",
                 "generation": self.window(self.generation_end) if self.generation_end else None,
                 "through_output_ready": self.window(end),
                 "calls": dict(self.timeline.calls - self.begin_counts),
                 "inclusive_wall_seconds": difference(dict(self.timeline.inclusive), dict(self.begin_inclusive)),
                 "episodes": self.finished, "sources": self.sources, "hooks": self.hooks}
        temporary = self.summary.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(value, indent=2))
        temporary.replace(self.summary)

    def wrap(self, target, name, phase):
        original = getattr(target, name)
        assert not getattr(original, "_internal_timing", False), (target, name)

        @functools.wraps(original)
        def measured(*args, **kwargs):
            with self.timeline.scope(phase):
                return original(*args, **kwargs)

        measured._internal_timing = True
        setattr(target, name, measured)
        self.hooks.append(phase)
        path = inspect.getsourcefile(inspect.unwrap(original))
        if path and Path(path).is_file():
            self.sources[path] = hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ActionQueue(asyncio.Queue):
    async def join(self):
        current = _execute.get()
        started = time.perf_counter()
        try:
            return await super().join()
        finally:
            if current is not None:
                current["queue_join_seconds"] += time.perf_counter() - started


def instrument_source(source):
    replacements = {
        "simulation_app = app_launcher.app": "simulation_app = app_launcher.app\nimport internal_timing as __timing",
        "    random.seed(generation_policy_params.seed)": "    __timing.install(env, success_term)\n    random.seed(generation_policy_params.seed)",
        "    env_action_queue: asyncio.Queue = asyncio.Queue()": "    env_action_queue: asyncio.Queue = __timing.ActionQueue()",
        "generation_completed = env_loop(": "generation_completed = __timing.run_loop(env_loop,",
        "        env.close()": "        __timing.close_env(env)",
    }
    for anchor, replacement in replacements.items():
        assert source.count(anchor) == 1, f"Timing integration anchor changed: {anchor}"
        source = source.replace(anchor, replacement, 1)
    return source


def install(env, success_term):
    global _profiler
    assert _profiler is None
    import telemetry
    from autodata_core import data_generator
    from autodata_interfaces.datastream.datastream import Datastream
    import autodata_interfaces.motion_planners.curobo.curobo_planner as planner
    import openarm_autodata.shared.envs.cameras as cameras
    import export_pool
    import async_export

    p = _profiler = Profiler(json.loads(os.environ["OPENARM_RUN_CONFIG"])["output_file"])
    for target, name, phase in (
        (env, "step", "env_step_other"), (env, "reset", "reset_other"),
        (env.action_manager, "process_action", "action_process"),
        (env.action_manager, "apply_action", "action_apply"),
        (env.scene, "write_data_to_sim", "scene_write"),
        (env.scene, "update", "scene_update"),
        (env.sim, "step", "physics_step"), (env.sim, "render", "render"),
        (env.observation_manager, "compute", "observation_other"),
        (env.recorder_manager, "record_pre_step", "record_pre_other"),
        (env.recorder_manager, "record_post_step", "record_post_other"),
        (env.recorder_manager, "add_to_episodes", "record_buffer_copy"),
        (env.recorder_manager, "export_episodes", "export_producer_other"),
        (Datastream, "target_eef_pose_to_action", "action_prepare"),
        (planner.CuroboPlanner, "update_world_and_plan_motion", "motion_plan"),
        (cameras, "update_mounted_camera_poses", "camera_pose"),
        (success_term, "func", "success_check"),
        (export_pool, "pack", "export_pack"),
        (export_pool.ExportPool, "poll", "export_poll_or_backpressure"),
        (export_pool.ExportPool, "_merge", "export_merge"),
        (async_export, "finish", "export_drain_other"),
        (type(env.sim.render_context), "update_transforms", "render_scene_transforms"),
    ):
        p.wrap(target, name, phase)

    # Camera.data drives lazy rendering in this IsaacLab version. Split the
    # renderer and output read from the subsequent explicit CPU transfer.
    renderers = {}
    for name in cameras.CAMERA_NAMES:
        camera = env.scene[name]
        assert camera._renderer is not None
        renderers[id(camera._renderer)] = camera._renderer
    for renderer in renderers.values():
        p.wrap(renderer, "render", "camera_render")
        p.wrap(renderer, "read_output", "camera_output_read")

    source = textwrap.dedent(inspect.getsource(cameras.rgb_image))
    anchor = '    return env.scene[name].data.output["rgb"].torch[..., :3].to(device="cpu", copy=True)'
    assert source.count(anchor) == 1, "Camera RGB hook changed; review copy semantics"
    source = source.replace(anchor, '''    with __timing_profiler.timeline.scope("camera_data_other"):
        rgb = env.scene[name].data.output["rgb"].torch[..., :3]
    with __timing_profiler.timeline.scope("rgb_cpu_copy"):
        return rgb.to(device="cpu", copy=True)''', 1)
    namespace = dict(cameras.rgb_image.__globals__, __timing_profiler=p)
    exec(compile(source, inspect.getsourcefile(cameras.rgb_image), "exec"), namespace)
    measured_rgb = namespace["rgb_image"]
    camera_hooks = 0
    for configs in env.observation_manager._group_obs_term_cfgs.values():
        for config in configs:
            if getattr(config.func, "__name__", "") == "rgb_image":
                config.func = measured_rgb
                p.wrap(config, "func", "rgb_readback_other")
                camera_hooks += 1
    assert camera_hooks == 3, f"Expected three RGB observation hooks, got {camera_hooks}"

    loop = asyncio.get_event_loop()
    p.wrap(loop, "run_until_complete", "scheduler_other")
    original_execute = data_generator.MultiWaypoint.execute

    @functools.wraps(original_execute)
    async def measured_execute(self, *args, **kwargs):
        episode = telemetry._episode_context.get()
        if episode is None or p.begin_snapshot is None:
            return await original_execute(self, *args, **kwargs)
        current = {"queue_join_seconds": 0.0}
        token = _execute.set(current)
        start = p.timeline.snapshot()
        completed = False
        try:
            result = await original_execute(self, *args, **kwargs)
            completed = True
            return result
        finally:
            end = p.timeline.snapshot()
            _execute.reset(token)
            stats = p.episodes.setdefault(episode["key"], {
                "episode_id": episode["key"], "env_id": episode["env_id"],
                "execute_calls": 0, "cancelled_execute_calls": 0,
                "execute_wall_seconds": 0.0, "queue_join_seconds": 0.0,
                "exclusive_during_execute_seconds": Counter()})
            if completed:
                stats["execute_calls"] += 1
                stats["execute_wall_seconds"] += end[0] - start[0]
                stats["queue_join_seconds"] += current["queue_join_seconds"]
                stats["exclusive_during_execute_seconds"].update(difference(end[1], start[1]))
            else:
                stats["cancelled_execute_calls"] += 1

    data_generator.MultiWaypoint.execute = measured_execute
    original_emit = telemetry.Telemetry.emit

    @functools.wraps(original_emit)
    def measured_emit(instance, event, **values):
        result = original_emit(instance, event, **values)
        if threading.get_ident() != p.timeline.owner:
            return result
        if event in ("episode_finished", "episode_cancelled"):
            stats = p.episodes.pop(values["episode_id"], None)
            if stats is not None:
                stats.update(outcome=event, success=values.get("success"),
                             episode_wall_seconds=values["duration_seconds"],
                             telemetry_execute_seconds=values["stages_seconds"]["execution_wait"])
                p.finished.append(stats)
                p.emit("episode_internal", **stats)
                p.checkpoint()
        elif event == "execution_progress":
            stats = p.episodes.get(values["episode_id"])
            if stats is not None:
                p.emit("execute_internal_progress", **stats)
                p.checkpoint()
        elif event == "output_ready":
            p.checkpoint(final=True)
        return result

    telemetry.Telemetry.emit = measured_emit
    p.emit("instrumentation_installed", camera_observation_hooks=camera_hooks, hooks=p.hooks)


def run_loop(loop, *args, **kwargs):
    p = _profiler
    p.begin()
    try:
        return loop(*args, **kwargs)
    finally:
        p.generation_end = p.timeline.snapshot()
        p.emit("generation_end", **p.window(p.generation_end))
        p.checkpoint()


def close_env(env):
    with _profiler.timeline.scope("env_close_other"):
        return env.close()
