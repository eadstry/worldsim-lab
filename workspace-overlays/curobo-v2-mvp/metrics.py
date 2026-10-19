# SPDX-FileCopyrightText: 2026 OpenAI
# SPDX-License-Identifier: Apache-2.0
"""Identical synchronized latency and PyTorch memory instrumentation for both backends."""
from __future__ import annotations

import functools
import json
import os
import time
from pathlib import Path


def emit(event: str, **fields) -> None:
    path = Path(os.environ['MVP_METRICS_FILE'])
    with path.open('a') as file:
        file.write(json.dumps(dict(event=event, time_unix=time.time(), backend=os.environ['MVP_BACKEND'], **fields)) + '\n')


def install(planner_class) -> None:
    import torch
    import curobo
    from importlib.metadata import version
    from autodata_core.data_generator import DataGenerator

    emit('runtime', curobo_version=version('nvidia-curobo'), curobo_file=curobo.__file__,
         torch_version=version('torch'), cuda_version=torch.version.cuda,
         gpu_name=torch.cuda.get_device_name(0), pid=os.getpid(),
         planner_file=__import__(planner_class.__module__, fromlist=['x']).__file__)
    original_init = planner_class.__init__

    @functools.wraps(original_init)
    def initialize(self, *args, **kwargs):
        torch.cuda.synchronize()
        before = torch.cuda.memory_allocated()
        started = time.perf_counter()
        original_init(self, *args, **kwargs)
        torch.cuda.synchronize()
        emit('planner_initialized', elapsed_seconds=time.perf_counter() - started,
                 allocated_before_bytes=before, allocated_after_bytes=torch.cuda.memory_allocated(),
                 reserved_after_bytes=torch.cuda.memory_reserved(),
                 profile={name: getattr(self.config, name) for name in [
                     'num_trajopt_seeds', 'num_graph_seeds', 'trajopt_tsteps', 'interpolation_dt',
                     'enable_graph', 'max_planning_attempts', 'position_threshold', 'rotation_threshold',
                     'collision_activation_distance', 'motion_step_size', 'n_repeat']})
        # No later peak reset: keep a comparable session peak, including initialization.
    planner_class.__init__ = initialize
    for name, event in [('update_world_and_plan_motion', 'request'), ('_plan_to_contact_pose', 'phase')]:
        original = getattr(planner_class, name)

        def wrap(method, kind):
            @functools.wraps(method)
            def measured(self, *args, **kwargs):
                torch.cuda.synchronize()
                started, result, error = time.perf_counter(), None, None
                try:
                    result = method(self, *args, **kwargs)
                    return result
                except BaseException as exc:
                    error = f'{type(exc).__name__}: {exc}'
                    raise
                finally:
                    torch.cuda.synchronize()
                    emit(kind, elapsed_seconds=time.perf_counter() - started, success=bool(result) if result is not None else None,
                         error=error, contact=kwargs.get('contact') if kind == 'phase' else None,
                         allocated_bytes=torch.cuda.memory_allocated(), reserved_bytes=torch.cuda.memory_reserved(),
                         peak_allocated_bytes=torch.cuda.max_memory_allocated(), peak_reserved_bytes=torch.cuda.max_memory_reserved())
            return measured
        setattr(planner_class, name, wrap(original, event))
    original_reset = DataGenerator._reset_environment_for_generation
    counter = 0

    @functools.wraps(original_reset)
    async def reset(self, *args, **kwargs):
        nonlocal counter
        import random
        import numpy as np
        seed = int(os.environ['MVP_SEED']) + counter
        counter += 1
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        result = await original_reset(self, *args, **kwargs)
        poses = {k: v.detach().cpu().tolist() for k, v in self.datastream.get_object_poses(env_ids=[0]).items()}
        joints = self.datastream.get_robot_joint_positions(env_ids=[0]).detach().cpu().tolist()
        emit('episode_reset', episode_index=counter - 1, seed=seed, object_poses=poses, joint_positions=joints)
        return result
    DataGenerator._reset_environment_for_generation = reset
